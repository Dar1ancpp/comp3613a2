from decimal import Decimal

from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from app.utilities.flash import get_flashed_messages
from jinja2 import Environment, FileSystemLoader
from app.config import get_settings


template_env = Environment(loader = FileSystemLoader("app/templates",), )
template_env.globals['get_flashed_messages'] = get_flashed_messages


def format_hours(value) -> str:
    """Render stored hour precision without insignificant trailing zeroes."""
    number = Decimal(str(value))
    return format(number.normalize(), "f")


template_env.globals["format_hours"] = format_hours
templates = Jinja2Templates(env=template_env)
static_files = StaticFiles(directory="app/static")

router = APIRouter(tags=["Jinja Based Endpoints"], include_in_schema=get_settings().env.lower() in ["dev","development"])
api_router = APIRouter(tags=["API Endpoints"], prefix="/api")

from . import (index, login, register, admin_home, user_home, volunteer_submissions, admin_reviews, progress, awards, admin_awards, logout, server_config)
from . import api_auth as api_auth
from . import api_volunteer_submissions as api_volunteer_submissions
from . import api_progress as api_progress
from . import api_awards as api_awards
from . import api_admin as api_admin
