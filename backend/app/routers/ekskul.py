"""Router Ekstrakurikuler — modul Ekskul.

Master ekskul + pembina + anggota + kegiatan + presensi (model manual).
Pembina (guru) hanya bisa input presensi ekskul yang dia pegang.
"""
from datetime import date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..audit import log_action
from ..deps import get_tenant_db, require_permission
from ..models import (Ekskul, EkskulAnggota, EkskulKegiatan, EkskulPresensi,
                      Guru, Kelas, Murid)
from ..xlsx_utils import XLSX_MIME, rows_to_xlsx

router = APIRouter(prefix="/api/ekskul", tags=["Ekstrakurikuler"])
WIB = ZoneInfo("Asia/Jakarta")


class EkskulCreate(BaseModel):
    nama: str
    pembina_guru_id: int | None = None
    deskripsi: str | None = None
    kuota: int = 0
    hari: str | None = None
    jam_mulai: str | None = None
    jam_selesai: str | None = None
    is_active: bool = True
    is_wajib: bool = False
    wajib_tingkat: str | None = None  # "7"|"8"|"9"|"semua"


class EkskulUpdate(BaseModel):
    nama: str | None = None
    pembina_guru_id: int | None = None
    deskripsi: str | None = None
    kuota: int | None = None
    hari: str | None = None
    jam_mulai: str | None = None
    jam_selesai: str | None = None
    is_active: bool | None = None
    is_wajib: bool | None = None
    wajib_tingkat: str | None = None


class AnggotaCreate(BaseModel):
    murid_id: int


class KegiatanCreate(BaseModel):
    tanggal: date
    topik: str | None = None
    catatan: str | None = None


class PresensiCreate(BaseModel):
    hadir: list[int] = []  # daftar murid_id yang hadir


def _ekskul_out(e: Ekskul) -> dict:
    return {
        "id": e.id,
        "nama": e.nama,
        "pembina_guru_id": e.pembina_guru_id,
        "pembina_nama": e.pembina.nama if e.pembina else None,
        "deskripsi": e.deskripsi,
        "kuota": e.kuota,
        "hari": e.hari,
        "jam_mulai": e.jam_mulai,
        "jam_selesai": e.jam_selesai,
        "is_active": e.is_active,
        "is_wajib": e.is_wajib,
        "wajib_tingkat": e.wajib_tingkat,
        "jumlah_anggota": len(e.anggota),
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _is_pembina(user: dict, ekskul: Ekskul) -> bool:
    """Cek apakah user (guru) adalah pembina ekskul ini."""
    return user.get("role") == "guru" and user.get("id") == ekskul.pembina_guru_id


@router.get("")
def ekskul_list(
    q: str | None = Query(None),
    db: Session = Depends(get_tenant_db),
    _: dict = Depends(require_permission("ekskul.view")),
):
    query = db.query(Ekskul)
    if q:
        query = query.filter(Ekskul.nama.ilike(f"%{q}%"))
    ekskul = query.order_by(Ekskul.nama).all()
    return [_ekskul_out(e) for e in ekskul]


@router.post("")
def ekskul_create(
    data: EkskulCreate,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("ekskul.kelola")),
):
    e = Ekskul(**data.model_dump())
    db.add(e)
    db.commit()
    db.refresh(e)
    log_action(user, f"ekskul_create {e.nama}")
    return _ekskul_out(e)


@router.get("/export.xlsx", response_class=Response)
def ekskul_export(
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("ekskul.export")),
):
    """Export rekap ekskul + jumlah anggota ke Excel."""
    ekskul = db.query(Ekskul).order_by(Ekskul.nama).all()
    rows = [[e.nama, e.pembina.nama if e.pembina else "",
             e.hari or "", e.jam_mulai or "", len(e.anggota), e.kuota]
            for e in ekskul]
    xlsx = rows_to_xlsx(
        ["Nama", "Pembina", "Hari", "Jam", "Jumlah Anggota", "Kuota"], rows)
    log_action(user, f"ekskul_export ({len(ekskul)} ekskul)")
    return Response(content=xlsx, media_type=XLSX_MIME,
                    headers={"Content-Disposition": 'attachment; filename="ekskul.xlsx"'})


