"""Adapters that swap measured evidence in for placeholders.

The simulator's semantics never depend on where a distribution came from:
the engine only reads ``CatalogModel`` fields and the resolved fleet
parameter dict. These adapters let the catalog-inventory and shared-harness
tasks replace placeholder rows with measured cohorts later by supplying a
versioned override document, without any engine change.

Override document shape (JSON, ``schema_version`` mandatory)::

    {
      "schema_version": "1.0.0",
      "kind": "measured-overrides",
      "models": {
        "<model_id>": {
          "source": "<mandatory evidence reference>",
          "evidence_class": "<e.g. fresh fail-closed n=20>",
          "strategy_default": "snapshot" | "conventional",
          "ready_seconds": [..],
          "call1_seconds": [..],
          "call2_seconds": [..],
          "artifact_bytes": <int>,
          "artifact_digest": "<content identity>",
          "local_full_read_seconds": <float or null>,
          "conventional_ready_seconds": <float, optional>
        }, ...
      },
      "fleet": {                       # optional measured fleet scalars
        "l2_fetch_bytes_per_s": {"value": <num>, "source": "<evidence>"},
        ...
      }
    }

Every override becomes ``provenance="measured"`` and every distribution keeps
the supplied source string, so a report built from an adapted catalog remains
audit-traceable per model.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Dict, Tuple

from .catalog import CatalogModel
from .schema import EmpiricalDist, SchemaError, require_schema_version
from .units import seconds_to_micros

FLEET_OVERRIDABLE = (
    "l2_fetch_bytes_per_s",
    "l1_capacity_bytes",
    "gpu_release_micros",
    "node_mtbf_micros",
    "node_reprovision_micros",
    "gpu_hour_usd",
    "l2_egress_usd_per_gib",
)


def load_override_document(path: Path) -> dict:
    doc = json.loads(Path(path).read_text())
    require_schema_version(doc, f"override document {path}")
    if doc.get("kind") != "measured-overrides":
        raise SchemaError(f"{path}: kind must be 'measured-overrides'")
    if not isinstance(doc.get("models"), dict):
        raise SchemaError(f"{path}: 'models' must be an object")
    return doc


def apply_model_overrides(
    catalog: Dict[str, CatalogModel], doc: dict
) -> Tuple[Dict[str, CatalogModel], list]:
    """Return a new catalog with measured overrides applied.

    Unknown model ids are an error: an override that silently matches nothing
    would leave a placeholder posing as covered. Returns the new catalog and
    the list of replaced model ids.
    """
    updated = dict(catalog)
    replaced = []
    for model_id, spec in sorted(doc["models"].items()):
        if model_id not in updated:
            raise SchemaError(f"override references unknown model {model_id!r}")
        source = spec.get("source", "")
        if not source or not str(source).strip():
            raise SchemaError(f"override for {model_id!r} requires a source")
        current = updated[model_id]

        def dist(field: str) -> EmpiricalDist:
            samples = spec.get(field)
            if not isinstance(samples, list) or not samples:
                raise SchemaError(
                    f"override for {model_id!r} requires non-empty {field!r}"
                )
            return EmpiricalDist.from_seconds(
                f"{model_id}-{field}", samples, source
            )

        artifact_bytes = spec.get("artifact_bytes")
        if not isinstance(artifact_bytes, int) or artifact_bytes <= 0:
            raise SchemaError(
                f"override for {model_id!r} requires positive int artifact_bytes"
            )
        digest = spec.get("artifact_digest")
        if not digest or not str(digest).strip():
            raise SchemaError(
                f"override for {model_id!r} requires artifact_digest"
            )
        full_read = spec.get("local_full_read_seconds")
        full_read_micros = (
            0 if full_read is None else seconds_to_micros(float(full_read))
        )
        strategy = spec.get("strategy_default", current.strategy_default)
        if strategy not in ("snapshot", "conventional"):
            raise SchemaError(
                f"override for {model_id!r}: bad strategy {strategy!r}"
            )
        conv = spec.get("conventional_ready_seconds")
        conv_micros = (
            current.conventional_ready_micros
            if conv is None
            else seconds_to_micros(float(conv))
        )
        updated[model_id] = replace(
            current,
            provenance="measured",
            evidence_class=spec.get("evidence_class", "measured override"),
            strategy_default=strategy,
            ready_dist=dist("ready_seconds"),
            call1_dist=dist("call1_seconds"),
            call2_dist=dist("call2_seconds"),
            artifact_bytes=artifact_bytes,
            artifact_digest=str(digest),
            local_full_read_micros=full_read_micros,
            conventional_ready_micros=conv_micros,
            scale=1.0,
        )
        replaced.append(model_id)
    return updated, replaced


def apply_fleet_overrides(fleet: dict, doc: dict) -> Tuple[dict, list]:
    """Replace placeholder fleet scalars with measured values."""
    overrides = doc.get("fleet") or {}
    updated = dict(fleet)
    replaced = []
    for key, spec in sorted(overrides.items()):
        if key not in FLEET_OVERRIDABLE:
            raise SchemaError(f"fleet override key {key!r} is not overridable")
        if not isinstance(spec, dict) or "value" not in spec:
            raise SchemaError(f"fleet override {key!r} must be {{value, source}}")
        if not str(spec.get("source", "")).strip():
            raise SchemaError(f"fleet override {key!r} requires a source")
        value = spec["value"]
        if isinstance(updated[key], int):
            value = int(value)
        if value < 0:
            raise SchemaError(f"fleet override {key!r} must be non-negative")
        updated[key] = value
        replaced.append(key)
    return updated, replaced
