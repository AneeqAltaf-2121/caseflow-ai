"""CaseFlow AI — FastAPI application entrypoint.

Run locally with: uvicorn app.main:app --reload
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import rate_limit_middleware, request_context_middleware
from app.api.router import api_router
from app.config import get_settings
from app.database import create_engine, create_session_factory
from app.errors import CaseFlowError, caseflow_error_handler, unhandled_exception_handler
from app.integrations.storage import get_storage_backend
from app.jobs.inline_worker import start_inline_worker, stop_inline_worker
from app.logging import configure_logging
from app.redis import create_redis_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(settings)

    engine = create_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis_client = create_redis_client(settings)
    app.state.storage_backend = get_storage_backend(settings)

    if settings.run_inline_worker:
        start_inline_worker()

    yield

    if settings.run_inline_worker:
        stop_inline_worker()
    await app.state.redis_client.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="CaseFlow AI API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(rate_limit_middleware)
    app.middleware("http")(request_context_middleware)

    app.add_exception_handler(CaseFlowError, caseflow_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(api_router)

    return app


app = create_app()