@router.get("/{ekskul_id}")
def ekskul_detail(
    ekskul_id: int,
    db: Session = Depends(get_tenant_db),
    _: dict = Depends(require_permission("ekskul.view")),
):
    e = db.get(Ekskul, ekskul_id)
    if not e:
        raise HTTPException(404, "Ekskul tidak ditemukan")
    return _ekskul_out(e)


@router.patch("/{ekskul_id}")
def ekskul_update(
    ekskul_id: int,
    data: EkskulUpdate,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("ekskul.kelola")),
):
    e = db.get(Ekskul, ekskul_id)
    if not e:
        raise HTTPException(404, "Ekskul tidak ditemukan")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    db.commit()
    db.refresh(e)
    log_action(user, f"ekskul_update {e.nama}")
    return _ekskul_out(e)


@router.delete("/{ekskul_id}")
def ekskul_delete(
    ekskul_id: int,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("ekskul.kelola")),
):
    e = db.get(Ekskul, ekskul_id)
    if not e:
        raise HTTPException(404, "Ekskul tidak ditemukan")
    db.delete(e)
    db.commit()
    log_action(user, f"ekskul_delete {e.nama}")
    return {"ok": True}


# ── Anggota ────────────────────────────────────────────────────────────

@router.get("/{ekskul_id}/anggota")
def anggota_list(
    ekskul_id: int,
    db: Session = Depends(get_tenant_db),
    _: dict = Depends(require_permission("ekskul.view")),
):
    e = db.get(Ekskul, ekskul_id)
    if not e:
        raise HTTPException(404, "Ekskul tidak ditemukan")
    out = []
    for a in e.anggota:
        out.append({
            "id": a.id,
            "murid_id": a.murid_id,
            "nama": a.murid.nama if a.murid else "?",
            "nisn": a.murid.nisn if a.murid else None,
            "kelas_nama": a.murid.kelas.nama_kelas if a.murid and a.murid.kelas else "",
            "tanggal_daftar": a.tanggal_daftar.isoformat() if a.tanggal_daftar else None,
        })
    return out


@router.post("/{ekskul_id}/masukkan-tingkat")
def anggota_bulk_tingkat(
    ekskul_id: int,
    data: dict,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("ekskul.kelola")),
):
    """Masukkan semua murid pada tingkat tertentu (7/8/9/semua) ke ekskul.

    Manual trigger dari halaman detail. Skip murid yang sudah jadi anggota.
    """
    e = db.get(Ekskul, ekskul_id)
    if not e:
        raise HTTPException(404, "Ekskul tidak ditemukan")
    tingkat = data.get("tingkat", "").strip()
    if tingkat not in ("7", "8", "9", "semua"):
        raise HTTPException(400, "Tingkat harus 7/8/9/semua")

    # Ambil semua kelas unik (nama_kelas) -> filter tingkat
    kelas_ids = []
    for k in db.query(Kelas).all():
        nama = k.nama_kelas.strip()
        if tingkat == "semua" or nama.startswith(tingkat):
            kelas_ids.append(k.id)
    if not kelas_ids:
        return {"ok": True, "ditambahkan": 0, "sudah": 0, "kelas": 0}

    murid_ids = [m.id for m in db.query(Murid).filter(Murid.kelas_id.in_(kelas_ids), Murid.is_active.is_(True)).all()]
    existing = {a.murid_id for a in e.anggota}
    baru = [m for m in murid_ids if m not in existing]
    for mid in baru:
        db.add(EkskulAnggota(ekskul_id=ekskul_id, murid_id=mid))
    db.commit()
    log_action(user, f"ekskul_bulk_tingkat {e.nama} tingkat {tingkat} (+{len(baru)})")
    return {"ok": True, "ditambahkan": len(baru), "sudah": len(existing),
            "kelas": len(kelas_ids), "total_murid": len(murid_ids)}


