"""Fail-closed content-addressed artifact cache.

The cache has one writer, publishes only complete digest-named directories,
never follows symlinks, and verifies content again at use time. Live use must
set ``require_fsverity=True``; the portable CPU test path records the weaker
read-only-plus-full-rehash seal explicitly and is not performance evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO


DIGEST = re.compile(r"^[0-9a-f]{64}$")
COPY_CHUNK = 1024 * 1024


class CacheError(RuntimeError):
    """Base cache error."""


class CacheIntegrityError(CacheError):
    """Artifact bytes or immutable metadata failed verification."""


class InjectedIngestCrash(CacheError):
    """Deterministic partial-write crash used by the adversary suite."""


@dataclass(frozen=True)
class CacheReceipt:
    digest: str
    size_bytes: int
    path: str
    seal: str
    state: str
    bytes_moved: int


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _validate_digest(value: str) -> str:
    if DIGEST.fullmatch(value) is None:
        raise CacheError("artifact digest must be 64 lowercase hex characters")
    return value


def _ensure_real_directory(path: Path, mode: int = 0o700) -> None:
    _reject_symlink_components(path)
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    _reject_symlink_components(path)


def _reject_symlink_components(path: Path) -> None:
    current = path
    while True:
        try:
            details = os.lstat(current)
        except FileNotFoundError:
            pass
        else:
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
                raise CacheError(f"cache path is not a real directory: {current}")
        if current.parent == current:
            break
        current = current.parent


def _open_regular_nofollow(path: Path) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise CacheError(f"cannot open artifact without following links: {type(exc).__name__}") from exc
    details = os.fstat(fd)
    if not stat.S_ISREG(details.st_mode):
        os.close(fd)
        raise CacheError("artifact source must be a regular file")
    return fd, details


def _hash_stream(stream: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    while chunk := stream.read(COPY_CHUNK):
        digest.update(chunk)
        total += len(chunk)
    return digest.hexdigest(), total


class ContentAddressedCache:
    """A single-writer immutable cache rooted at a task-owned directory."""

    def __init__(self, root: Path, *, require_fsverity: bool) -> None:
        self.root = root.absolute()
        self.require_fsverity = require_fsverity
        self.objects = self.root / "sha256"
        self.incoming = self.root / ".incoming"
        self.quarantine = self.root / "quarantine"
        for directory in (self.root, self.objects, self.incoming, self.quarantine):
            _ensure_real_directory(directory)
        os.chmod(self.root, 0o700)

    def _entry(self, digest: str) -> Path:
        return self.objects / _validate_digest(digest)

    @staticmethod
    def _fsverity_enabled(path: Path) -> bool:
        binary = shutil.which("fsverity")
        if binary is None:
            return False
        result = subprocess.run(
            [binary, "measure", str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        return result.returncode == 0

    @staticmethod
    def _enable_fsverity(path: Path) -> bool:
        binary = shutil.which("fsverity")
        if binary is None:
            return False
        result = subprocess.run(
            [binary, "enable", str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )
        return result.returncode == 0 and ContentAddressedCache._fsverity_enabled(path)

    def _quarantine_path(self, digest: str, observed: str) -> Path:
        fd, raw = tempfile.mkstemp(prefix=f"{digest}.{observed}.", dir=self.quarantine)
        os.close(fd)
        path = Path(raw)
        path.unlink()
        return path

    def _quarantine_entry(self, entry: Path, digest: str, observed: str) -> Path:
        quarantine = self._quarantine_path(digest, observed)
        os.chmod(entry, 0o700)
        os.replace(entry, quarantine)
        return quarantine

    def ingest(
        self,
        source: Path,
        expected_digest: str,
        *,
        expected_size: int | None = None,
        crash_after_bytes: int | None = None,
    ) -> CacheReceipt:
        """Hash, optionally fs-verity-seal, and atomically publish one file."""

        expected_digest = _validate_digest(expected_digest)
        existing = self._entry(expected_digest)
        if existing.is_symlink():
            raise CacheIntegrityError("digest path is a symlink")
        if existing.exists():
            receipt = self.verify(expected_digest, expected_size=expected_size)
            return CacheReceipt(**{**asdict(receipt), "state": "verified_hit", "bytes_moved": 0})

        source_fd, source_stat = _open_regular_nofollow(source)
        if expected_size is not None and source_stat.st_size != expected_size:
            os.close(source_fd)
            raise CacheIntegrityError("artifact source size differs from the pinned size")
        temp_fd, temp_name = tempfile.mkstemp(prefix=f"{expected_digest}.", dir=self.incoming)
        temp_path = Path(temp_name)
        digest = hashlib.sha256()
        copied = 0
        crashed = False
        try:
            with os.fdopen(source_fd, "rb", closefd=True) as src, os.fdopen(
                temp_fd, "wb", closefd=True
            ) as destination:
                while chunk := src.read(COPY_CHUNK):
                    destination.write(chunk)
                    digest.update(chunk)
                    copied += len(chunk)
                    if crash_after_bytes is not None and copied >= crash_after_bytes:
                        destination.flush()
                        os.fsync(destination.fileno())
                        crashed = True
                        raise InjectedIngestCrash("injected crash left only an unpublished temp file")
                destination.flush()
                os.fsync(destination.fileno())
        except InjectedIngestCrash:
            raise
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        finally:
            if not crashed and temp_path.exists() and copied == 0:
                temp_path.unlink(missing_ok=True)

        observed = digest.hexdigest()
        if observed != expected_digest or (expected_size is not None and copied != expected_size):
            quarantine = self._quarantine_path(expected_digest, observed)
            os.replace(temp_path, quarantine)
            os.chmod(quarantine, 0o400)
            raise CacheIntegrityError(f"artifact digest mismatch; quarantined as {quarantine.name}")

        staging = Path(tempfile.mkdtemp(prefix=f"{expected_digest}.", dir=self.incoming))
        payload = staging / "payload"
        metadata = staging / "receipt.json"
        try:
            os.replace(temp_path, payload)
            seal = "fs-verity" if self._enable_fsverity(payload) else "readonly-full-rehash"
            if self.require_fsverity and seal != "fs-verity":
                raise CacheError("live cache requires fs-verity but the filesystem/tool did not enable it")
            metadata.write_bytes(
                _canonical(
                    {
                        "schema": "catalog-switch-content-cache-entry/v1",
                        "sha256": expected_digest,
                        "size_bytes": copied,
                        "seal": seal,
                    }
                )
            )
            with metadata.open("rb") as handle:
                os.fsync(handle.fileno())
            os.chmod(payload, 0o400)
            os.chmod(metadata, 0o400)
            try:
                os.replace(staging, existing)
            except OSError:
                if not existing.exists():
                    raise
                os.chmod(staging, 0o700)
                shutil.rmtree(staging)
            else:
                os.chmod(existing, 0o500)
            directory_fd = os.open(self.objects, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            if staging.exists():
                os.chmod(staging, 0o700)
                shutil.rmtree(staging, ignore_errors=True)
            temp_path.unlink(missing_ok=True)
            raise
        receipt = self.verify(expected_digest, expected_size=expected_size)
        return CacheReceipt(**{**asdict(receipt), "state": "ingested", "bytes_moved": copied})

    def verify(self, digest: str, *, expected_size: int | None = None) -> CacheReceipt:
        digest = _validate_digest(digest)
        entry = self._entry(digest)
        if entry.is_symlink() or not entry.is_dir():
            raise CacheIntegrityError("cache entry is missing or is not a real directory")
        payload = entry / "payload"
        metadata = entry / "receipt.json"
        try:
            fd, details = _open_regular_nofollow(payload)
        except CacheError as exc:
            quarantine = self._quarantine_entry(entry, digest, "invalid-payload")
            raise CacheIntegrityError(
                f"cached payload is invalid; quarantined as {quarantine.name}"
            ) from exc
        with os.fdopen(fd, "rb", closefd=True) as stream:
            observed, size = _hash_stream(stream)
        if observed != digest or (expected_size is not None and size != expected_size):
            quarantine = self._quarantine_entry(entry, digest, observed)
            raise CacheIntegrityError(f"cached artifact failed use-time verification: {quarantine.name}")
        if details.st_mode & 0o222:
            quarantine = self._quarantine_entry(entry, digest, "writable-payload")
            raise CacheIntegrityError(
                f"cached payload is writable; quarantined as {quarantine.name}"
            )
        try:
            metadata_fd, metadata_details = _open_regular_nofollow(metadata)
            with os.fdopen(metadata_fd, "rb", closefd=True) as handle:
                receipt = json.loads(handle.read().decode("utf-8"))
            if metadata_details.st_mode & 0o222:
                raise CacheIntegrityError("cache receipt is writable")
        except (CacheError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            quarantine = self._quarantine_entry(entry, digest, "invalid-receipt")
            raise CacheIntegrityError(
                f"cache receipt is invalid; quarantined as {quarantine.name}"
            ) from exc
        expected = {
            "schema": "catalog-switch-content-cache-entry/v1",
            "sha256": digest,
            "size_bytes": size,
            "seal": receipt.get("seal"),
        }
        if receipt != expected or receipt["seal"] not in {"fs-verity", "readonly-full-rehash"}:
            quarantine = self._quarantine_entry(entry, digest, "mismatched-receipt")
            raise CacheIntegrityError(
                f"cache receipt does not bind the artifact; quarantined as {quarantine.name}"
            )
        if self.require_fsverity and (
            receipt["seal"] != "fs-verity" or not self._fsverity_enabled(payload)
        ):
            quarantine = self._quarantine_entry(entry, digest, "missing-fsverity")
            raise CacheIntegrityError(
                f"live cached artifact lacks enforced fs-verity; quarantined as {quarantine.name}"
            )
        return CacheReceipt(
            digest=digest,
            size_bytes=size,
            path=str(payload),
            seal=receipt["seal"],
            state="verified_hit",
            bytes_moved=0,
        )

    def collect_orphans(self) -> list[str]:
        """Remove only unpublished objects in this cache's incoming directory."""

        removed: list[str] = []
        for path in sorted(self.incoming.iterdir(), key=lambda item: item.name):
            if path.is_symlink():
                path.unlink()
            elif path.is_dir():
                os.chmod(path, 0o700)
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append(path.name)
        return removed
