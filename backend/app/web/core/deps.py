"""Auth deps untuk web pages.

Berbeda dari `app/deps.py` (yang dipakai API JSON):
- Read JWT dari cookie (bukan Authorization header)
- Return dict user (sama shape dengan `get_current_user` di app/deps.py)
- Redirect ke /madrasah-app/login (bukan raise 401)
"""
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from ...security import decode_token
from .auth import get_token_from_request


def get_current_user_web(request: Request) -> dict:
    """Decode JWT dari cookie, return dict user (atau raise 401).

    Shape identik dengan `app.deps.get_current_user`:
        {id, username, nama, role, tenant_id, tenant_kode}

    JWT payload tidak berisi nama/username (hanya sub+role+tenant).
    Lookup nama dari DB kalau tenant_kode ada, supaya greeting lebih personal.
    """
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(401, "Login diperlukan")
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(401, "Token tidak valid")

    role = payload.get("role")
    user_id = payload.get("sub")
    if not role or not user_id:
        raise HTTPException(401, "Token tidak lengkap")

    user = {
        "id": int(user_id),
        "username": "",
        "nama": "Pengguna",
        "role": role,
        "tenant_id": payload.get("tenant_id"),
        "tenant_kode": payload.get("tenant_kode"),
    }

    # Lookup identitas lengkap dari DB — superadmin tidak punya tenant_kode.
    # Sama logic dengan `app.deps.get_current_user` (zero regression ke API existing).
    try:
        from ...db import tenant_session_factory
        from ...models import Guru, SuperAdmin
        from ...db import GlobalSession
        if role == "super_admin":
            with GlobalSession() as s:
                sa = s.get(SuperAdmin, int(user_id))
                if sa:
                    user["username"] = sa.username
                    user["nama"] = sa.nama
        elif user["tenant_kode"]:
            with tenant_session_factory(user["tenant_kode"])() as s:
                g = s.get(Guru, int(user_id))
                if g and g.is_active:
                    user["username"] = g.username
                    user["nama"] = g.nama
                    # Tambah role_id untuk has_perm() lookup (Fase 2)
                    if g.role_id:
                        user["role_id"] = g.role_id
    except Exception:
        pass  # fallback ke "Pengguna" kalau DB error

    return user


def require_login_web(request: Request):
    """Dependency: redirect ke login kalau belum auth.

    Mengembalikan user dict kalau OK. Template-side bisa pakai
    `user.role`, `user.nama`, `user.tenant_kode`, dll.

    CATATAN: super_admin DITOLAK (403) — semua halaman modul absensi
    butuh tenant (guru/admin). Super admin punya panel sendiri di
    /madrasah-app/superadmin/*.
    """
    try:
        user = get_current_user_web(request)
    except HTTPException:
        # Redirect (bukan raise) — lebih natural untuk browser navigation
        raise _RedirectToLogin()
    if user.get("role") == "super_admin":
        raise HTTPException(403, "Halaman ini khusus akun tenant (guru/admin)")
    return user


class _RedirectToLogin(Exception):
    """Internal: signal ke handler untuk redirect ke login."""


def handle_login_redirect(request: Request, exc: Exception | None = None) -> RedirectResponse:
    """Convert exception ke RedirectResponse."""
    return RedirectResponse("/madrasah-app/login", status_code=303)


def require_admin_web(user: dict = Depends(get_current_user_web)) -> dict:
    """Dependency: HANYA admin tenant (bukan guru, BUKAN super_admin).

    Super admin punya panel sendiri di /madrasah-app/superadmin/* —
    mereka TIDAK boleh melihat halaman/fitur admin tenant.
    """
    if user.get("role") != "admin":
        raise HTTPException(403, "Hanya admin tenant yang dapat mengakses")
    return user


def require_permission_web(*kode: str):
    """Dependency: butuh salah satu permission (OR) untuk halaman web.

    Sama pola `require_permission` API tapi untuk web — user dict dari
    cookie. Super_admin → True (biar bisa preview). Admin role → True
    semua. Guru → ROLE_DEFAULT_PERMISSIONS. Role custom → lookup DB.

    Kalau tidak punya → HTTPException 403 (bukan redirect login).
    """
    def checker(user: dict = Depends(get_current_user_web)) -> dict:
        # Reuse logic dari templates.py _has_perm — panggil helper global
        from .templates import _has_perm
        if any(_has_perm(user, k) for k in kode):
            return user
        raise HTTPException(403, f"Tidak punya permission: {'/'.join(kode)}")
    return checker

def require_super_admin_web(user: dict = Depends(get_current_user_web)) -> dict:
    """Dependency: HANYA super_admin (tenant admin/guru TIDAK boleh).

    Dipakai untuk semua endpoint /madrasah-app/superadmin/*.
    """
    if user.get("role") != "super_admin":
        raise HTTPException(403, "Hanya Super Admin yang dapat mengakses")
    return user