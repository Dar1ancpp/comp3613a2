"""Fail-closed fixtures for the dedicated A2 SQLite integration database."""

import os
import socket
import sys
import threading
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import ArgumentError
from sqlmodel import Session, SQLModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE = PROJECT_ROOT / "a2_test.db"
# Pytest's cache can have private ACLs when created by another Windows account.
# Keep one fixed lock in the shared repository, independent of cacheprovider.
LOCK_FILE = PROJECT_ROOT / ".a2_integration.lock"


def abort_isolation(reason):
    pytest.exit(f"Integration database isolation refused: {reason}", returncode=4)


# This conftest is scoped to integration tests; unit-only runs do not load it.
if any(
    name in sys.modules
    for name in (
        "app.config",
        "app.database",
        "app.main",
        "app.routers",
        "app.utilities.security",
    )
):
    abort_isolation(
        "application configuration was imported too early; use a fresh process"
    )
if os.environ.get("ENV", "test").strip().lower() not in {"test", "testing"}:
    abort_isolation("ENV must be test; remove incompatible inherited settings")
if os.environ.get("PYTEST_XDIST_WORKER"):
    abort_isolation("the fixed test database requires a serial pytest run")
os.environ["ENV"] = "test"

# Import settings only after the profile is selected. No engine exists yet.
config_module = import_module("app.config")


def assert_database_url(uri):
    try:
        url = make_url(uri)
    except ArgumentError:
        abort_isolation("invalid database URL; value withheld")
    if (
        url.drivername not in {"sqlite", "sqlite+pysqlite"}
        or not url.database
        or url.host
        or url.username
        or url.password
        or url.query
        or not Path(url.database).is_absolute()
        or Path(url.database).resolve() != TEST_DATABASE
    ):
        abort_isolation("only this repository's local a2_test.db is permitted")
    if TEST_DATABASE.is_symlink() or (
        TEST_DATABASE.exists()
        and (not TEST_DATABASE.is_file() or TEST_DATABASE.stat().st_nlink != 1)
    ):
        abort_isolation("the test database must be a regular, unlinked file")


def assert_test_settings():
    if os.environ.get("ENV") != "test":
        abort_isolation("the test profile changed during execution")
    try:
        settings = config_module.get_settings()
    except (ValueError, TypeError):
        abort_isolation("test settings are invalid; values withheld")
    if settings.env != "test" or settings.config_password:
        abort_isolation("require the test profile with the config console disabled")
    assert_database_url(settings.database_uri)


assert_test_settings()


@contextmanager
def exclusive_test_database():
    """Prevent two local pytest processes from sharing the fixed SQLite file."""
    assert_test_settings()
    try:
        descriptor = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        abort_isolation("another integration run or stale lock owns the test database")
    except PermissionError:
        abort_isolation(
            "cannot create .a2_integration.lock; check repository permissions"
        )
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        yield
    finally:
        os.close(descriptor)
        LOCK_FILE.unlink()


@pytest.fixture
def isolated_database(monkeypatch):
    """Own and reset only the guarded test schema, including committed writes."""
    assert_test_settings()
    selected_engine = None
    real_connect = Engine.connect
    real_raw_connection = Engine.raw_connection

    def assert_engine(engine):
        assert_test_settings()
        if engine is not selected_engine:
            abort_isolation("an unexpected engine attempted to connect")
        assert_database_url(engine.url)

    def guarded_connect(engine, *args, **kwargs):
        assert_engine(engine)
        return real_connect(engine, *args, **kwargs)

    def guarded_raw_connection(engine, *args, **kwargs):
        assert_engine(engine)
        return real_raw_connection(engine, *args, **kwargs)

    network_context = threading.local()
    real_socketpair = socket.socketpair
    real_socket_connect = socket.socket.connect
    real_socket_connect_ex = socket.socket.connect_ex

    def runtime_socketpair(*args, **kwargs):
        # Windows implements asyncio's internal socketpair over loopback TCP.
        previous = getattr(network_context, "socketpair", False)
        network_context.socketpair = True
        try:
            return real_socketpair(*args, **kwargs)
        finally:
            network_context.socketpair = previous

    def runtime_connection_allowed(address):
        return (
            getattr(network_context, "socketpair", False)
            and isinstance(address, tuple)
            and address[0] in {"127.0.0.1", "::1"}
        )

    def guarded_socket_connect(sock, address):
        if runtime_connection_allowed(address):
            return real_socket_connect(sock, address)
        abort_isolation("application network connections are not allowed")

    def guarded_socket_connect_ex(sock, address):
        if runtime_connection_allowed(address):
            return real_socket_connect_ex(sock, address)
        abort_isolation("application network connections are not allowed")

    monkeypatch.setattr(Engine, "connect", guarded_connect)
    monkeypatch.setattr(Engine, "raw_connection", guarded_raw_connection)
    monkeypatch.setattr(socket, "socketpair", runtime_socketpair)
    monkeypatch.setattr(socket.socket, "connect", guarded_socket_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_socket_connect_ex)

    with exclusive_test_database():
        database = import_module("app.database")
        import_module("app.models")
        selected_engine = database.engine
        assert_engine(selected_engine)
        # Do not capture SQL parameters that could include future dummy passwords.
        monkeypatch.setattr(selected_engine, "echo", False)

        def assert_bindings():
            assert_engine(database.engine)
            console = sys.modules.get("app.routers.server_config")
            if console is not None and console.engine is not selected_engine:
                abort_isolation("the config console holds a different engine")
            dependency = sys.modules.get("app.dependencies.session")
            if (
                dependency is not None
                and dependency.get_session is not database.get_session
            ):
                abort_isolation("the request session dependency was replaced")

        def reset_test_schema():
            assert_bindings()
            tables = set(inspect(selected_engine).get_table_names())
            if tables - set(SQLModel.metadata.tables):
                abort_isolation(
                    "unexpected tables exist in the dedicated test database"
                )
            SQLModel.metadata.drop_all(selected_engine)

        try:
            reset_test_schema()
            yield SimpleNamespace(
                engine=selected_engine,
                database=database,
                expected_path=TEST_DATABASE,
                assert_isolated=assert_bindings,
            )
        finally:
            try:
                reset_test_schema()
            finally:
                selected_engine.dispose()


@pytest.fixture
def app(isolated_database):
    application = import_module("app.main").app
    isolated_database.assert_isolated()
    return application


@pytest.fixture
def test_engine(isolated_database):
    return isolated_database.engine


@pytest.fixture
def client(app):
    """Run the actual lifespan and provide a fresh cookie jar per test."""
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


@pytest.fixture
def session_factory(client, isolated_database):
    """Create independent sessions after lifespan has initialized the schema."""

    @contextmanager
    def new_session():
        isolated_database.assert_isolated()
        with Session(isolated_database.engine) as session:
            yield session

    return new_session


@pytest.fixture
def db_session(session_factory):
    with session_factory() as session:
        yield session
