from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from typing import Callable

from .chain import VerificationReport
from .records import DecodeError, MedicalRecord, ValidationError, validate_day
from .storage import MAX_PENDING, StorageConflict, State, WorkspaceStore
from .structures import LinkedSequence


class IntegrityError(ValueError):
    pass


def local_timestamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


class MedKeepService:
    def __init__(self, directory: Path, clock: Callable[[], str] = local_timestamp):
        self.store = WorkspaceStore(directory)
        self.clock = clock
        self.report: VerificationReport | None = None
        try:
            self._state = self.store.load()
        except BaseException:
            self.store.close()
            raise

    def close(self):
        self.store.close()

    def pending_count(self):
        return len(self._state.queue)

    pending_count = property(pending_count)

    def record_count(self):
        return self._state.chain.record_count

    record_count = property(record_count)

    def node_count(self):
        return self._state.chain.node_count

    node_count = property(node_count)

    def head_digest(self):
        return self._state.chain.tail.link_hash

    head_digest = property(head_digest)

    def pending(self):
        result: LinkedSequence[MedicalRecord] = LinkedSequence()
        for record in self._state.queue:
            result.append(record)
        return result

    def verify(self):
        try:
            self.store.ensure_current()
            self._state.validate_queue()
        except (StorageConflict, DecodeError) as error:
            self.report = VerificationReport().fail(str(error))
            return self.report
        self.report = self._state.chain.verify()
        return self.report

    def _require_integrity(self):
        report = self.verify()
        if not report.ok:
            raise IntegrityError(report.message)

    def _commit(self, candidate: State):
        self.store.save(candidate)
        self._state = candidate
        self.report = None

    def enqueue(self, patient: str, author: str, visit_date: str, title: str, notes: str):
        request = MedicalRecord(self._state.next_request_id, patient, author, visit_date,
                                title, notes, self.clock())
        if self.pending_count >= MAX_PENDING:
            raise ValidationError("The queue is full (5,000 requests). Process pending requests first.")
        self._require_integrity()
        candidate = self._state.copy()
        candidate.queue.enqueue(request)
        candidate.next_request_id += 1
        self._commit(candidate)
        return request

    def process_next(self):
        if not self.pending_count:
            raise IndexError("There are no pending requests to process.")
        self._require_integrity()
        candidate = self._state.copy()
        processed = candidate.queue.peek().recorded(self.clock())
        candidate.chain.append(processed)
        candidate.queue.dequeue()
        self._commit(candidate)
        return processed

    def history(self):
        if self.report is None or not self.report.ok:
            raise IntegrityError("Verify the chain in Approval before opening record history.")
        self._require_integrity()
        return self.report.records

    def archive(self, day: str):
        validate_day(day)
        self._require_integrity()
        selected: LinkedSequence[MedicalRecord] = LinkedSequence()
        for record in self.report.records:
            if record.recorded_at[:10] == day:
                selected.append(record)
        if not len(selected):
            raise ValidationError("No verified records were processed on this date.")
        chunks: LinkedSequence[str] = LinkedSequence()
        chunks.append("MedKeep daily archive\n")
        chunks.append(f"Processed date: {day}\nExported at: {self.clock()}\n")
        chunks.append(f"Verified records: {len(selected)}\nSnapshot head: {self.head_digest}\n")
        chunks.append("Hash: hand-written SHA-256 / MedKeep paired chain v1\n")
        chunks.append("Order: newest first. This export does not remove records from the workspace.\n")
        for record in selected:
            chunks.append("\n" + "=" * 64 + "\n")
            chunks.append(f"Request: {record.reference}\nPatient reference: {record.patient}\n")
            chunks.append(f"Recorded by: {record.author}\nVisit date: {record.visit_date}\n")
            chunks.append(f"Submitted at: {record.submitted_at}\nProcessed at: {record.recorded_at}\n")
            chunks.append(f"Title: {record.title}\nNotes:\n    " + record.notes.replace("\n", "\n    ") + "\n")
        output = "".join(chunks).encode("utf-8")
        directory = self.store.directory / "archives"
        directory.mkdir(exist_ok=True, mode=0o700)
        timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f")
        destination = directory / f"medkeep-{day}-{timestamp}.txt"
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(output)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            destination.unlink(missing_ok=True)
            raise
        return destination
