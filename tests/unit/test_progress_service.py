"""Progress and Milestones units: approved plan cases UT-2.1 to UT-2.3.

Repository results are already ordered; SQL sorting and filtering belong to
integration tests. No database, HTTP client or application startup is used.
"""

import socket
import sqlite3
from decimal import Decimal
from unittest.mock import create_autospec

import pytest
from sqlalchemy.engine import Engine

from app.models.milestone import Milestone
from app.repositories.progress import ProgressRepository
from app.services.progress_service import ProgressService


@pytest.fixture(autouse=True)
def forbid_database_and_network_connections(monkeypatch):
    """Fail immediately if a unit invocation attempts external I/O."""

    def forbidden_connection(*args, **kwargs):
        pytest.fail("Progress units must not connect to a database or network.")

    monkeypatch.setattr(Engine, "connect", forbidden_connection)
    monkeypatch.setattr(Engine, "raw_connection", forbidden_connection)
    monkeypatch.setattr(sqlite3, "connect", forbidden_connection)
    monkeypatch.setattr(socket.socket, "connect", forbidden_connection)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden_connection)


@pytest.fixture
def repository():
    return create_autospec(ProgressRepository, instance=True, spec_set=True)


@pytest.fixture
def service(repository):
    return ProgressService(repository)


@pytest.fixture
def milestone():
    return Milestone(
        id=201,
        name="Bronze Volunteer",
        description="A strong start in community service.",
        required_hours=Decimal(10),
    )


def test_ut_2_1_dense_ranking_and_current_student(service, repository):
    repository.leaderboard_totals.return_value = [
        (101, "Alice", Decimal(10)),
        (102, "Ben", Decimal(10)),
        (103, "Cara", Decimal("4.5")),
        (104, "Dan", Decimal(0)),
    ]
    repository.list_milestones.return_value = []

    result = service.get_student_progress(student_id=102)

    assert [
        (
            entry["student_id"],
            entry["username"],
            entry["verified_hours"],
            entry["rank"],
            entry["is_current"],
        )
        for entry in result["leaderboard"]
    ] == [
        (101, "Alice", Decimal(10), 1, False),
        (102, "Ben", Decimal(10), 1, True),
        (103, "Cara", Decimal("4.5"), 2, False),
        (104, "Dan", Decimal(0), 3, False),
    ]
    assert result["verified_hours"] == Decimal(10)
    assert result["rank"] == 1
    assert result["milestones"] == []


def test_ut_2_2_empty_progress_and_missing_current_student(
    service, repository, milestone
):
    repository.leaderboard_totals.return_value = []
    repository.list_milestones.return_value = [milestone]

    result = service.get_student_progress(student_id=101)

    assert result["verified_hours"] == 0
    assert result["rank"] is None
    assert result["leaderboard"] == []
    assert result["milestones"] == [
        {
            "name": "Bronze Volunteer",
            "description": "A strong start in community service.",
            "required_hours": Decimal(10),
            "completed": False,
            "percentage": 0.0,
        }
    ]


def test_ut_2_3_milestone_boundaries_rounding_and_cap(service, repository, milestone):
    # One real service result can contain milestones below, at and above the
    # same student's total. Zero progress is independently covered by UT-2.2.
    hours = Decimal("9.75")
    milestones = [
        milestone,
        milestone.model_copy(
            update={"id": 202, "name": "Exact", "required_hours": Decimal("9.75")}
        ),
        milestone.model_copy(
            update={"id": 203, "name": "Exceeded", "required_hours": Decimal("9.5")}
        ),
        milestone.model_copy(
            update={"id": 204, "name": "One third", "required_hours": Decimal("29.25")}
        ),
    ]
    repository.leaderboard_totals.return_value = [(101, "Alice", hours)]
    repository.list_milestones.return_value = milestones

    result = service.get_student_progress(student_id=101)

    assert result["verified_hours"] == hours
    assert result["rank"] == 1
    assert result["milestones"] == [
        {
            "name": "Bronze Volunteer",
            "description": "A strong start in community service.",
            "required_hours": Decimal(10),
            "completed": False,
            "percentage": 97.5,
        },
        {
            "name": "Exact",
            "description": milestone.description,
            "required_hours": Decimal("9.75"),
            "completed": True,
            "percentage": 100,
        },
        {
            "name": "Exceeded",
            "description": milestone.description,
            "required_hours": Decimal("9.5"),
            "completed": True,
            "percentage": 100,
        },
        {
            "name": "One third",
            "description": milestone.description,
            "required_hours": Decimal("29.25"),
            "completed": False,
            "percentage": 33.3,
        },
    ]
