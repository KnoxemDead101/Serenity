"""Strict request bodies for owner-confirmed investment conversion."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt


class ConversionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApprovalRequest(ConversionInput):
    report_token: str = Field(min_length=1, max_length=20_000_000)
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_source_ids: list[StrictInt] = Field(min_length=1, max_length=10_000)
    account_corrections_cents: dict[str, StrictInt] = Field(default_factory=dict)
    backup_evidence_reference: str = Field(min_length=1, max_length=2000)
    backup_cutoff: datetime
    rollback_deadline: datetime
    confirm_approval: StrictBool
    test_only_synthetic: StrictBool = False


class ExecuteRequest(ConversionInput):
    idempotency_key: str = Field(min_length=8, max_length=255)
    confirm_execute: StrictBool


class ReverseRequest(ConversionInput):
    reason: str = Field(min_length=3, max_length=2000)
    confirm_reverse: StrictBool