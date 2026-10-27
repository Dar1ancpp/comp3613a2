"""Thin JSON adapters for volunteer submission creation and private history."""

from fastapi import HTTPException, status

from app.dependencies.auth import AuthDep
from app.dependencies.session import SessionDep
from app.repositories.volunteer_submission import VolunteerSubmissionRepository
from app.schemas.api_auth import ApiAuthError
from app.schemas.api_volunteer_submission import (
    ApiSubmissionValidationError,
    ApiVolunteerSubmission,
    ApiVolunteerSubmissionCreate,
)
from app.services.volunteer_submission_service import VolunteerSubmissionService

from . import api_router


@api_router.post(
    "/volunteer-submissions",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiVolunteerSubmission,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ApiAuthError},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiSubmissionValidationError},
    },
    name="api_create_volunteer_submission",
)
def create_submission(
    payload: ApiVolunteerSubmissionCreate, user: AuthDep, db: SessionDep
):
    service = VolunteerSubmissionService(VolunteerSubmissionRepository(db))
    try:
        return service.submit(student_id=user.id, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@api_router.get(
    "/volunteer-submissions",
    response_model=list[ApiVolunteerSubmission],
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ApiAuthError}},
    name="api_list_volunteer_submissions",
)
def list_submissions(user: AuthDep, db: SessionDep):
    service = VolunteerSubmissionService(VolunteerSubmissionRepository(db))
    return service.list_for_student(user.id)
