from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from node_runtime.cache import (
    CacheError,
    CacheIntegrityError,
    ContentAddressedCache,
    InjectedIngestCrash,
)

from .helpers import ARTIFACT, ARTIFACT_SHA


class ContentCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cache = ContentAddressedCache(self.root / "cache", require_fsverity=False)
        self.source = self.root / "source"
        self.source.write_bytes(ARTIFACT)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_publish_is_digest_named_readonly_and_idempotent(self) -> None:
        first = self.cache.ingest(self.source, ARTIFACT_SHA, expected_size=len(ARTIFACT))
        second = self.cache.ingest(self.source, ARTIFACT_SHA, expected_size=len(ARTIFACT))
        self.assertEqual(first.state, "ingested")
        self.assertEqual(first.bytes_moved, len(ARTIFACT))
        self.assertEqual(second.state, "verified_hit")
        self.assertEqual(second.bytes_moved, 0)
        self.assertEqual(Path(first.path).read_bytes(), ARTIFACT)
        self.assertEqual(os.stat(first.path).st_mode & 0o222, 0)

    def test_wrong_digest_is_quarantined_and_never_published(self) -> None:
        with self.assertRaisesRegex(CacheIntegrityError, "quarantined"):
            self.cache.ingest(self.source, "d" * 64)
        self.assertFalse((self.cache.objects / ("d" * 64)).exists())
        self.assertEqual(len(list(self.cache.quarantine.iterdir())), 1)

    def test_partial_write_crash_stays_incoming_and_is_collected(self) -> None:
        with self.assertRaises(InjectedIngestCrash):
            self.cache.ingest(self.source, ARTIFACT_SHA, crash_after_bytes=1)
        self.assertFalse((self.cache.objects / ARTIFACT_SHA).exists())
        self.assertEqual(len(list(self.cache.incoming.iterdir())), 1)
        self.assertEqual(len(self.cache.collect_orphans()), 1)
        self.assertEqual(list(self.cache.incoming.iterdir()), [])

    def test_use_time_corruption_moves_entry_to_quarantine(self) -> None:
        receipt = self.cache.ingest(self.source, ARTIFACT_SHA)
        payload = Path(receipt.path)
        os.chmod(payload, 0o600)
        payload.write_bytes(b"corrupt")
        with self.assertRaisesRegex(CacheIntegrityError, "use-time"):
            self.cache.verify(ARTIFACT_SHA)
        self.assertFalse((self.cache.objects / ARTIFACT_SHA).exists())

    def test_receipt_symlink_is_refused_and_entry_quarantined(self) -> None:
        receipt = self.cache.ingest(self.source, ARTIFACT_SHA)
        entry = Path(receipt.path).parent
        metadata = entry / "receipt.json"
        os.chmod(entry, 0o700)
        metadata.unlink()
        metadata.symlink_to(self.source)
        with self.assertRaisesRegex(CacheIntegrityError, "receipt is invalid"):
            self.cache.verify(ARTIFACT_SHA)
        self.assertFalse((self.cache.objects / ARTIFACT_SHA).exists())

    def test_receipt_content_mismatch_is_quarantined(self) -> None:
        receipt = self.cache.ingest(self.source, ARTIFACT_SHA)
        entry = Path(receipt.path).parent
        metadata = entry / "receipt.json"
        os.chmod(entry, 0o700)
        os.chmod(metadata, 0o600)
        metadata.write_text("{}\n", encoding="utf-8")
        os.chmod(metadata, 0o400)
        with self.assertRaisesRegex(CacheIntegrityError, "does not bind"):
            self.cache.verify(ARTIFACT_SHA)
        self.assertFalse((self.cache.objects / ARTIFACT_SHA).exists())

    def test_cache_root_with_symlink_component_is_refused(self) -> None:
        destination = self.root / "real-cache"
        destination.mkdir()
        alias = self.root / "cache-alias"
        alias.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(CacheError, "not a real directory"):
            ContentAddressedCache(alias / "child", require_fsverity=False)

    def test_symlink_source_and_unavailable_fsverity_fail_closed(self) -> None:
        link = self.root / "link"
        link.symlink_to(self.source)
        with self.assertRaises(CacheError):
            self.cache.ingest(link, ARTIFACT_SHA)
        live = ContentAddressedCache(self.root / "live-cache", require_fsverity=True)
        with self.assertRaisesRegex(CacheError, "fs-verity"):
            live.ingest(self.source, ARTIFACT_SHA)


if __name__ == "__main__":
    unittest.main()
