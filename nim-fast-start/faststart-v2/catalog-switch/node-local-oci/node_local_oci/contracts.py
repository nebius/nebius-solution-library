"""Closed-set contracts for every input the node agent consumes.

The agent acts only on four foreign-signed inputs — admission policy and
switch command bundle (controller), acceptance authorization (recorder), and
semantic verdict (oracle).  Each has an exact closed key set: unknown keys,
missing keys, or malformed values refuse.  There is no partial acceptance and
no ``zip``-style truncation anywhere: cardinalities are checked explicitly.
"""

from __future__ import annotations

import re

from .errors import Refusal, require

POLICY_SCHEMA = "catalog-switch/nlo-admission-policy/v1"
BUNDLE_SCHEMA = "catalog-switch/nlo-switch-command/v1"
AUTHORIZATION_SCHEMA = "catalog-switch/nlo-acceptance-authorization/v1"
VERDICT_SCHEMA = "catalog-switch/nlo-oracle-verdict/v1"
RECEIPT_SCHEMA = "catalog-switch/nlo-receipt/v1"
JOURNAL_SCHEMA = "catalog-switch/nlo-journal-link/v1"
REPORT_SCHEMA = "catalog-switch/nlo-run-report/v1"

LAUNCH_CLASSES = ("offline-validation", "live-h100")
LAUNCH_MODES = ("conventional", "snapshot")
INSTANCE_SOURCES = ("machine-id", "cloud-metadata")
REQUIRED_BINARIES = ("ctr", "nvidia-smi")

ID_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,191}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z")
IMAGE_DIGEST_RE = re.compile(r"(?:[^\s@]+@)?sha256:[0-9a-f]{64}")
BOOT_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _expect_keys(value: dict, keys: set[str], label: str) -> None:
    require(isinstance(value, dict), f"contract.{label}-shape", f"{label} is not an object")
    require(set(value) == keys, f"contract.{label}-keys",
            f"{label} keys {sorted(value)} != required {sorted(keys)}")


def _id(value, label: str) -> str:
    require(isinstance(value, str) and ID_RE.fullmatch(value) is not None,
            f"contract.{label}-id", f"{label} is not a valid identifier: {value!r}")
    return value


def _sha256(value, label: str) -> str:
    require(isinstance(value, str) and SHA256_RE.fullmatch(value) is not None,
            f"contract.{label}-sha256", f"{label} is not lowercase 64-hex")
    return value


def _utc(value, label: str) -> str:
    require(isinstance(value, str) and UTC_RE.fullmatch(value) is not None,
            f"contract.{label}-utc", f"{label} is not a microsecond UTC timestamp")
    return value


def _int_min(value, minimum: int, label: str) -> int:
    require(isinstance(value, int) and not isinstance(value, bool) and value >= minimum,
            f"contract.{label}-int", f"{label} must be an integer >= {minimum}")
    return value


