#!/usr/bin/env python3
"""Source-bound node-local and Kubernetes action/evidence adapters."""

from __future__ import annotations

import copy
import base64
import fcntl
import hashlib
import hmac
import json
import os
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from state_machine import (
    ABSENCE_SCHEMA,
    ACTION_RECEIPT_SCHEMA,
    GPU_RELEASE_SCHEMA,
    OPERATION_ABSENCE_SCHEMA,
    ActionReceipt,
    ControllerFence,
    GpuReleaseProof,
    LaunchOperationAbsenceProof,
    LaunchReservation,
    NvmlObservation,
    ProofRejected,
    RuntimeAbsenceProof,
    RuntimeAuthority,
    RuntimeIdentity,
    ScrubReceipt,
    canonical_json,
    canonical_sha256,
    key_sha256,
    sign_payload,
)


COMMAND_SCHEMA = "archvteams.nebius.ai/catalog-switch-command-envelope/v1"
AGENT_ATTESTATION_SCHEMA = "archvteams.nebius.ai/catalog-switch-agent-attestation/v1"
DEFAULT_NODE_AGENT_EXECUTABLE = "/usr/local/libexec/catalog-switch-agent"
DEFAULT_K8S_AGENT_EXECUTABLE = "/usr/local/libexec/catalog-switch-k8s-agent"


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, argv: Sequence[str]) -> CommandResult: ...


class SubprocessRunner:
    def run(self, argv: Sequence[str]) -> CommandResult:
        completed = subprocess.run(list(argv), check=False, capture_output=True, text=True)
        return CommandResult(tuple(argv), completed.returncode, completed.stdout, completed.stderr)


@dataclass(frozen=True)
class CommandEnvelope:
    schema: str
    command_id: str
    idempotency_key: str
    command_sequence: int
    switch_id: str
    operation: str
    subject_sha256: str
    controller_id: str
    controller_lease_id: str
    controller_generation: int
    authority_sha256: str
    issued_at_ns: int
    expires_at_ns: int
    argv_sha256: str
    admission_policy_sha256: str
    signer_id: str
    signer_key_sha256: str
    signature_sha256: str

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("signature_sha256")
        return value

    @property
    def digest(self) -> str:
        return canonical_sha256(asdict(self))


class ControllerCommandSigner:
    def __init__(self, *, signer_id: str, key: bytes):
        self.signer_id = signer_id
        self.key = key

    def create(
        self,
        *,
        command_id: str,
        idempotency_key: str,
        command_sequence: int,
        switch_id: str,
        operation: str,
        subject_sha256: str,
        fence: ControllerFence,
        authority: RuntimeAuthority,
        argv: Sequence[str],
        admission_policy_sha256: str,
        issued_at_ns: int,
        expires_at_ns: int,
    ) -> CommandEnvelope:
        payload = {
            "schema": COMMAND_SCHEMA,
            "command_id": command_id,
            "idempotency_key": idempotency_key,
            "command_sequence": command_sequence,
            "switch_id": switch_id,
            "operation": operation,
            "subject_sha256": subject_sha256,
            "controller_id": fence.controller_id,
            "controller_lease_id": fence.lease_id,
            "controller_generation": fence.generation,
            "authority_sha256": authority.digest,
            "issued_at_ns": issued_at_ns,
            "expires_at_ns": expires_at_ns,
            "argv_sha256": canonical_sha256(list(argv)),
            "admission_policy_sha256": admission_policy_sha256,
            "signer_id": self.signer_id,
            "signer_key_sha256": key_sha256(self.key),
        }
        return CommandEnvelope(**payload, signature_sha256=sign_payload(self.key, payload))


