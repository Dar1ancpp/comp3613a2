"""IT-3.1 to IT-3.3: real volunteer submissions, review and persistence."""

import secrets
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hmac import compare_digest
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from app.models.award import Award
from app.models.milestone import Milestone
from app.models.redemption import Redemption
from app.models.user import User
from app.models.volunteer_submission import VolunteerSubmission
from app.repositories.user import UserRepository
from app.repositories.volunteer_submission import VolunteerSubmissionRepository
from app.schemas.user import AdminCreate, RegularUserCreate
from app.services.volunteer_submission_service import VolunteerSubmissionService
from app.utilities.security import encrypt_password

FIXTURE_TIME = datetime.fromisoformat("2026-10-20T09:00:00")


@dataclass
class Actor:
    user_id: int
    username: str
    client: TestClient = field(repr=False)


@pytest.fixture(autouse=True)
def hide_sql_parameters(monkeypatch, test_engine):
    monkeypatch.setattr(test_engine, "hide_parameters", True)


@pytest.fixture
def actor_factory(app, session_factory):
    """Real users and logins with separate cookie jars, closed before cleanup."""
    with ExitStack() as clients:

        def create_actor(role="regular_user"):
            username = f"hours_{role}_{uuid4().hex}"
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
            return Actor(user_id=user_id, username=username, client=client)

        yield create_actor


def valid_hour_form():
    return {
        "activity_name": "  Beach Cleanup  ",
        "organization": "  Campus Volunteers  ",
        "hours": "4",
        "activity_date": "2026-10-20",
        "supporting_information": "  Confirmed by organizer  ",
    }


def submission_records(session_factory):
    with session_factory() as session:
        return [
            row.model_dump()
            for row in session.exec(
                select(VolunteerSubmission).order_by(VolunteerSubmission.id)
            ).all()
        ]


def verified_hours(session_factory, student_id):
    with session_factory() as session:
        return VolunteerSubmissionService(
            VolunteerSubmissionRepository(session)
        ).verified_hours(student_id)