def validate_policy(body: dict) -> dict:
    """Validate the controller admission policy body (signature already checked)."""
    _expect_keys(body, {"schema", "policy_id", "issued_utc", "launch_class", "node",
                        "lease", "binaries", "gpu", "storage", "models", "oracle",
                        "containerd_namespace"}, "policy")
    require(body["schema"] == POLICY_SCHEMA, "contract.policy-schema",
            f"policy schema {body['schema']!r}")
    _id(body["policy_id"], "policy-id")
    _utc(body["issued_utc"], "policy-issued")
    require(body["launch_class"] in LAUNCH_CLASSES, "contract.policy-launch-class",
            f"launch_class {body['launch_class']!r}")

    node = body["node"]
    _expect_keys(node, {"instance_id", "instance_source", "boot_id", "hostname"}, "policy-node")
    _id(node["instance_id"], "policy-instance")
    require(node["instance_source"] in INSTANCE_SOURCES, "contract.policy-instance-source",
            f"instance_source {node['instance_source']!r}")
    require(isinstance(node["boot_id"], str) and BOOT_ID_RE.fullmatch(node["boot_id"]) is not None,
            "contract.policy-boot-id", "node.boot_id is not a boot UUID")
    _id(node["hostname"], "policy-hostname")

    lease = body["lease"]
    _expect_keys(lease, {"lease_id", "owner_task_id", "resource_prefix",
                         "project_id", "region"}, "policy-lease")
    for key in sorted(lease):
        _id(lease[key], f"policy-lease-{key}")

    binaries = body["binaries"]
    require(isinstance(binaries, dict), "contract.policy-binaries-shape",
            "binaries is not an object")
    for name in REQUIRED_BINARIES:
        require(name in binaries, "contract.policy-binaries-missing",
                f"required binary pin absent: {name}")
    for name, pin in binaries.items():
        _id(name, "policy-binary-name")
        _expect_keys(pin, {"path", "sha256"}, "policy-binary")
        require(isinstance(pin["path"], str) and pin["path"].startswith("/"),
                "contract.policy-binary-path", f"binary path not absolute: {pin['path']!r}")
        _sha256(pin["sha256"], "policy-binary")

    gpu = body["gpu"]
    _expect_keys(gpu, {"product", "count", "uuids", "memory_total_mib"}, "policy-gpu")
    require(isinstance(gpu["product"], str) and len(gpu["product"]) > 0,
            "contract.policy-gpu-product", "gpu.product empty")
    _int_min(gpu["count"], 1, "policy-gpu-count")
    require(isinstance(gpu["uuids"], list) and len(gpu["uuids"]) == gpu["count"],
            "contract.policy-gpu-uuids", "gpu.uuids length != gpu.count")
    for uuid in gpu["uuids"]:
        require(isinstance(uuid, str) and uuid.startswith("GPU-") and len(uuid) > 4,
                "contract.policy-gpu-uuid", f"gpu uuid malformed: {uuid!r}")
    require(len(set(gpu["uuids"])) == gpu["count"], "contract.policy-gpu-uuid-dup",
            "gpu.uuids contains duplicates")
    _int_min(gpu["memory_total_mib"], 1, "policy-gpu-memory")

    storage = body["storage"]
    _expect_keys(storage, {"device", "mountpoint", "fs_uuid", "storage_class"}, "policy-storage")
    require(isinstance(storage["device"], str) and storage["device"].startswith("/dev/"),
            "contract.policy-storage-device", "storage.device not under /dev/")
    require(isinstance(storage["mountpoint"], str) and storage["mountpoint"].startswith("/"),
            "contract.policy-storage-mount", "storage.mountpoint not absolute")
    _id(storage["fs_uuid"], "policy-storage-uuid")
    _id(storage["storage_class"], "policy-storage-class")

    models = body["models"]
    require(isinstance(models, dict) and len(models) > 0, "contract.policy-models",
            "models catalog empty")
    for model_id, model in models.items():
        _id(model_id, "policy-model-id")
        _expect_keys(model, {"model_version", "image_digest", "artifact_id",
                             "artifact_version", "artifact_sha256", "artifact_path",
                             "endpoint", "health_path", "infer_path",
                             "run_args", "command", "snapshot_command"},
                     "policy-model")
        _id(model["model_version"], "policy-model-version")
        require(isinstance(model["image_digest"], str)
                and IMAGE_DIGEST_RE.fullmatch(model["image_digest"]) is not None,
                "contract.policy-model-image", f"image_digest malformed for {model_id}")
        _id(model["artifact_id"], "policy-artifact-id")
        _id(model["artifact_version"], "policy-artifact-version")
        _sha256(model["artifact_sha256"], "policy-artifact")
        require(isinstance(model["artifact_path"], str) and model["artifact_path"].startswith("/"),
                "contract.policy-artifact-path", "artifact_path not absolute")
        require(isinstance(model["endpoint"], str)
                and model["endpoint"].startswith("http://127.0.0.1:"),
                "contract.policy-endpoint",
                f"endpoint must be node-local 127.0.0.1: {model['endpoint']!r}")
        for key in ("health_path", "infer_path"):
            require(isinstance(model[key], str) and model[key].startswith("/"),
                    f"contract.policy-{key}", f"{key} not absolute")
        require(isinstance(model["run_args"], list)
                and all(isinstance(arg, str) for arg in model["run_args"]),
                "contract.policy-run-args", "run_args must be a list of strings")
        require(isinstance(model["command"], list) and len(model["command"]) > 0
                and all(isinstance(arg, str) for arg in model["command"]),
                "contract.policy-command",
                "command must be a non-empty list of strings")
        snapshot_command = model["snapshot_command"]
        require(snapshot_command is None
                or (isinstance(snapshot_command, list) and len(snapshot_command) > 0
                    and all(isinstance(arg, str) for arg in snapshot_command)),
                "contract.policy-snapshot-command",
                "snapshot_command must be null or a non-empty list of strings")

    oracle = body["oracle"]
    _expect_keys(oracle, {"validator_id", "validator_sha256"}, "policy-oracle")
    _id(oracle["validator_id"], "policy-oracle-id")
    _sha256(oracle["validator_sha256"], "policy-oracle")

    _id(body["containerd_namespace"], "policy-namespace")

    if body["launch_class"] == "live-h100":
        require(node["instance_source"] == "cloud-metadata",
                "contract.policy-live-instance-source",
                "live-h100 policy must bind cloud-metadata instance identity")
        require(gpu["product"].startswith("NVIDIA H100"),
                "contract.policy-live-gpu", f"live-h100 requires H100, got {gpu['product']!r}")
    return body


