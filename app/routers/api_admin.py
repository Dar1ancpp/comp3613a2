"""Thin administrator JSON adapters over existing application services."""

from typing import Literal

from fastapi import HTTPException, status

from app.dependencies.auth import AdminDep
from app.dependencies.session import SessionDep
from app.repositories.award import AwardRepository
from app.repositories.volunteer_submission import VolunteerSubmissionRepository
from app.schemas.api_admin import (
    ApiActionableRedemption,
    ApiAdminError,
    ApiAwardWrite,
    ApiPendingSubmission,
    ApiProcessingResult,
    ApiRedemptionProcessing,
    ApiSubmissionReview,
)
from app.schemas.api_awards import ApiAward
from app.schemas.api_volunteer_submission import ApiVolunteerSubmission
from app.services.award_service import AwardService
from app.services.volunteer_submission_service import VolunteerSubmissionService

from . import api_router

AUTH_ERRORS = {
    status.HTTP_401_UNAUTHORIZED: {"model": ApiAdminError},
    status.HTTP_403_FORBIDDEN: {"model": ApiAdminError},
}
WRITE_ERRORS = {
    **AUTH_ERRORS,
    status.HTTP_404_NOT_FOUND: {"model": ApiAdminError},
    status.HTTP_409_CONFLICT: {"model": ApiAdminError},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiAdminError},
}
SERVICE_ERROR_STATUSES = {
    "Volunteer submission was not found.": status.HTTP_404_NOT_FOUND,
    "Award was not found.": status.HTTP_404_NOT_FOUND,
    "Redemption request was not found.": status.HTTP_404_NOT_FOUND,
    "The requested Award was not found.": status.HTTP_404_NOT_FOUND,
    "Only pending submissions can be reviewed.": status.HTTP_409_CONFLICT,
    "An Award with that name already exists.": status.HTTP_409_CONFLICT,
    "That processing action is not valid for the current status.": status.HTTP_409_CONFLICT,
}


def _service_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    return HTTPException(
        status_code=SERVICE_ERROR_STATUSES.get(
            message, status.HTTP_422_UNPROCESSABLE_CONTENT
        ),
        detail=message,
    )


@api_router.get(
    "/admin/volunteer-submissions",
    response_model=list[ApiPendingSubmission],
    responses=AUTH_ERRORS,
    name="api_admin_pending_submissions",
)
def pending_submissions(
    user: AdminDep, db: SessionDep, status: Literal["pending"] = "pending"
):
    service = VolunteerSubmissionService(VolunteerSubmissionRepository(db))
    return [
        ApiPendingSubmission(
            **submission.model_dump(), student_username=student.username
        )
        for submission, student in service.list_pending_with_students()
    ]


@api_router.patch(
    "/admin/volunteer-submissions/{id}",
    response_model=ApiVolunteerSubmission,
    responses=WRITE_ERRORS,
    name="api_admin_review_submission",
)
def review_submission(
    id: int, payload: ApiSubmissionReview, user: AdminDep, db: SessionDep
):
    service = VolunteerSubmissionService(VolunteerSubmissionRepository(db))
    try:
        return service.review(
            submission_id=id, reviewer_id=user.id, decision=payload.status
        )
    except ValueError as exc:
        raise _service_error(exc) from exc


@api_router.get(
    "/admin/awards",
    response_model=list[ApiAward],
    responses=AUTH_ERRORS,
    name="api_admin_awards",
)
def all_awards(user: AdminDep, db: SessionDep):
    return AwardService(AwardRepository(db)).list_all_awards()


@api_router.post(
    "/admin/awards",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiAward,
    responses=WRITE_ERRORS,
    name="api_admin_create_award",
)
def create_award(payload: ApiAwardWrite, user: AdminDep, db: SessionDep):
    service = AwardService(AwardRepository(db))
    try:
        return service.create_award(
            **payload.model_dump(exclude={"description"}),
            description=payload.description or "",
        )
    except ValueError as exc:
        raise _service_error(exc) from exc


@api_router.put(
    "/admin/awards/{id}",
    response_model=ApiAward,
    responses=WRITE_ERRORS,
    name="api_admin_update_award",
)
def update_award(id: int, payload: ApiAwardWrite, user: AdminDep, db: SessionDep):
    service = AwardService(AwardRepository(db))
    try:
        return service.update_award(
            award_id=id,
            **payload.model_dump(exclude={"description"}),
            description=payload.description or "",
        )
    except ValueError as exc:
        raise _service_error(exc) from exc


@api_router.get(
    "/admin/redemptions",
    response_model=list[ApiActionableRedemption],
    responses=AUTH_ERRORS,
    name="api_admin_actionable_redemptions",
)
def actionable_redemptions(user: AdminDep, db: SessionDep):
    service = AwardService(AwardRepository(db))
    return [
        ApiActionableRedemption(
            **redemption.model_dump(),
            student_username=student.username,
            award_name=award.name,
        )
        for redemption, student, award in service.list_actionable_redemptions()
    ]


@api_router.patch(
    "/admin/redemptions/{id}",
    response_model=ApiProcessingResult,
    responses=WRITE_ERRORS,
    name="api_admin_process_redemption",
)
def process_redemption(
    id: int, payload: ApiRedemptionProcessing, user: AdminDep, db: SessionDep
):
    repository = AwardRepository(db)
    service = AwardService(repository)
    try:
        message = service.process_redemption(
            redemption_id=id, administrator_id=user.id, decision=payload.status
        )
    except ValueError as exc:
        raise _service_error(exc) from exc
    return {"redemption": repository.get_redemption(id), "message": message}
