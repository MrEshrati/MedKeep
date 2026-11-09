# Algorithms and data structures

## Hand-written SHA-256

`medkeep/hashing.py` implements SHA-256 directly from [NIST FIPS 180-4](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.180-4.pdf), sections 4.1.2, 4.2.2, 5, and 6.2. It does not call `hashlib`, OpenSSL, or any third-party hashing implementation. This satisfies the intended hand-written-hash extension without inventing a weak checksum or an unstudied cryptographic design. It is an educational implementation, not a certified cryptographic module.

1. Encode text as UTF-8 at the caller. The hash accepts raw bytes.
2. Append a one bit, enough zero bits to reach byte 56 modulo 64, then the original bit length as a 64-bit big-endian integer.
3. Read each 64-byte block as sixteen 32-bit words.
4. Expand those words using the SHA-256 small-sigma rotations and shifts. A hand-written **16-node circular linked buffer** retains the required rolling window; no Python list or array holds the schedule.
5. Run 64 compression rounds with choose, majority, large-sigma rotations, the published round constants, and addition modulo 2^32.
6. Add the working registers back into eight state registers and concatenate them into the 32-byte digest.

The initial values and round constants are mathematical constants from the standard, stored as immutable raw bytes. `digest()` finalizes a copy, so repeated calls and subsequent incremental updates are safe.

Tests include empty input, `abc`, published two-block/multi-block examples, one million `a` bytes, incremental updates around padding/block boundaries, independent state copies, and repeatable digest calls. The `abc` and two-block calculations are also illustrated in [NIST's SHA-256 example](https://csrc.nist.gov/CSRC/media/Projects/Cryptographic-Standards-and-Guidelines/documents/examples/SHA256.pdf). No reference hash implementation is imported by the application or tests.

## The two linked containers

`LinkedQueue` owns front and rear references, a count, and explicit node allocation. Enqueue links a new rear; dequeue detaches the front and resets the rear when the last item is removed. `LinkedSequence` owns a head, tail, and count for verification results and history. Both are implemented in `medkeep/structures.py`.

| Operation | Time | Additional space |
| --- | --- | --- |
| Queue enqueue / peek / dequeue | O(1) | O(1) per enqueue |
| Queue iteration / copy | O(n) | O(1) iteration / O(n) copy |
| Result sequence append | O(1) | O(1) per append |
| Chain append | O(record bytes) for hashing | Two nodes, except the first request |
| Chain verification / extraction | O(nodes + total payload bytes) | O(nodes + extracted record bytes) |
| SHA-256 | O(message bytes) | O(1) working state, excluding input/output |

Python strings, bytes, integers, scalar tuple assignments, type metadata, GUI widget options, and standard-library internals are not replacements for these domain data structures. The core queue, chain, record collections, and hash schedule do not use built-in lists, dictionaries, sets, deques, or ready-made linked-list implementations as storage.

## The paired backward chain

Creation order for two requests:

```text
content #1 <- seal #2 <- content #3 <- seal #4 (tail)
```

Every arrow is the right-hand node's single `previous` reference. Construction begins with empty content node #1; the first request fills it and creates seal #2. Each later request adds a new content/seal pair. Genesis has no predecessor and inherits a zero hash.

The digest describing a node is:

```text
SHA256(
  ASCII("MedKeep/node/v1") + zero byte
  + node index as 8 bytes
  + kind as one byte (C or S)
  + inherited link hash as 32 bytes
  + payload length as 8 bytes
  + payload bytes
)
```

Integers are unsigned big-endian. **The successor stores this digest as its `link_hash`.** This binds content, position, kind, and the preceding chain together. The first node's link hash is 32 zero bytes.

Medical-record payloads have their own version marker, request number, and length-prefixed UTF-8 fields. Length prefixes avoid ambiguous concatenations such as `ab|c` versus `a|bc`. A processed record has a timestamp distinct from its request-submission timestamp.

## Verification and the tail rule

Verification starts at the latest seal and follows `previous`. It checks count, positions, alternation, hash encoding, each stored hash against a recalculated predecessor digest, genesis, record encoding, and FIFO record numbering. An index countdown bounds traversal and detects missing links, cycles, and inconsistent lengths without a ready-made visited set.

Content nodes are odd-numbered in creation order and even-positioned when a complete chain is read backward. Record values are released only when the **entire** verification succeeds. A failed report contains no partially verified records.

The latest seal's own payload is unprotected because it has no successor. It is ignored during extraction, as the PDF requires. A subsequent record protects that older seal's payload through its inherited digest. An interrupted content/seal pair fails verification and cannot be shown as valid history.

Hash chaining detects inconsistencies relative to the stored chain. It does not encrypt data, authenticate a person, prevent an attacker from replacing the entire chain with recomputed hashes, or prove that a complete suffix was not removed without a separately trusted head digest. There is no medical production-readiness claim.
