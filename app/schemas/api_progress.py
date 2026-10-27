"""JSON representation of the existing progress service's read model."""

from decimal import Decimal

from pydantic import BaseModel


class ApiMilestoneProgress(BaseModel):
    name: str
    description: str | None
    required_hours: Decimal
    completed: bool
    percentage: float


class ApiLeaderboardEntry(BaseModel):
    student_id: int
    username: str
    verified_hours: Decimal
    rank: int
    is_current: bool


class ApiProgressResponse(BaseModel):
    verified_hours: Decimal
    rank: int | None
    milestones: list[ApiMilestoneProgress]
    leaderboard: list[ApiLeaderboardEntry]
