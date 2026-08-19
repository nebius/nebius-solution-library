#!/usr/bin/env python3
"""Render isolated Boltz2 target, one-shot restore, and semantic-probe YAML."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import posixpath
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Iterable

import yaml


HERE = Path(__file__).resolve().parent
BASE_DYNAMO = HERE.parent / "dynamo"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


base = _load_module("openfold2_dynamo_render_for_boltz2", BASE_DYNAMO / "render.py")
base_lint = _load_module("openfold2_dynamo_lint_for_boltz2", BASE_DYNAMO / "lint_manifest.py")

NAMESPACE = "nim-fast-start"
NIM_IMAGE = (
    "nvcr.io/nim/mit/boltz2@sha256:"
    "0788c95c8b5b6c1a73a62c656b298ecc353a8187dc22b794f496ae40672c4c98"
)
OPENFOLD_IMAGE = base.NIM_IMAGE
RUN_SCHEMA = "archvteams.nebius.ai/boltz2-faststart-run/v1"
EXTERNAL_TMP_RUN_SCHEMA = (
    "archvteams.nebius.ai/boltz2-external-tmp-faststart-run/v1"
)
BINDING_SCHEMA = "archvteams.nebius.ai/boltz2-target-binding/v1"
VALIDATOR_SHA256 = "4b4e04b62cd8aff2027844f75002012439d7cb5d44f91f4ac514a99abf2217c8"
EXTERNAL_TMP_CHECKPOINT_ID = "boltz2-native-f7-external-tmp-v2"
EXTERNAL_TMP_ARTIFACT_VERSION = "2"
EXTERNAL_TMP_PVC = "boltz2-tmp-state-native-f7-v2"
EXTERNAL_TMP_CSI_DRIVER = "compute.csi.nebius.com"
EXTERNAL_TMP_VOLUME_HANDLE_PREFIX = "computedisk-"
EXTERNAL_TMP_SEED_VERSION = "boltz2-native-f7-tmp-seed-v2"
EXTERNAL_TMP_MOUNT_PATH = "/tmp"
EXTERNAL_TMP_ENV = [
    {"name": "TMPDIR", "value": EXTERNAL_TMP_MOUNT_PATH},
    {"name": "TEMP", "value": EXTERNAL_TMP_MOUNT_PATH},
    {"name": "TMP", "value": EXTERNAL_TMP_MOUNT_PATH},
]
SHA256 = re.compile(r"^[0-9a-f]{64}$")
DNS_SUBDOMAIN = re.compile(
    r"^[a-z0-9](?:[-a-z0-9.]{0,251}[a-z0-9])?$"
)
VOLUME_HANDLE = re.compile(r"^computedisk-[a-z0-9]+$")


class RenderError(ValueError):
    pass


def _target_name(run_id: str) -> str:
    return f"b2-target-{run_id}"


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RenderError(f"cannot read {label}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(value, dict):
        raise RenderError(f"{label} must be an object")
    return value


def validate_contract(value: dict[str, Any]) -> dict[str, Any]:
    original = base.VALIDATOR_SHA256
    try:
        base.VALIDATOR_SHA256 = VALIDATOR_SHA256
        return base.validate_contract(value)
    except base.RenderError as exc:
        raise RenderError(str(exc)) from exc
    finally:
        base.VALIDATOR_SHA256 = original


def validate_run(value: dict[str, Any]) -> dict[str, Any]:
    schema = value.get("schema")
    if schema not in {RUN_SCHEMA, EXTERNAL_TMP_RUN_SCHEMA}:
        raise RenderError("run config schema is not supported")
    base_keys = {
        "schema",
        "demand_at",
        "run_id",
        "target_node",
        "checkpoint_id",
        "artifact_version",
        "artifact_manifest_sha256",
        "artifact_pvc",
        "cache_pvc",
    }
    external_keys = {
        "tmp_state_pvc",
        "tmp_state_pvc_uid",
        "tmp_state_pv_name",
        "tmp_state_pv_uid",
        "tmp_state_csi_driver",
        "tmp_state_volume_handle",
        "tmp_clone_subpath",
        "tmp_seed_version",
        "tmp_seed_tree_sha256",
        "tmp_clone_tree_sha256",
        "tmp_seed_seal_receipt_sha256",
        "tmp_clone_receipt_sha256",
    }
    expected_keys = base_keys | (external_keys if schema == EXTERNAL_TMP_RUN_SCHEMA else set())
    actual_keys = set(value)
    if actual_keys != expected_keys:
        raise RenderError(
            "run config keys do not match schema; "
            f"missing={sorted(expected_keys - actual_keys)}, "
            f"extra={sorted(actual_keys - expected_keys)}"
        )
    translated = {key: copy.deepcopy(value[key]) for key in base_keys}
    translated["schema"] = base.RUN_SCHEMA
    try:
        base.validate_run(translated)
    except base.RenderError as exc:
        raise RenderError(str(exc)) from exc
    if schema == EXTERNAL_TMP_RUN_SCHEMA:
        if value["checkpoint_id"] != EXTERNAL_TMP_CHECKPOINT_ID:
            raise RenderError("external-tmp run checkpoint_id is not the reviewed candidate")
        if value["artifact_version"] != EXTERNAL_TMP_ARTIFACT_VERSION:
            raise RenderError("external-tmp run artifact_version must be 2")
        if value["artifact_pvc"] != "mlspec-archvteams-2407-ckpt-m3":
            raise RenderError("external-tmp run changed the checkpoint PVC")
        if value["cache_pvc"] != "boltz2-nim-cache-native-f7-r3":
            raise RenderError("external-tmp run changed the Boltz2 cache PVC")
        if value["tmp_state_pvc"] != EXTERNAL_TMP_PVC:
            raise RenderError("external-tmp run tmp_state_pvc is not the dedicated claim")
        try:
            pvc_uid = uuid.UUID(str(value["tmp_state_pvc_uid"]))
        except ValueError as exc:
            raise RenderError("tmp_state_pvc_uid must be a canonical UUID") from exc
        if str(pvc_uid) != value["tmp_state_pvc_uid"]:
            raise RenderError("tmp_state_pvc_uid must be a canonical lowercase UUID")
        pv_name = value["tmp_state_pv_name"]
        if (
            not isinstance(pv_name, str)
            or not pv_name
            or len(pv_name) > 253
            or not DNS_SUBDOMAIN.fullmatch(pv_name)
        ):
            raise RenderError("tmp_state_pv_name must be one normalized PV name")
        try:
            pv_uid = uuid.UUID(str(value["tmp_state_pv_uid"]))
        except ValueError as exc:
            raise RenderError("tmp_state_pv_uid must be a canonical UUID") from exc
        if str(pv_uid) != value["tmp_state_pv_uid"]:
            raise RenderError("tmp_state_pv_uid must be a canonical lowercase UUID")
        if value["tmp_state_csi_driver"] != EXTERNAL_TMP_CSI_DRIVER:
            raise RenderError("tmp_state_csi_driver is not the reviewed CSI driver")
        handle = value["tmp_state_volume_handle"]
        if (
            not isinstance(handle, str)
            or not VOLUME_HANDLE.fullmatch(handle)
        ):
            raise RenderError("tmp_state_volume_handle is not an immutable provider identity")
        expected_subpath = f"runs/{value['run_id']}"
        subpath = value["tmp_clone_subpath"]
        if (
            not isinstance(subpath, str)
            or posixpath.normpath(subpath) != subpath
            or subpath != expected_subpath
            or subpath.startswith("/")
        ):
            raise RenderError("tmp_clone_subpath must be the exact runs/<run_id> path")
        if value["tmp_seed_version"] != EXTERNAL_TMP_SEED_VERSION:
            raise RenderError("tmp_seed_version is not the reviewed immutable seed")
        for field in (
            "tmp_seed_tree_sha256",
            "tmp_clone_tree_sha256",
            "tmp_seed_seal_receipt_sha256",
            "tmp_clone_receipt_sha256",
        ):
            if not isinstance(value[field], str) or not SHA256.fullmatch(value[field]):
                raise RenderError(f"{field} must be one lowercase SHA-256")
        if value["tmp_clone_tree_sha256"] != value["tmp_seed_tree_sha256"]:
            raise RenderError("tmp clone tree must exactly match the admitted seed tree")
    return value


def validate_binding(value: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    translated = copy.deepcopy(value)
    if translated.get("schema") != BINDING_SCHEMA:
        raise RenderError("binding schema is not supported")
    translated["schema"] = base.BINDING_SCHEMA
    translated["pod_name"] = f"of2-target-{run['run_id']}"
    translated["container_name"] = "openfold2"
    translated["image_id"] = OPENFOLD_IMAGE
    translated_run = copy.deepcopy(run)
    translated_run["schema"] = base.RUN_SCHEMA
    try:
        base.validate_binding(translated, translated_run)
    except base.RenderError as exc:
        raise RenderError(str(exc)) from exc
    if value.get("pod_name") != _target_name(run["run_id"]):
        raise RenderError("binding pod_name does not match the rendered Boltz2 target")
    if value.get("container_name") != "boltz2":
        raise RenderError("binding container_name must be boltz2")
    if value.get("image_id") != NIM_IMAGE:
        raise RenderError("binding image_id is not the exact pinned Boltz2 digest")
    return value


def _base_tokens(run: dict[str, Any], contract: dict[str, Any]) -> dict[str, str]:
    run_id = run["run_id"]
    return {
        "@@RUN_ID@@": run_id,
        "@@TARGET_NAME@@": _target_name(run_id),
        "@@TARGET_NODE@@": run["target_node"],
        "@@CHECKPOINT_ID@@": run["checkpoint_id"],
        "@@ARTIFACT_VERSION@@": run["artifact_version"],
        "@@ARTIFACT_MANIFEST_SHA256@@": run["artifact_manifest_sha256"],
        "@@ARTIFACT_PVC@@": run["artifact_pvc"],
        "@@CACHE_PVC@@": run["cache_pvc"],
        "@@TOOL_BUNDLE_SHA256@@": contract["tool_bundle"]["content_sha256"],
        "@@CANARY_SERVICE@@": f"b2-canary-{run_id}",
        "@@QUALIFIED_SERVICE@@": f"b2-qualified-{run_id}",
        "@@TARGET_NETWORK_POLICY@@": f"b2-target-{run_id}",
        "@@PROBE_NETWORK_POLICY@@": f"b2-probe-{run_id}",
        "@@WORKER_NAME@@": f"b2-restore-{run_id}",
        "@@WORKER_IMAGE@@": contract["worker_image"],
        "@@WORKER_EXECUTABLE@@": contract["worker_executable"],
        "@@PROBE_NAME@@": f"b2-semantic-{run_id}",
        "@@PROBE_IMAGE@@": contract["probe_image"],
        "@@PROBE_EXECUTABLE@@": contract["probe_executable"],
        "@@PROBE_RUN_ID_1@@": f"{run_id}-semantic-a",
        "@@PROBE_RUN_ID_2@@": f"{run_id}-semantic-b",
        "@@DEMAND_AT@@": run["demand_at"],
    }


def _boltz_structure(value: Any) -> Any:
    if isinstance(value, dict):
        return {_boltz_structure(key): _boltz_structure(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_boltz_structure(item) for item in value]
    if isinstance(value, str):
        if value == OPENFOLD_IMAGE:
            return NIM_IMAGE
        return value.replace("validate_openfold2", "validate_boltz2").replace(
            "OpenFold2", "Boltz2"
        ).replace("openfold2", "boltz2")
    return value


def _load_template(name: str) -> list[dict[str, Any]]:
    try:
        docs = base._load_template(name)
    except base.RenderError as exc:
        raise RenderError(str(exc)) from exc
    return _boltz_structure(docs)


def render_target(run: dict[str, Any], contract: dict[str, Any]) -> list[dict[str, Any]]:
    documents = base._replace(_load_template("target.yaml.tmpl"), _base_tokens(run, contract), None)
    if run["schema"] == EXTERNAL_TMP_RUN_SCHEMA:
        pods = [document for document in documents if document.get("kind") == "Pod"]
        if len(pods) != 1:
            raise RenderError("target template must contain exactly one Pod")
        pod = pods[0]
        annotations = pod["metadata"]["annotations"]
        annotations.update(
            {
                "archvteams.nebius.ai/tmp-state-pvc-name": run["tmp_state_pvc"],
                "archvteams.nebius.ai/tmp-state-pvc-uid": run["tmp_state_pvc_uid"],
                "archvteams.nebius.ai/tmp-state-pv-name": run["tmp_state_pv_name"],
                "archvteams.nebius.ai/tmp-state-pv-uid": run["tmp_state_pv_uid"],
                "archvteams.nebius.ai/tmp-state-csi-driver": run[
                    "tmp_state_csi_driver"
                ],
                "archvteams.nebius.ai/tmp-state-volume-handle": run[
                    "tmp_state_volume_handle"
                ],
                "archvteams.nebius.ai/tmp-clone-subpath": run["tmp_clone_subpath"],
                "archvteams.nebius.ai/tmp-seed-version": run["tmp_seed_version"],
                "archvteams.nebius.ai/tmp-seed-tree-sha256": run[
                    "tmp_seed_tree_sha256"
                ],
                "archvteams.nebius.ai/tmp-clone-tree-sha256": run[
                    "tmp_clone_tree_sha256"
                ],
                "archvteams.nebius.ai/tmp-seed-seal-receipt-sha256": run[
                    "tmp_seed_seal_receipt_sha256"
                ],
                "archvteams.nebius.ai/tmp-clone-receipt-sha256": run[
                    "tmp_clone_receipt_sha256"
                ],
            }
        )
        container = pod["spec"]["containers"][0]
        container["env"].extend(copy.deepcopy(EXTERNAL_TMP_ENV))
        container["volumeMounts"].append(
            {
                "name": "tmp-state",
                "mountPath": EXTERNAL_TMP_MOUNT_PATH,
                "subPath": run["tmp_clone_subpath"],
                "readOnly": False,
            }
        )
        pod["spec"]["volumes"].append(
            {
                "name": "tmp-state",
                "persistentVolumeClaim": {
                    "claimName": run["tmp_state_pvc"],
                    "readOnly": False,
                },
            }
        )
    base._assert_no_placeholders(documents)
    return documents


def render_restore(
    run: dict[str, Any], contract: dict[str, Any], binding: dict[str, Any]
) -> list[dict[str, Any]]:
    fields = {
        "target_namespace": binding["namespace"],
        "target_name": binding["pod_name"],
        "target_uid": binding["pod_uid"],
        "target_container": binding["container_name"],
        "target_container_id": binding["container_id"],
        "target_cgroup": binding["cgroup"],
        "target_pod_ip": binding["pod_ip"],
        "target_node": binding["node"],
        "target_pod_spec_sha256": binding["pod_spec_sha256"],
        "expected_image_id": binding["image_id"],
        "run_id": run["run_id"],
        "checkpoint_id": run["checkpoint_id"],
        "artifact_version": run["artifact_version"],
        "artifact_manifest_sha256": run["artifact_manifest_sha256"],
        "tool_bundle_sha256": contract["tool_bundle"]["content_sha256"],
    }
    args = [item.format_map(fields) for item in base.REQUIRED_ARGUMENT_TEMPLATE]
    tokens = _base_tokens(run, contract)
    tokens.update({
        "@@TARGET_UID@@": binding["pod_uid"],
        "@@TARGET_CONTAINER_ID@@": binding["container_id"],
        "@@TARGET_CGROUP@@": binding["cgroup"],
        "@@TARGET_POD_IP@@": binding["pod_ip"],
        "@@TARGET_POD_SPEC_SHA256@@": binding["pod_spec_sha256"],
    })
    documents = base._replace(_load_template("restore-worker.yaml.tmpl"), tokens, args)
    base._assert_no_placeholders(documents)
    return documents


def render_probe(
    run: dict[str, Any], contract: dict[str, Any], binding: dict[str, Any]
) -> list[dict[str, Any]]:
    source = (HERE / "validate_boltz2.py").read_bytes()
    if hashlib.sha256(source).hexdigest() != VALIDATOR_SHA256:
        raise RenderError("strict Boltz2 validator source digest changed")
    tokens = _base_tokens(run, contract)
    tokens.update({
        "@@TARGET_UID@@": binding["pod_uid"],
        "@@TARGET_POD_SPEC_SHA256@@": binding["pod_spec_sha256"],
        "@@VALIDATOR_SHA256@@": VALIDATOR_SHA256,
        "@@VALIDATOR_SOURCE@@": source.decode("utf-8"),
    })
    documents = base._replace(_load_template("semantic-probe.yaml.tmpl"), tokens, None)
    jobs = [document for document in documents if document.get("kind") == "Job"]
    if len(jobs) != 1:
        raise RenderError("semantic probe template must contain exactly one Job")
    # Keep the external client as a separate Pod reached through the ClusterIP,
    # but constrain it to the same stable, explicitly approved node as the
    # target.  This prevents an otherwise CPU-only probe from being assigned to
    # transient preemptible capacity while preserving the service boundary.
    jobs[0]["spec"]["template"]["spec"]["affinity"] = {
        "nodeAffinity": {
            "requiredDuringSchedulingIgnoredDuringExecution": {
                "nodeSelectorTerms": [{
                    "matchExpressions": [{
                        "key": "kubernetes.io/hostname",
                        "operator": "In",
                        "values": [run["target_node"]],
                    }]
                }]
            }
        }
    }
    base._assert_no_placeholders(documents)
    return documents


def _normalize_for_openfold_lint(value: Any, *, source_value: bool = False) -> Any:
    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            normalized_key = _normalize_for_openfold_lint(key)
            result[normalized_key] = _normalize_for_openfold_lint(
                item, source_value=source_value or key == "data"
            )
        return result
    if isinstance(value, list):
        return [_normalize_for_openfold_lint(item, source_value=source_value) for item in value]
    if isinstance(value, str) and not source_value:
        if value == NIM_IMAGE:
            return OPENFOLD_IMAGE
        return value.replace("validate_boltz2", "validate_openfold2").replace(
            "Boltz2", "OpenFold2"
        ).replace("boltz2", "openfold2").replace("b2-", "of2-")
    return value


def lint_documents(documents: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    prepared = copy.deepcopy(documents)
    targets = [document for document in prepared if document.get("kind") == "Pod"]
    for target in targets:
        labels = target.get("metadata", {}).get("labels", {})
        if labels.get("app.kubernetes.io/component") != "restore-target":
            continue
        annotations = target.get("metadata", {}).get("annotations", {})
        spec = target.get("spec", {})
        containers = spec.get("containers", [])
        if not isinstance(containers, list) or len(containers) != 1:
            continue
        container = containers[0]
        volumes = spec.get("volumes", [])
        mounts = container.get("volumeMounts", [])
        tmp_volumes = [item for item in volumes if item.get("name") == "tmp-state"]
        tmp_mounts = [item for item in mounts if item.get("name") == "tmp-state"]
        external_markers = {
            "archvteams.nebius.ai/tmp-state-pvc-name",
            "archvteams.nebius.ai/tmp-state-pvc-uid",
            "archvteams.nebius.ai/tmp-state-pv-name",
            "archvteams.nebius.ai/tmp-state-pv-uid",
            "archvteams.nebius.ai/tmp-state-csi-driver",
            "archvteams.nebius.ai/tmp-state-volume-handle",
            "archvteams.nebius.ai/tmp-clone-subpath",
            "archvteams.nebius.ai/tmp-seed-version",
            "archvteams.nebius.ai/tmp-seed-tree-sha256",
            "archvteams.nebius.ai/tmp-clone-tree-sha256",
            "archvteams.nebius.ai/tmp-seed-seal-receipt-sha256",
            "archvteams.nebius.ai/tmp-clone-receipt-sha256",
        }
        is_external = bool(tmp_volumes or tmp_mounts or external_markers & set(annotations))
        if not is_external:
            continue
        run_id = labels.get("archvteams.nebius.ai/run-id")
        expected_subpath = f"runs/{run_id}" if isinstance(run_id, str) else None
        if len(tmp_volumes) != 1 or tmp_volumes[0].get("persistentVolumeClaim") != {
            "claimName": EXTERNAL_TMP_PVC,
            "readOnly": False,
        }:
            errors.append("external-tmp target must use the exact writable tmp-state PVC")
        expected_mount = {
            "name": "tmp-state",
            "mountPath": EXTERNAL_TMP_MOUNT_PATH,
            "subPath": expected_subpath,
            "readOnly": False,
        }
        if len(tmp_mounts) != 1 or tmp_mounts[0] != expected_mount:
            errors.append("external-tmp target must mount the exact per-run subPath at /tmp")
        expected_annotations = {
            "archvteams.nebius.ai/tmp-state-pvc-name": EXTERNAL_TMP_PVC,
            "archvteams.nebius.ai/tmp-state-csi-driver": EXTERNAL_TMP_CSI_DRIVER,
            "archvteams.nebius.ai/tmp-clone-subpath": expected_subpath,
            "archvteams.nebius.ai/tmp-seed-version": EXTERNAL_TMP_SEED_VERSION,
        }
        if any(annotations.get(key) != value for key, value in expected_annotations.items()):
            errors.append("external-tmp target annotations do not match the run-scoped mount")
        for label, key in (
            ("PVC", "archvteams.nebius.ai/tmp-state-pvc-uid"),
            ("PV", "archvteams.nebius.ai/tmp-state-pv-uid"),
        ):
            try:
                parsed_uid = uuid.UUID(str(annotations.get(key)))
            except ValueError:
                parsed_uid = None
            if parsed_uid is None or str(parsed_uid) != annotations.get(key):
                errors.append(
                    f"external-tmp target {label} UID annotation is not canonical"
                )
        pv_name = annotations.get("archvteams.nebius.ai/tmp-state-pv-name")
        if (
            not isinstance(pv_name, str)
            or not pv_name
            or len(pv_name) > 253
            or not DNS_SUBDOMAIN.fullmatch(pv_name)
        ):
            errors.append("external-tmp target PV name annotation is not normalized")
        volume_handle = annotations.get(
            "archvteams.nebius.ai/tmp-state-volume-handle"
        )
        if (
            not isinstance(volume_handle, str)
            or not VOLUME_HANDLE.fullmatch(volume_handle)
        ):
            errors.append("external-tmp target CSI volume handle is not provider-scoped")
        for key in (
            "archvteams.nebius.ai/tmp-seed-tree-sha256",
            "archvteams.nebius.ai/tmp-clone-tree-sha256",
            "archvteams.nebius.ai/tmp-seed-seal-receipt-sha256",
            "archvteams.nebius.ai/tmp-clone-receipt-sha256",
        ):
            if not isinstance(annotations.get(key), str) or not SHA256.fullmatch(
                annotations[key]
            ):
                errors.append(f"external-tmp target annotation {key} is not a SHA-256")
        if annotations.get(
            "archvteams.nebius.ai/tmp-clone-tree-sha256"
        ) != annotations.get("archvteams.nebius.ai/tmp-seed-tree-sha256"):
            errors.append("external-tmp target clone and seed tree annotations differ")
        base_env = [
            {"name": "DYN_SNAPSHOT_RESTORE_STANDBY", "value": "1"},
            {"name": "DYN_SNAPSHOT_CONTROL_DIR", "value": "/snapshot-control"},
            {"name": "NIM_CACHE_PATH", "value": "/opt/nim/.cache"},
        ]
        if container.get("env") != base_env + EXTERNAL_TMP_ENV:
            errors.append("external-tmp target environment is not the exact approved set")
        # The shared OpenFold2 linter knows the production target's exact base
        # shape.  Validate the one-variable extension above, then remove only
        # that extension before reusing all of its existing safety checks.
        container["env"] = base_env
        container["volumeMounts"] = [item for item in mounts if item.get("name") != "tmp-state"]
        spec["volumes"] = [item for item in volumes if item.get("name") != "tmp-state"]
    normalized = _normalize_for_openfold_lint(prepared)
    original = base_lint.VALIDATOR_SHA256
    try:
        base_lint.VALIDATOR_SHA256 = VALIDATOR_SHA256
        return errors + base_lint.lint_documents(normalized)
    finally:
        base_lint.VALIDATOR_SHA256 = original


def dump_documents(documents: Iterable[dict[str, Any]]) -> None:
    yaml.safe_dump_all(
        list(documents), sys.stdout, explicit_start=True, default_flow_style=False, sort_keys=False
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)
    for mode in ("target", "restore", "probe"):
        child = subparsers.add_parser(mode)
        child.add_argument("--contract", type=Path, required=True)
        child.add_argument("--run-config", type=Path, required=True)
        if mode != "target":
            child.add_argument("--binding", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        contract = validate_contract(_read_json(args.contract, "contract"))
        run = validate_run(_read_json(args.run_config, "run config"))
        if args.mode == "target":
            documents = render_target(run, contract)
        else:
            binding = validate_binding(_read_json(args.binding, "binding"), run)
            documents = (
                render_restore(run, contract, binding)
                if args.mode == "restore"
                else render_probe(run, contract, binding)
            )
        errors = lint_documents(documents)
        if errors:
            raise RenderError("rendered manifest failed static checks: " + "; ".join(errors))
        dump_documents(documents)
    except (RenderError, OSError, UnicodeDecodeError) as exc:
        print(f"render-boltz2: refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
