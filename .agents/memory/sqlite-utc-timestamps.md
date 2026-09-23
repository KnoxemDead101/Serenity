---
name: SQLite UTC timestamps
description: Why SQLite-backed responses need explicit UTC normalization despite timezone-aware ORM columns.
---

SQLite's SQLAlchemy DateTime(timezone=True) does not preserve timezone metadata when values are read back. Serenity writes UTC timestamps, so interpret naive SQLite values as UTC when returning them to clients; retain explicit UTC offsets in API responses. PostgreSQL preserves the timezone and should still be normalized to UTC for consistency.

**Why:** A migration to timezone-aware columns alone left SQLite-backed responses serialized without an offset, which browsers can interpret as local time. The SQLite migration is necessarily a no-op for the column's timezone type.

**How to apply:** For new timestamp-bearing read models, ensure the response boundary normalizes naive timestamps to UTC. Do not treat arbitrary user-supplied naive local times as UTC.