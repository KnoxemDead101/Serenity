---
name: System health authority boundary
description: Keep status visibility separate from authority to change financial write behavior.
---

The initial System Health slice is evidence visibility, not a new global
operational-mode controller. Do not turn displayed statuses into new financial
mutation rules without defining and reviewing the failure semantics separately.

**Why:** The approved baseline intentionally reuses existing write safety.
Schema readability, backup evidence, and market provenance have independent
meanings; combining them into a global write switch could unexpectedly change
legacy financial behavior or block useful historical reads.

**How to apply:** Future degradation, maintenance, or data-health work should
first define which subsystem is affected and what operations are unsafe.
Keep visibility truthful while preserving existing enforcement until that
behavior change is explicitly part of the implementation scope.

Do not infer real-world completeness or a verification date from stored-row
presence, an edit, or a conversion capture.

**Why:** Manual records can be incomplete even when every stored field is valid.
An edit can change only notes, and capturing an old valuation does not make it
current. Explicit owner-check evidence is now separately supported under the
owner-approved manual verification design; ordinary edits remain non-evidence.

**How to apply:** Any future "last verified" feature needs explicit owner
evidence separate from edits and capture timestamps. Preserve unknown evidence
where no explicit matching check exists, and describe date-based notices as
review reminders, not independent verified freshness or authority to change balances.