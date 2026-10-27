"""JSON login/logout adapters over the existing authentication service."""

from fastapi import HTTPException, Response, status

from app.dependencies.session import SessionDep
from app.repositories.user import UserRepository
from app.schemas.api_auth import (
    ApiAuthError,
    ApiLoginRequest,
    ApiLoginResponse,
    ApiPublicUser,
)
from app.services.auth_service import AuthService
from app.utilities.security import access_token_cookie_kwargs

from . import api_router


@api_router.post(
    "/auth/login",
    response_model=ApiLoginResponse,
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ApiAuthError}},
    name="api_login",
)
def login(payload: ApiLoginRequest, response: Response, db: SessionDep):
    repository = UserRepository(db)
    token = AuthService(repository).authenticate_user(
        payload.username, payload.password.get_secret_value()
    )
    user = repository.get_by_username(payload.username) if token else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    response.set_cookie("access_token", token, **access_token_cookie_kwargs())
    response.headers["Cache-Control"] = "no-store"
    return ApiLoginResponse(user=ApiPublicUser.model_validate(user))


@api_router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    name="api_logout",
)
def logout():
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie("access_token", **access_token_cookie_kwargs())
    return response
