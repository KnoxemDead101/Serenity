---
name: Private GitHub source
description: How to access the upstream Serenity repository for future source syncs.
---

The upstream Serenity repository is private, so source syncs must use the authenticated GitHub integration rather than an unauthenticated shell `git clone`.

**Why:** The shell clone path rejected the repository credentials, while the connected GitHub integration can read the repository without exposing credentials.

**How to apply:** Reconnect GitHub if needed, then read the repository through its authenticated API before copying files into the workspace.

For workspace-to-GitHub syncs through the integration, compare local Git blob IDs against the remote tree, create missing blobs, then build a tree using blob IDs and move the branch with a non-force update. Avoid putting file contents directly in a Git Trees API request: the proxy can return a Cloudflare challenge even for a small content-bearing tree. For binary files, read bytes through the sandbox filesystem instead of shell callback base64 output, which may truncate large output without an obvious error. Always verify every tracked blob ID after the ref update.

**Why:** A content-bearing tree request was blocked, and a large screenshot encoded through the shell callback was silently truncated; checking blob IDs exposed the mismatch.

**How to apply:** When syncing a private repository through the connected API rather than a Git remote, upload base64 blobs, use SHA-only tree entries, avoid force-updating the branch, and compare final remote blob IDs with local tracked Git IDs.