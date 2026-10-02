"""Validated full-edit work payloads; callers cannot set ownership or lifecycle."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from models.work import WORK_PRIORITIES, WORK_STATUSES
from schemas.timestamps import TimestampReadModel
from utils.validators import optional_text, require_choice, require_text


class WorkFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    notes: str | None = None
    priority: str = "NORMAL"

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        return require_text(value, "Name")

    @field_validator("description", "notes")
    @classmethod
    def check_text(cls, value: str | None) -> str | None:
        return optional_text(value, max_length=1000)

    @field_validator("priority")
    @classmethod
    def check_priority(cls, value: str) -> str:
        return require_choice(value, WORK_PRIORITIES, "Priority")


class ProjectFields(WorkFields):
    goal_id: StrictInt | None = Field(default=None, gt=0, le=2147483647)
    target_date: date | None = None


class TaskFields(WorkFields):
    project_id: StrictInt | None = Field(default=None, gt=0, le=2147483647)
    due_date: date | None = None


class WorkStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str

    @field_validator("status")
    @classmethod
    def check_status(cls, value: str) -> str:
        return require_choice(value, WORK_STATUSES, "Status")


class WorkRead(TimestampReadModel):
    id: int
    name: str
    description: str | None
    notes: str | None
    priority: str
    status: str
    active: bool
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_validator("completed_at")
    @classmethod
    def normalize_completed_at(cls, value: datetime | None) -> datetime | None:
        return cls.normalize_timestamp_to_utc(value) if value is not None else None


class ProjectRead(WorkRead):
    goal_id: int | None
    goal_name: str | None
    target_date: date | None


class TaskRead(WorkRead):
    project_id: int | None
    project_name: str | None
    due_date: date | None