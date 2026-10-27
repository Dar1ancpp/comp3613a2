"""Administrator processing units: approved plan cases UT-4.1 to UT-4.5.

Use fresh models, mocked repositories and a controlled service clock. These
units establish state transitions, not HTTP authorization or atomic commits.
"""

import socket
import sqlite3
from datetime import datetime
from decimal import Decimal
from unittest.mock import create_autospec

import pytest
from sqlalchemy.engine import Engine

from app.models.award import Award
from app.models.redemption import Redemption
from app.repositories.award import AwardRepository
from app.services import award_service as service_module
from app.services.award_service import AwardService

# Intentionally naive UTC, matching the existing service's stored timestamps.
REQUEST_TIME = datetime(2026, 10, 20, 9, 0, 0)  # noqa: DTZ001
PREVIOUS_PROCESSING_TIME = datetime(2026, 10, 26, 9, 0, 0)  # noqa: DTZ001
PROCESSING_TIME = datetime(2026, 10, 27, 12, 0, 0)  # noqa: DTZ001


@pytest.fixture(autouse=True)
def forbid_database_and_network_connections(monkeypatch):
    """Fail immediately if a unit invocation attempts external I/O."""

    def forbidden_connection(*args, **kwargs):
        pytest.fail("Processing units must not connect to a database or network.")

    monkeypatch.setattr(Engine, "connect", forbidden_connection)
    monkeypatch.setattr(Engine, "raw_connection", forbidden_connection)
    monkeypatch.setattr(sqlite3, "connect", forbidden_connection)
    monkeypatch.setattr(socket.socket, "connect", forbidden_connection)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden_connection)


@pytest.fixture
def repository():
    return create_autospec(AwardRepository, instance=True, spec_set=True)


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


@pytest.fixture
def redemption():
    return Redemption(
        id=401,
        student_id=101,
        award_id=201,
        status="pending",
        requested_at=REQUEST_TIME,
    )


@pytest.fixture
def service(repository, award, redemption):
    repository.get_redemption.return_value = redemption
    repository.get_award.return_value = award
    repository.save_processing.return_value = redemption
    return AwardService(repository)


@pytest.fixture
def fixed_processing_clock(monkeypatch):
    class FixedClock:
        @staticmethod
        def utcnow():
            return PROCESSING_TIME

    monkeypatch.setattr(service_module, "datetime", FixedClock)


def test_ut_4_1_approval_and_last_item_boundary(
    service, repository, award, redemption, fixed_processing_clock
):
    quantity = 1
    decision = "  ApPrOvEd  "
    expected_quantity = 0
    award.quantity_available = quantity
    award_details_before = award.model_dump(exclude={"quantity_available"})
    request_details_before = redemption.model_dump(
        exclude={"status", "processed_by", "processed_at"}
    )

    result = service.process_redemption(
        redemption_id=401, administrator_id=900, decision=decision
    )

    assert result == "Redemption approved."
    assert redemption.status == "approved"
    assert redemption.processed_by == 900
    assert redemption.processed_at == PROCESSING_TIME
    assert award.quantity_available == expected_quantity
    assert award.model_dump(exclude={"quantity_available"}) == award_details_before
    assert (
        redemption.model_dump(exclude={"status", "processed_by", "processed_at"})
        == request_details_before
    )
    repository.get_redemption.assert_called_once_with(401)
    repository.get_award.assert_called_once_with(201)
    repository.save_processing.assert_called_once_with(redemption, award)
    repository.save_award.assert_not_called()
    repository.create_redemption.assert_not_called()


def test_ut_4_2_rejection_preserves_inventory(
    service, repository, award, redemption, fixed_processing_clock
):
    quantity = 0
    award.quantity_available = quantity
    before = award.model_dump()

    result = service.process_redemption(
        redemption_id=401, administrator_id=900, decision="rejected"
    )

    assert result == "Redemption rejected."
    assert redemption.status == "rejected"
    assert redemption.processed_by == 900
    assert redemption.processed_at == PROCESSING_TIME
    assert redemption.requested_at == REQUEST_TIME
    assert award.model_dump() == before
    repository.save_processing.assert_called_once_with(redemption, award)
    repository.save_award.assert_not_called()
    repository.create_redemption.assert_not_called()


def test_ut_4_3_stock_exhausted_before_approval(
    service, repository, award, redemption, fixed_processing_clock
):
    # Model the current lookup state; request creation is tested separately.
    award.quantity_available = 0
    before = award.model_dump()

    result = service.process_redemption(
        redemption_id=401, administrator_id=900, decision="approved"
    )

    assert result == "Request rejected because the Award is out of stock."
    assert redemption.status == "rejected"
    assert redemption.processed_by == 900
    assert redemption.processed_at == PROCESSING_TIME
    assert redemption.requested_at == REQUEST_TIME
    assert award.model_dump() == before
    repository.save_processing.assert_called_once_with(redemption, award)
    repository.save_award.assert_not_called()
    repository.create_redemption.assert_not_called()


def test_ut_4_4_fulfillment_does_not_deduct_inventory_again(
    service, repository, award, redemption, fixed_processing_clock
):
    redemption.status = "approved"
    redemption.processed_by = 800
    redemption.processed_at = PREVIOUS_PROCESSING_TIME
    award.quantity_available = 1
    award_before = award.model_dump()
    request_details_before = redemption.model_dump(
        exclude={"status", "processed_by", "processed_at"}
    )

    result = service.process_redemption(
        redemption_id=401, administrator_id=900, decision="fulfilled"
    )

    assert result == "Redemption marked as fulfilled."
    assert redemption.status == "fulfilled"
    assert redemption.processed_by == 900
    assert redemption.processed_at == PROCESSING_TIME
    assert (
        redemption.model_dump(exclude={"status", "processed_by", "processed_at"})
        == request_details_before
    )
    assert award.model_dump() == award_before
    repository.save_processing.assert_called_once_with(redemption)
    repository.save_award.assert_not_called()
    repository.create_redemption.assert_not_called()


def test_ut_4_5_invalid_processing_preserves_state(
    service, repository, award, redemption
):
    status = "pending"
    decision = "fulfilled"
    redemption.status = status
    if status != "pending":
        redemption.processed_by = 800
        redemption.processed_at = PREVIOUS_PROCESSING_TIME
    request_before = redemption.model_dump()
    award_before = award.model_dump()

    with pytest.raises(
        ValueError,
        match=r"^That processing action is not valid for the current status\.$",
    ):
        service.process_redemption(
            redemption_id=401, administrator_id=900, decision=decision
        )

    assert redemption.model_dump() == request_before
    assert award.model_dump() == award_before
    repository.save_processing.assert_not_called()
    repository.save_award.assert_not_called()
    repository.create_redemption.assert_not_called()
