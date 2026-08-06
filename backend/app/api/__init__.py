from fastapi import APIRouter
from app.api.projects import router as projects_router
from app.api.backlog import router as backlog_router
from app.api.github import router as github_router
from app.api.execution import router as execution_router
from app.api.testing import router as testing_router

api_router = APIRouter(prefix="/api")
api_router.include_router(projects_router)
api_router.include_router(backlog_router)
api_router.include_router(github_router)
api_router.include_router(execution_router)
api_router.include_router(testing_router)
