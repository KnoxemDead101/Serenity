"""Shared UTC normalization for timestamps returned by the database."""

from datetime import datetime, timezone

from pydantic import BaseModel, field_validator


class TimestampReadModel(BaseModel):
    """Read-model base that makes SQLite and PostgreSQL timestamps agree."""

    @field_validator(
        "created_at",
        "updated_at",
        "changed_at",
        mode="after",
        check_fields=False,
    )
    @classmethod
    def normalize_timestamp_to_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)