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


def test_alembic_version_table_column_is_actually_widened(tmp_path: Path) -> None:
    """Alembic's own alembic_version.version_num column is hardcoded to
    VARCHAR(32) in this Alembic version (alembic/ddl/impl.py's
    DefaultImpl.version_table_impl — verified directly against the
    installed alembic source; there is no `version_table_column_length`
    config option here despite that name appearing in some older
    docs/blog posts, and an earlier version of this fix silently did
    nothing because of exactly that mistake). This project's revision
    ids are descriptive slugs, not short hashes —
    "0003_add_document_chunks_pgvector" alone is 34 characters — so the
    default raises asyncpg.exceptions.StringDataRightTruncationError the
    moment a long-enough revision id is written to a real Postgres
    database. SQLite doesn't enforce VARCHAR length at all, so the tests
    above running the full chain against SQLite prove nothing about
    this — this test instead checks what actually matters: the real,
    reflected column width after a migration run, not just that some
    option was passed somewhere.

    alembic/env.py fixes this by pre-creating alembic_version itself,
    wider, before Alembic's own bootstrap gets a chance to (which uses
    checkfirst=True and leaves an existing table alone).
    """
    db_path = tmp_path / f"migrations_{uuid.uuid4().hex}.db"
    config = _alembic_config(db_path)

    command.upgrade(config, "head")

    sync_engine = create_engine(f"sqlite:///{db_path}")
    columns = {c["name"]: c for c in inspect(sync_engine).get_columns("alembic_version")}
    sync_engine.dispose()

    assert "version_num" in columns
    reflected_length = columns["version_num"]["type"].length
    assert reflected_length is not None and reflected_length >= 255


def test_every_revision_id_fits_comfortably_under_the_widened_column() -> None:
    """A sanity check independent of the DB-level test above: no current
    revision id is anywhere near the width alembic_version.version_num
    is now created at, and this fails loudly if a future migration's id
    ever gets long enough to matter again."""
    script_directory = ScriptDirectory(str(API_ROOT / "alembic"))
    revision_ids = [script.revision for script in script_directory.walk_revisions()]
    assert revision_ids  # sanity: the migration chain isn't empty

    too_long = [r for r in revision_ids if len(r) > 100]
    assert too_long == [], f"revision id(s) unexpectedly long: {too_long}"
