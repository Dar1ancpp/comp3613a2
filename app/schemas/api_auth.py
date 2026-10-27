"""Explicit JSON authentication contracts; credentials are never response fields."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr


class ApiLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    username: str = Field(min_length=1)
    password: SecretStr = Field(min_length=1)


class ApiPublicUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    role: str


class ApiLoginResponse(BaseModel):
    user: ApiPublicUser


class ApiAuthError(BaseModel):
    detail: str
