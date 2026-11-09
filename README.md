# MedKeep

An offline Python desktop project for recording, queuing, verifying, and reviewing medical-record entries through a hash-linked chain.

**Status:** requirements reviewed; interface selection pending. Application implementation will begin after the interface is selected.

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

Three interface concepts are being reviewed: **Clinical**, **Workspace**, and **Ledger**. See [the interface design references](docs/interface-concepts.md). These previews are design demonstrations using synthetic data, not the Python application.

## Implementation commitments

- Python application that works without internet access.
- Explicit node classes, references, traversals, and FIFO operations.
- No `queue`, `collections.deque`, third-party linked lists, or built-in collections used as substitutes for the core chain or queue.
- UI and hashing dependencies are separate from the data-structure implementation. The brief explicitly permits a ready-made SHA-256 function.
- Clear names, comments, readable formatting, algorithm explanations, and meaningful tests.
- Documented limitations: hash chaining is tamper-evident under its trust assumptions; it is not encryption or an independently authenticated audit log.

## Development milestones

1. Requirements and interface choice — in progress.
2. Hand-written data structures and verification algorithms — planned.
3. Local persistence and daily archive workflow — planned.
4. Selected tabbed desktop interface — planned.
5. End-to-end checks, documentation, and submission packaging — planned.

The README will gain installation, launch, usage, testing, architecture, and packaging instructions as the corresponding parts are implemented. No launch command is available yet.

## Course submission

The brief requests `DSAProject1_FirstnameLastname_StudentNumber.zip` submitted through Quera. It states that work is individual, blind copying or blind use of AI is prohibited, and the student must understand and explain the code. Extra credit requires at least 80% completion of the core project and is capped at 30%.
