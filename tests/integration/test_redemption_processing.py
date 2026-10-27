"""IT-6.1's complete request lifecycle and IT-7.1 to IT-7.3 processing guards."""

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
    """Authenticate each actor through real login with independent cookies."""
    with ExitStack() as clients:

        def create_actor(role="regular_user"):
            username = f"processing_{uuid4().hex}"
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


@pytest.fixture
def processing_setup(actor_factory, session_factory):
    """Independent eligible student/admin and an active Award; no requests yet."""
    student = actor_factory()
    administrator = actor_factory("admin")
    with session_factory() as session:
        session.add(
            VolunteerSubmission(
                student_id=student.user_id,
                activity_name="Verified community service",
                organization="Campus Volunteers",
                hours=Decimal(10),
                activity_date=date(2026, 10, 20),
                supporting_information="Verified fixture attendance",
                status="approved",
                submitted_at=FIXTURE_TIME,
                reviewed_by=administrator.user_id,
                reviewed_at=FIXTURE_TIME,
            )
        )
        # Default stock 2 suits IT-7.1/7.3; boundary journeys set it to 1.
        award = AwardRepository(session).save_award(
            Award(
                name="Community Recognition Award",
                description="Recognition for verified service",
                required_hours=Decimal(10),
                quantity_available=2,
                active=True,
            )
        )
        award_id = award.id
    return student, administrator, award_id


def records(session_factory, model):
    with session_factory() as session:
        return [
            row.model_dump()
            for row in session.exec(select(model).order_by(model.id)).all()
        ]


def snapshot(session_factory):
    return {
        model.__tablename__: records(session_factory, model)
        for model in (Award, Redemption, VolunteerSubmission)
    }


def set_fixture_stock(session_factory, award_id, quantity):
    with session_factory() as session:
        repository = AwardRepository(session)
        award = repository.get_award(award_id)
        award.quantity_available = quantity
        repository.save_award(award)


def seed_request(session_factory, student, administrator, award_id, status="pending"):
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
        session.refresh(row)
        return row.id


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def follow_redirect(client, response, path, feedback):
    assert response.status_code == 303
    assert urlsplit(response.headers["location"]).path == path
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert feedback in page.text
    return page


def process(administrator, redemption_id, decision, feedback):
    after = utc_now() - timedelta(seconds=1)
    response = administrator.client.post(
        f"/admin/redemptions/{redemption_id}/process", data={"decision": decision}
    )
    before = utc_now() + timedelta(seconds=1)
    follow_redirect(administrator.client, response, "/admin/approvals", feedback)
    return after, before


def assert_processed(session_factory, original, administrator, status, after, before):
    rows = records(session_factory, Redemption)
    assert len(rows) == 1
    row = rows[0]
    assert row == {
        **original,
        "status": status,
        "processed_by": administrator.user_id,
        "processed_at": row["processed_at"],
    }
    assert after <= row["processed_at"] <= before
    return row


def assert_actor_views(administrator, student, expected_redemption, expected_award):
    """Check fresh joined queue/history reads plus scoped HTML action controls."""
    queue = administrator.client.get("/admin/approvals")
    assert queue.status_code == 200
    actionable = expected_redemption["status"] in {"pending", "approved"}
    queue_ids = [row.id for row, user, award in queue.context["redemptions"]]
    assert queue_ids == ([expected_redemption["id"]] if actionable else [])
    section = queue.text.split('aria-labelledby="redemptions-heading"', 1)[1].split(
        "</section>", 1
    )[0]
    if actionable:
        row, user, award = queue.context["redemptions"][0]
        assert row.model_dump() == expected_redemption
        owner_id = user.id
        assert owner_id == student.user_id
        assert award.model_dump() == expected_award
        assert expected_award["name"] in section
        assert f">{expected_redemption['status'].title()}</span>" in section
        assert f"/admin/redemptions/{expected_redemption['id']}/process" in section
        if expected_redemption["status"] == "pending":
            assert 'value="approved"' in section
            assert 'value="rejected"' in section
            assert 'value="fulfilled"' not in section
        else:
            assert 'value="fulfilled"' in section
            assert "Mark as fulfilled" in section
            assert 'value="approved"' not in section
            assert 'value="rejected"' not in section
    else:
        assert expected_award["name"] not in section
        assert "There are no pending or approved redemption requests." in section
        assert f"/admin/redemptions/{expected_redemption['id']}/process" not in section

    page = student.client.get("/app/awards")
    assert page.status_code == 200
    catalogue = page.context["catalogue"]
    assert catalogue["verified_hours"] == Decimal(10)
    assert len(catalogue["redemptions"]) == 1
    row, award = catalogue["redemptions"][0]
    assert row.model_dump() == expected_redemption
    assert award.model_dump() == expected_award
    history = page.text.split('aria-labelledby="redemptions-heading"', 1)[1].split(
        "</section>", 1
    )[0]
    assert expected_award["name"] in history
    assert f">{expected_redemption['status'].title()}</span>" in history
    assert expected_redemption["requested_at"].strftime("%d %b %Y") in history
    assert catalogue["awards"][0]["award"].model_dump() == expected_award


