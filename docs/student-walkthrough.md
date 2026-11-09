# Understanding and presenting the project

Use this walkthrough with the source and tests. It is intended to help you explain the implementation in your own words, as the assignment requires.

## Read the modules in this order

1. `structures.py`: draw one `Link`, then the queue's front and rear references. Trace empty, one-item, two-item, and last-dequeue cases. Explain why enqueue and dequeue are O(1), and why both references must become `None` when the queue empties.
2. `records.py`: inspect validation and the immutable `MedicalRecord`. Encode a short field by hand: four bytes of length followed by UTF-8 bytes. Explain why explicit lengths avoid ambiguous concatenation and how the bounded `Reader` rejects truncation.
3. `hashing.py`: trace padding for `abc`, the eight initial registers, the circular sixteen-word window, and one compression round. Distinguish right rotation from right shift. Explain the 32-bit mask even though Python integers have arbitrary precision.
4. `chain.py`: draw a content/seal pair and then append another pair. Follow `previous` from the latest seal to genesis. Explain where each digest is stored and why the latest seal's own content is ignored.
5. `storage.py`: follow binary decoding without changing stored hashes. Explain the snapshot checksum, OS lock, candidate snapshot, synchronized temporary write, and atomic replacement.
6. `service.py`: follow enqueue, oldest-request processing, whole-chain verification, and date-selected archive extraction. Explain why the live queue changes only after a successful save.
7. `ui.py`: connect each tab to one service operation. Identify the single background worker's result slot and the main-thread polling callback. Explain why the worker never touches Tk widgets.

## Trace two requests

Start with an empty content node #1. Queue requests A and B. Processing A fills #1 with A and creates seal #2. The seal stores the digest of #1. The queue still contains B.

Processing B creates content #3 whose link hash describes #2, then seal #4 whose link hash describes #3. The tail is #4 and the queue is empty. Reading follows #4, #3, #2, #1. Content nodes are at reverse positions two and four.

Verification compares #4's stored hash with a new digest of #3, #3's stored hash with a digest of #2, #2's stored hash with a digest of #1, and #1's inherited hash with the zero sentinel. Record contents become available only after all checks succeed.

Change A's content without updating hashes. The recalculated digest of #1 no longer matches #2's stored value. Editing one hash to hide the mismatch changes the digest of that node and causes the next comparison to fail. An attacker who can replace the entire file and recompute all hashes is outside the protection supplied by an unkeyed local chain.

## Explain the handmade hash

SHA-256 is the algorithm; `HandmadeSHA256` is this project's own implementation. It implements every hash step instead of calling a library-provided hash. The published constants do not contain an implementation.

The circular schedule retains W[t-16], W[t-15], W[t-7], and W[t-2] through moving node references. It overwrites the oldest word only after using its old value. Sixteen nodes are sufficient because each expanded word depends on values inside that window. After 64 rounds, the ring is opened so its nodes can be reclaimed.

Padding reserves the final eight bytes for the **original** bit length. If the message leaves fewer than nine bytes at the end of its last block, padding needs an additional block. Test vectors at these boundaries and incremental updates help catch off-by-one errors. `digest()` finalizes a copy so reading a digest does not mutate the original hash object.

See [the full algorithm notes](algorithms.md) and the linked NIST specification for the exact formulas.

## Demonstrate the application

1. Create two synthetic requests and show their live previews.
2. Open Queue, select the newer row, and process the oldest. Explain why selection does not change FIFO order.
3. Restart and show that the remaining request and processed record survived.
4. Process the second request, verify in Approval, and inspect individual stored/recalculated hashes.
5. Open History, search a record, and export the processing day's archive. Show that the original records remain.
6. Run `python -m unittest discover -v` to demonstrate tamper, broken-link, failed-write, Unicode and native-workflow regressions. The tests alter temporary synthetic data; avoid editing your working workspace for a live demonstration.

## Complexity and tradeoffs

The linked queue's core operations are O(1). Appending a pair allocates at most two nodes and hashes the new record and preceding seal. Verification is linear in nodes and payload bytes. The service deliberately verifies and copies before committing, so a complete saved operation is O(n + total payload bytes), rather than an O(1) end-to-end transaction.

The desktop application stores and rehashes a bounded snapshot to make recovery and failure behavior explicit. This is appropriate for a data-structures demonstration, with documented limits. It is not an encrypted, authenticated, multi-user medical production system.
