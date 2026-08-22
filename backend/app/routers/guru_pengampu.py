"""CRUD Pengampu (guru × mapel × kelas) — pivot table penugasan mengajar."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import log_action
from ..deps import get_tenant_db, require_permission
from ..models import (Guru, GuruPengampu, Kelas, MataPelajaran, TahunAjaran)

router = APIRouter(prefix="/api/guru-pengampu", tags=["pengampu"])


# ── Pydantic schemas (inline) ──────────────────────────────────────
class PengampuIn(BaseModel):
    guru_id: int
    mapel_id: Optional[int] = None  # NULL = wali kelas (semua mapel)
    kelas_id: int
    tahun_ajaran_id: int
    is_wali: bool = False


class PengampuBulkIn(BaseModel):
    """Set/replace semua pengampu untuk 1 guru di 1 TA."""
    guru_id: int
    tahun_ajaran_id: int
    items: list[PengampuIn] = Field(default_factory=list)


class PengampuOut(BaseModel):
    id: int
    guru_id: int
    guru_nama: str
    mapel_id: Optional[int]
    mapel_nama: Optional[str]
    kelas_id: int
    kelas_nama: str
    tahun_ajaran_id: int
    tahun_ajaran_nama: str
    is_wali: bool
    is_active: bool
    created_at: str


def _serialize(p: GuruPengampu, db: Session) -> dict:
    g = db.get(Guru, p.guru_id)
    m = db.get(MataPelajaran, p.mapel_id) if p.mapel_id else None
    k = db.get(Kelas, p.kelas_id)
    ta = db.get(TahunAjaran, p.tahun_ajaran_id)
    return {
        "id": p.id,
        "guru_id": p.guru_id,
        "guru_nama": g.nama if g else "?",
        "mapel_id": p.mapel_id,
        "mapel_nama": m.nama if m else None,
        "kelas_id": p.kelas_id,
        "kelas_nama": k.nama_kelas if k else "?",
        "tahun_ajaran_id": p.tahun_ajaran_id,
        "tahun_ajaran_nama": ta.nama if ta else "?",
        "is_wali": p.is_wali,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat() if p.created_at else "",
    }


# ── List dengan filter ────────────────────────────────────────────
@router.get("", response_model=list[PengampuOut])
def list_pengampu(
    guru_id: Optional[int] = Query(None, description="Filter by guru"),
    mapel_id: Optional[int] = Query(None),
    kelas_id: Optional[int] = Query(None),
    tahun_ajaran_id: Optional[int] = Query(None),
    is_wali: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(True),
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("pengampu.view", "pengampu.kelola")),
):
    """List penugasan mengajar. Guru cuma bisa lihat penugasan sendiri."""
    q = select(GuruPengampu)
    # Authorization: guru non-admin cuma bisa lihat sendiri
    if user.get("role") not in ("admin", "super_admin") and guru_id is None:
        guru_id = int(user.get("id") or user.get("sub") or 0)
    if guru_id is not None:
        q = q.where(GuruPengampu.guru_id == guru_id)
    if mapel_id is not None:
        q = q.where(GuruPengampu.mapel_id == mapel_id)
    if kelas_id is not None:
        q = q.where(GuruPengampu.kelas_id == kelas_id)
    if tahun_ajaran_id is not None:
        q = q.where(GuruPengampu.tahun_ajaran_id == tahun_ajaran_id)
    if is_wali is not None:
        q = q.where(GuruPengampu.is_wali == is_wali)
    if is_active is not None:
        q = q.where(GuruPengampu.is_active == is_active)
    rows = db.execute(q.order_by(GuruPengampu.id)).scalars().all()
    return [_serialize(r, db) for r in rows]


# ── List per guru (shortcut) ─────────────────────────────────────
@router.get("/guru/{guru_id}", response_model=list[PengampuOut])
def list_pengampu_per_guru(
    guru_id: int,
    tahun_ajaran_id: Optional[int] = Query(None),
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("pengampu.view", "pengampu.kelola")),
):
    """List penugasan untuk 1 guru. Guru cuma bisa lihat punya sendiri."""
    if user.get("role") not in ("admin", "super_admin") and int(user.get("id") or user.get("sub") or 0) != guru_id:
        raise HTTPException(403, "Hanya bisa lihat penugasan sendiri")
    q = select(GuruPengampu).where(GuruPengampu.guru_id == guru_id)
    if tahun_ajaran_id:
        q = q.where(GuruPengampu.tahun_ajaran_id == tahun_ajaran_id)
    q = q.where(GuruPengampu.is_active.is_(True))
    rows = db.execute(q.order_by(GuruPengampu.id)).scalars().all()
    return [_serialize(r, db) for r in rows]


# ── Tambah 1 pengampu ───────────────────────────────────────────
@router.post("", response_model=PengampuOut, status_code=status.HTTP_201_CREATED)
def create_pengampu(
    data: PengampuIn,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("pengampu.kelola")),
):
    """Tambah 1 penugasan mengajar."""
    # Validasi foreign key
    if not db.get(Guru, data.guru_id):
        raise HTTPException(404, "Guru tidak ditemukan")
    if data.mapel_id and not db.get(MataPelajaran, data.mapel_id):
        raise HTTPException(404, "Mata pelajaran tidak ditemukan")
    if not db.get(Kelas, data.kelas_id):
        raise HTTPException(404, "Kelas tidak ditemukan")
    if not db.get(TahunAjaran, data.tahun_ajaran_id):
        raise HTTPException(404, "Tahun ajaran tidak ditemukan")

    p = GuruPengampu(
        guru_id=data.guru_id,
        mapel_id=data.mapel_id,
        kelas_id=data.kelas_id,
        tahun_ajaran_id=data.tahun_ajaran_id,
        is_wali=data.is_wali,
        is_active=True,
    )
    db.add(p)
    try:
        db.commit()
        db.refresh(p)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Penugasan sudah ada (guru, mapel, kelas, TA) kombinasi duplikat")
    log_action(user, "tambah_pengampu",
               f"Pengampu: guru={data.guru_id} mapel={data.mapel_id} kelas={data.kelas_id} TA={data.tahun_ajaran_id}")
    return _serialize(p, db)


# ── Bulk set (replace all pengampu 1 guru di 1 TA) ───────────────
@router.post("/bulk", response_model=list[PengampuOut])
def bulk_set_pengampu(
    data: PengampuBulkIn,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("pengampu.kelola")),
):
    """Set/replace semua pengampu untuk 1 guru di 1 tahun ajaran.

    Items kosong = hapus semua pengampu guru tsb di TA tsb.
    """
    if not db.get(Guru, data.guru_id):
        raise HTTPException(404, "Guru tidak ditemukan")
    if not db.get(TahunAjaran, data.tahun_ajaran_id):
        raise HTTPException(404, "Tahun ajaran tidak ditemukan")

    # Hapus semua pengampu existing guru di TA tsb
    db.query(GuruPengampu).filter_by(
        guru_id=data.guru_id,
        tahun_ajaran_id=data.tahun_ajaran_id,
    ).delete()
    db.flush()

    # Insert items baru
    inserted = []
    for item in data.items:
        p = GuruPengampu(
            guru_id=data.guru_id,
            mapel_id=item.mapel_id,
            kelas_id=item.kelas_id,
            tahun_ajaran_id=data.tahun_ajaran_id,
            is_wali=item.is_wali,
            is_active=True,
        )
        db.add(p)
        inserted.append(p)
    db.commit()
    for p in inserted:
        db.refresh(p)
    log_action(user, "bulk_pengampu",
               f"Pengampu bulk: guru={data.guru_id} TA={data.tahun_ajaran_id} items={len(inserted)}")
    return [_serialize(p, db) for p in inserted]


# ── Hapus 1 pengampu ────────────────────────────────────────────
@router.delete("/{pengampu_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pengampu(
    pengampu_id: int,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("pengampu.kelola")),
):
    """Hapus 1 penugasan mengajar."""
    p = db.get(GuruPengampu, pengampu_id)
    if not p:
        raise HTTPException(404, "Penugasan tidak ditemukan")
    db.delete(p)
    db.commit()
    log_action(user, "hapus_pengampu", f"Pengampu id={pengampu_id} dihapus")
    return None
