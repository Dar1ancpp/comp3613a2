"""IT-2.1 to IT-2.3: real registration, password hashing and cookie login."""

import secrets
from dataclasses import dataclass, field
from hmac import compare_digest
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from pwdlib.exceptions import UnknownHashError
from sqlmodel import select

from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import AdminCreate, RegularUserCreate
from app.utilities.security import encrypt_password, verify_password


@dataclass
class Account:
    username: str
    email: str
    password: str = field(repr=False)
    role: str = "regular_user"
    user_id: int | None = None
    encoded_password: str = field(default="", repr=False)

    def public_record(self):
        return {
            "id": self.user_id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
        }


def new_account(role="regular_user"):
    identifier = f"it_{uuid4().hex}"
    return Account(
        username=identifier,
        email=f"{identifier}@example.com",
        password=secrets.token_urlsafe(24),
        role=role,
    )


def require_private(condition, message):
    """Fail without pytest expanding password/hash operands into its output."""
    if not condition:
        pytest.fail(message, pytrace=False)


def read_users(session_factory):
    """Read committed data in a new session; keep hashes out of public diffs."""
    with session_factory() as session:
        users = session.exec(select(User).order_by(User.id)).all()
        public_records = [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
            }
            for user in users
        ]
        encoded_passwords = {user.id: user.password for user in users}
    return public_records, encoded_passwords


def authentication_cookie_flags(response):
    """Expose only flags, never the authentication cookie's value."""
    cookies = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        cookies.load(header)
    cookie = cookies.get("access_token")
    return {
        "present": cookie is not None,
        "httponly": bool(cookie["httponly"]) if cookie is not None else False,
        "samesite": cookie["samesite"].lower() if cookie is not None else "",
        "secure": bool(cookie["secure"]) if cookie is not None else False,
    }


@pytest.fixture(autouse=True)
def hide_sql_parameters(monkeypatch, test_engine):
    # Expected UNIQUE errors are logged by UserRepository; redact their values.
    monkeypatch.setattr(test_engine, "hide_parameters", True)


@pytest.fixture
def user_factory(session_factory):
    """Create only this test's prerequisite users with real repository writes."""

    def create_user(role="regular_user"):
        account = new_account(role)
        schema = AdminCreate if role == "admin" else RegularUserCreate
        with session_factory() as session:
            user = UserRepository(session).create(
                schema(
                    username=account.username,
                    email=account.email,
                    password=encrypt_password(account.password),
                )
            )
            account.user_id = user.id
            account.encoded_password = user.password
        return account

    return create_user


def test_it_2_1_registration_persistence_and_student_role(client, session_factory):
    account = new_account()

    response = client.post(
        "/register",
        data={
            "username": account.username,
            "email": account.email,
            "password": account.password,
            "role": "admin",
        },
    )

    assert response.status_code == 303
    assert urlsplit(response.headers["location"]).path == "/login"
    confirmation = client.get(response.headers["location"])
    assert confirmation.status_code == 200
    assert "Registration completed! Sign in now!" in confirmation.text
    assert authentication_cookie_flags(response)["present"] is False
    authenticated = "access_token" in client.cookies
    assert authenticated is False

    records, encoded_passwords = read_users(session_factory)
    assert len(records) == 1
    account.user_id = records[0]["id"]
    assert account.user_id is not None
    assert records == [account.public_record()]
    stored_hash = encoded_passwords[account.user_id]
    require_private(
        bool(stored_hash) and not compare_digest(stored_hash, account.password),
        "Registration did not store a hashed password.",
    )
    try:
        verified = verify_password(account.password, stored_hash)
    except UnknownHashError:
        pytest.fail(
            "Persisted registration password could not be verified.", pytrace=False
        )
    require_private(verified, "Persisted password does not verify against the input.")


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param("username", id="IT-2.2-duplicate-username"),
        pytest.param("email", id="IT-2.2-duplicate-email"),
    ],
)
def test_it_2_2_duplicate_or_invalid_registration(
    client, session_factory, user_factory, scenario
):
    existing = user_factory()
    candidate = new_account()
    if scenario == "username":
        candidate.username = existing.username
    elif scenario == "email":
        candidate.email = existing.email
    else:
        candidate.email = "not-an-email"

    response = client.post(
        "/register",
        data={
            "username": candidate.username,
            "email": candidate.email,
            "password": candidate.password,
        },
    )

    assert response.status_code == 303
    assert urlsplit(response.headers["location"]).path == "/register"
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert "Username or email already exists" in page.text
    assert authentication_cookie_flags(response)["present"] is False
    records, encoded_passwords = read_users(session_factory)
    assert records == [existing.public_record()]
    require_private(
        compare_digest(encoded_passwords[existing.user_id], existing.encoded_password),
        "Rejected registration changed the existing user's password hash.",
    )


@pytest.mark.parametrize(
    ("scenario", "role", "destination", "heading"),
    [
        pytest.param(
            "valid",
            "regular_user",
            "/app",
            "Welcome to Student Awards",
            id="IT-2.3-valid-student-login",
        ),
        pytest.param(
            "valid",
            "admin",
            "/admin",
            "Administrator dashboard",
            id="IT-2.3-valid-administrator-login",
        ),
    ],
)
def test_it_2_3_valid_and_invalid_login(
    client, session_factory, user_factory, scenario, role, destination, heading
):
    account = user_factory(role)
    username = (
        account.username + "_missing"
        if scenario == "unknown-user"
        else account.username
    )
    password = (
        account.password + "_incorrect"
        if scenario == "wrong-password"
        else account.password
    )

    response = client.post("/login", data={"username": username, "password": password})

    assert response.status_code == 303
    assert urlsplit(response.headers["location"]).path == destination
    flags = authentication_cookie_flags(response)
    authenticated = "access_token" in client.cookies
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    if scenario == "valid":
        assert flags == {
            "present": True,
            "httponly": True,
            "samesite": "lax",
            "secure": False,
        }
        assert authenticated is True
        assert f"<h1>{heading}</h1>" in page.text
        assert f"Signed in as {account.username}" in page.text
    else:
        assert flags["present"] is False
        assert authenticated is False
        assert "Incorrect username or password" in page.text

    records, encoded_passwords = read_users(session_factory)
    assert records == [account.public_record()]
    require_private(
        compare_digest(encoded_passwords[account.user_id], account.encoded_password),
        "Login changed a persisted password hash.",
    )
