"""Top-level API router — aggregates all route modules under app/api/routes."""

from fastapi import APIRouter

from app.api.routes import health

api_router = APIRouter()
api_router.include_router(health.router)
