import asyncio
from logging.config import fileConfig

from sqlalchemy import Column, MetaData, PrimaryKeyConstraint, String, Table, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import the models package so every model is registered on Base.metadata
# before Alembic inspects it for autogenerate.
import app.models  # noqa: F401,E402
from alembic import context
from app.config import get_settings
from app.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Alembic's default alembic_version.version_num column is VARCHAR(32)
# (hardcoded — alembic/ddl/impl.py's DefaultImpl.version_table_impl —
# no config option controls it in this Alembic version, despite older
# docs/blog posts describing a `version_table_column_length` kwarg that
# does not exist here; verified against the installed alembic 1.19.2
# source before relying on it). This project's revision ids are
# descriptive slugs, not short hashes — "0003_add_document_chunks_pgvector"
# alone is 34 characters — so the default silently truncates-and-errors
# on a fresh Postgres database the moment a migration with a long-enough
# id is applied (asyncpg.exceptions.StringDataRightTruncationError).
# SQLite never caught this locally since it doesn't enforce VARCHAR
# length at all; a truly fresh Postgres (a clean CI run, `docker compose
# up` against a brand-new volume) does.
#
# Fixed by pre-creating alembic_version ourselves, wider, before Alembic
# gets a chance to (its own bootstrap uses `checkfirst=True`, so it
# leaves an already-existing table alone — see
# MigrationContext._ensure_version_table in alembic/runtime/migration.py).
VERSION_TABLE_NAME = "alembic_version"
VERSION_TABLE_COLUMN_LENGTH = 255


def _ensure_wide_version_table(connection: Connection) -> None:
    table = Table(
        VERSION_TABLE_NAME,
        MetaData(),
        Column("version_num", String(VERSION_TABLE_COLUMN_LENGTH), nullable=False),
    )
    table.append_constraint(PrimaryKeyConstraint("version_num", name=f"{VERSION_TABLE_NAME}_pkc"))
    table.create(connection, checkfirst=True)
    connection.commit()


def get_url() -> str:
    """Resolve the DB URL: -x sqlalchemy_url=... override, else app settings.

    The -x override exists so migration tests (tests/test_migrations.py) and
    CI can point Alembic at a throwaway SQLite/Postgres instance without
    touching the app's real .env configuration.
    """
    x_args = context.get_x_argument(as_dictionary=True)
    return x_args.get("sqlalchemy_url") or get_settings().database_url


def run_migrations_offline() -> None:
    # Offline mode only ever emits SQL to a script (no live connection to
    # create the version table against), so there's nothing to widen here
    # — the online path below is what every real run (including CI/
    # docker-compose's `migrate` service) actually takes.
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _ensure_wide_version_table(connection)
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
