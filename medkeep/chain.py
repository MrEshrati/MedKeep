from __future__ import annotations

from datetime import datetime

from .hashing import sha256
from .records import DecodeError, MedicalRecord
from .structures import LinkedSequence

ZERO_HASH = "0" * 64
CONTENT = "content"
SEAL = "seal"
MAX_NODES = 10000


class ChainNode:
    __slots__ = ("index", "kind", "payload", "previous", "link_hash")

    def __init__(self, index=1, kind=CONTENT, payload=b"", previous=None, link_hash=ZERO_HASH):
        self.index = index
        self.kind = kind
        self.payload = payload
        self.previous = previous
        self.link_hash = link_hash


def digest_node(node: ChainNode):
    data = b"MedKeep/node/v1\x00"
    data += node.index.to_bytes(8, "big")
    if node.kind == CONTENT:
        data += b"C"
    else:
        data += b"S"
    data += bytes.fromhex(node.link_hash)
    data += len(node.payload).to_bytes(8, "big")
    data += node.payload
    return sha256(data)


class CheckStep:
    __slots__ = ("index", "kind", "stored", "calculated", "ok")

    def __init__(self, index: int, kind: str, stored: str, calculated: str, ok: bool):
        self.index = index
        self.kind = kind
        self.stored = stored
        self.calculated = calculated
        self.ok = ok


class VerificationReport:
    def __init__(self):
        self.ok = False
        self.message = "Not checked."
        self.failure_node: int | None = None
        self.steps: LinkedSequence[CheckStep] = LinkedSequence()
        self.records: LinkedSequence[MedicalRecord] = LinkedSequence()
        self.checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self.ignored_tail_content = False

    def fail(self, message: str, index: int | None = None):
        self.ok = False
        self.message = message
        self.failure_node = index
        self.records = LinkedSequence()
        return self


class HashChain:
    def __init__(self):
        self.tail = ChainNode()
        self.node_count = 1

    def record_count(self):
        return self.node_count // 2

    record_count = property(record_count)

    def nodes(self):
        current = self.tail
        for _ in range(self.node_count):
            if current is None:
                raise DecodeError("The chain ended before its declared node count.")
            yield current
            current = current.previous
        if current is not None:
            raise DecodeError("The chain contains a cycle or excess nodes.")

    def append(self, record: MedicalRecord):
        if not record.recorded_at:
            raise ValueError("Only processed requests can enter the record chain.")
        if record.request_id != self.record_count + 1:
            raise ValueError("Records must be appended in request arrival order.")
        first_record = self.node_count == 1
        nodes_to_add = 1 if first_record else 2
        if self.node_count + nodes_to_add > MAX_NODES:
            raise ValueError("This workspace has reached its 5,000-record limit.")
        if first_record:
            if self.tail.payload or self.tail.previous is not None or self.tail.link_hash != ZERO_HASH:
                raise ValueError("The initial content node is not empty and valid.")
        elif self.tail.kind != SEAL or self.node_count % 2:
            raise ValueError("The chain ends in an incomplete record pair.")

        new_content = ChainNode()
        new_content.payload = record.to_bytes()
        if not first_record:
            new_content.index = self.node_count + 1
            new_content.previous = self.tail
            new_content.link_hash = digest_node(self.tail)

        new_seal = ChainNode()
        new_seal.index = new_content.index + 1
        new_seal.kind = SEAL
        new_seal.link_hash = digest_node(new_content)

        if first_record:
            self.tail.payload = new_content.payload
            new_content = self.tail
        new_seal.previous = new_content
        self.tail = new_seal
        self.node_count += nodes_to_add

    def copy(self):
        copied_chain = HashChain()
        newer_node = None
        for node in self.nodes():
            new_node = ChainNode()
            new_node.index = node.index
            new_node.kind = node.kind
            new_node.payload = node.payload
            new_node.link_hash = node.link_hash
            if newer_node is None:
                copied_chain.tail = new_node
            else:
                newer_node.previous = new_node
            newer_node = new_node
        copied_chain.node_count = self.node_count
        return copied_chain

    def verify(self):
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
