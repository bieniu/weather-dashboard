"""Tests for app.database — engine, session management."""

from sqlalchemy import inspect, text


async def test_init_db_creates_tables(db_engine) -> None:
    # tables created by db_engine fixture via Base.metadata.create_all
    async with db_engine.connect() as conn:
        tables = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
    assert "weather_readings" in tables


async def test_db_session_insert_and_query(db_session) -> None:
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
    from app.database import get_db

    async for session in get_db():
        assert session is not None
        from sqlalchemy.ext.asyncio import AsyncSession

        assert isinstance(session, AsyncSession)
