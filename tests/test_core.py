"""Published SHA-256 vectors plus data-structure and chain regressions."""

import unittest

from medkeep.chain import CONTENT, HashChain, digest_node
from medkeep.hashing import HandmadeSHA256, sha256
from medkeep.records import DecodeError, MedicalRecord, ValidationError
from medkeep.structures import LinkedQueue, LinkedSequence

STAMP = "2026-11-09T14:00:00+01:00"


def record(number=1, notes="Follow-up recorded.", processed=True):
    return MedicalRecord(number, "PT-1048", "Clinician 07", "2026-11-09",
                         "Follow-up", notes, STAMP, STAMP if processed else "")


class HashTests(unittest.TestCase):
    def test_published_vectors(self):
        vectors = (
            (b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
            (b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
            (b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq", "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"),
            (b"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu", "cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1"),
        )
        for message, expected in vectors:
            with self.subTest(length=len(message)):
                self.assertEqual(sha256(message), expected)

    def test_million_a_vector(self):
        self.assertEqual(sha256(b"a" * 1000000), "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0")

    def test_incremental_padding_boundaries(self):
        for length in (0, 1, 55, 56, 63, 64, 65, 119, 120, 127, 128, 129, 1000):
            message = bytes(index % 256 for index in range(length))
            for chunk_size in (1, 7, 63, 64, 65):
                with self.subTest(length=length, chunk=chunk_size):
                    digest = HandmadeSHA256()
                    for offset in range(0, length, chunk_size):
                        digest.update(message[offset:offset + chunk_size])
                    self.assertEqual(digest.hexdigest(), sha256(message))
                    self.assertEqual(digest.hexdigest(), digest.hexdigest())

    def test_digest_does_not_finalize_original(self):
        digest = HandmadeSHA256(b"a")
        digest.hexdigest()
        digest.update(b"bc")
        self.assertEqual(digest.hexdigest(), sha256(b"abc"))

    def test_copy_is_independent(self):
        original = HandmadeSHA256(b"ab")
        copied = original.copy().update(b"c")
        self.assertEqual(copied.hexdigest(), sha256(b"abc"))
        self.assertEqual(original.hexdigest(), sha256(b"ab"))

    def test_text_requires_explicit_encoding(self):
        with self.assertRaises(TypeError):
            sha256("abc")


class ContainerTests(unittest.TestCase):
    def test_empty_queue(self):
        queue = LinkedQueue()
        self.assertEqual(len(queue), 0)
        with self.assertRaises(IndexError):
            queue.peek()
        with self.assertRaises(IndexError):
            queue.dequeue()

    def test_fifo_and_refill(self):
        queue = LinkedQueue()
        for number in range(100):
            queue.enqueue(number)
        for number in range(100):
            self.assertEqual(queue.peek(), number)
            self.assertEqual(queue.dequeue(), number)
        self.assertIsNone(queue._front)
        self.assertIsNone(queue._rear)
        queue.enqueue(200)
        self.assertEqual(queue.dequeue(), 200)

    def test_queue_copy(self):
        queue = LinkedQueue()
        queue.enqueue(1)
        copied = queue.copy()
        copied.enqueue(2)
        self.assertEqual(len(queue), 1)
        self.assertEqual(tuple(copied), (1, 2))

    def test_sequence(self):
        sequence = LinkedSequence()
        self.assertEqual(tuple(sequence), ())
        sequence.append("a")
        sequence.append("b")
        self.assertEqual(len(sequence), 2)
        self.assertEqual(tuple(sequence), ("a", "b"))


class RecordTests(unittest.TestCase):
    def test_unicode_round_trip_and_boundaries(self):
        value = record(notes="یادداشت بیمار\nFollow-up: ✅\tend")
        self.assertEqual(MedicalRecord.from_bytes(value.to_bytes()).notes, value.notes)
        self.assertNotEqual(record(notes="a|bc").to_bytes(), record(notes="ab|c").to_bytes())

    def test_immutable(self):
        with self.assertRaises(AttributeError):
            record().notes = "changed"

    def test_reject_invalid_fields(self):
        for patient, day, notes in (("", "2026-11-09", "notes"), ("P1", "2026-02-30", "notes"), ("P1", "20261109", "notes"), ("P1", "2026-11-09", "\x00")):
            with self.subTest(patient=patient, day=day):
                with self.assertRaises(ValidationError):
                    MedicalRecord(1, patient, "Doctor", day, "Title", notes, STAMP)

    def test_reject_truncated_extra_and_noncanonical_bytes(self):
        raw = record().to_bytes()
        for invalid in (raw[:-1], raw + b"x", b"BAD!" + raw[4:]):
            with self.assertRaises(DecodeError):
                MedicalRecord.from_bytes(invalid)


class ChainTests(unittest.TestCase):
    def test_empty_seed(self):
        chain = HashChain()
        self.assertEqual(chain.node_count, 1)
        self.assertTrue(chain.verify().ok)
        self.assertEqual(len(chain.verify().records), 0)

    def test_pairs_and_reverse_extraction(self):
        chain = HashChain()
        for number in range(1, 4):
            chain.append(record(number))
        self.assertEqual(chain.node_count, 6)
        self.assertEqual(tuple(node.kind for node in chain.nodes()), ("seal", "content", "seal", "content", "seal", "content"))
        report = chain.verify()
        self.assertTrue(report.ok, report.message)
        self.assertEqual(tuple(value.request_id for value in report.records), (3, 2, 1))
        self.assertEqual(len(report.steps), 6)

    def test_content_tamper_blocks_all_records(self):
        chain = HashChain()
        chain.append(record())
        chain.tail.previous.payload = record(notes="Changed").to_bytes()
        report = chain.verify()
        self.assertFalse(report.ok)
        self.assertEqual(report.failure_node, 2)
        self.assertEqual(len(report.records), 0)

    def test_hash_tamper_and_seal_tamper(self):
        chain = HashChain()
        chain.append(record())
        chain.append(record(2))
        chain.tail.previous.previous.payload = b"altered older seal"
        self.assertFalse(chain.verify().ok)
        chain.tail.previous.previous.payload = b""
        chain.tail.link_hash = "f" * 64
        self.assertFalse(chain.verify().ok)

    def test_latest_seal_content_is_ignored_but_next_record_protects_it(self):
        chain = HashChain()
        chain.append(record())
        chain.tail.payload = b"unprotected tail content"
        self.assertTrue(chain.verify().ok)
        self.assertTrue(chain.verify().ignored_tail_content)
        chain.append(record(2))
        self.assertTrue(chain.verify().ok)
        chain.tail.previous.previous.payload = b"later changed"
        self.assertFalse(chain.verify().ok)

    def test_cycle_missing_link_and_incomplete_pair(self):
        chain = HashChain()
        chain.append(record())
        chain.tail.previous.previous = chain.tail
        self.assertFalse(chain.verify().ok)
        chain.tail.previous.previous = None
        chain.tail.previous = None
        self.assertFalse(chain.verify().ok)
        chain = HashChain()
        chain.append(record())
        chain.tail = chain.tail.previous
        chain.node_count = 1
        self.assertFalse(chain.verify().ok)

    def test_genesis_hash_and_kind_are_checked(self):
        chain = HashChain()
        chain.tail.link_hash = "f" * 64
        self.assertFalse(chain.verify().ok)
        chain.tail.link_hash = "0" * 64
        chain.tail.kind = "seal"
        self.assertFalse(chain.verify().ok)

    def test_copy_and_fifo_enforcement(self):
        chain = HashChain()
        chain.append(record())
        copied = chain.copy()
        copied.append(record(2))
        self.assertEqual(chain.record_count, 1)
        self.assertEqual(copied.record_count, 2)
        with self.assertRaises(ValueError):
            chain.append(record(3))
        with self.assertRaises(ValueError):
            chain.append(record(2, processed=False))


if __name__ == "__main__":
    unittest.main()
