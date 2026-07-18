"""Database configuration — async SQLAlchemy with SQLite."""

import os
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./weather.db")

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    """Base declarative class for ORM models."""


_MIGRATIONS: list[tuple[str, str]] = [
    ("level", "VARCHAR(20)"),
    ("valid_to", "DATETIME"),
]


async def init_db(
    custom_engine: AsyncEngine | None = None,
) -> None:
    """Create all database tables and apply migrations."""
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


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency — yields a database session."""
    async with SessionLocal() as session:
        yield session
