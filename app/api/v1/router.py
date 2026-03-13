from fastapi import APIRouter
from app.api.v1.apps import router as apps_router
from app.api.v1.settings import router as settings_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.suggestions import router as suggestions_router
from app.api.v1.keywords import router as keywords_router
from app.api.v1.reviews import router as reviews_router
from app.api.v1.facts import router as facts_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.logs import router as logs_router
from app.api.v1.team import router as team_router

api_router = APIRouter()

api_router.include_router(apps_router, prefix="/apps", tags=["apps"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(suggestions_router, prefix="/apps", tags=["suggestions"])
api_router.include_router(keywords_router, prefix="/apps", tags=["keywords"])
api_router.include_router(reviews_router, prefix="/apps", tags=["reviews"])
api_router.include_router(facts_router, prefix="/apps", tags=["facts"])
api_router.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
api_router.include_router(logs_router, prefix="/logs", tags=["logs"])
api_router.include_router(team_router, prefix="/team", tags=["team"])
