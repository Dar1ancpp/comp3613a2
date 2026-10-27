"""Local-only Postman profile commands; select ENV before application imports."""

import argparse
import os
import secrets
import sys
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCK_FILE = PROJECT_ROOT / ".a2_postman.lock"


def select_profile():
    mode = os.environ.get("ENV", "postman").strip().lower()
    if mode != "postman":
        raise ValueError("Set ENV=postman or remove the incompatible inherited ENV")
    os.environ["ENV"] = "postman"


def require_settings():
    from app.config import assert_postman_database, get_settings

    settings = get_settings()
    if settings.env != "postman":
        raise ValueError("This command requires ENV=postman before application imports")
    assert_postman_database(settings.database_uri)
    database = sys.modules.get("app.database")
    if database is not None:
        existing_engine = getattr(database, "engine", None)
        if existing_engine is None:
            raise RuntimeError("An application engine was imported too early")
        assert_postman_database(existing_engine.url)
    return settings


@contextmanager
def database_lock():
    """Shared by initialization/reset and the server's entire lifespan."""
    require_settings()
    try:
        descriptor = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise RuntimeError(
            "Postman database is locked; stop its server before preparing it"
        ) from None
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        yield
    finally:
        os.close(descriptor)
        LOCK_FILE.unlink()


def configure():
    """Create private local credentials once; never overwrite an existing file."""
    destination = PROJECT_ROOT / ".env.postman"
    content = (
        'ENV="postman"\nDATABASE_URI="sqlite:///./a2_postman.db"\n'
        f'SECRET_KEY="{secrets.token_urlsafe(48)}"\n'
        'APP_HOST="127.0.0.1"\nAPP_PORT=5001\nCONFIG_PASSWORD=""\n'
        f'POSTMAN_STUDENT_PASSWORD="{secrets.token_urlsafe(24)}"\n'
        f'POSTMAN_ADMIN_PASSWORD="{secrets.token_urlsafe(24)}"\n'
    )
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    print("Created ignored .env.postman with private credentials; values withheld.")


def check():
    settings = require_settings()
    from app.database import assert_database_target, engine

    assert_database_target()
    if engine.echo or not engine.hide_parameters:
        raise RuntimeError("Postman SQL logging is not isolated")
    print("Profile: postman; SQLite target: a2_postman.db (repository root).")
    print(f"Server: http://{settings.app_host}:{settings.app_port}; console: disabled.")
    print("Database target and logging guards verified without opening a connection.")


def verify_reset_target(target):
    from app.config import POSTMAN_DATABASE, assert_postman_database

    settings = require_settings()
    candidate = Path(target)
    if not candidate.is_absolute() or candidate != POSTMAN_DATABASE:
        raise ValueError("Reset requires the exact absolute a2_postman.db target")
    assert_postman_database(settings.database_uri)
    if not POSTMAN_DATABASE.is_file():
        raise ValueError("No Postman database exists to reset; use init")


