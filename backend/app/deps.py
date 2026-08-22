"""Dependencies FastAPI — autentikasi + resolusi tenant"""
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

import jwt

from .db import GlobalSession, tenant_session_factory
from .models import GlobalSetting, Guru, SuperAdmin, Tenant
from .security import decode_token

bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Login diperlukan / token tidak valid",
    headers={"WWW-Authenticate": "Bearer"},
)


def _maintenance_on() -> bool:
    """Maintenance mode global (superadmin tetep bisa, tenant diblokir)."""
    try:
        with GlobalSession() as s:
            g = s.get(GlobalSetting, 1)
            return bool(g and g.maintenance)
    except Exception:  # noqa: BLE001
        return False


def maintenance_block() -> None:
    """Blokir akses tenant nalika maintenance (503)."""
    if _maintenance_on():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Maintenance: sistem sedang dalam pemeliharaan. Coba lagi nanti.",
        )


def _fail() -> HTTPException:
    return _UNAUTHORIZED


def get_current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    """Maca token -> bali dict user. Super admin (global) utawa guru/admin (tenant)."""
    if not cred:
        raise _UNAUTHORIZED
    try:
        payload = decode_token(cred.credentials)
    except jwt.PyJWTError:
        raise _UNAUTHORIZED

    role = payload.get("role")
    user_id = payload.get("sub")
    if not role or not user_id:
        raise _UNAUTHORIZED

    if role == "super_admin":
        with GlobalSession() as s:
            u = s.get(SuperAdmin, int(user_id))
            if not u:
                raise _UNAUTHORIZED
        return {"id": u.id, "username": u.username, "nama": u.nama,
                "role": "super_admin", "tenant_id": None, "tenant_kode": None}

    maintenance_block()
    kode = payload.get("tenant_kode")
    if not kode:
        raise _UNAUTHORIZED
    with tenant_session_factory(kode)() as s:
        u = s.get(Guru, int(user_id))
        if not u or not u.is_active:
            raise _UNAUTHORIZED
    return {"id": u.id, "username": u.username, "nama": u.nama,
            "role": u.role, "role_id": u.role_id,
            "tenant_id": payload.get("tenant_id"), "tenant_kode": kode}


def require_roles(*roles: str):
    """Backward-compat: require role legacy (admin/guru)."""
    def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Tidak memiliki akses")
        return user
    return checker


def user_has_permission(db: Session, user: dict, kode: str) -> bool:
    """Cek apakah user punya permission `kode`.

    Urutan (PENTING — role custom MENANG atas role string):
    1. role_id ada → lookup RolePermission (role custom yang di-assign admin)
    2. admin → True semua
    3. guru → ROLE_DEFAULT_PERMISSIONS
    """
    role_id = user.get("role_id")
    # Role custom (di-assign via Role Manager) → permission dari DB
    if role_id:
        from .models import Permission, RolePermission
        p = db.query(Permission).filter_by(kode=kode).first()
        if not p:
            return False
        return db.query(RolePermission).filter_by(
            role_id=role_id, permission_id=p.id).first() is not None

    if user.get("role") == "admin":
        return True
    if user.get("role") == "guru":
        from .permissions import ROLE_DEFAULT_PERMISSIONS
        return kode in ROLE_DEFAULT_PERMISSIONS["guru"]
    return False


def require_permission(*kode: str):
    """Dependency: butuh salah satu permission (OR)."""
    def checker(user: dict = Depends(get_current_user),
                db: Session = Depends(get_tenant_db)) -> dict:
        if user.get("role") == "super_admin":
            return user
        for k in kode:
            if user_has_permission(db, user, k):
                return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"Tidak punya permission: {'/'.join(kode)}")
    return checker


def get_tenant_db(user: dict = Depends(get_current_user)) -> Session:
    """Session DB menyang tenant-nya user sing login.

    Wajib yield-based supaya FastAPI otomatis menutup session setelah
    request selesai (commit sukses / rollback gagal). Tanpa ini, session
    bocor → koneksi 'idle in transaction' menumpuk → pool habis →
    QueuePool timeout (kejadian 2026-08-19 di prod, 4 koneksi 21 jam).
    """
    if user["role"] == "super_admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Super admin tidak memiliki konteks tenant")
    code = user["tenant_kode"]
    db = tenant_session_factory(code)()
    try:
        _ensure_tenant_seeded(db, code)
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


_SEEDED_TENANTS: set[str] = set()


def _ensure_tenant_seeded(db: Session, kode: str) -> None:
    """Idempotent: seed permissions + default roles untuk tenant DB ini."""
    if kode in _SEEDED_TENANTS:
        return
    from .permissions import seed_permissions, seed_default_roles
    try:
        from .models import Permission
        db.rollback()
        db.query(Permission).first()
    except Exception:
        db.rollback()
        return
    seed_permissions(db)
    seed_default_roles(db)
    # Seed master BK (kategori, pelanggaran, prestasi, konfigurasi)
    try:
        from .seed_bk import seed_bk_defaults
        db.rollback()
        seed_bk_defaults(db)
    except Exception:
        pass  # tidak fatal
    _SEEDED_TENANTS.add(kode)


def get_tenant_db_publik(kode: str = Query(...)) -> Session:
    """Session DB tenant untuk endpoint PUBLIK (tanpa login).

    Kode madrasah diambil dari query param — dipakai portal orang tua
    yang tidak memerlukan autentikasi. Validasi kode ada.
    Yield-based supaya session ditutup otomatis (anti bocor, lihat
    get_tenant_db).
    """
    from .db import GlobalSession
    with GlobalSession() as gs:
        t = gs.query(Tenant).filter_by(kode=kode.strip()).first()
        if not t:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                "Kode madrasah tidak ditemukan")
        if t.status == "suspended":
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Madrasah sedang disuspend")
    db = tenant_session_factory(kode.strip())()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_tenant_info(user: dict = Depends(get_current_user)) -> Tenant:
    """Info tenant saka registry global (kanggo validasi status)."""
    with GlobalSession() as s:
        t = s.query(Tenant).filter_by(kode=user["tenant_kode"]).first()
        if not t:
            raise HTTPException(status_code=404, detail="Tenant tidak ditemukan")
    return t
