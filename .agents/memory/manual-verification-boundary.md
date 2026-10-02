---
name: Manual verification evidence
description: Owner-approved evidence retention and meaning, separate from edits and conversion approval.
---

Use explicit owner evidence bound to the reviewed financial fact; never infer a
verification from edits, conversion capture, or a recently saved explanation.

**Why:** On 2026-10-02 the owner approved the latest-check design before
implementation, including snapshot binding and replacement/deletion rather than
an immutable evidence history. Verification is an owner assertion, not external
bank/broker certification or operational write authority.

**How to apply:** Preserve the distinction in reminders and future review
features. Keep the latest owner-only check until replacement or explicit deletion;
source removal must leave evidence removable without verifying a current source.
No automatic expiry or backup-erasure promise. Any change to these retention or
verification semantics needs a new explicit design review.