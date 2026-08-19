"""HTTP client helper untuk forward dari web panel ke API JSON existing.

Backend FastAPI serve di 127.0.0.1:8010, JSON API di /api/* (dipakai Flutter).
Web panel forward via HTTP supaya:
- Decoupling (web tidak import service function langsung)
- Konsisten dengan API contract (single source of truth)
- Auth otomatis via Authorization header dari cookie
"""
import httpx
from fastapi import Request

from .auth import get_token_from_request

API_BASE = "http://127.0.0.1:8010"


def _headers(request: Request) -> dict:
    """Headers dengan JWT Bearer dari cookie."""
    token = get_token_from_request(request)
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


async def api_get(request: Request, path: str, **params):
    """GET ke API existing. Return httpx Response."""
    async with httpx.AsyncClient(timeout=10) as c:
        return await c.get(
            f"{API_BASE}{path}",
            params={k: v for k, v in params.items() if v not in (None, "")},
            headers=_headers(request),
        )


async def api_get_raw(request: Request, path: str, **params) -> bytes:
    """GET yang return bytes (untuk binary seperti Excel/PDF/QR PNG)."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            f"{API_BASE}{path}",
            params={k: v for k, v in params.items() if v not in (None, "")},
            headers=_headers(request),
        )
        r.raise_for_status()
        return r.content


async def api_post(request: Request, path: str, json: dict | None = None,
                   raw_json: bool = False):
    """POST ke API existing. raw_json=True → kirim body mentah (list/str)."""
    import json as _json
    async with httpx.AsyncClient(timeout=10) as c:
        if raw_json:
            return await c.post(
                f"{API_BASE}{path}",
                content=_json.dumps(json or []),
                headers={**_headers(request), "Content-Type": "application/json"},
            )
        return await c.post(
            f"{API_BASE}{path}",
            json=json or {},
            headers=_headers(request),
        )


async def api_put(request: Request, path: str, json: dict | None = None):
    """PUT ke API existing."""
    async with httpx.AsyncClient(timeout=10) as c:
        return await c.put(
            f"{API_BASE}{path}",
            json=json or {},
            headers=_headers(request),
        )


async def api_patch(request: Request, path: str, json: dict | None = None):
    """PATCH ke API existing."""
    async with httpx.AsyncClient(timeout=10) as c:
        return await c.patch(
            f"{API_BASE}{path}",
            json=json or {},
            headers=_headers(request),
        )


async def api_delete(request: Request, path: str, json: dict | None = None):
    """DELETE ke API existing."""
    async with httpx.AsyncClient(timeout=10) as c:
        return await c.request(
            "DELETE",
            f"{API_BASE}{path}",
            headers=_headers(request),
            json=json,
        )


async def api_post_multipart(
    request: Request,
    path: str,
    files: dict,
    data: dict | None = None,
):
    """POST multipart (untuk upload Excel dsb)."""
    async with httpx.AsyncClient(timeout=30) as c:
        return await c.post(
            f"{API_BASE}{path}",
            files=files,
            data=data or {},
            headers=_headers(request),
        )