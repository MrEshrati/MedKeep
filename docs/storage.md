# Local storage and daily archives

## Workspace format

`medkeep.mkd` is a versioned binary snapshot. It contains a format marker, revision, next request number, node and queue counts, nodes in newest-to-oldest order, pending records in FIFO order, and a 32-byte checksum calculated by the project's hand-written SHA-256 implementation.

Node metadata includes the node index, kind, predecessor index, inherited hash, and a length-prefixed raw payload. Loading reconstructs the **single** previous-node reference and preserves every stored hash. It does not rebuild or repair hashes to make a corrupt chain appear valid. Record fields are bounded, length-prefixed UTF-8 values; no pickle, code evaluation, database, or object-deserialization library is involved.

The application permits at most 10,000 chain nodes (5,000 processed records), 5,000 pending requests, 6,000 characters per note, and a 32 MiB snapshot. These are explicit resource limits for the educational desktop application. A limit failure preserves existing data.

## Saving and concurrency

- A workspace uses an operating-system file lock so a second cooperating MedKeep process cannot open it simultaneously. Closing the application releases the lock; a crash releases the operating-system lock automatically. The small lock file may remain and is not evidence that a process is still running.
- Before saving, the service copies the chain and queue using the custom linked structures. It changes that candidate, writes a temporary file in the same directory, flushes and synchronizes it, then atomically replaces the snapshot.
- Only after replacement succeeds does the service switch its live state to the candidate. Failed enqueueing does not consume a request number. Failed processing does not lose a queued request or leave a half-created live pair.
- The saved snapshot fingerprint is checked before and after serialization. Outside changes, deletion, or a newly appearing file block writes instead of being overwritten.
- The UI will perform expensive operations in a single background job and keep all GUI operations on the main thread. No library queue is used to communicate with the worker.

## Verification and recovery

The snapshot checksum catches accidental changes to pending requests, metadata, and chain bytes. The paired-chain verifier independently checks the stored links. History requires a successful explicit verification, and reading it verifies again. Processing and enqueueing also verify before changing a workspace. A write invalidates the previous explicit approval.

A malformed snapshot fails to open and is preserved. A structurally readable chain with broken hashes can be inspected through its verification report, but cannot be changed, exported, or presented as verified history. The application never automatically resets the workspace or silently discards damaged records.

To work separately, choose another directory with the application's `--data-dir` option once the launcher is available. For recovery, preserve the original file and use a known-good copy of the entire workspace. Do not edit hashes or remove nodes to silence a failure. Backups and archives contain the same sensitive content as the workspace.

## Daily archive

The service verifies the chain immediately before exporting. It selects records by their **processing date**, not by the visit date or request-submission date. It writes a UTF-8 text file under `archives/`, including the selected date, export timestamp, verified count, current chain-head digest, and record details in newest-first order.

Archive filenames contain only validated dates and application-generated timestamps. Exclusive creation prevents overwriting an existing export. Exporting the same day again creates another file. Exporting a day with no records explains that result without creating an empty archive. Nothing clears or modifies the original chain.

## Security decisions

- Use bounded, data-only decoding, canonical field encoding, atomic snapshot replacement, and operating-system workspace locks.
- Keep patient content out of logs and Git; default data and archive directories are ignored. On POSIX, newly created private directories/files use restrictive modes. On Windows, access inherits the workspace directory's ACLs.
- The requested handmade hash is tested against published vectors, but this implementation is educational and not certified. A checksum or unkeyed chain is not encryption or an authenticated external anchor; a fully privileged attacker can rewrite and recompute it.
- This single-user, local course project has no network service, authentication, encrypted storage, automatic backup, or medical compliance claim. Use synthetic data for demonstrations and protect the containing directory and any exported copies through the operating system.
