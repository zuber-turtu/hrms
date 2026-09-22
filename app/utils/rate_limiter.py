import time
import threading
from typing import Dict, List, Optional
from fastapi import Request, HTTPException, status


class SlidingWindowRateLimiter:
    """
    Thread-safe in-memory Sliding Window Rate Limiter.
    Tracks timestamps of requests per client key (IP or IP+Identifier).
    """

    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._records: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def _get_client_ip(self, request: Request) -> str:
        # Check reverse proxy headers (Cloudflare CF-Connecting-IP, X-Forwarded-For)
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip.strip()

        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        if request.client and request.client.host:
            return request.client.host

        return "127.0.0.1"

    def check(self, request: Request, identifier: Optional[str] = None) -> None:
        """
        Validates request against rate limit.
        Raises HTTPException(429) if threshold exceeded.
        """
        ip = self._get_client_ip(request)
        key = f"{ip}:{identifier.strip().lower()}" if identifier else ip
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            # Clean up old timestamps for this key
            timestamps = self._records.get(key, [])
            valid_timestamps = [ts for ts in timestamps if ts > window_start]

            if len(valid_timestamps) >= self.max_requests:
                oldest = valid_timestamps[0]
                retry_after = max(1, int(self.window_seconds - (now - oldest)))
                self._records[key] = valid_timestamps
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many failed attempts. Please try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )

            # Record this attempt
            valid_timestamps.append(now)
            self._records[key] = valid_timestamps

            # Periodic cleanup of completely stale keys
            if len(self._records) > 2000:
                self._cleanup_stale_records(now)

    def reset(self, request: Request, identifier: Optional[str] = None) -> None:
        """Clears records for this key upon successful authentication."""
        ip = self._get_client_ip(request)
        key = f"{ip}:{identifier.strip().lower()}" if identifier else ip
        with self._lock:
            self._records.pop(key, None)
            if identifier:
                self._records.pop(ip, None)

    def _cleanup_stale_records(self, now: float) -> None:
        window_start = now - self.window_seconds
        stale_keys = [
            k for k, v in self._records.items() if not v or v[-1] <= window_start
        ]
        for k in stale_keys:
            self._records.pop(k, None)


# Global Login Rate Limiter: 5 attempts per 60 seconds per IP/Account
login_rate_limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
