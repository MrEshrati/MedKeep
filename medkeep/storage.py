"""Bounded binary snapshots, exclusive workspace leases and atomic replacement."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

from .chain import CONTENT, SEAL, MAX_NODES, ChainNode, HashChain
from .hashing import sha256
from .records import DecodeError, MedicalRecord, Reader
from .structures import LinkedQueue, LinkedSequence

MAGIC = b"MEDKEEP1"
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_PENDING = 5000


class StorageError(OSError):
    pass


class StorageConflict(StorageError):
    pass


class WorkspaceBusy(StorageError):
    pass


class State:
    def __init__(self) -> None:
        self.chain = HashChain()
        self.queue: LinkedQueue[MedicalRecord] = LinkedQueue()
        self.next_request_id = 1
        self.revision = 0

    def copy(self) -> State:
        result = State()
        result.chain = self.chain.copy()
        result.queue = self.queue.copy()
        result.next_request_id = self.next_request_id
        result.revision = self.revision + 1
        return result

    def validate_queue(self) -> None:
        if len(self.queue) > MAX_PENDING:
            raise DecodeError("The pending queue exceeds its 5,000-request limit.")
        expected = self.chain.record_count + 1
        for record in self.queue:
            if record.request_id != expected or record.recorded_at:
                raise DecodeError("Pending requests have an invalid FIFO sequence or processed timestamp.")
            expected += 1
        if self.next_request_id != expected:
            raise DecodeError("The next request number does not match the saved queue and chain.")


def encode_state(state: State) -> bytes:
    state.validate_queue()
    chunks: LinkedSequence[bytes] = LinkedSequence()
    chunks.append(MAGIC)
    chunks.append(state.revision.to_bytes(8, "big"))
    chunks.append(state.next_request_id.to_bytes(8, "big"))
    chunks.append(state.chain.node_count.to_bytes(8, "big"))
    chunks.append(len(state.queue).to_bytes(8, "big"))
    for node in state.chain.nodes():
        chunks.append(node.index.to_bytes(8, "big"))
        chunks.append(b"C" if node.kind == CONTENT else b"S")
        chunks.append((node.previous.index if node.previous else 0).to_bytes(8, "big"))
        chunks.append(bytes.fromhex(node.link_hash))
        chunks.append(len(node.payload).to_bytes(4, "big") + node.payload)
    for record in state.queue:
        payload = record.to_bytes()
        chunks.append(len(payload).to_bytes(4, "big") + payload)
    # join only assembles raw I/O bytes; the chunks live in our linked sequence.
    body = b"".join(chunks)
    if len(body) + 32 > MAX_FILE_BYTES:
        raise StorageError("The workspace has reached its 32 MiB file limit. Nothing was changed.")
    return body + bytes.fromhex(sha256(body))


def decode_state(data: bytes) -> State:
    if len(data) > MAX_FILE_BYTES or len(data) < 72:
        raise DecodeError("The workspace file has an invalid size.")
    body, checksum = data[:-32], data[-32:]
    if bytes.fromhex(sha256(body)) != checksum:
        raise DecodeError("The workspace checksum does not match. The original file was preserved.")
    reader = Reader(body)
    if reader.take(len(MAGIC)) != MAGIC:
        raise DecodeError("Unknown workspace format or version.")
    state = State()
    state.revision = reader.number()
    state.next_request_id = reader.number()
    node_count, queue_count = reader.number(), reader.number()
    if not 1 <= node_count <= MAX_NODES or queue_count > MAX_PENDING:
        raise DecodeError("The workspace declares too many nodes or pending requests.")
    newer: ChainNode | None = None
    for expected in range(node_count, 0, -1):
        index = reader.number()
        kind = reader.take(1)
        predecessor = reader.number()
        inherited = reader.take(32).hex()
        length = reader.number(4)
        if index != expected or predecessor != expected - 1 or kind not in (b"C", b"S") or length > 30000:
            raise DecodeError("A saved node has invalid metadata or payload size.")
        node = ChainNode(index, CONTENT if kind == b"C" else SEAL, reader.take(length), None, inherited)
        if newer is None:
            state.chain.tail = node
        else:
            newer.previous = node
        newer = node
    state.chain.node_count = node_count
    for _ in range(queue_count):
        length = reader.number(4)
        if length > 30000:
            raise DecodeError("A pending record exceeds the supported length.")
        state.queue.enqueue(MedicalRecord.from_bytes(reader.take(length)))
    reader.finish()
    state.validate_queue()
    # Stored chain hashes are preserved. They are never silently recomputed here.
    return state


class WorkspaceLease:
    """One cooperating process per local workspace, enforced by the OS."""

    def __init__(self, directory: Path) -> None:
        self._file = (directory / ".medkeep.lock").open("a+b")
        self._file.seek(0, os.SEEK_END)
        if self._file.tell() == 0:
            self._file.write(b"\x00")
            self._file.flush()
        self._file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._file.close()
            raise WorkspaceBusy("This workspace is already open in another MedKeep window.") from None

    def close(self) -> None:
        if self._file.closed:
            return
        self._file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()


class WorkspaceStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "medkeep.mkd"
        self._lease = WorkspaceLease(self.directory)
        self._fingerprint: str | None = None

    def close(self) -> None:
        self._lease.close()

    def _read(self) -> bytes:
        with self.path.open("rb") as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise StorageError("The workspace exceeds the 32 MiB supported file size.")
        return data

    def load(self) -> State:
        if not self.path.exists():
            return State()
        data = self._read()
        state = decode_state(data)
        self._fingerprint = data[-32:].hex()
        return state

    def ensure_current(self) -> None:
        if self._fingerprint is None:
            if self.path.exists():
                raise StorageConflict("A workspace appeared on disk. Restart MedKeep before continuing.")
            return
        try:
            data = self._read()
        except OSError:
            raise StorageConflict("The workspace changed or became unavailable. Restart MedKeep before continuing.") from None
        if len(data) < 32 or data[-32:].hex() != self._fingerprint or sha256(data[:-32]) != self._fingerprint:
            raise StorageConflict("The workspace changed outside MedKeep. No files were overwritten; restart to inspect it.")

    def save(self, state: State) -> None:
        self.ensure_current()
        data = encode_state(state)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=self.directory, prefix=".medkeep-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            # Catch external changes made while serialization was running too.
            self.ensure_current()
            os.replace(temporary, self.path)
            self._fingerprint = data[-32:].hex()
        except OSError as error:
            raise StorageError("Could not save the workspace. The previous saved data and pending queue were kept.") from error
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
