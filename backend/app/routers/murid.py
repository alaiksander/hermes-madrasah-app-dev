"""CRUD Murid (per tenant) — tulis: admin; baca: guru/admin + export/import Excel"""
import csv
import io
import re
import uuid
from datetime import date, datetime

import openpyxl
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..deps import get_tenant_db, require_permission, require_roles
from ..models import Kelas, Murid, TahunAjaran
from ..schemas import MuridCreate, MuridList, MuridOut, MuridUpdate
from ..xlsx_utils import XLSX_MIME, rows_to_xlsx, xlsx_to_rows

router = APIRouter(prefix="/api/murid", tags=["murid"])


def _to_out(m: Murid, db: Session) -> MuridOut:
    kn = None
    if m.kelas_id:
        k = db.get(Kelas, m.kelas_id)
        kn = k.nama_kelas if k else None
    return MuridOut.model_validate(m).model_copy(update={"kelas_nama": kn})


@router.get("", response_model=MuridList)
def list_murid(q: str | None = None,
               kelas_id: int | None = None,
               semua: bool = False,
               page: int = Query(1, ge=1),
               per_page: int = Query(50, ge=1, le=200),
               db: Session = Depends(get_tenant_db),
               _: dict = Depends(require_permission("murid.view", "murid.create", "murid.update", "murid.delete", "murid.import", "murid.qr", "absen.scan", "absen.manual", "absen.rekap"))):
    query = db.query(Murid)
    if not semua:
        query = query.filter(Murid.is_active.is_(True))
    if kelas_id:
        query = query.filter(Murid.kelas_id == kelas_id)
    if q:
        like = f"%{q}%"
        # ilike (case-insensitive) — konsisten SQLite & PostgreSQL
        query = query.filter((Murid.nama.ilike(like)) | (Murid.nisn.ilike(like)))
    total = query.count()
    rows = query.order_by(Murid.nama).offset((page - 1) * per_page).limit(per_page).all()
    return MuridList(total=total, items=[_to_out(m, db) for m in rows])


@router.get("/export.csv", response_class=Response)
def export_murid(db: Session = Depends(get_tenant_db),
                 _: dict = Depends(require_permission("murid.view", "murid.create", "murid.update", "murid.delete", "murid.import", "murid.qr"))):
    """Export SEMUA murid aktif dadi CSV (BOM — kebukak bener ing Excel)."""
    rows = (db.query(Murid).filter(Murid.is_active.is_(True))
            .order_by(Murid.nisn).all())
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM supaya Excel maca UTF-8
    w = csv.writer(buf)
    w.writerow(["NISN", "Nama", "Kelas", "Nama Ortu", "Telepon", "QR UUID"])
    for m in rows:
        k = db.get(Kelas, m.kelas_id)
        w.writerow([m.nisn or "", m.nama, k.nama_kelas if k else "",
                    m.nama_ortu or "", m.telepon or "", m.qr_uuid])
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="murid.csv"'})


