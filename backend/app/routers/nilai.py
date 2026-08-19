"""CRUD Penilaian (per tenant) — modul Penilaian.

Jenis nilai: tugas | sumatif | asas | asat.
KKTP per materi. Ekspor RDM pakai NISN (kita tidak punya NIS).
"""
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..audit import log_action
from ..deps import get_tenant_db, require_permission
from ..models import (Guru, Kelas, MateriPenilaian, MataPelajaran, Murid,
                      Nilai, PeriodeAkademik)
from ..schemas import (JENIS_PENILAIAN, MateriPenilaianCreate,
                       MateriPenilaianOut, MateriPenilaianUpdate,
                       NilaiBulkCreate, NilaiOut, NilaiUpdate)

router = APIRouter(prefix="/api/nilai", tags=["nilai"])


def _periode_aktif(db: Session) -> PeriodeAkademik | None:
    return (db.query(PeriodeAkademik)
            .join(Kelas, Kelas.tahun_ajaran_id == PeriodeAkademik.tahun_ajaran_id)
            .filter(Kelas.tahun_ajaran_id.isnot(None))
            .first())


def _materi_out(db: Session, m: MateriPenilaian) -> dict:
    mp = db.get(MataPelajaran, m.mapel_id)
    kls = db.get(Kelas, m.kelas_id) if m.kelas_id else None
    jml = 0
    terisi = 0
    rata = None
    tuntas = 0
    if m.kelas_id:
        jml = (db.query(Murid).filter(Murid.kelas_id == m.kelas_id,
                                      Murid.is_active.is_(True)).count())
        stats = (db.query(func.count(Nilai.id),
                          func.avg(Nilai.skor),
                          func.sum(case((Nilai.skor >= m.kkpt, 1), else_=0)))
                 .filter(Nilai.materi_penilaian_id == m.id).first())
        terisi = stats[0] or 0
        rata = round(stats[1], 1) if stats[1] is not None else None
        tuntas = stats[2] or 0
    return {
        "id": m.id, "mapel_id": m.mapel_id, "kelas_id": m.kelas_id,
        "jenis": m.jenis, "nama": m.nama, "materi": m.materi, "kkpt": m.kkpt,
        "guru_id": m.guru_id, "periode_akademik_id": m.periode_akademik_id,
        "mapel_nama": mp.nama if mp else None,
        "kelas_nama": kls.nama_kelas if kls else None,
        "jumlah_murid": jml, "terisi": terisi, "rata_rata": rata,
        "tuntas": tuntas,
        "created_at": m.created_at,
    }


@router.get("/materi", response_model=list[MateriPenilaianOut])
def list_materi(kelas_id: int | None = None,
                mapel_id: int | None = None,
                jenis: str | None = None,
                db: Session = Depends(get_tenant_db),
                _: dict = Depends(require_permission("penilaian.view", "penilaian.input", "penilaian.export"))):
    q = db.query(MateriPenilaian)
    if kelas_id:
        q = q.filter(MateriPenilaian.kelas_id == kelas_id)
    if mapel_id:
        q = q.filter(MateriPenilaian.mapel_id == mapel_id)
    if jenis:
        q = q.filter(MateriPenilaian.jenis == jenis)
    return [_materi_out(db, m) for m in q.order_by(MateriPenilaian.created_at.desc()).all()]


