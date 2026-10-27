import os
import re
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
# ENV=test must be set before importing the application (including in pytest).
_DOTENV_CANDIDATES = (".env", ".env.example", "env.example")
_TEST_DOTENV_CANDIDATES = (".env.test", ".env.test.example")
_POSTMAN_DOTENV_CANDIDATES = (".env.postman", ".env.postman.example")
POSTMAN_DATABASE = _PROJECT_ROOT / "a2_postman.db"


def resolve_dotenv_path() -> Path | None:
    """Isolated profiles never fall back to development secrets."""
    mode = os.environ.get("ENV", "").strip().lower()
    if mode == "postman":
        candidates = _POSTMAN_DOTENV_CANDIDATES
    elif mode in {"test", "testing"}:
        candidates = _TEST_DOTENV_CANDIDATES
    else:
        candidates = _DOTENV_CANDIDATES
    for name in candidates:
        path = _PROJECT_ROOT / name
        if path.is_file():
            return path
    return None


def _env_files_for_settings() -> tuple[str, ...]:
    """Keep Settings() and get_settings() on the same selected profile."""
    path = resolve_dotenv_path()
    return (str(path),) if path is not None else ()


_ENV_FILE = _PROJECT_ROOT / ".env"


@lru_cache
def get_settings():
    path = resolve_dotenv_path()
    # Re-bind env_file each call so clearing the cache picks up a new .env.
    return Settings(_env_file=path if path is not None else _env_files_for_settings())


def clear_settings_cache() -> None:
    get_settings.cache_clear()


def set_runtime_env(mode: str) -> str:
    """Switch ENV at runtime (and persist to .env when that file exists)."""
    if get_settings().env == "postman":
        raise ValueError("The Postman profile cannot be switched at runtime")
    normalized = mode.strip().lower()
    if normalized in {"prod", "production"}:
        value = "production"
    elif normalized in {"dev", "development"}:
        value = "development"
    else:
        raise ValueError("ENV must be production or development")

    os.environ["ENV"] = value
    clear_settings_cache()
    _upsert_dotenv("ENV", value)
    return value


def _upsert_dotenv(key: str, value: str) -> None:
    # Never rewrite the committed example files — only a real `.env`.
    if not _ENV_FILE.is_file():
        return
    text = _ENV_FILE.read_text(encoding="utf-8")
    pattern = re.compile(rf"(?m)^{re.escape(key)}=.*$")
    line = f'{key}="{value}"'
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"
    _ENV_FILE.write_text(text, encoding="utf-8")


def mask_secret(value: str | None, *, keep_tail: int = 4) -> str:
    if not value:
        return "(unset)"
    if len(value) <= keep_tail:
        return "*" * len(value)
    return "*" * (len(value) - keep_tail) + value[-keep_tail:]


def mask_database_uri(uri: str) -> str:
    """Hide credentials in database URLs for the config panel."""
    if "://" not in uri:
        return uri
    scheme, rest = uri.split("://", 1)
    if "@" in rest and ":" in rest.split("@", 1)[0]:
        userinfo, hostpart = rest.split("@", 1)
        user = userinfo.split(":", 1)[0]
        return f"{scheme}://{user}:****@{hostpart}"
    return uri


def assert_postman_database(uri: str) -> Path:
    """Validate the exact local target and its SQLite sidecars without connecting."""
    try:
        url = make_url(uri)
    except ArgumentError:
        raise ValueError("Invalid Postman database URL; value withheld") from None
    if (
        url.drivername not in {"sqlite", "sqlite+pysqlite"}
        or not url.database
        or url.host
        or url.username
        or url.password
        or url.query
    ):
        raise ValueError("Postman requires the dedicated local SQLite database")
    configured = Path(url.database)
    if not configured.is_absolute():
        configured = _PROJECT_ROOT / configured
    for suffix in ("", "-journal", "-wal", "-shm"):
        target = POSTMAN_DATABASE.with_name(POSTMAN_DATABASE.name + suffix)
        if target.is_symlink() or (
            target.exists() and (not target.is_file() or target.stat().st_nlink != 1)
        ):
            raise ValueError("Postman database files must be regular and unlinked")
    if configured.resolve() != POSTMAN_DATABASE:
        raise ValueError("Postman permits only this repository's a2_postman.db")
    return POSTMAN_DATABASE


class Settings(BaseSettings):
    database_uri: str
    secret_key: str = Field(repr=False)
    env: str
    config_password: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expires: int = 30
    app_host: str = "0.0.0.0"
    app_port: int = 5000
    db_pool_size: int = 10
    db_additional_overflow: int = 10
    db_pool_timeout: int = 10
    db_pool_recycle: int = 10
    postman_student_password: SecretStr = SecretStr("")
    postman_admin_password: SecretStr = SecretStr("")

    @field_validator("env", mode="before")
    @classmethod
    def normalize_env(cls, value: object) -> str:
        mode = str(value).strip().lower()
        aliases = {"dev": "development", "testing": "test", "prod": "production"}
        mode = aliases.get(mode, mode)
        if mode not in {"development", "test", "postman", "staging", "production"}:
            raise ValueError(
                "ENV must be development, test, postman, staging, or production"
            )
        return mode

    @model_validator(mode="after")
    def isolate_local_database(self):
        """Fail before engine creation if a local profile targets other data."""
        if self.env == "production":
            return self
        if self.env == "postman":
            expected = assert_postman_database(self.database_uri)
            if self.app_host != "127.0.0.1" or self.app_port != 5001:
                raise ValueError("Postman must bind to 127.0.0.1:5001")
            if self.config_password:
                raise ValueError("Postman requires the configuration console disabled")
            if len(self.secret_key) < 32:
                raise ValueError(
                    "Configure a private Postman SECRET_KEY of at least 32 characters"
                )
            self.database_uri = (
                make_url(self.database_uri)
                .set(database=expected.as_posix())
                .render_as_string()
            )
            return self
        try:
            url = make_url(self.database_uri)
        except ArgumentError:
            raise ValueError("DATABASE_URI must be a valid local SQLite URL") from None
        if (
            url.drivername not in {"sqlite", "sqlite+pysqlite"}
            or not url.database
            or url.database == ":memory:"
            or url.host
            or url.username
            or url.password
            or url.query
        ):
            raise ValueError("Development and test profiles require an A2 SQLite file")
        filename = "a2_test.db" if self.env == "test" else "a2_development.db"
        expected = (_PROJECT_ROOT / filename).resolve()
        configured = Path(url.database)
        if not configured.is_absolute():
            configured = _PROJECT_ROOT / configured
        if configured.resolve() != expected:
            raise ValueError(f"This ENV requires the A2-local {filename} database")
        self.database_uri = url.set(database=expected.as_posix()).render_as_string()
        return self

    @field_validator("app_port", mode="before")
    @classmethod
    def port_from_render(cls, value: object, info: ValidationInfo) -> object:
        # Render sets PORT. An explicit --port on the CLI still wins in cmd_run.
        if info.data.get("env") == "postman":
            return value
        port = os.environ.get("PORT")
        if port:
            return int(port)
        return value

    model_config = SettingsConfigDict(
        env_file=_env_files_for_settings(),
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )
