"""Volunteer Hours units: approved plan cases UT-1.1 through UT-1.4.

Only in-memory models and repository mocks are used. Connection guards fail
the test if database or network access is attempted during a test invocation.
"""

import socket
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import create_autospec

import pytest
from sqlalchemy.engine import Engine

from app.models.volunteer_submission import VolunteerSubmission
from app.repositories.volunteer_submission import VolunteerSubmissionRepository
from app.services import volunteer_submission_service as service_module
from app.services.volunteer_submission_service import VolunteerSubmissionService

# Intentionally naive UTC to match the existing review service's timestamps.
REVIEW_TIME = datetime(2026, 10, 27, 12, 0, 0)  # noqa: DTZ001
ORIGINAL_REVIEW_TIME = datetime(2026, 10, 26, 9, 0, 0)  # noqa: DTZ001


@pytest.fixture(autouse=True)
def forbid_database_and_network_connections(monkeypatch):
    """Enforce this module's unit-only boundary without opening connections."""

    def forbidden_connection(*args, **kwargs):
        pytest.fail("Volunteer Hours units must not connect to a database or network.")

    monkeypatch.setattr(Engine, "connect", forbidden_connection)
    monkeypatch.setattr(Engine, "raw_connection", forbidden_connection)
    monkeypatch.setattr(sqlite3, "connect", forbidden_connection)
    monkeypatch.setattr(socket.socket, "connect", forbidden_connection)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden_connection)


@pytest.fixture
def repository():
    return create_autospec(VolunteerSubmissionRepository, instance=True, spec_set=True)


@pytest.fixture
def service(repository):
    return VolunteerSubmissionService(repository)


@pytest.fixture
def submission_inputs():
    return {
        "student_id": 101,
        "activity_name": "Beach Cleanup",
        "organization": "Campus Volunteers",
        "hours": Decimal(4),
        "activity_date": date(2026, 10, 20),
        "supporting_information": "Confirmed by organizer",
    }


@pytest.fixture
def pending_submission(submission_inputs):
    return VolunteerSubmission(id=301, **submission_inputs)


@pytest.fixture
def fixed_review_clock(monkeypatch):
    class FixedClock:
        @staticmethod
        def utcnow():
            return REVIEW_TIME

    monkeypatch.setattr(service_module, "datetime", FixedClock)


def test_ut_1_1_valid_submission_and_defaults(service, repository, submission_inputs):
    hours = Decimal("0.01")
    supporting_information = "   "
    expected_support = ""
    submission_inputs.update(
        activity_name="  Beach Cleanup  ",
        organization="  Campus Volunteers  ",
        hours=hours,
        supporting_information=supporting_information,
    )
    repository.create.side_effect = lambda submission: submission

    result = service.submit(**submission_inputs)

    repository.create.assert_called_once_with(result)
    assert result is repository.create.call_args.args[0]
    assert isinstance(result, VolunteerSubmission)
    assert result.student_id == 101
    assert result.activity_name == "Beach Cleanup"
    assert result.organization == "Campus Volunteers"
    assert result.activity_date == date(2026, 10, 20)
    assert result.hours == hours
    assert isinstance(result.hours, Decimal)
    assert result.supporting_information == expected_support
    assert result.status == "pending"
    assert isinstance(result.submitted_at, datetime)
    assert result.reviewed_by is None
    assert result.reviewed_at is None


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        pytest.param(
            "organization",
            "   ",
            "Activity name and organization are required.",
            id="UT-1.2-whitespace-organization",
        ),
        pytest.param(
            "hours",
            Decimal(0),
            "Hours must be greater than zero.",
            id="UT-1.2-zero-hours",
        ),
        pytest.param(
            "hours",
            Decimal("-0.25"),
            "Hours must be greater than zero.",
            id="UT-1.2-negative-hours",
        ),
    ],
)
def test_ut_1_2_invalid_submission_values(
    service, repository, submission_inputs, field, value, error
):
    submission_inputs[field] = value

    with pytest.raises(ValueError) as exc_info:
        service.submit(**submission_inputs)

    assert str(exc_info.value) == error
    repository.create.assert_not_called()
    repository.save.assert_not_called()


def test_ut_1_3_review_pending_submission(
    service, repository, pending_submission, fixed_review_clock
):
    decision = "  ApPrOvEd  "
    expected_status = "approved"
    repository.get_by_id.return_value = pending_submission
    repository.save.side_effect = lambda submission: submission
    activity_before = pending_submission.model_dump(
        exclude={"status", "reviewed_by", "reviewed_at"}
    )

    result = service.review(submission_id=301, reviewer_id=900, decision=decision)

    repository.get_by_id.assert_called_once_with(301)
    repository.save.assert_called_once_with(pending_submission)
    assert result is pending_submission
    assert result.status == expected_status
    assert result.reviewed_by == 900
    assert result.reviewed_at == REVIEW_TIME
    assert (
        result.model_dump(exclude={"status", "reviewed_by", "reviewed_at"})
        == activity_before
    )
    repository.create.assert_not_called()


def test_ut_1_4_invalid_decision_precedes_lookup(
    service, repository, pending_submission
):
    decision = "pending"
    repository.get_by_id.return_value = pending_submission
    before = pending_submission.model_dump()

    with pytest.raises(
        ValueError, match="^Review decision must be approved or rejected\\.$"
    ):
        service.review(submission_id=301, reviewer_id=900, decision=decision)

    repository.get_by_id.assert_not_called()
    repository.save.assert_not_called()
    repository.create.assert_not_called()
    assert pending_submission.model_dump() == before
