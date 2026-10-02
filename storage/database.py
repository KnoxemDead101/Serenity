"""
Database connection.

This file owns ONE job: connecting Serenity to its SQLite database.

Key pieces:
- engine        : the connection to the database file.
- SessionLocal  : a factory that creates "sessions". A session is one
                  unit of work: you add/read objects, then commit.
- Base          : the parent class every database model inherits from.
                  SQLAlchemy uses it to know which tables exist.
- get_db()      : hands a session to each API request and closes it
                  afterwards, even if something goes wrong.
- init_db()     : creates any tables that don't exist yet.

SQLAlchemy is an "ORM" (Object-Relational Mapper). It lets us work with
Python objects (Account) instead of writing SQL strings by hand. You can
still see the SQL it runs by setting echo=True on the engine below.
"""

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# The database location comes from an environment variable so it can be
# changed without editing code (see .env.example). The default is a file
# called serenity.db in the folder you run the app from.
def get_database_url() -> str:
    """Return a SQLAlchemy URL for SQLite or Replit PostgreSQL."""
    url = os.getenv("DATABASE_URL", "sqlite:///./serenity.db")
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = get_database_url()
# This runtime engine is not evidence of the managed production schema.
# The opt-in post-publication check uses Replit read-only metadata separately;
# see storage/goals_schema_readiness.py. Never add startup schema repair here.
IS_SQLITE = DATABASE_URL.startswith("sqlite")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    """Parent class for all database models."""


# Enforce safety for direct service calls as well as HTTP requests. Identity
# bootstrap remains available; owner-scoped domain mutations fail closed.
from services.write_safety import protect_bulk, protect_flush

event.listen(Session, "before_flush", protect_flush)
event.listen(Session, "do_orm_execute", protect_bulk)


def get_db():
    """Give one database session to a request, then always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
