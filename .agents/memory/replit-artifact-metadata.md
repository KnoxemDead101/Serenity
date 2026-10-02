---
name: Replit artifact manifest updates
description: Non-obvious constraints when retiring or repurposing registered Replit artifacts.
---

Replit-managed artifact manifests cannot be edited or deleted with ordinary file
patches. They must be written to a sibling temporary TOML file and passed
through the artifact TOML validation/replacement flow.

**Why:** Registered artifacts retain their managed workflows and can affect
preview or deployment even after their application source is removed.

**How to apply:** When a Python app replaces a Node/Vite artifact, repoint the
manifest to the Python service or make it explicitly retired. Development and
Publish may start an artifact service from different working directories. A
fixed `cd ../..` worked from the artifact directory but moved outside the app
when Publish started at the repository root, causing Uvicorn to fail importing
`main`. Use an explicit shell run array that detects `main.py` in either `.`
or `../..`, then starts Uvicorn with `--app-dir` set to that location. Verify
the exact command from both directories. Avoid a pip-install build step because
publishing installs root requirements automatically.

Use one managed application workflow rather than a second root workflow for the
same artifact service.

**Why:** Workflow reconciliation after merges restarted both processes on the
same injected port, leaving the artifact preview failed with address-in-use
even while the duplicate root process was serving.

**How to apply:** Route the Run group to the existing managed artifact workflow,
remove the duplicate root workflow, and restart the managed service once.
Changes to root `.replit` also require a complete temporary TOML plus
`verifyAndReplaceDotReplit`; ordinary patches are rejected.