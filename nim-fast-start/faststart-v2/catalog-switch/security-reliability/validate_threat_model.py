#!/usr/bin/env python3
"""Fail-closed consistency validator for the catalog-switch threat model.

The threat model is only usable as a production gate if its cross-references
hold: every invariant is enforced by a control, every control is adversary-
or test-exercised, every test maps to declared evidence fields, and every
backend and pilot is covered. This validator enforces those properties and
refuses (non-zero exit, full error list) on any gap. Absence of evidence is
failure, matching INV-03 of the model itself.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = "archvteams.nebius.ai/catalog-switch-threat-model/v1"
BACKEND_IDS = ("k8s", "k8s-hotpath", "node-vm", "modal")
PILOT_IDS = ("k8s", "node-local", "modal")
BACKEND_APPLICABILITY = ("required", "delegated", "partial", "not-applicable")
REQUIRED_ADVERSARY_CATEGORIES = (
    "crash",
    "preemption",
    "api-loss",
    "partial-write",
    "foreign-replacement",
    "stale-cache",
)
ALLOWED_STATUSES = ("draft-pending-independent-review", "reviewed")
ACCEPTED_RISK_MARKER = "Accepted-risk exception"
ID_PATTERNS = {
    "assets": r"^AST-\d{2}$",
    "trust_boundaries": r"^TB-\d{2}$",
    "threat_actors": r"^TA-\d{2}$",
    "invariants": r"^INV-\d{2}$",
    "controls": r"^CTL-\d{2}$",
    "adversaries": r"^ADV-\d{2}$",
    "tests": r"^TST-\d{2}$",
    "review_findings": r"^RF-\d{2}$",
}
TOP_LEVEL_KEYS = (
    "schema",
    "title",
    "scope",
    "status",
    "backends",
    "assets",
    "trust_boundaries",
    "threat_actors",
    "invariants",
    "controls",
    "adversaries",
    "tests",
    "evidence_fields",
    "reliability",
    "review_findings",
)


class ThreatModelError(ValueError):
    """The threat model failed fail-closed validation."""


def _ids(doc: dict, section: str, errors: list[str]) -> set[str]:
    seen: set[str] = set()
    pattern = re.compile(ID_PATTERNS[section])
    for entry in doc.get(section, []):
        entry_id = entry.get("id", "")
        if not pattern.match(entry_id):
            errors.append(f"{section}: bad or missing id {entry_id!r}")
        if entry_id in seen:
            errors.append(f"{section}: duplicate id {entry_id!r}")
        seen.add(entry_id)
    return seen


def _require_nonempty_str(entry: dict, key: str, where: str, errors: list[str]) -> None:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{where}: missing or empty {key!r}")


def validate(doc: dict, md_text: str) -> list[str]:
    """Return the full list of validation errors (empty means pass)."""
    errors: list[str] = []

    for key in TOP_LEVEL_KEYS:
        if key not in doc:
            errors.append(f"top-level: missing key {key!r}")
    if doc.get("schema") != SCHEMA:
        errors.append(f"schema: expected {SCHEMA!r}, got {doc.get('schema')!r}")
    if doc.get("status") not in ALLOWED_STATUSES:
        errors.append(f"status: {doc.get('status')!r} not in {ALLOWED_STATUSES}")

    backend_ids = tuple(b.get("id") for b in doc.get("backends", []))
    if backend_ids != BACKEND_IDS:
        errors.append(f"backends: expected exactly {BACKEND_IDS}, got {backend_ids}")
    backend_invariant_exceptions: dict[str, dict[str, str]] = {}
    exception_scored_refs: list[tuple[str, str]] = []
    for backend in doc.get("backends", []):
        where = f"backend {backend.get('id')}"
        _require_nonempty_str(backend, "name", where, errors)
        _require_nonempty_str(backend, "description", where, errors)
        surface = backend.get("attack_surface")
        if not isinstance(surface, list) or not surface:
            errors.append(f"{where}: attack_surface must be a non-empty list")
        exceptions: dict[str, str] = {}
        for exception in backend.get("invariant_exceptions", []):
            invariant = exception.get("invariant", "")
            if not str(exception.get("note", "")).strip():
                errors.append(f"{where}: invariant exception {invariant!r} needs a note")
            if not re.match(r"^ADV-\d{2}$", str(exception.get("scored_by", ""))):
                errors.append(
                    f"{where}: invariant exception {invariant!r} must name the "
                    "adversary (scored_by) that scores the accepted risk"
                )
            else:
                exception_scored_refs.append((where, exception["scored_by"]))
            exceptions[invariant] = exception.get("note", "")
        backend_invariant_exceptions[backend.get("id", "")] = exceptions

    asset_ids = _ids(doc, "assets", errors)
    boundary_ids = _ids(doc, "trust_boundaries", errors)
    actor_ids = _ids(doc, "threat_actors", errors)
    invariant_ids = _ids(doc, "invariants", errors)
    control_ids = _ids(doc, "controls", errors)
    adversary_ids = _ids(doc, "adversaries", errors)
    test_ids = _ids(doc, "tests", errors)
    _ids(doc, "review_findings", errors)
    if not asset_ids:
        errors.append("assets: section is empty")
    if not actor_ids:
        errors.append("threat_actors: section is empty")

    for boundary in doc.get("trust_boundaries", []):
        where = f"trust boundary {boundary.get('id')}"
        _require_nonempty_str(boundary, "description", where, errors)
        for backend in boundary.get("backends", []):
            if backend not in BACKEND_IDS:
                errors.append(f"{where}: unknown backend {backend!r}")

    field_names: set[str] = set()
    for field in doc.get("evidence_fields", []):
        name = field.get("name", "")
        if not re.match(r"^[a-z][a-z0-9_]+$", name):
            errors.append(f"evidence_fields: bad field name {name!r}")
        if name in field_names:
            errors.append(f"evidence_fields: duplicate field {name!r}")
        field_names.add(name)
        _require_nonempty_str(field, "description", f"evidence field {name}", errors)
        _require_nonempty_str(field, "type", f"evidence field {name}", errors)

    controls_referencing_invariant: dict[str, int] = {i: 0 for i in invariant_ids}
    required_backend_invariants: dict[str, set[str]] = {b: set() for b in BACKEND_IDS}
    tests_referenced_by_controls: set[str] = set()
    used_fields: set[str] = set()

    for control in doc.get("controls", []):
        cid = control.get("id", "?")
        where = f"control {cid}"
        _require_nonempty_str(control, "name", where, errors)
        _require_nonempty_str(control, "statement", where, errors)
        if not control.get("invariants"):
            errors.append(f"{where}: must serve at least one invariant")
        for inv in control.get("invariants", []):
            if inv not in invariant_ids:
                errors.append(f"{where}: unknown invariant {inv!r}")
            else:
                controls_referencing_invariant[inv] += 1
        for actor in control.get("threat_actors", []):
            if actor not in actor_ids:
                errors.append(f"{where}: unknown threat actor {actor!r}")
        backends = control.get("backends", {})
        if not isinstance(backends, dict):
            errors.append(f"{where}: backends must be a mapping")
            backends = {}
        needs_note = False
        for backend_id in BACKEND_IDS:
            applicability = backends.get(backend_id)
            if applicability not in BACKEND_APPLICABILITY:
                errors.append(
                    f"{where}: backend {backend_id!r} applicability "
                    f"{applicability!r} not in {BACKEND_APPLICABILITY}"
                )
            elif applicability != "required":
                needs_note = True
            if applicability == "required":
                for inv in control.get("invariants", []):
                    required_backend_invariants[backend_id].add(inv)
        for key in backends:
            if key not in BACKEND_IDS + ("delegation_note",):
                errors.append(f"{where}: unexpected backends key {key!r}")
        if needs_note and not str(backends.get("delegation_note", "")).strip():
            errors.append(
                f"{where}: non-required backend applicability requires a delegation_note"
            )
        if not control.get("tests"):
            errors.append(f"{where}: must map to at least one test")
        for test in control.get("tests", []):
            if test not in test_ids:
                errors.append(f"{where}: unknown test {test!r}")
            tests_referenced_by_controls.add(test)
        if not control.get("evidence_fields"):
            errors.append(f"{where}: must name at least one evidence field")
        for field in control.get("evidence_fields", []):
            if field not in field_names:
                errors.append(f"{where}: undeclared evidence field {field!r}")
            used_fields.add(field)
        cost = control.get("cost", {})
        if not isinstance(cost.get("critical_path"), bool):
            errors.append(f"{where}: cost.critical_path must be a bool")
        _require_nonempty_str(cost, "estimate", f"{where} cost", errors)
        _require_nonempty_str(cost, "risk_if_weakened", f"{where} cost", errors)

    for inv, count in controls_referencing_invariant.items():
        if count == 0:
            errors.append(f"invariant {inv}: not enforced by any control")

    for backend_id in BACKEND_IDS:
        exceptions = backend_invariant_exceptions.get(backend_id, {})
        for exc_inv in exceptions:
            if exc_inv not in invariant_ids:
                errors.append(
                    f"backend {backend_id}: invariant exception for unknown {exc_inv!r}"
                )
        for inv in sorted(invariant_ids):
            covered = inv in required_backend_invariants[backend_id]
            excepted = inv in exceptions
            if not covered and not excepted:
                errors.append(
                    f"backend {backend_id}: invariant {inv} has no required control "
                    "and no explicit invariant_exceptions entry"
                )
            if covered and excepted:
                errors.append(
                    f"backend {backend_id}: redundant invariant exception for {inv} "
                    "(a required control already enforces it)"
                )

    assets_referenced: set[str] = set()
    controls_covered_by_adversaries: set[str] = set()
    seen_categories: set[str] = set()
    for adversary in doc.get("adversaries", []):
        aid = adversary.get("id", "?")
        where = f"adversary {aid}"
        _require_nonempty_str(adversary, "name", where, errors)
        _require_nonempty_str(adversary, "scenario", where, errors)
        _require_nonempty_str(adversary, "category", where, errors)
        _require_nonempty_str(adversary, "expected_outcome", where, errors)
        seen_categories.add(adversary.get("category", ""))
        for actor in adversary.get("actors", []):
            if actor not in actor_ids:
                errors.append(f"{where}: unknown actor {actor!r}")
        if not adversary.get("actors"):
            errors.append(f"{where}: must name at least one actor")
        if not adversary.get("trust_boundaries"):
            errors.append(f"{where}: must name at least one trust boundary")
        for boundary in adversary.get("trust_boundaries", []):
            if boundary not in boundary_ids:
                errors.append(f"{where}: unknown trust boundary {boundary!r}")
        if not adversary.get("assets_at_risk"):
            errors.append(f"{where}: must name at least one asset at risk")
        for asset in adversary.get("assets_at_risk", []):
            if asset not in asset_ids:
                errors.append(f"{where}: unknown asset {asset!r}")
            assets_referenced.add(asset)
        for inv in adversary.get("invariants_at_risk", []):
            if inv not in invariant_ids:
                errors.append(f"{where}: unknown invariant {inv!r}")
        if not adversary.get("invariants_at_risk"):
            errors.append(f"{where}: must name at least one invariant at risk")
        if not adversary.get("controls"):
            errors.append(f"{where}: must name at least one mitigating control")
        for control in adversary.get("controls", []):
            if control not in control_ids:
                errors.append(f"{where}: unknown control {control!r}")
            controls_covered_by_adversaries.add(control)
        fails_closed = adversary.get("fails_closed")
        if not isinstance(fails_closed, bool):
            errors.append(f"{where}: fails_closed must be a bool")
        elif not fails_closed:
            if ACCEPTED_RISK_MARKER not in adversary.get("fail_note", ""):
                errors.append(
                    f"{where}: fails_closed=false requires an explicit "
                    f"{ACCEPTED_RISK_MARKER!r} fail_note"
                )
        _require_nonempty_str(adversary, "fail_note", where, errors)

    for category in REQUIRED_ADVERSARY_CATEGORIES:
        if category not in seen_categories:
            errors.append(f"adversaries: required category {category!r} is not modeled")

    for asset in sorted(asset_ids - assets_referenced):
        errors.append(f"asset {asset}: not referenced by any adversary")

    for where, scored_by in exception_scored_refs:
        if scored_by not in adversary_ids:
            errors.append(f"{where}: scored_by names unknown adversary {scored_by!r}")

    for control_id in sorted(control_ids):
        if control_id not in controls_covered_by_adversaries:
            errors.append(
                f"control {control_id}: not exercised by any adversary scenario"
            )

    pilots_covered: set[str] = set()
    for test in doc.get("tests", []):
        tid = test.get("id", "?")
        where = f"test {tid}"
        _require_nonempty_str(test, "name", where, errors)
        _require_nonempty_str(test, "procedure", where, errors)
        pilots = test.get("pilots", [])
        if not pilots:
            errors.append(f"{where}: must target at least one pilot")
        for pilot in pilots:
            if pilot not in PILOT_IDS:
                errors.append(f"{where}: unknown pilot {pilot!r}")
            pilots_covered.add(pilot)
        if not test.get("evidence_fields"):
            errors.append(f"{where}: must map to at least one evidence field")
        for field in test.get("evidence_fields", []):
            if field not in field_names:
                errors.append(f"{where}: undeclared evidence field {field!r}")
            used_fields.add(field)
        if tid not in tests_referenced_by_controls:
            errors.append(f"{where}: not required by any control")

    for pilot in PILOT_IDS:
        if pilot not in pilots_covered:
            errors.append(f"tests: pilot {pilot!r} has no mapped test")

    for field in sorted(field_names - used_fields):
        errors.append(f"evidence field {field!r}: declared but never used")

    fields_by_test = {
        t.get("id"): set(t.get("evidence_fields", [])) for t in doc.get("tests", [])
    }
    produced_fields = set().union(*fields_by_test.values()) if fields_by_test else set()
    for field in sorted(field_names - produced_fields):
        errors.append(f"evidence field {field!r}: produced by no test")
    for control in doc.get("controls", []):
        produced_by_mapped = set().union(
            *(fields_by_test.get(t, set()) for t in control.get("tests", [])), set()
        )
        control_fields = set(control.get("evidence_fields", []))
        if control_fields and not control_fields & produced_by_mapped:
            errors.append(
                f"control {control.get('id')}: none of its evidence fields are "
                "produced by its mapped tests"
            )

    reliability = doc.get("reliability", {})
    slos = reliability.get("slos", [])
    if len(slos) < 3:
        errors.append("reliability: at least three SLOs are required")
    for slo in slos:
        if not re.match(r"^SLO-\d{2}$", slo.get("id", "")):
            errors.append(f"reliability: bad SLO id {slo.get('id')!r}")
        _require_nonempty_str(slo, "statement", f"SLO {slo.get('id')}", errors)
    if not reliability.get("fallback_ladder"):
        errors.append("reliability: fallback_ladder is empty")
    machines = reliability.get("state_machines", {})
    for machine_name in ("switch", "rollback"):
        machine = machines.get(machine_name)
        if not machine:
            errors.append(f"reliability: state machine {machine_name!r} is missing")
            continue
        states = machine.get("states", [])
        if not states:
            errors.append(f"state machine {machine_name}: no states")
        transitions = machine.get("transitions", [])
        if not transitions:
            errors.append(f"state machine {machine_name}: no transitions")
        for transition in transitions:
            src, dst = transition.get("from"), transition.get("to")
            if src not in states and src != "ANY":
                errors.append(f"state machine {machine_name}: unknown from-state {src!r}")
            if dst not in states:
                errors.append(f"state machine {machine_name}: unknown to-state {dst!r}")
            _require_nonempty_str(
                transition, "on", f"state machine {machine_name} {src}->{dst}", errors
            )

    findings = doc.get("review_findings", [])
    for finding in findings:
        where = f"review finding {finding.get('id')}"
        _require_nonempty_str(finding, "source", where, errors)
        _require_nonempty_str(finding, "finding", where, errors)
        if finding.get("status") not in ("open", "closed"):
            errors.append(f"{where}: status must be open or closed")
        if finding.get("status") == "closed":
            _require_nonempty_str(finding, "resolution", where, errors)
    if doc.get("status") == "reviewed":
        if not findings:
            errors.append("status 'reviewed' requires at least one recorded review finding")
        for finding in findings:
            if finding.get("status") != "closed":
                errors.append(
                    f"status 'reviewed' requires all findings closed; "
                    f"{finding.get('id')} is {finding.get('status')!r}"
                )

    referenced_ids = (
        set().union(
            asset_ids,
            boundary_ids,
            actor_ids,
            invariant_ids,
            control_ids,
            adversary_ids,
            test_ids,
            {slo.get("id", "") for slo in slos},
        )
        | set(BACKEND_IDS)
    )
    for token in sorted(referenced_ids):
        if token and token not in md_text:
            errors.append(f"THREAT_MODEL.md: does not mention {token!r}")

    return errors


def load_and_validate(json_path: Path, md_path: Path) -> dict:
    doc = json.loads(json_path.read_text())
    md_text = md_path.read_text()
    errors = validate(doc, md_text)
    if errors:
        raise ThreatModelError(
            f"{len(errors)} threat-model validation error(s):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
    return doc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=HERE / "threat_model.json")
    parser.add_argument("--md", type=Path, default=HERE / "THREAT_MODEL.md")
    args = parser.parse_args(argv)
    try:
        doc = load_and_validate(args.json, args.md)
    except (ThreatModelError, OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS: threat model consistent "
        f"(status={doc['status']}, {len(doc['controls'])} controls, "
        f"{len(doc['adversaries'])} adversaries, {len(doc['tests'])} tests, "
        f"{len(doc['review_findings'])} review findings)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
