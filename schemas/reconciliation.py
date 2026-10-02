"""Inputs for a stateless, read-only shadow reconciliation."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator


class PreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceMapping(PreviewInput):
    source_id: StrictInt
    portfolio_id: StrictInt | None = None
    account_id: StrictInt | None = None
    investment_account_id: StrictInt | None = None
    instrument_id: StrictInt | None = None
    specification_id: StrictInt | None = None
    identity_confirmed: StrictBool = False
    beneficial_ownership: Literal["unknown", "personal", "simulation", "prop", "other"] = "unknown"
    basis_status: Literal["unknown", "unverified"] = "unverified"
    zero_basis_reviewed: StrictBool = False
    valuation_as_of: date | None = None
    valuation_evidence: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def dated_value_requires_evidence(self):
        if self.valuation_as_of and not (self.valuation_evidence or "").strip():
            raise ValueError("Dated original values require valuation evidence")
        return self


class AccountEvidence(PreviewInput):
    account_id: StrictInt
    balance_meaning: Literal["unknown", "cash_only", "combined"] = "unknown"
    evidence: str | None = Field(default=None, max_length=2000)
    complete: StrictBool = False
    source_ids: list[StrictInt] = Field(default_factory=list, max_length=10000)
    cash_cents: StrictInt | None = None
    prior_conversion_complete: StrictBool = False
    prior_opening_position_ids: list[StrictInt] = Field(default_factory=list, max_length=10000)
    prior_cash_entry_ids: list[StrictInt] = Field(default_factory=list, max_length=10000)


class PreviewRequest(PreviewInput):
    mappings: list[SourceMapping] = Field(default_factory=list, max_length=10000)
    accounts: list[AccountEvidence] = Field(default_factory=list, max_length=10000)


class ReportToken(PreviewInput):
    report_token: str = Field(min_length=1, max_length=20000000)
