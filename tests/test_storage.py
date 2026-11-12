import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from medkeep.hashing import sha256
from medkeep.records import DecodeError, ValidationError
from medkeep.service import IntegrityError, MedKeepService
from medkeep.storage import MAX_FILE_BYTES, StorageError, WorkspaceBusy, decode_state, encode_state

STAMP = "2026-11-09T14:00:00+01:00"


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.service = MedKeepService(self.directory, clock=lambda: STAMP)

    def tearDown(self):
        self.service.close()
        self.temporary.cleanup()

    def add(self, title="Follow-up", notes="Synthetic notes."):
        return self.service.enqueue("PT-1048", "Clinician 07", "2026-11-09", title, notes)

    def reopen(self):
        self.service.close()
        self.service = MedKeepService(self.directory, clock=lambda: STAMP)

    def test_empty_workspace_and_lease(self):
        self.assertTrue(self.service.verify().ok)
        self.assertFalse(self.service.store.path.exists())
        with self.assertRaises(WorkspaceBusy):
            MedKeepService(self.directory)

    def test_pending_requests_survive_restart_and_keep_order(self):
        self.add("First")
        self.add("Second")
        self.reopen()
        self.assertEqual(self.service.pending_count, 2)
        self.assertEqual(tuple(value.title for value in self.service.pending()), ("First", "Second"))
        self.assertEqual(self.service.process_next().title, "First")
        self.assertEqual(self.service.process_next().title, "Second")
        self.reopen()
        self.assertTrue(self.service.verify().ok)
        self.assertEqual(tuple(value.title for value in self.service.history()), ("Second", "First"))

    def test_verification_gate_and_mutation_invalidation(self):
        with self.assertRaises(IntegrityError):
            self.service.history()
        self.add()
        self.service.process_next()
        with self.assertRaises(IntegrityError):
            self.service.history()
        self.service.verify()
        self.assertEqual(len(self.service.history()), 1)
        self.add("Second")
        self.assertIsNone(self.service.report)

    def test_unicode_roundtrip(self):
        self.add(notes="معاینه بیمار\nFollow-up ✅")
        self.service.process_next()
        self.reopen()
        self.service.verify()
        self.assertEqual(next(iter(self.service.history())).notes, "معاینه بیمار\nFollow-up ✅")

    def test_failed_enqueue_keeps_memory_and_disk(self):
        self.add("First")
        before = self.service.store.path.read_bytes()
        with patch.object(self.service.store, "save", side_effect=StorageError("disk full")):
            with self.assertRaises(StorageError):
                self.add("Second")
        self.assertEqual(self.service.pending_count, 1)
        self.assertEqual(self.service.store.path.read_bytes(), before)
        self.assertEqual(self.add("Second").request_id, 2)

    def test_failed_process_does_not_lose_request(self):
        self.add()
        before = self.service.store.path.read_bytes()
        with patch("medkeep.storage.os.replace", side_effect=PermissionError("blocked")):
            with self.assertRaises(StorageError):
                self.service.process_next()
        self.assertEqual(self.service.pending_count, 1)
        self.assertEqual(self.service.record_count, 0)
        self.assertEqual(self.service.store.path.read_bytes(), before)
        self.assertEqual(tuple(self.directory.glob("*.tmp")), ())

    def test_external_edit_blocks_history_archive_and_writes(self):
        self.add()
        self.service.process_next()
        self.service.verify()
        raw = self.service.store.path.read_bytes()
        self.service.store.path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
        altered = self.service.store.path.read_bytes()
        self.assertFalse(self.service.verify().ok)
        with self.assertRaises(IntegrityError):
            self.service.history()
        with self.assertRaises(IntegrityError):
            self.add("Second")
        with self.assertRaises(IntegrityError):
            self.service.archive("2026-11-09")
        self.assertEqual(self.service.store.path.read_bytes(), altered)

    def test_corrupt_snapshot_is_not_replaced(self):
        self.add()
        path = self.service.store.path
        self.service.close()
        corrupted = b"bad workspace"
        path.write_bytes(corrupted)
        with self.assertRaises(DecodeError):
            MedKeepService(self.directory)
        self.assertEqual(path.read_bytes(), corrupted)
        path.unlink()
        self.service = MedKeepService(self.directory)

    def test_hashes_preserved_on_reload_and_tampering_detected(self):
        self.add()
        self.service.process_next()
        state = decode_state(self.service.store.path.read_bytes())
        inherited = state.chain.tail.link_hash
        state.chain.tail.previous.payload = state.chain.tail.previous.payload.replace(b"Synthetic", b"Malicious")
        altered = encode_state(state)
        self.service.close()
        (self.directory / "medkeep.mkd").write_bytes(altered)
        self.service = MedKeepService(self.directory)
        self.assertEqual(self.service.head_digest, inherited)
        self.assertFalse(self.service.verify().ok)

    def test_checksum_truncation_and_extra_bytes_rejected(self):
        self.add()
        raw = self.service.store.path.read_bytes()
        for altered in (raw[:-1], raw + b"x", b"x" + raw[1:]):
            with self.assertRaises(DecodeError):
                decode_state(altered)

    def test_bounded_counts_and_lengths(self):
        self.add()
        raw = self.service.store.path.read_bytes()
        body = raw[:-32]
        altered = body[:24] + (10000000).to_bytes(8, "big") + body[32:]
        with self.assertRaises(DecodeError):
            decode_state(altered + bytes.fromhex(sha256(altered)))
        with self.assertRaises(DecodeError):
            decode_state(b"x" * (MAX_FILE_BYTES + 1))

    def test_request_numbers_continue_after_restart(self):
        self.assertEqual(self.add().request_id, 1)
        self.service.process_next()
        self.reopen()
        self.assertEqual(self.add().request_id, 2)

    def test_archive_is_verified_nondestructive_and_never_overwritten(self):
        self.add(notes="Line one\nLine two")
        self.service.process_next()
        first = self.service.archive("2026-11-09")
        second = self.service.archive("2026-11-09")
        self.assertNotEqual(first, second)
        output = first.read_text(encoding="utf-8")
        self.assertIn("Verified records: 1", output)
        self.assertIn(self.service.head_digest, output)
        self.assertIn("    Line one\n    Line two", output)
        self.assertEqual(self.service.record_count, 1)
        if os.name != "nt":
            self.assertEqual(first.stat().st_mode & 0o777, 0o600)

    def test_archive_uses_processing_day_not_visit_or_submission_day(self):
        self.add()
        self.service.clock = lambda: "2026-11-10T00:10:00+01:00"
        self.service.process_next()
        with self.assertRaises(ValidationError):
            self.service.archive("2026-11-09")
        path = self.service.archive("2026-11-10")
        self.assertIn("Processed date: 2026-11-10", path.read_text(encoding="utf-8"))

    def test_archive_rejects_empty_day_and_path_injection(self):
        for day in ("../../outside", "2026-02-30", "20261109", "2026-11-09"):
            with self.assertRaises(ValidationError):
                self.service.archive(day)

    def test_process_empty_queue(self):
        with self.assertRaises(IndexError):
            self.service.process_next()


if __name__ == "__main__":
    unittest.main()
