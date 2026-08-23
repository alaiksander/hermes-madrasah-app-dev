"""Rate limiter sederhana untuk endpoint login (anti brute-force).

Tanpa dependensi ekstern — pakai in-memory dict {key: list_timestamps}.
Membatasi N percobaan per menit per key (biasanya IP address).

Catatan:
- In-memory (reset saat service restart). Untuk production multi-worker
  sebaiknya pakai Redis, tapi cukup untuk VPS single-process.
- Gunakan sebagai dependency FastAPI: Depends(rate_limit_login)
"""

import time
import threading
from collections import defaultdict, deque
from typing import Callable

from fastapi import HTTPException, Request

# Konfigurasi: maks 5 percobaan login per 60 detik per IP
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 60

_lock = threading.Lock()
# {ip: deque[timestamp]}
_attempts: dict[str, deque] = defaultdict(deque)


def _cleanup(now: float) -> None:
    """Buang timestamp lama dari window."""
    for ip in list(_attempts):
        dq = _attempts[ip]
        while dq and now - dq[0] > WINDOW_SECONDS:
            dq.popleft()
        if not dq:
            del _attempts[ip]


def rate_limit_login(request: Request) -> None:
    """Dependency FastAPI: blokir kalau IP sudah terlalu banyak percobaan login."""
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    with _lock:
        _cleanup(now)
        dq = _attempts[ip]
        if len(dq) >= MAX_ATTEMPTS:
            # blokir
            retry_after = int(WINDOW_SECONDS - (now - dq[0])) + 1
            raise HTTPException(
                status_code=429,
                detail="Terlalu banyak percobaan. Coba lagi nanti.",
                headers={"Retry-After": str(retry_after)},
            )
        # catat percobaan (dipanggil di awal request)
        dq.append(now)
