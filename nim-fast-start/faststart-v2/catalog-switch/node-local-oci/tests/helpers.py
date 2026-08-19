"""Test helpers for the node-local OCI adapter.

The fakes here live *only* in the test tree, in two honest forms:

- stub executables written to a temp bin directory whose sha256s the test
  controller pins into a signed offline-validation policy (the same trust
  chain a live policy uses for the real ``ctr``/``nvidia-smi``); the stub
  ``ctr`` spawns real processes, so PID/liveness observations are genuine;
- direct construction of dataclasses/objects for unit-level adversaries.

The production package contains no fake and imports nothing from here.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

LANE_DIR = Path(__file__).resolve().parents[1]
FASTSTART_ROOT = LANE_DIR.parent.parent
for entry in (str(LANE_DIR), str(FASTSTART_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from node_local_oci import contracts  # noqa: E402
from node_local_oci.journal import canonical_json  # noqa: E402
from node_local_oci.keys import ROLES, generate_keypair, load_private, sign  # noqa: E402

STUB_GPU_UUID = "GPU-0f7a1111-2222-3333-4444-555566667777"
STUB_GPU_PRODUCT = "STUB OFFLINE GPU"
STUB_GPU_MEMORY_MIB = 1024
STUB_DRIVER = "580.00-stub"
STUB_IMAGE = "registry.local/stub-model@sha256:" + "ab" * 32


def utc_in(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def make_keys(base: Path) -> dict:
    """Agent keys dir + authority private keys held only by the test."""
    agent_dir = base / "keys" / "agent"
    authority_dir = base / "keys" / "authorities"
    agent_dir.mkdir(parents=True)
    authority_dir.mkdir(parents=True)
    privates = {}
    for role in ROLES:
        target = agent_dir if role == "agent" else authority_dir
        key_path, pub_path = generate_keypair(target, role)
        privates[role] = load_private(key_path)
        if role != "agent":
            (agent_dir / f"{role}.pub").write_bytes(pub_path.read_bytes())
    return {"agent_dir": agent_dir, "authority_dir": authority_dir,
            "privates": privates}


def sign_envelope(private, role: str, schema: str, body: dict) -> dict:
    envelope = dict(body)
    envelope["signature"] = sign(private, role, schema, body)
    return envelope


_CTR_STUB = textwrap.dedent('''\
    #!/usr/bin/env python3
    """Offline ctr stub: keeps a JSON state next to itself, spawns REAL
    processes for `run`, and mirrors the ctr output shapes the adapter
    parses.  Pinned by sha256 in the test controller's signed policy."""
    import json, os, signal, subprocess, sys
    from pathlib import Path

    STATE = Path(__file__).resolve().parent / "ctr-state"
    STATE.mkdir(exist_ok=True)
    IMAGES = STATE / "images.json"
    CONTAINERS = STATE / "containers.json"

    def load(path, default):
        return json.loads(path.read_text()) if path.exists() else default

    def save(path, value):
        path.write_text(json.dumps(value))

    def alive(pid):
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    args = sys.argv[1:]
    if len(args) < 3 or args[0] != "-n":
        sys.exit(64)
    cmd = args[2:]
    images = load(IMAGES, [])
    containers = load(CONTAINERS, {})

    if cmd[:3] == ["images", "ls", "-q"]:
        for ref in images:
            print(ref)
        sys.exit(0)
    if cmd[:2] == ["images", "pull"]:
        if cmd[2] not in images:
            images.append(cmd[2])
        save(IMAGES, images)
        sys.exit(0)
    if cmd[0] == "run":
        rest = cmd[1:]
        if rest[0] != "-d":
            sys.exit(64)
        rest = rest[1:]
        idx = next((i for i, a in enumerate(rest) if a in images), None)
        if idx is None:
            print("ctr: image not found", file=sys.stderr)
            sys.exit(1)
        image, cid, command = rest[idx], rest[idx + 1], rest[idx + 2:]
        if cid in containers:
            print(f"ctr: container {cid}: already exists", file=sys.stderr)
            sys.exit(1)
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
        containers[cid] = {"image": image, "pid": proc.pid}
        save(CONTAINERS, containers)
        sys.exit(0)
    if cmd[:2] == ["containers", "info"]:
        cid = cmd[2]
        if cid not in containers:
            print(f"ctr: container \\"{cid}\\": not found", file=sys.stderr)
            sys.exit(1)
        print(json.dumps({"ID": cid, "Image": containers[cid]["image"],
                          "Runtime": {"Name": "io.containerd.runc.v2"}}))
        sys.exit(0)
    if cmd[:2] == ["tasks", "ls"]:
        print("TASK    PID    STATUS")
        for cid, entry in containers.items():
            if entry.get("task_deleted"):
                continue
            status = "RUNNING" if alive(entry["pid"]) else "STOPPED"
            print(f"{cid}    {entry['pid']}    {status}")
        sys.exit(0)
    if cmd[:2] == ["tasks", "kill"]:
        signame, cid = cmd[3], cmd[4]
        if cid not in containers:
            print(f"ctr: task \\"{cid}\\": not found", file=sys.stderr)
            sys.exit(1)
        signum = {"SIGTERM": signal.SIGTERM, "SIGKILL": signal.SIGKILL}[signame]
        try:
            os.kill(containers[cid]["pid"], signum)
        except OSError:
            pass
        sys.exit(0)
    if cmd[:2] == ["tasks", "delete"]:
        cid = cmd[2]
        if cid not in containers or containers[cid].get("task_deleted"):
            print(f"ctr: task \\"{cid}\\": not found", file=sys.stderr)
            sys.exit(1)
        containers[cid]["task_deleted"] = True
        save(CONTAINERS, containers)
        sys.exit(0)
    if cmd[:2] == ["containers", "delete"]:
        cid = cmd[2]
        if cid not in containers:
            print(f"ctr: container \\"{cid}\\": not found", file=sys.stderr)
            sys.exit(1)
        del containers[cid]
        save(CONTAINERS, containers)
        sys.exit(0)
    print("ctr-stub: unknown command", file=sys.stderr)
    sys.exit(64)
