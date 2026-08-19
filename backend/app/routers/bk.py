"""Bimbingan Konseling (BK) — CRUD API.

Permission: bk.view, bk.catatan, bk.sesi, bk.export, bk.monitor.
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..deps import get_tenant_db, require_permission
from ..models import (BkCatatan, BkKategori, BkKonfigurasi, BkPelanggaran,
                      BkPeserta, BkSesi, Guru, Kelas, Murid, TahunAjaran)

router = APIRouter(prefix="/api/bk", tags=["bk"])


# ── Schemas ───────────────────────────────────────────────────────────────

class KategoriIn(BaseModel):
    nama: str
    jenis: str = "netral"     # 'positif' / 'negatif' / 'netral'
    warna: str = "zinc"
    poin: Optional[int] = None
    urutan: int = 0


class KategoriUpdate(BaseModel):
    nama: Optional[str] = None
    jenis: Optional[str] = None
    warna: Optional[str] = None
    poin: Optional[int] = None
    urutan: Optional[int] = None


class PelanggaranIn(BaseModel):
    nama: str
    poin: int = 0
    tingkat: Optional[str] = None
    urutan: int = 0


class CatatanIn(BaseModel):
    """Multi-murid: catatan 1 untuk N murid (mis. kelas ramai)."""
    murid_ids: list[int]
    kategori_id: int
    pelanggaran_id: Optional[int] = None
    judul: str
    isi: str = ""
    tanggal: Optional[date] = None
    tingkat: Optional[str] = None


class CatatanUpdate(BaseModel):
    judul: Optional[str] = None
    isi: Optional[str] = None
    tanggal: Optional[date] = None
    tingkat: Optional[str] = None
    # kategori_id & pelanggaran_id biasanya tidak diubah (auditing)
    # tapi boleh via field berikut:
    pelanggaran_id: Optional[int] = None


class SesiIn(BaseModel):
    """Sesi konseling multi-murid atau single."""
    peserta_ids: list[int] = []
    tanggal: Optional[date] = None
    tempat: str = "Ruang BK"
    topik: str
    hasil: str = ""
    tindak_lanjut: str = ""
    berikutnya_tanggal: Optional[date] = None


class KonfigurasiUpdate(BaseModel):
    threshold_sp1: Optional[int] = None
    threshold_sp2: Optional[int] = None
    threshold_sp3: Optional[int] = None
    periode_reset: Optional[str] = None  # 'semester' / 'tahun_ajaran'
    catatan: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────

def _kategori_to_dict(k: BkKategori) -> dict:
    return {
        "id": k.id, "nama": k.nama, "jenis": k.jenis,
        "warna": k.warna, "poin": k.poin, "urutan": k.urutan,
        "is_system": bool(k.is_system),
    }


def _pelanggaran_to_dict(p: BkPelanggaran) -> dict:
    return {
        "id": p.id, "kategori_id": p.kategori_id, "nama": p.nama,
        "poin": p.poin, "tingkat": p.tingkat, "urutan": p.urutan,
        "is_system": bool(p.is_system),
    }


def _catatan_to_dict(c: BkCatatan, db: Session) -> dict:
    g = db.get(Guru, c.dibuat_oleh)
    k = db.get(BkKategori, c.kategori_id)
    p = db.get(BkPelanggaran, c.pelanggaran_id) if c.pelanggaran_id else None
    # Peserta (multi-murid)
    peserta_ids = [ps.murid_id for ps in c.peserta] if c.peserta else []
    if not peserta_ids and hasattr(c, 'murid_id') and c.murid_id:
        # Backward-compat: catatan lama masih ada murid_id
        peserta_ids = [c.murid_id]
    peserta = []
    if peserta_ids:
        for mid in peserta_ids:
            m = db.get(Murid, mid)
            if m:
                kls = db.get(Kelas, m.kelas_id)
                peserta.append({
                    "id": m.id, "nisn": m.nisn, "nama": m.nama,
                    "kelas_nama": kls.nama_kelas if kls else "-",
                })
    return {
        "id": c.id,
        "murid_id": peserta_ids[0] if peserta_ids else None,
        "murid_nama": peserta[0]["nama"] if peserta else "-",
        "murid_nisn": peserta[0]["nisn"] if peserta else "-",
        "kelas_nama": peserta[0]["kelas_nama"] if peserta else "-",
        "murid_ids": peserta_ids,
        "peserta": peserta,
        "kategori_id": c.kategori_id,
        "kategori_nama": k.nama if k else "-",
        "kategori_jenis": k.jenis if k else "netral",
        "kategori_warna": k.warna if k else "zinc",
        "pelanggaran_id": c.pelanggaran_id,
        "pelanggaran_nama": p.nama if p else None,
        "judul": c.judul,
        "isi": c.isi,
        "tanggal": c.tanggal.isoformat(),
        "tingkat": c.tingkat,
        "poin_snapshot": c.poin_snapshot,
        "dibuat_oleh": c.dibuat_oleh,
        "dibuat_oleh_nama": g.nama if g else "-",
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _sesi_to_dict(s: BkSesi, db: Session) -> dict:
    g = db.get(Guru, s.guru_id)
    # Peserta (multi-murid)
    peserta_ids = [ps.murid_id for ps in s.peserta] if s.peserta else []
    if not peserta_ids and getattr(s, "murid_id", None):
        peserta_ids = [s.murid_id]
    peserta = []
    if peserta_ids:
        for mid in peserta_ids:
            m = db.get(Murid, mid)
            if m:
                kls = db.get(Kelas, m.kelas_id)
                peserta.append({
                    "id": m.id, "nisn": m.nisn, "nama": m.nama,
                    "kelas_nama": kls.nama_kelas if kls else "-",
                })
    return {
        "id": s.id,
        "murid_id": peserta_ids[0] if peserta_ids else None,
        "murid_nama": peserta[0]["nama"] if peserta else None,
        "murid_ids": peserta_ids,
        "peserta": peserta,
        "tanggal": s.tanggal.isoformat(),
        "tempat": s.tempat,
        "topik": s.topik,
        "hasil": s.hasil,
        "tindak_lanjut": s.tindak_lanjut,
        "berikutnya_tanggal": s.berikutnya_tanggal.isoformat() if s.berikutnya_tanggal else None,
        "guru_id": s.guru_id,
        "guru_nama": g.nama if g else "-",
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


# ── Kategori ─────────────────────────────────────────────────────────────

@router.get("/kategori")
def list_kategori(db: Session = Depends(get_tenant_db),
                  user: dict = Depends(require_permission("bk.view"))):
    rows = db.query(BkKategori).order_by(BkKategori.urutan, BkKategori.id).all()
    return [_kategori_to_dict(k) for k in rows]


@router.post("/kategori", status_code=status.HTTP_201_CREATED)
def create_kategori(data: KategoriIn,
                    db: Session = Depends(get_tenant_db),
                    user: dict = Depends(require_permission("bk.master"))):
    if data.jenis not in ("positif", "negatif", "netral"):
        raise HTTPException(400, "jenis harus positif/negatif/netral")
    if db.query(BkKategori).filter_by(nama=data.nama).first():
        raise HTTPException(400, f"Nama kategori '{data.nama}' sudah ada")
    k = BkKategori(nama=data.nama, jenis=data.jenis, warna=data.warna,
                   poin=data.poin, urutan=data.urutan, is_system=False)
    db.add(k)
    db.commit()
    db.refresh(k)
    return _kategori_to_dict(k)


@router.patch("/kategori/{kat_id}")
def update_kategori(kat_id: int, data: KategoriUpdate,
                    db: Session = Depends(get_tenant_db),
                    user: dict = Depends(require_permission("bk.master"))):
    k = db.get(BkKategori, kat_id)
    if not k:
        raise HTTPException(404, "Kategori tidak ditemukan")
    for field in ("nama", "jenis", "warna", "poin", "urutan"):
        v = getattr(data, field)
        if v is not None:
            setattr(k, field, v)
    db.commit()
    return _kategori_to_dict(k)


@router.delete("/kategori/{kat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_kategori(kat_id: int,
                    db: Session = Depends(get_tenant_db),
                    user: dict = Depends(require_permission("bk.master"))):
    k = db.get(BkKategori, kat_id)
    if not k:
        raise HTTPException(404, "Kategori tidak ditemukan")
    # Tidak bisa hapus kalau ada pelanggaran/catatan
    pakai_p = db.query(BkPelanggaran).filter_by(kategori_id=kat_id).count()
    pakai_c = db.query(BkCatatan).filter_by(kategori_id=kat_id).count()
    if pakai_p or pakai_c:
        raise HTTPException(400,
            f"Kategori dipakai {pakai_p} pelanggaran + {pakai_c} catatan. "
            "Hapus item terkait dulu.")
    db.delete(k)
    db.commit()
    return None


# ── Pelanggaran (master item) ────────────────────────────────────────────

@router.get("/pelanggaran")
def list_pelanggaran(kategori_id: Optional[int] = None,
                     db: Session = Depends(get_tenant_db),
                     user: dict = Depends(require_permission("bk.view"))):
    q = db.query(BkPelanggaran)
    if kategori_id:
        q = q.filter_by(kategori_id=kategori_id)
    rows = q.order_by(BkPelanggaran.kategori_id, BkPelanggaran.urutan, BkPelanggaran.id).all()
    return [_pelanggaran_to_dict(p) for p in rows]


@router.post("/pelanggaran", status_code=status.HTTP_201_CREATED)
def create_pelanggaran(data: PelanggaranIn, kategori_id: int = Query(...),
                       db: Session = Depends(get_tenant_db),
                       user: dict = Depends(require_permission("bk.master"))):
    if not db.get(BkKategori, kategori_id):
        raise HTTPException(404, "Kategori tidak ditemukan")
    p = BkPelanggaran(kategori_id=kategori_id, nama=data.nama,
                      poin=data.poin, tingkat=data.tingkat,
                      urutan=data.urutan, is_system=False)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _pelanggaran_to_dict(p)


@router.patch("/pelanggaran/{pel_id}")
def update_pelanggaran(pel_id: int, data: PelanggaranIn,
                       db: Session = Depends(get_tenant_db),
                       user: dict = Depends(require_permission("bk.master"))):
    p = db.get(BkPelanggaran, pel_id)
    if not p:
        raise HTTPException(404, "Pelanggaran tidak ditemukan")
    # Historis: perubahan poin tidak affect catatan lama (poin_snapshot)
    for field in ("nama", "poin", "tingkat", "urutan"):
        v = getattr(data, field)
        if v is not None:
            setattr(p, field, v)
    db.commit()
    return _pelanggaran_to_dict(p)


@router.delete("/pelanggaran/{pel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pelanggaran(pel_id: int,
                       db: Session = Depends(get_tenant_db),
                       user: dict = Depends(require_permission("bk.master"))):
    p = db.get(BkPelanggaran, pel_id)
    if not p:
        raise HTTPException(404, "Pelanggaran tidak ditemukan")
    pakai = db.query(BkCatatan).filter_by(pelanggaran_id=pel_id).count()
    if pakai:
        raise HTTPException(400, f"Dipakai {pakai} catatan. Hapus catatan terkait dulu.")
    db.delete(p)
    db.commit()
    return None


# ── Catatan (per kejadian) ───────────────────────────────────────────────

@router.get("/catatan")
def list_catatan(
    murid_id: Optional[int] = None,
    kategori_id: Optional[int] = None,
    dari: Optional[date] = None,
    sampai: Optional[date] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("bk.view")),
):
    q = db.query(BkCatatan)
    if murid_id:
        q = q.filter(BkCatatan.murid_id == murid_id)
    if kategori_id:
        q = q.filter(BkCatatan.kategori_id == kategori_id)
    if dari:
        q = q.filter(BkCatatan.tanggal >= dari)
    if sampai:
        q = q.filter(BkCatatan.tanggal <= sampai)
    q = q.order_by(desc(BkCatatan.tanggal), desc(BkCatatan.id))
    rows = q.limit(limit).all()
    return [_catatan_to_dict(r, db) for r in rows]


@router.post("/catatan", status_code=status.HTTP_201_CREATED)
def create_catatan(data: CatatanIn,
                   db: Session = Depends(get_tenant_db),
                   user: dict = Depends(require_permission("bk.catatan"))):
    """Buat catatan untuk 1+ murid. 1 catatan = 1 kejadian = N murid (mis. kelas ramai)."""
    if not data.murid_ids:
        raise HTTPException(400, "Pilih minimal 1 murid")
    k = db.get(BkKategori, data.kategori_id)
    if not k:
        raise HTTPException(404, "Kategori tidak ditemukan")
    poin = 0
    if data.pelanggaran_id:
        p = db.get(BkPelanggaran, data.pelanggaran_id)
        if not p:
            raise HTTPException(404, "Pelanggaran tidak ditemukan")
        if p.kategori_id != data.kategori_id:
            raise HTTPException(400, "Pelanggaran tidak sesuai kategori")
        poin = p.poin
    tgl = data.tanggal or datetime.now().date()
    # Validasi semua murid exist
    valid_ids = []
    for mid in data.murid_ids:
        m = db.get(Murid, mid)
        if m and m.is_active:
            valid_ids.append(mid)
    if not valid_ids:
        raise HTTPException(400, "Tidak ada murid valid")
    # 1 catatan + N peserta (via BkPeserta)
    c = BkCatatan(
        kategori_id=data.kategori_id,
        pelanggaran_id=data.pelanggaran_id, judul=data.judul,
        isi=data.isi, tanggal=tgl, tingkat=data.tingkat,
        poin_snapshot=poin, dibuat_oleh=user["id"],
    )
    db.add(c)
    db.flush()
    for mid in valid_ids:
        db.add(BkPeserta(entitas="catatan", entitas_id=c.id, murid_id=mid))
    db.commit()
    db.refresh(c)
    return _catatan_to_dict(c, db)


@router.patch("/catatan/{id}")
def update_catatan(id: int, data: CatatanUpdate,
                   db: Session = Depends(get_tenant_db),
                   user: dict = Depends(require_permission("bk.catatan"))):
    c = db.get(BkCatatan, id)
    if not c:
        raise HTTPException(404, "Catatan tidak ditemukan")
    if data.pelanggaran_id is not None:
        p = db.get(BkPelanggaran, data.pelanggaran_id)
        if not p:
            raise HTTPException(404, "Pelanggaran tidak ditemukan")
        if p.kategori_id != c.kategori_id:
            raise HTTPException(400, "Pelanggaran tidak sesuai kategori")
        c.pelanggaran_id = data.pelanggaran_id
        c.poin_snapshot = p.poin
    for field in ("judul", "isi", "tanggal", "tingkat"):
        v = getattr(data, field)
        if v is not None:
            setattr(c, field, v)
    # Update peserta jika murid_ids diberikan
    if data.murid_ids is not None:
        if not data.murid_ids:
            raise HTTPException(400, "Pilih minimal 1 murid")
        valid_ids = [mid for mid in data.murid_ids
                     if db.get(Murid, mid) and db.get(Murid, mid).is_active]
        if not valid_ids:
            raise HTTPException(400, "Tidak ada murid valid")
        db.query(BkPeserta).filter_by(entitas="catatan", entitas_id=c.id).delete()
        for mid in valid_ids:
            db.add(BkPeserta(entitas="catatan", entitas_id=c.id, murid_id=mid))
    db.commit()
    return _catatan_to_dict(c, db)


@router.delete("/catatan/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_catatan(id: int,
                   db: Session = Depends(get_tenant_db),
                   user: dict = Depends(require_permission("bk.catatan"))):
    c = db.get(BkCatatan, id)
    if not c:
        raise HTTPException(404, "Catatan tidak ditemukan")
    # Hapus peserta terkait
    db.query(BkPeserta).filter_by(entitas="catatan", entitas_id=c.id).delete()
    db.delete(c)
    db.commit()
    return None


# ── Sesi konseling ───────────────────────────────────────────────────────

@router.get("/sesi")
def list_sesi(murid_id: Optional[int] = None,
             dari: Optional[date] = None,
             sampai: Optional[date] = None,
             db: Session = Depends(get_tenant_db),
             user: dict = Depends(require_permission("bk.sesi"))):
    q = db.query(BkSesi)
    if murid_id:
        q = q.filter(BkSesi.murid_id == murid_id)
    if dari:
        q = q.filter(BkSesi.tanggal >= dari)
    if sampai:
        q = q.filter(BkSesi.tanggal <= sampai)
    q = q.order_by(desc(BkSesi.tanggal), desc(BkSesi.id))
    return [_sesi_to_dict(s, db) for s in q.all()]


@router.post("/sesi", status_code=status.HTTP_201_CREATED)
def create_sesi(data: SesiIn,
                db: Session = Depends(get_tenant_db),
                user: dict = Depends(require_permission("bk.sesi"))):
    """Sesi konseling 1+ murid (multi-murid via BkPeserta)."""
    valid_ids = []
    for mid in data.peserta_ids or []:
        m = db.get(Murid, mid)
        if m and m.is_active:
            valid_ids.append(mid)
    tgl = data.tanggal or datetime.now().date()
    s = BkSesi(
        tanggal=tgl, tempat=data.tempat,
        topik=data.topik, hasil=data.hasil,
        tindak_lanjut=data.tindak_lanjut,
        berikutnya_tanggal=data.berikutnya_tanggal,
        guru_id=user["id"],
    )
    db.add(s)
    db.flush()
    for mid in valid_ids:
        db.add(BkPeserta(entitas="sesi", entitas_id=s.id, murid_id=mid))
    db.commit()
    db.refresh(s)
    return _sesi_to_dict(s, db)


@router.patch("/sesi/{id}")
def update_sesi(id: int, data: SesiIn,
               db: Session = Depends(get_tenant_db),
               user: dict = Depends(require_permission("bk.sesi"))):
    s = db.get(BkSesi, id)
    if not s:
        raise HTTPException(404, "Sesi tidak ditemukan")
    for field in ("tanggal", "tempat", "topik", "hasil",
                  "tindak_lanjut", "berikutnya_tanggal"):
        v = getattr(data, field)
        if v is not None:
            setattr(s, field, v)
    if data.peserta_ids is not None:
        valid_ids = [mid for mid in data.peserta_ids
                     if db.get(Murid, mid) and db.get(Murid, mid).is_active]
        db.query(BkPeserta).filter_by(entitas="sesi", entitas_id=s.id).delete()
        for mid in valid_ids:
            db.add(BkPeserta(entitas="sesi", entitas_id=s.id, murid_id=mid))
    db.commit()
    return _sesi_to_dict(s, db)


@router.delete("/sesi/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sesi(id: int,
                db: Session = Depends(get_tenant_db),
                user: dict = Depends(require_permission("bk.sesi"))):
    s = db.get(BkSesi, id)
    if not s:
        raise HTTPException(404, "Sesi tidak ditemukan")
    db.query(BkPeserta).filter_by(entitas="sesi", entitas_id=s.id).delete()
    db.delete(s)
    db.commit()
    return None


# ── Monitor per murid (profil BK) ────────────────────────────────────────

@router.get("/monitor/{murid_id}")
def monitor_murid(murid_id: int,
                  dari: Optional[date] = None,
                  sampai: Optional[date] = None,
                  db: Session = Depends(get_tenant_db),
                  user: dict = Depends(require_permission("bk.monitor"))):
    """Profil BK lengkap per murid: total poin, status SP, ringkasan."""
    m = db.get(Murid, murid_id)
    if not m:
        raise HTTPException(404, "Murid tidak ditemukan")
    kelas = db.get(Kelas, m.kelas_id) if m else None

    # Filter tanggal — via BkPeserta (multi-murid)
    catatan_ids_sub = db.query(BkPeserta.entitas_id).filter(
        BkPeserta.entitas == "catatan", BkPeserta.murid_id == murid_id)
    cq = db.query(BkCatatan).filter(BkCatatan.id.in_(catatan_ids_sub))
    sesi_ids_sub = db.query(BkPeserta.entitas_id).filter(
        BkPeserta.entitas == "sesi", BkPeserta.murid_id == murid_id)
    sq = db.query(BkSesi).filter(BkSesi.id.in_(sesi_ids_sub))
    if dari:
        cq = cq.filter(BkCatatan.tanggal >= dari)
        sq = sq.filter(BkSesi.tanggal >= dari)
    if sampai:
        cq = cq.filter(BkCatatan.tanggal <= sampai)
        sq = sq.filter(BkSesi.tanggal <= sampai)

    catatan = cq.order_by(desc(BkCatatan.tanggal)).all()
    sesi = sq.order_by(desc(BkSesi.tanggal)).all()

    # Total poin pelanggaran (kategori jenis == 'negatif')
    total_poin = sum(
        c.poin_snapshot for c in catatan
        if (k := db.get(BkKategori, c.kategori_id)) and k.jenis == "negatif"
    )
    # Poin positif (terpisah)
    total_poin_positif = sum(
        c.poin_snapshot for c in catatan
        if (k := db.get(BkKategori, c.kategori_id)) and k.jenis == "positif"
    )

    # Status SP
    konfig = db.get(BkKonfigurasi, 1) or BkKonfigurasi(id=1)
    if total_poin >= konfig.threshold_sp3:
        status_sp = "SP 3 / Panggilan Ortu"
    elif total_poin >= konfig.threshold_sp2:
        status_sp = "SP 2"
    elif total_poin >= konfig.threshold_sp1:
        status_sp = "SP 1"
    elif total_poin > 0:
        status_sp = "Peringatan Lisan"
    else:
        status_sp = "Aman"

    return {
        "murid": {"id": m.id, "nisn": m.nisn, "nama": m.nama,
                   "kelas_nama": kelas.nama_kelas if kelas else "-"},
        "periode": {"dari": dari.isoformat() if dari else None,
                    "sampai": sampai.isoformat() if sampai else None},
        "rekap": {
            "total_catatan": len(catatan),
            "total_sesi": len(sesi),
            "total_poin_pelanggaran": total_poin,
            "total_poin_prestasi": total_poin_positif,
            "status_sp": status_sp,
            "threshold": {
                "sp1": konfig.threshold_sp1,
                "sp2": konfig.threshold_sp2,
                "sp3": konfig.threshold_sp3,
            },
        },
        "catatan": [_catatan_to_dict(c, db) for c in catatan[:50]],
        "sesi": [_sesi_to_dict(s, db) for s in sesi[:50]],
    }


# ── Rekap poin (per kelas / seluruh madrasah) ───────────────────────────

@router.get("/rekap-poin")
def rekap_poin(kelas_id: Optional[int] = None,
               dari: Optional[date] = None,
               sampai: Optional[date] = None,
               limit: int = Query(100, ge=1, le=500),
               db: Session = Depends(get_tenant_db),
               user: dict = Depends(require_permission("bk.view"))):
    """Rekap total poin pelanggaran per murid (untuk ranking)."""
    # Subquery: total poin per murid (kategori negatif)
    from sqlalchemy import func
    q = (db.query(
            Murid.id, Murid.nama, Murid.nisn, Kelas.nama_kelas,
            func.coalesce(func.sum(BkCatatan.poin_snapshot), 0).label("total_poin")
        )
        .select_from(Murid)
        # Multi-murid: join via BkPeserta
        .outerjoin(BkPeserta, (BkPeserta.entitas == "catatan") &
                                (BkPeserta.murid_id == Murid.id))
        .outerjoin(BkCatatan, (BkCatatan.id == BkPeserta.entitas_id) &
                                 (BkCatatan.tanggal >= dari if dari else True) &
                                 (BkCatatan.tanggal <= sampai if sampai else True))
        .outerjoin(BkKategori, BkKategori.id == BkCatatan.kategori_id)
        .join(Kelas, Kelas.id == Murid.kelas_id)
        .filter(Murid.is_active.is_(True))
        .filter((BkKategori.jenis == "negatif") | (BkKategori.id.is_(None)))
        .group_by(Murid.id)
        .order_by(desc("total_poin"))
    )
    if kelas_id:
        q = q.filter(Murid.kelas_id == kelas_id)
    rows = q.limit(limit).all()

    konfig = db.get(BkKonfigurasi, 1) or BkKonfigurasi(id=1)
    out = []
    for r in rows:
        total = int(r.total_poin or 0)
        if total >= konfig.threshold_sp3:
            status = "SP 3"
        elif total >= konfig.threshold_sp2:
            status = "SP 2"
        elif total >= konfig.threshold_sp1:
            status = "SP 1"
        elif total > 0:
            status = "Peringatan"
        else:
            status = "Aman"
        out.append({
            "murid_id": r.id,
            "nama": r.nama,
            "nisn": r.nisn,
            "kelas_nama": r.nama_kelas,
            "total_poin": total,
            "status_sp": status,
        })
    return out


# ── Konfigurasi ──────────────────────────────────────────────────────────

@router.get("/konfigurasi")
def get_konfigurasi(db: Session = Depends(get_tenant_db),
                    user: dict = Depends(require_permission("bk.view"))):
    k = db.get(BkKonfigurasi, 1)
    if not k:
        k = BkKonfigurasi(id=1)
        db.add(k)
        db.commit()
        db.refresh(k)
    return {
        "threshold_sp1": k.threshold_sp1,
        "threshold_sp2": k.threshold_sp2,
        "threshold_sp3": k.threshold_sp3,
        "periode_reset": k.periode_reset,
        "catatan": k.catatan,
    }


@router.put("/konfigurasi")
def put_konfigurasi(data: KonfigurasiUpdate,
                    db: Session = Depends(get_tenant_db),
                    user: dict = Depends(require_permission("bk.master"))):
    k = db.get(BkKonfigurasi, 1)
    if not k:
        k = BkKonfigurasi(id=1)
        db.add(k)
    for field in ("threshold_sp1", "threshold_sp2", "threshold_sp3",
                  "periode_reset", "catatan"):
        v = getattr(data, field)
        if v is not None:
            setattr(k, field, v)
    db.commit()
    db.refresh(k)
    return {
        "threshold_sp1": k.threshold_sp1,
        "threshold_sp2": k.threshold_sp2,
        "threshold_sp3": k.threshold_sp3,
        "periode_reset": k.periode_reset,
        "catatan": k.catatan,
    }


# ── Dashboard BK (ringkasan) ────────────────────────────────────────────

@router.get("/dashboard")
def dashboard_bk(dari: Optional[date] = None,
                 sampai: Optional[date] = None,
                 db: Session = Depends(get_tenant_db),
                 user: dict = Depends(require_permission("bk.view"))):
    """Ringkasan BK: total catatan bulan ini, top 5 murid pelanggaran, dll."""
    from sqlalchemy import func
    if not dari:
        today = datetime.now().date()
        dari = today.replace(day=1)
    if not sampai:
        sampai = datetime.now().date()

    # Total catatan bulan ini
    catatan_q = db.query(BkCatatan).filter(
        BkCatatan.tanggal >= dari, BkCatatan.tanggal <= sampai)
    total_catatan = catatan_q.count()
    # Total pelanggaran (kategori jenis == 'negatif')
    total_pelanggaran = (catatan_q
        .join(BkKategori, BkKategori.id == BkCatatan.kategori_id)
        .filter(BkKategori.jenis == "negatif").count())
    # Total sesi bulan ini
    total_sesi = db.query(BkSesi).filter(
        BkSesi.tanggal >= dari, BkSesi.tanggal <= sampai).count()

    # Top 5 murid pelanggaran (sum poin)
    top5 = (db.query(
        Murid.id, Murid.nama, Murid.nisn, Kelas.nama_kelas,
        func.coalesce(func.sum(BkCatatan.poin_snapshot), 0).label("total")
    )
    .join(BkPeserta, (BkPeserta.entitas == "catatan") & (BkPeserta.murid_id == Murid.id))
    .join(BkCatatan, BkCatatan.id == BkPeserta.entitas_id)
    .join(BkKategori, BkKategori.id == BkCatatan.kategori_id)
    .join(Kelas, Kelas.id == Murid.kelas_id)
    .filter(BkCatatan.tanggal >= dari, BkCatatan.tanggal <= sampai,
            BkKategori.jenis == "negatif")
    .group_by(Murid.id)
    .order_by(desc("total"))
    .limit(5).all())

    konfig = db.get(BkKonfigurasi, 1) or BkKonfigurasi(id=1)

    return {
        "periode": {"dari": dari.isoformat(), "sampai": sampai.isoformat()},
        "ringkasan": {
            "total_catatan": total_catatan,
            "total_pelanggaran": total_pelanggaran,
            "total_sesi": total_sesi,
        },
        "top_pelanggaran": [
            {"murid_id": r.id, "nama": r.nama, "nisn": r.nisn,
             "kelas_nama": r.nama_kelas, "total_poin": int(r.total or 0)}
            for r in top5
        ],
        "threshold": {
            "sp1": konfig.threshold_sp1,
            "sp2": konfig.threshold_sp2,
            "sp3": konfig.threshold_sp3,
        },
    }
