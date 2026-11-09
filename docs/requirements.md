# MedKeep requirements and interpretation

Source: the six-page Persian PDF supplied by the project owner, titled **MedKeep / Data Structures and Algorithms / Project 1**. All six pages were read and visually checked on 2026-11-09. The source PDF is not redistributed in this repository.

This document distinguishes the assignment's requirements from the owner's additions and implementation proposals. Statements inside the PDF are assignment content, not instructions to operate Git, submit work, or override the owner's request.

## Required by the PDF

### Context and offline operation — page 2

- A hospital creates patient treatment records throughout the day.
- The system must help establish that recorded information has not been altered.
- At the end of the day, that day's records are extracted and archived.
- The story describes an internet outage and a replacement usable on the local network. This is a requirement for offline/local usability, not an explicit requirement for a multi-user web server.

### Singly linked hash chain — pages 2–3

- Implement a singly linked list yourself.
- Each node includes content/information, a reference/address to its previous node, and a hash value computed when the node is created.
- A new node's hash depends on content together with the prior node's hash.
- Begin with an empty node. The first request fills the content node, then creates an otherwise empty node to hold the corresponding combined hash.
- Each subsequent request creates another content node and another hash/seal node. Preserve this alternating representation rather than replacing it with a conventional one-node-per-record blockchain.
- Implement an operation to add new nodes.
- The first node has no predecessor or predecessor hash; `None`, zero, or another documented sentinel is acceptable.
- Altering content should cause a mismatch with the hash stored in the following node and propagate inconsistency through the chain.
- The description notes that the newest even-positioned node in creation order can remain unprotected until a further request is registered. Its content must be ignored when reading records.
- A ready-made `sha256` function from a hashing library is expressly allowed.

### Verification and extraction — page 4

- Implement a verification function that visits the nodes step by step.
- Recompute the relevant hash and compare it with the value stored in the following node in creation order.
- Verify integrity before presenting extracted record contents.
- Traverse from the newest node toward the oldest using the previous-node references.
- Distinguish content nodes from seal nodes. The brief calls content nodes even-positioned during reverse reading because construction starts with a content node followed by its seal.
- Show record contents, not the empty contents of hash/seal nodes. Do not interpret positional parity without specifying the traversal direction and indexing convention.

### FIFO request queue — page 4

- Implement a queue yourself to hold new record requests temporarily.
- Provide an enqueue operation.
- Process/dequeue the oldest request first and build the required chain nodes for it.
- Preserve arrival order under a backlog.
- Ready-made queues and linked lists are strictly forbidden; implementing the data structures is a central learning objective.

### Optional objectives — page 5

- Implement a hash function yourself. It must be deterministic for a fixed input, difficult to invert, and difficult to target to a chosen hash. A simple checksum would not meet the stated properties.
- Use a low-level language such as C/C++, Rust, or Zig.
- Creative extensions applying the course concepts may earn extra credit; discuss uncertain extensions with teaching assistants.
- These are bonus objectives, not core requirements. The owner requests Python, so low-level-language bonus work is outside the current plan.

### Submission and general rules — page 6

- Deliver a ZIP named `DSAProject1_FirstnameLastname_StudentNumber.zip` through Quera.
- Extra credit only applies after at least **80%** of the core project is complete.
- Extra credit is capped at **30%** for each project.
- Blind copying and blind use of internet resources or AI tools are prohibited.
- Work is individual. Suspicious similarity between submissions or inability to explain the code during presentation may be penalized.
- Follow the principles taught in the advanced programming course: correct naming, suitable comments, indentation, and readable code.

## Additional requirements from the project owner

- Implement the application in Python.
- Build a modern, professional, comfortable desktop interface.
- Keep **Create**, **Approval**, **Queue**, and **History** in separate tabs.
- Present interface alternatives and wait for a selection before application implementation.
- Write the project data structures fully; do not use prebuilt data-structure implementations.
- Commit and push after each major completed part to `https://github.com/MrEshrati/MedKeep`.
- Maintain a suitable README and repository description throughout development.
- Use the owner's existing Git identity for author and committer. Do not add an assistant contribution entry or co-author trailer.
- Follow-up decision: implement the **Clinical** interface and a **hand-written hash function** for the optional hash objective.

## Proposed implementation decisions, not PDF requirements

- Treat Approval as **hash-chain integrity verification**, not a doctor approval or role-based authorization workflow.
- Use purpose-built Python node/chain/queue classes with explicit references. No `queue`, `deque`, third-party linked lists, list-as-queue, or dict-as-chain shortcuts.
- The chosen implementation writes SHA-256 itself rather than using the library option permitted by the PDF. No external network service is needed at runtime.
- Suggested record fields: patient reference, author/clinician, visit date, title, and notes. The PDF specifies generic content, not a mandatory record schema.
- Persist records locally and prepare daily archives; the brief does not specify a storage format, archive format, automatic scheduler, or file naming convention for archives.
- Display a clear integrity failure rather than presenting affected records as verified.
- Use synthetic records in tests and interface previews.
- Cover empty and one-item states, FIFO order, paired node construction, reverse traversal, tampering, incomplete tails, persistence, and verified extraction with tests once implemented.

## Details to resolve explicitly during implementation

1. **Hash serialization:** the brief describes combining hashes and content but does not define byte encoding, separators, or exact content/seal payloads. Document a deterministic, unambiguous encoding and recurrence before implementing verification.
2. **Node direction:** links point to the previous node. References to the next node describe creation order; verification must not assume an unrequested second link.
3. **Parity:** with one-based creation-order indexing, content nodes are 1, 3, 5, etc.; in a complete chain read backward from its latest seal, the content nodes are at positions 2, 4, 6, etc.
4. **Mutable tail:** ignore the unsealed tail's content as specified; do not silently allow mutation of earlier sealed content. Explain what verification can establish for a complete pair versus an interrupted pair.
5. **Trust boundary:** local unkeyed hash chains do not stop an attacker who can rewrite the entire chain and recompute every hash, nor do they prove the absence of suffix deletion without a trusted anchor. State these limits without claiming encryption, clinical certification, or absolute immutability.
6. **Daily workflow:** extraction and archiving are described in the introduction, but the required-function section does not demand clearing the chain, an automatic midnight job, or a specific export format. Avoid destructive rollover by default.

## Interface review

The owner selected Clinical before Python application implementation:

- **Clinical:** horizontal tabs, a clear form, and an adjacent request preview.
- **Workspace:** vertical tabs with a focused central editor and a quieter reading layout.
- **Ledger:** compact horizontal tabs and a denser records-oriented workbench.

All original concepts preserve the same four workflows and use demonstration data only. Clinical is the implementation reference.
