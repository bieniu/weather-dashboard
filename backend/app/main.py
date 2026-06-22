"""Main FastAPI application — Weather Dashboard."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from sqlalchemy import delete

from .config import settings
from .database import init_db, SessionLocal
from .models import WeatherReading
from .mqtt_client import mqtt_listener
from .routers.weather import router as weather_router


async def cleanup_old_readings() -> None:
    """Delete readings older than 30 days — runs every hour."""
    while True:
        await asyncio.sleep(3600)
        async with SessionLocal() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            await db.execute(
                delete(WeatherReading).where(WeatherReading.timestamp < cutoff)
            )
            await db.commit()
            print("[Cleanup] Old records removed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup/shutdown lifecycle — initialize DB, MQTT and cleanup tasks."""
    await init_db()
    mqtt_task = asyncio.create_task(mqtt_listener())
    cleanup_task = asyncio.create_task(cleanup_old_readings())
    yield
    cleanup_task.cancel()
    mqtt_task.cancel()
    try:
        await mqtt_task
    except asyncio.CancelledError:
        pass
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


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
    async def dispatch(self, request: Request, call_next):
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
