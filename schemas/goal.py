"""Goal inputs use decimal dollars; storage and raw output use integer cents."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from schemas.timestamps import TimestampReadModel
from utils.choices import (
    GOAL_CATEGORIES, GOAL_PRIORITIES, GOAL_PROGRESS_SOURCES, GOAL_STATUSES, GOAL_TYPES,
)
from utils.validators import optional_text, require_choice, require_text, validate_money


class GoalFields(BaseModel):
    """Full editable payload, following Serenity's existing PUT convention."""

    # Reject ownership, lifecycle and completion-time fields instead of silently
    # ignoring a caller's attempt to alter protected state.
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    goal_type: str
    category: str
    priority: str = "NORMAL"
    target_date: date | None = None
    target_amount: Decimal | None = None
    progress_source: str = "MANUAL"
    # Only holds real progress when progress_source is MANUAL. Future automatic
    # sources must calculate progress, never read or trust this stored field.
    current_progress_amount: Decimal | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        return require_text(value, "Name")

    @field_validator("description", "notes")
    @classmethod
    def check_text(cls, value: str | None) -> str | None:
        return optional_text(value, max_length=1000)

    @field_validator("goal_type", "category", "priority", "progress_source")
    @classmethod
    def check_choice(cls, value: str, info) -> str:
        choices = {
            "goal_type": GOAL_TYPES,
            "category": GOAL_CATEGORIES,
            "priority": GOAL_PRIORITIES,
            "progress_source": GOAL_PROGRESS_SOURCES,
        }
        return require_choice(value, choices[info.field_name], info.field_name.replace("_", " ").title())

    @field_validator("target_amount", "current_progress_amount")
    @classmethod
    def check_money(cls, value: Decimal | None, info) -> Decimal | None:
        if value is None:
            return None
        label = info.field_name.replace("_", " ").title()
        value = validate_money(value, label)
        if value < 0:
            raise ValueError(f"{label} cannot be negative")
        return value

    @model_validator(mode="after")
    def check_manual_progress(self) -> "GoalFields":
        """Reject invalid source/amount combinations without clearing the input."""
        if self.progress_source != "MANUAL" and self.current_progress_amount is not None:
            raise ValueError(
                "Current progress amount can only be set when progress source is MANUAL."
            )
        return self


class GoalCreate(GoalFields):
    """New goals start NOT_STARTED; only the status action changes that."""


class GoalUpdate(GoalFields):
    """Status, active state and completed_at are not general editable fields."""


class GoalStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str

    @field_validator("status")
    @classmethod
    def check_status(cls, value: str) -> str:
        return require_choice(value, GOAL_STATUSES, "Status")


class GoalRead(TimestampReadModel):
    id: int
    name: str
    description: str | None
    goal_type: str
    category: str
    status: str
    priority: str
    target_date: date | None
    target_amount_cents: int | None
    target_amount: Decimal | None
    progress_source: str
    # Only represents real progress for MANUAL. Future automatic sources must
    # calculate their progress, never read or trust this stored manual field.
    current_progress_amount_cents: int | None
    current_progress_amount: Decimal | None
    notes: str | None
    active: bool
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_validator("completed_at")
    @classmethod
    def normalize_completion_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return cls.normalize_timestamp_to_utc(value)