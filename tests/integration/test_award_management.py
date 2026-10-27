"""IT-5.1 and IT-5.2: real administrator Award management and catalogue reads."""

import secrets
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import date, datetime
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
    """Real repository accounts and cookie logins, each with its own client."""
    with ExitStack() as clients:

        def create_actor(role="regular_user"):
            username = f"award_{role}_{uuid4().hex}"
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


def valid_award_form():
    return {
        "name": "  Community Service Award  ",
        "description": "  Recognition for verified volunteering.  ",
        "required_hours": "10",
        "quantity_available": "2",
        "active": "true",
    }


def award_records(session_factory):
    with session_factory() as session:
        return [
            row.model_dump()
            for row in session.exec(select(Award).order_by(Award.id)).all()
        ]


def related_records(session_factory):
    with session_factory() as session:
        return {
            model.__tablename__: [
                row.model_dump()
                for row in session.exec(select(model).order_by(model.id)).all()
            ]
            for model in (VolunteerSubmission, Redemption)
        }


def seed_approved_hours(session_factory, student, administrator):
    with session_factory() as session:
        session.add(
            VolunteerSubmission(
                student_id=student.user_id,
                activity_name="Community service",
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
        session.commit()


def follow_management_redirect(client, response, feedback):
    assert response.status_code == 303
    assert urlsplit(response.headers["location"]).path == "/admin/awards"
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert feedback in page.text
    return page


def assert_catalogues(administrator, student, expected, eligible):
    management = administrator.client.get("/admin/awards")
    assert management.status_code == 200
    assert [row.model_dump() for row in management.context["awards"]] == [expected]
    admin_section = management.text.split(
        'aria-labelledby="award-catalogue-heading"', 1
    )[1].split("</section>", 1)[0]
    assert expected["name"] in admin_section
    assert expected["description"] in admin_section
    assert f"<td>{expected['quantity_available']}</td>" in admin_section
    status = "Active" if expected["active"] else "Inactive"
    assert f">{status}</span>" in admin_section

    catalogue_page = student.client.get("/app/awards")
    assert catalogue_page.status_code == 200
    catalogue = catalogue_page.context["catalogue"]
    assert catalogue["verified_hours"] == Decimal(10)
    assert catalogue["redemptions"] == []
    student_section = catalogue_page.text.split(
        'aria-labelledby="available-awards-heading"', 1
    )[1].split("</section>", 1)[0]
    if expected["active"]:
        assert len(catalogue["awards"]) == 1
        item = catalogue["awards"][0]
        assert item["award"].model_dump() == expected
        assert item["eligible"] is eligible
        assert item["pending"] is False
        assert expected["name"] in student_section
        assert expected["description"] in student_section
        assert f"<td>{expected['quantity_available']}</td>" in student_section
        if eligible:
            assert ">Redeem</button>" in student_section
            assert ">Locked</button>" not in student_section
        else:
            assert "disabled>Locked</button>" in student_section
            assert ">Redeem</button>" not in student_section
    else:
        assert catalogue["awards"] == []
        assert expected["name"] not in student_section
        assert "No Awards are available right now." in student_section


def test_it_5_1_award_creation_editing_and_availability(actor_factory, session_factory):
    threshold = "0.25"
    quantity = "0"
    active = True
    administrator = actor_factory("admin")
    student = actor_factory()
    seed_approved_hours(session_factory, student, administrator)
    related_before = related_records(session_factory)
    assert award_records(session_factory) == []
    form = valid_award_form()
    form.update(required_hours=threshold, quantity_available=quantity)
    if not active:
        del form["active"]

    response = administrator.client.post("/admin/awards", data=form)
    follow_management_redirect(administrator.client, response, "Award created.")
    rows = award_records(session_factory)
    assert len(rows) == 1
    award_id = rows[0]["id"]
    assert award_id is not None
    expected = {
        "id": award_id,
        "name": "Community Service Award",
        "description": "Recognition for verified volunteering.",
        "required_hours": Decimal(threshold),
        "quantity_available": int(quantity),
        "active": active,
    }
    assert rows == [expected]
    assert_catalogues(administrator, student, expected, eligible=True)

    # Keep this Award's own name; each edit must update its original ID only.
    form = valid_award_form()
    form.update(
        name=expected["name"],
        description="  Updated community recognition.  ",
        required_hours="25",
        quantity_available="3",
    )
    response = administrator.client.post(f"/admin/awards/{award_id}", data=form)
    follow_management_redirect(administrator.client, response, "Award updated.")
    expected.update(
        description="Updated community recognition.",
        required_hours=Decimal(25),
        quantity_available=3,
        active=True,
    )
    assert award_records(session_factory) == [expected]
    assert_catalogues(administrator, student, expected, eligible=False)

    form.update(required_hours="10")
    del form["active"]
    response = administrator.client.post(f"/admin/awards/{award_id}", data=form)
    follow_management_redirect(administrator.client, response, "Award updated.")
    expected.update(required_hours=Decimal(10), active=False)
    assert award_records(session_factory) == [expected]
    assert_catalogues(administrator, student, expected, eligible=True)

    form["active"] = "true"
    response = administrator.client.post(f"/admin/awards/{award_id}", data=form)
    follow_management_redirect(administrator.client, response, "Award updated.")
    expected["active"] = True
    assert award_records(session_factory) == [expected]
    assert_catalogues(administrator, student, expected, eligible=True)
    assert related_records(session_factory) == related_before


@pytest.mark.parametrize(
    ("operation", "field_name", "value", "status_code", "feedback"),
    [
        pytest.param(
            "create",
            "name",
            "  Existing Award  ",
            303,
            "An Award with that name already exists.",
            id="IT-5.2-create-duplicate-name",
        ),
        pytest.param(
            "create",
            "required_hours",
            "0",
            303,
            "Required hours must be greater than zero.",
            id="IT-5.2-create-zero-threshold",
        ),
    ],
)
def test_it_5_2_invalid_award_creation_and_editing(
    actor_factory, session_factory, operation, field_name, value, status_code, feedback
):
    administrator = actor_factory("admin")
    with session_factory() as session:
        repository = AwardRepository(session)
        for name in ("Existing Award", "Another Award"):
            repository.save_award(
                Award(
                    name=name,
                    description="Original description",
                    required_hours=Decimal(10),
                    quantity_available=2,
                    active=True,
                )
            )
    before = award_records(session_factory)
    related_before = related_records(session_factory)
    target_id = before[0]["id"]
    if operation == "missing":
        target_id = max(row["id"] for row in before) + 1000
    path = "/admin/awards" if operation == "create" else f"/admin/awards/{target_id}"
    form = valid_award_form()
    # Other fields deliberately differ, so a failed edit must preserve them all.
    form.update(description="Changed description", required_hours="25", active="true")
    form[field_name] = value

    response = administrator.client.post(path, data=form)

    assert response.status_code == status_code
    if status_code == 422:
        locations = [error["loc"][-1] for error in response.json()["detail"]]
        assert field_name in locations
    else:
        follow_management_redirect(administrator.client, response, feedback)
    assert award_records(session_factory) == before
    assert related_records(session_factory) == related_before
