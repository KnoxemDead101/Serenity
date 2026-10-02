---
name: GitHub source sync
description: How to access the upstream Serenity repository for future source syncs.
---

Use the authenticated GitHub integration for source syncs. Check current repository
visibility before uploading; do not assume historical visibility still applies.

**Why:** The shell clone path rejected the repository credentials, while the connected GitHub integration can read the repository without exposing credentials.

**How to apply:** Reconnect GitHub if needed, then read the repository through its authenticated API before copying files into the workspace.

For workspace-to-GitHub syncs through the integration, compare local Git blob IDs against the remote tree, create missing blobs, then build a tree using blob IDs and move the branch with a non-force update. Avoid putting file contents directly in a Git Trees API request: the proxy can return a Cloudflare challenge even for a small content-bearing tree. For binary files, read bytes through the sandbox filesystem instead of shell callback base64 output, which may truncate large output without an obvious error. Always verify every included source blob ID after the ref update.

**Why:** A content-bearing tree request was blocked, and a large screenshot encoded through the shell callback was silently truncated; checking blob IDs exposed the mismatch.

**How to apply:** When syncing a private repository through the connected API rather than a Git remote, upload base64 blobs, use SHA-only tree entries, avoid force-updating the branch, and compare final remote blob IDs with local tracked Git IDs.

Keep unreviewed raw uploads, diagnostics, exports, and record snapshots out of
public source synchronization, even when platform checkpoints tracked them.
Canonical product documentation is not the same as a raw conversation/log file.

**Why:** Checkpoint tracking is not consent to disclose the file publicly.
Uploaded diagnostics can contain information unrelated to runnable source.

**How to apply:** Recheck repository visibility, build an explicit source
allowlist, exclude raw input/log files, and verify that allowlist after syncing.
Do not delete already-published history or overwrite unknown remote versions
without separate review.