"""IT-1.1: actual lifespan, isolated schema and SQLite foreign-key baseline."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models.user import User
from app.models.volunteer_submission import VolunteerSubmission


def test_it_1_1_lifespan_and_database_isolation(app, isolated_database, test_engine):
    # Fixture cleanup has removed the test schema; startup must create it.
    isolated_database.assert_isolated()
    assert Path(test_engine.url.database).resolve() == isolated_database.expected_path
    assert inspect(test_engine).get_table_names() == []

    with TestClient(app, follow_redirects=False) as client:
        isolated_database.assert_isolated()
        assert set(inspect(test_engine).get_table_names()) == {
            "user",
            "volunteersubmission",
            "milestone",
            "award",
            "redemption",
        }
        with test_engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

        # Both real application session paths must bind to the same test engine.
        generator = isolated_database.database.get_session()
        try:
            request_session = next(generator)
            assert request_session.get_bind() is test_engine
            assert (
                request_session.connection()
                .exec_driver_sql("PRAGMA foreign_keys")
                .scalar_one()
                == 1
            )
        finally:
            generator.close()
        with isolated_database.database.get_cli_session() as cli_session:
            assert cli_session.get_bind() is test_engine
            assert (
                cli_session.connection()
                .exec_driver_sql("PRAGMA foreign_keys")
                .scalar_one()
                == 1
            )

        # A genuine INSERT/commit failure establishes FK enforcement, not a mock.
        with Session(test_engine) as session:
            assert session.exec(select(User)).all() == []
            session.add(
                VolunteerSubmission(
                    student_id=999999,
                    activity_name="Orphan fixture activity",
                    organization="Campus Volunteers",
                    activity_date=date(2026, 10, 20),
                    hours=Decimal(4),
                    supporting_information="IT-1.1 fixture",
                    submitted_at=datetime.fromisoformat("2026-10-20T09:00:00"),
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
            assert session.exec(select(VolunteerSubmission)).all() == []