def validate_bundle(body: dict, policy: dict, policy_sha256: str) -> dict:
    """Validate the switch command bundle body against its admitted policy."""
    _expect_keys(body, {"schema", "command_id", "switch_uid", "policy_sha256",
                        "trace_id", "ledger_id", "fence", "nonce", "issued_utc",
                        "deadline_utc", "node", "prior_occupant", "target_model_id",
                        "launch_mode", "snapshot", "requests"}, "bundle")
    require(body["schema"] == BUNDLE_SCHEMA, "contract.bundle-schema",
            f"bundle schema {body['schema']!r}")
    _id(body["command_id"], "bundle-command")
    _id(body["switch_uid"], "bundle-switch-uid")
    _sha256(body["policy_sha256"], "bundle-policy")
    require(body["policy_sha256"] == policy_sha256, "contract.bundle-policy-binding",
            "bundle is not bound to the admitted policy bytes")
    _id(body["trace_id"], "bundle-trace")
    _id(body["ledger_id"], "bundle-ledger")
    _int_min(body["fence"], 1, "bundle-fence")
    _sha256(body["nonce"], "bundle-nonce")
    _utc(body["issued_utc"], "bundle-issued")
    _utc(body["deadline_utc"], "bundle-deadline")
    require(body["deadline_utc"] > body["issued_utc"], "contract.bundle-deadline-order",
            "deadline_utc must be after issued_utc")

    node = body["node"]
    _expect_keys(node, {"instance_id", "boot_id"}, "bundle-node")
    require(node["instance_id"] == policy["node"]["instance_id"],
            "contract.bundle-node-instance", "bundle instance_id != policy instance_id")
    require(node["boot_id"] == policy["node"]["boot_id"],
            "contract.bundle-node-boot", "bundle boot_id != policy boot_id")

    prior = body["prior_occupant"]
    if prior is not None:
        _expect_keys(prior, {"model_id", "model_version", "container_id"}, "bundle-prior")
        _id(prior["model_id"], "bundle-prior-model")
        _id(prior["model_version"], "bundle-prior-version")
        _id(prior["container_id"], "bundle-prior-container")

    target = body["target_model_id"]
    require(target in policy["models"], "contract.bundle-target-unknown",
            f"target model {target!r} is not in the admitted policy catalog")
    if prior is not None:
        require(prior["container_id"].startswith("nlo-"),
                "contract.bundle-prior-prefix",
                "prior occupant container is outside the task-owned nlo- prefix")

    require(body["launch_mode"] in LAUNCH_MODES, "contract.bundle-launch-mode",
            f"launch_mode {body['launch_mode']!r}")
    snapshot = body["snapshot"]
    if body["launch_mode"] == "snapshot":
        _expect_keys(snapshot, {"snapshot_id", "bytes", "sha256", "runtime_image_digest",
                                "driver_version", "gpu_product"}, "bundle-snapshot")
        _id(snapshot["snapshot_id"], "bundle-snapshot-id")
        _int_min(snapshot["bytes"], 1, "bundle-snapshot-bytes")
        _sha256(snapshot["sha256"], "bundle-snapshot")
        require(snapshot["runtime_image_digest"] == policy["models"][target]["image_digest"],
                "contract.bundle-snapshot-image",
                "snapshot runtime image digest != target image digest")
        require(isinstance(snapshot["driver_version"], str)
                and len(snapshot["driver_version"]) > 0,
                "contract.bundle-snapshot-driver", "snapshot driver_version empty")
        require(snapshot["gpu_product"] == policy["gpu"]["product"],
                "contract.bundle-snapshot-gpu",
                "snapshot gpu_product != policy gpu product")
    else:
        require(snapshot is None, "contract.bundle-snapshot-extraneous",
                "conventional launch must not carry a snapshot binding")

    requests = body["requests"]
    require(isinstance(requests, list), "contract.bundle-requests-shape",
            "requests is not a list")
    require(len(requests) == 2, "contract.bundle-cardinality",
            f"exactly two request bindings required, got {len(requests)}")
    for item in requests:
        _expect_keys(item, {"attempt_id", "request_id", "payload_sha256",
                            "input_bytes", "scenario"}, "bundle-request")
        _id(item["attempt_id"], "bundle-attempt")
        _id(item["request_id"], "bundle-request-id")
        _sha256(item["payload_sha256"], "bundle-payload")
        _int_min(item["input_bytes"], 1, "bundle-input-bytes")
        _id(item["scenario"], "bundle-scenario")
    require(len({r["attempt_id"] for r in requests}) == 2, "contract.bundle-attempt-dup",
            "request bindings must name two distinct attempts")
    require(len({r["request_id"] for r in requests}) == 2, "contract.bundle-request-dup",
            "request bindings must name two distinct requests")
    require(len({r["payload_sha256"] for r in requests}) == 2, "contract.bundle-payload-dup",
            "the two pinned request payloads must be distinct")
    return body


