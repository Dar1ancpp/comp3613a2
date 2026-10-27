"""IT-2.4/IT-2.5: strict 401/403 contracts and unchanged protected data.

Known status-code defects deliberately fail the final assertions. Do not mark
these cases xfail or accept the current HTTP 200 error pages as correct.
"""

import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from hmac import compare_digest
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from sqlmodel import select

from app.models.award import Award
from app.models.milestone import Milestone
from app.models.redemption import Redemption
from app.models.user import User
from app.models.volunteer_submission import VolunteerSubmission
from app.repositories.user import UserRepository
from app.schemas.user import AdminCreate, RegularUserCreate
from app.utilities.security import create_access_token, encrypt_password

FIXTURE_TIME = datetime.fromisoformat("2026-10-20T09:00:00")
PRIVATE_EVIDENCE = "Private evidence belonging to student B"


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
    def create_user(role="regular_user"):
        username = f"auth_{uuid4().hex}"
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
        return Account(user_id=user_id, username=username, password=password)

    return create_user


def log_in_student(client, account):
    response = client.post(
        "/login", data={"username": account.username, "password": account.password}
    )
    assert response.status_code == 303
    assert urlsplit(response.headers["location"]).path == "/app"
    authenticated = "access_token" in client.cookies
    assert authenticated
    dashboard = client.get(response.headers["location"])
    assert dashboard.status_code == 200
    assert f"Signed in as {account.username}" in dashboard.text


def database_snapshot(session_factory):
    """Snapshot all domain rows; never include password hashes in public diffs."""
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
        pytest.fail(
            "Protected operation changed a user's password hash.", pytrace=False
        )


def valid_hour_form():
    return {
        "activity_name": "Unauthorized submission attempt",
        "organization": "Campus Volunteers",
        "hours": "4",
        "activity_date": "2026-10-20",
        "supporting_information": "Must not be saved",
    }


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param("expired", id="IT-2.4-expired-token"),
        pytest.param("logout", id="IT-2.4-after-logout"),
    ],
)
def test_it_2_4_logout_and_unauthenticated_requests(
    client, session_factory, user_factory, scenario
):
    account = user_factory()
    if scenario == "logout":
        log_in_student(client, account)
        response = client.get("/logout")
        assert response.status_code == 303
        assert urlsplit(response.headers["location"]).path == "/login"
        authenticated = "access_token" in client.cookies
        assert authenticated is False
        cookies = SimpleCookie()
        for header in response.headers.get_list("set-cookie"):
            cookies.load(header)
        deletion = cookies.get("access_token")
        removed = (
            deletion is not None and deletion.value == "" and deletion["max-age"] == "0"
        )
        assert removed, "Logout must expire the authentication cookie."
    elif scenario == "expired":
        token = create_access_token(
            {"sub": str(account.user_id), "role": "regular_user"},
            expires_delta=timedelta(minutes=-1),
        )
        client.cookies.set("access_token", token)

    before = database_snapshot(session_factory)
    observed = {}
    for path, protected_marker in (
        ("/app/hours", "My submissions"),
        ("/app/progress", "My Progress"),
        ("/app/awards", "My Redemptions"),
    ):
        response = client.get(path)
        observed[f"GET {path}"] = response.status_code
        assert protected_marker not in response.text
    response = client.post("/app/hours", data=valid_hour_form())
    observed["POST /app/hours"] = response.status_code
    assert 'id="activity_name"' not in response.text
    assert_database_unchanged(session_factory, before)

    # Assert last so a bad status does not prevent the other safety checks.
    expected = dict.fromkeys(observed, 401)
    assert observed == expected, "Missing/invalid authentication must return HTTP 401."


def test_it_2_5_student_denied_administrator_operations(
    client, session_factory, user_factory
):
    student_a = user_factory()
    student_b = user_factory()
    administrator = user_factory("admin")
    with session_factory() as session:
        award = Award(
            name="Protected Award",
            description="Original catalogue entry",
            required_hours=Decimal(10),
            quantity_available=2,
            active=True,
        )
        session.add(award)
        session.commit()
        session.refresh(award)
        award_id = award.id
        verified = VolunteerSubmission(
            student_id=student_b.user_id,
            activity_name="Verified prerequisite",
            organization="Campus Volunteers",
            activity_date=date(2026, 10, 20),
            hours=Decimal(10),
            supporting_information="Verified eligibility fixture",
            submitted_at=FIXTURE_TIME,
            status="approved",
            reviewed_by=administrator.user_id,
            reviewed_at=FIXTURE_TIME,
        )
        pending = VolunteerSubmission(
            student_id=student_b.user_id,
            activity_name="Pending private activity",
            organization="Campus Volunteers",
            activity_date=date(2026, 10, 20),
            hours=Decimal(4),
            supporting_information=PRIVATE_EVIDENCE,
            submitted_at=FIXTURE_TIME,
        )
        redemption = Redemption(
            student_id=student_b.user_id,
            award_id=award_id,
            requested_at=FIXTURE_TIME,
        )
        session.add_all([verified, pending, redemption])
        session.commit()
        session.refresh(pending)
        session.refresh(redemption)
        submission_id, redemption_id = pending.id, redemption.id

    log_in_student(client, student_a)
    before = database_snapshot(session_factory)
    observed = {}
    for path in ("/admin", "/admin/approvals", "/admin/awards"):
        response = client.get(path)
        observed[f"GET {path}"] = response.status_code
        assert PRIVATE_EVIDENCE not in response.text
        assert "Pending private activity" not in response.text
        assert "Protected Award" not in response.text
        assert "<h1>Administrator dashboard</h1>" not in response.text

    award_form = {
        "name": "Unauthorized Award",
        "description": "Must not be saved",
        "required_hours": "1",
        "quantity_available": "42",
        "active": "true",
    }
    attempts = [
        ("create Award", "/admin/awards", award_form),
        ("edit Award", f"/admin/awards/{award_id}", award_form),
        (
            "approve hours",
            f"/admin/submissions/{submission_id}/review",
            {"decision": "approved"},
        ),
        (
            "reject hours",
            f"/admin/submissions/{submission_id}/review",
            {"decision": "rejected"},
        ),
        (
            "approve redemption",
            f"/admin/redemptions/{redemption_id}/process",
            {"decision": "approved"},
        ),
        (
            "reject redemption",
            f"/admin/redemptions/{redemption_id}/process",
            {"decision": "rejected"},
        ),
    ]
    for label, path, data in attempts:
        response = client.post(path, data=data)
        observed[f"POST {path} ({label})"] = response.status_code
        assert PRIVATE_EVIDENCE not in response.text

    assert_database_unchanged(session_factory, before)
    expected = dict.fromkeys(observed, 403)
    assert observed == expected, "A signed-in student must receive HTTP 403."
