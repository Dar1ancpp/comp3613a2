"""JSON authentication verification using the existing guarded test database.

Temporary, schema-hidden probe routes exercise real AuthDep/AdminDep and error
handlers without adding protected API resources to the application itself.
"""

import secrets
from dataclasses import dataclass, field
from hmac import compare_digest
from http.cookies import SimpleCookie
from uuid import uuid4

import pytest
from fastapi import APIRouter

from app.dependencies.auth import AdminDep, AuthDep
from app.repositories.user import UserRepository
from app.schemas.user import AdminCreate, RegularUserCreate
from app.utilities.security import create_access_token, encrypt_password


@dataclass
class Account:
    user_id: int
    username: str
    email: str
    role: str
    password: str = field(repr=False)
    password_hash: str = field(repr=False)

    def public_details(self):
        return {
            "id": self.user_id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
        }


@pytest.fixture(autouse=True)
def hide_sql_parameters(monkeypatch, test_engine):
    monkeypatch.setattr(test_engine, "hide_parameters", True)


@pytest.fixture
def user_factory(session_factory):
    def create_user(role="regular_user"):
        username = f"api_auth_{uuid4().hex}"
        email = f"{username}@example.com"
        password = secrets.token_urlsafe(24)
        schema = AdminCreate if role == "admin" else RegularUserCreate
        with session_factory() as session:
            user = UserRepository(session).create(
                schema(
                    username=username, email=email, password=encrypt_password(password)
                )
            )
            return Account(user.id, username, email, role, password, user.password)

    return create_user


@pytest.fixture
def auth_probes(app, monkeypatch):
    # Restore the shared application's routes after each case; no production URLs.
    monkeypatch.setattr(app.router, "routes", list(app.router.routes))
    probes = APIRouter(include_in_schema=False)

    @probes.get("/api/_test/authenticated")
    def authenticated(user: AuthDep):
        return {"id": user.id}

    @probes.get("/api/_test/administrator")
    def administrator(user: AdminDep):
        return {"id": user.id}

    app.include_router(probes)


def cookie_flags(response):
    cookies = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        cookies.load(header)
    cookie = cookies.get("access_token")
    return {
        "present": cookie is not None,
        "httponly": bool(cookie["httponly"]) if cookie is not None else False,
        "samesite": cookie["samesite"].lower() if cookie is not None else "",
        "secure": bool(cookie["secure"]) if cookie is not None else False,
        "path": cookie["path"] if cookie is not None else "",
        "deleted": cookie is not None
        and cookie.value == ""
        and cookie["max-age"] == "0",
    }


def assert_json(response, expected_status):
    assert response.status_code == expected_status
    assert response.headers["content-type"].split(";", 1)[0] == "application/json"
    assert "location" not in response.headers
    return response.json()


def assert_private_values_absent(response, *values):
    if any(value and value in response.text for value in values):
        pytest.fail("An API response exposed a credential value.", pytrace=False)


def assert_account_unchanged(session_factory, account):
    with session_factory() as session:
        stored = UserRepository(session).get_by_id(account.user_id)
        public = {key: getattr(stored, key) for key in account.public_details()}
        assert public == account.public_details()
        if not compare_digest(stored.password, account.password_hash):
            pytest.fail(
                "Authentication changed the stored password hash.", pytrace=False
            )


@pytest.mark.parametrize("role", ["regular_user", "admin"])
def test_api_student_and_admin_login_logout(
    client, session_factory, user_factory, auth_probes, role
):
    account = user_factory(role)
    if role == "regular_user":
        # The student journey also checks representative invalid JSON and redaction.
        malformed = client.post("/api/auth/login", json={"password": account.password})
        errors = assert_json(malformed, 422)["detail"]
        assert errors and all(set(error) == {"type", "loc", "msg"} for error in errors)
        assert_private_values_absent(malformed, account.password)
    response = client.post(
        "/api/auth/login",
        json={"username": account.username, "password": account.password},
    )

    assert assert_json(response, 200) == {"user": account.public_details()}
    assert_private_values_absent(response, account.password, account.password_hash)
    cookie = client.cookies.get("access_token")
    assert_private_values_absent(response, cookie)
    assert response.headers["cache-control"] == "no-store"
    assert cookie_flags(response) == {
        "present": True,
        "httponly": True,
        "samesite": "lax",
        "secure": False,
        "path": "/",
        "deleted": False,
    }
    assert bool(cookie)
    assert assert_json(client.get("/api/_test/authenticated"), 200) == {
        "id": account.user_id
    }
    if role == "admin":
        assert assert_json(client.get("/api/_test/administrator"), 200) == {
            "id": account.user_id
        }
    else:
        assert assert_json(client.get("/api/_test/administrator"), 403) == {
            "detail": "You are not authorized to access this page"
        }
    destination = "/admin" if role == "admin" else "/app"
    dashboard = client.get(destination)
    assert dashboard.status_code == 200
    assert f"Signed in as {account.username}" in dashboard.text

    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    assert response.content == b""
    assert "location" not in response.headers
    assert cookie_flags(response)["deleted"] is True
    authenticated = "access_token" in client.cookies
    assert authenticated is False
    assert_json(client.get("/api/_test/authenticated"), 401)
    browser = client.get(destination)
    assert browser.status_code == 401
    assert browser.headers["content-type"].startswith("text/html")
    if role == "regular_user":
        failed_login = client.post(
            "/api/auth/login",
            json={
                "username": account.username,
                "password": account.password + "_incorrect",
            },
        )
        assert assert_json(failed_login, 401) == {
            "detail": "Incorrect username or password"
        }
        assert failed_login.headers["www-authenticate"] == "Bearer"
        assert cookie_flags(failed_login)["present"] is False
        assert_private_values_absent(
            failed_login, account.password, account.password_hash
        )
    assert_account_unchanged(session_factory, account)


def test_api_authentication_errors_are_json(client, user_factory, auth_probes):
    # Expiry is retained in IT-2.4; cookie removal/missing auth in the journey above.
    account = user_factory()
    parts = create_access_token(
        {"sub": str(account.user_id), "role": account.role}
    ).split(".")
    signature = parts[2]
    parts[2] = ("A" if signature[0] != "A" else "B") + signature[1:]
    client.cookies.set("access_token", ".".join(parts))
    response = client.get("/api/_test/authenticated")
    assert assert_json(response, 401) == {"detail": "Could not validate credentials"}
    assert response.headers["www-authenticate"] == "Bearer"
