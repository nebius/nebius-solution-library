from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from performance.request_slo import harness
from performance.storage_cache_matrix.catalog_boundary_analysis.analysis import (
    ATTEMPT_SCHEMA,
    CLEANUP_EVIDENCE_KEYS,
    EVIDENCE_SCHEMA,
    OPERATION_EVIDENCE_KEYS,
    OPERATIONS,
    OWNERSHIP_SCHEMA,
    AnalysisError,
    analyze_capacity,
    load_attempts,
    validate_attempts,
    validate_source_manifest,
    verify_pinned_sources,
)


PACKAGE = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[6]
TASK_DECK_ROOT = Path("/home/tux/dashboard/data")
ARTIFACT_BYTES = 1024
RESOURCE_KINDS = (
    "broker_lease",
    "node",
    "pvc",
    "pv",
    "provider_volume",
    "node_seed",
    "object_store_object",
)
WRITABLE_KINDS = {"pvc", "pv", "provider_volume"}


def _load(name: str):
    return json.loads((PACKAGE / name).read_text(encoding="utf-8"))


def _catalog() -> dict:
    models = []
    for index, suffix in enumerate(("a", "b", "c"), 1):
        models.append(
            {
                "model_id": f"model-{suffix}",
                "model_version": f"v{index}",
                "artifact_id": f"artifact-{suffix}",
                "artifact_version": f"av{index}",
                "artifact_sha256": suffix * 64,
                "input": {
                    "workload_id": f"workload-{suffix}",
                    "input_id": f"input-{suffix}",
                    "payload_sha256": str(index) * 64,
                    "input_bytes": index * 100,
                },
            }
        )
    return {"schema": harness.CATALOG_SCHEMA, "models": models}


def _state_for(request: dict) -> str:
    return {
        "same_model_hot": "A_materialized_hit",
        "idle_local": "B_node_seed_post_t0_materialization",
        "capacity_miss": "C_remote_miss_post_t0",
        "a_to_b_remote": "D_active_a_to_b_reclaim",
        "a_to_b_local": "D_active_a_to_b_reclaim",
        "checkpoint_fallback": "D_active_a_to_b_reclaim",
    }[request["scenario"]]


class CatalogBoundaryAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifest = _load("source_manifest.json")
        self.config = _load("analysis_config.json")
        self.trace = harness.generate_trace(
            _catalog(),
            distribution="adversarial",
            seed=2407,
            request_count=10,
            trace_id="storage-cache-v2-smoke",
            interval_ms=10,
        )
        self.events = copy.deepcopy(harness.synthetic_smoke_ledger(self.trace))
        self._bind_slo_ownership()
        self.results = {
            item["attempt_id"]: item
            for item in harness.validate_ledger(self.events, self.trace)
        }
        self.trace_path = self.root / "request-slo-trace.json"
        self.ledger_path = self.root / "request-slo-ledger.jsonl"
        self.trace_path.write_text(harness.canonical_json(self.trace) + "\n")
        harness.write_ledger(self.ledger_path, self.events)
        self.trace_sha = hashlib.sha256(self.trace_path.read_bytes()).hexdigest()
        self.ledger_sha = hashlib.sha256(self.ledger_path.read_bytes()).hexdigest()
        self.ledger_id = self.events[0]["ledger_id"]
        self.clock = {
            **self.events[0]["recorder"],
            "timestamp_source": "external-request-slo-recorder-monotonic/v1",
        }
        self.global_operation_base = max(
            event["observed_monotonic_ns"]
            for event in self.events
            if event["event_type"] == "request.accepted"
        ) + 1_000_000
        self.attempts = [self._build_attempt(request) for request in self.trace["requests"]]
        concurrent = [self.attempts[1], self.attempts[4]]
        for attempt, peer in ((concurrent[0], concurrent[1]), (concurrent[1], concurrent[0])):
            attempt["concurrency"]["group_id"] = "two-model-overlap"
            attempt["concurrency"]["peer_attempt_ids"] = [peer["attempt_id"]]
            self._sync_evidence(attempt)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _resources(self, attempt_id: str) -> list[dict]:
        project = "project-e00z6b02t8ddk96c49"
        return [
            {
                "kind": kind,
                "id": f"{kind}-{attempt_id}",
                "project_id": project,
                "region": "eu-north1",
            }
            for kind in RESOURCE_KINDS
        ]

    def _bind_slo_ownership(self) -> None:
        requests = {request["attempt_id"]: request for request in self.trace["requests"]}
        for event in self.events:
            request = requests[event["attempt_id"]]
            resources = self._resources(event["attempt_id"])
            if event["event_type"] == "request.accepted":
                environment = dict(event["data"]["environment"])
                environment["node_id"] = f"node-{event['attempt_id']}"
                event["data"]["environment"] = environment
                event["data"]["ownership"] = {
                    "owner_task_id": "catalog-switch-storage-cache-matrix",
                    "resource_prefix": f"storage-v2-{request['sequence']}",
                    "dedicated": True,
                    "cleanup_required": True,
                    "resources": resources,
                }
            elif event["event_type"] == "cleanup.finished":
                state = _state_for(request)
                deleted = (
                    []
                    if state == "A_materialized_hit"
                    else [item["id"] for item in resources if item["kind"] in WRITABLE_KINDS]
                )
                retained = [item["id"] for item in resources if item["id"] not in deleted]
                event["data"] = {
                    "required": True,
                    "status": "retained",
                    "resources_deleted": deleted,
                    "resources_retained": retained,
                    "receipt_sha256": hashlib.sha256(
                        f"slo-cleanup:{event['attempt_id']}".encode()
                    ).hexdigest(),
                    "reason": "synthetic exact-ID final-state fixture",
                }

    def _event(self, attempt_id: str, event_types: set[str]) -> dict:
        return next(
            event
            for event in self.events
            if event["attempt_id"] == attempt_id and event["event_type"] in event_types
        )

    def _write_document(self, relative: str, document: dict) -> str:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(harness.canonical_json(document) + "\n", encoding="utf-8")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _operation_names(self, state: str, remote: bool, success: bool) -> dict[str, str]:
        outcomes = {name: "skipped" for name in OPERATIONS}
        outcomes.update({"catalog_selection": "completed", "queue": "completed"})
        if not success:
            outcomes["placement"] = "failed"
            return outcomes
        outcomes["first_read"] = "completed"
        if state == "A_materialized_hit":
            return outcomes
        outcomes.update(
            {
                "placement": "completed",
                "materialization": "completed",
                "hash": "completed",
                "artifact_fetch" if remote else "clone": "completed",
            }
        )
        if state == "D_active_a_to_b_reclaim":
            outcomes.update(
                {"drain": "completed", "gpu_release": "completed", "eviction": "completed"}
            )
        return outcomes

    def _build_attempt(self, request: dict) -> dict:
        attempt_id = request["attempt_id"]
        accepted = self._event(attempt_id, {"request.accepted"})
        terminal = self._event(attempt_id, {"response.validated", "attempt.failed"})
        result = self.results[attempt_id]
        state = _state_for(request)
        remote = state == "C_remote_miss_post_t0" or request["scenario"] == "a_to_b_remote"
        success = result["success"]
        target = {**request["target"], "artifact_bytes": ARTIFACT_BYTES}
        flags = {
            "A_materialized_hit": (True, False, False, "materialized_generation"),
            "B_node_seed_post_t0_materialization": (
                False,
                True,
                False,
                "immutable_node_local_seed",
            ),
            "C_remote_miss_post_t0": (
                False,
                False,
                True,
                "immutable_remote_artifact",
            ),
            "D_active_a_to_b_reclaim": (
                False,
                not remote,
                remote,
                "immutable_remote_artifact" if remote else "immutable_node_local_seed",
            ),
        }[state]
        source_available = accepted["observed_monotonic_ns"] - 60_000_000_000
        medium = "object_storage" if remote else "network_ssd"
        rate = float(
            self.manifest["cost_source"][
                "object_storage_usd_per_gib_month"
                if remote
                else "network_ssd_usd_per_gib_month"
            ]
        )
        residency_cost = round(
            ARTIFACT_BYTES / (1024**3) * rate * 60 / (30 * 24 * 60 * 60), 12
        )
        investment = {
            "source_available_monotonic_ns": source_available,
            "source_age_seconds": 60.0,
            "residency_medium": medium,
            "residency_bytes": ARTIFACT_BYTES,
            "residency_rate_usd_per_gib_month": rate,
            "residency_cost_usd": residency_cost,
            "prehydration_bytes": ARTIFACT_BYTES,
            "prehydration_cost_usd": None,
            "prehydration_cost_status": "not-measured-no-live-receipt",
            "price_source_commit": self.manifest["cost_source"]["commit"],
            "included_in_request_totals": False,
        }
        outcomes = self._operation_names(state, remote, success)
        operations = []
        for index, name in enumerate(OPERATIONS, 1):
            outcome = outcomes[name]
            executed = outcome != "skipped"
            byte_fields = {
                "logical_bytes": 0,
                "bytes_read": 0,
                "bytes_written": 0,
                "bytes_network": 0,
                "bytes_deleted": 0,
                "slo_bytes_moved": 0,
            }
            if executed and success and name in {
                "eviction",
                "artifact_fetch",
                "clone",
                "materialization",
                "hash",
                "first_read",
            }:
                byte_fields["logical_bytes"] = ARTIFACT_BYTES
            if executed and success and name == "eviction":
                byte_fields["bytes_deleted"] = ARTIFACT_BYTES
            elif executed and success and name == "artifact_fetch":
                byte_fields["bytes_network"] = ARTIFACT_BYTES
                byte_fields["slo_bytes_moved"] = ARTIFACT_BYTES
            elif executed and success and name == "clone":
                byte_fields["bytes_read"] = ARTIFACT_BYTES
                byte_fields["bytes_written"] = ARTIFACT_BYTES
                byte_fields["slo_bytes_moved"] = ARTIFACT_BYTES
            elif executed and success and name == "materialization":
                byte_fields["bytes_written"] = ARTIFACT_BYTES
            elif executed and success and name in {"hash", "first_read"}:
                byte_fields["bytes_read"] = ARTIFACT_BYTES
            operations.append(
                {
                    "name": name,
                    "outcome": outcome,
                    "started_monotonic_ns": self.global_operation_base + index * 2_000_000
                    if executed
                    else None,
                    "finished_monotonic_ns": self.global_operation_base
                    + index * 2_000_000
                    + 1_000_000
                    if executed
                    else None,
                    **byte_fields,
                    "reason": "synthetic typed operation fixture"
                    if executed
                    else "not required by cache state",
                    "evidence_ref": f"operation-{attempt_id}-{name}" if executed else None,
                }
            )
        totals = {
            "bytes_read_total": sum(item["bytes_read"] for item in operations),
            "bytes_written_total": sum(item["bytes_written"] for item in operations),
            "bytes_network_total": sum(item["bytes_network"] for item in operations),
            "bytes_deleted_total": sum(item["bytes_deleted"] for item in operations),
            "operation_slo_bytes_moved_total": sum(
                item["slo_bytes_moved"] for item in operations
            ),
        }
        dirty = state != "A_materialized_hit"
        cleanup = {
            "generation_id": f"generation-{attempt_id}",
            "generation_uid": f"generation-uid-{attempt_id}",
            "writable_resource_uid": f"uid-provider_volume-{attempt_id}",
            "final_state": "ABSENT" if dirty else "SEALED_RETAINED",
            "dirty": dirty,
            "reusable": not dirty,
            "verified_absent": dirty,
            "evidence_ref": f"cleanup-{attempt_id}",
        }
        attempt = {
            "schema": ATTEMPT_SCHEMA,
            "source_manifest_sha256": harness.canonical_sha256(self.manifest),
            "evidence_classification": "synthetic-contract-smoke-not-performance-evidence",
            "attempt_id": attempt_id,
            "request_id": request["request_id"],
            "cache_state": state,
            "demand_label": {
                "A_materialized_hit": "cache_hit",
                "B_node_seed_post_t0_materialization": "unknown_model_cold_start",
                "C_remote_miss_post_t0": "unknown_model_cold_start",
                "D_active_a_to_b_reclaim": "active_a_to_b_switch",
            }[state],
            "target": target,
            "starting_state": {
                "target_materialized": flags[0],
                "immutable_node_local_seed_present": flags[1],
                "remote_artifact_required": flags[2],
                "target_source": flags[3],
                "active_model": result["current_node_occupant"],
            },
            "request": {
                "t0_boundary": harness.T0_BOUNDARY,
                "accepted_at_utc": accepted["observed_at_utc"],
                "accepted_monotonic_ns": accepted["observed_monotonic_ns"],
                "input_id": request["input"]["input_id"],
                "input_sha256": request["input"]["payload_sha256"],
                "input_bytes": request["input"]["input_bytes"],
            },
            "clock_binding": copy.deepcopy(self.clock),
            "request_slo_binding": {
                "trace_path": self.trace_path.name,
                "ledger_path": self.ledger_path.name,
                "trace_sha256": self.trace_sha,
                "ledger_sha256": self.ledger_sha,
                "trace_id": self.trace["trace_id"],
                "ledger_id": self.ledger_id,
                "request_id": request["request_id"],
                "attempt_id": attempt_id,
            },
            "ownership_binding": {
                "path": f"evidence/{attempt_id}/ownership.json",
                "sha256": "0" * 64,
                "receipt_id": f"ownership-{attempt_id}",
            },
            "pre_t0_investment": investment,
            "operations": operations,
            "accounting": {
                **totals,
                "physical_bytes_total": sum(
                    totals[key]
                    for key in (
                        "bytes_read_total",
                        "bytes_written_total",
                        "bytes_network_total",
                        "bytes_deleted_total",
                    )
                ),
                "request_slo_bytes_moved_total": result["accounting"]["bytes_moved_total"],
                "request_slo_cost_usd": result["accounting"]["cost_usd"],
            },
            "concurrency": {
                "group_id": None,
                "peer_attempt_ids": [],
                "mutable_namespace_id": f"mutable-{attempt_id}",
                "source_read_only": True,
            },
            "terminal": {
                "success": success,
                "failure_class": result["failure_class"],
                "observed_monotonic_ns": terminal["observed_monotonic_ns"],
            },
            "cleanup": cleanup,
            "supporting_evidence": [],
        }
        self._sync_evidence(attempt)
        return attempt

    def _ownership_document(self, attempt: dict) -> dict:
        attempt_id = attempt["attempt_id"]
        source_kind = (
            "object_store_object"
            if attempt["starting_state"]["remote_artifact_required"]
            else "node_seed"
        )
        resources = []
        for raw in self._resources(attempt_id):
            is_source = raw["kind"] == source_kind
            resources.append(
                {
                    **raw,
                    "uid": f"uid-{raw['kind']}-{attempt_id}",
                    "role": "immutable_source" if is_source else "owned_supporting_resource",
                    "artifact_version": attempt["target"]["artifact_version"] if is_source else None,
                    "artifact_sha256": attempt["target"]["artifact_sha256"] if is_source else None,
                    "artifact_bytes": attempt["target"]["artifact_bytes"] if is_source else None,
                }
            )
        source = next(item for item in resources if item["kind"] == source_kind)
        return {
            "schema": OWNERSHIP_SCHEMA,
            "receipt_id": attempt["ownership_binding"]["receipt_id"],
            "attempt_id": attempt_id,
            "owner_task_id": "catalog-switch-storage-cache-matrix",
            "clock_binding": copy.deepcopy(attempt["clock_binding"]),
            "selected_node_id": f"node-{attempt_id}",
            "target": copy.deepcopy(attempt["target"]),
            "source_available_monotonic_ns": attempt["pre_t0_investment"][
                "source_available_monotonic_ns"
            ],
            "source_resource_uid": source["uid"],
            "resources": resources,
            "generation": {
                "generation_id": attempt["cleanup"]["generation_id"],
                "generation_uid": attempt["cleanup"]["generation_uid"],
                "parent_source_uid": source["uid"],
                "writable_resource_uid": attempt["cleanup"]["writable_resource_uid"],
                "mutable_namespace_id": attempt["concurrency"]["mutable_namespace_id"],
            },
            "pre_t0_investment": copy.deepcopy(attempt["pre_t0_investment"]),
        }

    def _sync_evidence(self, attempt: dict) -> None:
        entries = []
        ownership = self._ownership_document(attempt)
        ownership_sha = self._write_document(attempt["ownership_binding"]["path"], ownership)
        attempt["ownership_binding"]["sha256"] = ownership_sha
        entries.append(
            {
                "kind": "ownership",
                "path": attempt["ownership_binding"]["path"],
                "sha256": ownership_sha,
                "receipt_id": attempt["ownership_binding"]["receipt_id"],
            }
        )
        provider_uid = attempt["cleanup"]["writable_resource_uid"]
        for operation in attempt["operations"]:
            if operation["outcome"] == "skipped":
                continue
            receipt_id = operation["evidence_ref"]
            relative = f"evidence/{attempt['attempt_id']}/{operation['name']}.json"
            document = {
                "schema": EVIDENCE_SCHEMA,
                "kind": "operation",
                "receipt_id": receipt_id,
                "attempt_id": attempt["attempt_id"],
                "clock_binding": copy.deepcopy(attempt["clock_binding"]),
                "operation": {key: operation[key] for key in OPERATION_EVIDENCE_KEYS},
                "cleanup": None,
                "resource_uids": [provider_uid],
            }
            digest = self._write_document(relative, document)
            entries.append(
                {"kind": "operation", "path": relative, "sha256": digest, "receipt_id": receipt_id}
            )
        cleanup = attempt["cleanup"]
        cleanup_uids = [
            cleanup["generation_uid"],
            cleanup["writable_resource_uid"],
            f"uid-pvc-{attempt['attempt_id']}",
            f"uid-pv-{attempt['attempt_id']}",
        ]
        relative = f"evidence/{attempt['attempt_id']}/cleanup.json"
        document = {
            "schema": EVIDENCE_SCHEMA,
            "kind": "cleanup",
            "receipt_id": cleanup["evidence_ref"],
            "attempt_id": attempt["attempt_id"],
            "clock_binding": copy.deepcopy(attempt["clock_binding"]),
            "operation": None,
            "cleanup": {key: cleanup[key] for key in CLEANUP_EVIDENCE_KEYS},
            "resource_uids": cleanup_uids,
        }
        digest = self._write_document(relative, document)
        entries.append(
            {
                "kind": "cleanup",
                "path": relative,
                "sha256": digest,
                "receipt_id": cleanup["evidence_ref"],
            }
        )
        attempt["supporting_evidence"] = entries

    def _replace_document(self, attempt: dict, receipt_id: str, document: dict) -> None:
        entry = next(
            item for item in attempt["supporting_evidence"] if item["receipt_id"] == receipt_id
        )
        digest = self._write_document(entry["path"], document)
        entry["sha256"] = digest
        if receipt_id == attempt["ownership_binding"]["receipt_id"]:
            attempt["ownership_binding"]["sha256"] = digest

    def _attempt_for_scenario(self, attempts: list[dict], scenario: str) -> dict:
        attempt_id = next(
            request["attempt_id"]
            for request in self.trace["requests"]
            if request["scenario"] == scenario
        )
        return next(item for item in attempts if item["attempt_id"] == attempt_id)

    def _recompute_operation_accounting(self, attempt: dict) -> None:
        mapping = {
            "bytes_read_total": "bytes_read",
            "bytes_written_total": "bytes_written",
            "bytes_network_total": "bytes_network",
            "bytes_deleted_total": "bytes_deleted",
            "operation_slo_bytes_moved_total": "slo_bytes_moved",
        }
        for total, operation_key in mapping.items():
            attempt["accounting"][total] = sum(
                operation[operation_key] for operation in attempt["operations"]
            )
        attempt["accounting"]["physical_bytes_total"] = sum(
            attempt["accounting"][key]
            for key in (
                "bytes_read_total",
                "bytes_written_total",
                "bytes_network_total",
                "bytes_deleted_total",
            )
        )

    def validate(self, attempts=None):
        return validate_attempts(self.manifest, attempts or self.attempts, self.root)

    def test_complete_ten_attempt_ledger_retains_failures_and_all_states(self) -> None:
        shaped = self.validate()
        self.assertEqual(len(shaped), self.trace["request_count"])
        self.assertEqual(sum(not item["terminal"]["success"] for item in shaped), 2)
        self.assertEqual({item["raw"]["cache_state"] for item in shaped}, {
            "A_materialized_hit",
            "B_node_seed_post_t0_materialization",
            "C_remote_miss_post_t0",
            "D_active_a_to_b_reclaim",
        })

    def test_a_to_b_remote_cannot_be_relabelled_as_node_seed_clone(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempt = self._attempt_for_scenario(attempts, "a_to_b_remote")
        attempt["starting_state"].update(
            {
                "immutable_node_local_seed_present": True,
                "remote_artifact_required": False,
                "target_source": "immutable_node_local_seed",
            }
        )
        investment = attempt["pre_t0_investment"]
        rate = float(self.manifest["cost_source"]["network_ssd_usd_per_gib_month"])
        investment.update(
            {
                "residency_medium": "network_ssd",
                "residency_rate_usd_per_gib_month": rate,
                "residency_cost_usd": round(
                    attempt["target"]["artifact_bytes"]
                    / (1024**3)
                    * rate
                    * investment["source_age_seconds"]
                    / (30 * 24 * 60 * 60),
                    12,
                ),
            }
        )
        fetch = next(
            operation for operation in attempt["operations"] if operation["name"] == "artifact_fetch"
        )
        fetch.update(
            {
                "outcome": "skipped",
                "started_monotonic_ns": None,
                "finished_monotonic_ns": None,
                "logical_bytes": 0,
                "bytes_read": 0,
                "bytes_written": 0,
                "bytes_network": 0,
                "bytes_deleted": 0,
                "slo_bytes_moved": 0,
                "reason": "relabel adversary skips authoritative remote fetch",
                "evidence_ref": None,
            }
        )
        clone_index = OPERATIONS.index("clone") + 1
        clone = next(
            operation for operation in attempt["operations"] if operation["name"] == "clone"
        )
        clone.update(
            {
                "outcome": "completed",
                "started_monotonic_ns": self.global_operation_base + clone_index * 2_000_000,
                "finished_monotonic_ns": self.global_operation_base
                + clone_index * 2_000_000
                + 1_000_000,
                "logical_bytes": ARTIFACT_BYTES,
                "bytes_read": ARTIFACT_BYTES,
                "bytes_written": ARTIFACT_BYTES,
                "bytes_network": 0,
                "bytes_deleted": 0,
                "slo_bytes_moved": ARTIFACT_BYTES,
                "reason": "self-consistent but false node-seed clone adversary",
                "evidence_ref": f"operation-{attempt['attempt_id']}-clone",
            }
        )
        self._recompute_operation_accounting(attempt)
        self._sync_evidence(attempt)
        with self.assertRaisesRegex(
            AnalysisError, "exact SLO scenario/cache contract"
        ):
            self.validate(attempts)

    def test_capacity_failure_cleanup_cannot_be_relabelled_sealed_reusable(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempt = self._attempt_for_scenario(attempts, "capacity_miss")
        attempt["cleanup"].update(
            {
                "final_state": "SEALED_RETAINED",
                "dirty": False,
                "reusable": True,
                "verified_absent": False,
            }
        )
        self._sync_evidence(attempt)
        with self.assertRaisesRegex(
            AnalysisError, "SLO terminal/deleted resource IDs"
        ):
            self.validate(attempts)

    def test_runtime_schema_rejects_empty_cleanup_resource_uids(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempt = self._attempt_for_scenario(attempts, "same_model_hot")
        receipt_id = attempt["cleanup"]["evidence_ref"]
        entry = next(
            item for item in attempt["supporting_evidence"] if item["receipt_id"] == receipt_id
        )
        document = json.loads((self.root / entry["path"]).read_text())
        document["resource_uids"] = []
        self._replace_document(attempt, receipt_id, document)
        with self.assertRaisesRegex(
            AnalysisError, "operation evidence fails checked-in JSON schema"
        ):
            self.validate(attempts)
        document["resource_uids"] = [attempt["cleanup"]["generation_uid"]]
        self._replace_document(attempt, receipt_id, document)
        with self.assertRaisesRegex(
            AnalysisError, "exact generation and writable resource UIDs"
        ):
            self.validate(attempts)

    def test_receipt_coverage_cannot_be_partial_or_success_only(self) -> None:
        with self.assertRaisesRegex(AnalysisError, "cover every SLO attempt/failure"):
            self.validate(self.attempts[:-1])
        successes = [item for item in self.attempts if item["terminal"]["success"]]
        with self.assertRaisesRegex(AnalysisError, "cover every SLO attempt/failure"):
            self.validate(successes)

    def test_storage_clock_must_be_the_exact_external_recorder_clock(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempts[0]["clock_binding"]["clock_id"] = "invented-monotonic-clock"
        self._sync_evidence(attempts[0])
        with self.assertRaisesRegex(AnalysisError, "clock identity differs"):
            self.validate(attempts)

    def test_selected_node_must_join_external_slo_environment(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempt = attempts[0]
        entry = attempt["ownership_binding"]
        document = json.loads((self.root / entry["path"]).read_text())
        document["selected_node_id"] = "invented-selected-node"
        node = next(item for item in document["resources"] if item["kind"] == "node")
        node["id"] = "invented-selected-node"
        self._replace_document(attempt, entry["receipt_id"], document)
        with self.assertRaisesRegex(AnalysisError, "selected node is not joined"):
            self.validate(attempts)

    def test_artifact_size_version_and_digest_are_anchored_to_source_uid(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempt = attempts[0]
        entry = attempt["ownership_binding"]
        document = json.loads((self.root / entry["path"]).read_text())
        source = next(
            item for item in document["resources"] if item["uid"] == document["source_resource_uid"]
        )
        source["artifact_bytes"] += 1
        self._replace_document(attempt, entry["receipt_id"], document)
        with self.assertRaisesRegex(AnalysisError, "size/version/digest"):
            self.validate(attempts)

    def test_source_age_and_pre_t0_cost_are_derived_not_invented(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempts[0]["pre_t0_investment"]["source_age_seconds"] += 1
        self._sync_evidence(attempts[0])
        with self.assertRaisesRegex(AnalysisError, "deterministically derived"):
            self.validate(attempts)

    def test_operation_phase_order_cannot_be_inverted(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        seed = next(
            item for item in attempts if item["cache_state"] == "B_node_seed_post_t0_materialization"
        )
        clone = next(item for item in seed["operations"] if item["name"] == "clone")
        materialize = next(
            item for item in seed["operations"] if item["name"] == "materialization"
        )
        materialize["started_monotonic_ns"] = clone["finished_monotonic_ns"] - 1
        self._sync_evidence(seed)
        with self.assertRaisesRegex(AnalysisError, "operation order is inverted"):
            self.validate(attempts)

    def test_concurrency_requires_true_same_clock_overlap(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        shifted = attempts[4]
        for operation in shifted["operations"]:
            if operation["outcome"] != "skipped":
                operation["started_monotonic_ns"] += 50_000_000
                operation["finished_monotonic_ns"] += 50_000_000
        self._sync_evidence(shifted)
        with self.assertRaisesRegex(AnalysisError, "no true same-clock localization overlap"):
            self.validate(attempts)

    def test_plaintext_or_reused_evidence_cannot_back_operations(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempt = attempts[0]
        entry = next(item for item in attempt["supporting_evidence"] if item["kind"] == "operation")
        path = self.root / entry["path"]
        path.write_text("arbitrary plaintext\n", encoding="utf-8")
        entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(AnalysisError, "is not JSON"):
            self.validate(attempts)

    def test_physical_and_slo_bytes_are_exactly_reconciled(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        seed = next(
            item for item in attempts if item["cache_state"] == "B_node_seed_post_t0_materialization"
        )
        clone = next(item for item in seed["operations"] if item["name"] == "clone")
        clone["bytes_written"] -= 1
        seed["accounting"]["bytes_written_total"] -= 1
        seed["accounting"]["physical_bytes_total"] -= 1
        self._sync_evidence(seed)
        with self.assertRaisesRegex(AnalysisError, "exactly reconcile clone/SLO bytes"):
            self.validate(attempts)

    def test_ownership_requires_pvc_pv_provider_volume_object_and_node_uids(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempt = attempts[0]
        entry = attempt["ownership_binding"]
        document = json.loads((self.root / entry["path"]).read_text())
        document["resources"][-1]["kind"] = "pvc"
        self._replace_document(attempt, entry["receipt_id"], document)
        with self.assertRaisesRegex(AnalysisError, "kind is unknown or duplicated"):
            self.validate(attempts)

    def test_dirty_physical_uid_cannot_be_renamed_and_reused(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        dirty = attempts[1]
        later = attempts[2]
        reused_uid = dirty["cleanup"]["generation_uid"]
        later["cleanup"]["generation_uid"] = reused_uid
        self._sync_evidence(later)
        with self.assertRaisesRegex(AnalysisError, "dirty physical UID was renamed and reused"):
            self.validate(attempts)

    def test_prepared_clone_cannot_be_unknown_model_cold_start(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        seed = next(
            item for item in attempts if item["cache_state"] == "B_node_seed_post_t0_materialization"
        )
        seed["starting_state"].update(
            {
                "target_materialized": True,
                "immutable_node_local_seed_present": False,
                "target_source": "materialized_generation",
            }
        )
        self._sync_evidence(seed)
        with self.assertRaisesRegex(AnalysisError, "prepared clone cannot be labeled"):
            self.validate(attempts)

    def test_b_through_d_preparation_must_be_inside_external_t0(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        seed = next(
            item for item in attempts if item["cache_state"] == "B_node_seed_post_t0_materialization"
        )
        selection = next(
            item for item in seed["operations"] if item["name"] == "catalog_selection"
        )
        selection["started_monotonic_ns"] = seed["request"]["accepted_monotonic_ns"] - 2
        selection["finished_monotonic_ns"] = seed["request"]["accepted_monotonic_ns"] - 1
        self._sync_evidence(seed)
        with self.assertRaisesRegex(AnalysisError, "outside external T0/terminal"):
            self.validate(attempts)

    def test_failure_terminal_cannot_be_omitted_or_relabeled(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        failed = next(item for item in attempts if not item["terminal"]["success"])
        failed["terminal"] = {
            "success": True,
            "failure_class": None,
            "observed_monotonic_ns": failed["terminal"]["observed_monotonic_ns"],
        }
        with self.assertRaisesRegex(
            AnalysisError, "successful SLO attempt contains failed storage operation"
        ):
            self.validate(attempts)

    def test_reviewed_source_commit_is_resolved_and_content_identical(self) -> None:
        result = verify_pinned_sources(
            self.manifest,
            REPO_ROOT,
            TASK_DECK_ROOT if TASK_DECK_ROOT.exists() else None,
        )
        self.assertEqual(result["verified_file_count"], 15)
        self.assertEqual(
            result["reviewed_request_slo_tree"], result["integrated_request_slo_tree"]
        )
        self.assertEqual(result["request_slo_integration"], "content-identical-reviewed-subtree")
        bad = copy.deepcopy(self.manifest)
        bad["request_slo"]["reviewed_commit"] = "0180915001fff47fbed0f82292fe32edc40e40ea"
        with self.assertRaisesRegex(AnalysisError, "request-SLO tree|pinned Git tree"):
            verify_pinned_sources(bad, REPO_ROOT)

    def test_projection_uses_canonical_models_not_scaled_row_duplicate_ceiling(self) -> None:
        result = analyze_capacity(self.manifest, self.config)
        summary = result["catalog_summary"]
        self.assertEqual(summary["pinned_canonical_models"], 171)
        self.assertEqual(summary["planning_models"], 200)
        self.assertEqual(summary["pinned_catalog_rows"], 220)
        self.assertFalse(summary["row_duplicate_high_ceiling_used_in_projection"])
        self.assertEqual(
            summary["row_duplicate_high_ceiling_excluded_bytes"],
            self.manifest["catalog"]["row_storage_high_bytes"],
        )
        self.assertNotIn("row_level_high_ceiling", self.config)

    def test_capacity_math_and_cache_reuse_sensitivity_are_deterministic(self) -> None:
        first = analyze_capacity(self.manifest, self.config)
        self.assertEqual(first, analyze_capacity(self.manifest, self.config))
        self.assertTrue(first["cache_budget_sensitivity"])
        self.assertTrue(first["top_k_reuse_sensitivity"])
        for row in first["request_state_sensitivity"]:
            self.assertAlmostEqual(sum(row["state_probabilities"].values()), 1.0, places=9)
        self.assertEqual(first["simulator_input"]["latency_samples"], [])

    def test_checked_in_summaries_match_v2_source_and_capacity_outputs(self) -> None:
        analysis = analyze_capacity(self.manifest, self.config)
        capacity = _load("results/capacity-summary.json")
        self.assertEqual(capacity["schema"], "archvteams.nebius.ai/catalog-boundary-capacity-summary/v2")
        self.assertEqual(capacity["source_manifest_sha256"], analysis["source_manifest_sha256"])
        self.assertEqual(capacity["analysis_config_sha256"], analysis["analysis_config_sha256"])
        for key in (
            "pinned_catalog_rows",
            "pinned_canonical_models",
            "row_duplicate_high_ceiling_excluded_bytes",
            "row_duplicate_high_ceiling_used_in_projection",
        ):
            self.assertEqual(capacity[key], analysis["catalog_summary"][key])
        source = _load("results/source-verification.json")
        verified = verify_pinned_sources(self.manifest, REPO_ROOT)
        for key in (
            "schema",
            "source_manifest_sha256",
            "verified_file_count",
            "reviewed_request_slo_tree",
            "integrated_request_slo_tree",
            "request_slo_integration",
        ):
            self.assertEqual(source[key], verified[key])

    def test_boltz_observation_remains_prepared_clone_not_external_t0_result(self) -> None:
        result = analyze_capacity(self.manifest, self.config)["boltz_external_tmp"]
        self.assertEqual(result["bytes_per_attempt"], 1_826_220_898)
        self.assertEqual(result["elapsed_seconds_range"], [440, 442])
        self.assertIsNone(result["external_t0_latency_distribution"])

    def test_execution_gate_is_offline_and_local_nvme_is_not_substituted(self) -> None:
        manifest = validate_source_manifest(self.manifest)
        self.assertFalse(manifest["execution_gate"]["live_execution_permitted"])
        self.assertEqual(manifest["execution_gate"]["created_resource_ids"], [])
        self.assertEqual(
            manifest["execution_gate"]["local_nvme"],
            {"status": "unavailable-entitlement-not-proven", "substitution_permitted": False},
        )
        attempts = copy.deepcopy(self.attempts)
        for attempt in attempts:
            attempt["evidence_classification"] = "measured-live-product-slo"
        with self.assertRaisesRegex(AnalysisError, "execution gate is closed"):
            self.validate(attempts)

    def test_attempt_ledger_requires_canonical_complete_json_lines(self) -> None:
        path = self.root / "attempts.jsonl"
        path.write_text(json.dumps(self.attempts[0], indent=2) + "\n")
        with self.assertRaisesRegex(AnalysisError, "invalid JSON|canonical JSON"):
            load_attempts(path)
        path.write_text("".join(harness.canonical_json(item) + "\n" for item in self.attempts))
        self.assertEqual(len(load_attempts(path)), 10)

    def test_all_v2_schemas_are_closed_and_meta_valid(self) -> None:
        self.assertEqual(
            (PACKAGE / "requirements.txt").read_text(encoding="utf-8"),
            "jsonschema==4.10.3\n",
        )
        for name in (
            "source_manifest.schema.json",
            "analysis_config.schema.json",
            "attempt.schema.json",
            "ownership-receipt.schema.json",
            "operation-evidence.schema.json",
        ):
            schema = _load(name)
            jsonschema.Draft202012Validator.check_schema(schema)
            self.assertFalse(schema["additionalProperties"])
            self.assertIn("v2", schema["$id"])


if __name__ == "__main__":
    unittest.main()
