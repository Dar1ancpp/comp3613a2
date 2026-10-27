"""IT-4.1 and IT-4.2: real progress aggregation, milestones and leaderboard."""

import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from html import unescape
from urllib.parse import urlsplit

import pytest
from sqlmodel import select

from app.models.milestone import Milestone
from app.models.volunteer_submission import VolunteerSubmission
from app.repositories.award import AwardRepository
from app.repositories.progress import ProgressRepository
from app.repositories.user import UserRepository
from app.repositories.volunteer_submission import VolunteerSubmissionRepository
from app.schemas.user import AdminCreate, RegularUserCreate
from app.services.volunteer_submission_service import VolunteerSubmissionService
from app.utilities.security import encrypt_password

FIXTURE_TIME = datetime.fromisoformat("2026-10-20T09:00:00")
MILESTONES = (
    {
        "name": "First Milestone",
        "description": "An initial contribution to the community.",
        "required_hours": Decimal("4.5"),
    },
    {
        "name": "Community Milestone",
        "description": "Continued service to the community.",
        "required_hours": Decimal(10),
    },
)


@dataclass
class Account:
    user_id: int
    username: str
    password: str = field(repr=False)


@pytest.fixture(autouse=True)
def hide_sql_parameters(monkeypatch, test_engine):
    monkeypatch.setattr(test_engine, "hide_parameters", True)


@pytest.fixture
def user_factory(session_factory):
    """Persist this case's accounts; only the current student needs to log in."""

    def create_user(username, role="regular_user"):
        password = secrets.token_urlsafe(24)
        schema = AdminCreate if role == "admin" else RegularUserCreate
        with session_factory() as session:
            user = UserRepository(session).create(
                schema(
                    username=username,
                    email=f"{username.lower()}@example.com",
                    password=encrypt_password(password),
                )
            )
            return Account(user.id, username, password)

    return create_user


def login_student(client, account):
    response = client.post(
        "/login", data={"username": account.username, "password": account.password}
    )
    assert response.status_code == 303
    assert urlsplit(response.headers["location"]).path == "/app"
    authenticated = "access_token" in client.cookies
    assert authenticated


def persist_submissions(session_factory, reviewer_id, records):
    """Committed setup rows, not mocked aggregate results or HTTP responses."""
    with session_factory() as session:
        for account, hours, status in records:
            session.add(
                VolunteerSubmission(
                    student_id=account.user_id,
                    activity_name=f"{account.username} {status} service",
                    organization="Campus Volunteers",
                    hours=Decimal(hours),
                    activity_date=date(2026, 10, 20),
                    supporting_information="Recorded fixture evidence",
                    status=status,
                    submitted_at=FIXTURE_TIME,
                    reviewed_by=reviewer_id if status != "pending" else None,
                    reviewed_at=FIXTURE_TIME if status != "pending" else None,
                )
            )
        session.commit()


def persist_milestones(session_factory):
    # Deliberately insert the higher threshold first to exercise the SQL ORDER BY.
    with session_factory() as session:
        for details in reversed(MILESTONES):
            session.add(Milestone(**details))
        session.commit()


def progress_records(session_factory):
    """Fresh-session snapshots prove the read views leave source data intact."""
    with session_factory() as session:
        return {
            model.__tablename__: [
                row.model_dump()
                for row in session.exec(select(model).order_by(model.id)).all()
            ]
            for model in (VolunteerSubmission, Milestone)
        }


def assert_milestone_output(page, expected_states):
    expected = [
        {**details, "completed": completed, "percentage": percentage}
        for details, (completed, percentage) in zip(
            MILESTONES, expected_states, strict=bool(expected_states)
        )
    ]
    assert page.context["progress"]["milestones"] == expected
    cards = re.findall(
        r'<article class="milestone-item">(.*?)</article>', page.text, re.DOTALL
    )
    assert len(cards) == len(expected)
    if not expected:
        assert "No milestones have been configured yet." in page.text
    for card, milestone in zip(cards, expected, strict=True):
        assert milestone["name"] in card
        assert milestone["description"] in card
        assert f'aria-valuenow="{milestone["percentage"]}"' in card
        assert f"width: {milestone['percentage']}%" in card
        assert (">Complete</span>" in card) is milestone["completed"]
        if not milestone["completed"]:
            threshold = format(milestone["required_hours"], "f")
            assert f" / {threshold} hrs</span>" in card