@router.post("/materi", response_model=MateriPenilaianOut, status_code=status.HTTP_201_CREATED)
def create_materi(data: MateriPenilaianCreate,
                  db: Session = Depends(get_tenant_db),
                  user: dict = Depends(require_permission("penilaian.input"))):
    if not db.get(MataPelajaran, data.mapel_id):
        raise HTTPException(404, "Mata pelajaran tidak ditemukan")
    if data.kelas_id and not db.get(Kelas, data.kelas_id):
        raise HTTPException(404, "Kelas tidak ditemukan")
    if data.jenis not in JENIS_PENILAIAN:
        raise HTTPException(400, f"Jenis harus salah satu: {', '.join(JENIS_PENILAIAN)}")
    if not (0 <= data.kkpt <= 100):
        raise HTTPException(400, "KKTP harus 0-100")
    m = MateriPenilaian(
        mapel_id=data.mapel_id, kelas_id=data.kelas_id, jenis=data.jenis,
        nama=data.nama.strip(), materi=data.materi.strip(), kkpt=data.kkpt,
        guru_id=user["id"], periode_akademik_id=data.periode_akademik_id,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    log_action(user, "tambah_materi_penilaian",
               f"Penilaian '{m.nama}' ({m.jenis}) mapel={data.mapel_id} kelas={data.kelas_id}")
    return _materi_out(db, m)


@router.patch("/materi/{materi_id}", response_model=MateriPenilaianOut)
def update_materi(materi_id: int, data: MateriPenilaianUpdate,
                  db: Session = Depends(get_tenant_db),
                  user: dict = Depends(require_permission("penilaian.input"))):
    m = db.get(MateriPenilaian, materi_id)
    if not m:
        raise HTTPException(404, "Materi penilaian tidak ditemukan")
    if data.nama is not None:
        m.nama = data.nama.strip()
    if data.materi is not None:
        m.materi = data.materi.strip()
    if data.kkpt is not None:
        if not (0 <= data.kkpt <= 100):
            raise HTTPException(400, "KKTP harus 0-100")
        m.kkpt = data.kkpt
    if data.jenis is not None:
        if data.jenis not in JENIS_PENILAIAN:
            raise HTTPException(400, "Jenis tidak valid")
        m.jenis = data.jenis
    db.commit()
    db.refresh(m)
    log_action(user, "ubah_materi_penilaian", f"Materi penilaian id={materi_id} diubah")
    return _materi_out(db, m)


@router.delete("/materi/{materi_id}")
def delete_materi(materi_id: int,
                  db: Session = Depends(get_tenant_db),
                  user: dict = Depends(require_permission("penilaian.input"))):
    m = db.get(MateriPenilaian, materi_id)
    if not m:
        raise HTTPException(404, "Materi penilaian tidak ditemukan")
    db.query(Nilai).filter(Nilai.materi_penilaian_id == materi_id).delete()
    db.delete(m)
    db.commit()
    log_action(user, "hapus_materi_penilaian", f"Materi penilaian id={materi_id} dihapus")
    return {"ok": True}


@router.get("/materi/{materi_id}/siswa")
def siswa_materi(materi_id: int,
                 db: Session = Depends(get_tenant_db),
                 _: dict = Depends(require_permission("penilaian.view", "penilaian.input"))):
    """Daftar murid kelas + nilai existing untuk form input."""
    m = db.get(MateriPenilaian, materi_id)
    if not m:
        raise HTTPException(404, "Materi penilaian tidak ditemukan")
    if not m.kelas_id:
        raise HTTPException(400, "Materi ini tidak terkait kelas")
    murids = (db.query(Murid).filter(Murid.kelas_id == m.kelas_id,
                                     Murid.is_active.is_(True))
              .order_by(Murid.nama).all())
    nilai_map = {n.murid_id: n for n in db.query(Nilai).filter(
        Nilai.materi_penilaian_id == materi_id).all()}
    return {
        "materi": _materi_out(db, m),
        "siswa": [{
            "murid_id": x.id, "nama": x.nama, "nisn": x.nisn,
            "skor": nilai_map[x.id].skor if x.id in nilai_map else None,
            "nilai_id": nilai_map[x.id].id if x.id in nilai_map else None,
        } for x in murids],
    }


@router.post("/bulk")
def input_nilai_bulk(data: NilaiBulkCreate,
                     db: Session = Depends(get_tenant_db),
                     user: dict = Depends(require_permission("penilaian.input"))):
    """Simpan/update nilai banyak murid sekaligus untuk satu materi."""
    m = db.get(MateriPenilaian, data.materi_penilaian_id)
    if not m:
        raise HTTPException(404, "Materi penilaian tidak ditemukan")
    if not m.kelas_id:
        raise HTTPException(400, "Materi ini tidak terkait kelas")
    kelas_murid = {x[0] for x in db.query(Murid.id).filter(
        Murid.kelas_id == m.kelas_id).all()}

    saved = 0
    for e in data.entries:
        mid = e.get("murid_id")
        skor = e.get("skor")
        if mid not in kelas_murid:
            continue  # murid bukan anggota kelas materi ini
        if skor is not None and not (0 <= skor <= 100):
            raise HTTPException(400, f"Nilai murid id={mid} harus 0-100")
        n = db.query(Nilai).filter_by(materi_penilaian_id=m.id,
                                      murid_id=mid).first()
        if n:
            n.skor = skor
            n.catatan = str(e.get("catatan") or "")
        else:
            db.add(Nilai(materi_penilaian_id=m.id, murid_id=mid,
                         skor=skor, catatan=str(e.get("catatan") or "")))
        saved += 1
    db.commit()
    log_action(user, "input_nilai", f"Nilai '{m.nama}' ({m.jenis}): {saved} murid disimpan")
    return {"ok": True, "disimpan": saved}


@router.patch("/{nilai_id}", response_model=NilaiOut)
def update_nilai(nilai_id: int, data: NilaiUpdate,
                 db: Session = Depends(get_tenant_db),
                 user: dict = Depends(require_permission("penilaian.input"))):
    """Update nilai per baris (dipakai koreksi cepat)."""
    n = db.get(Nilai, nilai_id)
    if not n:
        raise HTTPException(404, "Nilai tidak ditemukan")
    if data.skor is not None:
        if not (0 <= data.skor <= 100):
            raise HTTPException(400, "Nilai harus 0-100")
        n.skor = data.skor
    if data.catatan is not None:
        n.catatan = data.catatan
    db.commit()
    db.refresh(n)
    log_action(user, "koreksi_nilai", f"Nilai id={nilai_id} dikoreksi")
    from ..models import Murid as MuridModel
    m = db.get(MuridModel, n.murid_id)
    return {
        "id": n.id, "materi_penilaian_id": n.materi_penilaian_id,
        "murid_id": n.murid_id, "skor": n.skor, "catatan": n.catatan,
        "murid_nama": m.nama if m else None, "murid_nisn": m.nisn if m else None,
    }


@router.get("/rekap")
def rekap_nilai(kelas_id: int = Query(...),
                mapel_id: int | None = None,
                db: Session = Depends(get_tenant_db),
                _: dict = Depends(require_permission("penilaian.view", "penilaian.input", "penilaian.export"))):
    """Rekap nilai per kelas: per murid → semua materi + rata-rata + status KKTP."""
    kls = db.get(Kelas, kelas_id)
    if not kls:
        raise HTTPException(404, "Kelas tidak ditemukan")
    q = db.query(MateriPenilaian).filter(MateriPenilaian.kelas_id == kelas_id)
    if mapel_id:
        q = q.filter(MateriPenilaian.mapel_id == mapel_id)
    materis = q.order_by(MateriPenilaian.jenis, MateriPenilaian.nama).all()
    if not materis:
        return {"kelas_nama": kls.nama_kelas, "materi": [], "murid": []}

    murids = (db.query(Murid).filter(Murid.kelas_id == kelas_id,
                                     Murid.is_active.is_(True))
              .order_by(Murid.nama).all())
    # nilai: (materi_id, murid_id) → skor
    rows = (db.query(Nilai.materi_penilaian_id, Nilai.murid_id, Nilai.skor)
            .filter(Nilai.materi_penilaian_id.in_([m.id for m in materis])).all())
    nilai_map = {(r[0], r[1]): r[2] for r in rows}

    materi_out = [{
        "id": m.id, "nama": m.nama, "jenis": m.jenis, "kkpt": m.kkpt,
        "materi": m.materi,
    } for m in materis]

    murid_out = []
    for x in murids:
        skors = [nilai_map.get((m.id, x.id)) for m in materis]
        terisi = [s for s in skors if s is not None]
        rata = round(sum(terisi) / len(terisi), 1) if terisi else None
        if not terisi:
            status = "Belum Dinilai"
        elif all(s >= m.kkpt for s, m in zip(skors, materis) if s is not None):
            status = "Tuntas"
        else:
            status = "Perlu Perbaikan"
        murid_out.append({
            "murid_id": x.id, "nama": x.nama, "nisn": x.nisn,
            "skor": skors, "rata_rata": rata,
            "status": status,
        })

    return {"kelas_nama": kls.nama_kelas, "materi": materi_out, "murid": murid_out}


@router.get("/export-rdm")
def export_rdm(kelas_id: int = Query(...),
               db: Session = Depends(get_tenant_db),
               _: dict = Depends(require_permission("penilaian.export", "penilaian.view"))):
    """Export rekap nilai format RDM (NISN, nama, nilai per materi)."""
    from fastapi.responses import Response
    import openpyxl

    kls = db.get(Kelas, kelas_id)
    if not kls:
        raise HTTPException(404, "Kelas tidak ditemukan")
    materis = (db.query(MateriPenilaian).filter(MateriPenilaian.kelas_id == kelas_id)
               .order_by(MateriPenilaian.jenis, MateriPenilaian.nama).all())
    murids = (db.query(Murid).filter(Murid.kelas_id == kelas_id,
                                     Murid.is_active.is_(True))
              .order_by(Murid.nama).all())
    rows = (db.query(Nilai.materi_penilaian_id, Nilai.murid_id, Nilai.skor)
            .filter(Nilai.materi_penilaian_id.in_([m.id for m in materis])).all())
    nilai_map = {(r[0], r[1]): r[2] for r in rows}

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rekap Nilai"
    ws.append([f"Rekap Nilai {kls.nama_kelas} — RDM", "", "", ""])
    ws.append([])
    header = ["No", "NISN", "Nama"]
    for m in materis:
        header.append(f"{m.jenis.capitalize()}: {m.nama}")
    header.append("Rata-rata")
    ws.append(header)
    for i, x in enumerate(murids, start=1):
        skors = [nilai_map.get((m.id, x.id)) for m in materis]
        terisi = [s for s in skors if s is not None]
        rata = round(sum(terisi) / len(terisi), 1) if terisi else ""
        ws.append([i, x.nisn or "", x.nama, *["" if s is None else s for s in skors], rata])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"rekap-nilai-{kls.nama_kelas}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
