"""Auth: login tenant (kode madrasah) + login super admin"""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import GlobalSession, tenant_session_factory
from ..deps import get_current_user, maintenance_block
from ..models import Guru, SuperAdmin, Tenant
from ..schemas import LoginRequest, SuperLoginRequest, TokenResponse, UserMe
from ..security import create_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

WIB = ZoneInfo("Asia/Jakarta")


def get_global_db():
    with GlobalSession() as s:
        yield s


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, gs: Session = Depends(get_global_db)):
    """Login guru/admin madrasah: kode_madrasah + username + password."""
    maintenance_block()
    tenant = gs.query(Tenant).filter_by(kode=data.kode_madrasah).first()
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kode madrasah tidak ditemukan")
    if tenant.status == "suspended":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Madrasah sedang disuspend — hubungi admin")
    if (tenant.masa_langganan_hingga
            and tenant.masa_langganan_hingga < datetime.now(WIB).date()):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Masa langganan telah berakhir — hubungi admin platform")

    with tenant_session_factory(tenant.kode)() as s:
        guru = s.query(Guru).filter_by(username=data.username).first()
        if not guru or not verify_password(data.password, guru.password_hash):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Username atau password salah")
        if not guru.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Akun dinonaktifkan")
        guru.last_login = datetime.now(WIB)
        s.commit()

    # Heartbeat: catat aktivitas terakhir tenant (untuk dashboard superadmin)
    tenant.last_active_at = datetime.now(WIB)
    gs.commit()

    token = create_token({
        "sub": str(guru.id),
        "role": guru.role,
        "tenant_id": str(tenant.id),
        "tenant_kode": tenant.kode,
    })
    return TokenResponse(access_token=token, role=guru.role, nama=guru.nama,
                         tenant_kode=tenant.kode, tenant_nama=tenant.nama)


@router.post("/login-super", response_model=TokenResponse)
def login_super(data: SuperLoginRequest, gs: Session = Depends(get_global_db)):
    """Login super admin (kelola seluruh tenant)."""
    sa = gs.query(SuperAdmin).filter_by(username=data.username).first()
    if not sa or not verify_password(data.password, sa.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Username atau password salah")

    token = create_token({"sub": str(sa.id), "role": "super_admin"})
    return TokenResponse(access_token=token, role="super_admin", nama=sa.nama)

@router.get("/me", response_model=UserMe)
def me(user: dict = Depends(get_current_user)):
    tenant_nama = None
    if user.get("tenant_kode"):
        with GlobalSession() as gs:
            t = gs.query(Tenant).filter_by(kode=user["tenant_kode"]).first()
            tenant_nama = t.nama if t else None
    return UserMe(id=user["id"], username=user["username"], nama=user["nama"],
                  role=user["role"], tenant_kode=user.get("tenant_kode"),
                  tenant_nama=tenant_nama)
