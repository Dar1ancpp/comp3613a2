"""IT-6.2 to IT-6.4: request validation, duplicate scope and private history.

The complete IT-6.1 lifecycle resides in test_redemption_processing.py.
"""

import secrets
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from app.models.award import Award
from app.models.redemption import Redemption
from app.models.volunteer_submission import VolunteerSubmission
from app.repositories.award import AwardRepository
from app.repositories.user import UserRepository
from app.schemas.user import AdminCreate, RegularUserCreate
from app.utilities.security import encrypt_password

FIXTURE_TIME = datetime.fromisoformat("2026-10-20T09:00:00")


@dataclass
class Actor:
    user_id: int
    client: TestClient = field(repr=False)


@pytest.fixture(autouse=True)
def hide_sql_parameters(monkeypatch, test_engine):
    monkeypatch.setattr(test_engine, "hide_parameters", True)


@pytest.fixture
def actor_factory(app, session_factory):
    with ExitStack() as clients:

        def create_actor(role="regular_user"):
            username = f"request_{uuid4().hex}"
            password = secrets.token_urlsafe(24)
            schema = AdminCreate if role == "admin" else RegularUserCreate
            with session_factory() as session:
                user = UserRepository(session).create(
                    schema(
                        username=username,
                        email=f"{username}@example.com",
                        password=encrypt_password(password),
                    )
                )
                user_id = user.id
            client = clients.enter_context(TestClient(app, follow_redirects=False))
            response = client.post(
                "/login", data={"username": username, "password": password}
            )
            assert response.status_code == 303
            destination = "/admin" if role == "admin" else "/app"
            assert urlsplit(response.headers["location"]).path == destination
            authenticated = "access_token" in client.cookies
            assert authenticated
            return Actor(user_id, client)

        yield create_actor


def records(session_factory, model):
    with session_factory() as session:
        return [
            row.model_dump()
            for row in session.exec(select(model).order_by(model.id)).all()
        ]


def source_records(session_factory):
    return {
        "awards": records(session_factory, Award),
        "hours": records(session_factory, VolunteerSubmission),
    }


def verified_hours(session_factory, student):
    with session_factory() as session:
        return AwardRepository(session).verified_hours(student.user_id)


def seed_hours(
    session_factory,
    student,
    administrator,
    hours="10",
    status="approved",
    marker="Service",
):
    with session_factory() as session:
        session.add(
            VolunteerSubmission(
                student_id=student.user_id,
                activity_name=marker,
                organization="Campus Volunteers",
                hours=Decimal(hours),
                activity_date=date(2026, 10, 20),
                supporting_information="Fixture attendance evidence",
                status=status,
                submitted_at=FIXTURE_TIME,
                reviewed_by=administrator.user_id if status != "pending" else None,
                reviewed_at=FIXTURE_TIME if status != "pending" else None,
            )
        )
        session.commit()


def seed_award(session_factory, name="Shared Request Award", active=True):
    with session_factory() as session:
        award = AwardRepository(session).save_award(
            Award(
                name=name,
                description="A demonstration Award",
                required_hours=Decimal(10),
                quantity_available=1,
                active=active,
            )
        )
        return award.id


def seed_history(session_factory, student, award_id, administrator, status):
    with session_factory() as session:
        row = Redemption(
            student_id=student.user_id,
            award_id=award_id,
            status=status,
            requested_at=FIXTURE_TIME,
            processed_by=administrator.user_id if status != "pending" else None,
            processed_at=FIXTURE_TIME if status != "pending" else None,
        )
        session.add(row)
        session.commit()


def utc_now():
    # Existing application timestamps are naive UTC; compare like with like.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def request_award(student, award_id, feedback, extra=None):
    after = utc_now() - timedelta(seconds=1)
    response = student.client.post(f"/app/awards/{award_id}/redeem", data=extra or {})
    before = utc_now() + timedelta(seconds=1)
    assert response.status_code == 303
    assert urlsplit(response.headers["location"]).path == "/app/awards"
    page = student.client.get(response.headers["location"])
    assert page.status_code == 200
    assert feedback in page.text
    return page, after, before


def assert_pending(row, student, award_id, after, before):
    assert row["student_id"] == student.user_id
    assert row["award_id"] == award_id
    assert row["status"] == "pending"
    assert after <= row["requested_at"] <= before
    assert row["processed_by"] is None
    assert row["processed_at"] is None


def private_section(page, heading):
    assert page.status_code == 200
    return page.text.split(f'aria-labelledby="{heading}"', 1)[1].split("</section>", 1)[
        0
    ]


