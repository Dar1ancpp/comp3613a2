import logging
import os
import threading
import time
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError
from sqlmodel import Session, SQLModel, create_engine

from app.config import assert_postman_database, get_settings

logger = logging.getLogger(__name__)

_schema_lock = threading.Lock()


def sqlalchemy_uri(uri: str) -> str:
    """Accept Render's postgres:// URLs in the sync SQLAlchemy engine."""
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    return uri


_settings = get_settings()
_database_url = make_url(sqlalchemy_uri(_settings.database_uri))
_engine_options = {
    "echo": _settings.env in {"development", "test", "staging"},
}
if _settings.env == "postman":
    _engine_options["hide_parameters"] = True
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
if _database_url.get_backend_name() == "sqlite":
    # FastAPI may use a request's session across worker threads.
    _engine_options["connect_args"] = {"check_same_thread": False}
else:
    _engine_options.update(
        pool_size=_settings.db_pool_size,
        max_overflow=_settings.db_additional_overflow,
        pool_timeout=_settings.db_pool_timeout,
        pool_recycle=_settings.db_pool_recycle,
    )
engine = create_engine(_database_url, **_engine_options)


def assert_database_target() -> None:
    """Recheck Postman isolation before connections, sessions and schema operations."""
    if _settings.env == "postman":
        if os.environ.get("ENV", "").strip().lower() != "postman":
            raise RuntimeError(
                "The Postman profile changed after engine initialization"
            )
        settings = get_settings()
        if settings.env != "postman" or settings.config_password:
            raise RuntimeError("Postman settings changed after engine initialization")
        assert_postman_database(settings.database_uri)
        assert_postman_database(engine.url)


if _settings.env == "postman":

    @event.listens_for(engine, "do_connect")
    def _guard_postman_connect(dialect, connection_record, cargs, cparams):
        assert_database_target()
        if not cargs or cargs[0] != str(assert_postman_database(engine.url)):
            raise RuntimeError("Unexpected Postman driver connection target")

    @event.listens_for(engine, "checkout")
    def _guard_postman_checkout(dbapi_connection, connection_record, connection_proxy):
        assert_database_target()

    @event.listens_for(engine, "before_cursor_execute")
    def _guard_postman_statement(
        connection, cursor, statement, parameters, context, many
    ):
        assert_database_target()


if _database_url.get_backend_name() == "sqlite":

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        """SQLite needs foreign-key enforcement enabled on every connection."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def create_db_and_tables() -> None:
    assert_database_target()
    # Ensure model modules are imported so tables are registered on metadata.
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def drop_all() -> None:
    assert_database_target()
    if _settings.env == "postman":
        raise RuntimeError(
            "Use the guarded Postman reset command with an explicit target"
        )
    SQLModel.metadata.drop_all(bind=engine)


def is_db_not_ready_error(exc: BaseException) -> bool:
    """True when Postgres is unreachable or the schema/tables are missing."""
    if isinstance(exc, OperationalError):
        return True
    if isinstance(exc, ProgrammingError):
        return True
    if isinstance(exc, DBAPIError) and getattr(exc, "connection_invalidated", False):
        return True

    text = str(exc).lower()
    markers = (
        "does not exist",
        "undefinedtable",
        "undefined table",
        "no such table",
        "relation ",
        "could not connect",
        "connection refused",
        "connection timed out",
        "server closed the connection",
        "the database system is starting up",
        "remaining connection slots",
        "too many connections",
        "ssl connection has been closed",
    )
    return any(m in text for m in markers)


def ensure_db_and_tables(
    *,
    retries: int = 8,
    delay_seconds: float = 2.0,
) -> None:
    """Create tables, retrying while the prod DB is still coming up."""
    assert_database_target()
    last: BaseException | None = None
    for attempt in range(1, retries + 1):
        try:
            with _schema_lock:
                create_db_and_tables()
            if attempt > 1:
                logger.info("Database schema ready after %s attempt(s)", attempt)
            return
        except Exception as exc:  # noqa: BLE001 — first-boot resilience
            last = exc
            if not is_db_not_ready_error(exc) or attempt >= retries:
                raise
            logger.warning(
                "Database not ready (attempt %s/%s): %s",
                attempt,
                retries,
                type(exc).__name__ if _settings.env == "postman" else exc,
            )
            time.sleep(delay_seconds * attempt)
    if last is not None:
        raise last


def recover_if_uninitialized(exc: BaseException) -> bool:
    """If *exc* looks like a missing schema, create tables and return True."""
    assert_database_target()
    if not is_db_not_ready_error(exc):
        return False
    logger.warning(
        "Uninitialized database detected; creating tables: %s",
        type(exc).__name__ if _settings.env == "postman" else exc,
    )
    ensure_db_and_tables()
    return True


def _session_generator():
    assert_database_target()
    with Session(engine) as session:
        try:
            yield session
        except Exception as e:
            if _settings.env == "postman":
                logger.error("Postman database session error (%s)", type(e).__name__)
            else:
                logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()


def get_session():
    yield from _session_generator()


@contextmanager
def get_cli_session():
    yield from _session_generator()