def test_it_6_1_deferred_approval_and_fulfillment(processing_setup, session_factory):
    """Join the formerly separate request/processing tests into one full lifecycle."""
    student, administrator, award_id = processing_setup
    set_fixture_stock(session_factory, award_id, 1)
    before = snapshot(session_factory)
    assert before["redemption"] == []
    catalogue = student.client.get("/app/awards")
    assert catalogue.status_code == 200
    assert catalogue.context["catalogue"]["verified_hours"] == Decimal(10)
    assert catalogue.context["catalogue"]["awards"][0]["eligible"] is True
    requested_after = utc_now() - timedelta(seconds=1)
    response = student.client.post(f"/app/awards/{award_id}/redeem")
    requested_before = utc_now() + timedelta(seconds=1)
    page = follow_redirect(
        student.client, response, "/app/awards", "Award redemption requested."
    )
    pending_rows = records(session_factory, Redemption)
    assert len(pending_rows) == 1
    pending = pending_rows[0]
    redemption_id = pending["id"]
    assert pending["student_id"] == student.user_id
    assert pending["award_id"] == award_id
    assert requested_after <= pending["requested_at"] <= requested_before
    assert pending["status"] == "pending"
    assert pending["processed_by"] is None
    assert pending["processed_at"] is None
    assert page.context["catalogue"]["awards"][0]["pending"] is True
    assert records(session_factory, Award) == before["award"]
    assert_actor_views(administrator, student, pending, before["award"][0])

    after, until = process(
        administrator, redemption_id, "approved", "Redemption approved."
    )

    approved = assert_processed(
        session_factory, pending, administrator, "approved", after, until
    )
    empty_stock_award = {**before["award"][0], "quantity_available": 0}
    assert records(session_factory, Award) == [empty_stock_award]
    assert_actor_views(administrator, student, approved, empty_stock_award)

    after, until = process(
        administrator, redemption_id, "fulfilled", "Redemption marked as fulfilled."
    )

    fulfilled = assert_processed(
        session_factory, approved, administrator, "fulfilled", after, until
    )
    assert fulfilled["processed_at"] >= approved["processed_at"]
    assert records(session_factory, Award) == [empty_stock_award]
    assert_actor_views(administrator, student, fulfilled, empty_stock_award)
    assert (
        records(session_factory, VolunteerSubmission) == before["volunteersubmission"]
    )


def test_it_7_1_rejection_without_stock_change(processing_setup, session_factory):
    student, administrator, award_id = processing_setup
    redemption_id = seed_request(session_factory, student, administrator, award_id)
    before = snapshot(session_factory)
    assert before["award"][0]["quantity_available"] == 2
    assert_actor_views(
        administrator, student, before["redemption"][0], before["award"][0]
    )

    after, until = process(
        administrator, redemption_id, "rejected", "Redemption rejected."
    )

    rejected = assert_processed(
        session_factory,
        before["redemption"][0],
        administrator,
        "rejected",
        after,
        until,
    )
    assert records(session_factory, Award) == before["award"]
    assert (
        records(session_factory, VolunteerSubmission) == before["volunteersubmission"]
    )
    assert_actor_views(administrator, student, rejected, before["award"][0])


def test_it_7_2_stock_depleted_between_request_and_approval(
    processing_setup, session_factory
):
    student, administrator, award_id = processing_setup
    set_fixture_stock(session_factory, award_id, 1)
    before = snapshot(session_factory)
    assert before["redemption"] == []
    response = student.client.post(f"/app/awards/{award_id}/redeem")
    follow_redirect(
        student.client, response, "/app/awards", "Award redemption requested."
    )
    pending_rows = records(session_factory, Redemption)
    assert len(pending_rows) == 1
    pending = pending_rows[0]
    assert pending["status"] == "pending"
    assert pending["student_id"] == student.user_id
    assert pending["award_id"] == award_id
    assert records(session_factory, Award) == before["award"]
    assert_actor_views(administrator, student, pending, before["award"][0])

    award = before["award"][0]
    response = administrator.client.post(
        f"/admin/awards/{award_id}",
        data={
            "name": award["name"],
            "description": award["description"],
            "required_hours": "10",
            "quantity_available": "0",
            "active": "true",
        },
    )
    follow_redirect(administrator.client, response, "/admin/awards", "Award updated.")
    depleted = {**award, "quantity_available": 0}
    assert records(session_factory, Award) == [depleted]
    assert records(session_factory, Redemption) == pending_rows

    after, until = process(
        administrator,
        pending["id"],
        "approved",
        "Request rejected because the Award is out of stock.",
    )

    rejected = assert_processed(
        session_factory, pending, administrator, "rejected", after, until
    )
    assert records(session_factory, Award) == [depleted]
    assert (
        records(session_factory, VolunteerSubmission) == before["volunteersubmission"]
    )
    assert_actor_views(administrator, student, rejected, depleted)


@pytest.mark.parametrize(
    ("status", "decision", "missing"),
    [
        pytest.param("approved", "approved", False, id="IT-7.3-cannot-approve-twice"),
        pytest.param("pending", "approved", True, id="IT-7.3-nonexistent-request"),
    ],
)
def test_it_7_3_invalid_missing_or_repeated_processing(
    processing_setup, session_factory, status, decision, missing
):
    student, administrator, award_id = processing_setup
    redemption_id = seed_request(
        session_factory, student, administrator, award_id, status=status
    )
    before = snapshot(session_factory)
    assert before["award"][0]["quantity_available"] == 2
    target_id = redemption_id + 1000 if missing else redemption_id
    feedback = (
        "Redemption request was not found."
        if missing
        else "That processing action is not valid for the current status."
    )

    process(administrator, target_id, decision, feedback)

    assert snapshot(session_factory) == before
    assert_actor_views(
        administrator, student, before["redemption"][0], before["award"][0]
    )
