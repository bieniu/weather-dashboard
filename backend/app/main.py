"""Main FastAPI application — Weather Dashboard."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .database import SessionLocal, init_db
from .models import WeatherReading
from .mqtt_client import mqtt_listener
from .routers.weather import router as weather_router

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response

logger = logging.getLogger(__name__)


async def cleanup_old_readings() -> None:
    """Delete readings older than 30 days — runs every hour."""
    while True:
        await asyncio.sleep(3600)
        async with SessionLocal() as db:
            cutoff = datetime.now(UTC) - timedelta(days=30)
            await db.execute(
                delete(WeatherReading).where(WeatherReading.timestamp < cutoff),
            )
            await db.commit()
            logger.info("Old records removed")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Startup/shutdown lifecycle — initialize DB, MQTT and cleanup tasks."""
    await init_db()
    mqtt_task = asyncio.create_task(mqtt_listener())
    cleanup_task = asyncio.create_task(cleanup_old_readings())
    yield
    cleanup_task.cancel()
    mqtt_task.cancel()
    with suppress(asyncio.CancelledError):
        await mqtt_task
    with suppress(asyncio.CancelledError):
        await cleanup_task


CSP_HEADER = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self' ws: wss:; "
    "worker-src 'self'; "
    "frame-ancestors 'none';"
)


class CSPMiddleware(BaseHTTPMiddleware):
    """Middleware that adds Content-Security-Policy header to all responses."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Add CSP header to every response."""
        response: Response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP_HEADER
        return response


app = FastAPI(title="Weather Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CSPMiddleware)

app.include_router(weather_router)

# Serve frontend from static files
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
