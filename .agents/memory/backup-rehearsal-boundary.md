---
name: Backup rehearsal safety boundary
description: Keep synthetic recovery proof separate from live-data recovery operations.
---

Keep the automated backup rehearsal incapable of accepting an existing database
target. Real recovery belongs in an explicit operator procedure with independently
verified source and empty destination, not a convenience flag on the rehearsal.

**Why:** A test intended to prove recoverability must not gain the ability to
overwrite the financial records it is supposed to protect. A successful local
synthetic round trip also cannot establish off-host backup or key availability.

**How to apply:** Preserve disposable-only provisioning when extending the
rehearsal. Validate host-specific backup storage, encryption/key recovery, and
cutover separately. Strip ambient PostgreSQL settings for in-process drivers as
well as subprocesses; passing an explicit URL does not isolate every libpq option.