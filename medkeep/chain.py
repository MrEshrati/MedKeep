"""The assignment's backward-linked, alternating content/seal chain."""

from __future__ import annotations

from datetime import datetime
from typing import Iterator

from .hashing import sha256
from .records import DecodeError, MedicalRecord
from .structures import LinkedSequence

ZERO_HASH = "0" * 64
CONTENT = "content"
SEAL = "seal"
MAX_NODES = 10000


class ChainNode:
    __slots__ = ("index", "kind", "payload", "previous", "link_hash")

    def __init__(self, index: int, kind: str, payload: bytes,
                 previous: ChainNode | None, link_hash: str) -> None:
        self.index = index
        self.kind = kind
        self.payload = payload
        self.previous = previous
        self.link_hash = link_hash


def digest_node(node: ChainNode) -> str:
    """The NEXT node stores this digest; all boundaries are explicit.

    H(domain || index:u64 || kind:u8 || inherited_hash:32 bytes ||
      payload_length:u64 || payload). Genesis inherits 32 zero bytes.
    """
    return sha256(
        b"MedKeep/node/v1\x00" + node.index.to_bytes(8, "big")
        + (b"C" if node.kind == CONTENT else b"S")
        + bytes.fromhex(node.link_hash)
        + len(node.payload).to_bytes(8, "big") + node.payload
    )


class CheckStep:
    __slots__ = ("index", "kind", "stored", "calculated", "ok")

    def __init__(self, index: int, kind: str, stored: str, calculated: str, ok: bool) -> None:
        self.index, self.kind = index, kind
        self.stored, self.calculated, self.ok = stored, calculated, ok


class VerificationReport:
    def __init__(self) -> None:
        self.ok = False
        self.message = "Not checked."
        self.failure_node: int | None = None
        self.steps: LinkedSequence[CheckStep] = LinkedSequence()
        self.records: LinkedSequence[MedicalRecord] = LinkedSequence()
        self.checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self.ignored_tail_content = False

    def fail(self, message: str, index: int | None = None) -> VerificationReport:
        self.ok = False
        self.message = message
        self.failure_node = index
        # Never expose partially verified record contents after any failure.
        self.records = LinkedSequence()
        return self


class HashChain:
    """Singly linked list: the tail points toward earlier nodes, never forward."""

    def __init__(self) -> None:
        self.tail = ChainNode(1, CONTENT, b"", None, ZERO_HASH)
        self.node_count = 1

    @property
    def record_count(self) -> int:
        return self.node_count // 2

    def nodes(self) -> Iterator[ChainNode]:
        """Bounded traversal also prevents malformed cycles from hanging a reader."""
        current = self.tail
        for _ in range(self.node_count):
            if current is None:
                raise DecodeError("The chain ended before its declared node count.")
            yield current
            current = current.previous
        if current is not None:
            raise DecodeError("The chain contains a cycle or excess nodes.")

    def append(self, record: MedicalRecord) -> None:
        if not record.recorded_at:
            raise ValueError("Only processed requests can enter the record chain.")
        if record.request_id != self.record_count + 1:
            raise ValueError("Records must be appended in request arrival order.")
        if self.node_count + (1 if self.node_count == 1 else 2) > MAX_NODES:
            raise ValueError("This workspace has reached its 5,000-record limit.")
        if self.node_count == 1:
            if self.tail.payload or self.tail.previous is not None or self.tail.link_hash != ZERO_HASH:
                raise ValueError("The initial content node is not empty and valid.")
            content = self.tail
            # Do the work before changing the seed: a hash failure must not leave
            # a half-written first pair behind.
            candidate = ChainNode(1, CONTENT, record.to_bytes(), None, ZERO_HASH)
            seal = ChainNode(2, SEAL, b"", content, digest_node(candidate))
            content.payload = candidate.payload
            self.tail = seal
            self.node_count = 2
        else:
            if self.tail.kind != SEAL or self.node_count % 2:
                raise ValueError("The chain ends in an incomplete record pair.")
            content = ChainNode(self.node_count + 1, CONTENT, record.to_bytes(), self.tail, digest_node(self.tail))
            seal = ChainNode(self.node_count + 2, SEAL, b"", content, digest_node(content))
            self.tail = seal
            self.node_count += 2

    def copy(self) -> HashChain:
        result = HashChain()
        newer: ChainNode | None = None
        for node in self.nodes():
            copied = ChainNode(node.index, node.kind, node.payload, None, node.link_hash)
            if newer is None:
                result.tail = copied
            else:
                newer.previous = copied
            newer = copied
        result.node_count = self.node_count
        return result

    def verify(self) -> VerificationReport:
        report = VerificationReport()
        if not 1 <= self.node_count <= MAX_NODES:
            return report.fail("The declared chain length is invalid.")
        if self.node_count > 1 and self.node_count % 2:
            return report.fail("The newest record is missing its seal; no history was released.", self.node_count)
        current: ChainNode | None = self.tail
        expected = self.node_count
        while expected > 0:
            if current is None or current.index != expected:
                return report.fail("A node reference, position, or chain length is inconsistent.", expected)
            required_kind = CONTENT if expected % 2 else SEAL
            if current.kind != required_kind:
                return report.fail("Content and seal nodes do not alternate correctly.", expected)
            if not isinstance(current.payload, bytes) or len(current.payload) > 30000:
                return report.fail("A node payload has an invalid type or size.", expected)
            if not isinstance(current.link_hash, str) or len(current.link_hash) != 64:
                return report.fail("A stored hash has an invalid length.", expected)
            try:
                if bytes.fromhex(current.link_hash).hex() != current.link_hash:
                    raise ValueError
            except ValueError:
                return report.fail("A stored hash is not canonical lowercase hexadecimal.", expected)
            if expected == 1:
                if current.previous is not None:
                    return report.fail("The first node unexpectedly has a predecessor.", expected)
                calculated = ZERO_HASH
            else:
                if current.previous is None or current.previous.index != expected - 1:
                    return report.fail("A previous-node reference is missing or out of order.", expected)
                try:
                    calculated = digest_node(current.previous)
                except (ValueError, TypeError, OverflowError, AttributeError):
                    return report.fail("A predecessor cannot be hashed because its fields are invalid.", expected - 1)
            matched = current.link_hash == calculated
            report.steps.append(CheckStep(expected, current.kind, current.link_hash, calculated, matched))
            if not matched:
                return report.fail(f"Hash mismatch at node {expected}. History and writes are blocked.", expected)
            if current.kind == CONTENT and not (self.node_count == 1 and current.payload == b""):
                try:
                    record = MedicalRecord.from_bytes(current.payload)
                except (DecodeError, ValueError):
                    return report.fail("A content node contains an invalid record encoding.", expected)
                if not record.recorded_at or record.request_id != (expected + 1) // 2:
                    return report.fail("A record timestamp or FIFO sequence is invalid.", expected)
                report.records.append(record)
            elif current.kind == SEAL and current is self.tail:
                # The latest seal's own content has no successor to protect it.
                # It is deliberately excluded from record extraction, as required.
                report.ignored_tail_content = bool(current.payload)
            current = current.previous
            expected -= 1
        if current is not None:
            return report.fail("Unexpected nodes remain beyond the first node.")
        if len(report.records) != self.record_count:
            return report.fail("The extracted record count does not match the chain.")
        report.ok = True
        report.message = f"Integrity verified. {len(report.records)} record(s), {len(report.steps)} node check(s)."
        return report
