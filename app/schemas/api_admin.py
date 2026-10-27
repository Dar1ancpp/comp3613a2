"""JSON contracts for administrator review, Award management and processing."""

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.schemas.api_awards import ApiRedemption, ApiRedemptionHistoryEntry
from app.schemas.api_volunteer_submission import ApiVolunteerSubmission


class ApiSubmissionReview(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    status: Literal["approved", "rejected"]


class ApiPendingSubmission(ApiVolunteerSubmission):
    student_username: str


class ApiAwardWrite(BaseModel):
    """Complete editable representation shared by creation and replacement."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    name: str = Field(min_length=1)
    description: str | None
    required_hours: Decimal = Field(gt=0, allow_inf_nan=False)
    quantity_available: int = Field(ge=0, strict=True)
    active: StrictBool


class ApiRedemptionProcessing(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    status: Literal["approved", "rejected", "fulfilled"]


class ApiActionableRedemption(ApiRedemptionHistoryEntry):
    student_username: str


class ApiProcessingResult(BaseModel):
    redemption: ApiRedemption
    message: str


class ApiAdminError(BaseModel):
    detail: str | list[dict[str, Any]]