''')

_NVIDIA_SMI_STUB = textwrap.dedent('''\
    #!/usr/bin/env python3
    """Offline nvidia-smi stub driven by nvidia-smi-config.json beside it."""
    import json, sys
    from pathlib import Path

    config = json.loads((Path(__file__).resolve().parent /
                         "nvidia-smi-config.json").read_text())
    args = sys.argv[1:]
    if any(a.startswith("--query-gpu=") for a in args):
        for row in config["gpu_rows"]:
            print(row)
        sys.exit(0)
    if any(a.startswith("--query-compute-apps=") for a in args):
        for row in config["compute_rows"]:
            print(row)
        sys.exit(0)
    if args[:1] == ["pmon"]:
        sys.stdout.write(config["pmon_text"])
        sys.exit(0)
    sys.exit(64)
''')

_GPU_SCRUB_STUB = textwrap.dedent('''\
    #!/usr/bin/env python3
    """Offline gpu-scrub stub driven by gpu-scrub-config.json beside it."""
    import json, sys
    from pathlib import Path

    config = json.loads((Path(__file__).resolve().parent /
                         "gpu-scrub-config.json").read_text())
    print(json.dumps({"gpu_uuid": sys.argv[1], "method": config["method"],
                      "bytes_scrubbed": config["bytes_scrubbed"]}))
    sys.exit(0)
