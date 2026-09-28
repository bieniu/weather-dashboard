"""Rate limiting middleware — sliding window per IP."""

import time
from collections import OrderedDict, deque
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
LIMITED_PATH_PREFIX = "/api/"
# Upper bound on distinct client keys kept in memory. Only reachable if
# Cf-Connecting-IP can be forged (i.e. the port is exposed past the tunnel);
# then the least recently seen key is evicted instead of growing without limit.
MAX_TRACKED_IPS = 10_000


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter keyed by `request.state.real_ip`.

    Only paths under ``/api/`` are counted; static assets pass through untouched.
    WebSocket upgrades never reach ``dispatch`` (BaseHTTPMiddleware forwards
    non-HTTP scopes directly), so they are not limited here.
    Returns 429 Too Many Requests when the limit is exceeded.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialise rate limiter with empty windows."""
        super().__init__(app)
        # Ordered by last access so eviction drops the least recently seen key.
        self._windows: OrderedDict[str, deque[float]] = OrderedDict()
        self._request_count = 0

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Check rate limit and reject with 429 if exceeded."""
        if not request.url.path.startswith(LIMITED_PATH_PREFIX):
            return await call_next(request)

        ip = getattr(request.state, "real_ip", "unknown")
        now = time.monotonic()
        window = self._windows.get(ip)
        if window is None:
            if len(self._windows) >= MAX_TRACKED_IPS:
                self._windows.popitem(last=False)
            window = self._windows[ip] = deque()
        else:
            # Also on the 429 path: a throttled client is still "recently seen"
            # and must not be the eviction victim; only idle keys should age out.
            self._windows.move_to_end(ip)

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
