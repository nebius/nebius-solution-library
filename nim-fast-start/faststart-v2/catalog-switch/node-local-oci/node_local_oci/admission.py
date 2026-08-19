"""Admission: node identity, storage identity, and durable external T0.

Nothing side-effecting happens until every check here passes:

- the node's kernel boot id and instance identity match the controller-pinned
  policy (CTL-12 fencing: a foreign replacement node has zero trust);
- the Network SSD device/mount identity matches the policy pins, read from
  the kernel's own ``/proc`` mounts table and ``/dev/disk/by-uuid``;
- the ``request.accepted`` event exists in the shared request-SLO ledger *on
  disk*, its exact line bytes hash to the recorder-signed authorization, and
  its payload passes the pinned shared harness validator
  (``_validate_acceptance_data``) against the pinned trace request — the
  agent never defines its own T0 schema.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .errors import Refusal, require

BOOT_ID_PATH = Path("/proc/sys/kernel/random/boot_id")
MACHINE_ID_PATH = Path("/etc/machine-id")
MOUNTS_PATH = Path("/proc/self/mounts")
DEV_BY_UUID = Path("/dev/disk/by-uuid")


def observe_boot_id(boot_id_path: Path = BOOT_ID_PATH) -> str:
    try:
        value = boot_id_path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise Refusal("admission.boot-id-unreadable", f"{boot_id_path}: {error}") from error
    require(len(value) == 36, "admission.boot-id-shape", f"boot id malformed: {value!r}")
    return value


def verify_node_identity(policy: dict, binaries, *,
                         boot_id_path: Path = BOOT_ID_PATH,
                         machine_id_path: Path = MACHINE_ID_PATH) -> dict:
    """Prove this process runs on the exact node the controller admitted."""
    node = policy["node"]
    boot_id = observe_boot_id(boot_id_path)
    require(boot_id == node["boot_id"], "admission.boot-id",
            f"observed boot id {boot_id} != pinned {node['boot_id']}; "
            "a rebooted or replaced node has zero prior trust")
    if node["instance_source"] == "machine-id":
        try:
            observed = machine_id_path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise Refusal("admission.machine-id-unreadable",
                          f"{machine_id_path}: {error}") from error
    else:  # cloud-metadata: controller pins a metadata client binary
        execution = binaries.run("metadata-client", [], timeout_s=15.0)
        require(execution.returncode == 0, "admission.metadata-client",
                f"metadata client failed: {execution.stderr.strip()!r}")
        observed = execution.stdout.strip()
    require(observed == node["instance_id"], "admission.instance-id",
            f"observed instance id {observed!r} != pinned {node['instance_id']!r}")
    return {"boot_id": boot_id, "instance_id": observed,
            "instance_source": node["instance_source"]}


def verify_storage(policy: dict, *, mounts_path: Path = MOUNTS_PATH,
                   dev_by_uuid: Path = DEV_BY_UUID) -> dict:
    """Prove the pinned storage device is the filesystem behind the mountpoint."""
    storage = policy["storage"]
    uuid_link = dev_by_uuid / storage["fs_uuid"]
    require(uuid_link.exists(), "admission.storage-uuid",
            f"no device carries filesystem uuid {storage['fs_uuid']}")
    resolved_device = str(uuid_link.resolve())
    expected_device = str(Path(storage["device"]).resolve())
    require(resolved_device == expected_device, "admission.storage-device",
            f"fs uuid {storage['fs_uuid']} resolves to {resolved_device}, "
            f"policy pins {expected_device}")
    try:
        mounts = mounts_path.read_text(encoding="utf-8")
    except OSError as error:
        raise Refusal("admission.mounts-unreadable", f"{mounts_path}: {error}") from error
    mounted_device = None
    for line in mounts.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] == storage["mountpoint"]:
            mounted_device = fields[0]
    require(mounted_device is not None, "admission.storage-unmounted",
            f"nothing is mounted at {storage['mountpoint']}")
    mounted_resolved = str(Path(mounted_device).resolve())
    require(mounted_resolved == expected_device, "admission.storage-mount-device",
            f"{storage['mountpoint']} is backed by {mounted_resolved}, "
            f"policy pins {expected_device}")
    return {"device": expected_device, "mountpoint": storage["mountpoint"],
            "fs_uuid": storage["fs_uuid"], "storage_class": storage["storage_class"]}


def verify_artifact(policy: dict, model_id: str) -> dict:
    """Full-content hash of the model artifact against the pinned sha256."""
    model = policy["models"][model_id]
    path = Path(model["artifact_path"])
    require(path.is_file() and not path.is_symlink(), "admission.artifact-missing",
            f"artifact absent or symlink: {path}")
    hasher = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            hasher.update(chunk)
    digest = hasher.hexdigest()
    require(digest == model["artifact_sha256"], "admission.artifact-hash",
            f"{path}: sha256 {digest} != pinned {model['artifact_sha256']}")
    return {"artifact_path": str(path), "artifact_sha256": digest, "bytes": size}


def _ledger_lines(ledger_path: Path) -> list[bytes]:
    require(ledger_path.is_file() and not ledger_path.is_symlink(),
            "admission.ledger-missing", f"shared ledger absent or symlink: {ledger_path}")
    data = ledger_path.read_bytes()
    require(len(data) > 0 and data.endswith(b"\n"), "admission.ledger-tail",
            "shared ledger is empty or not newline-terminated")
    return data.split(b"\n")[:-1]


def verify_t0(harness, trace: dict, ledger_path: Path, authorization: dict,
              bundle: dict, request_binding: dict, policy: dict) -> dict:
    """Verify the durable external ``request.accepted`` event for one attempt.

    ``authorization`` is the recorder-signed body (signature already verified
    by the caller against the recorder public key).
    """
    require(authorization["attempt_id"] == request_binding["attempt_id"],
            "admission.t0-attempt", "authorization names a different attempt")
    require(authorization["request_id"] == request_binding["request_id"],
            "admission.t0-request", "authorization names a different request")
    require(authorization["trace_id"] == bundle["trace_id"],
            "admission.t0-trace", "authorization trace_id != bundle trace_id")
    require(authorization["ledger_id"] == bundle["ledger_id"],
            "admission.t0-ledger", "authorization ledger_id != bundle ledger_id")

    lines = _ledger_lines(ledger_path)
    line_number = authorization["ledger_line_number"]
    require(line_number <= len(lines), "admission.t0-line-range",
            f"authorization points at line {line_number} but ledger has {len(lines)}")
    line = lines[line_number - 1]
    digest = hashlib.sha256(line + b"\n").hexdigest()
    require(digest == authorization["line_sha256"], "admission.t0-line-hash",
            "ledger line bytes do not hash to the recorder-authorized value")

    events = harness.load_ledger(ledger_path)  # shared shape/canonical validation
    event = events[line_number - 1]
    require(event["event_type"] == "request.accepted", "admission.t0-event-type",
            f"authorized line is a {event['event_type']!r} event, not request.accepted")
    require(event["attempt_id"] == request_binding["attempt_id"],
            "admission.t0-event-attempt", "event attempt_id mismatch")
    require(event["ledger_id"] == bundle["ledger_id"], "admission.t0-event-ledger",
            "event ledger_id != bundle ledger_id")
    require(event["trace_id"] == bundle["trace_id"], "admission.t0-event-trace",
            "event trace_id != bundle trace_id")
    require(event["observed_monotonic_ns"] == authorization["accepted_monotonic_ns"],
            "admission.t0-monotonic", "authorization monotonic != event monotonic")
    require(event["recorder"]["recorder_id"] == authorization["recorder_id"],
            "admission.t0-recorder", "authorization recorder_id != event recorder")
    require(bundle["issued_utc"] <= event["observed_at_utc"] <= bundle["deadline_utc"],
            "admission.t0-window",
            f"acceptance at {event['observed_at_utc']} is outside the command window "
            f"[{bundle['issued_utc']}, {bundle['deadline_utc']}]")

    matching = [request for request in trace["requests"]
                if request["attempt_id"] == request_binding["attempt_id"]]
    require(len(matching) == 1, "admission.t0-trace-request",
            f"trace does not contain exactly one request for attempt "
            f"{request_binding['attempt_id']!r}")
    trace_request = matching[0]
    require(trace_request["request_id"] == request_binding["request_id"],
            "admission.t0-trace-request-id", "trace request_id mismatch")

    # The pinned shared validator is the T0 authority; no private schema.
    harness._validate_acceptance_data(event["data"], trace_request)

    target = event["data"]["target"]
    model = policy["models"][bundle["target_model_id"]]
    require(target["model_id"] == bundle["target_model_id"],
            "admission.t0-model", f"accepted target model {target['model_id']!r} != "
            f"bundle target {bundle['target_model_id']!r}")
    require(target["model_version"] == model["model_version"],
            "admission.t0-model-version", "accepted model_version != policy pin")
    require(target["artifact_id"] == model["artifact_id"],
            "admission.t0-artifact-id", "accepted artifact_id != policy pin")
    require(target["artifact_version"] == model["artifact_version"],
            "admission.t0-artifact-version", "accepted artifact_version != policy pin")
    require(target["artifact_sha256"] == model["artifact_sha256"],
            "admission.t0-artifact-hash", "accepted artifact_sha256 != policy pin")

    event_input = event["data"]["input"]
    require(event_input["payload_sha256"] == request_binding["payload_sha256"],
            "admission.t0-input-hash",
            "accepted input payload hash != command-bundle pinned payload hash")
    require(event_input["input_bytes"] == request_binding["input_bytes"],
            "admission.t0-input-bytes",
            "accepted input byte count != command-bundle pinned byte count")

    environment = event["data"]["environment"]
    require(environment["image_digest"] == model["image_digest"],
            "admission.t0-image", "accepted environment image_digest != policy pin")
    require(environment["node_id"] == policy["node"]["instance_id"],
            "admission.t0-node", "accepted environment node_id != policy instance")
    require(environment["gpu_type"] == policy["gpu"]["product"],
            "admission.t0-gpu-type", "accepted gpu_type != policy gpu product")
    require(environment["gpu_count"] == policy["gpu"]["count"],
            "admission.t0-gpu-count", "accepted gpu_count != policy gpu count")

    ownership = event["data"]["ownership"]
    lease = policy["lease"]
    require(ownership["owner_task_id"] == lease["owner_task_id"],
            "admission.t0-owner", "accepted ownership owner_task_id != lease owner")
    require(ownership["resource_prefix"] == lease["resource_prefix"],
            "admission.t0-prefix", "accepted resource_prefix != lease prefix")

    return {"event": event, "trace_request": trace_request,
            "ledger_line_number": line_number, "line_sha256": digest}
