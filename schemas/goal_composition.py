"""Strict composition inputs; dollars at the boundary, integer cents in storage."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas.goal import GoalRead
from schemas.timestamps import TimestampReadModel
from utils.choices import GOAL_ITEM_STATUSES, GOAL_MILESTONE_STATUSES
from utils.validators import optional_text, require_choice, require_text, validate_money


class CompositionFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sort_order: int = Field(default=0, strict=True, ge=0, le=2147483647)


def _nonnegative_money(value: Decimal | None, label: str) -> Decimal | None:
    if value is None:
        return None
    value = validate_money(value, label)
    if value < 0:
        raise ValueError(f"{label} cannot be negative")
    return value


class GoalItemCreate(CompositionFields):
    name: str
    description: str | None = None
    expected_cost: Decimal | None = None
    # Provisional only: future Transaction-derived actual cost takes precedence;
    # the override itself never represents real spending or changes any total.
    manual_actual_cost_override: Decimal | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        return require_text(value, "Name")

    @field_validator("description", "notes")
    @classmethod
    def check_text(cls, value: str | None) -> str | None:
        return optional_text(value, max_length=1000)

    @field_validator("expected_cost", "manual_actual_cost_override")
    @classmethod
    def check_money(cls, value: Decimal | None, info) -> Decimal | None:
        return _nonnegative_money(value, info.field_name.replace("_", " ").title())


class GoalItemUpdate(GoalItemCreate):
    """Full editable replacement; status and archive are separate actions."""


class GoalMilestoneCreate(CompositionFields):
    title: str
    description: str | None = None
    target_date: date | None = None

    @field_validator("title")
    @classmethod
    def check_title(cls, value: str) -> str:
        return require_text(value, "Title")

    @field_validator("description")
    @classmethod
    def check_description(cls, value: str | None) -> str | None:
        return optional_text(value, max_length=1000)


class GoalMilestoneUpdate(GoalMilestoneCreate):
    """Status/completion timestamps cannot be changed through this payload."""


class GoalCheckpointCreate(CompositionFields):
    amount: Decimal
    label: str | None = None

    @field_validator("amount")
    @classmethod
    def check_money(cls, value: Decimal) -> Decimal:
        return _nonnegative_money(value, "Amount")

    @field_validator("label")
    @classmethod
    def check_label(cls, value: str | None) -> str | None:
        return optional_text(value, max_length=100)


class GoalCheckpointUpdate(GoalCheckpointCreate):
    """Reached and parent ownership are never client-editable."""


class GoalItemStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str

    @field_validator("status")
    @classmethod
    def check_status(cls, value: str) -> str:
        return require_choice(value, GOAL_ITEM_STATUSES, "Status")


class GoalMilestoneStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str

    @field_validator("status")
    @classmethod
    def check_status(cls, value: str) -> str:
        return require_choice(value, GOAL_MILESTONE_STATUSES, "Status")


class CompositionRead(TimestampReadModel):
    id: int
    goal_id: int
    sort_order: int
    created_at: datetime
    updated_at: datetime


class GoalItemRead(CompositionRead):
    name: str
    description: str | None
    expected_cost_cents: int | None
    expected_cost: Decimal | None
    manual_actual_cost_override_cents: int | None
    manual_actual_cost_override: Decimal | None
    notes: str | None
    status: str
    active: bool


class GoalMilestoneRead(CompositionRead):
    title: str
    description: str | None
    target_date: date | None
    status: str
    completed_at: datetime | None

    @field_validator("completed_at")
    @classmethod
    def normalize_completion_timestamp(cls, value: datetime | None) -> datetime | None:
        return cls.normalize_timestamp_to_utc(value) if value is not None else None


class GoalCheckpointRead(CompositionRead):
    amount_cents: int
    amount: Decimal
    label: str | None
    # Response-only comparison; None means meaningful manual progress is absent.
    reached: bool | None


class GoalCompositionRead(BaseModel):
    goal: GoalRead
    items: list[GoalItemRead]
    milestones: list[GoalMilestoneRead]
    checkpoints: list[GoalCheckpointRead]