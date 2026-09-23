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

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

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


def get_db():
    """Give one database session to a request, then always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
