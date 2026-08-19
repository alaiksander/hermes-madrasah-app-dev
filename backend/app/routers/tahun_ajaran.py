"""Tahun Ajaran (per tenant) — CRUD + set aktif. Mung admin."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..deps import get_tenant_db, require_permission, require_roles
from ..models import Kelas, PeriodeAkademik, TahunAjaran
from ..schemas import (PeriodeAkademikOut, PeriodeAkademikUpsert,
                       TahunAjaranCreate, TahunAjaranOut, TahunAjaranUpdate)

router = APIRouter(prefix="/api/tahun-ajaran", tags=["tahun-ajaran"])


def _to_out(t: TahunAjaran, db: Session) -> TahunAjaranOut:
    jk = db.query(Kelas).filter(Kelas.tahun_ajaran_id == t.id).count()
    return TahunAjaranOut.model_validate(t).model_copy(update={"jumlah_kelas": jk})


def _get(db: Session, ta_id: int) -> TahunAjaran:
    t = db.get(TahunAjaran, ta_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tahun ajaran tidak ditemukan")
    return t


def _validate_period(t: TahunAjaran, data: PeriodeAkademikUpsert,
                     db: Session, current_id: int | None = None) -> None:
    if data.tanggal_mulai > data.tanggal_selesai:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Tanggal selesai harus setelah tanggal mulai")
    if data.tanggal_mulai < t.tanggal_mulai or data.tanggal_selesai > t.tanggal_selesai:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Periode semester harus berada dalam rentang tahun ajaran")
    q = db.query(PeriodeAkademik).filter(
        PeriodeAkademik.tahun_ajaran_id == t.id,
        PeriodeAkademik.kode == data.kode)
    if current_id:
        q = q.filter(PeriodeAkademik.id != current_id)
    if q.first():
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Periode semester tersebut sudah ada")
    others = db.query(PeriodeAkademik).filter(
        PeriodeAkademik.tahun_ajaran_id == t.id,
        PeriodeAkademik.tanggal_mulai <= data.tanggal_selesai,
        PeriodeAkademik.tanggal_selesai >= data.tanggal_mulai)
    if current_id:
        others = others.filter(PeriodeAkademik.id != current_id)
    if others.first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Periode semester tidak boleh tumpang tindih")


@router.get("/{ta_id}/periode", response_model=list[PeriodeAkademikOut])
def list_periode(ta_id: int, db: Session = Depends(get_tenant_db),
                 _: dict = Depends(require_permission("ta.view", "ta.update", "absen.rekap", "absen.cetak"))):
    _get(db, ta_id)
    return db.query(PeriodeAkademik).filter(
        PeriodeAkademik.tahun_ajaran_id == ta_id).order_by(
            PeriodeAkademik.tanggal_mulai).all()


@router.put("/{ta_id}/periode", response_model=PeriodeAkademikOut)
def upsert_periode(ta_id: int, data: PeriodeAkademikUpsert,
                   db: Session = Depends(get_tenant_db),
                   _: dict = Depends(require_permission("ta.view", "ta.update"))):
    t = _get(db, ta_id)
    existing = db.query(PeriodeAkademik).filter_by(
        tahun_ajaran_id=ta_id, kode=data.kode).first()
    _validate_period(t, data, db, existing.id if existing else None)
    if existing:
        existing.nama = data.nama
        existing.tanggal_mulai = data.tanggal_mulai
        existing.tanggal_selesai = data.tanggal_selesai
        item = existing
    else:
        item = PeriodeAkademik(tahun_ajaran_id=ta_id, **data.model_dump())
        db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("", response_model=list[TahunAjaranOut])
def list_tahun(db: Session = Depends(get_tenant_db),
               _: dict = Depends(require_permission("ta.view", "ta.create", "ta.update", "absen.rekap", "absen.cetak", "kelas.view"))):
    """Daftar taun ajaran — permission-aware (guru default dapat via ta.view)."""
    return [_to_out(t, db) for t in db.query(TahunAjaran)
            .order_by(TahunAjaran.tanggal_mulai.desc()).all()]


@router.post("", response_model=TahunAjaranOut, status_code=status.HTTP_201_CREATED)
def create_tahun(data: TahunAjaranCreate,
                 db: Session = Depends(get_tenant_db),
                 _: dict = Depends(require_permission("ta.view", "ta.create", "ta.update"))):
    """Gawe taun anyar — otomatis dadi aktif (is_active liyane dipateni)."""
    if db.query(TahunAjaran).filter_by(nama=data.nama).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Nama tahun ajaran sudah dipakai")
    if data.tanggal_selesai < data.tanggal_mulai:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Tanggal selesai harus setelah tanggal mulai")
    t = TahunAjaran(nama=data.nama, tanggal_mulai=data.tanggal_mulai,
                    tanggal_selesai=data.tanggal_selesai, is_active=True)
    db.query(TahunAjaran).update({TahunAjaran.is_active: False})
    db.add(t)
    db.commit()
    db.refresh(t)
    return _to_out(t, db)


@router.patch("/{ta_id}", response_model=TahunAjaranOut)
def update_tahun(ta_id: int, data: TahunAjaranUpdate,
                 db: Session = Depends(get_tenant_db),
                 _: dict = Depends(require_permission("ta.view", "ta.create", "ta.update"))):
    """Edit nama/tanggal, utawa jadikake aktif (mateni liyane)."""
    t = _get(db, ta_id)
    if data.nama is not None and data.nama != t.nama:
        if db.query(TahunAjaran).filter(TahunAjaran.nama == data.nama,
                                        TahunAjaran.id != ta_id).first():
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Nama tahun ajaran sudah dipakai")
        t.nama = data.nama
    if data.tanggal_mulai is not None:
        t.tanggal_mulai = data.tanggal_mulai
    if data.tanggal_selesai is not None:
        t.tanggal_selesai = data.tanggal_selesai
    if data.is_active:
        db.query(TahunAjaran).update({TahunAjaran.is_active: False})
        t.is_active = True
    db.commit()
    db.refresh(t)
    return _to_out(t, db)


@router.delete("/{ta_id}")
def delete_tahun(ta_id: int,
                 db: Session = Depends(get_tenant_db),
                 _: dict = Depends(require_permission("ta.view", "ta.create", "ta.update"))):
    """Busak taun — mung yen ora nduwe kelas."""
    t = _get(db, ta_id)
    jk = db.query(Kelas).filter(Kelas.tahun_ajaran_id == ta_id).count()
    if jk > 0:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Tahun ajaran masih memiliki {jk} kelas — hapus kelasnya dulu")
    db.delete(t)
    db.commit()
    return {"ok": True}
