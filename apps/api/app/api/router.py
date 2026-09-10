"""Top-level API router — aggregates all route modules under app/api/routes."""

from fastapi import APIRouter

from app.api.routes import (
    auth,
    conversations,
    documents,
    health,
    projects,
    prompt_versions,
    rag,
    reports,
    search,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(documents.router)
api_router.include_router(search.router)
api_router.include_router(rag.router)
api_router.include_router(conversations.router)
api_router.include_router(prompt_versions.router)
api_router.include_router(reports.router)
