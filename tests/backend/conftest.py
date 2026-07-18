"""Shared fixtures for backend tests."""

import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("MQTT_USER", "test")
os.environ.setdefault("MQTT_PASSWORD", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

# Ensure CWD is the backend/ directory so that app.main resolves ../frontend
_backend_dir = Path(__file__).resolve().parent.parent.parent / "backend"
os.chdir(str(_backend_dir))
sys.path.insert(0, str(_backend_dir))


@pytest.fixture
async def db_engine():
    """Create a fresh in-memory SQLite engine for each test."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    from app.database import Base  # ty: ignore[unresolved-import]

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, Any]:
    """Yield a session bound to the test engine."""
    session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
async def async_client(
    db_engine,
) -> AsyncGenerator[AsyncClient, Any]:
    """FastAPI test client with get_db overridden to use the test engine."""
    from app.database import get_db  # ty: ignore[unresolved-import]
    from app.main import app  # ty: ignore[unresolved-import]

    session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, Any]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_ws_manager() -> None:
    """Clear WebSocket connections and sun state before each test."""
    from app.mqtt_client import manager, sun_state  # ty: ignore[unresolved-import]

    manager.active_connections.clear()
    sun_state["value"] = None


@pytest.fixture
async def seed_data(db_session: AsyncSession) -> None:
    """Insert sample readings into the test database."""
    from datetime import UTC, datetime, timedelta

    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    now = datetime.now(UTC)
    samples = [
        WeatherReading(
            parameter="temperature",
            value=22.5,
            unit="°C",
            timestamp=now - timedelta(hours=2),
        ),
        WeatherReading(
            parameter="temperature",
            value=23.0,
            unit="°C",
            timestamp=now - timedelta(hours=1),
        ),
        WeatherReading(
            parameter="humidity",
            value=55.0,
            unit="%",
            timestamp=now - timedelta(hours=1),
        ),
        WeatherReading(
            parameter="condition",
            value=None,
            unit="",
            value_str="sunny",
            icon="mdi:weather-sunny",
            timestamp=now - timedelta(minutes=30),
        ),
        WeatherReading(
            parameter="air_quality",
            value=None,
            unit="",
            value_str="bardzo dobra",
            icon="",
            timestamp=now - timedelta(minutes=15),
        ),
        WeatherReading(
            parameter="temperature",
            value=24.0,
            unit="°C",
            timestamp=now,
        ),
    ]
    for r in samples:
        db_session.add(r)
    await db_session.commit()
