"""Dependent schemas: validated API input and read responses."""

from datetime import datetime

from pydantic import BaseModel, field_validator

from schemas.timestamps import TimestampReadModel
from utils.validators import optional_text, require_text


class DependentCreate(BaseModel):
    display_name: str
    notes: str | None = None

    @field_validator("display_name")
    @classmethod
    def check_display_name(cls, value: str) -> str:
        return require_text(value, "Display name", max_length=100)

    @field_validator("notes")
    @classmethod
    def check_notes(cls, value: str | None) -> str | None:
        return optional_text(value, max_length=1000)


class DependentUpdate(DependentCreate):
    """Updates replace the editable dependent fields."""


class DependentRead(TimestampReadModel):
    id: int
    display_name: str
    notes: str | None
    active: bool
    created_at: datetime
    updated_at: datetime