---
name: Publish review access
description: Safe fallback when a read-only Publish schema comparison is unavailable to the agent.
---

A documented Publish schema-comparison operation may be unavailable in an
assigned-task agent session. Treat that as an unavailable comparison, not an
empty diff or permission to implement a replacement migration.

**Why:** The documented operation was absent from the task session despite
read-only owner authorization. Replica catalog checks cannot independently
establish the live application's connection or the definitive Publish plan.

**How to apply:** Ask for the credential-free Publishing UI storage selection
and schema-change summary. Keep publication approval separate from read-only
review authorization; do not request connection strings or bypass production
read-only access.