"""Award Management units: approved plan cases UT-5.1 through UT-5.3.

Exercise public service methods with independent models and repository mocks.
Database uniqueness, persistence and HTTP authorization are not tested here.
"""

import socket
import sqlite3
from decimal import Decimal
from unittest.mock import create_autospec

import pytest
from sqlalchemy.engine import Engine

from app.models.award import Award
from app.repositories.award import AwardRepository
from app.services.award_service import AwardService


@pytest.fixture(autouse=True)
def forbid_database_and_network_connections(monkeypatch):
    """Fail immediately if a unit invocation attempts external I/O."""

    def forbidden_connection(*args, **kwargs):
        pytest.fail("Award Management units must not connect to a database or network.")

    monkeypatch.setattr(Engine, "connect", forbidden_connection)
    monkeypatch.setattr(Engine, "raw_connection", forbidden_connection)
    monkeypatch.setattr(sqlite3, "connect", forbidden_connection)
    monkeypatch.setattr(socket.socket, "connect", forbidden_connection)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden_connection)


@pytest.fixture
def repository():
    return create_autospec(AwardRepository, instance=True, spec_set=True)


@pytest.fixture
def service(repository):
    return AwardService(repository)


@pytest.fixture
def award():
    return Award(
        id=201,
        name="Campus Voucher",
        description="Campus cafe voucher",
        required_hours=Decimal(10),
        quantity_available=2,
        active=True,
    )


def test_ut_5_1_valid_creation_and_zero_stock(service, repository):
    quantity = 0
    active = True
    description = "  Recognition voucher  "
    expected_description = "Recognition voucher"
    repository.get_by_name.return_value = None
    repository.save_award.side_effect = lambda saved_award: saved_award

    result = service.create_award(
        name="  Community Voucher  ",
        description=description,
        required_hours=Decimal("0.25"),
        quantity_available=quantity,
        active=active,
    )

    repository.get_by_name.assert_called_once_with("Community Voucher")
    repository.save_award.assert_called_once_with(result)
    assert result is repository.save_award.call_args.args[0]
    assert isinstance(result, Award)
    assert result.id is None
    assert result.name == "Community Voucher"
    assert result.description == expected_description
    assert result.required_hours == Decimal("0.25")
    assert result.quantity_available == quantity
    assert result.active is active


def test_ut_5_2_valid_update_and_unchanged_own_name(service, repository, award):
    name = "  Campus Voucher  "
    expected_name = "Campus Voucher"
    keep_name = True
    initial_active = True
    active = False
    award.active = initial_active
    repository.get_award.return_value = award
    repository.get_by_name.return_value = award if keep_name else None
    repository.save_award.side_effect = lambda saved_award: saved_award

    result = service.update_award(
        award_id=201,
        name=name,
        description="   ",
        required_hours=Decimal(25),
        quantity_available=0,
        active=active,
    )

    repository.get_award.assert_called_once_with(201)
    repository.get_by_name.assert_called_once_with(expected_name)
    repository.save_award.assert_called_once_with(award)
    assert result is award
    assert result.id == 201
    assert result.name == expected_name
    assert result.description is None
    assert result.required_hours == Decimal(25)
    assert result.quantity_available == 0
    assert result.active is active


@pytest.mark.parametrize(
    ("operation", "field", "value", "error"),
    [
        pytest.param(
            "create",
            "name",
            "   ",
            "Award name is required.",
            id="UT-5.3-create-blank-name",
        ),
        pytest.param(
            "update",
            "name",
            "  Existing Award  ",
            "An Award with that name already exists.",
            id="UT-5.3-update-duplicate-name",
        ),
        pytest.param(
            "update",
            "required_hours",
            Decimal("-0.25"),
            "Required hours must be greater than zero.",
            id="UT-5.3-update-negative-threshold",
        ),
        pytest.param(
            "update",
            "quantity_available",
            -1,
            "Quantity cannot be negative.",
            id="UT-5.3-update-negative-inventory",
        ),
    ],
)
def test_ut_5_3_invalid_management_inputs_preserve_state(
    service, repository, award, operation, field, value, error
):
    inputs = {
        "name": "  Updated Voucher  ",
        "description": "  Updated description  ",
        "required_hours": Decimal(25),
        "quantity_available": 0,
        "active": False,
    }
    inputs[field] = value
    repository.get_award.return_value = award
    duplicate = field == "name" and value == "  Existing Award  "
    repository.get_by_name.return_value = (
        Award(
            id=202,
            name="Existing Award",
            required_hours=Decimal(10),
            quantity_available=2,
            active=True,
        )
        if duplicate
        else None
    )
    before = award.model_dump()

    with pytest.raises(ValueError) as exc_info:
        if operation == "create":
            service.create_award(**inputs)
        else:
            service.update_award(award_id=201, **inputs)

    assert str(exc_info.value) == error
    repository.save_award.assert_not_called()
    assert award.model_dump() == before
    if duplicate:
        repository.get_by_name.assert_called_once_with("Existing Award")
