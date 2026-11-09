"""SHA-256 written from the FIPS 180-4 specification, without hashing libraries.

Padding, scheduling, rotations, compression and digest assembly are implemented
here. The schedule uses a hand-written 16-node circular linked buffer, rather
than a ready-made array/list. Constants are immutable raw bytes from the standard.
This educational implementation is not a FIPS-validated cryptographic module.
"""

from __future__ import annotations

MASK = 0xFFFFFFFF
ROUND_CONSTANTS = bytes.fromhex(
    "428a2f98 71374491 b5c0fbcf e9b5dba5 3956c25b 59f111f1 923f82a4 ab1c5ed5 "
    "d807aa98 12835b01 243185be 550c7dc3 72be5d74 80deb1fe 9bdc06a7 c19bf174 "
    "e49b69c1 efbe4786 0fc19dc6 240ca1cc 2de92c6f 4a7484aa 5cb0a9dc 76f988da "
    "983e5152 a831c66d b00327c8 bf597fc7 c6e00bf3 d5a79147 06ca6351 14292967 "
    "27b70a85 2e1b2138 4d2c6dfc 53380d13 650a7354 766a0abb 81c2c92e 92722c85 "
    "a2bfe8a1 a81a664b c24b8b70 c76c51a3 d192e819 d6990624 f40e3585 106aa070 "
    "19a4c116 1e376c08 2748774c 34b0bcb5 391c0cb3 4ed8aa4a 5b9cca4f 682e6ff3 "
    "748f82ee 78a5636f 84c87814 8cc70208 90befffa a4506ceb bef9a3f7 c67178f2"
)


def rotate_right(word: int, count: int) -> int:
    return ((word >> count) | (word << (32 - count))) & MASK


class _Word:
    __slots__ = ("value", "next")

    def __init__(self, value: int) -> None:
        self.value = value
        self.next: _Word = self


class _Schedule:
    """A moving window W[t-16]..W[t-1] in sixteen circular nodes."""

    def __init__(self, block: bytes) -> None:
        head = _Word(int.from_bytes(block[:4], "big"))
        tail = head
        for offset in range(4, 64, 4):
            tail.next = _Word(int.from_bytes(block[offset:offset + 4], "big"))
            tail = tail.next
        tail.next = head
        self._last = tail
        self.oldest = head
        self.lag15 = head.next
        self.lag7 = head
        self.lag2 = head
        for _ in range(9):
            self.lag7 = self.lag7.next
        for _ in range(14):
            self.lag2 = self.lag2.next
        self.round = 0

    def take(self) -> int:
        if self.round >= 16:
            x = self.lag15.value
            y = self.lag2.value
            sigma0 = rotate_right(x, 7) ^ rotate_right(x, 18) ^ (x >> 3)
            sigma1 = rotate_right(y, 17) ^ rotate_right(y, 19) ^ (y >> 10)
            self.oldest.value = (self.oldest.value + sigma0 + self.lag7.value + sigma1) & MASK
        word = self.oldest.value
        self.oldest = self.oldest.next
        self.lag15 = self.lag15.next
        self.lag7 = self.lag7.next
        self.lag2 = self.lag2.next
        self.round += 1
        if self.round == 64:
            # Break the circle when finished so reference counting can reclaim
            # the nodes immediately, rather than relying on the cycle collector.
            self._last.next = None
        return word


class HandmadeSHA256:
    """Incremental byte-oriented SHA-256 with non-destructive digest()."""

    def __init__(self, data: bytes = b"") -> None:
        self._h0 = 0x6A09E667
        self._h1 = 0xBB67AE85
        self._h2 = 0x3C6EF372
        self._h3 = 0xA54FF53A
        self._h4 = 0x510E527F
        self._h5 = 0x9B05688C
        self._h6 = 0x1F83D9AB
        self._h7 = 0x5BE0CD19
        self._pending = b""
        self._length = 0
        self.update(data)

    def update(self, data: bytes) -> HandmadeSHA256:
        if not isinstance(data, bytes):
            raise TypeError("SHA-256 input must be bytes; encode text as UTF-8 first.")
        if self._length + len(data) >= (1 << 61):
            raise ValueError("SHA-256 requires a message shorter than 2^64 bits.")
        self._length += len(data)
        offset = 0
        if self._pending:
            required = 64 - len(self._pending)
            self._pending += data[:required]
            offset = min(required, len(data))
            if len(self._pending) == 64:
                self._compress(self._pending)
                self._pending = b""
        while offset + 64 <= len(data):
            self._compress(data[offset:offset + 64])
            offset += 64
        self._pending += data[offset:]
        return self

    def copy(self) -> HandmadeSHA256:
        result = HandmadeSHA256()
        result._h0, result._h1 = self._h0, self._h1
        result._h2, result._h3 = self._h2, self._h3
        result._h4, result._h5 = self._h4, self._h5
        result._h6, result._h7 = self._h6, self._h7
        result._pending = self._pending
        result._length = self._length
        return result

    def digest(self) -> bytes:
        result = self.copy()
        padding = b"\x80" + b"\x00" * ((55 - self._length) % 64)
        result.update(padding + (self._length * 8).to_bytes(8, "big"))
        return (
            result._h0.to_bytes(4, "big") + result._h1.to_bytes(4, "big")
            + result._h2.to_bytes(4, "big") + result._h3.to_bytes(4, "big")
            + result._h4.to_bytes(4, "big") + result._h5.to_bytes(4, "big")
            + result._h6.to_bytes(4, "big") + result._h7.to_bytes(4, "big")
        )

    def hexdigest(self) -> str:
        return self.digest().hex()

    def _compress(self, block: bytes) -> None:
        schedule = _Schedule(block)
        a, b, c, d = self._h0, self._h1, self._h2, self._h3
        e, f, g, h = self._h4, self._h5, self._h6, self._h7
        for round_number in range(64):
            sigma1 = rotate_right(e, 6) ^ rotate_right(e, 11) ^ rotate_right(e, 25)
            choose = (e & f) ^ ((~e) & g)
            constant = int.from_bytes(ROUND_CONSTANTS[round_number * 4:round_number * 4 + 4], "big")
            temp1 = (h + sigma1 + choose + constant + schedule.take()) & MASK
            sigma0 = rotate_right(a, 2) ^ rotate_right(a, 13) ^ rotate_right(a, 22)
            majority = (a & b) ^ (a & c) ^ (b & c)
            temp2 = (sigma0 + majority) & MASK
            h, g, f, e = g, f, e, (d + temp1) & MASK
            d, c, b, a = c, b, a, (temp1 + temp2) & MASK
        self._h0 = (self._h0 + a) & MASK
        self._h1 = (self._h1 + b) & MASK
        self._h2 = (self._h2 + c) & MASK
        self._h3 = (self._h3 + d) & MASK
        self._h4 = (self._h4 + e) & MASK
        self._h5 = (self._h5 + f) & MASK
        self._h6 = (self._h6 + g) & MASK
        self._h7 = (self._h7 + h) & MASK


def sha256(data: bytes) -> str:
    """Return a 64-character lowercase digest using only our implementation."""
    return HandmadeSHA256(data).hexdigest()