@router.get("/export.xlsx", response_class=Response)
def export_murid_xlsx(db: Session = Depends(get_tenant_db),
                      _: dict = Depends(require_permission("murid.view", "murid.create", "murid.update", "murid.delete", "murid.import", "murid.qr"))):
    """Export SEMUA murid aktif dadi .xlsx (Excel)."""
    rows = (db.query(Murid).filter(Murid.is_active.is_(True))
            .order_by(Murid.nisn).all())
    data = []
    for m in rows:
        k = db.get(Kelas, m.kelas_id)
        data.append([m.nisn or "", m.nama, k.nama_kelas if k else "",
                     m.nama_ortu or "", m.telepon or "", m.qr_uuid])
    return Response(
        content=rows_to_xlsx(["NISN", "Nama", "Kelas", "Nama Ortu", "Telepon",
                              "QR UUID"], data),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": 'attachment; filename="murid.xlsx"'})


@router.get("/template.xlsx", response_class=Response)
def template_murid(_: dict = Depends(require_permission("murid.view", "murid.create", "murid.update", "murid.delete", "murid.import", "murid.qr"))):
    """Template import murid .xlsx — diisi pengguna banjur di-Import."""
    data = [
        ["2400000001", "Contoh Nama Murid", "7A", "Nama Orang Tua", "6281234567890"],
        ["2400000002", "Contoh Nama Murid 2", "7A", "Nama Orang Tua 2", ""],
    ]
    return Response(
        content=rows_to_xlsx(["NISN", "Nama", "Kelas", "Nama Ortu", "Telepon"],
                             data),
        media_type=XLSX_MIME,
        headers={"Content-Disposition":
                 'attachment; filename="template-import-murid.xlsx"'})


@router.get("/lulus")
def lulus_murid(kelas_nama: str, tahun_ajaran_id: int | None = None,
                db: Session = Depends(get_tenant_db),
                _: dict = Depends(require_permission("murid.view", "murid.create", "murid.update", "murid.delete", "kelas.view", "absen.rekap"))):
    """Murid lulus (is_active=False) saka kelas jeneng X — lintas taun, grouped per taun.

    Tanpa tahun_ajaran_id → list group [{tahun_ajaran_id, tahun_nama, kelas_id,
    kelas_nama, jumlah, items}]. Kanthi tahun_ajaran_id → siji group.
    """
    q = (db.query(Murid)
         .join(Kelas, Kelas.id == Murid.kelas_id)
         .filter(Murid.is_active.is_(False), Kelas.nama_kelas == kelas_nama))
    if tahun_ajaran_id is not None:
        q = q.filter(Kelas.tahun_ajaran_id == tahun_ajaran_id)
    rows = q.order_by(Kelas.tahun_ajaran_id, Murid.nisn).all()

    groups: dict[int, dict] = {}
    for m in rows:
        k = db.get(Kelas, m.kelas_id)
        key = k.tahun_ajaran_id if k else 0
        g = groups.setdefault(key, {
            "tahun_ajaran_id": key, "tahun_nama": "-",
            "kelas_id": m.kelas_id, "kelas_nama": kelas_nama, "items": [],
        })
        if g["tahun_nama"] == "-" and k:
            t = db.get(TahunAjaran, k.tahun_ajaran_id)
            g["tahun_nama"] = t.nama if t else "-"
        g["items"].append(_to_out(m, db))
    for g in groups.values():
        g["jumlah"] = len(g["items"])

    out = list(groups.values())
    if tahun_ajaran_id is not None:
        if out:
            return out[0]
        return {"tahun_ajaran_id": tahun_ajaran_id, "tahun_nama": "-",
                "kelas_id": None, "kelas_nama": kelas_nama, "jumlah": 0,
                "items": []}
    return out


@router.post("/import")
async def import_murid(file: UploadFile = File(...),
                       db: Session = Depends(get_tenant_db),
                       _: dict = Depends(require_permission("murid.view", "murid.create", "murid.update", "murid.delete", "murid.import", "murid.qr"))):
    """Import murid massal saka .xlsx/.xls (utawa CSV lawas).

    Kolom: NISN, Nama, Kelas, Nama Ortu, Telepon (NISN/Nama Ortu/Telepon opsional).
    - Kelas sing durung ana bakal digawe otomatis
    - NISN sing wis ana dilewati (skip)
    """
    content = await file.read()
    fname = (file.filename or "").lower()
    if fname.endswith((".xlsx", ".xls")):
        headers, rows = xlsx_to_rows(content)
        dict_rows = [dict(zip(headers, r)) for r in rows]
    else:
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        dict_rows = list(reader)
        headers = reader.fieldnames or []

    header_map = {}
    for h in headers:
        key = h.strip().lower().replace("_", " ").replace("-", " ")
        header_map[key] = h

    def cell(row: dict, *aliases: str) -> str:
        for a in aliases:
            if a in header_map:
                return (row.get(header_map[a]) or "").strip()
        return ""

    kelas_cache = {k.nama_kelas: k.id for k in db.query(Kelas).all()}
    added = skipped = 0
    errors = []
    for i, raw in enumerate(dict_rows, start=2):
        nisn = cell(raw, "nisn", "nis")  # 'nis' diterima sebagai alias legacy
        nama = cell(raw, "nama", "nama lengkap")
        kelas_nama = cell(raw, "kelas", "nama kelas")
        nama_ortu = cell(raw, "nama ortu", "ortu", "nama orang tua")
        wa_ortu = cell(raw, "telepon", "no telepon", "no hp", "nowa", "wa ortu", "no wa ortu")
        if not nama:
            errors.append({"baris": i, "pesan": "Nama kosong"})
            continue
        nisn = nisn or None
        if nisn and (not nisn.isdigit() or len(nisn) != 10):
            errors.append({"baris": i, "pesan": "NISN harus 10 digit angka"})
            continue
        if nisn and db.query(Murid).filter_by(nisn=nisn).first():
            skipped += 1
            continue
        if kelas_nama not in kelas_cache:
            k = Kelas(nama_kelas=kelas_nama)
            db.add(k)
            db.flush()
            kelas_cache[kelas_nama] = k.id
        db.add(Murid(nisn=nisn, nama=nama, kelas_id=kelas_cache[kelas_nama],
                     qr_uuid=str(uuid.uuid4()),
                     nama_ortu=nama_ortu or None, telepon=wa_ortu or None))
        added += 1
    db.commit()
    return {"total": added + skipped + len(errors),
            "ditambahkan": added, "sudah_ada": skipped, "error": errors}


@router.get("/{murid_id}", response_model=MuridOut)
def get_murid(murid_id: int,
              db: Session = Depends(get_tenant_db),
              _: dict = Depends(require_permission("murid.view", "murid.create", "murid.update", "murid.delete", "murid.qr", "absen.scan", "absen.manual", "absen.rekap"))):
    m = db.get(Murid, murid_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Murid tidak ditemukan")
    return _to_out(m, db)


@router.post("", response_model=MuridOut, status_code=status.HTTP_201_CREATED)
def create_murid(data: MuridCreate,
                 db: Session = Depends(get_tenant_db),
                 _: dict = Depends(require_permission("murid.view", "murid.create", "murid.update", "murid.delete", "murid.import", "murid.qr"))):
    if data.nisn and db.query(Murid).filter_by(nisn=data.nisn).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "NISN sudah dipakai")
    if not db.get(Kelas, data.kelas_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kelas tidak ditemukan")
    m = Murid(
        nisn=data.nisn, nama=data.nama, kelas_id=data.kelas_id,
        qr_uuid=str(uuid.uuid4()),
        nama_ortu=data.nama_ortu, telepon=data.telepon,
        nik=data.nik, tempat_lahir=data.tempat_lahir,
        tanggal_lahir=data.tanggal_lahir, jenis_kelamin=data.jenis_kelamin,
        alamat=data.alamat, nama_ayah_kandung=data.nama_ayah_kandung,
        nama_ibu_kandung=data.nama_ibu_kandung)
    db.add(m)
    db.commit()
    db.refresh(m)
    return _to_out(m, db)


@router.patch("/{murid_id}", response_model=MuridOut)
def update_murid(murid_id: int, data: MuridUpdate,
                 db: Session = Depends(get_tenant_db),
                 _: dict = Depends(require_permission("murid.view", "murid.create", "murid.update", "murid.delete", "murid.import", "murid.qr"))):
    m = db.get(Murid, murid_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Murid tidak ditemukan")
    if "nisn" in data.model_fields_set:
        if data.nisn and db.query(Murid).filter(Murid.nisn == data.nisn, Murid.id != murid_id).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "NISN sudah dipakai")
        m.nisn = data.nisn  # None → kosongkan (valid: NULL unik per baris)
    if data.nama is not None:
        m.nama = data.nama
    if data.kelas_id is not None:
        if not db.get(Kelas, data.kelas_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Kelas tidak ditemukan")
        m.kelas_id = data.kelas_id
    # Field EMIS — pakai model_fields_set supaya None bisa kosongkan
    for f in ("nama_ortu", "telepon", "nik", "tempat_lahir", "tanggal_lahir",
              "jenis_kelamin", "alamat", "nama_ayah_kandung", "nama_ibu_kandung"):
        if f in data.model_fields_set:
            setattr(m, f, getattr(data, f))
    if data.is_active is not None:
        m.is_active = data.is_active
    db.commit()
    db.refresh(m)
    return _to_out(m, db)


@router.delete("/{murid_id}")
def deactivate_murid(murid_id: int,
                     db: Session = Depends(get_tenant_db),
                     _: dict = Depends(require_permission("murid.view", "murid.create", "murid.update", "murid.delete", "murid.import", "murid.qr"))):
    """Soft-delete: archive (is_active=False), absensi tetep tersimpen."""
    m = db.get(Murid, murid_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Murid tidak ditemukan")
    m.is_active = False
    db.commit()
    return {"ok": True}


# ── Import EMIS (2026-08-17) ──────────────────────────────────────────────
# File ekspor EMIS Kemenag: multi-sheet per rombel, kolom standar EMIS.
# Mapping otomatis ke field app + auto-create kelas + skip duplikat NISN.


def _parse_rombel(tingkat_rombel: str) -> tuple[int | None, int | None]:
    """Parse 'Kelas 7 - 01' → (tingkat=7, rombel=1). None kalau tidak cocok."""
    m = re.search(r"(\d+)\s*[-_]\s*(\d+)", str(tingkat_rombel or ""))
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+)\s*(\d{2})", str(tingkat_rombel or ""))
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def _resolve_kelas(db: Session, tingkat: int | None, rombel: int | None,
                   raw: str, ta_id: int) -> Kelas:
    """Cari kelas existing (ABC / 7-01 / 7.1) atau buat baru.

    Prioritas:
    1. Pola ABC: 01→A, 02→B... ("7A") — kalau kelas seperti itu sudah ada.
    2. Pola angka: "7-01"/"7.1" — kalau sudah ada.
    3. Fallback: buat kelas baru dengan nama normalisasi ("7-01").
    """
    nama_candidates: list[str] = []
    if tingkat is not None and rombel is not None:
        abjad = chr(ord("A") + rombel - 1) if 1 <= rombel <= 26 else None
        if abjad:
            nama_candidates.append(f"{tingkat}{abjad}")          # 7A
        nama_candidates.append(f"{tingkat}-{rombel:02d}")        # 7-01
        nama_candidates.append(f"{tingkat}.{rombel}")            # 7.1
    raw_norm = re.sub(r"\s+", " ", str(raw or "")).strip()
    if raw_norm and raw_norm.lower().startswith("kelas"):
        raw_norm = raw_norm.split(" ", 1)[1].strip()             # "7 - 01"
    if raw_norm:
        nama_candidates.append(raw_norm)

    for nama in nama_candidates:
        k = (db.query(Kelas)
             .filter(Kelas.nama_kelas == nama, Kelas.tahun_ajaran_id == ta_id)
             .first())
        if k:
            return k
    # Buat baru: nama pertama yang valid
    nama_baru = nama_candidates[0] if nama_candidates else f"Kelas {raw}"
    k = Kelas(nama_kelas=nama_baru, tahun_ajaran_id=ta_id)
    db.add(k)
    db.flush()
    return k


def _parse_tanggal(v) -> date | None:
    if not v:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


@router.post("/import-emis")
async def import_emis(file: UploadFile = File(...),
                      db: Session = Depends(get_tenant_db),
                      _: dict = Depends(require_permission("murid.view", "murid.create", "murid.update", "murid.delete", "murid.import", "murid.qr"))):
    """Import murid dari file ekspor EMIS Kemenag (multi-sheet per rombel).

    Kolom EMIS (sheet per rombel): Nama Lengkap, NISN, NIK, Tempat Lahir,
    Tanggal Lahir, Tingkat - Rombel, Jenis Kelamin, Alamat, No Telepon,
    Nama Ayah Kandung, Nama Ibu Kandung, dll. Kolom lain diabaikan.

    - Auto-create kelas (pola ABC/angka, lihat _resolve_kelas)
    - Skip duplikat NISN (sudah ada di DB)
    - NISN wajib 10 digit kalau diisi; nama wajib
    """
    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"File bukan Excel EMIS valid: {e}")

    ta = db.query(TahunAjaran).filter(TahunAjaran.is_active.is_(True)).first()
    if not ta:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Belum ada tahun ajaran aktif — buat dulu")

    def norm(h):
        return str(h or "").strip().lower().replace("_", " ").replace("-", " ")

    # Map kolom EMIS → key internal
    KEY_ALIASES = {
        "nama": ("nama lengkap", "nama"),
        "nisn": ("nisn",),
        "nik": ("nik", "nik ktp"),
        "tempat_lahir": ("tempat lahir",),
        "tanggal_lahir": ("tanggal lahir", "ttl tanggal"),
        "tingkat_rombel": ("tingkat - rombel", "tingkat rombel", "rombel", "kelas"),
        "jenis_kelamin": ("jenis kelamin", "jk", "jenis kelamin (lk/pr)"),
        "alamat": ("alamat",),
        "telepon": ("no telepon", "telepon", "no hp", "no telp"),
        "ayah": ("nama ayah kandung", "nama ayah", "ayah kandung"),
        "ibu": ("nama ibu kandung", "nama ibu", "ibu kandung"),
        "nama_ortu": ("nama wali", "nama ortu", "nama orang tua"),
    }

    added = skipped = 0
    errors: list[dict] = []
    kelas_cache: dict[str, Kelas] = {}

    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        headers = [norm(h) for h in rows[0]]
        idx: dict[str, int] = {}
        for key, aliases in KEY_ALIASES.items():
            for a in aliases:
                if a in headers:
                    idx[key] = headers.index(a)
                    break

        for r_idx, row in enumerate(rows[1:], start=2):
            if all(c is None or str(c).strip() == "" for c in row):
                continue
            def cell(key: str) -> str:
                i = idx.get(key)
                return str(row[i]).strip() if i is not None and row[i] is not None else ""

            nama = cell("nama")
            nisn = cell("nisn")
            if not nama:
                errors.append({"sheet": ws.title, "baris": r_idx,
                               "pesan": "Nama kosong"})
                continue
            if nisn and (not nisn.isdigit() or len(nisn) != 10):
                errors.append({"sheet": ws.title, "baris": r_idx,
                               "pesan": f"NISN '{nisn}' bukan 10 digit"})
                continue
            if nisn and db.query(Murid).filter_by(nisn=nisn).first():
                skipped += 1
                continue

            # Kelas
            raw_rombel = cell("tingkat_rombel") or ws.title
            tingkat, rombel = _parse_rombel(raw_rombel)
            cache_key = raw_rombel or ws.title
            if cache_key not in kelas_cache:
                kelas_cache[cache_key] = _resolve_kelas(
                    db, tingkat, rombel, raw_rombel, ta.id)
            kelas = kelas_cache[cache_key]

            ayah = cell("ayah") or None
            ibu = cell("ibu") or None
            nama_ortu = cell("nama_ortu") or (ibu or ayah) or None
            nik_raw = cell("nik").lstrip("'")  # Excel text format sering ada apostrof
            db.add(Murid(
                nisn=nisn or None,
                nama=nama,
                kelas_id=kelas.id,
                qr_uuid=str(uuid.uuid4()),
                nik=nik_raw or None,
                tempat_lahir=cell("tempat_lahir") or None,
                tanggal_lahir=_parse_tanggal(cell("tanggal_lahir")),
                jenis_kelamin=cell("jenis_kelamin") or None,
                alamat=cell("alamat") or None,
                telepon=cell("telepon") or None,
                nama_ayah_kandung=ayah,
                nama_ibu_kandung=ibu,
                nama_ortu=nama_ortu,
            ))
            added += 1

    db.commit()
    return {
        "total": added + skipped + len(errors),
        "ditambahkan": added,
        "dilewati_duplikat": skipped,
        "error": errors,
    }


@router.get("/{murid_id}/riwayat")
def riwayat_murid(murid_id: int,
                  bulan: str | None = Query(None),  # YYYY-MM
                  db: Session = Depends(get_tenant_db),
                  _: dict = Depends(require_permission("murid.view", "kelas.view", "wali.view"))):
    """Riwayat komposit murid untuk halaman Wali Kelas (per bulan).

    Gabung dalam 1 request: ringkasan absensi bulan (H/I/S/A + %),
    catatan & sesi BK + status SP, plus placeholder tagihan/nilai
    (null — diisi modul SPP/rapor nanti).
    """
    from datetime import date, datetime, timedelta
    from sqlalchemy import func
    from ..models import (Absensi, BkCatatan, BkKategori, BkKonfigurasi,
                          BkPeserta, BkSesi, Guru, JenisPembayaran,
                          Kelas as KelasModel, Pembayaran, Tagihan)

    m = db.get(Murid, murid_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Murid tidak ditemukan")
    kelas = db.get(KelasModel, m.kelas_id)

    # Bulan default: berjalan
    now = date.today()
    if bulan:
        try:
            tgl_awal = datetime.strptime(bulan, "%Y-%m").date().replace(day=1)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Format bulan tidak valid (YYYY-MM)")
    else:
        tgl_awal = now.replace(day=1)
    if tgl_awal.month == 12:
        tgl_akhir = tgl_awal.replace(year=tgl_awal.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        tgl_akhir = tgl_awal.replace(month=tgl_awal.month + 1, day=1) - timedelta(days=1)
    if tgl_akhir > now:
        tgl_akhir = now

    # ── Absensi bulan: gabung per tanggal (prioritas alpa>sakit>izin>hadir)
    recs = (db.query(Absensi).filter(
        Absensi.murid_id == murid_id,
        Absensi.tanggal >= tgl_awal, Absensi.tanggal <= tgl_akhir)
        .order_by(Absensi.tanggal.asc(), Absensi.waktu.asc()).all())
    by_tgl: dict[date, dict] = {}
    for r in recs:
        by_tgl.setdefault(r.tanggal, {})[r.sesi] = r
    PRIORITAS = ["alpa", "sakit", "izin", "hadir"]
    STATUS_LETTER = {"hadir": "H", "izin": "I", "sakit": "S", "alpa": "A"}
    HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    ringkas = {"hadir": 0, "izin": 0, "sakit": 0, "alpa": 0}
    detail = []
    for tgl in sorted(by_tgl.keys()):
        st = "hadir"
        for p in PRIORITAS:
            if any(r.status == p for r in by_tgl[tgl].values()):
                st = p
                break
        ringkas[st] += 1
        rm = by_tgl[tgl].get("masuk")
        rp = by_tgl[tgl].get("pulang")
        detail.append({
            "tanggal": tgl.strftime("%d/%m/%Y"),
            "hari": HARI[tgl.weekday()],
            "jam_masuk": rm.waktu.strftime("%H:%M") if rm and rm.waktu else "-",
            "jam_pulang": rp.waktu.strftime("%H:%M") if rp and rp.waktu else "-",
            "status": st,
            "status_letter": STATUS_LETTER.get(st, "-"),
        })
    total = len(detail)

    # ── BK: catatan + sesi bulan + status SP (semua periode)
    konfig = db.get(BkKonfigurasi, 1)
    total_poin = 0
    catatan = []
    catatan_q = (db.query(BkCatatan, BkKategori)
                 .join(BkPeserta, (BkPeserta.entitas == "catatan") &
                                 (BkPeserta.entitas_id == BkCatatan.id))
                 .outerjoin(BkKategori, BkKategori.id == BkCatatan.kategori_id)
                 .filter(BkPeserta.murid_id == murid_id,
                         BkCatatan.tanggal >= tgl_awal, BkCatatan.tanggal <= tgl_akhir)
                 .order_by(BkCatatan.tanggal.desc()).limit(20).all())
    for c, k in catatan_q:
        if k and k.jenis == "negatif":
            total_poin += (c.poin_snapshot or 0)
        catatan.append({
            "tanggal": c.tanggal.strftime("%d/%m/%Y"),
            "kategori": k.nama if k else "-",
            "kategori_jenis": k.jenis if k else "netral",
            "judul": c.judul,
            "isi": (c.isi or "")[:120],
            "poin": c.poin_snapshot,
        })
    sesi = []
    sesi_q = (db.query(BkSesi, Guru)
              .join(BkPeserta, (BkPeserta.entitas == "sesi") &
                              (BkPeserta.entitas_id == BkSesi.id))
              .outerjoin(Guru, Guru.id == BkSesi.guru_id)
              .filter(BkPeserta.murid_id == murid_id,
                      BkSesi.tanggal >= tgl_awal, BkSesi.tanggal <= tgl_akhir)
              .order_by(BkSesi.tanggal.desc()).limit(10).all())
    for s, g in sesi_q:
        sesi.append({
            "tanggal": s.tanggal.strftime("%d/%m/%Y"),
            "topik": s.topik or "-",
            "hasil": (s.hasil or "")[:120],
            "guru": g.nama if g else "-",
        })
    if konfig:
        if total_poin >= konfig.threshold_sp3:
            status_sp = "SP 3"
        elif total_poin >= konfig.threshold_sp2:
            status_sp = "SP 2"
        elif total_poin >= konfig.threshold_sp1:
            status_sp = "SP 1"
        elif total_poin > 0:
            status_sp = "Peringatan"
        else:
            status_sp = "Aman"
    else:
        status_sp = "Aman"

    # ── Tagihan bulan ini (ringkas — modul Pembayaran) ──
    tagihan_q = (db.query(Tagihan, JenisPembayaran)
                 .join(JenisPembayaran, Tagihan.jenis_id == JenisPembayaran.id)
                 .filter(Tagihan.murid_id == murid_id,
                         Tagihan.periode == tgl_awal.strftime("%Y-%m"))
                 .all())
    tagihan_list = []
    tagihan_lunas = tagihan_sebagian = tagihan_belum = 0
    tagihan_nominal = tagihan_terbayar = 0
    for t, j in tagihan_q:
        dibayar = (db.query(func.coalesce(func.sum(Pembayaran.nominal), 0))
                   .filter(Pembayaran.tagihan_id == t.id).scalar()) or 0
        status = t.status
        if status == "lunas":
            tagihan_lunas += 1
        elif status == "sebagian":
            tagihan_sebagian += 1
        else:
            tagihan_belum += 1
        tagihan_nominal += t.nominal
        tagihan_terbayar += dibayar
        tagihan_list.append({
            "id": t.id, "jenis": j.nama if j else "-",
            "nominal": t.nominal, "potongan": t.potongan,
            "dibayar": dibayar, "sisa": max(t.nominal - t.potongan - dibayar, 0),
            "status": status,
        })

    return {
        "murid": {"id": m.id, "nama": m.nama, "nisn": m.nisn,
                  "kelas_nama": kelas.nama_kelas if kelas else "-"},
        "data_murid": {
            "nik": m.nik,
            "tempat_lahir": m.tempat_lahir,
            "tanggal_lahir": m.tanggal_lahir.strftime("%d/%m/%Y") if m.tanggal_lahir else None,
            "jenis_kelamin": m.jenis_kelamin,
            "alamat": m.alamat,
            "telepon": m.telepon,
            "nama_ayah_kandung": m.nama_ayah_kandung,
            "nama_ibu_kandung": m.nama_ibu_kandung,
            "nama_ortu": m.nama_ortu,
            "qr_uuid": m.qr_uuid,
        },
        "bulan": tgl_awal.strftime("%Y-%m"),
        "bulan_label": f"{BULAN_NAMES[tgl_awal.month - 1]} {tgl_awal.year}",
        "absensi": {
            "ringkas": ringkas,
            "total": total,
            "pct_hadir": f"{ringkas['hadir'] / total * 100:.0f}%" if total else "0%",
            "detail": detail,
        },
        "bk": {
            "catatan": catatan,
            "sesi": sesi,
            "total_poin_pelanggaran": total_poin,
            "status_sp": status_sp,
        },
        "tagihan": {
            "total": len(tagihan_list),
            "lunas": tagihan_lunas,
            "sebagian": tagihan_sebagian,
            "belum": tagihan_belum,
            "nominal": tagihan_nominal,
            "terbayar": tagihan_terbayar,
            "rincian": tagihan_list,
        },  # ringkas — detail transaksi di menu Pembayaran
        "nilai": None,    # placeholder — modul rapor nanti
    }


BULAN_NAMES = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
               "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