def seed_submission(session_factory, student, administrator=None, status="pending"):
    with session_factory() as session:
        row = VolunteerSubmission(
            student_id=student.user_id,
            activity_name="Existing fixture activity",
            organization="Campus Volunteers",
            activity_date=date(2026, 10, 20),
            hours=Decimal(4),
            supporting_information="Existing fixture evidence",
            submitted_at=FIXTURE_TIME,
            status=status,
            reviewed_by=administrator.user_id if status != "pending" else None,
            reviewed_at=FIXTURE_TIME if status != "pending" else None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def database_snapshot(session_factory):
    """Compare all domain rows while keeping password hashes out of diffs."""
    public_rows = {}
    password_hashes = {}
    with session_factory() as session:
        for model in (User, VolunteerSubmission, Milestone, Award, Redemption):
            rows = session.exec(select(model).order_by(model.id)).all()
            public_rows[model.__tablename__] = [
                row.model_dump(exclude={"password"}) for row in rows
            ]
            if model is User:
                password_hashes = {row.id: row.password for row in rows}
    return public_rows, password_hashes


def assert_database_unchanged(session_factory, before):
    before_rows, before_hashes = before
    after_rows, after_hashes = database_snapshot(session_factory)
    assert after_rows == before_rows
    unchanged = before_hashes.keys() == after_hashes.keys() and all(
        compare_digest(value, after_hashes[user_id])
        for user_id, value in before_hashes.items()
    )
    if not unchanged:
        pytest.fail("Failed operation changed a user's password hash.", pytrace=False)


def utc_now():
    # The current application stores UTC timestamps without timezone information.
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.mark.parametrize(
    ("hours", "decision", "support", "expected_support"),
    [
        pytest.param(
            Decimal(4),
            "approved",
            "  Confirmed by organizer  ",
            "Confirmed by organizer",
            id="IT-3.1-whole-hours-approved",
        ),
        pytest.param(
            Decimal("4.5"), "rejected", "   ", "", id="IT-3.1-fractional-hours-rejected"
        ),
    ],
)
def test_it_3_1_submission_persistence_and_administrator_review(
    actor_factory, session_factory, hours, decision, support, expected_support
):
    student = actor_factory()
    administrator = actor_factory("admin")
    assert submission_records(session_factory) == []
    form = valid_hour_form()
    form.update(hours=str(hours), supporting_information=support)

    submitted_after = utc_now() - timedelta(seconds=1)
    response = student.client.post("/app/hours", data=form)
    submitted_before = utc_now() + timedelta(seconds=1)

    assert response.status_code == 303
    assert urlsplit(response.headers["location"]).path == "/app/hours"
    history = student.client.get(response.headers["location"])
    assert history.status_code == 200
    assert "Volunteer hours submitted for review." in history.text
    assert f"<td>{hours}</td>" in history.text
    assert ">Pending</span>" in history.text
    records = submission_records(session_factory)
    assert len(records) == 1
    pending = records[0]
    submission_id = pending["id"]
    assert pending["student_id"] == student.user_id
    assert pending["activity_name"] == "Beach Cleanup"
    assert pending["organization"] == "Campus Volunteers"
    assert pending["activity_date"] == date(2026, 10, 20)
    assert pending["hours"] == hours
    assert pending["supporting_information"] == expected_support
    assert pending["status"] == "pending"
    assert submitted_after <= pending["submitted_at"] <= submitted_before
    assert pending["reviewed_by"] is None
    assert pending["reviewed_at"] is None
    assert verified_hours(session_factory, student.user_id) == 0

    queue = administrator.client.get("/admin/approvals")
    assert queue.status_code == 200
    queue_ids = [row.id for row, owner in queue.context["pending_submissions"]]
    assert submission_id in queue_ids
    for detail in (
        student.username,
        "Beach Cleanup",
        "Campus Volunteers",
        "20 Oct 2026",
        expected_support or "None provided",
    ):
        assert detail in queue.text

    reviewed_after = utc_now() - timedelta(seconds=1)
    response = administrator.client.post(
        f"/admin/submissions/{submission_id}/review", data={"decision": decision}
    )
    reviewed_before = utc_now() + timedelta(seconds=1)

    assert response.status_code == 303
    assert urlsplit(response.headers["location"]).path == "/admin/approvals"
    queue = administrator.client.get(response.headers["location"])
    assert queue.status_code == 200
    assert f"Submission {decision}." in queue.text
    queue_ids = [row.id for row, owner in queue.context["pending_submissions"]]
    assert submission_id not in queue_ids
    history = student.client.get("/app/hours")
    assert history.status_code == 200
    assert f">{decision.title()}</span>" in history.text
    records = submission_records(session_factory)
    assert len(records) == 1
    reviewed = records[0]
    assert reviewed["status"] == decision
    assert reviewed["reviewed_by"] == administrator.user_id
    assert reviewed_after <= reviewed["reviewed_at"] <= reviewed_before
    assert {
        key: value
        for key, value in reviewed.items()
        if key not in {"status", "reviewed_by", "reviewed_at"}
    } == {
        key: value
        for key, value in pending.items()
        if key not in {"status", "reviewed_by", "reviewed_at"}
    }
    assert verified_hours(session_factory, student.user_id) == (
        hours if decision == "approved" else Decimal(0)
    )


@pytest.mark.parametrize(
    ("field", "value", "status_code", "feedback"),
    [
        pytest.param(
            "activity_name", None, 422, "", id="IT-3.2-missing-required-field"
        ),
        pytest.param(
            "activity_name",
            "   ",
            303,
            "Activity name and organization are required.",
            id="IT-3.2-whitespace-activity",
        ),
    ],
)
def test_it_3_2_submission_validation_preserves_database(
    actor_factory, session_factory, field, value, status_code, feedback
):
    student = actor_factory()
    seed_submission(session_factory, student)
    before = database_snapshot(session_factory)
    form = valid_hour_form()
    if value is None:
        del form[field]
    else:
        form[field] = value

    response = student.client.post("/app/hours", data=form)

    assert response.status_code == status_code
    if status_code == 422:
        locations = [error["loc"][-1] for error in response.json()["detail"]]
        assert field in locations
    else:
        assert urlsplit(response.headers["location"]).path == "/app/hours"
        page = student.client.get(response.headers["location"])
        assert page.status_code == 200
        assert feedback in page.text
        assert "Existing fixture activity" in page.text
    assert_database_unchanged(session_factory, before)


def test_it_3_3_invalid_or_repeated_review_preserves_database(
    actor_factory, session_factory
):
    scenario = "reviewed"
    status = "approved"
    decision = "rejected"
    feedback = "Only pending submissions can be reviewed."
    student = actor_factory()
    administrator = actor_factory("admin")
    submission_id = seed_submission(session_factory, student, administrator, status)
    target_id = submission_id + 1000 if scenario == "missing" else submission_id
    before = database_snapshot(session_factory)

    response = administrator.client.post(
        f"/admin/submissions/{target_id}/review", data={"decision": decision}
    )

    assert response.status_code == 303
    assert urlsplit(response.headers["location"]).path == "/admin/approvals"
    page = administrator.client.get(response.headers["location"])
    assert page.status_code == 200
    assert feedback in page.text
    assert_database_unchanged(session_factory, before)
