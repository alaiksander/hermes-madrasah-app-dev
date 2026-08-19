"""Shared router untuk web panel: login, logout, root, static.

Prefix: /madrasah-app (lihat main.py untuk include).
Modul-modul (absensi, jurnal, dll) include router masing-masing
di bawah prefix /madrasah-app/<modul>.
"""
import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response

from .core.auth import clear_token_cookie, get_token_from_request, set_token_cookie
from .core.deps import get_current_user_web
from .core.templates import templates

router = APIRouter(tags=["web-shared"])

API_BASE = "http://127.0.0.1:8010"


@router.get("/")
async def root(request: Request):
    """Redirect ke default modul — role-aware:
    superadmin → /superadmin/dashboard, tenant admin/guru → /absensi/dashboard."""
    try:
        user = get_current_user_web(request)
        if user.get("role") == "super_admin":
            return RedirectResponse("/madrasah-app/superadmin/dashboard", status_code=303)
    except Exception:
        pass
    return RedirectResponse("/madrasah-app/absensi/dashboard", status_code=303)


@router.get("/login")
async def login_page(request: Request):
    """Tampilkan form login. Kalau sudah login, langsung ke dashboard."""
    try:
        user = get_current_user_web(request)
        if user.get("role") == "super_admin":
            return RedirectResponse("/madrasah-app/superadmin/dashboard", status_code=303)
        return RedirectResponse("/madrasah-app/absensi/dashboard", status_code=303)
    except Exception:
        pass
    next_path = request.query_params.get("next", "")
    return templates.TemplateResponse(
        request, "login.html", {"error": None, "next": next_path}
    )


@router.post("/login")
async def login_submit(
    request: Request,
    kode: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(""),
):
    """Login → panggil API existing → set cookie."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            f"{API_BASE}/api/auth/login",
            json={"kode_madrasah": kode, "username": username, "password": password},
        )

    if r.status_code != 200:
        # Map error → user-friendly message
        try:
            detail = r.json().get("detail", "Login gagal")
        except Exception:
            detail = "Login gagal"
        error_msg = {
            401: "Kode madrasah, username, atau kata sandi salah",
            403: detail,
            404: f"Kode madrasah '{kode}' tidak ditemukan",
            503: "Sistem sedang dalam pemeliharaan. Coba lagi nanti.",
        }.get(r.status_code, detail)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": error_msg, "kode": kode, "username": username, "next": next},
            status_code=r.status_code,
        )

    data = r.json()
    token = data["access_token"]
    expire_hours = 12  # sinkron dengan config.py jwt_expire_hours default

    # Redirect ke next kalau valid (path internal /madrasah-app/* saja)
    safe_next = ""
    if next.startswith("/madrasah-app/") and "//" not in next and "\\" not in next:
        safe_next = next
    response = RedirectResponse(
        safe_next or "/madrasah-app/absensi/dashboard", status_code=303
    )
    set_token_cookie(response, token, max_age_seconds=expire_hours * 3600,
                     secure=request.url.scheme == "https")
    return response


@router.get("/login-super")
async def login_super_page(request: Request):
    """Halaman login super admin (terpisah dari login tenant)."""
    try:
        u = get_current_user_web(request)
        if u.get("role") == "super_admin":
            return RedirectResponse("/madrasah-app/superadmin/dashboard", status_code=303)
    except Exception:
        pass
    return templates.TemplateResponse(
        request,
        "login_super.html",
        {"error": None, "next": request.query_params.get("next", "")},
    )


@router.post("/login-super")
async def login_super_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(""),
):
    """Login super admin → POST /api/auth/login-super → set cookie."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            f"{API_BASE}/api/auth/login-super",
            json={"username": username, "password": password},
        )

    if r.status_code != 200:
        try:
            detail = r.json().get("detail", "Login gagal")
        except Exception:
            detail = "Login gagal"
        error_msg = {
            401: "Username atau kata sandi salah",
            503: "Sistem sedang dalam pemeliharaan. Coba lagi nanti.",
        }.get(r.status_code, detail)
        return templates.TemplateResponse(
            request,
            "login_super.html",
            {"error": error_msg, "username": username, "next": next},
            status_code=r.status_code,
        )

    data = r.json()
    token = data["access_token"]
    expire_hours = 12

    safe_next = ""
    if next.startswith("/madrasah-app/") and "//" not in next and "\\" not in next:
        safe_next = next
    response = RedirectResponse(
        safe_next or "/madrasah-app/superadmin/dashboard", status_code=303
    )
    set_token_cookie(response, token, max_age_seconds=expire_hours * 3600,
                     secure=request.url.scheme == "https")
    return response


@router.post("/logout")
async def logout():
    """Hapus cookie → redirect ke login."""
    response = RedirectResponse("/madrasah-app/login", status_code=303)
    clear_token_cookie(response)
    return response


# Catatan: Handler HTTP error (404/500) didefinisikan di main.py
# sebagai app.exception_handler — bukan di router. Lihat main.py:web_panel_http_exception_handler.


@router.get("/static-htmx-check")
async def static_check():
    """Sanity endpoint: cek apakah static served di /madrasah-app/static/."""
    return Response(content="ok", media_type="text/plain")