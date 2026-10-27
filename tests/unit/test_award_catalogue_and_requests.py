"""Award catalogue/request units: approved plan cases UT-3.1 to UT-3.4.

Repositories are mocked; SQL active-row filtering and persisted hour totals
remain integration concerns. No processing or Award-management units run here.
"""

import socket
import sqlite3
from datetime import datetime
from decimal import Decimal
from unittest.mock import create_autospec, sentinel

import pytest
from sqlalchemy.engine import Engine

from app.models.award import Award
from app.models.redemption import Redemption
from app.repositories.award import AwardRepository
from app.services.award_service import AwardService


@pytest.fixture(autouse=True)
def forbid_database_and_network_connections(monkeypatch):
    """Fail immediately if a unit invocation attempts external I/O."""

    def forbidden_connection(*args, **kwargs):
        pytest.fail("Award request units must not connect to a database or network.")

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
        quantity_available=1,
        active=True,
    )


def test_ut_3_1_catalogue_eligibility_and_pending_flags(service, repository):
    populated = True
    awards = (
        [
            Award(
                id=201,
                name="Coffee Voucher",
                required_hours=Decimal(4),
                quantity_available=2,
                active=True,
            ),
            Award(
                id=202,
                name="Movie Ticket",
                required_hours=Decimal(10),
                quantity_available=2,
                active=True,
            ),
            Award(
                id=203,
                name="Hoodie",
                required_hours=Decimal(25),
                quantity_available=2,
                active=True,
            ),
        ]
        if populated
        else []
    )
    history = [sentinel.redemption_history]
    pending = {(101, 201): False, (101, 202): True, (101, 203): False}
    repository.verified_hours.return_value = Decimal(10)
    repository.list_active.return_value = awards
    repository.has_pending.side_effect = lambda student_id, award_id: pending[
        (student_id, award_id)
    ]
    repository.list_student_redemptions.return_value = history

    result = service.get_student_awards(student_id=101)

    assert result["verified_hours"] == Decimal(10)
    assert result["redemptions"] is history
    if populated:
        assert result["awards"] == [
            {"award": awards[0], "eligible": True, "pending": False},
            {"award": awards[1], "eligible": True, "pending": True},
            {"award": awards[2], "eligible": False, "pending": False},
        ]
    else:
        assert result["awards"] == []
        repository.has_pending.assert_not_called()
    repository.verified_hours.assert_called_once_with(101)
    repository.list_student_redemptions.assert_called_once_with(101)
    repository.create_redemption.assert_not_called()


def test_ut_3_2_valid_redemption_without_reservation(service, repository, award):
    verified_hours = Decimal(10)
    repository.get_award.return_value = award
    repository.verified_hours.return_value = verified_hours
    repository.has_pending.return_value = False
    repository.create_redemption.side_effect = lambda redemption: redemption
    before = award.model_dump()

    result = service.request_redemption(student_id=101, award_id=201)

    repository.get_award.assert_called_once_with(201)
    repository.verified_hours.assert_called_once_with(101)
    repository.has_pending.assert_called_once_with(101, 201)
    repository.create_redemption.assert_called_once_with(result)
    assert result is repository.create_redemption.call_args.args[0]
    assert isinstance(result, Redemption)
    assert result.student_id == 101
    assert result.award_id == 201
    assert result.status == "pending"
    assert isinstance(result.requested_at, datetime)
    assert result.processed_by is None
    assert result.processed_at is None
    assert award.model_dump() == before
    repository.save_award.assert_not_called()
    repository.save_processing.assert_not_called()


def test_ut_3_3_unavailable_or_ineligible_award(service, repository, award):
    scenario = "missing"
    error = "This Award is not available."
    if scenario == "inactive":
        award.active = False
    verified_hours = (
        Decimal("9.75") if scenario == "insufficient-hours" else Decimal(10)
    )
    repository.get_award.return_value = None if scenario == "missing" else award
    repository.verified_hours.return_value = verified_hours
    repository.has_pending.return_value = False
    before = award.model_dump()

    with pytest.raises(ValueError) as exc_info:
        service.request_redemption(student_id=101, award_id=201)

    assert str(exc_info.value) == error
    repository.create_redemption.assert_not_called()
    repository.save_award.assert_not_called()
    repository.save_processing.assert_not_called()
    assert award.model_dump() == before


def test_ut_3_4_duplicate_pending_request_rejection(service, repository, award):
    repository.get_award.return_value = award
    repository.verified_hours.return_value = Decimal(10)
    repository.has_pending.return_value = True
    before = award.model_dump()

    with pytest.raises(
        ValueError, match="^You already have a pending request for this Award\\.$"
    ):
        service.request_redemption(student_id=101, award_id=201)

    repository.has_pending.assert_called_once_with(101, 201)
    repository.create_redemption.assert_not_called()
    repository.save_award.assert_not_called()
    repository.save_processing.assert_not_called()
    assert award.model_dump() == before
