"""Main FastAPI application — Weather Dashboard."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .database import SessionLocal, init_db
from .models import WeatherReading
from .mqtt_client import _load_sun_state, mqtt_listener
from .ratelimit import RateLimitMiddleware
from .routers.weather import router as weather_router

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

    from sqlalchemy.engine import CursorResult
    from starlette.requests import Request
    from starlette.responses import Response

logger = logging.getLogger(__name__)

RETENTION_DAYS = 30
CLEANUP_INTERVAL_SECONDS = 3600

# Long-running tasks started by the lifespan; /health reports 503 if any has died.
background_tasks: dict[str, asyncio.Task[None]] = {}


def _configure_logging() -> None:
    """Attach a root handler so `app.*` INFO logs are visible next to uvicorn's."""
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def cleanup_old_readings() -> None:
    """Delete readings older than RETENTION_DAYS — immediately, then hourly.

    One failed cycle is logged and retried on the next one instead of killing
    the task for the lifetime of the process.
    """
    while True:
        try:
            async with SessionLocal() as db:
                cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
                result = cast(
                    "CursorResult[Any]",
                    await db.execute(
                        delete(WeatherReading).where(WeatherReading.timestamp < cutoff),
                    ),
                )
                await db.commit()
                logger.info(
                    "Removed %d reading(s) older than %d days",
                    result.rowcount,
                    RETENTION_DAYS,
                )
        except Exception:
            logger.exception("Cleanup of old readings failed; retrying next cycle")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


def _log_task_exit(task: asyncio.Task[None]) -> None:
    """Report a background task that ended for any reason other than cancellation."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is None:
        logger.error("Background task %s exited unexpectedly", task.get_name())
    else:
        logger.error("Background task %s died", task.get_name(), exc_info=exc)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Startup/shutdown lifecycle — initialize DB, MQTT and cleanup tasks."""
    _configure_logging()
    await init_db()
    await _load_sun_state()
    background_tasks["mqtt_listener"] = asyncio.create_task(
        mqtt_listener(), name="mqtt_listener"
    )
    background_tasks["cleanup_old_readings"] = asyncio.create_task(
        cleanup_old_readings(), name="cleanup_old_readings"
    )
    for task in background_tasks.values():
        task.add_done_callback(_log_task_exit)
    yield
    for task in background_tasks.values():
        task.cancel()
    for task in background_tasks.values():
        with suppress(asyncio.CancelledError):
            await task
    background_tasks.clear()


def _build_csp() -> str:
    script_src = "'self' https://cdn.jsdelivr.net"
    if settings.umami_host:
        script_src += f" {settings.umami_host}"
    return (
        "default-src 'self'; "
        f"script-src {script_src}; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self' ws: wss:; "
        "worker-src 'self'; "
        "frame-ancestors 'none';"
    )


CSP_HEADER = _build_csp()


class CloudflareIPMiddleware(BaseHTTPMiddleware):
    """Middleware that overrides client IP with the Cf-Connecting-IP header."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Set real_ip from Cf-Connecting-IP, falling back to client.host."""
        cf_ip = request.headers.get("Cf-Connecting-IP")
        request.state.real_ip = cf_ip or (
            request.client.host if request.client else "unknown"
        )
        return await call_next(request)


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


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check for Docker — 503 when a background task has stopped."""
    dead = sorted(name for name, task in background_tasks.items() if task.done())
    if dead:
        raise HTTPException(
            status_code=503, detail=f"background tasks stopped: {', '.join(dead)}"
        )
    return {"status": "ok"}


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Starlette runs the middleware added LAST as the outermost layer, so the order
# below yields: CSP -> CloudflareIP -> RateLimit -> CORS -> app. CloudflareIP must
# wrap RateLimit so that `request.state.real_ip` is set before the limiter reads it.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CloudflareIPMiddleware)
app.add_middleware(CSPMiddleware)

app.include_router(weather_router)

# Serve frontend from static files
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
