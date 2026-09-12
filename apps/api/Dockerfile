# CaseFlow AI — backend image (Phase 39).
#
# Serves both the API and the worker: same dependencies, same code,
# different process (see docker-compose.yml's `command:` override for the
# worker service — `dramatiq app.jobs.worker` instead of `uvicorn`). One
# image for both avoids maintaining two dependency sets that would
# otherwise be identical.
#
# Build context is the *repo root*, not apps/api — this image also
# installs packages/evals, which apps/api imports at runtime
# (app/evals/__init__.py) exactly like a local dev venv does (see the
# root README's two-package install).
#
# docker build -f apps/api/Dockerfile -t caseflow-api .

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY packages/evals packages/evals
COPY apps/api apps/api

RUN pip install -e ./packages/evals && pip install -e ./apps/api

WORKDIR /app/apps/api

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
