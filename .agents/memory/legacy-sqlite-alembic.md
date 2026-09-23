---
name: Legacy SQLite and Alembic
description: How to handle local SQLite files predating the migration-managed schema.
---

When a local SQLite file predates Alembic, do not stamp it as migrated or delete it merely because tables already exist. First inspect whether it contains records and whether its columns match the migration baseline. An empty incompatible file can be archived before initializing a fresh migration-managed database; a populated file needs a deliberate data-preserving migration.

**Why:** A former development run created tables directly without Alembic. The later migration workflow failed with “table accounts already exists,” despite no user records being present. Schema shape differed from the migration baseline.

**How to apply:** If migration startup fails on an existing SQLite table, inspect row counts and columns before changing the database. Preserve even empty legacy files under a separate name; never silently discard populated data.