"""Per-user in-memory rate limiter. Sufficient for single-process MVP."""

import time
from collections import defaultdict

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # {user_token: [timestamp, ...]}
        self._minute_log: dict[str, list[float]] = defaultdict(list)
        self._day_log: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Only rate-limit authenticated API endpoints
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer ") or not request.url.path.startswith("/api/"):
            return await call_next(request)

        token = auth_header[7:]
        now = time.time()

        # Clean old entries and check minute limit
        minute_ago = now - 60
        self._minute_log[token] = [t for t in self._minute_log[token] if t > minute_ago]
        if len(self._minute_log[token]) >= settings.rate_limit_per_minute:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded. Try again in a minute."},
            )

        # Check daily limit
        day_ago = now - 86400
        self._day_log[token] = [t for t in self._day_log[token] if t > day_ago]
        if len(self._day_log[token]) >= settings.rate_limit_per_day:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Daily rate limit exceeded."},
            )

        self._minute_log[token].append(now)
        self._day_log[token].append(now)

        return await call_next(request)
