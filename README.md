# MedKeep

An offline Python desktop project for recording, queuing, verifying, and reviewing medical-record entries through a hash-linked chain.

**Status:** Clinical interface selected. The hand-written containers, paired hash chain, handmade SHA-256, local storage, and daily archives are complete. The desktop interface is in development.

## Project requirements

The course brief requires a singly linked chain and FIFO request queue implemented from scratch. Each record is followed by a hash/seal node. Verification checks the stored hashes against recalculated hashes before records are displayed.

See [the complete requirements](docs/requirements.md) for required behavior, optional objectives, submission rules, and specification ambiguities.

## Planned interface

Four separate tabs:

- **Create:** prepare and enqueue a record request.
- **Approval:** verify chain integrity and show the result.
- **Queue:** view pending requests and process the oldest request first.
- **History:** read verified records and prepare daily archives.

Approval refers to integrity verification, not a clinical authorization system. Patient fields and UI layouts are proposed conveniences; the brief does not prescribe a medical-record schema.

The owner selected **Clinical**. See [the interface design references](docs/interface-concepts.md). The original previews use synthetic data; the working application is being built around Clinical.

## Implementation commitments

- Python application that works without internet access.
- Explicit node classes, references, traversals, and FIFO operations.
- No `queue`, `collections.deque`, third-party linked lists, or built-in collections used as substitutes for the core chain or queue.
- SHA-256 is implemented by hand, including a 16-node circular linked message schedule. No hashing library is used. See [the algorithm explanation](docs/algorithms.md).
- Clear names, comments, readable formatting, algorithm explanations, and meaningful tests.
- Documented limitations: hash chaining is tamper-evident under its trust assumptions; it is not encryption or an independently authenticated audit log.

## Development milestones

1. Requirements and interface choice — complete.
2. Hand-written data structures and verification algorithms — complete; 22 core tests pass.
3. Local persistence and daily archive workflow — complete; 38 core/storage tests pass.
4. Selected tabbed desktop interface — planned.
5. End-to-end checks, documentation, and submission packaging — planned.

The application uses Python's standard library. Run the current checks with `python -m unittest discover -v`. Desktop launch instructions will be added when the UI is complete. See [the storage design](docs/storage.md) for recovery behavior and local-file limits.

## Course submission

The brief requests `DSAProject1_FirstnameLastname_StudentNumber.zip` submitted through Quera. It states that work is individual, blind copying or blind use of AI is prohibited, and the student must understand and explain the code. Extra credit requires at least 80% completion of the core project and is capped at 30%.
