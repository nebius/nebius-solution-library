"""Fail-closed, identity-bound cleanup (CTL-05 shape).

Rules, all enforced structurally:

- an intent is journaled durably *before* each resource is created, so every
  crash window is covered and ``recover`` can replay it;
- cleanup acts only on resource ids read back from this run's own intent
  journal, and every id must carry the task-owned ``nlo-`` prefix — foreign
  or free-form ids are refused, never "proven absent";
- deletion is only recorded after a positive per-id absence proof from the
  runtime authority;
- failures are persisted to the journal *and* re-raised; there is no code
  path that swallows a cleanup exception;
- the occupancy lock is released only after every open resource reached
  ``deleted-verified`` or an explicit ``retained`` decision.
"""

from __future__ import annotations

from .errors import Refusal, require
from .journal import IntentJournal, canonical_json, sha256_hex
from .oci import CtrAdapter

RETAINABLE_KINDS = ("evidence-file",)


class CleanupManager:
    def __init__(self, intents: IntentJournal, adapter: CtrAdapter,
                 resource_prefix: str) -> None:
        self.intents = intents
        self.adapter = adapter
        self.resource_prefix = resource_prefix

    def register(self, kind: str, resource_id: str, detail: dict) -> None:
        require(resource_id.startswith("nlo-"), "cleanup.prefix",
                f"resource id {resource_id!r} lacks the task-owned nlo- prefix")
        self.intents.record_intent(kind, resource_id, detail)

    def _cleanup_container(self, entry: dict) -> dict:
        container_id = entry["resource_id"]
        detail = entry["detail"]
        try:
            task = self.adapter.task_row(container_id)
        except Refusal as error:
            if error.code != "oci.task-missing":
                raise
            task = None
        if task is not None:
            self.adapter.stop(container_id, task["pid"],
                              term_wait_s=detail.get("term_wait_s", 30.0),
                              kill_wait_s=detail.get("kill_wait_s", 15.0))
        absence = self.adapter.remove(container_id)
        return absence

    def cleanup_all(self) -> dict:
        """Tear down every open resource; persist and re-raise any failure."""
        outcomes: list[dict] = []
        failures: list[dict] = []
        for entry in reversed(self.intents.open_resources()):
            resource_id = entry["resource_id"]
            require(resource_id.startswith("nlo-"), "cleanup.journal-prefix",
                    f"journaled resource id {resource_id!r} lacks nlo- prefix; "
                    "refusing to act on foreign state")
            kind = entry["kind"]
            try:
                if kind == "container":
                    proof = self._cleanup_container(entry)
                    self.intents.record_outcome(resource_id, "deleted-verified",
                                                {"proof": proof})
                    outcomes.append({"resource_id": resource_id, "kind": kind,
                                     "outcome": "deleted-verified", "proof": proof})
                elif kind in RETAINABLE_KINDS:
                    self.intents.record_outcome(resource_id, "retained",
                                                {"reason": "raw evidence is retained "
                                                           "by design"})
                    outcomes.append({"resource_id": resource_id, "kind": kind,
                                     "outcome": "retained"})
                else:
                    raise Refusal("cleanup.unknown-kind",
                                  f"no cleanup handler for resource kind {kind!r}")
            except Exception as error:
                record = {"resource_id": resource_id, "kind": kind,
                          "outcome": "cleanup-failed", "error": repr(error)}
                self.intents.record_outcome(resource_id, "cleanup-failed",
                                            {"error": repr(error)})
                failures.append(record)
                outcomes.append(record)
        report = {"outcomes": outcomes, "failures": failures,
                  "complete": len(failures) == 0}
        report["report_sha256"] = sha256_hex(canonical_json(
            {k: v for k, v in report.items() if k != "report_sha256"}).encode("utf-8"))
        if failures:
            raise CleanupFailed(report)
        return report


class CleanupFailed(Refusal):
    def __init__(self, report: dict) -> None:
        self.report = report
        super().__init__("cleanup.failed",
                         f"{len(report['failures'])} resource(s) failed cleanup; "
                         "failures are persisted in the intent journal and the node "
                         "must be treated as quarantined")
