#!/usr/bin/env python3
"""Queued external-T0 controller for Kubernetes catalog-switch attempts."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from performance.request_slo.harness import (
    EVENT_SCHEMA,
    PHASES,
    TERMINAL_BOUNDARY,
    T0_BOUNDARY,
    canonical_json,
    canonical_sha256,
    default_recorder,
    load_ledger,
    validate_ledger,
    validate_trace,
)

from .contract import BaselineError


@dataclass(frozen=True)
class PhaseResult:
    outcome: str
    reason: str
    bytes_moved: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.outcome not in {"completed", "failed", "skipped"}:
            raise BaselineError("phase result has an invalid outcome")
        if not self.reason:
            raise BaselineError("phase result reason cannot be empty")
        if not isinstance(self.bytes_moved, int) or self.bytes_moved < 0:
            raise BaselineError("phase bytes_moved must be a nonnegative integer")


@dataclass(frozen=True)
class TerminalResult:
    success: bool
    response: bytes = b""
    validator_id: str = ""
    validator_sha256: str = ""
    failure_class: str = "backend"
    reason: str = "backend execution failed"
    retryable: bool = False


@dataclass(frozen=True)
class AccountingResult:
    cost_usd: float
    gpu_active_seconds: float
    gpu_idle_seconds: float
    billed_seconds: float


@dataclass(frozen=True)
class CleanupResult:
    required: bool
    status: str
    resources_deleted: tuple[str, ...]
    resources_retained: tuple[str, ...]
    receipt_sha256: str | None
    reason: str


class Backend(Protocol):
    """Backend boundary; only the controller owns canonical event timestamps."""

    classification: str

    def prepare(self) -> None: ...

    def accepted(self, request: dict[str, Any], event: dict[str, Any]) -> None: ...

    def environment(self, request: dict[str, Any]) -> dict[str, Any]: ...

    def ownership(self, request: dict[str, Any]) -> dict[str, Any]: ...

    def should_skip(self, request: dict[str, Any], phase: str) -> str | None: ...

    def run_phase(self, request: dict[str, Any], phase: str) -> PhaseResult: ...

    def terminal(self, request: dict[str, Any], failed: PhaseResult | None) -> TerminalResult: ...

    def post_terminal(self, request: dict[str, Any], terminal: TerminalResult) -> None: ...

    def accounting(
        self, request: dict[str, Any], elapsed_seconds: float, bytes_moved: int
    ) -> AccountingResult: ...

    def cleanup(self, request: dict[str, Any]) -> CleanupResult: ...

    def write_evidence(self, path: Path) -> None: ...

    def qualification_summary(self) -> dict[str, Any]: ...


class EventSink:
    """Append canonical observations with one immutable external recorder."""

    def __init__(self, ledger: Path, ledger_id: str, trace_id: str) -> None:
        self.ledger = ledger
        self.ledger_id = ledger_id
        self.trace_id = trace_id
        self.recorder = default_recorder(
            "catalog-switch-k8s-external-client", max_error_ms=50.0
        )
        self._lock = threading.Lock()
        self._ledger_sequence = 0
        self._attempt_sequences: dict[str, int] = {}
        self._writes: queue.Queue[tuple[dict[str, Any], threading.Event] | None] = queue.Queue()
        self._writer_errors: list[Exception] = []
        self._closed = False
        self._writer = threading.Thread(
            target=self._write_loop, name="catalog-switch-ledger-writer", daemon=False
        )
        self._writer.start()

    def _write_loop(self) -> None:
        while True:
            item = self._writes.get()
            if item is None:
                self._writes.task_done()
                return
            event, done = item
            try:
                flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                descriptor = os.open(self.ledger, flags, 0o600)
                try:
                    payload = (canonical_json(event) + "\n").encode("utf-8")
                    written = os.write(descriptor, payload)
                    if written != len(payload):
                        raise BaselineError("short write to canonical event ledger")
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except Exception as exc:
                self._writer_errors.append(exc)
            finally:
                done.set()
                self._writes.task_done()

    def _append_locked(
        self,
        request: dict[str, Any],
        event_type: str,
        data: dict[str, Any],
        *,
        observed_at_utc: str | None = None,
        observed_monotonic_ns: int | None = None,
    ) -> tuple[dict[str, Any], threading.Event]:
        attempt_sequence = self._attempt_sequences.get(request["attempt_id"], 0)
        event = {
            "schema": EVENT_SCHEMA,
            "ledger_id": self.ledger_id,
            "ledger_sequence": self._ledger_sequence,
            "trace_id": self.trace_id,
            "request_id": request["request_id"],
            "attempt_id": request["attempt_id"],
            "attempt_sequence": attempt_sequence,
            "event_id": f"{request['attempt_id']}:{attempt_sequence:06d}",
            "observed_at_utc": observed_at_utc
            or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "observed_monotonic_ns": observed_monotonic_ns or time.monotonic_ns(),
            "recorder": dict(self.recorder),
            "event_type": event_type,
            "data": data,
        }
        self._ledger_sequence += 1
        self._attempt_sequences[request["attempt_id"]] = attempt_sequence + 1
        done = threading.Event()
        self._writes.put((event, done))
        return event, done

    def add(self, request: dict[str, Any], event_type: str, data: dict[str, Any]) -> None:
        with self._lock:
            _, done = self._append_locked(request, event_type, data)
        # The response/failure boundary cannot be acknowledged until the
        # complete preceding chain is durable. FIFO writes make this a flush.
        if event_type in {"response.validated", "attempt.failed", "cleanup.finished"}:
            done.wait()
            self._raise_writer_error()

    def accept(self, request: dict[str, Any], backend: Backend) -> dict[str, Any]:
        """Capture T0 before deriving any request-specific backend metadata.

        The ledger lock is acquired first so a worker event cannot be inserted
        between the acceptance clock sample and its append.
        """

        if self.ledger.exists() and self.ledger.is_symlink():
            raise BaselineError("ledger output cannot be a symlink")
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            observed_at_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            observed_monotonic_ns = time.monotonic_ns()
            data = {
                "boundary": T0_BOUNDARY,
                "trace_request_sha256": canonical_sha256(request),
                "scenario": request["scenario"],
                "target": request["target"],
                "input": request["input"],
                "precondition": request["precondition"],
                "environment": backend.environment(request),
                "ownership": backend.ownership(request),
            }
            event, done = self._append_locked(
                request,
                "request.accepted",
                data,
                observed_at_utc=observed_at_utc,
                observed_monotonic_ns=observed_monotonic_ns,
            )
            if getattr(backend, "requires_durable_t0_before_accepted_hook", False):
                done.wait()
                self._raise_writer_error()
            return event

    def _raise_writer_error(self) -> None:
        if self._writer_errors:
            raise BaselineError(f"canonical ledger writer failed: {self._writer_errors[0]}")

    def close(self) -> None:
        if self._closed:
            self._raise_writer_error()
            return
        self._writes.put(None)
        self._writes.join()
        self._writer.join()
        self._closed = True
        self._raise_writer_error()

    def phase_started(self, request: dict[str, Any], phase: str) -> None:
        self.add(request, "phase.started", {"phase": phase, "occurrence": 0})

    def phase_finished(
        self, request: dict[str, Any], phase: str, result: PhaseResult
    ) -> None:
        self.add(
            request,
            "phase.finished",
            {
                "phase": phase,
                "occurrence": 0,
                "outcome": result.outcome,
                "reason": result.reason,
                "bytes_moved": result.bytes_moved,
            },
        )


def _phase_failure(exc: Exception) -> PhaseResult:
    reason = f"{type(exc).__name__}: {exc}"[:1000]
    return PhaseResult("failed", reason or "unknown backend exception")


def _run_phase(
    sink: EventSink,
    backend: Backend,
    request: dict[str, Any],
    phase: str,
    *,
    force_skip: str | None = None,
) -> PhaseResult:
    skip_reason = force_skip if force_skip is not None else backend.should_skip(request, phase)
    if skip_reason is not None:
        result = PhaseResult("skipped", skip_reason)
        sink.phase_finished(request, phase, result)
        return result
    sink.phase_started(request, phase)
    try:
        result = backend.run_phase(request, phase)
    except Exception as exc:  # The ledger must retain the failed offered attempt.
        result = _phase_failure(exc)
    if result.outcome == "skipped":
        result = PhaseResult(
            "failed",
            "backend returned skipped after phase.started; fail-closed",
            result.bytes_moved,
            result.evidence,
        )
    sink.phase_finished(request, phase, result)
    return result


def _record_terminal(
    sink: EventSink,
    backend: Backend,
    request: dict[str, Any],
    failure: PhaseResult | None,
) -> TerminalResult:
    terminal = backend.terminal(request, failure)
    if failure is not None and terminal.success:
        terminal = TerminalResult(
            False,
            failure_class="backend",
            reason="backend tried to report success after a failed phase",
        )
    if terminal.success:
        if not terminal.response or len(terminal.validator_sha256) != 64:
            raise BaselineError("successful terminal lacks response or validator identity")
        sink.add(
            request,
            "response.validated",
            {
                "boundary": TERMINAL_BOUNDARY,
                "validator_id": terminal.validator_id,
                "validator_sha256": terminal.validator_sha256,
                "response_sha256": hashlib.sha256(terminal.response).hexdigest(),
                "response_bytes": len(terminal.response),
                "complete_body": True,
                "semantically_valid": True,
                "model_id": request["target"]["model_id"],
                "model_version": request["target"]["model_version"],
            },
        )
    else:
        sink.add(
            request,
            "attempt.failed",
            {
                "failure_class": terminal.failure_class,
                "reason": terminal.reason[:1000] or "unspecified backend failure",
                "retryable": terminal.retryable,
            },
        )
    return terminal


def _record_accounting_and_cleanup(
    sink: EventSink,
    backend: Backend,
    request: dict[str, Any],
    *,
    started_ns: int,
    bytes_moved: int,
) -> None:
    accounting = backend.accounting(
        request,
        max(0.0, (time.monotonic_ns() - started_ns) / 1_000_000_000),
        bytes_moved,
    )
    sink.add(
        request,
        "accounting.recorded",
        {
            "currency": "USD",
            "cost_usd": accounting.cost_usd,
            "gpu_active_seconds": accounting.gpu_active_seconds,
            "gpu_idle_seconds": accounting.gpu_idle_seconds,
            "billed_seconds": accounting.billed_seconds,
            "bytes_moved_total": bytes_moved,
        },
    )
    cleanup = backend.cleanup(request)
    sink.add(
        request,
        "cleanup.finished",
        {
            "required": cleanup.required,
            "status": cleanup.status,
            "resources_deleted": list(cleanup.resources_deleted),
            "resources_retained": list(cleanup.resources_retained),
            "receipt_sha256": cleanup.receipt_sha256,
            "reason": cleanup.reason,
        },
    )


def run_trace(
    trace: dict[str, Any],
    backend: Backend,
    ledger: Path,
    evidence: Path,
    *,
    ledger_id: str,
) -> dict[str, Any]:
    """Execute a trace while accepting offered requests on their pinned schedule.

    One scheduler owns T0, catalog selection, and queue admission. One worker
    serializes a single exclusive GPU. This prevents a long switch from moving
    later request acceptance and queueing before the request's externally
    observed T0.
    """

    trace = validate_trace(trace)
    if ledger.exists() or ledger.is_symlink():
        raise BaselineError("ledger output must be new")
    if evidence.exists() or evidence.is_symlink():
        raise BaselineError("backend evidence output must be new")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    backend.prepare()
    sink = EventSink(ledger, ledger_id, trace["trace_id"])
    accepted: queue.Queue[tuple[dict[str, Any], int, PhaseResult | None] | None] = queue.Queue()
    worker_errors: list[Exception] = []

    def worker() -> None:
        while True:
            item = accepted.get()
            if item is None:
                accepted.task_done()
                return
            request, accepted_ns, prior_failure = item
            moved = 0
            failure = prior_failure
            try:
                if failure is not None:
                    # phase.started was already emitted at the enqueue edge, so
                    # a selection failure completes the measured queue as failed.
                    queue_result = PhaseResult(
                        "failed", "catalog selection failed; queued work refused"
                    )
                else:
                    try:
                        queue_result = backend.run_phase(request, "queue")
                    except Exception as exc:
                        queue_result = _phase_failure(exc)
                    if queue_result.outcome == "skipped":
                        queue_result = PhaseResult(
                            "failed",
                            "backend returned skipped for an already-started queue phase",
                        )
                sink.phase_finished(request, "queue", queue_result)
                moved += queue_result.bytes_moved
                if queue_result.outcome == "failed" and failure is None:
                    failure = queue_result
                for phase in PHASES[2:]:
                    result = _run_phase(
                        sink,
                        backend,
                        request,
                        phase,
                        force_skip=(
                            "skipped after an exposed failed phase"
                            if failure is not None
                            else None
                        ),
                    )
                    moved += result.bytes_moved
                    if result.outcome == "failed" and failure is None:
                        failure = result
                terminal = _record_terminal(sink, backend, request, failure)
                backend.post_terminal(request, terminal)
                _record_accounting_and_cleanup(
                    sink,
                    backend,
                    request,
                    started_ns=accepted_ns,
                    bytes_moved=moved,
                )
            except Exception as exc:
                worker_errors.append(exc)
                # An incomplete attempt is intentionally not papered over. The
                # canonical validator will reject it and preserve the raw file.
            finally:
                accepted.task_done()

    thread = threading.Thread(target=worker, name="catalog-switch-gpu-worker", daemon=False)
    thread.start()
    schedule_origin_ns = time.monotonic_ns()
    try:
        for request in trace["requests"]:
            deadline_ns = schedule_origin_ns + request["offered_at_offset_ms"] * 1_000_000
            while True:
                remaining = deadline_ns - time.monotonic_ns()
                if remaining <= 0:
                    break
                time.sleep(min(remaining / 1_000_000_000, 0.01))
            acceptance = sink.accept(request, backend)
            accepted_ns = acceptance["observed_monotonic_ns"]
            backend.accepted(request, acceptance)
            catalog_result = _run_phase(sink, backend, request, "catalog_selection")
            sink.phase_started(request, "queue")
            # The worker owns only the queue finish; the start above is the
            # exact enqueue edge. It cannot call _run_phase for queue because
            # that would append a second start.
            accepted.put(
                (
                    request,
                    accepted_ns,
                    catalog_result if catalog_result.outcome == "failed" else None,
                )
            )
        accepted.put(None)
        accepted.join()
        thread.join()
        sink.close()
    finally:
        if thread.is_alive():
            accepted.put(None)
            thread.join(timeout=5)
        if not sink._closed:
            sink.close()
    if worker_errors:
        raise BaselineError(f"worker left incomplete evidence: {worker_errors[0]}")
    # The queue phase is special: scheduler wrote its start. Rewrite validation
    # is avoided by having the worker's queue handler return only its finish.
    events = load_ledger(ledger)
    attempts = validate_ledger(events, trace)
    backend.write_evidence(evidence)
    qualification = backend.qualification_summary()
    return {
        "classification": backend.classification,
        "trace_id": trace["trace_id"],
        "ledger_id": ledger_id,
        "attempt_count": len(attempts),
        "success_count": sum(item["success"] for item in attempts),
        "failure_count": sum(not item["success"] for item in attempts),
        "ledger_sha256": hashlib.sha256(ledger.read_bytes()).hexdigest(),
        "backend_evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        "two_call_qualification": qualification,
    }


class ScriptedBackend:
    """Contract test backend; its output is never empirical performance evidence."""

    classification = "synthetic-controller-contract-test-not-performance-evidence"
    requires_durable_t0_before_accepted_hook = False

    def __init__(self) -> None:
        self._responses: dict[str, bytes] = {}
        self._events: list[dict[str, Any]] = []
        self._owned: dict[str, tuple[str, ...]] = {}

    def prepare(self) -> None:
        self._events.append({"operation": "prepare", "target_specific": False})

    def accepted(self, request: dict[str, Any], event: dict[str, Any]) -> None:
        self._events.append(
            {
                "operation": "accepted",
                "attempt_id": request["attempt_id"],
                "t0_monotonic_ns": event["observed_monotonic_ns"],
            }
        )

    def environment(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "backend": "kubernetes-scripted-test",
            "backend_version": "v1",
            "provider": "local",
            "project_id": "local-contract-test",
            "region": "local",
            "node_id": "synthetic-node",
            "gpu_type": "synthetic-gpu",
            "gpu_count": 1,
            "image_digest": "example.invalid/model@sha256:" + "a" * 64,
            "code_revision": "0" * 40,
            "config_sha256": "1" * 64,
            "experiment_id": "k8s-controller-contract-test",
        }

    def ownership(self, request: dict[str, Any]) -> dict[str, Any]:
        resource_id = f"k8s:test/pod/{request['attempt_id']}"
        self._owned[request["attempt_id"]] = (resource_id,)
        return {
            "owner_task_id": "catalog-switch-k8s-baseline",
            "resource_prefix": "synthetic-k8s-test",
            "dedicated": True,
            "cleanup_required": True,
            "resources": [
                {
                    "kind": "pod",
                    "id": resource_id,
                    "project_id": "local-contract-test",
                    "region": "local",
                }
            ],
        }

    def should_skip(self, request: dict[str, Any], phase: str) -> str | None:
        scenario = request["scenario"]
        if scenario == "same_model_hot" and phase in {
            "drain",
            "gpu_release",
            "placement",
            "image_readiness",
            "artifact_readiness",
            "storage_readiness",
            "runtime_launch",
        }:
            return "synthetic same-model hot path"
        if scenario == "idle_local" and phase in {"drain", "gpu_release"}:
            return "synthetic idle node"
        return None

    def run_phase(self, request: dict[str, Any], phase: str) -> PhaseResult:
        if phase == "queue":
            # The scheduler already wrote phase.started at enqueue.
            result = PhaseResult("completed", "synthetic single-GPU queue admitted")
            self._events.append({"attempt_id": request["attempt_id"], "phase": phase})
            return result
        if request["scenario"] == "capacity_miss" and phase == "placement":
            return PhaseResult("failed", "synthetic capacity unavailable")
        moved = (
            request["input"]["input_bytes"]
            if phase == "artifact_readiness" and request["scenario"] == "a_to_b_remote"
            else 0
        )
        if phase == "inference":
            self._responses[request["attempt_id"]] = (
                json.dumps(
                    {
                        "attempt_id": request["attempt_id"],
                        "model_id": request["target"]["model_id"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode()
        self._events.append({"attempt_id": request["attempt_id"], "phase": phase})
        return PhaseResult("completed", "synthetic controller contract step", moved)

    def terminal(
        self, request: dict[str, Any], failed: PhaseResult | None
    ) -> TerminalResult:
        if failed is not None:
            return TerminalResult(
                False,
                failure_class=(
                    "capacity" if request["scenario"] == "capacity_miss" else "backend"
                ),
                reason=failed.reason,
                retryable=True,
            )
        return TerminalResult(
            True,
            response=self._responses[request["attempt_id"]],
            validator_id="synthetic-k8s-semantic-validator-v1",
            validator_sha256="2" * 64,
        )

    def post_terminal(
        self, request: dict[str, Any], terminal: TerminalResult
    ) -> None:
        self._events.append(
            {
                "operation": "second_semantic_inference",
                "attempt_id": request["attempt_id"],
                "status": "PASS" if terminal.success else "NOT_RUN",
            }
        )

    def accounting(
        self, request: dict[str, Any], elapsed_seconds: float, bytes_moved: int
    ) -> AccountingResult:
        return AccountingResult(0.0, elapsed_seconds, 0.0, elapsed_seconds)

    def cleanup(self, request: dict[str, Any]) -> CleanupResult:
        owned = self._owned[request["attempt_id"]]
        return CleanupResult(
            True,
            "complete",
            owned,
            (),
            hashlib.sha256(request["attempt_id"].encode()).hexdigest(),
            "synthetic per-attempt resources removed",
        )

    def write_evidence(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "classification": self.classification,
                    "events": self._events,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

    def qualification_summary(self) -> dict[str, Any]:
        attempted = [
            item for item in self._events if item.get("operation") == "second_semantic_inference"
        ]
        passed = [item for item in attempted if item["status"] == "PASS"]
        return {
            "classification": self.classification,
            "required_semantic_calls": 2,
            "product_terminal_call": 1,
            "attempt_count": len(attempted),
            "qualified_count": len(passed),
        }