@dataclass(frozen=True)
class CommandAdmissionPolicy:
    """Exact executable allowlist evaluated by the agent, not just a hash label."""

    operation_executables: dict[str, tuple[str, ...]]
    allowed_artifact_sha256s: tuple[str, ...]

    @property
    def digest(self) -> str:
        return canonical_sha256(
            {
                "schema": "archvteams.nebius.ai/catalog-switch-command-policy/v1",
                "operation_executables": self.operation_executables,
                "allowed_artifact_sha256s": sorted(self.allowed_artifact_sha256s),
                "shell_forbidden": True,
            }
        )

    def authorize(
        self,
        envelope: CommandEnvelope,
        argv: Sequence[str],
        authority: RuntimeAuthority,
    ) -> None:
        allowed = self.operation_executables.get(envelope.operation)
        if not argv or allowed is None or argv[0] not in allowed:
            raise ProofRejected("command operation/executable is outside admission policy")
        if any(not isinstance(value, str) or "\x00" in value for value in argv):
            raise ProofRejected("command argv contains invalid bytes")
        if argv[0] in {"sh", "bash", "/bin/sh", "/bin/bash"} or any(
            value in {"--privileged", "--host-network", "--host-pid"} for value in argv
        ):
            raise ProofRejected("command privilege profile is outside admission policy")
        subcommands = {
            "stop-runtime": "stop",
            "cleanup-launch-operation": "cleanup-operation",
            "launch-runtime": "launch",
            "scrub-gpu": "scrub-gpu",
            "revoke-placement-lease": "revoke-placement",
            "noop": "noop",
        }
        expected_subcommand = subcommands[envelope.operation]
        if len(argv) < 2:
            raise ProofRejected("command omits its exact operation subcommand")
        if argv[1] != expected_subcommand:
            if envelope.operation != "stop-runtime" or not self._is_kubectl_stop(
                argv, authority
            ):
                raise ProofRejected("command subcommand/argument grammar is outside policy")
        else:
            self._authorize_agent_argv(envelope.operation, argv, authority)
        if envelope.operation == "launch-runtime":
            try:
                artifact = argv[argv.index("--artifact-sha256") + 1]
            except (ValueError, IndexError) as exc:
                raise ProofRejected("launch command omits artifact digest") from exc
            if artifact not in self.allowed_artifact_sha256s:
                raise ProofRejected("launch artifact is outside admission policy")

    @staticmethod
    def _options(argv: Sequence[str]) -> dict[str, str]:
        tail = list(argv[2:])
        if len(tail) % 2:
            raise ProofRejected("agent command options are not exact flag/value pairs")
        options: dict[str, str] = {}
        for index in range(0, len(tail), 2):
            flag, value = tail[index], tail[index + 1]
            if not flag.startswith("--") or not value or flag in options:
                raise ProofRejected("agent command options are malformed or duplicated")
            options[flag] = value
        return options

    @classmethod
    def _authorize_agent_argv(
        cls,
        operation: str,
        argv: Sequence[str],
        authority: RuntimeAuthority,
    ) -> None:
        if operation == "noop":
            if len(argv) != 2:
                raise ProofRejected("noop command has unexpected arguments")
            return
        options = cls._options(argv)
        allowed_sets = {
            "stop-runtime": [{"--runtime-uid", "--pid", "--start-ticks"}],
            "cleanup-launch-operation": [
                {"--operation-id", "--generation"},
                {"--operation-id", "--generation", "--cluster-uid", "--namespace"},
            ],
            "launch-runtime": [
                {"--operation-id", "--generation", "--artifact-sha256"},
                {
                    "--operation-id",
                    "--generation",
                    "--artifact-sha256",
                    "--cluster-uid",
                    "--namespace",
                },
            ],
            "scrub-gpu": [
                {
                    "--gpu-uuid",
                    "--subject-sha256",
                    "--method",
                    "--total-memory-bytes",
                }
            ],
            "revoke-placement-lease": [
                {"--placement-lease-id", "--node-uid"},
                {
                    "--placement-lease-id",
                    "--cluster-uid",
                    "--node-uid",
                    "--namespace",
                },
            ],
        }[operation]
        if set(options) not in allowed_sets:
            raise ProofRejected("agent command exact option set is outside policy")
        if "--cluster-uid" in options and options["--cluster-uid"] != authority.cluster_uid:
            raise ProofRejected("agent command cluster UID differs from authority")
        if "--namespace" in options and options["--namespace"] != authority.namespace:
            raise ProofRejected("agent command namespace differs from authority")
        if "--node-uid" in options and options["--node-uid"] != authority.node_uid:
            raise ProofRejected("agent command node UID differs from authority")
        if "--placement-lease-id" in options and (
            options["--placement-lease-id"] != authority.placement_lease_id
        ):
            raise ProofRejected("agent command placement lease differs from authority")

    @staticmethod
    def _is_kubectl_stop(
        argv: Sequence[str], authority: RuntimeAuthority
    ) -> bool:
        return (
            authority.backend == "kubernetes"
            and len(argv) == 11
            and argv[1] == "--kubeconfig"
            and Path(argv[2]).is_absolute()
            and tuple(argv[3:6])
            == ("--context", authority.kube_context, "delete")
            and argv[6] == "pod"
            and bool(argv[7])
            and tuple(argv[8:])
            == ("--namespace", authority.namespace, "--wait=true")
        )


