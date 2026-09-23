---
name: Python publish dependencies
description: How Python dependencies must be handled for Replit publishing.
---

Do not add `python -m pip install -r requirements.txt` as a Replit publish build
command or post-merge setup step. Keep dependencies in `requirements.txt` and
let Replit manage their installation.

**Why:** The production build environment is PEP 668 externally managed and its
Nix store is immutable, so explicit global pip installation fails before the
application image is built and during post-merge setup.

**How to apply:** Configure only the production run command unless the
application has a real compilation or asset-build step. To remove a previously
saved build command through deployment configuration, pass an explicit empty
build list; omitting the build field preserves the old value. Keep post-merge
setup limited to idempotent local initialization such as development migrations.