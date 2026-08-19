#!/usr/bin/env python3
"""Fail-closed admission contract for the Kubernetes switch baseline."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from performance.request_slo.harness import (
    HarnessError,
    IMAGE_DIGEST_RE,
    SCENARIOS,
    _json_loads,
    canonical_json,
    canonical_sha256,
    file_sha256,
    validate_trace,
)


BASELINE_PLAN_SCHEMA = "archvteams.nebius.ai/catalog-switch-k8s-baseline-plan/v2"
LEASE_SCHEMA = "catalog-switch-kubernetes-resource-lease/v2"
AUTHORIZED_PROJECTS = {
    "project-e00z6b02t8ddk96c49": "eu-north1",
    "project-u00tds8vpr00jaxa76s22d": "us-central1",
    "project-i00xz31gpr00xp9jhp982v": "me-west1",
}
VARIANTS = {
    "per_run_service": frozenset(),
    "precreated_service": frozenset({"service"}),
}
STRATEGIES = {"conventional", "snapshot", "none"}
ELIGIBILITY = {"eligible", "not_applicable"}
DNS_LABEL = re.compile(r"[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}")
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
THREAT_SOURCE_REVIEWED_COMMIT = "9cfbc1b1311a1f784a407889b215aaec5200fe0e"
THREAT_INTEGRATED_COMMIT = "9b548153385b50d2ad05076a0322840b77bb8027"
INVENTORY_REVIEWED_COMMIT = "9abd49204e7dbfb9be17ebf6c3f213227a88e5ca"
METRIC_SOURCE_REVIEWED_COMMIT = "ba49c9e20f194e0f419d4209608904cc9335219d"
METRIC_INTEGRATED_COMMIT = "138c52fe3d3371b2d84bb3d0b2e770601ebc5609"
RUNTIME_ROOT = Path(__file__).resolve().parents[2]
FROZEN_METRIC_FILES = frozenset(
    {
        "performance/request_slo/README.md",
        "performance/request_slo/cli.py",
        "performance/request_slo/event.schema.json",
        "performance/request_slo/harness.py",
        "performance/request_slo/trace.schema.json",
    }
)
THREAT_MODEL_PATH = RUNTIME_ROOT / "catalog-switch/security-reliability/threat_model.json"
THREAT_MODEL_SHA256 = "a9bfccaf2425b75beb40ed6265736aa1d97b3a26327ac37db3a9b92877bbb765"
THREAT_MARKDOWN_PATH = RUNTIME_ROOT / "catalog-switch/security-reliability/THREAT_MODEL.md"
THREAT_MARKDOWN_SHA256 = "c0e7260b0b37ea1b57a6d3816d939fa6e947f29fa95d45ef3ec956f59cc94819"
THREAT_VALIDATOR_PATH = RUNTIME_ROOT / "catalog-switch/security-reliability/validate_threat_model.py"
THREAT_VALIDATOR_SHA256 = "81e4db3a39ae85fcc37fcf2da2146c1a0e24f3997bd1853741051fdbaaa9ceb4"
EXECUTABLE_VALIDATOR_ADAPTERS = {
    "proteinmpnn": "proteinmpnn-v1",
    "boltz2": "boltz2-v1",
    "openfold2": "openfold2-v1",
}
RUNTIME_SOURCES_SCHEMA = "archvteams.nebius.ai/k8s-runtime-sources/v1"


class BaselineError(ValueError):
    """A benchmark plan cannot be safely admitted."""


def _expect_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BaselineError(f"{label} must be an object")
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing or extra:
        raise BaselineError(f"{label} keys differ; missing={missing}, extra={extra}")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or IDENTIFIER.fullmatch(value) is None:
        raise BaselineError(f"{label} is not a canonical identifier")
    return value


def _dns_label(value: Any, label: str) -> str:
    if not isinstance(value, str) or DNS_LABEL.fullmatch(value) is None:
        raise BaselineError(f"{label} is not a Kubernetes DNS label")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise BaselineError(f"{label} is not a lowercase SHA-256")
    return value


def _utc(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z") or "T" not in value:
        raise BaselineError(f"{label} must be an explicit UTC timestamp")
    return value


def _parse_utc(value: Any, label: str) -> datetime:
    value = _utc(value, label)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise BaselineError(f"{label} is not a valid UTC timestamp") from exc
    if parsed.tzinfo != UTC:
        raise BaselineError(f"{label} must use UTC")
    return parsed


def _positive(value: Any, label: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BaselineError(f"{label} must be numeric")
    if value < 0 or (not allow_zero and value == 0):
        raise BaselineError(f"{label} must be {'nonnegative' if allow_zero else 'positive'}")
    return float(value)


def _regular_file(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise BaselineError(f"{label} must be absolute")
    if path.is_symlink() or not path.is_file():
        raise BaselineError(f"{label} must be an existing regular non-symlink file")
    return path


def _load_json(path: Path, label: str) -> Any:
    _regular_file(path, label)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineError(f"cannot load {label}: {type(exc).__name__}") from exc


def _load_pinned_json(
    path: Path, expected_sha256: str, label: str
) -> tuple[Any, str]:
    """Read, hash, and parse one regular file through the same descriptor."""

    if not path.is_absolute():
        raise BaselineError(f"{label} must be absolute")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise BaselineError(f"{label} must be a regular file")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                raw = stream.read()
        finally:
            os.close(descriptor)
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise BaselineError(f"{label} differs from its immutable plan hash")
        text = raw.decode("utf-8")
        value = _json_loads(text, label)
        if text != canonical_json(value) + "\n":
            raise BaselineError(
                f"{label} is not canonical JSON with one terminal newline"
            )
        return value, text
    except BaselineError:
        raise
    except HarnessError as exc:
        raise BaselineError(f"{label} is not duplicate-free JSON: {exc}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineError(f"cannot load {label}: {type(exc).__name__}") from exc


def admitted_document(plan: dict[str, Any], name: str) -> dict[str, Any]:
    """Return a copy of the exact source bytes retained during admission."""

    if name not in {"trace", "lease"}:
        raise BaselineError("admitted document name is invalid")
    sources = plan.get("_admitted_sources")
    if not isinstance(sources, dict) or set(sources) != {"trace", "lease"}:
        raise BaselineError("plan lacks exact admitted trace/lease sources")
    source = sources.get(name)
    expected = (
        plan.get("trace_sha256")
        if name == "trace"
        else plan.get("resource_lease", {}).get("sha256")
    )
    if (
        not isinstance(source, str)
        or not isinstance(expected, str)
        or hashlib.sha256(source.encode("utf-8")).hexdigest() != expected
    ):
        raise BaselineError(f"admitted {name} bytes differ from the pinned hash")
    try:
        value = _json_loads(source, f"admitted {name}")
    except HarnessError as exc:
        raise BaselineError(f"admitted {name} bytes are not duplicate-free JSON") from exc
    if source != canonical_json(value) + "\n":
        raise BaselineError(f"admitted {name} bytes are not canonical JSON")
    if not isinstance(value, dict):
        raise BaselineError(f"admitted {name} must be an object")
    return value


def _same_path(left: Path, right: Path) -> bool:
    return os.path.samefile(left, right) if left.exists() and right.exists() else left == right


def _load_pinned_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BaselineError(f"cannot import pinned validator {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _resolve(plan_path: Path, value: Any, label: str, *, live: bool) -> Path:
    if not isinstance(value, str) or not value:
        raise BaselineError(f"{label} must be a nonempty path")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = (plan_path.parent / candidate).resolve()
    if live:
        _regular_file(candidate, label)
    elif candidate.exists() and (candidate.is_symlink() or not candidate.is_file()):
        raise BaselineError(f"{label} cannot be a symlink or non-file")
    return candidate


def _validate_security(
    plan: dict[str, Any], plan_path: Path, *, require_live: bool
) -> dict[str, Path]:
    security = _expect_keys(
        plan["security"],
        {"threat_model", "credentials", "workload_service_account", "support_images", "audit"},
        "security",
    )
    _dns_label(security["workload_service_account"], "security.workload_service_account")
    threat = _expect_keys(
        security["threat_model"],
        {
            "path", "sha256", "markdown_path", "markdown_sha256", "validator_path",
            "validator_sha256", "source_reviewed_commit", "integrated_commit",
        },
        "security.threat_model",
    )
    threat_path = _resolve(plan_path, threat["path"], "security.threat_model.path", live=True)
    markdown_path = _resolve(
        plan_path, threat["markdown_path"], "security.threat_model.markdown_path", live=True
    )
    validator_path = _resolve(
        plan_path, threat["validator_path"], "security.threat_model.validator_path", live=True
    )
    if (
        not _same_path(threat_path, THREAT_MODEL_PATH)
        or not _same_path(markdown_path, THREAT_MARKDOWN_PATH)
        or not _same_path(validator_path, THREAT_VALIDATOR_PATH)
        or threat["sha256"] != THREAT_MODEL_SHA256
        or threat["markdown_sha256"] != THREAT_MARKDOWN_SHA256
        or threat["validator_sha256"] != THREAT_VALIDATOR_SHA256
        or file_sha256(threat_path) != THREAT_MODEL_SHA256
        or file_sha256(markdown_path) != THREAT_MARKDOWN_SHA256
        or file_sha256(validator_path) != THREAT_VALIDATOR_SHA256
    ):
        raise BaselineError("threat-model document/markdown/validator differs from reviewed sources")
    threat_value = _load_json(threat_path, "security threat model")
    try:
        validator = _load_pinned_module(
            validator_path, "catalog_switch_k8s_pinned_threat_validator"
        )
        errors = validator.validate(threat_value, markdown_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BaselineError(
            f"reviewed threat-model validator could not run: {type(exc).__name__}"
        ) from exc
    if errors:
        raise BaselineError(f"reviewed threat-model validator rejected the artifact: {errors[0]}")
    if (
        threat["source_reviewed_commit"] != THREAT_SOURCE_REVIEWED_COMMIT
        or threat["integrated_commit"] != THREAT_INTEGRATED_COMMIT
    ):
        raise BaselineError("threat-model commits differ from the integrated reviewed prerequisite")
    audit = _expect_keys(
        security["audit"], {"schema", "chain_id", "genesis_sha256"}, "security.audit"
    )
    if audit["schema"] != "archvteams.nebius.ai/hash-chained-audit/v1":
        raise BaselineError("audit schema is not the reviewed append-only contract")
    _identifier(audit["chain_id"], "security.audit.chain_id")
    _digest(audit["genesis_sha256"], "security.audit.genesis_sha256")

    credentials = _expect_keys(
        security["credentials"],
        {
            "owner_task_id", "secret_name", "secret_uid", "registry", "scope_sha256",
            "scope_manifest_path", "scope_manifest_sha256", "receipt_path", "receipt_sha256",
            "expires_at_utc", "revoke_by_utc",
        },
        "security.credentials",
    )
    if credentials["owner_task_id"] != plan["task_id"]:
        raise BaselineError("registry credential is not owned by this task")
    _dns_label(credentials["secret_name"], "security.credentials.secret_name")
    _identifier(credentials["secret_uid"], "security.credentials.secret_uid")
    _identifier(credentials["registry"], "security.credentials.registry")
    _digest(credentials["scope_sha256"], "security.credentials.scope_sha256")
    scope_path = _resolve(
        plan_path, credentials["scope_manifest_path"],
        "security.credentials.scope_manifest_path", live=True,
    )
    if file_sha256(scope_path) != _digest(
        credentials["scope_manifest_sha256"],
        "security.credentials.scope_manifest_sha256",
    ):
        raise BaselineError("registry scope manifest differs from its source-bound digest")
    images = _expect_keys(
        security["support_images"],
        {
            "sentinel_digest", "readiness_gate_digest", "source_receipt_path",
            "source_receipt_sha256",
        },
        "security.support_images",
    )
    for key in ("sentinel_digest", "readiness_gate_digest"):
        value = images[key]
        if not isinstance(value, str) or IMAGE_DIGEST_RE.fullmatch(value) is None:
            raise BaselineError(f"security.support_images.{key} is not digest-pinned")
        if not value.startswith("nvcr.io/"):
            raise BaselineError(f"security.support_images.{key} is outside the scoped NGC registry")
    support_receipt_path = _resolve(
        plan_path, images["source_receipt_path"],
        "security.support_images.source_receipt_path", live=True,
    )
    if file_sha256(support_receipt_path) != _digest(
        images["source_receipt_sha256"],
        "security.support_images.source_receipt_sha256",
    ):
        raise BaselineError("support-image source receipt differs from its digest")
    support_receipt = _expect_keys(
        _load_json(support_receipt_path, "support-image source receipt"),
        {
            "schema", "status", "owner_task_id", "build_source_commit",
            "receipt_commit", "build_source_path", "build_source_sha256", "images",
        },
        "support-image source receipt",
    )
    if support_receipt != {
        "schema": "archvteams.nebius.ai/k8s-support-image-source-receipt/v1",
        "status": "REVIEWED",
        "owner_task_id": plan["task_id"],
        "build_source_commit": support_receipt["build_source_commit"],
        "receipt_commit": support_receipt["receipt_commit"],
        "build_source_path": support_receipt["build_source_path"],
        "build_source_sha256": support_receipt["build_source_sha256"],
        "images": {
            "readiness_gate": images["readiness_gate_digest"],
            "sentinel": images["sentinel_digest"],
        },
    }:
        raise BaselineError("support-image source receipt is not bound to the admitted images")
    for key in ("build_source_commit", "receipt_commit"):
        if not isinstance(support_receipt[key], str) or COMMIT.fullmatch(support_receipt[key]) is None:
            raise BaselineError(f"support-image {key} is not an exact Git commit")
    _digest(support_receipt["build_source_sha256"], "support-image build_source_sha256")
    build_source_path = _resolve(
        plan_path, support_receipt["build_source_path"],
        "support-image build source path", live=True,
    )
    if file_sha256(build_source_path) != support_receipt["build_source_sha256"]:
        raise BaselineError("support-image build source differs from its receipt digest")

    scoped_image_digests = sorted(
        {
            *(item["image_digest"] for item in plan["models"]),
            images["sentinel_digest"],
            images["readiness_gate_digest"],
        }
    )
    expected_scope_manifest = {
        "schema": "archvteams.nebius.ai/registry-scope-manifest/v1",
        "owner_task_id": plan["task_id"],
        "registry": "nvcr.io",
        "secret_uid": credentials["secret_uid"],
        "namespace": plan["kubernetes"]["namespace"],
        "repositories": sorted({item.split("@", 1)[0] for item in scoped_image_digests}),
        "image_digests": scoped_image_digests,
    }
    scope_manifest = _load_json(scope_path, "registry scope manifest")
    expected_scope = canonical_sha256(expected_scope_manifest)
    if (
        scope_manifest != expected_scope_manifest
        or credentials["registry"] != "nvcr.io"
        or credentials["scope_sha256"] != expected_scope
        or any(not item.startswith("nvcr.io/") for item in expected_scope_manifest["image_digests"])
    ):
        raise BaselineError("registry credential scope is not bound to exact admitted NGC images")
    _utc(credentials["expires_at_utc"], "security.credentials.expires_at_utc")
    _utc(credentials["revoke_by_utc"], "security.credentials.revoke_by_utc")
    receipt_path = _resolve(
        plan_path, credentials["receipt_path"], "security.credentials.receipt_path", live=True
    )
    if file_sha256(receipt_path) != _digest(
        credentials["receipt_sha256"], "security.credentials.receipt_sha256"
    ):
        raise BaselineError("credential receipt differs from its source-bound digest")
    receipt = _expect_keys(
        _load_json(receipt_path, "registry credential receipt"),
        {
            "schema", "status", "owner_task_id", "secret_name", "secret_uid", "registry",
            "scope_sha256", "scope_manifest_sha256", "issued_at_utc", "expires_at_utc", "revoke_by_utc",
            "revocation_scope", "source", "audit_chain_id",
        },
        "registry credential receipt",
    )
    expected_receipt = {
        "schema": "archvteams.nebius.ai/k8s-registry-credential-receipt/v1",
        "status": "ACTIVE",
        **{
            key: credentials[key]
            for key in (
                "owner_task_id", "secret_name", "secret_uid", "registry", "scope_sha256",
                "scope_manifest_sha256", "expires_at_utc", "revoke_by_utc",
            )
        },
        "issued_at_utc": receipt["issued_at_utc"],
        "revocation_scope": "exact-secret-uid-only",
        "source": "catalog-switch-resource-broker-v2",
        "audit_chain_id": audit["chain_id"],
    }
    if receipt != expected_receipt:
        raise BaselineError("registry credential receipt identity/scope/provenance differs from plan")
    issued = _parse_utc(receipt["issued_at_utc"], "credential issued_at_utc")
    expires = _parse_utc(receipt["expires_at_utc"], "credential expires_at_utc")
    revoke = _parse_utc(receipt["revoke_by_utc"], "credential revoke_by_utc")
    cleanup_deadline = _parse_utc(plan["cleanup"]["deadline_utc"], "cleanup.deadline_utc")
    if not issued < expires or expires < cleanup_deadline or revoke < expires:
        raise BaselineError("registry credential lifecycle does not cover cleanup/revocation")
    if require_live:
        now = datetime.now(UTC)
        if issued > now:
            raise BaselineError("registry credential was issued after live admission time")
        if now >= expires or now >= cleanup_deadline:
            raise BaselineError("registry credential or cleanup deadline has expired at live admission")

    return {
        "threat_model": threat_path, "credential_receipt": receipt_path,
        "credential_scope_manifest": scope_path,
        "support_image_receipt": support_receipt_path,
    }


def _validate_live_tracked_source(path: Path, label: str) -> None:
    """Require a runtime asset to be a tracked file in the exact live revision."""

    repository = RUNTIME_ROOT.parents[1]
    try:
        relative = path.resolve().relative_to(repository.resolve())
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", str(relative)],
            cwd=repository, text=True, capture_output=True, check=True, timeout=15,
        )
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise BaselineError(f"{label} is not tracked by the exact live code revision") from exc


def _validate_live_source_blob(
    path: Path, source_commit: str, code_revision: str, label: str
) -> None:
    """Prove a reviewed source blob exists unchanged in an ancestor commit."""

    repository = RUNTIME_ROOT.parents[1]
    try:
        relative = path.resolve().relative_to(repository.resolve())
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", source_commit, code_revision],
            cwd=repository, text=True, capture_output=True, check=True, timeout=15,
        )
        source = subprocess.run(
            ["git", "show", f"{source_commit}:{relative}"],
            cwd=repository, capture_output=True, check=True, timeout=15,
        ).stdout
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise BaselineError(f"{label} is not reproducible from an ancestor source commit") from exc
    if hashlib.sha256(source).hexdigest() != file_sha256(path):
        raise BaselineError(f"{label} differs from its reviewed ancestor Git blob")


def _runtime_model_source(model: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical, executable source identity for one admitted model."""

    strategies: dict[str, Any] = {}
    for strategy in ("conventional", "snapshot"):
        template = model["target_templates"][strategy]
        if template is None:
            strategies[strategy] = None
            continue
        init_names = ["artifact-gate", "cache-gate", "storage-gate"]
        if strategy == "snapshot":
            init_names.append("snapshot-restore-gate")
        strategies[strategy] = {
            "path": template["path"],
            "sha256": template["sha256"],
            "container_names": [model["container_name"]],
            "init_container_names": sorted(init_names),
        }
    oracle = model["semantic_oracle"]
    return {
        "model_id": model["model_id"],
        "model_version": model["model_version"],
        "validator": {
            "validator_id": oracle["validator_id"],
            "adapter": model["validator_adapter"],
            "path": oracle["validator_path"],
            "sha256": oracle["validator_sha256"],
        },
        "target_templates": strategies,
    }


