"""Validated record values and an explicit length-prefixed binary encoding."""

from __future__ import annotations

from datetime import date, datetime


class ValidationError(ValueError):
    pass


class DecodeError(ValueError):
    pass


def encode_text(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return len(encoded).to_bytes(4, "big") + encoded


class Reader:
    """A bounded cursor over immutable bytes, not an object deserializer."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def take(self, size: int) -> bytes:
        if size < 0 or self.offset + size > len(self.data):
            raise DecodeError("The workspace is truncated or has an invalid field length.")
        value = self.data[self.offset:self.offset + size]
        self.offset += size
        return value

    def number(self, size: int = 8) -> int:
        return int.from_bytes(self.take(size), "big")

    def text(self, maximum: int) -> str:
        size = self.number(4)
        if size > maximum * 4:
            raise DecodeError("A text field exceeds the supported length.")
        try:
            value = self.take(size).decode("utf-8")
        except UnicodeDecodeError as error:
            raise DecodeError("A text field contains invalid UTF-8.") from error
        if len(value) > maximum:
            raise DecodeError("A text field exceeds the supported length.")
        return value

    def finish(self) -> None:
        if self.offset != len(self.data):
            raise DecodeError("The workspace contains unexpected trailing data.")


def validate_day(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
    except (ValueError, TypeError):
        raise ValidationError("Use a valid date in YYYY-MM-DD format.") from None
    return value


def _timestamp(value: str, optional: bool = False) -> str:
    if optional and value == "":
        return value
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or len(value) > 40:
            raise ValueError
    except (ValueError, TypeError):
        raise ValidationError("A record timestamp must include its time zone.") from None
    return value


def _text(value: str, label: str, limit: int, multiline: bool = False) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be text.")
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not value or len(value) > limit:
        raise ValidationError(f"{label} is required and must be at most {limit} characters.")
    for char in value:
        if (ord(char) < 32 or ord(char) == 127) and not (multiline and char in "\n\t"):
            raise ValidationError(f"{label} contains an unsupported control character.")
    return value


class MedicalRecord:
    """An immutable value; pending requests have an empty recorded_at field."""

    __slots__ = ("request_id", "patient", "author", "visit_date", "title", "notes", "submitted_at", "recorded_at", "_frozen")

    def __init__(self, request_id: int, patient: str, author: str, visit_date: str,
                 title: str, notes: str, submitted_at: str, recorded_at: str = "") -> None:
        if type(request_id) is not int or not 1 <= request_id < (1 << 63):
            raise ValidationError("Request number is outside the supported range.")
        self.request_id = request_id
        self.patient = _text(patient, "Patient reference", 64)
        self.author = _text(author, "Recorded by", 80)
        self.visit_date = validate_day(visit_date)
        self.title = _text(title, "Record title", 120)
        self.notes = _text(notes, "Clinical notes", 6000, multiline=True)
        self.submitted_at = _timestamp(submitted_at)
        self.recorded_at = _timestamp(recorded_at, optional=True)
        self._frozen = True

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_frozen", False):
            raise AttributeError("Records are immutable. Create a new request for a correction.")
        object.__setattr__(self, name, value)

    @property
    def reference(self) -> str:
        return f"REQ-{self.request_id:06d}"

    def recorded(self, timestamp: str) -> MedicalRecord:
        return MedicalRecord(self.request_id, self.patient, self.author, self.visit_date,
                             self.title, self.notes, self.submitted_at, timestamp)

    def to_bytes(self) -> bytes:
        return (
            b"MKR1" + self.request_id.to_bytes(8, "big")
            + encode_text(self.patient) + encode_text(self.author) + encode_text(self.visit_date)
            + encode_text(self.title) + encode_text(self.notes)
            + encode_text(self.submitted_at) + encode_text(self.recorded_at)
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> MedicalRecord:
        reader = Reader(data)
        if reader.take(4) != b"MKR1":
            raise DecodeError("Unknown record format.")
        try:
            record = cls(reader.number(), reader.text(64), reader.text(80), reader.text(10),
                         reader.text(120), reader.text(6000), reader.text(40), reader.text(40))
        except ValidationError as error:
            raise DecodeError(str(error)) from error
        reader.finish()
        if record.to_bytes() != data:
            raise DecodeError("A record uses a noncanonical encoding.")
        return record
