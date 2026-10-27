"""JSON contracts for owned volunteer submissions."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiVolunteerSubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    activity_name: str
    organization: str
    hours: Decimal = Field(allow_inf_nan=False)
    activity_date: date
    supporting_information: str = ""


class ApiVolunteerSubmission(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    activity_name: str
    organization: str
    hours: Decimal
    activity_date: date
    supporting_information: str
    status: Literal["pending", "approved", "rejected"]
    submitted_at: datetime
    reviewed_by: int | None
    reviewed_at: datetime | None


class ApiSubmissionValidationError(BaseModel):
    # Service errors have a message; JSON binding errors have structured details.
    detail: str | list[dict[str, Any]]
