"""Shared column helpers for ORM models.

Types here are chosen to be portable across PostgreSQL (production) and
SQLite (used only for fast local Alembic/repository tests — see
tests/test_migrations.py) so the same migration can be exercised in both.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import mapped_column
from sqlalchemy.types import Uuid


def uuid_pk():
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def created_at_column():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def updated_at_column():
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


UtcDateTime = DateTime(timezone=True)

__all__ = ["uuid_pk", "created_at_column", "updated_at_column", "UtcDateTime", "datetime", "uuid"]