def _validate_runtime_sources(
    plan: dict[str, Any], plan_path: Path, models: list[dict[str, Any]], *, require_live: bool
) -> Path:
    """Bind every executable validator/template/support image into the broker request."""

    ref = _expect_keys(plan["runtime_sources"], {"path", "sha256"}, "runtime_sources")
    path = _resolve(plan_path, ref["path"], "runtime_sources.path", live=True)
    if file_sha256(path) != _digest(ref["sha256"], "runtime_sources.sha256"):
        raise BaselineError("runtime source manifest differs from its immutable digest")
    value = _load_json(path, "runtime source manifest")
    reviewed_commit = value.get("reviewed_commit") if isinstance(value, dict) else None
    if not isinstance(reviewed_commit, str) or COMMIT.fullmatch(reviewed_commit) is None:
        raise BaselineError("runtime source manifest lacks an exact reviewed Git commit")
    expected = {
        "schema": RUNTIME_SOURCES_SCHEMA,
        "task_id": plan["task_id"],
        "reviewed_commit": reviewed_commit,
        "support_images": {
            key: plan["security"]["support_images"][key]
            for key in (
                "sentinel_digest", "readiness_gate_digest", "source_receipt_path",
                "source_receipt_sha256",
            )
        },
        "models": sorted(
            (_runtime_model_source(item) for item in plan["models"]),
            key=lambda item: (item["model_id"], item["model_version"]),
        ),
    }
    if value != expected:
        raise BaselineError(
            "runtime source manifest differs from exact validators/templates/support images"
        )
    if require_live:
        _validate_live_tracked_source(path, "runtime source manifest")
        _validate_live_source_blob(
            path, reviewed_commit, plan["code_revision"], "runtime source manifest"
        )
        support_receipt_path = _resolve(
            plan_path, plan["security"]["support_images"]["source_receipt_path"],
            "support-image source receipt", live=True,
        )
        _validate_live_tracked_source(support_receipt_path, "support-image source receipt")
        support_receipt = _load_json(support_receipt_path, "support-image source receipt")
        _validate_live_source_blob(
            support_receipt_path, support_receipt["receipt_commit"], plan["code_revision"],
            "support-image source receipt",
        )
        support_build_source_path = _resolve(
            plan_path, support_receipt["build_source_path"],
            "support-image build source", live=True,
        )
        _validate_live_tracked_source(
            support_build_source_path, "support-image build source"
        )
        _validate_live_source_blob(
            support_build_source_path, support_receipt["build_source_commit"],
            plan["code_revision"], "support-image build source",
        )
        repository = RUNTIME_ROOT.parents[1]
        try:
            subprocess.run(
                [
                    "git", "merge-base", "--is-ancestor",
                    support_receipt["build_source_commit"], support_receipt["receipt_commit"],
                ],
                cwd=repository, text=True, capture_output=True, check=True, timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BaselineError(
                "support-image build source is not an ancestor of its reviewed receipt"
            ) from exc
        for index, model in enumerate(models):
            _validate_live_tracked_source(
                Path(model["_paths"]["validator_path"]), f"models[{index}] validator"
            )
            for strategy in ("conventional", "snapshot"):
                template = model["_paths"][f"{strategy}_template"]
                if template is not None:
                    _validate_live_tracked_source(
                        Path(template), f"models[{index}] {strategy} template"
                    )
    return path


def _validate_gpu_profiles(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = plan["gpu_profiles"]
    if not isinstance(values, dict) or not values:
        raise BaselineError("gpu_profiles must contain at least one compatible profile")
    profiles: dict[str, dict[str, Any]] = {}
    for name, raw in values.items():
        _identifier(name, f"gpu_profiles.{name}")
        profile = _expect_keys(
            raw, {"product", "platform", "preset", "gpu_count"}, f"gpu_profiles.{name}"
        )
        for key in ("product", "platform", "preset"):
            _identifier(profile[key], f"gpu_profiles.{name}.{key}")
        if not any(family in profile["product"].upper() for family in ("H100", "H200")):
            raise BaselineError(f"gpu_profiles.{name} is not an admitted H100/H200 profile")
        if not isinstance(profile["gpu_count"], int) or profile["gpu_count"] <= 0:
            raise BaselineError(f"gpu_profiles.{name}.gpu_count must be positive")
        profiles[name] = profile
    return profiles


def _validate_metric_contract(plan: dict[str, Any], plan_path: Path) -> Path:
    metric = _expect_keys(
        plan["metric_contract"],
        {"path", "sha256", "source_reviewed_commit", "integrated_commit"},
        "metric_contract",
    )
    path = _resolve(plan_path, metric["path"], "metric_contract.path", live=True)
    if file_sha256(path) != _digest(metric["sha256"], "metric_contract.sha256"):
        raise BaselineError("metric contract file differs from its source-bound digest")
    if (
        metric["source_reviewed_commit"] != METRIC_SOURCE_REVIEWED_COMMIT
        or metric["integrated_commit"] != METRIC_INTEGRATED_COMMIT
    ):
        raise BaselineError("metric contract commits differ from the integrated reviewed prerequisite")
    value = _expect_keys(
        _load_json(path, "metric contract"),
        {"schema", "source_reviewed_commit", "integrated_commit", "files"},
        "metric contract artifact",
    )
    if (
        value["schema"] != "archvteams.nebius.ai/request-slo-contract-freeze/v1"
        or value["source_reviewed_commit"] != METRIC_SOURCE_REVIEWED_COMMIT
        or value["integrated_commit"] != METRIC_INTEGRATED_COMMIT
        or not isinstance(value["files"], dict)
        or not value["files"]
    ):
        raise BaselineError("metric contract artifact is not the reviewed frozen contract")
    if set(value["files"]) != FROZEN_METRIC_FILES:
        raise BaselineError("metric contract file set differs from the reviewed runtime surface")
    for name, digest in value["files"].items():
        if not isinstance(name, str) or not name.startswith("performance/request_slo/"):
            raise BaselineError("metric contract contains a foreign file identity")
        source = (RUNTIME_ROOT / name).resolve()
        if not source.is_relative_to(RUNTIME_ROOT) or source.is_symlink() or not source.is_file():
            raise BaselineError(f"metric contract runtime file is unsafe or absent: {name}")
        if file_sha256(source) != _digest(digest, f"metric contract file {name}"):
            raise BaselineError(f"metric contract runtime file differs from freeze: {name}")
    return path


def _validate_live_source_revision(code_revision: str) -> None:
    """Bind live admission to the exact clean checked-out executable revision."""

    repository = RUNTIME_ROOT.parents[1]
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repository, text=True,
            capture_output=True, check=True, timeout=15,
        ).stdout.strip()
        status = subprocess.run(
            [
                "git", "status", "--porcelain=v1", "--untracked-files=all", "--",
                "nim-fast-start/faststart-v2/performance/k8s_baseline",
                "nim-fast-start/faststart-v2/performance/request_slo",
                "nim-fast-start/faststart-v2/catalog-switch/security-reliability",
            ],
            cwd=repository, text=True, capture_output=True, check=True, timeout=15,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise BaselineError("cannot prove the live executable Git revision") from exc
    if head != code_revision or status:
        raise BaselineError(
            "live executable source is not the exact clean code_revision bound by the plan"
        )


def _validate_model(
    value: Any, index: int, plan_path: Path, profiles: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    label = f"models[{index}]"
    admitted = _expect_keys(
        value,
        {
            "model_id", "model_version", "version_label", "artifact_id", "artifact_version",
            "artifact_sha256", "image_digest", "gpu_profile", "strategy_eligibility",
            "target_templates", "semantic_oracle", "input", "endpoint_path", "ready_path",
            "request_file", "request_sha256", "container_name", "artifact_bytes", "image_bytes",
            "validator_adapter", "checkpoint",
        },
        label,
    )
    # Resolved private paths and derived validator aliases must never mutate
    # the canonical plan whose digest is bound into the accepted event.
    model = json.loads(canonical_json(admitted))
    _dns_label(model["model_id"], f"{label}.model_id")
    for key in ("model_version", "artifact_id", "artifact_version"):
        _identifier(model[key], f"{label}.{key}")
    _dns_label(model["version_label"], f"{label}.version_label")
    _digest(model["artifact_sha256"], f"{label}.artifact_sha256")
    if not isinstance(model["image_digest"], str) or IMAGE_DIGEST_RE.fullmatch(model["image_digest"]) is None:
        raise BaselineError(f"{label}.image_digest is not digest-pinned")
    if model["gpu_profile"] not in profiles:
        raise BaselineError(f"{label}.gpu_profile is not declared")
    expected_adapter = EXECUTABLE_VALIDATOR_ADAPTERS.get(model["model_id"])
    if model["validator_adapter"] != expected_adapter:
        raise BaselineError(
            f"{label} has no executable validator adapter admitted for {model['model_id']}"
        )
    _dns_label(model["container_name"], f"{label}.container_name")
    for key in ("endpoint_path", "ready_path"):
        if not isinstance(model[key], str) or not model[key].startswith("/") or "?" in model[key]:
            raise BaselineError(f"{label}.{key} must be an absolute HTTP path")
    for key in ("artifact_bytes", "image_bytes"):
        if not isinstance(model[key], int) or model[key] < 0:
            raise BaselineError(f"{label}.{key} must be nonnegative")

    eligibility = _expect_keys(
        model["strategy_eligibility"], {"conventional", "snapshot"},
        f"{label}.strategy_eligibility",
    )
    templates = _expect_keys(
        model["target_templates"], {"conventional", "snapshot"}, f"{label}.target_templates"
    )
    paths: dict[str, str | None] = {}
    for strategy in ("conventional", "snapshot"):
        proof = _expect_keys(
            eligibility[strategy], {"state", "evidence_path", "evidence_sha256"},
            f"{label}.strategy_eligibility.{strategy}",
        )
        if proof["state"] not in ELIGIBILITY:
            raise BaselineError(f"{label} has an invalid {strategy} eligibility state")
        evidence_path = _resolve(
            plan_path,
            proof["evidence_path"],
            f"{label}.strategy_eligibility.{strategy}.evidence_path",
            live=True,
        )
        if file_sha256(evidence_path) != _digest(
            proof["evidence_sha256"],
            f"{label}.strategy_eligibility.{strategy}.evidence_sha256",
        ):
            raise BaselineError(f"{label} {strategy} eligibility evidence digest drifted")
        evidence_value = _expect_keys(
            _load_json(evidence_path, f"{label} {strategy} eligibility evidence"),
            {
                "schema", "model_id", "model_version", "strategy", "state",
                "gpu_profile", "source_reviewed_commit",
            },
            f"{label} {strategy} eligibility evidence",
        )
        if evidence_value != {
            "schema": "archvteams.nebius.ai/k8s-strategy-eligibility/v1",
            "model_id": model["model_id"],
            "model_version": model["model_version"],
            "strategy": strategy,
            "state": proof["state"],
            "gpu_profile": model["gpu_profile"],
            "source_reviewed_commit": INVENTORY_REVIEWED_COMMIT,
        }:
            raise BaselineError(f"{label} {strategy} eligibility evidence is not source-bound")
        paths[f"{strategy}_eligibility_evidence"] = str(evidence_path)
        template = templates[strategy]
        if proof["state"] == "eligible":
            template_ref = _expect_keys(
                template, {"path", "sha256"}, f"{label}.target_templates.{strategy}"
            )
            path = _resolve(
                plan_path, template_ref["path"], f"{label}.target_templates.{strategy}.path", live=True
            )
            if file_sha256(path) != _digest(
                template_ref["sha256"], f"{label}.target_templates.{strategy}.sha256"
            ):
                raise BaselineError(f"{label} {strategy} template differs from its pinned digest")
            paths[f"{strategy}_template"] = str(path)
        elif template is not None:
            raise BaselineError(f"{label} {strategy} template must be null when not applicable")
        else:
            paths[f"{strategy}_template"] = None

    checkpoint = model["checkpoint"]
    if eligibility["snapshot"]["state"] == "eligible":
        checkpoint = _expect_keys(
            checkpoint,
            {"checkpoint_id", "checkpoint_sha256", "checkpoint_bytes"},
            f"{label}.checkpoint",
        )
        _identifier(checkpoint["checkpoint_id"], f"{label}.checkpoint.checkpoint_id")
        _digest(checkpoint["checkpoint_sha256"], f"{label}.checkpoint.checkpoint_sha256")
        if not isinstance(checkpoint["checkpoint_bytes"], int) or checkpoint["checkpoint_bytes"] <= 0:
            raise BaselineError(f"{label}.checkpoint.checkpoint_bytes must be positive")
    elif checkpoint is not None:
        raise BaselineError(f"{label}.checkpoint must be null when snapshot is not applicable")

    oracle = _expect_keys(
        model["semantic_oracle"], {"validator_id", "validator_path", "validator_sha256"},
        f"{label}.semantic_oracle",
    )
    _identifier(oracle["validator_id"], f"{label}.semantic_oracle.validator_id")
    validator_path = _resolve(
        plan_path, oracle["validator_path"], f"{label}.semantic_oracle.validator_path", live=True
    )
    if file_sha256(validator_path) != _digest(
        oracle["validator_sha256"], f"{label}.semantic_oracle.validator_sha256"
    ):
        raise BaselineError(f"{label} semantic oracle digest differs from the pinned file")

    input_value = _expect_keys(
        model["input"], {"workload_id", "input_id", "payload_sha256", "input_bytes"},
        f"{label}.input",
    )
    for key in ("workload_id", "input_id"):
        _identifier(input_value[key], f"{label}.input.{key}")
    _digest(input_value["payload_sha256"], f"{label}.input.payload_sha256")
    if not isinstance(input_value["input_bytes"], int) or input_value["input_bytes"] <= 0:
        raise BaselineError(f"{label}.input.input_bytes must be positive")
    request_path = _resolve(plan_path, model["request_file"], f"{label}.request_file", live=True)
    request_sha = _digest(model["request_sha256"], f"{label}.request_sha256")
    if file_sha256(request_path) != request_sha:
        raise BaselineError(f"{label} request digest differs from the pinned file")
    if request_sha != input_value["payload_sha256"] or request_path.stat().st_size != input_value["input_bytes"]:
        raise BaselineError(f"{label} exact input identity differs from the request bundle")
    bundle = _load_json(request_path, f"{label} request bundle")
    if (
        not isinstance(bundle, dict) or set(bundle) != {"schema", "calls"}
        or bundle["schema"] != "archvteams.nebius.ai/two-semantic-inference-bundle/v1"
        or not isinstance(bundle["calls"], list) or len(bundle["calls"]) != 2
    ):
        raise BaselineError(f"{label} request bundle must contain exactly two semantic calls")
    call_ids: set[str] = set()
    for call_index, call in enumerate(bundle["calls"]):
        call_label = f"{label} request bundle call {call_index}"
        call = _expect_keys(
            call, {"input_id", "payload_path", "payload_sha256", "overrides"}, call_label
        )
        call_id = _identifier(call["input_id"], f"{call_label}.input_id")
        if call_id in call_ids:
            raise BaselineError(f"{label} request bundle call identities are duplicated")
        call_ids.add(call_id)
        if not isinstance(call["overrides"], dict):
            raise BaselineError(f"{call_label}.overrides must be an object")
        payload_path = Path(call["payload_path"])
        if not payload_path.is_absolute():
            payload_path = (request_path.parent / payload_path).resolve()
        _regular_file(payload_path, f"{call_label}.payload_path")
        if file_sha256(payload_path) != _digest(
            call["payload_sha256"], f"{call_label}.payload_sha256"
        ):
            raise BaselineError(f"{call_label} payload differs from its exact digest")
        if not isinstance(_load_json(payload_path, f"{call_label} payload"), dict):
            raise BaselineError(f"{call_label} semantic payload must be an object")
    model["_paths"] = {
        **paths, "validator_path": str(validator_path), "request_file": str(request_path)
    }
    model["validator_id"] = oracle["validator_id"]
    model["validator_sha256"] = oracle["validator_sha256"]
    return model


def _validate_trace_binding(
    trace: dict[str, Any], models: list[dict[str, Any]], plan: dict[str, Any]
) -> None:
    by_key = {(item["model_id"], item["model_version"]): item for item in models}
    counts: dict[tuple[str, ...], int] = {}
    for request in trace["requests"]:
        key = (request["target"]["model_id"], request["target"]["model_version"])
        model = by_key.get(key)
        if model is None:
            raise BaselineError("trace selects a model absent from the plan")
        exact_target = {
            name: model[name]
            for name in ("model_id", "model_version", "artifact_id", "artifact_version", "artifact_sha256")
        }
        if request["target"] != exact_target:
            raise BaselineError("trace artifact identity differs from the executable plan")
        if request["input"] != model["input"]:
            raise BaselineError("trace input identity differs from the executable request bundle")
        if plan["campaign_arm"] == "B_new_preemptible_node":
            cache = request["precondition"]["cache"]
            if (
                request["scenario"] not in {"a_to_b_remote", "capacity_miss"}
                or request["precondition"]["current_node_occupant"] is not None
                or cache["image"] not in {"remote_required", "unavailable", "not_applicable"}
                or cache["artifact"] not in {"remote_miss", "unavailable", "not_applicable"}
                or cache["checkpoint"] not in {"missing", "not_applicable"}
                or cache["storage"] not in {"localization_required", "unavailable", "not_applicable"}
            ):
                raise BaselineError(
                    "new-node arm trace smuggles node/model/cache work before durable external T0"
                )
        strategy = plan["scenario_strategies"][request["scenario"]]
        if strategy != "none" and model["strategy_eligibility"][strategy]["state"] != "eligible":
            raise BaselineError("trace selects a strategy not eligible for its target model")
        cache_key = hashlib.sha256(canonical_json(request["precondition"]["cache"]).encode()).hexdigest()
        stratum = (
            request["scenario"], model["model_id"], model["model_version"], strategy,
            plan["variant"], cache_key, model["gpu_profile"],
        )
        counts[stratum] = counts.get(stratum, 0) + 1
    short = {
        "|".join(key): count
        for key, count in counts.items()
        if key[0] in plan["promoted_scenarios"] and count < plan["minimum_repetitions"]
    }
    if short:
        raise BaselineError(f"promoted stratified trace cohorts are undersized: {short}")
    planned_models = {(item["model_id"], item["model_version"]) for item in models}
    for scenario in plan["promoted_scenarios"]:
        observed_models = {
            (item["target"]["model_id"], item["target"]["model_version"])
            for item in trace["requests"]
            if item["scenario"] == scenario
        }
        if observed_models != planned_models:
            raise BaselineError(
                f"promoted scenario {scenario} does not cover every planned target model"
            )


def _validate_resource_graph(
    lease: dict[str, Any], plan: dict[str, Any], lease_ref: dict[str, Any], plan_path: Path
) -> None:
    resources = lease["resources"]
    if not isinstance(resources, list) or not resources:
        raise BaselineError("broker lease has no task-owned resource graph")
    ids: set[str] = set()
    for index, raw in enumerate(resources):
        item = _expect_keys(
            raw,
            {"kind", "id", "project_id", "region", "prefix", "task_id", "task_owned", "preexisting"},
            f"resource lease resources[{index}]",
        )
        _identifier(item["kind"], f"resource lease resources[{index}].kind")
        _identifier(item["id"], f"resource lease resources[{index}].id")
        if item["id"] in ids:
            raise BaselineError("broker resource graph contains duplicate IDs")
        ids.add(item["id"])
        if (
            item["project_id"] != plan["project_id"] or item["region"] != plan["region"]
            or item["prefix"] != lease_ref["prefix"] or item["task_id"] != plan["task_id"]
            or item["task_owned"] is not True or item["preexisting"] is not False
        ):
            raise BaselineError("broker resource graph contains a foreign or reused resource")
    kinds = {item["kind"] for item in resources}
    required_kinds = {"cluster", "network", "subnet", "service_account", "namespace"}
    if plan["campaign_arm"] == "A_prepared_node":
        required_kinds |= {"node_group", "node"}
    elif kinds & {"node_group", "node", "gpu", "pod", "model", "artifact", "checkpoint"}:
        raise BaselineError("new-node arm resource graph contains forbidden pre-T0 GPU/model work")
    if not required_kinds <= kinds:
        raise BaselineError("broker resource graph omits required task-owned dependencies")
    if kinds != required_kinds or any(
        sum(item["kind"] == kind for item in resources) != 1 for kind in required_kinds
    ):
        raise BaselineError("broker resource graph has hidden or duplicate capacity")
    by_kind = {item["kind"]: item["id"] for item in resources}
    kube = plan["kubernetes"]
    if (
        by_kind.get("namespace") != kube["namespace_resource_id"]
        or by_kind.get("service_account") != kube["service_account_resource_id"]
    ):
        raise BaselineError("broker namespace/service-account identities differ from the plan")
    if plan["campaign_arm"] == "A_prepared_node" and by_kind.get("node_group") != kube["broker_node_group_id"]:
        raise BaselineError("broker node-group identity differs from the plan")
    required = {lease["cluster_id"], *lease["node_group_ids"], *lease["node_ids"]}
    if not required <= ids:
        raise BaselineError("broker cluster/node identities are absent from its resource graph")
    if (
        by_kind["cluster"] != lease["cluster_id"]
        or ([by_kind["node_group"]] if "node_group" in by_kind else []) != lease["node_group_ids"]
        or ([by_kind["node"]] if "node" in by_kind else []) != lease["node_ids"]
    ):
        raise BaselineError("broker graph cluster/node identities differ from top-level lease IDs")
    proof = _expect_keys(
        lease["isolation_proof"],
        {
            "fresh", "task_owned", "preemptible", "gpu_product", "gpu_count", "cluster_id",
            "node_group_ids", "node_ids", "node_boot_id", "gpu_inventory_sha256",
            "resource_graph_sha256", "evidence_path", "evidence_sha256",
        },
        "resource lease isolation_proof",
    )
    if (
        proof["fresh"] is not True or proof["task_owned"] is not True
        or proof["preemptible"] is not True or proof["gpu_product"] != lease["gpu_product"]
        or proof["gpu_count"] != lease["gpu_count"] or proof["cluster_id"] != lease["cluster_id"]
        or proof["node_group_ids"] != lease["node_group_ids"] or proof["node_ids"] != lease["node_ids"]
        or proof["node_boot_id"] != lease["node_boot_id"]
        or proof["gpu_inventory_sha256"] != canonical_sha256(lease["gpu_inventory"])
        or proof["resource_graph_sha256"] != canonical_sha256(resources)
    ):
        raise BaselineError("broker isolation proof is not bound to the exact resource graph")
    evidence_path = _resolve(
        plan_path,
        proof["evidence_path"],
        "resource lease isolation evidence_path",
        live=True,
    )
    if file_sha256(evidence_path) != _digest(
        proof["evidence_sha256"], "resource lease isolation evidence"
    ):
        raise BaselineError("broker isolation evidence differs from its digest")
    expected_evidence = {
        key: proof[key]
        for key in (
            "fresh", "task_owned", "preemptible", "gpu_product", "gpu_count", "cluster_id",
            "node_group_ids", "node_ids", "node_boot_id", "gpu_inventory_sha256",
            "resource_graph_sha256",
        )
    }
    if _load_json(evidence_path, "broker isolation evidence") != expected_evidence:
        raise BaselineError("broker isolation evidence content differs from the lease")


def _validate_lease(
    plan: dict[str, Any], plan_path: Path, trace: dict[str, Any], models: list[dict[str, Any]],
    profiles: dict[str, dict[str, Any]], *, require_live: bool
) -> tuple[dict[str, Any] | None, Path, str | None]:
    lease_ref = _expect_keys(
        plan["resource_lease"],
        {"path", "sha256", "request_sha256", "lease_id", "prefix", "admitted_states"},
        "resource_lease",
    )
    _identifier(lease_ref["lease_id"], "resource_lease.lease_id")
    prefix = _dns_label(lease_ref["prefix"], "resource_lease.prefix")
    if not prefix.startswith("mlsp-csw-"):
        raise BaselineError("resource lease prefix is outside the frozen broker namespace")
    expected_states = (
        ["PLANNED", "ACTIVE"] if plan["campaign_arm"] == "A_prepared_node"
        else ["PLANNED", "SUPPORT_ACTIVE_NO_GPU_NODE_GROUP"]
    )
    if lease_ref["admitted_states"] != expected_states:
        raise BaselineError("resource lease states differ from the frozen arm transition")
    lease_path = _resolve(plan_path, lease_ref["path"], "resource_lease.path", live=require_live)
    if not lease_path.exists():
        return None, lease_path, None
    lease_value, lease_source = _load_pinned_json(
        lease_path,
        _digest(lease_ref["sha256"], "resource_lease.sha256"),
        "resource lease",
    )
    lease = _expect_keys(
        lease_value,
        {
            "schema_version", "lease_id", "request_sha256", "request", "prefix", "state",
            "project_id", "region", "cluster_id", "node_group_ids", "node_ids",
            "kubeconfig_path", "kubernetes_context", "api_server", "gpu_product", "gpu_count",
            "preemptible", "node_boot_id", "gpu_inventory", "resources", "isolation_proof", "initial_state_receipt",
            "resource_create_operations", "readiness_timestamps", "cost_estimate",
            "cleanup_plan", "audit_chain",
        },
        "resource lease",
    )
    if lease["schema_version"] != LEASE_SCHEMA:
        raise BaselineError("Kubernetes execution requires the versioned cluster/node-group broker contract")
    request = _expect_keys(
        lease["request"],
        {
            "lease_id", "prefix", "task_id", "campaign_arm", "project_id", "region",
            "code_revision", "expected_duration_hours", "ttl_hours", "hard_cost_cap_usd",
            "metric_contract_sha256", "trace_sha256", "model_input_sha256s", "cleanup_owner",
            "cleanup_deadline_utc", "cluster_version", "node_group_profile",
            "credential_receipt_sha256", "credential_scope_manifest_sha256",
            "threat_model_sha256", "runtime_sources_sha256",
        },
        "resource lease request",
    )
    if lease["request_sha256"] != canonical_sha256(request) or lease_ref["request_sha256"] != lease["request_sha256"]:
        raise BaselineError("broker request hash is not bound to the immutable request")
    expected_request = {
        "lease_id": lease_ref["lease_id"], "prefix": prefix, "task_id": plan["task_id"],
        "campaign_arm": plan["campaign_arm"], "project_id": plan["project_id"], "region": plan["region"],
        "code_revision": plan["code_revision"], "expected_duration_hours": plan["cost"]["expected_duration_hours"],
        "ttl_hours": plan["cleanup"]["ttl_hours"], "hard_cost_cap_usd": plan["cost"]["hard_cap_usd"],
        "metric_contract_sha256": plan["metric_contract"]["sha256"],
        "trace_sha256": plan["trace_sha256"],
        "model_input_sha256s": sorted({item["input"]["payload_sha256"] for item in models}),
        "cleanup_owner": plan["cleanup"]["owner"], "cleanup_deadline_utc": plan["cleanup"]["deadline_utc"],
        "cluster_version": plan["kubernetes"]["cluster_version"],
        "node_group_profile": plan["kubernetes"]["gpu_profile"],
        "credential_receipt_sha256": plan["security"]["credentials"]["receipt_sha256"],
        "credential_scope_manifest_sha256": plan["security"]["credentials"][
            "scope_manifest_sha256"
        ],
        "threat_model_sha256": plan["security"]["threat_model"]["sha256"],
        "runtime_sources_sha256": plan["runtime_sources"]["sha256"],
    }
    if request != expected_request:
        raise BaselineError("broker immutable request differs from the executable plan")
    if (
        lease["lease_id"] != lease_ref["lease_id"] or lease["prefix"] != prefix
        or lease["project_id"] != plan["project_id"] or lease["region"] != plan["region"]
        or lease["state"] not in lease_ref["admitted_states"]
    ):
        raise BaselineError("resource lease identity/state differs from the plan")
    expected_kubeconfig = str(_resolve(plan_path, plan["kubernetes"]["kubeconfig"], "kubernetes.kubeconfig", live=False))
    if (
        lease["kubeconfig_path"] != expected_kubeconfig
        or lease["kubernetes_context"] != plan["kubernetes"]["context"]
        or lease["api_server"] != plan["kubernetes"]["expected_server"]
    ):
        raise BaselineError("broker cluster connection identity differs from the executable plan")
    profile = profiles[plan["kubernetes"]["gpu_profile"]]
    if lease["preemptible"] is not True or lease["gpu_product"] != profile["product"] or lease["gpu_count"] != profile["gpu_count"]:
        raise BaselineError("broker lease is not the exact preemptible GPU profile")
    inventory = lease["gpu_inventory"]
    if plan["campaign_arm"] == "A_prepared_node":
        _identifier(lease["node_boot_id"], "resource lease node_boot_id")
        if not isinstance(inventory, list) or len(inventory) != lease["gpu_count"]:
            raise BaselineError("broker GPU inventory does not cover the exact admitted GPU count")
        expected_indices = set(range(lease["gpu_count"]))
        observed_indices: set[int] = set()
        observed_uuids: set[str] = set()
        for index, raw_gpu in enumerate(inventory):
            gpu = _expect_keys(
                raw_gpu,
                {"gpu_uuid", "gpu_index", "product", "memory_bytes_total"},
                f"resource lease gpu_inventory[{index}]",
            )
            _identifier(gpu["gpu_uuid"], f"resource lease gpu_inventory[{index}].gpu_uuid")
            if (
                not isinstance(gpu["gpu_index"], int)
                or isinstance(gpu["gpu_index"], bool)
                or gpu["gpu_index"] < 0
                or gpu["product"] != profile["product"]
                or not isinstance(gpu["memory_bytes_total"], int)
                or isinstance(gpu["memory_bytes_total"], bool)
                or gpu["memory_bytes_total"] <= 0
            ):
                raise BaselineError("broker GPU inventory identity/profile is invalid")
            observed_indices.add(gpu["gpu_index"])
            observed_uuids.add(gpu["gpu_uuid"])
        if observed_indices != expected_indices or len(observed_uuids) != len(inventory):
            raise BaselineError("broker GPU inventory has duplicate or noncontiguous identities")
    elif lease["node_boot_id"] is not None or inventory != []:
        raise BaselineError("new-node arm cannot admit a node boot or GPU inventory before T0")
    _validate_resource_graph(lease, plan, lease_ref, plan_path)
    operations = lease["resource_create_operations"]
    if not isinstance(operations, list) or len(operations) != len(lease["resources"]):
        raise BaselineError("broker create-operation receipts do not cover the resource graph")
    operation_ids: set[str] = set()
    for index, operation in enumerate(operations):
        operation = _expect_keys(
            operation,
            {"operation_id", "resource_id", "started_at_utc", "finished_at_utc", "request_sha256"},
            f"resource lease create operation {index}",
        )
        _identifier(operation["operation_id"], f"resource lease create operation {index}.operation_id")
        operation_ids.add(operation["resource_id"])
        _utc(operation["started_at_utc"], f"resource lease create operation {index}.started_at_utc")
        _utc(operation["finished_at_utc"], f"resource lease create operation {index}.finished_at_utc")
        if operation["request_sha256"] != lease["request_sha256"]:
            raise BaselineError("broker create operation is not bound to the immutable request")
    if operation_ids != {item["id"] for item in lease["resources"]}:
        raise BaselineError("broker create-operation IDs differ from the resource graph")
    readiness = _expect_keys(
        lease["readiness_timestamps"], {"cluster_ready_at_utc", "node_ready_at_utc"},
        "resource lease readiness_timestamps",
    )
    _utc(readiness["cluster_ready_at_utc"], "resource lease cluster_ready_at_utc")

    cost = _expect_keys(
        lease["cost_estimate"],
        {"currency", "lease_hour_usd", "transfer_usd_per_gib", "pre_t0_setup_cost_usd", "expected_duration_hours", "hard_cap_usd"},
        "resource lease cost_estimate",
    )
    if cost != {"currency": "USD", **{key: plan["cost"][key] for key in cost if key != "currency"}}:
        raise BaselineError("broker cost estimate differs from the admitted plan")
    cleanup = _expect_keys(
        lease["cleanup_plan"], {"owner", "deadline_utc", "ttl_hours", "delete_exact_ids", "desired_final_state"},
        "resource lease cleanup_plan",
    )
    if cleanup != {
        "owner": plan["cleanup"]["owner"], "deadline_utc": plan["cleanup"]["deadline_utc"],
        "ttl_hours": plan["cleanup"]["ttl_hours"], "delete_exact_ids": sorted(item["id"] for item in lease["resources"]),
        "desired_final_state": "ABSENT",
    }:
        raise BaselineError("broker TTL/cleanup plan is not bound to exact resource IDs")
    audit = _expect_keys(
        lease["audit_chain"],
        {
            "chain_id", "genesis_sha256", "head_sha256", "event_count", "events_path",
            "events_sha256",
        },
        "resource lease audit_chain",
    )
    if audit["chain_id"] != plan["security"]["audit"]["chain_id"] or audit["genesis_sha256"] != plan["security"]["audit"]["genesis_sha256"]:
        raise BaselineError("broker audit chain differs from the admitted hash chain")
    _digest(audit["head_sha256"], "resource lease audit head")
    if not isinstance(audit["event_count"], int) or audit["event_count"] <= 0:
        raise BaselineError("broker audit chain is empty")
    events_path = _resolve(
        plan_path, audit["events_path"], "resource lease audit events_path", live=True
    )
    if file_sha256(events_path) != _digest(
        audit["events_sha256"], "resource lease audit events_sha256"
    ):
        raise BaselineError("broker audit event file differs from its digest")
    events = _load_json(events_path, "broker audit events")
    if not isinstance(events, list) or len(events) != audit["event_count"]:
        raise BaselineError("broker audit event count differs from its receipt")
    previous = audit["genesis_sha256"]
    for index, raw in enumerate(events):
        event = _expect_keys(
            raw, {"sequence", "previous_sha256", "payload", "event_sha256"},
            f"broker audit event {index}",
        )
        if event["sequence"] != index or event["previous_sha256"] != previous:
            raise BaselineError("broker audit chain sequence/previous digest is broken")
        if not isinstance(event["payload"], dict):
            raise BaselineError("broker audit event payload must be an object")
        expected_event_sha = canonical_sha256(
            {
                "sequence": event["sequence"], "previous_sha256": event["previous_sha256"],
                "payload": event["payload"],
            }
        )
        if event["event_sha256"] != expected_event_sha:
            raise BaselineError("broker audit event digest is not hash-chained")
        previous = expected_event_sha
    if audit["head_sha256"] != previous:
        raise BaselineError("broker audit head differs from the recomputed event chain")

    arm_a = plan["campaign_arm"] == "A_prepared_node"
    if arm_a:
        if require_live and lease["state"] != "ACTIVE":
            raise BaselineError("prepared-node live execution requires an ACTIVE broker lease")
        if len(lease["node_group_ids"]) != 1 or len(lease["node_ids"]) != 1:
            raise BaselineError("prepared-node lease lacks exact node-group/node identities")
        _utc(readiness["node_ready_at_utc"], "resource lease node_ready_at_utc")
        receipt = _expect_keys(
            lease["initial_state_receipt"],
            {
                "schema", "node_id", "node_uid", "broker_node_id", "occupant", "cache",
                "cache_targets", "observed_at_utc", "evidence_path", "evidence_sha256",
            },
            "resource lease initial_state_receipt",
        )
        first = trace["requests"][0]
        occupant = first["precondition"]["current_node_occupant"]
        full = None
        if occupant is not None:
            selected = next(item for item in models if (item["model_id"], item["model_version"]) == (occupant["model_id"], occupant["model_version"]))
            full = {
                name: selected[name]
                for name in ("model_id", "model_version", "version_label", "artifact_id", "artifact_version", "artifact_sha256", "image_digest")
            }
        if (
            receipt["schema"] != "archvteams.nebius.ai/k8s-initial-state/v2"
            or receipt["node_id"] != lease["node_ids"][0]
            or receipt["broker_node_id"] != plan["kubernetes"]["broker_node_id"]
            or receipt["node_uid"] != plan["kubernetes"]["node_uid"]
            or receipt["occupant"] != full or receipt["cache"] != first["precondition"]["cache"]
        ):
            raise BaselineError("initial occupant/cache receipt differs from the first accepted precondition")
        expected_cache_targets = [
            {
                "model_id": item["model_id"],
                "model_version": item["model_version"],
                "artifact_id": item["artifact_id"],
                "artifact_version": item["artifact_version"],
                "artifact_sha256": item["artifact_sha256"],
                "artifact_bytes": item["artifact_bytes"],
                "image_digest": item["image_digest"],
                "image_bytes": item["image_bytes"],
                "checkpoint": item["checkpoint"],
            }
            for item in sorted(models, key=lambda value: (value["model_id"], value["model_version"]))
        ]
        if receipt["cache_targets"] != expected_cache_targets:
            raise BaselineError("initial cache targets differ from exact model/artifact/checkpoint identities")
        _utc(receipt["observed_at_utc"], "resource lease initial receipt timestamp")
        initial_evidence_path = _resolve(
            plan_path,
            receipt["evidence_path"],
            "resource lease initial receipt evidence_path",
            live=True,
        )
        if file_sha256(initial_evidence_path) != _digest(
            receipt["evidence_sha256"], "resource lease initial receipt evidence_sha256"
        ):
            raise BaselineError("initial occupant/cache evidence differs from its digest")
        expected_evidence = {
            key: receipt[key]
            for key in (
                "schema", "node_id", "node_uid", "broker_node_id", "occupant", "cache",
                "cache_targets", "observed_at_utc",
            )
        }
        if _load_json(initial_evidence_path, "resource lease initial receipt evidence") != expected_evidence:
            raise BaselineError("initial occupant/cache evidence content differs from the lease")
    elif (
        lease["initial_state_receipt"] is not None
        or lease["node_group_ids"] or lease["node_ids"]
        or readiness["node_ready_at_utc"] is not None
    ):
        raise BaselineError("new-node arm must enter T0 with support only and no GPU node identities")
    return lease, lease_path, lease_source


def validate_plan(value: Any, plan_path: Path, *, require_live: bool = False) -> dict[str, Any]:
    """Validate a plan and return a normalized copy with resolved private paths."""

    plan = _expect_keys(
        value,
        {
            "schema", "experiment_id", "task_id", "project_id", "region", "backend",
            "backend_version", "code_revision", "campaign_arm", "boundary_policy",
            "semantic_calls_per_attempt", "product_terminal_call", "variant", "precreated_support",
            "scenario_strategies", "promoted_scenarios", "minimum_repetitions", "metric_contract",
            "trace_path", "trace_sha256", "gpu_profiles", "models", "kubernetes",
            "resource_lease", "runtime_sources", "security", "cost", "cleanup",
        },
        "plan",
    )
    if plan["schema"] != BASELINE_PLAN_SCHEMA:
        raise BaselineError("plan schema is not supported")
    for key in ("experiment_id", "task_id", "backend", "backend_version"):
        _identifier(plan[key], f"plan.{key}")
    if plan["task_id"] != "catalog-switch-k8s-baseline":
        raise BaselineError("plan task_id does not own this benchmark")
    if plan["project_id"] not in AUTHORIZED_PROJECTS or plan["region"] != AUTHORIZED_PROJECTS[plan["project_id"]]:
        raise BaselineError("project and region are outside the epic allowlist")
    if not isinstance(plan["code_revision"], str) or COMMIT.fullmatch(plan["code_revision"]) is None:
        raise BaselineError("code_revision must be an exact Git commit")
    metric_path = _validate_metric_contract(plan, plan_path)
    if require_live:
        _validate_live_source_revision(plan["code_revision"])
    if plan["campaign_arm"] not in {"A_prepared_node", "B_new_preemptible_node"}:
        raise BaselineError("campaign_arm is invalid")
    boundary = _expect_keys(
        plan["boundary_policy"], {"node_creation", "artifact_localization", "model_specific_work"},
        "boundary_policy",
    )
    expected_boundary = (
        {"node_creation": "before_cohort_t0", "artifact_localization": "declared_cache_precondition_or_after_t0", "model_specific_work": "declared_occupant_precondition_or_after_t0"}
        if plan["campaign_arm"] == "A_prepared_node"
        else {"node_creation": "after_t0", "artifact_localization": "after_t0", "model_specific_work": "after_t0"}
    )
    if boundary != expected_boundary:
        raise BaselineError("campaign arm violates its frozen T0 boundary policy")
    if plan["semantic_calls_per_attempt"] != 2 or plan["product_terminal_call"] != 1:
        raise BaselineError("campaign must preserve two-call qualification and call-1 product terminal")
    if plan["variant"] not in VARIANTS or frozenset(plan["precreated_support"]) != VARIANTS[plan["variant"]]:
        raise BaselineError("variant differs from the admitted single support-object change")
    strategies = _expect_keys(plan["scenario_strategies"], set(SCENARIOS), "scenario_strategies")
    if (
        any(item not in STRATEGIES for item in strategies.values())
        or strategies["same_model_hot"] != "none"
        or strategies["capacity_miss"] != "none"
        or strategies["checkpoint_fallback"] != "conventional"
    ):
        raise BaselineError("scenario strategy violates conventional/snapshot/fallback policy")
    promoted = plan["promoted_scenarios"]
    if not isinstance(promoted, list) or not promoted or len(set(promoted)) != len(promoted) or any(item not in SCENARIOS for item in promoted):
        raise BaselineError("promoted_scenarios is invalid")
    if not isinstance(plan["minimum_repetitions"], int) or plan["minimum_repetitions"] < 30:
        raise BaselineError("promoted stratified cohorts require at least 30 repetitions")

    trace_path = _resolve(plan_path, plan["trace_path"], "trace_path", live=True)
    trace_value, trace_source = _load_pinned_json(
        trace_path, _digest(plan["trace_sha256"], "trace_sha256"), "trace"
    )
    trace = validate_trace(trace_value)
    profiles = _validate_gpu_profiles(plan)
    minimum_models = 1 if set(plan["promoted_scenarios"]) == {"same_model_hot"} else 2
    if not isinstance(plan["models"], list) or len(plan["models"]) < minimum_models:
        raise BaselineError(f"plan requires at least {minimum_models} matched model(s)")
    models = [_validate_model(item, index, plan_path, profiles) for index, item in enumerate(plan["models"])]
    if len({(item["model_id"], item["model_version"]) for item in models}) != len(models):
        raise BaselineError("model identities are duplicated")
    if len({item["version_label"] for item in models}) != len(models):
        raise BaselineError("model version labels are duplicated")
    _validate_trace_binding(trace, models, plan)
    security_paths = _validate_security(plan, plan_path, require_live=require_live)
    runtime_sources_path = _validate_runtime_sources(
        plan, plan_path, models, require_live=require_live
    )

    kube = _expect_keys(
        plan["kubernetes"],
        {
            "kubeconfig", "context", "expected_server", "cluster_version", "namespace",
            "namespace_resource_id", "namespace_uid", "service_account_resource_id",
            "service_account_uid", "node_name", "node_uid", "broker_node_id",
            "broker_node_group_id", "gpu_profile", "preemptible", "sentinel_pod",
            "ready_timeout_seconds", "drain_timeout_seconds",
        },
        "kubernetes",
    )
    for key in ("context", "cluster_version", "gpu_profile"):
        _identifier(kube[key], f"kubernetes.{key}")
    if plan["campaign_arm"] == "A_prepared_node":
        for key in ("node_name", "node_uid", "broker_node_id", "broker_node_group_id"):
            _identifier(kube[key], f"kubernetes.{key}")
    elif any(
        kube[key] is not None
        for key in ("node_name", "node_uid", "broker_node_id", "broker_node_group_id")
    ):
        raise BaselineError("new-node arm cannot name a GPU node before external T0")
    for key in ("namespace", "sentinel_pod"):
        _dns_label(kube[key], f"kubernetes.{key}")
    for key in (
        "namespace_resource_id", "namespace_uid", "service_account_resource_id",
        "service_account_uid",
    ):
        _identifier(kube[key], f"kubernetes.{key}")
    if kube["gpu_profile"] not in profiles or kube["preemptible"] is not True:
        raise BaselineError("Kubernetes node must use an admitted preemptible GPU profile")
    if any(model["gpu_profile"] != kube["gpu_profile"] for model in models):
        raise BaselineError("one campaign may contain only models compatible with its GPU profile")
    if not isinstance(kube["expected_server"], str) or not kube["expected_server"].startswith("https://"):
        raise BaselineError("kubernetes.expected_server must be HTTPS")
    for key in ("ready_timeout_seconds", "drain_timeout_seconds"):
        if not isinstance(kube[key], int) or kube[key] <= 0:
            raise BaselineError(f"kubernetes.{key} must be positive")
    if kube["drain_timeout_seconds"] > 30:
        raise BaselineError("drain timeout exceeds security control CTL-13")
    kubeconfig = _resolve(plan_path, kube["kubeconfig"], "kubernetes.kubeconfig", live=require_live and plan["campaign_arm"] == "A_prepared_node")

    cost = _expect_keys(
        plan["cost"], {"lease_hour_usd", "transfer_usd_per_gib", "pre_t0_setup_cost_usd", "expected_duration_hours", "hard_cap_usd", "price_snapshot_utc", "source"},
        "cost",
    )
    for key in ("lease_hour_usd", "expected_duration_hours", "hard_cap_usd"):
        _positive(cost[key], f"cost.{key}")
    for key in ("transfer_usd_per_gib", "pre_t0_setup_cost_usd"):
        _positive(cost[key], f"cost.{key}", allow_zero=True)
    if cost["lease_hour_usd"] * cost["expected_duration_hours"] + cost["pre_t0_setup_cost_usd"] > cost["hard_cap_usd"]:
        raise BaselineError("expected lease/setup cost exceeds the hard cap")
    _utc(cost["price_snapshot_utc"], "cost.price_snapshot_utc")
    if not isinstance(cost["source"], str) or len(cost["source"].strip()) < 10:
        raise BaselineError("cost.source is too vague")
    cleanup = _expect_keys(plan["cleanup"], {"owner", "deadline_utc", "ttl_hours", "plan"}, "cleanup")
    _identifier(cleanup["owner"], "cleanup.owner")
    _utc(cleanup["deadline_utc"], "cleanup.deadline_utc")
    _positive(cleanup["ttl_hours"], "cleanup.ttl_hours")
    if not isinstance(cleanup["plan"], str) or len(cleanup["plan"].strip()) < 20:
        raise BaselineError("cleanup.plan is too vague")

    lease, lease_path, lease_source = _validate_lease(
        plan, plan_path, trace, models, profiles, require_live=require_live
    )
    normalized = json.loads(canonical_json(plan))
    normalized["_resolved"] = {
        "plan_path": str(plan_path.resolve()), "trace_path": str(trace_path),
        "kubeconfig": str(kubeconfig), "lease_path": str(lease_path), "lease_loaded": lease is not None,
        "threat_model": str(security_paths["threat_model"]),
        "credential_receipt": str(security_paths["credential_receipt"]),
        "credential_scope_manifest": str(security_paths["credential_scope_manifest"]),
        "support_image_receipt": str(security_paths["support_image_receipt"]),
        "runtime_sources": str(runtime_sources_path),
        "metric_contract": str(metric_path),
        "config_sha256": hashlib.sha256(canonical_json(plan).encode()).hexdigest(),
    }
    normalized["models"] = models
    normalized["_admitted_sources"] = {
        "trace": trace_source,
        "lease": lease_source,
    }
    return normalized


def load_plan(path: Path, *, require_live: bool = False) -> dict[str, Any]:
    """Load and validate one canonical plan file."""

    _regular_file(path, "plan")
    raw = path.read_text(encoding="utf-8")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BaselineError("plan is invalid JSON") from exc
    if raw != canonical_json(value) + "\n":
        raise BaselineError("plan must be canonical JSON with one terminal newline")
    return validate_plan(value, path, require_live=require_live)


def safe_output_path(path: Path) -> Path:
    """Require a new output below an existing non-symlink directory."""

    if not path.is_absolute():
        raise BaselineError("output path must be absolute")
    if os.path.lexists(path):
        raise BaselineError("output path already exists")
    parent = path.parent.resolve(strict=True)
    if parent.is_symlink() or not parent.is_dir():
        raise BaselineError("output parent must be a real directory")
    return parent / path.name
