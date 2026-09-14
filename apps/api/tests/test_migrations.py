"""Alembic migration tests.

Run the full migration chain up and back down against a throwaway SQLite
database. This doesn't replace testing against real Postgres before a
production deploy, but it catches the common failure modes (broken
upgrade/downgrade ordering, typos, missing imports) cheaply and without
requiring a live database.
"""

import re
import uuid
from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from alembic.script import ScriptDirectory
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
    "reports",
    "report_sections",
    "report_citations",
    "evaluation_runs",
    "evaluation_results",
    "conversations",
    "messages",
    "jobs",
    "audit_events",
    "human_reviews",
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


def test_every_revision_id_fits_the_configured_version_table_column_length() -> None:
    """SQLite never enforces VARCHAR length at all, so the two tests
    above running the full chain against SQLite prove nothing about
    this: alembic_version.version_num defaults to VARCHAR(32), and this
    project's revision ids are descriptive slugs, not short hashes
    ("0003_add_document_chunks_pgvector" alone is 34 characters) — a
    real, strict-typed Postgres raises
    asyncpg.exceptions.StringDataRightTruncationError the moment a
    revision id longer than the column allows is written, which only
    ever showed up against a truly fresh Postgres database (this
    project's first real CI run, not this sandbox's SQLite-only local
    testing). alembic/env.py sets version_table_column_length=255 to
    fix it; this test guards both that alembic/env.py still sets it,
    and that no revision id ever grows past whatever it's set to.
    """
    env_py = (API_ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
    match = re.search(r"VERSION_TABLE_COLUMN_LENGTH\s*=\s*(\d+)", env_py)
    assert match, "alembic/env.py must define VERSION_TABLE_COLUMN_LENGTH"
    configured_length = int(match.group(1))

    assert "version_table_column_length=VERSION_TABLE_COLUMN_LENGTH" in env_py

    script_directory = ScriptDirectory(str(API_ROOT / "alembic"))
    revision_ids = [script.revision for script in script_directory.walk_revisions()]
    assert revision_ids  # sanity: the migration chain isn't empty

    too_long = [r for r in revision_ids if len(r) > configured_length]
    assert too_long == [], (
        f"revision id(s) exceed VERSION_TABLE_COLUMN_LENGTH={configured_length}: {too_long}"
    )
