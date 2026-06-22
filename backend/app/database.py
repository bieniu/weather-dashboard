"""Database configuration — async SQLAlchemy with SQLite."""

import os
from typing import TYPE_CHECKING

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
    """Create all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency — yields a database session."""
    async with SessionLocal() as session:
        yield session