def rendered_leaderboard(page):
    """Read only the leaderboard's rendered table, including its current marker."""
    section = page.text.split('aria-labelledby="leaderboard-heading"', 1)[1]
    body = re.search(r"<tbody>(.*?)</tbody>", section, re.DOTALL)
    assert body is not None
    rows = re.findall(r'<tr class="([^"]*)">(.*?)</tr>', body[1], re.DOTALL)
    return [
        (
            row_class,
            [
                " ".join(unescape(re.sub(r"<[^>]+>", "", cell)).split())
                for cell in re.findall(r"<td[^>]*>(.*?)</td>", cells, re.DOTALL)
            ],
        )
        for row_class, cells in rows
    ]


def test_it_4_1_approved_totals_and_milestone_output(
    client, session_factory, user_factory
):
    expected_total = Decimal("4.5")
    milestone_states = [(True, 100), (False, 45.0)]
    student = user_factory("StudentA")
    other_student = user_factory("StudentB")
    administrator = user_factory("Reviewer", "admin")
    records = [
        (student, "8", "pending"),
        (other_student, "20", "approved"),
        (student, "6", "rejected"),
        (student, "4", "approved"),
        (student, "0.5", "approved"),
    ]
    persist_submissions(session_factory, administrator.user_id, records)
    persist_milestones(session_factory)
    before = progress_records(session_factory)
    assert [row["required_hours"] for row in before["milestone"]] == [
        Decimal(10),
        Decimal("4.5"),
    ]

    with session_factory() as session:
        assert (
            VolunteerSubmissionService(
                VolunteerSubmissionRepository(session)
            ).verified_hours(student.user_id)
            == expected_total
        )
    with session_factory() as session:
        assert (
            AwardRepository(session).verified_hours(student.user_id) == expected_total
        )

    login_student(client, student)
    page = client.get("/app/progress")
    assert page.status_code == 200
    assert page.context["progress"]["verified_hours"] == expected_total
    assert f"<span>Verified hours</span><strong>{expected_total}</strong>" in page.text
    assert_milestone_output(page, milestone_states)

    # IT-4.1 requires the shared verified-total display, not Award operations.
    awards = client.get("/app/awards")
    assert awards.status_code == 200
    assert awards.context["catalogue"]["verified_hours"] == expected_total
    assert (
        f"<span>Verified hours</span><strong>{expected_total}</strong>" in awards.text
    )
    assert progress_records(session_factory) == before


def test_it_4_2_multistudent_leaderboard_ordering_and_dense_ranks(
    client, session_factory, user_factory
):
    # Neither insertion order nor IDs should determine totals or tied ordering.
    users = {
        name: user_factory(name, "admin" if name == "Manager" else "regular_user")
        for name in ("Eve", "Dan", "Manager", "Ben", "Cara", "Alice")
    }
    persist_submissions(
        session_factory,
        users["Manager"].user_id,
        [
            (users["Ben"], "10", "approved"),
            (users["Eve"], "30", "rejected"),
            (users["Manager"], "50", "approved"),
            (users["Cara"], "4.5", "approved"),
            (users["Eve"], "25", "pending"),
            (users["Alice"], "6", "approved"),
            (users["Alice"], "4", "approved"),
        ],
    )
    persist_milestones(session_factory)
    before = progress_records(session_factory)
    expected_totals = [
        (users[name].user_id, name, Decimal(hours))
        for name, hours in (
            ("Alice", "10"),
            ("Ben", "10"),
            ("Cara", "4.5"),
            ("Dan", "0"),
            ("Eve", "0"),
        )
    ]

    login_student(client, users["Ben"])
    page = client.get("/app/progress")
    assert page.status_code == 200
    progress = page.context["progress"]
    assert progress["leaderboard"] == [
        {
            "student_id": student_id,
            "username": name,
            "verified_hours": hours,
            "rank": rank,
            "is_current": name == "Ben",
        }
        for (student_id, name, hours), rank in zip(
            expected_totals, (1, 1, 2, 3, 3), strict=True
        )
    ]
    assert progress["verified_hours"] == Decimal(10)
    assert progress["rank"] == 1
    assert "<span>Leaderboard rank</span><strong>#1</strong>" in page.text
    assert rendered_leaderboard(page) == [
        ("", ["#1", "Alice", "10"]),
        ("current-student", ["#1", "You (Ben)", "10"]),
        ("", ["#2", "Cara", "4.5"]),
        ("", ["#3", "Dan", "0"]),
        ("", ["#3", "Eve", "0"]),
    ]
    # Ben is above the first threshold and exactly at the second; both cap at 100.
    assert_milestone_output(page, [(True, 100), (True, 100)])

    with session_factory() as session:
        totals = ProgressRepository(session).leaderboard_totals()
        assert totals == expected_totals
    assert progress_records(session_factory) == before
