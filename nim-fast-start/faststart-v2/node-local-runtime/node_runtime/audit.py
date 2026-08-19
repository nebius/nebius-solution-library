"""Payload-free hash-chained sidecar for canonical SLO events."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from performance.request_slo.harness import canonical_json


class AuditError(RuntimeError):
    """Audit chain is missing, reordered, altered, or noncanonical."""


class AuditChain:
    def __init__(self, path: Path) -> None:
        self.path = path
        if path.exists() and path.is_symlink():
            raise AuditError("audit path cannot be a symlink")
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        records = self.load() if self.path.exists() else []
        sequence = len(records)
        previous = records[-1]["chain_sha256"] if records else "0" * 64
        event_sha256 = hashlib.sha256(canonical_json(event).encode()).hexdigest()
        payload = {
            "schema": "catalog-switch-node-audit-link/v1",
            "sequence": sequence,
            "event_id": event["event_id"],
            "event_sha256": event_sha256,
            "previous_sha256": previous,
        }
        record = {
            **payload,
            "chain_sha256": hashlib.sha256(canonical_json(payload).encode()).hexdigest(),
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(self.path, flags, 0o600)
        try:
            os.write(fd, (canonical_json(record) + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        return record

    def load(self) -> list[dict[str, Any]]:
        if self.path.is_symlink() or not self.path.is_file():
            raise AuditError("audit chain must be a regular file")
        raw = self.path.read_bytes()
        if not raw or not raw.endswith(b"\n"):
            raise AuditError("audit chain is empty or unterminated")
        records: list[dict[str, Any]] = []
        previous = "0" * 64
        for sequence, line in enumerate(raw.decode("utf-8").splitlines()):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AuditError("audit chain contains invalid JSON") from exc
            if line != canonical_json(record):
                raise AuditError("audit chain contains noncanonical JSON")
            if set(record) != {
                "schema",
                "sequence",
                "event_id",
                "event_sha256",
                "previous_sha256",
                "chain_sha256",
            }:
                raise AuditError("audit chain record has unexpected fields")
            payload = {key: record[key] for key in record if key != "chain_sha256"}
            expected = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
            if (
                record["schema"] != "catalog-switch-node-audit-link/v1"
                or record["sequence"] != sequence
                or record["previous_sha256"] != previous
                or record["chain_sha256"] != expected
            ):
                raise AuditError("audit chain link is missing, reordered, or altered")
            previous = record["chain_sha256"]
            records.append(record)
        return records

    def verify_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        records = self.load()
        if len(records) != len(events):
            raise AuditError("audit chain does not cover every canonical event")
        for record, event in zip(records, events, strict=True):
            digest = hashlib.sha256(canonical_json(event).encode()).hexdigest()
            if record["event_id"] != event["event_id"] or record["event_sha256"] != digest:
                raise AuditError("audit link does not match its canonical event")
        return {
            "record_count": len(records),
            "chain_head": records[-1]["chain_sha256"],
            "complete": True,
        }

    def file_sha256(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()