class ActionJournal:
    """Durable idempotency and command-sequence journal for one exact agent."""

    def __init__(self, path: Path):
        self.path = path
        self.lock_path = path.with_name(path.name + ".lock")

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists() and self.lock_path.is_symlink():
            raise ProofRejected("action journal lock path is unsafe")
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        stream = os.fdopen(descriptor, "r+")
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            stream.close()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"last_sequence": -1, "operations": {}, "receipts": {}}
        if self.path.is_symlink() or not self.path.is_file():
            raise ProofRejected("action journal path is unsafe")
        raw = self.path.read_text(encoding="ascii")
        value = json.loads(raw)
        if raw != canonical_json(value) + "\n":
            raise ProofRejected("action journal is not canonical")
        if set(value) != {"last_sequence", "operations", "receipts"}:
            raise ProofRejected("action journal shape differs")
        return value

    def store(self, value: dict[str, Any]) -> None:
        if self.path.exists() and (self.path.is_symlink() or not self.path.is_file()):
            raise ProofRejected("action journal path is unsafe")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="ascii") as stream:
                stream.write(canonical_json(value) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class FencedActionExecutor:
    """Concrete agent-side mutation gate; stale commands never reach the runner."""

    def __init__(
        self,
        *,
        authority: RuntimeAuthority,
        controller_keys: dict[str, bytes],
        agent_key: bytes,
        current_fence: Callable[[], ControllerFence],
        admission_policy: CommandAdmissionPolicy,
        journal: ActionJournal,
        runner: CommandRunner | None = None,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ):
        self.authority = authority
        self.controller_keys = controller_keys
        self.agent_key = agent_key
        self.current_fence = current_fence
        self.admission_policy = admission_policy
        self.journal = journal
        self.runner = runner or SubprocessRunner()
        self.clock_ns = clock_ns
        if key_sha256(agent_key) != authority.node_agent_key_sha256:
            raise ValueError("agent key differs from authority binding")

    def execute(self, envelope: CommandEnvelope, argv: Sequence[str]) -> ActionReceipt:
        with self.journal.locked():
            return self._execute_locked(envelope, argv)

    def _execute_locked(self, envelope: CommandEnvelope, argv: Sequence[str]) -> ActionReceipt:
        if envelope.schema != COMMAND_SCHEMA:
            raise ProofRejected("command envelope schema differs")
        key = self.controller_keys.get(envelope.signer_id)
        if key is None or key_sha256(key) != envelope.signer_key_sha256:
            raise ProofRejected("command signer is untrusted")
        if not hmac.compare_digest(sign_payload(key, envelope.payload()), envelope.signature_sha256):
            raise ProofRejected("command signature differs")
        if envelope.authority_sha256 != self.authority.digest:
            raise ProofRejected("command targets a different node/cluster authority")
        current = self.current_fence()
        if (
            envelope.controller_id,
            envelope.controller_lease_id,
            envelope.controller_generation,
        ) != (
            current.controller_id,
            current.lease_id,
            current.generation,
        ):
            raise ProofRejected("stale controller command was refused before side effect")
        if envelope.argv_sha256 != canonical_sha256(list(argv)):
            raise ProofRejected("command argv differs from signed payload")
        if envelope.admission_policy_sha256 != self.admission_policy.digest:
            raise ProofRejected("command admission-policy hash differs")
        self.admission_policy.authorize(envelope, argv, self.authority)
        now = self.clock_ns()
        if not envelope.issued_at_ns <= now < envelope.expires_at_ns:
            raise ProofRejected("command is not within its signed validity window")
        journal = self.journal.load()
        previous = journal["receipts"].get(envelope.idempotency_key)
        if previous is not None:
            if previous["command_envelope_sha256"] != envelope.digest:
                raise ProofRejected("idempotency key replay differs from original command")
            if envelope.command_sequence < journal["last_sequence"]:
                raise ProofRejected("captured command replay was refused")
            return ActionReceipt(**previous)
        operation = journal["operations"].get(envelope.idempotency_key)
        if operation is not None:
            if operation["command_envelope_sha256"] != envelope.digest:
                raise ProofRejected("idempotency key operation differs from original command")
            raise ProofRejected(
                "physical action outcome is ambiguous or failed; exact cleanup is required"
            )
        if envelope.command_sequence <= journal["last_sequence"]:
            raise ProofRejected("non-monotonic command sequence was refused")
        started = self.clock_ns()
        journal["last_sequence"] = envelope.command_sequence
        journal["operations"][envelope.idempotency_key] = {
            "command_envelope_sha256": envelope.digest,
            "state": "executing",
            "started_at_ns": started,
        }
        # The intent is durable before the side effect. A process death after
        # this fsync leaves an ambiguous operation that is never replayed.
        self.journal.store(journal)
        result = self.runner.run(argv)
        finished = self.clock_ns()
        if result.returncode != 0:
            journal["operations"][envelope.idempotency_key] = {
                "command_envelope_sha256": envelope.digest,
                "state": "failed",
                "started_at_ns": started,
                "finished_at_ns": finished,
                "result_sha256": canonical_sha256(
                    {
                        "returncode": result.returncode,
                        "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
                        "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest(),
                    }
                ),
            }
            self.journal.store(journal)
            raise ProofRejected("physical action failed; no success receipt issued")
        result_attestation: dict[str, Any] | None = None
        if result.stdout:
            try:
                parsed = json.loads(result.stdout)
            except ValueError as exc:
                raise ProofRejected("physical action stdout is not structured evidence") from exc
            if not isinstance(parsed, dict):
                raise ProofRejected("physical action result attestation is not an object")
            result_attestation = parsed
        raw = {
            "argv": list(result.argv),
            "returncode": result.returncode,
            "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest(),
        }
        payload = {
            "schema": ACTION_RECEIPT_SCHEMA,
            "switch_id": envelope.switch_id,
            "operation": envelope.operation,
            "subject_sha256": envelope.subject_sha256,
            "command_envelope_sha256": envelope.digest,
            "controller_id": envelope.controller_id,
            "controller_lease_id": envelope.controller_lease_id,
            "controller_generation": envelope.controller_generation,
            "idempotency_key": envelope.idempotency_key,
            "source_authority_sha256": self.authority.digest,
            "source_id": self.authority.node_agent_id,
            "source_key_sha256": key_sha256(self.agent_key),
            "started_at_ns": started,
            "finished_at_ns": finished,
            "outcome": "completed",
            "result_attestation": result_attestation,
            "raw_evidence_sha256": canonical_sha256(raw),
        }
        receipt = ActionReceipt(**payload, signature_sha256=sign_payload(self.agent_key, payload))
        journal["operations"][envelope.idempotency_key] = {
            "command_envelope_sha256": envelope.digest,
            "state": "completed",
            "started_at_ns": started,
            "finished_at_ns": finished,
        }
        journal["receipts"][envelope.idempotency_key] = asdict(receipt)
        self.journal.store(journal)
        return receipt


def _require_action_target(
    envelope: CommandEnvelope,
    *,
    operation: str,
    subject_sha256: str,
    authority: RuntimeAuthority,
) -> None:
    if (
        envelope.operation,
        envelope.subject_sha256,
        envelope.authority_sha256,
    ) != (operation, subject_sha256, authority.digest):
        raise ProofRejected("signed command operation/subject/authority differs")


class NodeLocalActions:
    """Exact node-agent commands; runner execution is always fenced above."""

    def __init__(
        self,
        executor: FencedActionExecutor,
        *,
        agent_executable: str = DEFAULT_NODE_AGENT_EXECUTABLE,
    ):
        if not Path(agent_executable).is_absolute():
            raise ValueError("node agent executable must be absolute")
        self.executor = executor
        self.agent_executable = agent_executable

    def stop_runtime(self, envelope: CommandEnvelope, runtime: RuntimeIdentity) -> ActionReceipt:
        if runtime.backend != "node-local" or runtime.authority != self.executor.authority:
            raise ProofRejected("node-local action received Kubernetes runtime")
        _require_action_target(
            envelope,
            operation="stop-runtime",
            subject_sha256=runtime.digest,
            authority=self.executor.authority,
        )
        argv = (self.agent_executable, "stop", "--runtime-uid", runtime.runtime_uid, "--pid", str(runtime.host_pid), "--start-ticks", str(runtime.process_start_ticks))
        return self.executor.execute(envelope, argv)

    def cleanup_launch(self, envelope: CommandEnvelope, reservation: LaunchReservation) -> ActionReceipt:
        if (
            reservation.backend != "node-local"
            or reservation.authority_sha256 != self.executor.authority.digest
        ):
            raise ProofRejected("node-local cleanup reservation authority differs")
        _require_action_target(
            envelope,
            operation="cleanup-launch-operation",
            subject_sha256=reservation.digest,
            authority=self.executor.authority,
        )
        argv = (self.agent_executable, "cleanup-operation", "--operation-id", reservation.operation_id, "--generation", str(reservation.runtime_generation))
        return self.executor.execute(envelope, argv)

    def launch(self, envelope: CommandEnvelope, reservation: LaunchReservation) -> ActionReceipt:
        if (
            reservation.backend != "node-local"
            or reservation.authority_sha256 != self.executor.authority.digest
        ):
            raise ProofRejected("node-local launch reservation authority differs")
        if envelope.idempotency_key != reservation.idempotency_key:
            raise ProofRejected("node-local launch idempotency differs from reservation")
        _require_action_target(
            envelope,
            operation="launch-runtime",
            subject_sha256=reservation.digest,
            authority=self.executor.authority,
        )
        argv = (self.agent_executable, "launch", "--operation-id", reservation.operation_id, "--generation", str(reservation.runtime_generation), "--artifact-sha256", reservation.model.artifact_sha256)
        return self.executor.execute(envelope, argv)

    def revoke_placement(self, envelope: CommandEnvelope) -> ActionReceipt:
        authority = self.executor.authority
        _require_action_target(
            envelope,
            operation="revoke-placement-lease",
            subject_sha256=authority.placement_subject_sha256,
            authority=authority,
        )
        argv = (
            self.agent_executable,
            "revoke-placement",
            "--placement-lease-id",
            authority.placement_lease_id,
            "--node-uid",
            authority.node_uid,
        )
        return self.executor.execute(envelope, argv)


class KubernetesActions:
    def __init__(
        self,
        executor: FencedActionExecutor,
        *,
        kubeconfig: Path,
        context: str,
        kubectl_executable: Path,
        agent_executable: str = DEFAULT_K8S_AGENT_EXECUTABLE,
    ):
        if executor.authority.backend != "kubernetes":
            raise ValueError("Kubernetes actions require Kubernetes authority")
        if kubeconfig.is_symlink():
            raise ValueError("Kubernetes action kubeconfig cannot be a symlink")
        if not kubectl_executable.is_absolute() or not Path(agent_executable).is_absolute():
            raise ValueError("Kubernetes executables must use absolute paths")
        self.executor = executor
        self.kubeconfig = kubeconfig.resolve()
        self.context = context
        self.kubectl_executable = kubectl_executable
        self.agent_executable = agent_executable

    def _preflight(self) -> None:
        _verify_kubernetes_authority(
            authority=self.executor.authority,
            kubeconfig=self.kubeconfig,
            context=self.context,
            kubectl_executable=self.kubectl_executable,
            runner=self.executor.runner,
        )

    def stop_runtime(self, envelope: CommandEnvelope, runtime: RuntimeIdentity) -> ActionReceipt:
        if runtime.backend != "kubernetes" or runtime.authority != self.executor.authority:
            raise ProofRejected("Kubernetes action received node-local runtime")
        _require_action_target(
            envelope,
            operation="stop-runtime",
            subject_sha256=runtime.digest,
            authority=self.executor.authority,
        )
        self._preflight()
        argv = (
            str(self.kubectl_executable),
            "--kubeconfig",
            str(self.kubeconfig),
            "--context",
            self.context,
            "delete",
            "pod",
            str(runtime.pod_name),
            "--namespace",
            str(runtime.authority.namespace),
            "--wait=true",
        )
        return self.executor.execute(envelope, argv)

    def cleanup_launch(self, envelope: CommandEnvelope, reservation: LaunchReservation) -> ActionReceipt:
        if (
            reservation.backend != "kubernetes"
            or reservation.authority_sha256 != self.executor.authority.digest
        ):
            raise ProofRejected("Kubernetes cleanup reservation authority differs")
        _require_action_target(
            envelope,
            operation="cleanup-launch-operation",
            subject_sha256=reservation.digest,
            authority=self.executor.authority,
        )
        self._preflight()
        argv = (
            self.agent_executable,
            "cleanup-operation",
            "--operation-id",
            reservation.operation_id,
            "--generation",
            str(reservation.runtime_generation),
            "--cluster-uid",
            str(self.executor.authority.cluster_uid),
            "--namespace",
            str(self.executor.authority.namespace),
        )
        return self.executor.execute(envelope, argv)

    def launch(self, envelope: CommandEnvelope, reservation: LaunchReservation) -> ActionReceipt:
        if (
            reservation.backend != "kubernetes"
            or reservation.authority_sha256 != self.executor.authority.digest
        ):
            raise ProofRejected("Kubernetes launch reservation authority differs")
        if envelope.idempotency_key != reservation.idempotency_key:
            raise ProofRejected("Kubernetes launch idempotency differs from reservation")
        _require_action_target(
            envelope,
            operation="launch-runtime",
            subject_sha256=reservation.digest,
            authority=self.executor.authority,
        )
        self._preflight()
        argv = (
            self.agent_executable,
            "launch",
            "--operation-id",
            reservation.operation_id,
            "--generation",
            str(reservation.runtime_generation),
            "--artifact-sha256",
            reservation.model.artifact_sha256,
            "--cluster-uid",
            str(self.executor.authority.cluster_uid),
            "--namespace",
            str(self.executor.authority.namespace),
        )
        return self.executor.execute(envelope, argv)

    def revoke_placement(self, envelope: CommandEnvelope) -> ActionReceipt:
        authority = self.executor.authority
        _require_action_target(
            envelope,
            operation="revoke-placement-lease",
            subject_sha256=authority.placement_subject_sha256,
            authority=authority,
        )
        self._preflight()
        argv = (
            self.agent_executable,
            "revoke-placement",
            "--placement-lease-id",
            authority.placement_lease_id,
            "--cluster-uid",
            str(authority.cluster_uid),
            "--node-uid",
            authority.node_uid,
            "--namespace",
            str(authority.namespace),
        )
        return self.executor.execute(envelope, argv)


class GpuScrubAdapter:
    """Concrete fenced scrub command and exact-byte scrub receipt producer."""

    def __init__(
        self,
        executor: FencedActionExecutor,
        *,
        agent_executable: str = DEFAULT_NODE_AGENT_EXECUTABLE,
    ):
        if not Path(agent_executable).is_absolute():
            raise ValueError("GPU scrub agent executable must be absolute")
        self.executor = executor
        self.agent_executable = agent_executable

    def scrub(
        self,
        envelope: CommandEnvelope,
        *,
        switch_id: str,
        subject_sha256: str,
        gpu_uuid: str,
        method: str,
        total_memory_bytes: int,
    ) -> tuple[ActionReceipt, ScrubReceipt]:
        if method not in {"full-vram-zero", "gpu-reset", "mig-recreate"}:
            raise ProofRejected("scrub adapter method is not approved")
        if total_memory_bytes < 1:
            raise ProofRejected("scrub adapter total memory is invalid")
        _require_action_target(
            envelope,
            operation="scrub-gpu",
            subject_sha256=subject_sha256,
            authority=self.executor.authority,
        )
        argv = (
            self.agent_executable,
            "scrub-gpu",
            "--gpu-uuid",
            gpu_uuid,
            "--subject-sha256",
            subject_sha256,
            "--method",
            method,
            "--total-memory-bytes",
            str(total_memory_bytes),
        )
        action = self.executor.execute(envelope, argv)
        if (
            action.switch_id,
            action.operation,
            action.subject_sha256,
        ) != (switch_id, "scrub-gpu", subject_sha256):
            raise ProofRejected("scrub action receipt identity differs")
        expected_result = {
            "schema": "archvteams.nebius.ai/catalog-switch-scrub-command-result/v1",
            "gpu_uuid": gpu_uuid,
            "method": method,
            "bytes_scrubbed": total_memory_bytes if method == "full-vram-zero" else 0,
            "total_memory_bytes": total_memory_bytes,
            "completed": True,
        }
        if action.result_attestation != expected_result:
            raise ProofRejected("scrub command did not attest exact GPU/method/byte result")
        scrub = ScrubReceipt(
            schema="archvteams.nebius.ai/catalog-switch-gpu-scrub/v2",
            switch_id=switch_id,
            subject_sha256=subject_sha256,
            gpu_uuid=gpu_uuid,
            method=method,
            bytes_scrubbed=int(action.result_attestation["bytes_scrubbed"]),
            total_memory_bytes=int(action.result_attestation["total_memory_bytes"]),
            started_at_ns=action.started_at_ns,
            finished_at_ns=action.finished_at_ns,
            succeeded=True,
            raw_evidence_sha256=canonical_sha256(asdict(action)),
        )
        scrub.validate_for(switch_id, subject_sha256, gpu_uuid)
        return action, scrub


def _verify_kubernetes_authority(
    *,
    authority: RuntimeAuthority,
    kubeconfig: Path,
    context: str,
    kubectl_executable: Path,
    runner: CommandRunner,
) -> None:
    resolved = kubeconfig.resolve()
    if context != authority.kube_context:
        raise ProofRejected("Kubernetes context differs from runtime authority")
    if resolved.is_symlink() or not resolved.is_file():
        raise ProofRejected("kubeconfig is not an exact regular file")
    if (
        not kubectl_executable.is_absolute()
        or kubectl_executable.is_symlink()
        or not kubectl_executable.is_file()
    ):
        raise ProofRejected("kubectl executable is not an exact absolute regular file")
    if (
        hashlib.sha256(kubectl_executable.read_bytes()).hexdigest()
        != authority.kubectl_executable_sha256
    ):
        raise ProofRejected("kubectl executable bytes differ from runtime authority")
    if hashlib.sha256(resolved.read_bytes()).hexdigest() != authority.kubeconfig_sha256:
        raise ProofRejected("kubeconfig bytes differ from runtime authority")
    base = (
        str(kubectl_executable),
        "--kubeconfig",
        str(resolved),
        "--context",
        context,
    )
    config_cmd = (*base, "config", "view", "--minify", "--raw", "--output", "json")
    result = runner.run(config_cmd)
    if result.returncode != 0:
        raise ProofRejected("cannot verify exact Kubernetes context")
    try:
        config = json.loads(result.stdout)
        clusters = config["clusters"]
        if len(clusters) != 1:
            raise ProofRejected("Kubernetes context did not resolve exactly one cluster")
        cluster = clusters[0]["cluster"]
        ca_data = base64.b64decode(
            cluster.get("certificate-authority-data", ""), validate=True
        )
    except (KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ProofRejected("Kubernetes context/server CA data is malformed") from exc
    if (
        cluster.get("server") != authority.api_server_url
        or hashlib.sha256(ca_data).hexdigest() != authority.server_ca_sha256
    ):
        raise ProofRejected("Kubernetes API server/CA differs from runtime authority")
    uid_cmd = (*base, "get", "namespace", "kube-system", "--output", "json")
    uid_result = runner.run(uid_cmd)
    try:
        cluster_uid = json.loads(uid_result.stdout)["metadata"]["uid"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ProofRejected("Kubernetes cluster UID response is malformed") from exc
    if uid_result.returncode != 0 or cluster_uid != authority.cluster_uid:
        raise ProofRejected("Kubernetes cluster UID differs from runtime authority")
    node_cmd = (*base, "get", "node", authority.node_id, "--output", "json")
    node_result = runner.run(node_cmd)
    try:
        node = json.loads(node_result.stdout)
        node_uid = node["metadata"]["uid"]
        boot_id = node["status"]["nodeInfo"]["bootID"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ProofRejected("Kubernetes node identity response is malformed") from exc
    if (
        node_result.returncode != 0
        or node_uid != authority.node_uid
        or boot_id != authority.node_boot_id
    ):
        raise ProofRejected("Kubernetes node UID/boot differs from runtime authority")

@dataclass(frozen=True)
class AgentRuntimeObservation:
    schema: str
    authority_sha256: str
    runtime_identity_sha256: str
    observed_at_ns: int
    process_absent: bool
    cgroup_empty: bool
    container_absent: bool
    mounts_absent: bool
    namespaces_absent: bool
    credentials_revoked: bool
    kernel_residue_safe: bool
    logs_purged: bool
    sockets_absent: bool
    raw_evidence_sha256: str
    source_id: str
    source_key_sha256: str
    signature_sha256: str

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("signature_sha256")
        return value


@dataclass(frozen=True)
class AgentOperationObservation:
    schema: str
    authority_sha256: str
    reservation_sha256: str
    observed_at_ns: int
    launch_journal_terminal: str
    process_absent: bool
    cgroup_absent: bool
    container_absent: bool
    mounts_absent: bool
    namespaces_absent: bool
    credentials_revoked: bool
    kernel_residue_safe: bool
    raw_evidence_sha256: str
    source_id: str
    source_key_sha256: str
    signature_sha256: str

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("signature_sha256")
        return value


class NodeAgentClient(Protocol):
    def observe_runtime(self, runtime: RuntimeIdentity) -> AgentRuntimeObservation: ...

    def observe_operation(self, reservation: LaunchReservation) -> AgentOperationObservation: ...

    def sign(self, payload: dict[str, Any]) -> tuple[str, str, str]: ...


class LocalSignedNodeAgent:
    """Reference on-node evidence producer; paths are evaluated by the agent."""

    def __init__(
        self,
        *,
        authority: RuntimeAuthority,
        key: bytes,
        proc_root: Path = Path("/proc"),
        cgroup_root: Path = Path("/sys/fs/cgroup"),
        container_cli: str | None = None,
        runner: CommandRunner | None = None,
        clock_ns: Callable[[], int] = time.monotonic_ns,
        cleanup_assertions: Callable[[str], dict[str, bool]] | None = None,
        operation_assertions: Callable[[str], dict[str, Any]] | None = None,
    ):
        self.authority = authority
        self.key = key
        self.proc_root = proc_root
        self.cgroup_root = cgroup_root
        self.container_cli = container_cli
        self.runner = runner or SubprocessRunner()
        self.clock_ns = clock_ns
        self.cleanup_assertions = cleanup_assertions or (
            lambda _: (_ for _ in ()).throw(
                ProofRejected("host cleanup probe is not configured")
            )
        )
        self.operation_assertions = operation_assertions or (
            lambda _: (_ for _ in ()).throw(
                ProofRejected("launch-operation cleanup probe is not configured")
            )
        )
        if key_sha256(key) != authority.node_agent_key_sha256:
            raise ValueError("local agent key differs from bound authority")

    def sign(self, payload: dict[str, Any]) -> tuple[str, str, str]:
        return self.authority.node_agent_id, key_sha256(self.key), sign_payload(self.key, payload)

    def _process_absent(self, runtime: RuntimeIdentity) -> tuple[bool, str]:
        stat_path = self.proc_root / str(runtime.host_pid) / "stat"
        try:
            stat = stat_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return True, "pid-not-present"
        close = stat.rfind(")")
        fields = stat[close + 2 :].split() if close >= 0 else []
        if len(fields) <= 19:
            raise ProofRejected("node-agent /proc stat is malformed")
        observed = int(fields[19])
        return observed != runtime.process_start_ticks, f"observed-start-ticks={observed}"

    def _cgroup_empty(self, runtime: RuntimeIdentity) -> tuple[bool, str]:
        relative = Path(runtime.cgroup_path.lstrip("/"))
        if ".." in relative.parts:
            raise ProofRejected("runtime cgroup path attempts traversal")
        path = self.cgroup_root / relative / "cgroup.procs"
        try:
            pids = [line for line in path.read_text().splitlines() if line.strip()]
        except FileNotFoundError:
            return True, "cgroup-absent"
        return not pids, f"cgroup-pids={','.join(pids)}"

    def _container_absent(self, runtime: RuntimeIdentity) -> tuple[bool, str]:
        if runtime.container_id is None:
            return True, "no-container"
        if self.container_cli is None:
            raise ProofRejected("container identity exists without agent runtime CLI")
        result = self.runner.run((self.container_cli, "inspect", runtime.container_id))
        if result.returncode == 0:
            return False, "container-present"
        message = f"{result.stdout}\n{result.stderr}".lower()
        if not any(marker in message for marker in ("not found", "no such", "does not exist")):
            raise ProofRejected("container absence is ambiguous")
        return True, "container-not-found"

    def observe_runtime(self, runtime: RuntimeIdentity) -> AgentRuntimeObservation:
        if runtime.authority != self.authority:
            raise ProofRejected("node agent received runtime for wrong node/boot")
        process_absent, process_detail = self._process_absent(runtime)
        cgroup_empty, cgroup_detail = self._cgroup_empty(runtime)
        container_absent, container_detail = self._container_absent(runtime)
        cleanup = self.cleanup_assertions(runtime.runtime_uid)
        raw = {
            "process": process_detail,
            "cgroup": cgroup_detail,
            "container": container_detail,
            "cleanup": cleanup,
            "node_boot_id": self.authority.node_boot_id,
        }
        payload = {
            "schema": AGENT_ATTESTATION_SCHEMA,
            "authority_sha256": self.authority.digest,
            "runtime_identity_sha256": runtime.digest,
            "observed_at_ns": self.clock_ns(),
            "process_absent": process_absent,
            "cgroup_empty": cgroup_empty,
            "container_absent": container_absent,
            **cleanup,
            "raw_evidence_sha256": canonical_sha256(raw),
            "source_id": self.authority.node_agent_id,
            "source_key_sha256": key_sha256(self.key),
        }
        return AgentRuntimeObservation(**payload, signature_sha256=sign_payload(self.key, payload))

    def observe_operation(self, reservation: LaunchReservation) -> AgentOperationObservation:
        if reservation.authority_sha256 != self.authority.digest:
            raise ProofRejected("node agent received launch operation for wrong node/boot")
        values = self.operation_assertions(reservation.operation_id)
        payload = {
            "schema": AGENT_ATTESTATION_SCHEMA,
            "authority_sha256": self.authority.digest,
            "reservation_sha256": reservation.digest,
            "observed_at_ns": self.clock_ns(),
            **values,
            "raw_evidence_sha256": canonical_sha256(values),
            "source_id": self.authority.node_agent_id,
            "source_key_sha256": key_sha256(self.key),
        }
        return AgentOperationObservation(**payload, signature_sha256=sign_payload(self.key, payload))


def _verify_agent_signature(
    observation: AgentRuntimeObservation | AgentOperationObservation,
    *,
    authority: RuntimeAuthority,
    key: bytes,
) -> None:
    if observation.authority_sha256 != authority.digest:
        raise ProofRejected("agent observation authority differs")
    if observation.source_id != authority.node_agent_id or observation.source_key_sha256 != authority.node_agent_key_sha256:
        raise ProofRejected("agent observation source differs")
    if not hmac.compare_digest(sign_payload(key, observation.payload()), observation.signature_sha256):
        raise ProofRejected("agent observation signature differs")


class NodeLocalEvidenceAdapter:
    def __init__(
        self,
        *,
        authority: RuntimeAuthority,
        node_agent: NodeAgentClient,
        node_agent_verification_key: bytes,
    ):
        if authority.backend != "node-local":
            raise ValueError("node-local adapter requires node-local authority")
        self.authority = authority
        self.node_agent = node_agent
        self.node_agent_verification_key = node_agent_verification_key

    def collect_runtime_absence(self, *, switch_id: str, runtime: RuntimeIdentity) -> RuntimeAbsenceProof:
        if runtime.authority != self.authority:
            raise ProofRejected("node-local adapter runtime authority differs")
        observation = self.node_agent.observe_runtime(runtime)
        _verify_agent_signature(observation, authority=self.authority, key=self.node_agent_verification_key)
        payload = {
            "schema": ABSENCE_SCHEMA,
            "switch_id": switch_id,
            "runtime_identity_sha256": runtime.digest,
            "runtime_uid": runtime.runtime_uid,
            "runtime_generation": runtime.runtime_generation,
            "authority_sha256": self.authority.digest,
            "source_id": observation.source_id,
            "source_key_sha256": observation.source_key_sha256,
            "observed_at_ns": observation.observed_at_ns,
            "process_absent": observation.process_absent,
            "cgroup_empty": observation.cgroup_empty,
            "container_absent": observation.container_absent,
            "pod_absent": None,
            "mounts_absent": observation.mounts_absent,
            "namespaces_absent": observation.namespaces_absent,
            "credentials_revoked": observation.credentials_revoked,
            "kernel_residue_safe": observation.kernel_residue_safe,
            "logs_purged": observation.logs_purged,
            "sockets_absent": observation.sockets_absent,
            "raw_evidence_sha256": observation.raw_evidence_sha256,
        }
        source_id, source_key_sha, signature = self.node_agent.sign(payload)
        if (source_id, source_key_sha) != (observation.source_id, observation.source_key_sha256):
            raise ProofRejected("node agent signing identity changed")
        return RuntimeAbsenceProof(**payload, signature_sha256=signature)

    def collect_operation_absence(self, *, switch_id: str, reservation: LaunchReservation) -> LaunchOperationAbsenceProof:
        observation = self.node_agent.observe_operation(reservation)
        _verify_agent_signature(observation, authority=self.authority, key=self.node_agent_verification_key)
        payload = {
            "schema": OPERATION_ABSENCE_SCHEMA,
            "switch_id": switch_id,
            "reservation_sha256": reservation.digest,
            "operation_id": reservation.operation_id,
            "runtime_generation": reservation.runtime_generation,
            "authority_sha256": self.authority.digest,
            "source_id": observation.source_id,
            "source_key_sha256": observation.source_key_sha256,
            "observed_at_ns": observation.observed_at_ns,
            "launch_journal_terminal": observation.launch_journal_terminal,
            "process_absent": observation.process_absent,
            "cgroup_absent": observation.cgroup_absent,
            "container_absent": observation.container_absent,
            "pod_absent": None,
            "mounts_absent": observation.mounts_absent,
            "namespaces_absent": observation.namespaces_absent,
            "credentials_revoked": observation.credentials_revoked,
            "kernel_residue_safe": observation.kernel_residue_safe,
            "raw_evidence_sha256": observation.raw_evidence_sha256,
        }
        _, _, signature = self.node_agent.sign(payload)
        return LaunchOperationAbsenceProof(**payload, signature_sha256=signature)


class KubernetesEvidenceAdapter:
    def __init__(
        self,
        *,
        authority: RuntimeAuthority,
        kubeconfig: Path,
        kubectl_executable: Path,
        runner: CommandRunner,
        node_agent: NodeAgentClient,
        node_agent_verification_key: bytes,
    ):
        if authority.backend != "kubernetes":
            raise ValueError("Kubernetes adapter requires Kubernetes authority")
        if kubeconfig.is_symlink():
            raise ValueError("Kubernetes evidence kubeconfig cannot be a symlink")
        if not kubectl_executable.is_absolute():
            raise ValueError("Kubernetes evidence kubectl must be absolute")
        self.authority = authority
        self.kubeconfig = kubeconfig.resolve()
        self.kubectl_executable = kubectl_executable
        self.runner = runner
        self.node_agent = node_agent
        self.node_agent_verification_key = node_agent_verification_key

    def _base(self) -> tuple[str, ...]:
        return (
            str(self.kubectl_executable),
            "--kubeconfig",
            str(self.kubeconfig),
            "--context",
            str(self.authority.kube_context),
        )

    def _verify_cluster(self) -> None:
        _verify_kubernetes_authority(
            authority=self.authority,
            kubeconfig=self.kubeconfig,
            context=str(self.authority.kube_context),
            kubectl_executable=self.kubectl_executable,
            runner=self.runner,
        )

    def collect_runtime_absence(self, *, switch_id: str, runtime: RuntimeIdentity) -> RuntimeAbsenceProof:
        if runtime.authority != self.authority:
            raise ProofRejected("Kubernetes runtime authority differs")
        self._verify_cluster()
        observation = self.node_agent.observe_runtime(runtime)
        _verify_agent_signature(observation, authority=self.authority, key=self.node_agent_verification_key)
        pods_cmd = (*self._base(), "get", "pods", "--namespace", str(self.authority.namespace), "--output", "json")
        result = self.runner.run(pods_cmd)
        if result.returncode != 0:
            raise ProofRejected("Kubernetes Pod inventory query failed")
        items = json.loads(result.stdout).get("items")
        if not isinstance(items, list):
            raise ProofRejected("Kubernetes Pod inventory is malformed")
        pod_absent = all(item.get("metadata", {}).get("uid") != runtime.pod_uid for item in items)
        payload = {
            "schema": ABSENCE_SCHEMA,
            "switch_id": switch_id,
            "runtime_identity_sha256": runtime.digest,
            "runtime_uid": runtime.runtime_uid,
            "runtime_generation": runtime.runtime_generation,
            "authority_sha256": self.authority.digest,
            "source_id": observation.source_id,
            "source_key_sha256": observation.source_key_sha256,
            "observed_at_ns": observation.observed_at_ns,
            "process_absent": observation.process_absent,
            "cgroup_empty": observation.cgroup_empty,
            "container_absent": observation.container_absent,
            "pod_absent": pod_absent,
            "mounts_absent": observation.mounts_absent,
            "namespaces_absent": observation.namespaces_absent,
            "credentials_revoked": observation.credentials_revoked,
            "kernel_residue_safe": observation.kernel_residue_safe,
            "logs_purged": observation.logs_purged,
            "sockets_absent": observation.sockets_absent,
            "raw_evidence_sha256": canonical_sha256(
                {"agent": observation.raw_evidence_sha256, "pod_inventory": items}
            ),
        }
        _, _, signature = self.node_agent.sign(payload)
        return RuntimeAbsenceProof(**payload, signature_sha256=signature)

    def collect_operation_absence(self, *, switch_id: str, reservation: LaunchReservation) -> LaunchOperationAbsenceProof:
        self._verify_cluster()
        observation = self.node_agent.observe_operation(reservation)
        _verify_agent_signature(observation, authority=self.authority, key=self.node_agent_verification_key)
        pods_cmd = (*self._base(), "get", "pods", "--namespace", str(self.authority.namespace), "--output", "json")
        result = self.runner.run(pods_cmd)
        if result.returncode != 0:
            raise ProofRejected("Kubernetes Pod inventory query failed")
        items = json.loads(result.stdout).get("items", [])
        operation_labels = [item for item in items if item.get("metadata", {}).get("labels", {}).get("catalog-switch-operation") == reservation.operation_id]
        payload = {
            "schema": OPERATION_ABSENCE_SCHEMA,
            "switch_id": switch_id,
            "reservation_sha256": reservation.digest,
            "operation_id": reservation.operation_id,
            "runtime_generation": reservation.runtime_generation,
            "authority_sha256": self.authority.digest,
            "source_id": observation.source_id,
            "source_key_sha256": observation.source_key_sha256,
            "observed_at_ns": observation.observed_at_ns,
            "launch_journal_terminal": observation.launch_journal_terminal,
            "process_absent": observation.process_absent,
            "cgroup_absent": observation.cgroup_absent,
            "container_absent": observation.container_absent,
            "pod_absent": not operation_labels,
            "mounts_absent": observation.mounts_absent,
            "namespaces_absent": observation.namespaces_absent,
            "credentials_revoked": observation.credentials_revoked,
            "kernel_residue_safe": observation.kernel_residue_safe,
            "raw_evidence_sha256": canonical_sha256(
                {"agent": observation.raw_evidence_sha256, "operation_pods": operation_labels}
            ),
        }
        _, _, signature = self.node_agent.sign(payload)
        return LaunchOperationAbsenceProof(**payload, signature_sha256=signature)


class NvidiaSmiNvmlProbe:
    """NVML-backed UUID/memory plus pmon compute-and-graphics observation."""

    MIB = 1024 * 1024

    def __init__(self, runner: CommandRunner | None = None, *, clock_ns=time.monotonic_ns):
        self.runner = runner or SubprocessRunner()
        self.clock_ns = clock_ns

    @staticmethod
    def _csv_rows(output: str) -> list[list[str]]:
        return [[part.strip() for part in line.split(",")] for line in output.splitlines() if line.strip()]

    def observe(self, gpu_uuid: str) -> NvmlObservation:
        memory_cmd = (
            "nvidia-smi",
            "--query-gpu=index,uuid,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        )
        memory = self.runner.run(memory_cmd)
        if memory.returncode != 0:
            raise ProofRejected("NVML GPU query failed closed")
        matches = [row for row in self._csv_rows(memory.stdout) if len(row) == 4 and row[1] == gpu_uuid]
        if len(matches) != 1:
            raise ProofRejected("NVML did not identify exactly one GPU UUID")
        try:
            gpu_index, used_mib, total_mib = int(matches[0][0]), int(matches[0][2]), int(matches[0][3])
        except ValueError as exc:
            raise ProofRejected("NVML memory/index fields are malformed") from exc
        pmon_cmd = ("nvidia-smi", "pmon", "-c", "1", "-s", "m")
        pmon = self.runner.run(pmon_cmd)
        if pmon.returncode != 0:
            raise ProofRejected("NVML pmon compute/graphics query failed closed")
        compute: list[int] = []
        graphics: list[int] = []
        for line in pmon.stdout.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            fields = stripped.split()
            if len(fields) < 3 or fields[0] == "-":
                continue
            try:
                index, pid = int(fields[0]), int(fields[1])
            except ValueError as exc:
                raise ProofRejected("NVML pmon row is malformed") from exc
            if index != gpu_index:
                continue
            kind = fields[2].upper()
            if "C" in kind:
                compute.append(pid)
            if "G" in kind:
                graphics.append(pid)
        observation = NvmlObservation(
            self.clock_ns(),
            gpu_uuid,
            tuple(sorted(set(compute))),
            tuple(sorted(set(graphics))),
            True,
            used_mib * self.MIB,
            total_mib * self.MIB,
        )
        # Shape validation is performed with the exact total observed here.
        if observation.memory_total_bytes < 1:
            raise ProofRejected("NVML total memory is invalid")
        return observation


class GpuEvidenceAdapter:
    def __init__(
        self,
        *,
        authority: RuntimeAuthority,
        node_agent: NodeAgentClient,
        nvml_probe: NvidiaSmiNvmlProbe,
        sample_interval_seconds: float = 0.0,
    ):
        self.authority = authority
        self.node_agent = node_agent
        self.nvml_probe = nvml_probe
        self.sample_interval_seconds = sample_interval_seconds

    def collect_release(
        self,
        *,
        switch_id: str,
        subject_sha256: str,
        gpu_uuid: str,
        scrub: ScrubReceipt,
    ) -> GpuReleaseProof:
        first = self.nvml_probe.observe(gpu_uuid)
        if self.sample_interval_seconds:
            time.sleep(self.sample_interval_seconds)
        second = self.nvml_probe.observe(gpu_uuid)
        payload = {
            "schema": GPU_RELEASE_SCHEMA,
            "switch_id": switch_id,
            "subject_sha256": subject_sha256,
            "authority_sha256": self.authority.digest,
            "gpu_uuid": gpu_uuid,
            "source_id": self.authority.node_agent_id,
            "source_key_sha256": self.authority.node_agent_key_sha256,
            "observations": (first, second),
            "scrub": scrub,
            "raw_evidence_sha256": canonical_sha256(
                {"observations": [asdict(first), asdict(second)], "scrub": asdict(scrub)}
            ),
        }
        serializable = copy.deepcopy(payload)
        serializable["observations"] = [asdict(first), asdict(second)]
        serializable["scrub"] = asdict(scrub)
        _, _, signature = self.node_agent.sign(serializable)
        # asdict(GpuReleaseProof) uses the same list representation for tuples.
        return GpuReleaseProof(**payload, signature_sha256=signature)


__all__ = [name for name in globals() if not name.startswith("_")]
