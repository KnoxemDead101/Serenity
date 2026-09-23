---
name: Private GitHub source
description: How to access the upstream Serenity repository for future source syncs.
---

The upstream Serenity repository is private, so source syncs must use the authenticated GitHub integration rather than an unauthenticated shell `git clone`.

**Why:** The shell clone path rejected the repository credentials, while the connected GitHub integration can read the repository without exposing credentials.

**How to apply:** Reconnect GitHub if needed, then read the repository through its authenticated API before copying files into the workspace.