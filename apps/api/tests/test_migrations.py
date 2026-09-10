"""Alembic migration tests.

Run the full migration chain up and back down against a throwaway SQLite
database. This doesn't replace testing against real Postgres before a
production deploy, but it catches the common failure modes (broken
upgrade/downgrade ordering, typos, missing imports) cheaply and without
requiring a live database.
"""

import uuid
from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

API_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "users",
    "organizations",
    "projects",
    "project_members",
    "documents",
    "document_versions",
    "document_chunks",
    "citations",
    "prompt_versions",
    "model_runs",
    "conversations",
    "messages",
    "jobs",
    "audit_events",
    "alembic_version",
}


def _alembic_config(db_path: Path) -> Config:
    """An Alembic Config pointed at a scratch SQLite DB via the -x override
    that alembic/env.py::get_url() reads (see that file for why)."""
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.cmd_opts = SimpleNamespace(x=[f"sqlalchemy_url=sqlite+aiosqlite:///{db_path}"])
    return config


def test_upgrade_head_creates_all_tables(tmp_path: Path) -> None:
    db_path = tmp_path / f"migrations_{uuid.uuid4().hex}.db"
    config = _alembic_config(db_path)

    command.upgrade(config, "head")

    sync_engine = create_engine(f"sqlite:///{db_path}")
    tables = set(inspect(sync_engine).get_table_names())
    sync_engine.dispose()

    assert tables >= EXPECTED_TABLES


def test_downgrade_to_base_drops_all_tables(tmp_path: Path) -> None:
    db_path = tmp_path / f"migrations_{uuid.uuid4().hex}.db"
    config = _alembic_config(db_path)

    command.upgrade(config, "head")
    command.downgrade(config, "base")

    sync_engine = create_engine(f"sqlite:///{db_path}")
    tables = set(inspect(sync_engine).get_table_names()) - {"alembic_version"}
    sync_engine.dispose()

    assert tables == set()
