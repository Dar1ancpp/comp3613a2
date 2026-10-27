"""Student JSON catalogue and request adapters over the existing Award service."""

from fastapi import HTTPException, status

from app.dependencies.auth import AuthDep
from app.dependencies.session import SessionDep
from app.repositories.award import AwardRepository
from app.schemas.api_auth import ApiAuthError
from app.schemas.api_awards import (
    ApiAwardCatalogue,
    ApiRedemption,
    ApiRedemptionCreate,
    ApiRedemptionError,
    ApiRedemptionHistoryEntry,
)
from app.services.award_service import AwardService

from . import api_router

REDEMPTION_ERROR_STATUSES = {
    "This Award is not available.": status.HTTP_404_NOT_FOUND,
    "You have not earned enough verified hours for this Award.": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "You already have a pending request for this Award.": status.HTTP_409_CONFLICT,
}


@api_router.get(
    "/awards",
    response_model=ApiAwardCatalogue,
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ApiAuthError}},
    name="api_student_awards",
)
def student_awards(user: AuthDep, db: SessionDep):
    return AwardService(AwardRepository(db)).get_student_awards(user.id)


@api_router.post(
    "/redemptions",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiRedemption,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ApiAuthError},
        status.HTTP_404_NOT_FOUND: {"model": ApiRedemptionError},
        status.HTTP_409_CONFLICT: {"model": ApiRedemptionError},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiRedemptionError},
    },
    name="api_request_redemption",
)
def request_redemption(payload: ApiRedemptionCreate, user: AuthDep, db: SessionDep):
    service = AwardService(AwardRepository(db))
    try:
        return service.request_redemption(student_id=user.id, award_id=payload.award_id)
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(
            status_code=REDEMPTION_ERROR_STATUSES.get(
                message, status.HTTP_422_UNPROCESSABLE_CONTENT
            ),
            detail=message,
        ) from exc


@api_router.get(
    "/redemptions",
    response_model=list[ApiRedemptionHistoryEntry],
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ApiAuthError}},
    name="api_redemption_history",
)
def redemption_history(user: AuthDep, db: SessionDep):
    history = AwardService(AwardRepository(db)).get_student_awards(user.id)[
        "redemptions"
    ]
    return [
        ApiRedemptionHistoryEntry(**redemption.model_dump(), award_name=award.name)
        for redemption, award in history
    ]