@router.post("/{ekskul_id}/anggota")
def anggota_add(
    ekskul_id: int,
    data: AnggotaCreate,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("ekskul.kelola")),
):
    e = db.get(Ekskul, ekskul_id)
    if not e:
        raise HTTPException(404, "Ekskul tidak ditemukan")
    # cek duplikat
    dup = db.query(EkskulAnggota).filter_by(
        ekskul_id=ekskul_id, murid_id=data.murid_id).first()
    if dup:
        raise HTTPException(400, "Murid sudah terdaftar di ekskul ini")
    a = EkskulAnggota(ekskul_id=ekskul_id, murid_id=data.murid_id)
    db.add(a)
    db.commit()
    log_action(user, f"ekskul_anggota_add {e.nama} murid {data.murid_id}")
    return {"ok": True, "id": a.id}


@router.delete("/{ekskul_id}/anggota/{anggota_id}")
def anggota_remove(
    ekskul_id: int,
    anggota_id: int,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("ekskul.kelola")),
):
    a = db.get(EkskulAnggota, anggota_id)
    if not a or a.ekskul_id != ekskul_id:
        raise HTTPException(404, "Anggota tidak ditemukan")
    db.delete(a)
    db.commit()
    log_action(user, f"ekskul_anggota_remove {anggota_id}")
    return {"ok": True}


# ── Kegiatan ────────────────────────────────────────────────────────────

@router.get("/{ekskul_id}/kegiatan")
def kegiatan_list(
    ekskul_id: int,
    db: Session = Depends(get_tenant_db),
    _: dict = Depends(require_permission("ekskul.view")),
):
    e = db.get(Ekskul, ekskul_id)
    if not e:
        raise HTTPException(404, "Ekskul tidak ditemukan")
    out = []
    for k in e.kegiatan:
        hadir = sum(1 for p in k.presensi if p.hadir)
        out.append({
            "id": k.id,
            "tanggal": k.tanggal.isoformat(),
            "topik": k.topik,
            "catatan": k.catatan,
            "jumlah_hadir": hadir,
            "jumlah_anggota": len(e.anggota),
        })
    return sorted(out, key=lambda x: x["tanggal"], reverse=True)


@router.post("/{ekskul_id}/kegiatan")
def kegiatan_add(
    ekskul_id: int,
    data: KegiatanCreate,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("ekskul.kelola")),
):
    e = db.get(Ekskul, ekskul_id)
    if not e:
        raise HTTPException(404, "Ekskul tidak ditemukan")
    k = EkskulKegiatan(ekskul_id=ekskul_id, tanggal=data.tanggal,
                       topik=data.topik, catatan=data.catatan)
    db.add(k)
    db.commit()
    db.refresh(k)
    log_action(user, f"ekskul_kegiatan_add {e.nama} {data.tanggal}")
    return {"ok": True, "id": k.id}


# ── Presensi (model manual) ─────────────────────────────────────────────

@router.post("/{ekskul_id}/kegiatan/{kegiatan_id}/presensi")
def presensi_input(
    ekskul_id: int,
    kegiatan_id: int,
    data: PresensiCreate,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("ekskul.presensi")),
):
    e = db.get(Ekskul, ekskul_id)
    if not e:
        raise HTTPException(404, "Ekskul tidak ditemukan")
    # Pembina scope: guru hanya bisa input presensi ekskul yang dia pegang
    if user.get("role") == "guru" and not _is_pembina(user, e):
        raise HTTPException(403, "Anda bukan pembina ekskul ini")
    k = db.get(EkskulKegiatan, kegiatan_id)
    if not k or k.ekskul_id != ekskul_id:
        raise HTTPException(404, "Kegiatan tidak ditemukan")
    # hapus presensi lama, isi ulang
    db.query(EkskulPresensi).filter_by(kegiatan_id=kegiatan_id).delete()
    for mid in data.hadir:
        db.add(EkskulPresensi(kegiatan_id=kegiatan_id, murid_id=mid, hadir=True))
    db.commit()
    log_action(user, f"ekskul_presensi {e.nama} kegiatan {kegiatan_id} ({len(data.hadir)} hadir)")
    return {"ok": True, "hadir": len(data.hadir)}
