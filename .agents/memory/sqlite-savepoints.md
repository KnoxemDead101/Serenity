---
name: SQLite physical transactions and savepoints
description: Legacy sqlite3 transaction behavior can release locks before the ORM transaction ends.
---

Do not infer a physical SQLite outer transaction from SQLAlchemy's logical
transaction state. With the legacy sqlite3 driver, reads may not issue BEGIN;
releasing the first savepoint can commit writes and release their locks.

**Why:** A lock intended to serialize observation and audit append must survive
the intermediate savepoint release. A logical ORM transaction alone does not
provide that guarantee under the existing SQLite driver mode.

**How to apply:** For new SQLite workflows requiring locks across savepoints,
inspect actual driver transaction state and establish the physical transaction
before the savepoint. Test with separate connections to a disposable file,
not just a shared in-memory StaticPool. Do not change the global driver mode
without independently assessing existing financial transactions.