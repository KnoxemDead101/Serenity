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
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./serenity.db")

# check_same_thread=False is needed because FastAPI may use a different
# thread for each request, and SQLite normally forbids that.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
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


def init_db() -> None:
    """Create any missing tables. Safe to run every time the app starts."""
    # Importing the model module registers the Account table on Base.
    # Without this import, SQLAlchemy wouldn't know the table exists.
    import models.account  # noqa: F401

    Base.metadata.create_all(bind=engine)