def assert_private_histories(
    student,
    session_factory,
    own_activity_names,
    other_activity_names,
    own_award_names,
    other_award_names,
    query="",
):
    hours_page = student.client.get(f"/app/hours{query}")
    submissions = hours_page.context["submissions"]
    expected_submissions = [
        row
        for row in records(session_factory, VolunteerSubmission)
        if row["student_id"] == student.user_id
    ]
    assert sorted(row.id for row in submissions) == sorted(
        row["id"] for row in expected_submissions
    )
    assert all(row.student_id == student.user_id for row in submissions)
    history = private_section(hours_page, "history-heading")
    for name in own_activity_names:
        assert name in history
    for name in other_activity_names:
        assert name not in history

    awards_page = student.client.get(f"/app/awards{query}")
    redemptions = awards_page.context["catalogue"]["redemptions"]
    expected_redemptions = [
        row
        for row in records(session_factory, Redemption)
        if row["student_id"] == student.user_id
    ]
    assert sorted(row.id for row, award in redemptions) == sorted(
        row["id"] for row in expected_redemptions
    )
    assert all(row.student_id == student.user_id for row, award in redemptions)
    history = private_section(awards_page, "redemptions-heading")
    for name in own_award_names:
        assert name in history
    for name in other_award_names:
        assert name not in history
    assert awards_page.context["catalogue"]["verified_hours"] == Decimal(10)


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param("unverified", id="IT-6.2-only-pending-and-rejected-hours"),
        pytest.param("inactive", id="IT-6.2-inactive-award"),
    ],
)
def test_it_6_2_ineligible_or_unavailable_redemption(
    actor_factory, session_factory, scenario
):
    student = actor_factory()
    administrator = actor_factory("admin")
    if scenario == "unverified":
        for status in ("pending", "rejected"):
            seed_hours(session_factory, student, administrator, status=status)
        expected_total = Decimal(0)
    else:
        hours = "9.75" if scenario == "insufficient" else "10"
        seed_hours(session_factory, student, administrator, hours=hours)
        expected_total = Decimal(hours)
    award_id = seed_award(session_factory, active=scenario != "inactive")
    target_id = award_id + 1000 if scenario == "missing" else award_id
    before_sources = source_records(session_factory)
    before_requests = records(session_factory, Redemption)
    catalogue = student.client.get("/app/awards")
    assert catalogue.status_code == 200
    if scenario in {"insufficient", "unverified"}:
        assert catalogue.context["catalogue"]["awards"][0]["eligible"] is False
        assert "disabled>Locked</button>" in catalogue.text
        feedback = "You have not earned enough verified hours for this Award."
    else:
        if scenario == "inactive":
            assert catalogue.context["catalogue"]["awards"] == []
        feedback = "This Award is not available."

    request_award(student, target_id, feedback)

    assert records(session_factory, Redemption) == before_requests == []
    assert source_records(session_factory) == before_sources
    assert verified_hours(session_factory, student) == expected_total


@pytest.mark.parametrize(
    ("existing_owner", "existing_award", "existing_status", "blocked"),
    [
        pytest.param("A", "V", "pending", True, id="IT-6.3-same-pending-blocked"),
        pytest.param("A", "V", "approved", False, id="IT-6.3-repeat-after-approved"),
    ],
)
def test_it_6_3_pending_duplicate_scope_and_repeat_requests(
    actor_factory,
    session_factory,
    existing_owner,
    existing_award,
    existing_status,
    blocked,
):
    student = actor_factory()
    other_student = actor_factory()
    administrator = actor_factory("admin")
    for owner in (student, other_student):
        seed_hours(session_factory, owner, administrator)
    award_id = seed_award(session_factory)
    other_award_id = seed_award(session_factory, name="Other Award")
    seed_history(
        session_factory,
        student if existing_owner == "A" else other_student,
        award_id if existing_award == "V" else other_award_id,
        administrator,
        existing_status,
    )
    if not blocked:
        # One realistic history contains every nonmatching predicate together:
        # own nonpending V, another student's pending V and own pending other Award.
        # The single POST below must ignore all three without modifying any of them.
        seed_history(session_factory, other_student, award_id, administrator, "pending")
        seed_history(session_factory, student, other_award_id, administrator, "pending")
    before_requests = records(session_factory, Redemption)
    before_sources = source_records(session_factory)
    feedback = (
        "You already have a pending request for this Award."
        if blocked
        else "Award redemption requested."
    )

    page, after, before = request_award(student, award_id, feedback)

    rows = records(session_factory, Redemption)
    old_ids = {row["id"] for row in before_requests}
    assert [row for row in rows if row["id"] in old_ids] == before_requests
    new_rows = [row for row in rows if row["id"] not in old_ids]
    assert len(new_rows) == (0 if blocked else 1)
    if blocked:
        assert rows == before_requests
    else:
        assert_pending(new_rows[0], student, award_id, after, before)
    scoped_pending = [
        row
        for row in rows
        if row["student_id"] == student.user_id
        and row["award_id"] == award_id
        and row["status"] == "pending"
    ]
    assert len(scoped_pending) == 1
    target = next(
        item
        for item in page.context["catalogue"]["awards"]
        if item["award"].id == award_id
    )
    assert target["pending"] is True
    assert source_records(session_factory) == before_sources
    for owner in (student, other_student):
        assert verified_hours(session_factory, owner) == Decimal(10)


