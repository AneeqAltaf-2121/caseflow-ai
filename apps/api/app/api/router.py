"""Top-level API router — aggregates all route modules under app/api/routes."""

from fastapi import APIRouter

from app.api.routes import health, projects

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(projects.router)
