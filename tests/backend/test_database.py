"""Tests for app.database — engine, session management."""

from sqlalchemy import inspect, text


async def test_init_db_creates_tables(db_engine) -> None:
    """Verify Base.metadata.create_all creates the weather_readings table."""
    async with db_engine.connect() as conn:
        tables = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
    assert "weather_readings" in tables


async def test_db_session_insert_and_query(db_session) -> None:
    """Verify a WeatherReading can be inserted and queried via raw SQL."""
    from app.models import WeatherReading

    r = WeatherReading(parameter="temperature", value=22.5, unit="°C")
    db_session.add(r)
    await db_session.commit()

    result = await db_session.execute(
        text("SELECT parameter, value, unit FROM weather_readings")
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] == "temperature"
    assert row[1] == 22.5
    assert row[2] == "°C"


async def test_get_db_yields_session(db_engine) -> None:
    """Verify get_db dependency yields an AsyncSession."""
    from app.database import get_db

    async for session in get_db():
        assert session is not None
        from sqlalchemy.ext.asyncio import AsyncSession

        assert isinstance(session, AsyncSession)