def validate_authorization(body: dict) -> dict:
    """Validate a recorder acceptance authorization body."""
    _expect_keys(body, {"schema", "attempt_id", "request_id", "trace_id", "ledger_id",
                        "ledger_line_number", "line_sha256", "accepted_monotonic_ns",
                        "recorder_id"}, "authorization")
    require(body["schema"] == AUTHORIZATION_SCHEMA, "contract.authorization-schema",
            f"authorization schema {body['schema']!r}")
    _id(body["attempt_id"], "authorization-attempt")
    _id(body["request_id"], "authorization-request")
    _id(body["trace_id"], "authorization-trace")
    _id(body["ledger_id"], "authorization-ledger")
    _int_min(body["ledger_line_number"], 1, "authorization-line")
    _sha256(body["line_sha256"], "authorization-line-hash")
    _int_min(body["accepted_monotonic_ns"], 1, "authorization-monotonic")
    _id(body["recorder_id"], "authorization-recorder")
    return body


def validate_verdict(body: dict) -> dict:
    """Validate an oracle semantic verdict body."""
    _expect_keys(body, {"schema", "verdict_id", "switch_uid", "attempt_id", "model_id",
                        "model_version", "validator_id", "validator_sha256",
                        "request_payload_sha256", "response_sha256", "response_bytes",
                        "complete_body", "semantically_valid", "reason", "issued_utc"},
                 "verdict")
    require(body["schema"] == VERDICT_SCHEMA, "contract.verdict-schema",
            f"verdict schema {body['schema']!r}")
    _id(body["verdict_id"], "verdict-id")
    _id(body["switch_uid"], "verdict-switch-uid")
    _id(body["attempt_id"], "verdict-attempt")
    _id(body["model_id"], "verdict-model")
    _id(body["model_version"], "verdict-model-version")
    _id(body["validator_id"], "verdict-validator")
    _sha256(body["validator_sha256"], "verdict-validator")
    _sha256(body["request_payload_sha256"], "verdict-payload")
    _sha256(body["response_sha256"], "verdict-response")
    _int_min(body["response_bytes"], 1, "verdict-response-bytes")
    require(isinstance(body["complete_body"], bool), "contract.verdict-complete",
            "complete_body must be a bool")
    require(isinstance(body["semantically_valid"], bool), "contract.verdict-valid",
            "semantically_valid must be a bool")
    require(isinstance(body["reason"], str) and len(body["reason"]) > 0,
            "contract.verdict-reason", "reason empty")
    _utc(body["issued_utc"], "verdict-issued")
    require(body["response_sha256"] != body["request_payload_sha256"],
            "contract.verdict-echo",
            "response hash equals request payload hash: echo responses are never valid")
    return body
