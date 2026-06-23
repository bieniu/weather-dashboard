"""Rate limiting middleware — sliding window per IP."""

import time
from collections import defaultdict, deque
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp

RATE_LIMIT = 100
WINDOW_SECONDS = 60
CLEANUP_EVERY = 100


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter keyed by `request.state.real_ip`.

    Returns 429 Too Many Requests when the limit is exceeded.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialise rate limiter with empty windows."""
        super().__init__(app)
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._request_count = 0

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Check rate limit and reject with 429 if exceeded."""
        if request.url.path.startswith("/api/weather/ws"):
            return await call_next(request)

        ip = getattr(request.state, "real_ip", "unknown")
        now = time.monotonic()
        window = self._windows[ip]

        while window and window[0] <= now - WINDOW_SECONDS:
            window.popleft()

        if len(window) >= RATE_LIMIT:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests — try again later."},
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )

        window.append(now)

        self._request_count += 1
        if self._request_count % CLEANUP_EVERY == 0:
            self._cleanup()

        return await call_next(request)

    def _cleanup(self) -> None:
        now = time.monotonic()
        cutoff = now - WINDOW_SECONDS
        expired = [ip for ip, w in self._windows.items() if not w or w[-1] <= cutoff]
        for ip in expired:
            del self._windows[ip]
