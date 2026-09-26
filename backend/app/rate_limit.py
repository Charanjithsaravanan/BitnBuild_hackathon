from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request

try:
    from redis import Redis
except Exception:  # pragma: no cover
    Redis = None

from .config import get_settings

_memory: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def _key(request: Request, bucket: str) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return f"labforge:rl:{bucket}:{ip}"


def enforce_rate_limit(request: Request, bucket: str, limit: int, window_seconds: int = 60) -> None:
    settings = get_settings()
    key = _key(request, bucket)
    now = time.time()

    if settings.redis_url and Redis is not None:
        try:
            redis = Redis.from_url(settings.redis_url, decode_responses=True)
            current = int(redis.incr(key))
            if current == 1:
                redis.expire(key, window_seconds)
            if current > limit:
                raise HTTPException(status_code=429, detail="Too many requests. Please try again shortly.")
            return
        except HTTPException:
            raise
        except Exception:
            # Availability beats strict limiting in development; the in-memory
            # fallback still protects a single process.
            pass

    with _lock:
        q = _memory[key]
        cutoff = now - window_seconds
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(status_code=429, detail="Too many requests. Please try again shortly.")
        q.append(now)