def seed(settings):
    """Insert missing fixtures atomically; preserve existing records and passwords."""
    from datetime import date, datetime, timezone
    from decimal import Decimal

    from sqlmodel import select

    from app.database import get_cli_session
    from app.models.milestone import Milestone
    from app.models.user import User
    from app.models.volunteer_submission import VolunteerSubmission
    from app.repositories.user import UserRepository
    from app.schemas.user import AdminCreate, RegularUserCreate
    from app.utilities.security import encrypt_password, verify_password

    student_password = settings.postman_student_password.get_secret_value()
    admin_password = settings.postman_admin_password.get_secret_value()
    if len(student_password) < 16 or len(admin_password) < 16:
        raise ValueError("Set private Postman seed passwords of at least 16 characters")
    with get_cli_session() as session:
        users = {}
        repository = UserRepository(session)
        for username, role, password in (
            ("postman_student", "regular_user", student_password),
            ("postman_peer", "regular_user", student_password),
            ("postman_admin", "admin", admin_password),
        ):
            user = repository.get_by_username(username)
            if user is None:
                schema = AdminCreate if role == "admin" else RegularUserCreate
                user = User.model_validate(
                    schema(
                        username=username,
                        email=f"{username}@example.com",
                        password=encrypt_password(password),
                    )
                )
                session.add(user)
                session.flush()
            elif user.role != role or not verify_password(password, user.password):
                raise ValueError(
                    "An existing Postman account differs; no credentials overwritten"
                )
            users[username] = user
        for name, threshold in (("Postman Bronze", "10"), ("Postman Silver", "25")):
            milestone = session.exec(
                select(Milestone).where(Milestone.name == name)
            ).first()
            if milestone is None:
                session.add(
                    Milestone(
                        name=name,
                        description="Postman fixture milestone",
                        required_hours=Decimal(threshold),
                    )
                )
            elif milestone.required_hours != Decimal(threshold):
                raise ValueError(
                    "An existing Postman milestone differs; no fixture overwritten"
                )
        marker = "Postman peer baseline"
        peer = users["postman_peer"]
        baseline = session.exec(
            select(VolunteerSubmission).where(
                VolunteerSubmission.student_id == peer.id,
                VolunteerSubmission.activity_name == marker,
            )
        ).one_or_none()
        if baseline is None:
            timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
            session.add(
                VolunteerSubmission(
                    student_id=peer.id,
                    activity_name=marker,
                    organization="Campus Volunteers",
                    hours=Decimal(10),
                    activity_date=date(2026, 10, 20),
                    supporting_information="Isolated Postman baseline",
                    status="approved",
                    submitted_at=timestamp,
                    reviewed_by=users["postman_admin"].id,
                    reviewed_at=timestamp,
                )
            )
        elif baseline.hours != Decimal(10) or baseline.status != "approved":
            raise ValueError(
                "An existing Postman baseline differs; no fixture overwritten"
            )
        session.commit()
    print("Postman fixtures ready: three accounts, two milestones and peer baseline.")
    print("Existing workflow records preserved; no Awards or redemptions seeded.")


def prepare(reset_target=None, dry_run=False):
    settings = require_settings()
    if reset_target is not None:
        # Verify explicit confirmation before importing an engine or connecting.
        verify_reset_target(reset_target)
    if (
        min(
            len(settings.postman_student_password.get_secret_value()),
            len(settings.postman_admin_password.get_secret_value()),
        )
        < 16
    ):
        raise ValueError(
            "Run configure or supply private Postman seed credentials first"
        )
    with database_lock():
        from sqlalchemy import inspect
        from sqlmodel import SQLModel

        import app.models  # noqa: F401
        from app.database import assert_database_target, engine, ensure_db_and_tables

        try:
            assert_database_target()
            tables = set(inspect(engine).get_table_names())
            if tables - set(SQLModel.metadata.tables):
                raise ValueError(
                    "Unexpected tables found; refusing Postman preparation"
                )
            if dry_run:
                print(
                    "Reset target, exclusive lock and schema verified; no data changed."
                )
                return
            if reset_target is not None:
                verify_reset_target(reset_target)
                assert_database_target()
                SQLModel.metadata.drop_all(engine)
            ensure_db_and_tables()
            seed(settings)
        finally:
            engine.dispose()


def run():
    require_settings()
    import uvicorn

    uvicorn.run(
        "app.main:app", host="127.0.0.1", port=5001, reload=False, access_log=False
    )


def main():
    parser = argparse.ArgumentParser(description="Guarded local A2 Postman environment")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("configure", "check", "init", "run"):
        commands.add_parser(name)
    reset = commands.add_parser(
        "reset", help="Reset only the explicitly confirmed Postman target"
    )
    reset.add_argument("--confirm-database", required=True)
    reset.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        select_profile()
        if args.command == "configure":
            configure()
        elif args.command == "check":
            check()
        elif args.command == "init":
            prepare()
        elif args.command == "reset":
            prepare(reset_target=args.confirm_database, dry_run=args.dry_run)
        else:
            run()
    except (ValueError, RuntimeError, OSError) as exc:
        # Settings validation messages can contain inherited secrets; print no values.
        raise SystemExit(
            f"Postman operation refused ({type(exc).__name__}). "
            "Check the dedicated profile, target confirmation, credentials and lock."
        ) from None


if __name__ == "__main__":
    main()
