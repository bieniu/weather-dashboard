"""Database configuration — async SQLAlchemy with SQLite."""

import os
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./weather.db")

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    """Base declarative class for ORM models."""


async def init_db() -> None:
    """Create all database tables and apply migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Migration: add level column if missing (added after initial deployment)
        result = await conn.execute(text("PRAGMA table_info(weather_readings)"))
        columns = {row[1] for row in result.fetchall()}
        if "level" not in columns:
            await conn.execute(
                text("ALTER TABLE weather_readings ADD COLUMN level VARCHAR(20)")
            )


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency — yields a database session."""
    async with SessionLocal() as session:
        yield session
