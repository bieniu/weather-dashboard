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


async def test_init_db_adds_missing_columns_and_indexes(db_engine) -> None:
    """init_db upgrades a pre-alerts schema: missing columns AND missing indexes.

    ``create_all`` leaves existing tables alone, so both kinds of additions
    must be applied explicitly for databases created by older releases.
    """
    from app.database import _MIGRATIONS, init_db  # ty: ignore[unresolved-import]
    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    expected_indexes = {idx.name for idx in WeatherReading.__table__.indexes}

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
        indexes = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_indexes("weather_readings")
        )
        assert {idx["name"] for idx in indexes} == expected_indexes

    # Running it again on an up-to-date schema must be a no-op, not an error.
    await init_db(custom_engine=db_engine)


async def test_sqlite_pragmas_applied_on_file_database(tmp_path) -> None:
    """Every connection gets WAL, synchronous=NORMAL and a busy timeout."""
    from app.database import create_engine_with_pragmas  # ty: ignore[unresolved-import]

    engine = create_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'w.db'}")
    try:
        async with engine.connect() as conn:
            journal = (await conn.execute(text("PRAGMA journal_mode"))).scalar_one()
            synchronous = (await conn.execute(text("PRAGMA synchronous"))).scalar_one()
            busy = (await conn.execute(text("PRAGMA busy_timeout"))).scalar_one()
    finally:
        await engine.dispose()

    assert journal == "wal"
    assert synchronous == 1  # NORMAL
    assert busy == 5000


async def test_cleanup_delete_uses_timestamp_index(db_engine) -> None:
    """The retention DELETE (timestamp-only predicate) must not scan the table."""
    from datetime import UTC, datetime

    from app.models import WeatherReading  # ty: ignore[unresolved-import]
    from sqlalchemy import delete
    from sqlalchemy.dialects import sqlite

    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    stmt = delete(WeatherReading).where(WeatherReading.timestamp < cutoff)
    sql = str(
        stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
    )
    async with db_engine.connect() as conn:
        plan = (await conn.execute(text(f"EXPLAIN QUERY PLAN {sql}"))).fetchall()

    detail = " ".join(str(row[-1]) for row in plan)
    assert "ix_weather_timestamp" in detail
    assert "SCAN weather_readings" not in detail


async def test_get_db_yields_session(db_engine) -> None:
    """Verify get_db dependency yields an AsyncSession."""
    from app.database import get_db  # ty: ignore[unresolved-import]

    async for session in get_db():
        assert session is not None
        from sqlalchemy.ext.asyncio import AsyncSession

        assert isinstance(session, AsyncSession)
