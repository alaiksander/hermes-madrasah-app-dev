"""CRUD Mata Pelajaran (per tenant) — admin tulis, guru baca untuk jurnal."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit import log_action
from ..deps import get_tenant_db, require_permission
from ..models import MataPelajaran
from ..schemas import (MataPelajaranCreate, MataPelajaranOut,
                       MataPelajaranUpdate)

router = APIRouter(prefix="/api/mapel", tags=["mata_pelajaran"])


def _to_out(m: MataPelajaran) -> MataPelajaranOut:
    return MataPelajaranOut.model_validate(m)


@router.get("", response_model=list[MataPelajaranOut])
def list_mapel(
    aktif_saja: bool = False,
    db: Session = Depends(get_tenant_db),
    _: dict = Depends(require_permission(
        "mapel.view", "jurnal.view", "jurnal.input")),
):
    """Daftar mata pelajaran. `aktif_saja=true` → hanya yang aktif."""
    q = db.query(MataPelajaran)
    if aktif_saja:
        q = q.filter(MataPelajaran.is_active.is_(True))
    return [_to_out(m) for m in q.order_by(MataPelajaran.nama).all()]


@router.post("", response_model=MataPelajaranOut,
             status_code=status.HTTP_201_CREATED)
def create_mapel(
    data: MataPelajaranCreate,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("mapel.create")),
):
    """Tambah mata pelajaran baru."""
    nama = data.nama.strip()
    if not nama:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nama mapel wajib diisi")
    if db.query(MataPelajaran).filter(
            MataPelajaran.nama == nama).first():
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Mata pelajaran '{nama}' sudah ada")
    m = MataPelajaran(
        nama=nama,
        kode=data.kode.strip(),
        kelompok=data.kelompok.strip() or "umum",
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    log_action(user, "tambah_mapel", f"Mata pelajaran '{m.nama}' ditambah")
    return _to_out(m)


@router.patch("/{mapel_id}", response_model=MataPelajaranOut)
def update_mapel(
    mapel_id: int,
    data: MataPelajaranUpdate,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("mapel.update")),
):
    """Edit mata pelajaran."""
    m = db.get(MataPelajaran, mapel_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mata pelajaran tidak ditemukan")
    changes = []
    if data.nama is not None and data.nama.strip() != m.nama:
        nama = data.nama.strip()
        if db.query(MataPelajaran).filter(
                MataPelajaran.nama == nama,
                MataPelajaran.id != mapel_id).first():
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Mata pelajaran '{nama}' sudah ada")
        changes.append(f"nama '{m.nama}' → '{nama}'")
        m.nama = nama
    if data.kode is not None:
        m.kode = data.kode.strip()
    if data.kelompok is not None:
        m.kelompok = data.kelompok.strip() or "umum"
    if data.is_active is not None:
        m.is_active = data.is_active
    db.commit()
    db.refresh(m)
    if changes:
        log_action(user, "ubah_mapel",
                   f"Mapel id={mapel_id} ({m.nama}): {', '.join(changes)}")
    return _to_out(m)


@router.delete("/{mapel_id}")
def delete_mapel(
    mapel_id: int,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("mapel.delete")),
):
    """Hapus mata pelajaran."""
    m = db.get(MataPelajaran, mapel_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mata pelajaran tidak ditemukan")
    nama = m.nama
    db.delete(m)
    db.commit()
    log_action(user, "hapus_mapel", f"Mata pelajaran '{nama}' (id={mapel_id}) dihapus")
    return {"ok": True}
