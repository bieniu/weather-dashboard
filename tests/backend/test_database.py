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
    from app.models import WeatherReading  # ty: ignore[unresolved-import]

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


async def test_init_db_adds_missing_columns(db_engine) -> None:
    """Verify init_db adds columns that were added to the model post-deployment."""
    from app.database import _MIGRATIONS, init_db  # ty: ignore[unresolved-import]

    async with db_engine.begin() as conn:
        await conn.execute(text("DROP TABLE weather_readings"))
        await conn.execute(
            text(
                "CREATE TABLE weather_readings ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "parameter VARCHAR(50) NOT NULL, "
                "value FLOAT, "
                "unit VARCHAR(10) NOT NULL, "
                "value_str VARCHAR(100), "
                "icon VARCHAR(50), "
                "timestamp DATETIME NOT NULL"
                ")"
            )
        )
        result = await conn.execute(text("PRAGMA table_info(weather_readings)"))
        cols = {row[1] for row in result.fetchall()}
        for col_name, _ in _MIGRATIONS:
            assert col_name not in cols

    await init_db(custom_engine=db_engine)

    async with db_engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(weather_readings)"))
        cols = {row[1] for row in result.fetchall()}
        for col_name, _ in _MIGRATIONS:
            assert col_name in cols


async def test_get_db_yields_session(db_engine) -> None:
    """Verify get_db dependency yields an AsyncSession."""
    from app.database import get_db  # ty: ignore[unresolved-import]

    async for session in get_db():
        assert session is not None
        from sqlalchemy.ext.asyncio import AsyncSession

        assert isinstance(session, AsyncSession)