def test_it_6_4_student_histories_and_submitted_owner_spoofing(
    actor_factory, session_factory
):
    student = actor_factory()
    other_student = actor_factory()
    administrator = actor_factory("admin")
    seed_hours(session_factory, student, administrator, marker="A private activity")
    seed_hours(
        session_factory, other_student, administrator, marker="B private activity"
    )
    award_id = seed_award(session_factory)
    history_a = seed_award(session_factory, name="A History Award")
    history_b = seed_award(session_factory, name="B History Award")
    seed_history(session_factory, student, history_a, administrator, "rejected")
    seed_history(session_factory, other_student, history_b, administrator, "rejected")
    before_sources = source_records(session_factory)
    before_requests = records(session_factory, Redemption)
    assert_private_histories(
        student,
        session_factory,
        ["A private activity"],
        ["B private activity"],
        ["A History Award"],
        ["B History Award"],
        query=f"?student_id={other_student.user_id}",
    )
    assert source_records(session_factory) == before_sources
    assert records(session_factory, Redemption) == before_requests

    response = student.client.post(
        "/app/hours",
        data={
            "student_id": other_student.user_id,
            "activity_name": "A spoofed-owner activity",
            "organization": "Campus Volunteers",
            "hours": "0.5",
            "activity_date": "2026-10-20",
            "supporting_information": "Owner must come from the cookie",
        },
    )
    assert response.status_code == 303
    assert urlsplit(response.headers["location"]).path == "/app/hours"
    hours_page = student.client.get(response.headers["location"])
    assert hours_page.status_code == 200
    assert "Volunteer hours submitted for review." in hours_page.text
    after_hours = records(session_factory, VolunteerSubmission)
    old_hour_ids = {row["id"] for row in before_sources["hours"]}
    assert [row for row in after_hours if row["id"] in old_hour_ids] == before_sources[
        "hours"
    ]
    added_hours = [row for row in after_hours if row["id"] not in old_hour_ids]
    assert len(added_hours) == 1
    assert added_hours[0]["student_id"] == student.user_id
    assert added_hours[0]["activity_name"] == "A spoofed-owner activity"
    assert added_hours[0]["hours"] == Decimal("0.5")
    assert added_hours[0]["status"] == "pending"

    page, after, before = request_award(
        student,
        award_id,
        "Award redemption requested.",
        extra={"student_id": other_student.user_id},
    )
    rows = records(session_factory, Redemption)
    old_ids = {row["id"] for row in before_requests}
    assert [row for row in rows if row["id"] in old_ids] == before_requests
    new_requests = [row for row in rows if row["id"] not in old_ids]
    assert len(new_requests) == 1
    assert_pending(new_requests[0], student, award_id, after, before)
    assert page.context["catalogue"]["verified_hours"] == Decimal(10)
    assert_private_histories(
        student,
        session_factory,
        ["A private activity", "A spoofed-owner activity"],
        ["B private activity"],
        ["A History Award", "Shared Request Award"],
        ["B History Award"],
        query=f"?student_id={other_student.user_id}",
    )
    assert_private_histories(
        other_student,
        session_factory,
        ["B private activity"],
        ["A private activity", "A spoofed-owner activity"],
        ["B History Award"],
        ["A History Award", "Shared Request Award"],
        query=f"?student_id={student.user_id}",
    )
    assert records(session_factory, Award) == before_sources["awards"]
    assert records(session_factory, VolunteerSubmission) == after_hours
    assert records(session_factory, Redemption) == rows
    for owner in (student, other_student):
        assert verified_hours(session_factory, owner) == Decimal(10)
