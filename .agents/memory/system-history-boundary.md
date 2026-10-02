---
name: System observation history boundaries
description: Meaning and authority of request-driven operational history.
---

Keep operational history request-driven and owner-scoped. A retained timestamp
means a console request observed a status, not an outage start/end or proof of
availability between checks. Missing observations cannot be backfilled.

**Why:** Authentication and history storage can fail during the very outage
being investigated. Inventing observations or inferring durations would give
owners false evidence. Financial Data Health includes owner activity and is
outside the operational history privacy boundary.

**How to apply:** Future history extensions must distinguish observation time
from incident time, define safe fixed facts before persistence, and explicitly
review any scheduled monitoring or financial-data audit as separate scope.
Audit storage availability must not redefine financial write authority.

Request-driven retention does not guarantee physical deletion during idle
periods or deletion from backup copies.

**Why:** No background job exists in this slice; runtime cleanup cannot erase
off-host backups. An expiration window is a visibility policy as well as
opportunistic cleanup, not a promise of timed erasure everywhere.

**How to apply:** Describe purge timing and backup lifecycle honestly; require
separate scheduling and retention design before promising hard deletion times.