"""Database configuration — async SQLAlchemy with SQLite."""

import os
from contextlib import closing
from typing import TYPE_CHECKING

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.engine import Connection
    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./weather.db")

# Applied to every new SQLite connection. WAL lets readers (/history, /alerts)
# run while the MQTT ingest commits, and synchronous=NORMAL drops the per-commit
# fsync (WAL keeps this durable except for the last transactions on OS crash).
# journal_mode is persisted in the database file; the other two are per-connection.
SQLITE_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
)


def _set_sqlite_pragmas(
    dbapi_connection: DBAPIConnection, _record: ConnectionPoolEntry
) -> None:
    with closing(dbapi_connection.cursor()) as cursor:
        for pragma in SQLITE_PRAGMAS:
            cursor.execute(pragma)


def create_engine_with_pragmas(url: str) -> AsyncEngine:
    """Create the async engine used by the app (and by tests) with SQLite pragmas."""
    eng = create_async_engine(url, echo=False)
    event.listen(eng.sync_engine, "connect", _set_sqlite_pragmas)
    return eng


engine = create_engine_with_pragmas(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    """Base declarative class for ORM models."""


_MIGRATIONS: list[tuple[str, str]] = [
    ("level", "VARCHAR(20)"),
    ("valid_to", "DATETIME"),
]


def _create_missing_indexes(sync_conn: Connection) -> None:
    """Create indexes declared on the models that an existing table lacks.

    ``create_all`` skips tables that already exist, including their indexes,
    so an index added to a model after the first deployment would otherwise
    never reach a production database.
    """
    for table in Base.metadata.tables.values():
        for index in table.indexes:
            index.create(sync_conn, checkfirst=True)


async def init_db(
    custom_engine: AsyncEngine | None = None,
) -> None:
    """Create all database tables and apply migrations (columns, then indexes)."""
    eng = custom_engine or engine
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        result = await conn.execute(text("PRAGMA table_info(weather_readings)"))
        existing = {row[1] for row in result.fetchall()}
        for col_name, col_type in _MIGRATIONS:
            if col_name not in existing:
                await conn.execute(
                    text(
                        f"ALTER TABLE weather_readings ADD COLUMN {col_name} {col_type}"
                    )
                )

        # After the column migrations: an index may reference a new column.
        await conn.run_sync(_create_missing_indexes)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency — yields a database session."""
    async with SessionLocal() as session:
        yield session
