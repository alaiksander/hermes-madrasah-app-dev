"""Role & Permission Management (Fase 3).

API untuk admin tenant mengelola role custom + permission matrix.
- GET /api/roles - daftar role (sistem + custom)
- POST /api/roles - buat role baru
- PATCH /api/roles/{id} - edit nama/label
- DELETE /api/roles/{id} - hapus role (jika bukan sistem + tidak ada guru)
- GET /api/permissions - daftar semua permission (grouped by kategori)
- GET /api/roles/{id}/permissions - permission role tertentu
- POST /api/roles/{id}/permissions - update permission role (atomic replace)
- GET /api/roles/{id}/guru - daftar guru yang pakai role ini
"""
import json
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import get_tenant_db, require_permission
from ..models import Guru, Permission, Role, RolePermission

router = APIRouter(prefix="/api/roles", tags=["roles"])


# ── Schemas ───────────────────────────────────────────────────────────────

class RoleCreate(BaseModel):
    nama: str
    label: str = ""


class RoleUpdate(BaseModel):
    label: str | None = None


class ReplacementPerRole(BaseModel):
    """Set lengkap permission kode (replace total)."""
    permissions: list[str]


# ── Helpers ──────────────────────────────────────────────────────────────

def _role_to_dict(role: Role, perm_count: int = 0) -> dict:
    return {
        "id": role.id,
        "nama": role.nama,
        "label": role.label or "",
        "is_system": bool(role.is_system),
        "legacy_role": role.legacy_role,
        "perm_count": perm_count,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.get("")
def list_roles(db: Session = Depends(get_tenant_db),
                user: dict = Depends(require_permission("role.view"))):
    """List semua role (sistem + custom) + jumlah permission."""
    out = []
    for r in db.query(Role).order_by(Role.is_system.desc(), Role.nama).all():
        n = db.query(RolePermission).filter_by(role_id=r.id).count()
        out.append(_role_to_dict(r, n))
    return out


@router.get("/permissions")
def list_permissions(db: Session = Depends(get_tenant_db),
                    user: dict = Depends(require_permission("role.view"))):
    """List permission grouped by kategori (untuk matrix UI)."""
    grouped: dict[str, list] = defaultdict(list)
    for p in db.query(Permission).order_by(Permission.kategori, Permission.id).all():
        grouped[p.kategori].append({"kode": p.kode, "label": p.label or p.kode})
    return [{"kategori": k, "perms": v} for k, v in sorted(grouped.items())]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_role(data: RoleCreate,
                db: Session = Depends(get_tenant_db),
                user: dict = Depends(require_permission("role.update"))):
    """Buat role baru. Default: zero permission (admin set nanti)."""
    if not data.nama or not data.nama.strip():
        raise HTTPException(400, "Nama role tidak boleh kosong")
    nama = data.nama.strip()
    if db.query(Role).filter_by(nama=nama).first():
        raise HTTPException(400, f"Nama role '{nama}' sudah ada")
    role = Role(nama=nama, label=data.label or nama, is_system=False)
    db.add(role)
    db.commit()
    db.refresh(role)
    return _role_to_dict(role, 0)


@router.patch("/{role_id}")
def update_role(role_id: int, data: RoleUpdate,
                db: Session = Depends(get_tenant_db),
                user: dict = Depends(require_permission("role.update"))):
    """Edit label role. Nama role tidak dapat diubah (identifier)."""
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "Role tidak ditemukan")
    if data.label is not None:
        role.label = data.label.strip()
    db.commit()
    n = db.query(RolePermission).filter_by(role_id=role.id).count()
    return _role_to_dict(role, n)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: int,
                db: Session = Depends(get_tenant_db),
                user: dict = Depends(require_permission("role.update"))):
    """Hapus role. Sistem role tidak bisa dihapus. Tidak boleh kalau ada guru."""
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "Role tidak ditemukan")
    if role.is_system:
        raise HTTPException(400, "Role sistem tidak dapat dihapus")
    pakai = db.query(Guru).filter_by(role_id=role_id).count()
    if pakai > 0:
        raise HTTPException(400, f"Role dipakai oleh {pakai} guru. "
                                "Pindahkan guru ke role lain dulu.")
    # Hapus role_permissions
    db.query(RolePermission).filter_by(role_id=role_id).delete()
    db.delete(role)
    db.commit()
    return None


@router.get("/{role_id}/permissions")
def get_role_permissions(role_id: int,
                         db: Session = Depends(get_tenant_db),
                         user: dict = Depends(require_permission("role.view"))):
    """List kode permission yang dimiliki role (untuk preselect checkbox)."""
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "Role tidak ditemukan")
    rows = db.query(Permission.kode).join(
        RolePermission, RolePermission.permission_id == Permission.id
    ).filter(RolePermission.role_id == role_id).all()
    return [r[0] for r in rows]


@router.post("/{role_id}/permissions")
def set_role_permissions(role_id: int, data: ReplacementPerRole,
                         db: Session = Depends(get_tenant_db),
                         user: dict = Depends(require_permission("role.update"))):
    """Replace permission role (atomic).permissions: list kode."""
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "Role tidak ditemukan")
    # Validasi: semua kode harus exist
    valid_codes = {p.kode for p in db.query(Permission).all()}
    invalid = [k for k in data.permissions if k not in valid_codes]
    if invalid:
        raise HTTPException(400, f"Permission kode tidak dikenal: {invalid}")
    # Hapus semua permission lama + insert baru
    db.query(RolePermission).filter_by(role_id=role_id).delete()
    for kode in data.permissions:
        p = db.query(Permission).filter_by(kode=kode).first()
        if p:
            db.add(RolePermission(role_id=role_id, permission_id=p.id))
    db.commit()
    return {"role_id": role_id, "count": len(data.permissions)}


@router.get("/{role_id}/guru")
def role_guru_list(role_id: int,
                   db: Session = Depends(get_tenant_db),
                   user: dict = Depends(require_permission("role.view"))):
    """List guru yang memakai role ini."""
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "Role tidak ditemukan")
    gurus = db.query(Guru).filter_by(role_id=role_id).order_by(Guru.nama).all()
    return [{"id": g.id, "nama": g.nama, "username": g.username,
             "is_active": bool(g.is_active)} for g in gurus]
