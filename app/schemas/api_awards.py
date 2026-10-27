"""Student Award catalogue and redemption JSON contracts."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiAward(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    required_hours: Decimal
    quantity_available: int
    active: bool


class ApiStudentAward(BaseModel):
    award: ApiAward
    eligible: bool
    pending: bool


class ApiAwardCatalogue(BaseModel):
    verified_hours: Decimal
    awards: list[ApiStudentAward]


class ApiRedemptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    award_id: int = Field(gt=0, strict=True)


class ApiRedemption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    award_id: int
    status: Literal["pending", "approved", "rejected", "fulfilled"]
    requested_at: datetime
    processed_by: int | None
    processed_at: datetime | None


class ApiRedemptionHistoryEntry(ApiRedemption):
    award_name: str


class ApiRedemptionError(BaseModel):
    detail: str | list[dict[str, Any]]
