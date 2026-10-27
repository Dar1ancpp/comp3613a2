"""Authenticated JSON progress using the same service as the browser view."""

from fastapi import status

from app.dependencies.auth import AuthDep
from app.dependencies.session import SessionDep
from app.repositories.progress import ProgressRepository
from app.schemas.api_auth import ApiAuthError
from app.schemas.api_progress import ApiProgressResponse
from app.services.progress_service import ProgressService

from . import api_router


@api_router.get(
    "/progress",
    response_model=ApiProgressResponse,
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ApiAuthError}},
    name="api_progress",
)
def student_progress(user: AuthDep, db: SessionDep):
    service = ProgressService(ProgressRepository(db))
    return service.get_student_progress(user.id)
