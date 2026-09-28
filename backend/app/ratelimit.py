"""Client-IP resolution and sliding-window rate limiting per IP (pure ASGI)."""

import time
from collections import OrderedDict, deque
from typing import TYPE_CHECKING

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

RATE_LIMIT = 100
WINDOW_SECONDS = 60
CLEANUP_EVERY = 100
LIMITED_PATH_PREFIX = "/api/"
# Upper bound on distinct client keys kept in memory. Only reachable if
# Cf-Connecting-IP can be forged (i.e. the port is exposed past the tunnel);
# then the least recently seen key is evicted instead of growing without limit.
MAX_TRACKED_IPS = 10_000


def client_ip(scope: Scope) -> str:
    """Return the client IP: ``Cf-Connecting-IP``, else the socket peer.

    The Cloudflare tunnel is the only public entry point, so the header is
    trusted; uvicorn runs without ``--proxy-headers``.
    """
    cf_ip = Headers(scope=scope).get("cf-connecting-ip")
    if cf_ip:
        return cf_ip
    client = scope.get("client")
    return client[0] if client else "unknown"


class RateLimitMiddleware:
    """Resolve the client IP and apply a sliding-window limit to ``/api/*``.

    The IP is stored as ``scope["state"]["real_ip"]`` (``request.state.real_ip``)
    for every HTTP request; only paths under ``/api/`` are counted, so static
    assets pass through. Non-HTTP scopes (WebSocket, lifespan) pass through
    untouched. Returns 429 Too Many Requests when the limit is exceeded.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap ``app`` with empty per-IP windows."""
        self.app = app
        # Ordered by last access so eviction drops the least recently seen key.
        self._windows: OrderedDict[str, deque[float]] = OrderedDict()
        self._request_count = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reject with 429 when the client's window is full, else forward."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        ip = client_ip(scope)
        scope.setdefault("state", {})["real_ip"] = ip
        if scope["path"].startswith(LIMITED_PATH_PREFIX) and not self._allow(ip):
            response = JSONResponse(
                status_code=429,
                content={"detail": "Too many requests — try again later."},
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _allow(self, ip: str) -> bool:
        """Record a hit for ``ip``; ``False`` if its window is already full."""
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
            return False

        window.append(now)

        self._request_count += 1
        if self._request_count % CLEANUP_EVERY == 0:
            self._cleanup()
        return True

    def _cleanup(self) -> None:
        now = time.monotonic()
        cutoff = now - WINDOW_SECONDS
        expired = [ip for ip, w in self._windows.items() if not w or w[-1] <= cutoff]
        for ip in expired:
            del self._windows[ip]
