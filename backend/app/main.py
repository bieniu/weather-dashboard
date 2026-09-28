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
from starlette.datastructures import MutableHeaders, QueryParams

from .config import settings
from .database import SessionLocal, init_db
from .models import WeatherReading
from .mqtt_client import mqtt_listener
from .ratelimit import RateLimitMiddleware
from .routers.weather import router as weather_router

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.engine import CursorResult
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

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
    # Umami loads its script from its host and posts beacons back to it.
    script_src = "'self'"
    connect_src = "'self'"  # 'self' also covers the same-origin WebSocket (CSP3)
    if settings.umami_host:
        script_src += f" {settings.umami_host}"
        connect_src += f" {settings.umami_host}"
    return (
        "default-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "object-src 'none'; "
        f"script-src {script_src}; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        f"connect-src {connect_src}; "
        "worker-src 'self'; "
        "frame-ancestors 'none';"
    )


CSP_HEADER = _build_csp()

# Always revalidated: the HTML references the current ?v= assets and the
# service worker must reach clients on the very next navigation (Cloudflare
# honours this at the edge too). Cache-busted assets are immutable per version;
# any other static file (icons, ES modules imported without ?v=) is revalidated
# by ETag so the edge never serves a stale module next to a new app.js?v=N.
NO_CACHE_PATHS = frozenset({"/", "/index.html", "/service-worker.js"})
CACHE_CONTROL_NO_CACHE = "no-cache"
CACHE_CONTROL_NO_STORE = "no-store"
CACHE_CONTROL_IMMUTABLE = "public, max-age=31536000, immutable"


def _cache_control(path: str, query_string: bytes, status: int) -> str | None:
    if path in NO_CACHE_PATHS:
        return CACHE_CONTROL_NO_CACHE
    if path.startswith("/api/"):
        return CACHE_CONTROL_NO_STORE
    if "v" in QueryParams(query_string):
        # Never let a 404 for a versioned URL (typo, mid-deploy) become
        # immutable at the edge for a year.
        return CACHE_CONTROL_IMMUTABLE if status in {200, 304} else None
    return CACHE_CONTROL_NO_CACHE


class SecurityHeadersMiddleware:
    """Add CSP, MIME-sniffing and referrer protection, and cache policy headers.

    Pure ASGI: the headers are added to the ``http.response.start`` message.
    Non-HTTP scopes pass through untouched.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap ``app``."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Set the security and caching headers on every HTTP response."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Content-Security-Policy"] = CSP_HEADER
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                cache_control = _cache_control(
                    scope["path"], scope["query_string"], message["status"]
                )
                if cache_control and "cache-control" not in headers:
                    headers["Cache-Control"] = cache_control
            await send(message)

        await self.app(scope, receive, send_with_headers)


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
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Starlette runs the middleware added LAST as the outermost layer, so the order
# below yields: SecurityHeaders -> RateLimit (client IP + /api/* limit) -> CORS
# -> app. SecurityHeaders is outermost so that a 429 gets the headers too.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(weather_router)

# Serve frontend from static files
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
