"""Durable agent state: hash-chained journal, nonce/fence stores, occupancy lock.

Everything here survives process death:

- ``ReceiptJournal``  append-only JSONL with per-line predecessor hashing and
  fsync, so gaps, reordering, and truncation are detectable (CTL-10 shape).
- ``NonceStore``      one ``O_CREAT|O_EXCL`` file per consumed nonce.  A nonce
  is burned *before* any side effect and stays burned across restarts, so a
  replayed command bundle refuses in a fresh process.
- ``FenceStore``      durable monotonic per-node command fence (CTL-20).  A
  bundle whose fence is not strictly greater than the persisted value refuses,
  which also kills stale-controller replays.
- ``OccupancyLock``   durable single-occupant lock (CTL-19).  A second,
  correctly signed launch refuses while an occupant record exists; the record
  carries owner identity so a foreign process cannot silently take it over,
  and release requires verified-absence evidence upstream.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .errors import Refusal, require


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _refuse_symlink(path: Path) -> None:
    require(not path.is_symlink(), "journal.symlink", f"refusing symlink at {path}")


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_durable(path: Path, data: bytes) -> None:
    """Write a new file durably; refuses to overwrite and refuses symlinks."""
    _refuse_symlink(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_dir(path.parent)


class ReceiptJournal:
    """Append-only, hash-chained, fsync'd JSONL journal of agent receipts."""

    GENESIS = "0" * 64

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        _refuse_symlink(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._sequence, self._head = self._replay()

    def _replay(self) -> tuple[int, str]:
        if not self.path.exists():
            return 0, self.GENESIS
        head = self.GENESIS
        sequence = 0
        text = self.path.read_text(encoding="utf-8")
        require(text == "" or text.endswith("\n"), "journal.tail",
                f"{self.path} does not end with a newline")
        for number, line in enumerate(text.splitlines(), start=1):
            try:
                link = json.loads(line)
            except json.JSONDecodeError as error:
                raise Refusal("journal.parse", f"{self.path} line {number}: {error}") from error
            require(isinstance(link, dict) and set(link) == {"schema", "sequence",
                    "predecessor_sha256", "entry"},
                    "journal.link-keys", f"{self.path} line {number}: malformed link")
            require(link["schema"] == "catalog-switch/nlo-journal-link/v1",
                    "journal.link-schema", f"{self.path} line {number}: wrong schema")
            require(link["sequence"] == number - 1, "journal.link-sequence",
                    f"{self.path} line {number}: sequence gap")
            require(link["predecessor_sha256"] == head, "journal.link-chain",
                    f"{self.path} line {number}: predecessor hash mismatch")
            head = sha256_hex(line.encode("utf-8"))
            sequence = number
        return sequence, head

    @property
    def head(self) -> str:
        return self._head

    @property
    def sequence(self) -> int:
        return self._sequence

    def append(self, entry: dict) -> dict:
        require(isinstance(entry, dict), "journal.entry-shape", "entry must be a dict")
        link = {
            "schema": "catalog-switch/nlo-journal-link/v1",
            "sequence": self._sequence,
            "predecessor_sha256": self._head,
            "entry": entry,
        }
        line = canonical_json(link)
        _refuse_symlink(self.path)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        self._sequence += 1
        self._head = sha256_hex(line.encode("utf-8"))
        return link

    def entries(self) -> list[dict]:
        self._replay()  # re-verify chain from disk before exposing
        if not self.path.exists():
            return []
        return [json.loads(line)["entry"]
                for line in self.path.read_text(encoding="utf-8").splitlines()]


class NonceStore:
    """Durable consume-once nonce burn. Burn precedes every side effect."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        _refuse_symlink(self.directory)

    def burn(self, nonce: str, context: dict) -> None:
        require(isinstance(nonce, str) and len(nonce) == 64, "nonce.shape",
                "nonce must be 64 hex chars")
        path = self.directory / nonce
        try:
            write_durable(path, (canonical_json(context) + "\n").encode("utf-8"))
        except FileExistsError as error:
            raise Refusal("nonce.replay",
                          f"nonce already consumed (survives restart): {nonce}") from error


class FenceStore:
    """Durable strictly-monotonic command fence."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        _refuse_symlink(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def current(self) -> int:
        if not self.path.exists():
            return 0
        value = json.loads(self.path.read_text(encoding="utf-8"))
        require(isinstance(value, dict) and isinstance(value.get("fence"), int),
                "fence.state", f"{self.path} malformed")
        return value["fence"]

    def advance(self, fence: int, context: dict) -> None:
        require(isinstance(fence, int) and not isinstance(fence, bool), "fence.type",
                "fence must be an int")
        current = self.current()
        require(fence > current, "fence.regression",
                f"command fence {fence} is not greater than durable fence {current}")
        tmp = self.path.with_name(self.path.name + ".tmp")
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        write_durable(tmp, (canonical_json({"fence": fence, "context": context}) + "\n")
                      .encode("utf-8"))
        os.replace(tmp, self.path)
        _fsync_dir(self.path.parent)


class OccupancyLock:
    """Durable exclusive-occupancy record for the node's GPU trust epoch."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "occupant.json"

    def acquire(self, switch_uid: str, boot_id: str) -> None:
        record = {
            "schema": "catalog-switch/nlo-occupancy/v1",
            "switch_uid": switch_uid,
            "pid": os.getpid(),
            "boot_id": boot_id,
        }
        try:
            write_durable(self.path, (canonical_json(record) + "\n").encode("utf-8"))
        except FileExistsError as error:
            holder = self.holder()
            raise Refusal("occupancy.held",
                          "node already has an occupant record; a second launch is refused "
                          f"even for a correctly signed command: {holder}") from error

    def holder(self) -> dict | None:
        if not self.path.exists():
            return None
        value = json.loads(self.path.read_text(encoding="utf-8"))
        require(isinstance(value, dict) and value.get("schema") ==
                "catalog-switch/nlo-occupancy/v1", "occupancy.state",
                f"{self.path} malformed")
        return value

    def release(self, switch_uid: str, absence_receipt_sha256: str) -> None:
        holder = self.holder()
        require(holder is not None, "occupancy.not-held", "no occupant record to release")
        require(holder["switch_uid"] == switch_uid, "occupancy.foreign-release",
                f"lock held by {holder['switch_uid']!r}, not {switch_uid!r}")
        require(isinstance(absence_receipt_sha256, str)
                and len(absence_receipt_sha256) == 64,
                "occupancy.release-evidence",
                "release requires the sha256 of a verified-absence receipt")
        release_marker = self.directory / f"released-{switch_uid}.json"
        write_durable(release_marker, (canonical_json({
            "schema": "catalog-switch/nlo-occupancy-release/v1",
            "switch_uid": switch_uid,
            "absence_receipt_sha256": absence_receipt_sha256,
        }) + "\n").encode("utf-8"))
        self.path.unlink()
        _fsync_dir(self.directory)


class IntentJournal:
    """Cleanup intents, written durably *before* each resource is created."""

    def __init__(self, path: Path) -> None:
        self.journal = ReceiptJournal(path)

    def record_intent(self, kind: str, resource_id: str, detail: dict) -> None:
        require(isinstance(kind, str) and len(kind) > 0, "intent.kind", "kind empty")
        require(isinstance(resource_id, str) and len(resource_id) > 0,
                "intent.id", "resource id empty")
        self.journal.append({"intent": "create", "kind": kind,
                             "resource_id": resource_id, "detail": detail})

    def record_outcome(self, resource_id: str, outcome: str, detail: dict) -> None:
        require(outcome in ("deleted-verified", "cleanup-failed", "retained"),
                "intent.outcome", f"unknown cleanup outcome {outcome!r}")
        self.journal.append({"intent": "outcome", "resource_id": resource_id,
                             "outcome": outcome, "detail": detail})

    def open_resources(self) -> list[dict]:
        """Resources with a create intent and no terminal outcome, in order."""
        created: dict[str, dict] = {}
        closed: set[str] = set()
        for entry in self.journal.entries():
            if entry.get("intent") == "create":
                created[entry["resource_id"]] = entry
            elif entry.get("intent") == "outcome":
                if entry["outcome"] in ("deleted-verified", "retained"):
                    closed.add(entry["resource_id"])
                else:
                    closed.discard(entry["resource_id"])
        return [entry for rid, entry in created.items() if rid not in closed]
