"""Top-level API router — aggregates all route modules under app/api/routes."""

from fastapi import APIRouter

from app.api.routes import auth, documents, health, projects, search

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(documents.router)
api_router.include_router(search.router)