''')

_MODEL_SERVER = textwrap.dedent('''\
    #!/usr/bin/env python3
    """Real HTTP process the stub ctr launches as the "container"."""
    import hashlib, json, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            body = b"ok" if self.path == "/health" else b"nope"
            self.send_response(200 if self.path == "/health" else 404)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            payload = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            digest = hashlib.sha256(payload).hexdigest()
            body = json.dumps({"model": "stub", "payload_sha256": digest,
                               "result": "prediction-" + digest[:16]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
''')


def default_pmon_text() -> str:
    return ("# gpu   pid  type    sm   mem   enc   dec   command\n"
            "# Idx     #   C/G     %     %     %     %   name\n"
            "    0     -     -     -     -     -     -   -\n")


def make_stub_bins(base: Path, *, memory_used_mib: int = 0) -> Path:
    bin_dir = base / "bin"
    bin_dir.mkdir(parents=True)
    for name, source in (("ctr", _CTR_STUB), ("nvidia-smi", _NVIDIA_SMI_STUB),
                         ("gpu-scrub", _GPU_SCRUB_STUB)):
        path = bin_dir / name
        path.write_text(source, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    (bin_dir / "stub_model_server.py").write_text(_MODEL_SERVER, encoding="utf-8")
    write_nvidia_config(bin_dir, memory_used_mib=memory_used_mib)
    (bin_dir / "gpu-scrub-config.json").write_text(json.dumps({
        "method": "full-vram-zero",
        "bytes_scrubbed": STUB_GPU_MEMORY_MIB * 1024 * 1024,
    }), encoding="utf-8")
    return bin_dir


def write_nvidia_config(bin_dir: Path, *, memory_used_mib: int = 0,
                        compute_rows: list[str] | None = None,
                        pmon_text: str | None = None) -> None:
    (bin_dir / "nvidia-smi-config.json").write_text(json.dumps({
        "gpu_rows": [f"{STUB_GPU_UUID}, {STUB_GPU_PRODUCT}, {STUB_GPU_MEMORY_MIB}, "
                     f"{memory_used_mib}, {STUB_DRIVER}"],
        "compute_rows": compute_rows or [],
        "pmon_text": pmon_text if pmon_text is not None else default_pmon_text(),
    }), encoding="utf-8")


def seed_image(bin_dir: Path, image_ref: str) -> None:
    state = bin_dir / "ctr-state"
    state.mkdir(exist_ok=True)
    images_path = state / "images.json"
    images = json.loads(images_path.read_text()) if images_path.exists() else []
    if image_ref not in images:
        images.append(image_ref)
    images_path.write_text(json.dumps(images))


def real_boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def real_machine_id() -> str:
    return Path("/etc/machine-id").read_text().strip()


def real_root_storage() -> dict:
    """Pin the dev host's real root filesystem for honest offline admission."""
    mounts = Path("/proc/self/mounts").read_text()
    device = next(line.split()[0] for line in mounts.splitlines()
                  if line.split()[1] == "/")
    by_uuid = Path("/dev/disk/by-uuid")
    resolved = Path(device).resolve()
    fs_uuid = next(link.name for link in by_uuid.iterdir()
                   if link.resolve() == resolved)
    return {"device": device, "mountpoint": "/", "fs_uuid": fs_uuid,
            "storage_class": "offline-devhost-root"}


def make_policy_body(*, bin_dir: Path, artifact_path: Path, port: int,
                     validator_path: Path, model_id: str = "stub-model") -> dict:
    return {
        "schema": contracts.POLICY_SCHEMA,
        "policy_id": "nlo-test-policy-1",
        "issued_utc": utc_in(0),
        "launch_class": "offline-validation",
        "node": {
            "instance_id": real_machine_id(),
            "instance_source": "machine-id",
            "boot_id": real_boot_id(),
            "hostname": os.uname().nodename,
        },
        "lease": {
            "lease_id": "nlo-test-lease-1",
            "owner_task_id": "catalog-switch-node-local-concrete-oci-adapter",
            "resource_prefix": "nlo",
            "project_id": "offline-validation-no-project",
            "region": "offline",
        },
        "binaries": {
            "ctr": {"path": str(bin_dir / "ctr"),
                    "sha256": sha256_file(bin_dir / "ctr")},
            "nvidia-smi": {"path": str(bin_dir / "nvidia-smi"),
                           "sha256": sha256_file(bin_dir / "nvidia-smi")},
            "gpu-scrub": {"path": str(bin_dir / "gpu-scrub"),
                          "sha256": sha256_file(bin_dir / "gpu-scrub")},
        },
        "gpu": {"product": STUB_GPU_PRODUCT, "count": 1,
                "uuids": [STUB_GPU_UUID],
                "memory_total_mib": STUB_GPU_MEMORY_MIB},
        "storage": real_root_storage(),
        "models": {
            model_id: {
                "model_version": "stub-1.0.0",
                "image_digest": STUB_IMAGE,
                "artifact_id": "stub-artifact",
                "artifact_version": "v1",
                "artifact_sha256": sha256_file(artifact_path),
                "artifact_path": str(artifact_path),
                "endpoint": f"http://127.0.0.1:{port}",
                "health_path": "/health",
                "infer_path": "/infer",
                "run_args": [],
                "command": [sys.executable,
                            str(bin_dir / "stub_model_server.py"), str(port)],
                "snapshot_command": None,
            },
        },
        "oracle": {"validator_id": "stub-validator-v1",
                   "validator_sha256": sha256_file(validator_path)},
        "containerd_namespace": "nlo-test",
    }


def make_bundle_body(*, policy_envelope: dict, trace_id: str, ledger_id: str,
                     switch_uid: str, fence: int, nonce: str,
                     requests: list[dict], prior_occupant: dict | None,
                     target_model_id: str = "stub-model",
                     deadline_s: float = 600.0) -> dict:
    return {
        "schema": contracts.BUNDLE_SCHEMA,
        "command_id": f"nlo-cmd-{switch_uid}",
        "switch_uid": switch_uid,
        "policy_sha256": sha256_bytes(canonical_json(policy_envelope).encode("utf-8")),
        "trace_id": trace_id,
        "ledger_id": ledger_id,
        "fence": fence,
        "nonce": nonce,
        "issued_utc": utc_in(-1),
        "deadline_utc": utc_in(deadline_s),
        "node": {"instance_id": real_machine_id(), "boot_id": real_boot_id()},
        "prior_occupant": prior_occupant,
        "target_model_id": target_model_id,
        "launch_mode": "conventional",
        "snapshot": None,
        "requests": requests,
    }


def make_trace_requests(*, payload_1: bytes, payload_2: bytes, artifact_sha256: str,
                        model_id: str = "stub-model",
                        model_version: str = "stub-1.0.0",
                        prior_model: dict | None = None,
                        offset_2_ms: int = 3000) -> list[dict]:
    target = {"model_id": model_id, "model_version": model_version,
              "artifact_id": "stub-artifact", "artifact_version": "v1",
              "artifact_sha256": artifact_sha256}
    prior = prior_occupant_model() if prior_model is None else prior_model
    return [
        {
            "sequence": 0,
            "request_id": "nlo-e2e-request-000001",
            "attempt_id": "nlo-e2e-attempt-000001",
            "offered_at_offset_ms": 0,
            "scenario": "a_to_b_local",
            "target": dict(target),
            "input": {"workload_id": "stub-workload", "input_id": "input-1",
                      "payload_sha256": sha256_bytes(payload_1),
                      "input_bytes": len(payload_1)},
            "precondition": {
                "current_node_occupant": prior,
                "cache": {"image": "local_verified", "artifact": "node_local_hit",
                          "checkpoint": "not_applicable", "storage": "ready"},
                "capacity": "allocated", "queue_depth": 0,
            },
        },
        {
            "sequence": 1,
            "request_id": "nlo-e2e-request-000002",
            "attempt_id": "nlo-e2e-attempt-000002",
            "offered_at_offset_ms": offset_2_ms,
            "scenario": "same_model_hot",
            "target": dict(target),
            "input": {"workload_id": "stub-workload", "input_id": "input-2",
                      "payload_sha256": sha256_bytes(payload_2),
                      "input_bytes": len(payload_2)},
            "precondition": {
                "current_node_occupant": {"model_id": model_id,
                                          "model_version": model_version},
                "cache": {"image": "local_verified", "artifact": "memory_hit",
                          "checkpoint": "not_applicable", "storage": "ready"},
                "capacity": "allocated", "queue_depth": 0,
            },
        },
    ]


def prior_occupant_model() -> dict:
    return {"model_id": "prior-model", "model_version": "prior-1.0.0"}


def make_environment(*, policy_sha256: str, code_revision: str) -> dict:
    return {"backend": "node-local-oci", "backend_version": "v1",
            "provider": "offline-validation", "project_id":
            "offline-validation-no-project", "region": "offline",
            "experiment_id": "nlo-offline-e2e", "node_id": real_machine_id(),
            "gpu_type": STUB_GPU_PRODUCT, "gpu_count": 1,
            "image_digest": STUB_IMAGE, "code_revision": code_revision,
            "config_sha256": policy_sha256}


def make_ownership(container_id: str | None) -> dict:
    resources = []
    cleanup_required = container_id is not None
    if container_id is not None:
        resources.append({"kind": "container", "id": container_id,
                          "project_id": "offline-validation-no-project",
                          "region": "offline"})
    return {"owner_task_id": "catalog-switch-node-local-concrete-oci-adapter",
            "resource_prefix": "nlo", "dedicated": True,
            "cleanup_required": cleanup_required, "resources": resources}


def git_head() -> str:
    import subprocess

    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True, cwd=str(LANE_DIR),
                          check=True).stdout.strip()


VALIDATOR_SOURCE = textwrap.dedent('''\
    """Pinned stub validator: checks the model's semantic contract."""
    import hashlib, json


    def validate(payload: bytes, response: bytes):
        try:
            doc = json.loads(response)
        except Exception:
            return False, "response is not JSON"
        expected = hashlib.sha256(payload).hexdigest()
        if doc.get("payload_sha256") != expected:
            return False, "response does not answer this payload"
        if doc.get("model") != "stub":
            return False, "wrong model identity"
        if not str(doc.get("result", "")).startswith("prediction-"):
            return False, "no prediction in response"
        return True, "stub semantic invariants hold"
''')


def write_validator(base: Path) -> Path:
    path = base / "stub_validator.py"
    path.write_text(VALIDATOR_SOURCE, encoding="utf-8")
    return path
