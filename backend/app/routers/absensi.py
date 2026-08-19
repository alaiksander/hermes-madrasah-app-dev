"""Absensi: scan QR, manual, absen per kelas, anti-duplikat, hari ini, rekap, export"""
import csv
import io
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..deps import get_tenant_db, get_tenant_db_publik, require_permission, require_roles
from ..models import Absensi, Guru, Kelas, LogWA, Murid
from ..routers.pengaturan import get_pengaturan
from ..schemas import (ABSENSI_STATUSES, AbsenKoreksiRequest, AbsenManualRequest,
                       AbsenRecord, AbsenResult, AbsenScanRequest, KelasAbsenEntry,
                       KelasAbsenRequest, KelasAbsenResult, MuridOut, RekapOut,
                       RekapPerKelas, RosterItem)
from ..xlsx_utils import XLSX_MIME, rows_to_xlsx

router = APIRouter(prefix="/api/absensi", tags=["absensi"])

WIB = ZoneInfo("Asia/Jakarta")

STATUS_LABEL = {"hadir": "Hadir", "izin": "Izin", "sakit": "Sakit", "alpa": "Alpa"}
STATUS_LETTER = {"hadir": "H", "izin": "I", "sakit": "S", "alpa": "A"}


def _now_wib() -> datetime:
    return datetime.now(WIB)


def _to_absen_record(a: Absensi, db: Session) -> AbsenRecord:
    m = db.get(Murid, a.murid_id)
    k = db.get(Kelas, m.kelas_id) if m else None
    g = db.get(Guru, a.guru_id)
    return AbsenRecord(
        id=a.id, murid_id=a.murid_id, nisn=m.nisn if m else "-",
        nama=m.nama if m else "-", kelas=k.nama_kelas if k else "-",
        sesi=a.sesi, status=a.status, telat_menit=a.telat_menit,
        tanggal=a.tanggal, waktu=a.waktu,
        guru=g.nama if g else "-")


def _do_absen(db: Session, murid: Murid, user: dict) -> AbsenResult:
    """Catat absen (masuk/pulang) + anti-duplikat + cooldown + hook pengaturan.

    Auto-detect sesi:
    - Belum ada record masuk hari ini  -> sesi "masuk"
    - Sudah ada record masuk (≥1 jam)  -> sesi "pulang"
    - Sudah ada masuk & pulang         -> duplikat

    Cooldown 1 jam: scan kedua < 1 jam dari masuk ditolak sebagai duplikat
    (mencegah dobel scan pagi salah tercatat pulang). Admin bisa override
    via koreksi manual (POST /koreksi).

    Hook (miturut setelan madrasah):
    - dina non-aktif  -> ditolak (status "libur")
    - lewat jam_masuk -> ditandha telat_menit
    """
    now = _now_wib()
    st = get_pengaturan(db)
    COOLDOWN_JAM = 1  # jam — gap minimal masuk→pulang (override admin via koreksi)

    # Hook: dina non-aktif
    if now.isoweekday() not in st["hari_aktif"]:
        return AbsenResult(status="libur",
                           pesan="Hari ini non-aktif (libur) — absen tidak dibuka",
                           waktu=now, sesi="masuk")

    existing_masuk = db.query(Absensi).filter(
        Absensi.murid_id == murid.id,
        Absensi.sesi == "masuk",
        Absensi.tanggal == now.date(),
    ).first()
    existing_pulang = db.query(Absensi).filter(
        Absensi.murid_id == murid.id,
        Absensi.sesi == "pulang",
        Absensi.tanggal == now.date(),
    ).first()

    # ── Kasus: sudah masuk & pulang → duplikat total
    if existing_masuk and existing_pulang:
        guru = db.get(Guru, existing_pulang.guru_id)
        return AbsenResult(
            status="duplikat",
            pesan=f"Ananda sudah absen lengkap hari ini: masuk "
                  f"{existing_masuk.waktu.strftime('%H:%M')}, pulang "
                  f"{existing_pulang.waktu.strftime('%H:%M')} "
                  f"(oleh {guru.nama if guru else '-'})",
            waktu=existing_pulang.waktu, sesi="pulang",
            guru_pengabsen=guru.nama if guru else None)

    # ── Kasus: sudah masuk, belum pulang
    if existing_masuk:
        # COOLDOWN: < 1 jam sejak masuk → tolak (dobel scan pagi)
        # SQLite simpan waktu naive → normalize ke aware (WIB) dulu
        w_masuk = existing_masuk.waktu
        if w_masuk.tzinfo is None:
            w_masuk = w_masuk.replace(tzinfo=WIB)
        gap = now - w_masuk
        if gap < timedelta(hours=COOLDOWN_JAM):
            guru = db.get(Guru, existing_masuk.guru_id)
            return AbsenResult(
                status="duplikat",
                pesan=f"Ananda baru diabsen masuk jam "
                      f"{existing_masuk.waktu.strftime('%H:%M')} "
                      f"({int(gap.total_seconds() // 60)} menit lalu) — "
                      f"tunggu minimal {COOLDOWN_JAM} jam untuk scan pulang",
                waktu=existing_masuk.waktu, sesi="masuk",
                guru_pengabsen=guru.nama if guru else None)

        # Sah: catat pulang
        a = Absensi(murid_id=murid.id, guru_id=user["id"], sesi="pulang",
                    tanggal=now.date(), waktu=now, telat_menit=None)
        db.add(a)
        db.flush()
        db.add(LogWA(absensi_id=a.id, wa_to=murid.telepon, status="pending"))
        db.commit()
        db.refresh(a)

        kelas = db.get(Kelas, murid.kelas_id)
        mo = MuridOut.model_validate(murid).model_copy(
            update={"kelas_nama": kelas.nama_kelas if kelas else None})
        return AbsenResult(
            status="pulang",
            pesan=f"Pulang ✓ {murid.nama} "
                  f"({kelas.nama_kelas if kelas else '-'}) jam "
                  f"{now.strftime('%H:%M')}",
            murid=mo, waktu=a.waktu, sesi=a.sesi,
            guru_pengabsen=user["nama"], telat_menit=None)

    # ── Kasus: belum ada record → masuk
    # Hook: telat (lewat jam_masuk)
    telat = None
    try:
        hm = st["jam_masuk"]
        jam_masuk = time(int(hm.split(":")[0]), int(hm.split(":")[1]))
        if now.time() > jam_masuk:
            telat = int((datetime.combine(now.date(), now.time()) -
                         datetime.combine(now.date(), jam_masuk)).total_seconds() // 60)
    except (ValueError, TypeError):
        telat = None

    a = Absensi(murid_id=murid.id, guru_id=user["id"], sesi="masuk",
                tanggal=now.date(), waktu=now, telat_menit=telat)
    db.add(a)
    db.flush()
    db.add(LogWA(absensi_id=a.id, wa_to=murid.wa_ortu, status="pending"))
    db.commit()
    db.refresh(a)

    kelas = db.get(Kelas, murid.kelas_id)
    mo = MuridOut.model_validate(murid).model_copy(update={"kelas_nama": kelas.nama_kelas if kelas else None})
    pesan = f"Hadir ✓ {murid.nama} ({kelas.nama_kelas if kelas else '-'})"
    if telat:
        pesan += f" — Telat {telat} menit"
    return AbsenResult(status="hadir",
                       pesan=pesan,
                       murid=mo, waktu=a.waktu, sesi=a.sesi,
                       guru_pengabsen=user["nama"], telat_menit=telat)


@router.post("/scan", response_model=AbsenResult)
def absen_scan(data: AbsenScanRequest,
               db: Session = Depends(get_tenant_db),
               user: dict = Depends(require_permission("absen.scan", "absen.manual", "absen.rekap", "absen.koreksi", "absen.export", "absen.cetak"))):
    """Guru piket scan QR Card murid (isi: qr_uuid)."""
    murid = db.query(Murid).filter(Murid.qr_uuid == data.qr_uuid,
                                   Murid.is_active.is_(True)).first()
    if not murid:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "QR tidak dikenali — murid tidak ditemukan (hubungi admin)")
    return _do_absen(db, murid, user)


@router.post("/manual", response_model=AbsenResult)
def absen_manual(data: AbsenManualRequest,
                 db: Session = Depends(get_tenant_db),
                 user: dict = Depends(require_permission("absen.scan", "absen.manual", "absen.rekap", "absen.koreksi", "absen.export", "absen.cetak"))):
    """Fallback: QR ilang/rusak — admin pilih murid (cari nama/NIS)."""
    murid = db.get(Murid, data.murid_id)
    if not murid or not murid.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Murid tidak ditemukan")
    return _do_absen(db, murid, user)


@router.get("/kelas/{kelas_id}", response_model=list[RosterItem])
def roster_kelas(kelas_id: int, tanggal: date | None = None,
                 db: Session = Depends(get_tenant_db),
                 _: dict = Depends(require_permission("absen.scan", "absen.manual", "absen.rekap", "absen.koreksi", "absen.export", "absen.cetak"))):
    """Daftar murid aktif siji kelas + status absensi ing tanggal (None = durung)."""
    k = db.get(Kelas, kelas_id)
    if not k:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kelas tidak ditemukan")
    tgl = tanggal or _now_wib().date()
    murids = (db.query(Murid).filter(Murid.kelas_id == kelas_id,
                                     Murid.is_active.is_(True))
              .order_by(Murid.nisn).all())
    # Ambil SEMUA sesi per tanggal (gabung masuk+pulang per murid)
    absen_map: dict[int, dict[str, Absensi]] = {}
    for a in db.query(Absensi).filter(
            Absensi.tanggal == tgl,
            Absensi.murid_id.in_([m.id for m in murids])).all():
        absen_map.setdefault(a.murid_id, {})[a.sesi] = a

    def _jam(waktu):
        return waktu.strftime("%H:%M") if waktu else None

    out = []
    for m in murids:
        recs = absen_map.get(m.id, {})
        masuk = recs.get("masuk")
        pulang = recs.get("pulang")
        # Prioritas: kalau ada "izin/sakit/alpa" pakai itu; kalau hadir di
        # keduanya pakai Masuk (hadir pulang tidak ubah status)
        r_repr = masuk or pulang
        status = r_repr.status if r_repr else None
        waktu_legacy = masuk.waktu if masuk else (pulang.waktu if pulang else None)
        guru_masuk = db.get(Guru, masuk.guru_id) if masuk else None
        out.append(RosterItem(
            murid_id=m.id, nisn=m.nisn, nama=m.nama,
            status=status,
            jam_masuk=_jam(masuk.waktu) if masuk else None,
            jam_pulang=_jam(pulang.waktu) if pulang else None,
            waktu=waktu_legacy,
            guru=guru_masuk.nama if guru_masuk else None,
        ))
    return out


@router.post("/kelas/{kelas_id}", response_model=KelasAbsenResult)
def absen_kelas(kelas_id: int, data: KelasAbsenRequest,
                db: Session = Depends(get_tenant_db),
                user: dict = Depends(require_permission("absen.scan", "absen.manual", "absen.rekap", "absen.koreksi", "absen.export", "absen.cetak"))):
    """Bulk absen per kelas.

    - Guru  : mung nambah record anyar (sing wis ana → sudah_ada, ora diubah)
    - Admin : bisa uga MENGUBAH status record sing wis ana (diubah)
    - Tanggal bisa dipilih (back-fill); default dina iki
    """
    k = db.get(Kelas, kelas_id)
    if not k:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kelas tidak ditemukan")
    if len(data.entries) > 200:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Maksimal 200 murid per submit")
    tgl = data.tanggal or _now_wib().date()
    is_admin = user["role"] == "admin"

    murid_ids = [e.murid_id for e in data.entries]
    murids = {m.id: m for m in db.query(Murid)
              .filter(Murid.id.in_(murid_ids), Murid.kelas_id == kelas_id,
                      Murid.is_active.is_(True)).all()}
    existing = {a.murid_id: a for a in db.query(Absensi)
                .filter(Absensi.tanggal == tgl,
                        Absensi.murid_id.in_(murid_ids)).all()}

    seen: set[int] = set()
    added = diubah = sudah = 0
    errors = []
    for i, e in enumerate(data.entries, start=1):
        if e.status not in ABSENSI_STATUSES:
            errors.append({"baris": i, "pesan": f"Status '{e.status}' tidak valid"})
            continue
        if e.murid_id in seen:
            continue  # duplikat dalam siji submit → dedupe
        seen.add(e.murid_id)
        if e.murid_id not in murids:
            errors.append({"baris": i,
                           "pesan": "Murid tidak ditemukan / bukan kelas ini"})
            continue
        a = existing.get(e.murid_id)
        if a is not None:
            if is_admin and a.status != e.status:
                a.status = e.status
                a.guru_id = user["id"]
                diubah += 1
            else:
                sudah += 1
            continue
        a = Absensi(murid_id=e.murid_id, guru_id=user["id"], sesi="masuk",
                    tanggal=tgl, waktu=_now_wib(), status=e.status)
        db.add(a)
        db.flush()
        db.add(LogWA(absensi_id=a.id, wa_to=murids[e.murid_id].telepon,
                     status="pending"))
        added += 1
    db.commit()
    return KelasAbsenResult(ditambahkan=added, diubah=diubah,
                            sudah_ada=sudah, error=errors)


@router.get("/hari-ini", response_model=list[AbsenRecord])
def absen_hari_ini(tanggal: date | None = None,
                   limit: int | None = Query(None, ge=1, le=200),
                   db: Session = Depends(get_tenant_db),
                   _: dict = Depends(require_permission("absen.scan", "absen.manual", "absen.rekap", "absen.koreksi", "absen.export", "absen.cetak"))):
    """Daftar absen (counter guru piket + feed rekap).

    Urutan paling anyar dhisik; `limit` kanggo feed Daftar Hadir (10-15).
    Sekarang TAMPILKAN SEMUA SESI (masuk + pulang) — biar counter
    'Daftar Hadir' juga reflect siswa yang sudah scan pulang."""
    tgl = tanggal or _now_wib().date()
    q = db.query(Absensi).filter(Absensi.tanggal == tgl)
    if limit:
        q = q.order_by(Absensi.id.desc()).limit(limit)
    return [_to_absen_record(a, db) for a in q.all()]


@router.post("/koreksi", response_model=AbsenResult)
def absen_koreksi(data: AbsenKoreksiRequest,
                  db: Session = Depends(get_tenant_db),
                  user: dict = Depends(require_roles("admin"))):
    """Koreksi absensi oleh ADMIN (override cooldown / salah scan).

    mode='koreksi'      : ubah status record (hadir→izin, dst)
    mode='tambah_pulang': catat pulang manual (override cooldown 1 jam,
                          mis. siswa pulang awal untuk jemputan)
    mode='hapus'        : hapus record salah scan — sesi 'masuk' hanya
                          bisa dihapus kalau belum ada pulang
    """
    m = db.get(Murid, data.murid_id)
    if not m or not m.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Murid tidak ditemukan")
    tgl = data.tanggal or _now_wib().date()
    now = _now_wib()

    rec = db.query(Absensi).filter(
        Absensi.murid_id == data.murid_id,
        Absensi.sesi == data.sesi,
        Absensi.tanggal == tgl,
    ).first()

    # ── mode: koreksi (ubah status) ──
    if data.mode == "koreksi":
        if data.status not in ABSENSI_STATUSES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Status tidak valid (hadir/izin/sakit/alpa)")
        if not rec:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                f"Record sesi '{data.sesi}' tanggal {tgl} tidak ada")
        rec.status = data.status
        rec.guru_id = user["id"]
        if data.waktu:
            try:
                hh, mm = data.waktu.split(":")
                rec.waktu = datetime.combine(tgl, time(int(hh), int(mm)),
                                             tzinfo=WIB)
            except ValueError:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    "Format waktu tidak valid (HH:MM)")
        db.commit()
        return AbsenResult(
            status="koreksi",
            pesan=f"Koreksi {m.nama}: sesi {data.sesi} → {data.status}",
            murid=MuridOut.model_validate(m).model_copy(
                update={"kelas_nama": (db.get(Kelas, m.kelas_id).nama_kelas
                                       if db.get(Kelas, m.kelas_id) else None)}),
            waktu=rec.waktu, sesi=data.sesi, guru_pengabsen=user["nama"])

    # ── mode: tambah_pulang (override cooldown) ──
    if data.mode == "tambah_pulang":
        if data.sesi != "pulang":
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "mode tambah_pulang hanya untuk sesi pulang")
        existing_pulang = db.query(Absensi).filter(
            Absensi.murid_id == data.murid_id,
            Absensi.sesi == "pulang",
            Absensi.tanggal == tgl).first()
        if existing_pulang:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Sudah ada record pulang hari ini")
        # Wajib sudah ada masuk (pulang tanpa masuk tidak masuk akal)
        existing_masuk = db.query(Absensi).filter(
            Absensi.murid_id == data.murid_id,
            Absensi.sesi == "masuk",
            Absensi.tanggal == tgl).first()
        if not existing_masuk:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Belum ada record masuk — isi masuk dulu")

        waktu = now
        if data.waktu:
            try:
                hh, mm = data.waktu.split(":")
                waktu = datetime.combine(tgl, time(int(hh), int(mm)), tzinfo=WIB)
            except ValueError:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    "Format waktu tidak valid (HH:MM)")
        a = Absensi(murid_id=m.id, guru_id=user["id"], sesi="pulang",
                    tanggal=tgl, waktu=waktu, telat_menit=None)
        db.add(a)
        db.commit()
        db.refresh(a)
        return AbsenResult(
            status="pulang",
            pesan=f"Pulang manual ✓ {m.nama} jam {waktu.strftime('%H:%M')} "
                  f"(override cooldown oleh admin)",
            murid=MuridOut.model_validate(m).model_copy(
                update={"kelas_nama": (db.get(Kelas, m.kelas_id).nama_kelas
                                       if db.get(Kelas, m.kelas_id) else None)}),
            waktu=a.waktu, sesi="pulang", guru_pengabsen=user["nama"])

    # ── mode: hapus ──
    if data.mode == "hapus":
        if not rec:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                f"Record sesi '{data.sesi}' tanggal {tgl} tidak ada")
        # Proteksi: masuk yang sudah punya pulang tidak bisa dihapus
        if data.sesi == "masuk":
            punya_pulang = db.query(Absensi).filter(
                Absensi.murid_id == data.murid_id,
                Absensi.sesi == "pulang",
                Absensi.tanggal == tgl).first()
            if punya_pulang:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Tidak bisa hapus masuk — sudah ada record pulang. "
                    "Hapus pulang dulu.")
        # Hapus log_wa terkait dulu (FK NOT NULL absensi_id)
        db.query(LogWA).filter(LogWA.absensi_id == rec.id).delete()
        db.delete(rec)
        db.commit()
        return AbsenResult(
            status="dihapus",
            pesan=f"Hapus record {m.nama} sesi {data.sesi} tanggal {tgl}",
            murid=MuridOut.model_validate(m).model_copy(
                update={"kelas_nama": (db.get(Kelas, m.kelas_id).nama_kelas
                                       if db.get(Kelas, m.kelas_id) else None)}),
            waktu=now, sesi=data.sesi, guru_pengabsen=user["nama"])

    raise HTTPException(status.HTTP_400_BAD_REQUEST,
                        f"Mode '{data.mode}' tidak dikenal")


@router.get("/rekap", response_model=RekapOut)
def rekap(tanggal: date | None = None,
          kelas_id: int | None = Query(None),
          db: Session = Depends(get_tenant_db),
          _: dict = Depends(require_permission("absen.scan", "absen.manual", "absen.rekap", "absen.koreksi", "absen.export", "absen.cetak"))):
    """Rekap harian: total / hadir / izin / sakit / alpa / belum, rincian per kelas.

    Menghitung siswa yang tercatat (hadir/izin/sakit/alpa) dari
    SEMUA sesi (masuk + pulang) untuk tanggal itu. Siswa dianggap
    hadir kalau ada record masuk maupun pulang dengan status hadir.
    """
    tgl = tanggal or _now_wib().date()

    murid_q = db.query(Murid).filter(Murid.is_active.is_(True))
    if kelas_id:
        murid_q = murid_q.filter(Murid.kelas_id == kelas_id)
    all_murid = murid_q.all()

    # Ambil SEMUA sesi (masuk+pulang) per tanggal, gabung per murid
    q = db.query(Absensi).filter(Absensi.tanggal == tgl)
    if kelas_id:
        q = q.join(Murid, Absensi.murid_id == Murid.id).filter(
            Murid.kelas_id == kelas_id)

    by_murid: dict[int, dict[str, Absensi]] = {}
    for a in q.all():
        by_murid.setdefault(a.murid_id, {})[a.sesi] = a

    # Tentukan status final per murid (prioritas: izin/sakit/alpa > hadir)
    PRIORITAS = ["alpa", "sakit", "izin", "hadir"]
    by_status: dict[str, set[int]] = defaultdict(set)
    for mid, recs in by_murid.items():
        # Ambil status non-default dulu
        st = "hadir"
        for p in PRIORITAS:
            if any(r.status == p for r in recs.values()):
                st = p
                break
        by_status[st].add(mid)

    per_kelas: dict[str, dict] = {}
    for m in all_murid:
        k = db.get(Kelas, m.kelas_id)
        nama_k = k.nama_kelas if k else "-"
        row = per_kelas.setdefault(nama_k, {
            "kelas": nama_k, "total": 0, "hadir": 0, "izin": 0,
            "sakit": 0, "alpa": 0})
        row["total"] += 1
        for st in ("hadir", "izin", "sakit", "alpa"):
            if m.id in by_status.get(st, set()):
                row[st] += 1

    def mk(row: dict) -> RekapPerKelas:
        return RekapPerKelas(
            kelas=row["kelas"], total=row["total"], hadir=row["hadir"],
            izin=row["izin"], sakit=row["sakit"], alpa=row["alpa"],
            belum=row["total"] - row["hadir"] - row["izin"]
            - row["sakit"] - row["alpa"])

    return RekapOut(
        tanggal=tgl,
        total_murid=len(all_murid),
        hadir=len(by_status.get("hadir", set())),
        izin=len(by_status.get("izin", set())),
        sakit=len(by_status.get("sakit", set())),
        alpa=len(by_status.get("alpa", set())),
        belum=len(all_murid) - sum(len(s) for s in by_status.values()),
        per_kelas=[mk(per_kelas[k]) for k in sorted(per_kelas)])


@router.get("/export.xlsx", response_class=Response)
def export_absensi_xlsx(tanggal: date | None = None,
                        dari: date | None = None,
                        sampai: date | None = None,
                        db: Session = Depends(get_tenant_db),
                        _: dict = Depends(require_permission("absen.scan", "absen.manual", "absen.rekap", "absen.koreksi", "absen.export", "absen.cetak"))):
    """Export rekap absensi dadi .xlsx (Excel).

    - `tanggal=YYYY-MM-DD` → rincian harian (NIS, Nama, Kelas, Status, Jam, Petugas)
    - `dari=` & `sampai=` → matrix rentang: baris murid × kolom tanggal (H / kosong)
      + kolom Hadir & % kehadiran. Hanya tanggal sing ana absensi sing dimunculke.
    """
    if dari or sampai:
        if not (dari and sampai) or dari > sampai:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Rentang tanggal tidak valid (dari <= sampai)")
        headers, rows = _matrix_rows(db, dari, sampai)
        fname = f"rekap-{dari}-{sampai}.xlsx"
    else:
        tgl = tanggal or _now_wib().date()
        headers, rows = _harian_rows(db, tgl)
        fname = f"rekap-{tgl}.xlsx"
    return Response(
        content=rows_to_xlsx(headers, rows),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/export.csv", response_class=Response)
def export_absensi(tanggal: date | None = None,
                   dari: date | None = None,
                   sampai: date | None = None,
                   db: Session = Depends(get_tenant_db),
                   _: dict = Depends(require_permission("absen.scan", "absen.manual", "absen.rekap", "absen.koreksi", "absen.export", "absen.cetak"))):
    """Export rekap absensi CSV (legacy — frontend saiki nganggo .xlsx).

    - `tanggal=YYYY-MM-DD` → rincian harian (NIS, Nama, Kelas, Status, Jam, Petugas)
    - `dari=` & `sampai=` → matrix rentang: baris murid × kolom tanggal (H / kosong)
      + kolom Hadir & % kehadiran. Hanya tanggal sing ana absensi sing dimunculke.
    """
    if dari or sampai:
        if not (dari and sampai) or dari > sampai:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Rentang tanggal tidak valid (dari <= sampai)")
        return _export_matrix(db, dari, sampai)

    tgl = tanggal or _now_wib().date()
    return _export_harian(db, tgl)


def _harian_rows(db: Session, tgl: date) -> tuple[list[str], list[list]]:
    murids = (db.query(Murid).filter(Murid.is_active.is_(True))
              .order_by(Murid.nisn).all())
    # Ambil SEMUA sesi (masuk + pulang) — gabung per murid
    absen_by_murid: dict[int, dict[str, Absensi]] = {}
    for a in db.query(Absensi).filter(Absensi.tanggal == tgl).all():
        absen_by_murid.setdefault(a.murid_id, {})[a.sesi] = a

    PRIORITAS = ["alpa", "sakit", "izin", "hadir"]

    def status_final(recs: dict) -> tuple[str, datetime | None, Guru | None]:
        st = "hadir"
        for p in PRIORITAS:
            if any(r.status == p for r in recs.values()):
                st = p
                break
        rm = recs.get("masuk")
        rp = recs.get("pulang")
        rep = rm or rp
        guru = db.get(Guru, rep.guru_id) if rep else None
        return STATUS_LABEL.get(st, st), rep.waktu if rep else None, guru

    rows = []
    for m in murids:
        k = db.get(Kelas, m.kelas_id)
        recs = absen_by_murid.get(m.id, {})
        if recs:
            st_label, waktu, guru = status_final(recs)
            rows.append([m.nisn or "", m.nama, k.nama_kelas if k else "",
                         st_label,
                         waktu.strftime("%H:%M") if waktu else "",
                         guru.nama if guru else ""])
        else:
            rows.append([m.nisn or "", m.nama, k.nama_kelas if k else "",
                         "Tidak Hadir", "", ""])
    return ["NISN", "Nama", "Kelas", "Status", "Jam", "Diabsen oleh"], rows


def _export_harian(db: Session, tgl: date) -> Response:
    headers, rows = _harian_rows(db, tgl)
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="rekap-{tgl}.csv"'})


def _matrix_rows(db: Session, dari: date, sampai: date,
                 kelas_id: int | None = None,
                 murid_id: int | None = None) -> tuple[list[str], list[list]]:
    HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]

    # tanggal yang ada absensi (semua sesi) — exclude kosong
    days = [d for (d,) in db.query(Absensi.tanggal)
            .filter(Absensi.tanggal >= dari, Absensi.tanggal <= sampai)
            .distinct().order_by(Absensi.tanggal).all()]

    # murid -> {tanggal: status} — gabung SEMUA sesi (masuk + pulang)
    # Prioritas: izin/sakit/alpa > hadir (sama seperti rekap harian)
    PRIORITAS = ["alpa", "sakit", "izin", "hadir"]
    present: dict[int, dict] = defaultdict(dict)
    for mid, d, st in db.query(Absensi.murid_id, Absensi.tanggal, Absensi.status).filter(
            Absensi.tanggal >= dari, Absensi.tanggal <= sampai).all():
        cur = present[mid].get(d)
        # kalau existing adalah non-default, pertahankan (prioritas lebih tinggi)
        if cur is None or PRIORITAS.index(st) < PRIORITAS.index(cur):
            present[mid][d] = st

    q = db.query(Murid).filter(Murid.is_active.is_(True))
    if kelas_id:
        q = q.filter(Murid.kelas_id == kelas_id)
    if murid_id:
        q = q.filter(Murid.id == murid_id)
    murids = q.order_by(Murid.kelas_id, Murid.nisn).all()

    # Rekap angka HSIA ditaruh setelah matrix harian supaya wali kelas bisa
    # langsung menyalin jumlahnya ke rapor tanpa menghitung manual.
    header = (["NISN", "Nama", "Kelas"]
              + [f"{d.day:02d}/{d.month:02d} {HARI[d.weekday()]}" for d in days]
              + ["H", "I", "S", "A", "Hadir", "%"])
    rows = []
    for m in murids:
        k = db.get(Kelas, m.kelas_id)
        st_map = present.get(m.id, {})
        jumlah = {st: sum(1 for value in st_map.values() if value == st)
                  for st in ("hadir", "izin", "sakit", "alpa")}
        hadir_count = jumlah["hadir"]
        persen = f"{hadir_count / len(days) * 100:.0f}%" if days else "0%"
        rows.append([m.nisn or "", m.nama, k.nama_kelas if k else ""]
                    + [STATUS_LETTER.get(st_map.get(d, ""), "") for d in days]
                    + [jumlah["hadir"], jumlah["izin"], jumlah["sakit"],
                       jumlah["alpa"], hadir_count, persen])
    return header, rows


def _ringkasan_rows(db: Session, dari: date, sampai: date,
                    kelas_id: int | None = None,
                    murid_id: int | None = None) -> tuple[list[str], list[list]]:
    """Rekap hemat kertas: satu baris per murid dengan angka H/I/S/A."""
    _headers, rows = _matrix_rows(db, dari, sampai,
                                  kelas_id=kelas_id, murid_id=murid_id)
    return (["NISN", "Nama", "Kelas", "H", "I", "S", "A", "Hadir", "%"],
            [row[:3] + row[-6:] for row in rows])


def _export_matrix(db: Session, dari: date, sampai: date) -> Response:
    headers, rows = _matrix_rows(db, dari, sampai)
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)

    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="rekap-{dari}-{sampai}.csv"'})


# ── PDF: rekap absensi per murid ────────────────────────────────────────────
from io import BytesIO  # noqa: E402

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4, landscape  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,  # noqa: E402
                                Table, TableStyle)

_HARI_SINGKAT = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]


@router.get("/pdf/{murid_id}")
def absensi_pdf(murid_id: int,
                dari: date | None = Query(None),
                sampai: date | None = Query(None),
                db: Session = Depends(get_tenant_db),
                user: dict = Depends(require_permission("absen.scan", "absen.manual", "absen.rekap", "absen.koreksi", "absen.export", "absen.cetak"))):
    """PDF rekap absensi per murid: identitas + tabel + signature."""
    murid = db.get(Murid, murid_id)
    if not murid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Murid tidak ditemukan")

    q = db.query(Absensi).filter(Absensi.murid_id == murid.id,
                                 Absensi.sesi == "masuk")
    if dari:
        q = q.filter(Absensi.tanggal >= dari)
    if sampai:
        q = q.filter(Absensi.tanggal <= sampai)
    rows = q.order_by(Absensi.tanggal.asc(), Absensi.waktu.asc()).all()

    kelas = db.get(Kelas, murid.kelas_id)
    st = get_pengaturan(db)
    nama_aplikasi = st["nama_aplikasi"]
    now = _now_wib()

    # ── styles ──
    s_judul = ParagraphStyle("judul", fontName="Helvetica-Bold", fontSize=16,
                             textColor=colors.HexColor("#0F766E"), spaceAfter=2)
    s_sub = ParagraphStyle("sub", fontName="Helvetica-Bold", fontSize=11,
                           spaceAfter=10)
    s_teks = ParagraphStyle("teks", fontName="Helvetica", fontSize=10,
                            leading=14)
    s_teksb = ParagraphStyle("teksb", parent=s_teks, fontName="Helvetica-Bold")
    s_sig = ParagraphStyle("sig", fontName="Helvetica", fontSize=9,
                           textColor=colors.HexColor("#555555"), spaceBefore=2)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=20 * mm, bottomMargin=20 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            title=f"Rekap Absensi - {murid.nama}")
    story: list = []

    # Header + identitas
    story.append(Paragraph(nama_aplikasi, s_judul))
    story.append(Paragraph("Rekap Absensi Murid", s_sub))
    ident = Table([
        [Paragraph("<b>NISN</b>", s_teksb), Paragraph(murid.nisn or "-", s_teks),
         Paragraph("<b>Nama</b>", s_teksb), Paragraph(murid.nama or "-", s_teks)],
        [Paragraph("<b>Kelas</b>", s_teksb), Paragraph(kelas.nama_kelas if kelas else "-", s_teks),
         Paragraph("<b>Periode</b>", s_teksb),
         Paragraph(f"{dari.strftime('%d/%m/%Y') if dari else 'Awal'} s/d "
                   f"{sampai.strftime('%d/%m/%Y') if sampai else 'Sekarang'}", s_teks)],
    ], colWidths=[22 * mm, 65 * mm, 22 * mm, 61 * mm])
    ident.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(ident)
    story.append(Spacer(1, 8))

    # Tabel absensi
    header = [Paragraph("<b>Hari</b>", s_teksb), Paragraph("<b>Tanggal</b>", s_teksb),
              Paragraph("<b>Jam Masuk</b>", s_teksb),
              Paragraph("<b>Terlambat (menit)</b>", s_teksb),
              Paragraph("<b>Status</b>", s_teksb)]
    data = [header]
    for r in rows:
        data.append([
            _HARI_SINGKAT[r.tanggal.weekday()],
            r.tanggal.strftime("%d-%m-%Y"),
            r.waktu.strftime("%H:%M") if r.waktu else "-",
            str(r.telat_menit) if r.telat_menit else "-",
            STATUS_LETTER.get(r.status, "-"),
        ])
    if not rows:
        data.append(["-", "-", "-", "-", "Belum ada data"])

    tbl = Table(data, colWidths=[30 * mm, 38 * mm, 32 * mm, 42 * mm, 28 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F766E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BBBBBB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F1F5F9")]),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 16))

    # Signature (whitelabel: jeneng aplikasi custom + tanggal/jam cetak)
    story.append(Paragraph(f"Dibuat oleh: {nama_aplikasi}", s_sig))
    story.append(Paragraph(f"Dicetak: {now.strftime('%d/%m/%Y %H:%M')} WIB", s_sig))

    doc.build(story)
    buf.seek(0)

    slug = (murid.nama or "murid").replace(" ", "-").lower()
    return Response(content=buf.read(), media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="absensi-{slug}.pdf"'})


# ── Cetak Absen (menu admin): PDF & Excel, per murid / per kelas + rentang ──

@router.get("/cetak.json")
def cetak_json(kelas_id: int | None = None,
               murid_id: int | None = None,
               dari: date | None = None,
               sampai: date | None = None,
               ringkasan: bool = False,
               db: Session = Depends(get_tenant_db),
               _: dict = Depends(require_permission("absen.scan", "absen.manual", "absen.rekap", "absen.koreksi", "absen.export", "absen.cetak"))):
    """Data matrix absen (JSON) untuk preview HTML A4 di web.

    Sama isinya dengan cetak.xlsx / cetak-pdf.pdf — dipakai view
    cetak-absen untuk render preview A4 tanpa iframe PDF.
    """
    if not (kelas_id or murid_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Pilih kelas atau murid dulu")
    dari = dari or (_now_wib().date() - timedelta(days=30))
    sampai = sampai or _now_wib().date()
    if dari > sampai:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Rentang tanggal tidak valid (dari <= sampai)")

    if ringkasan:
        headers, rows = _ringkasan_rows(db, dari, sampai,
                                        kelas_id=kelas_id, murid_id=murid_id)
    else:
        headers, rows = _matrix_rows(db, dari, sampai,
                                     kelas_id=kelas_id, murid_id=murid_id)
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Tidak ada murid untuk filter ini")
    kelas_nama = None
    if kelas_id:
        k = db.get(Kelas, kelas_id)
        kelas_nama = k.nama_kelas if k else None
    return {
        "header": headers,
        "rows": rows,
        "dari": dari.isoformat(),
        "sampai": sampai.isoformat(),
        "kelas_nama": kelas_nama,
    }


@router.get("/murid/{murid_id}/rincian")
def rekap_rincian_murid(murid_id: int,
                        dari: date | None = None,
                        sampai: date | None = None,
                        db: Session = Depends(get_tenant_db),
                        _: dict = Depends(require_permission("absen.scan", "absen.manual", "absen.rekap", "absen.koreksi", "absen.export", "absen.cetak"))):
    """Rincian absen per murid (JSON) — untuk preview A4 portrait.

    Identitas murid + daftar rincian (tanggal, hari, waktu, status,
    telat) + ringkasan hadir/izin/sakit/alpa.
    """
    m = db.get(Murid, murid_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Murid tidak ditemukan")
    dari = dari or (_now_wib().date() - timedelta(days=30))
    sampai = sampai or _now_wib().date()
    if dari > sampai:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Rentang tanggal tidak valid (dari <= sampai)")

    q = db.query(Absensi).filter(Absensi.murid_id == murid_id,
                                 Absensi.tanggal >= dari,
                                 Absensi.tanggal <= sampai)
    rows = q.order_by(Absensi.tanggal.asc(), Absensi.waktu.asc()).all()

    kelas = db.get(Kelas, m.kelas_id)
    ringkas = {"hadir": 0, "izin": 0, "sakit": 0, "alpa": 0}
    HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    detail = []
    for r in rows:
        st = r.status
        if st in ringkas:
            ringkas[st] += 1
        detail.append({
            "tanggal": r.tanggal.strftime("%d/%m/%Y"),
            "hari": HARI[r.tanggal.weekday()],
            "waktu": r.waktu.strftime("%H:%M") if r.waktu else "-",
            "status": st,
            "status_letter": STATUS_LETTER.get(st, "-"),
            "telat": str(r.telat_menit) if r.telat_menit else "-",
        })
    total = len(rows)
    return {
        "murid": {"id": m.id, "nisn": m.nisn, "nama": m.nama,
                  "kelas_nama": kelas.nama_kelas if kelas else "-"},
        "dari": dari.isoformat(),
        "sampai": sampai.isoformat(),
        "rows": detail,
        "ringkas": ringkas,
        "total": total,
        "pct": f"{ringkas['hadir'] / total * 100:.0f}%" if total else "0%",
    }


BULAN_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


@router.get("/ortu/rekap")
def rekap_ortu_publik(nisn: str = Query(..., alias="nisn"),
                      nama_ortu: str = Query(...),
                      bulan: str | None = Query(None),  # YYYY-MM
                      db: Session = Depends(get_tenant_db_publik)):
    """Rekap absensi bulanan untuk ORANG TUA (publik, tanpa login).

    Verifikasi: NISN + nama orang tua (case-insensitive, strip).
    Butuh `kode` madrasah (query param) untuk resolve DB tenant.
    """
    m = db.query(Murid).filter(Murid.nisn == nisn.strip()).first()
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "NISN tidak ditemukan")
    if not m.nama_ortu or m.nama_ortu.strip().lower() != nama_ortu.strip().lower():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Nama orang tua tidak cocok")

    # Bulan: default bulan berjalan
    now = _now_wib()
    if bulan:
        try:
            tgl_awal = datetime.strptime(bulan, "%Y-%m").date().replace(day=1)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Format bulan tidak valid (YYYY-MM)")
    else:
        tgl_awal = now.date().replace(day=1)
    # Akhir bulan
    if tgl_awal.month == 12:
        tgl_akhir = tgl_awal.replace(year=tgl_awal.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        tgl_akhir = tgl_awal.replace(month=tgl_awal.month + 1, day=1) - timedelta(days=1)
    # Jangan tampilkan masa depan
    if tgl_akhir > now.date():
        tgl_akhir = now.date()

    q = db.query(Absensi).filter(
        Absensi.murid_id == m.id,
        Absensi.tanggal >= tgl_awal,
        Absensi.tanggal <= tgl_akhir)
    # Ambil semua sesi (masuk + pulang) — gabung per tanggal
    records = q.order_by(Absensi.tanggal.asc(), Absensi.waktu.asc()).all()

    kelas = db.get(Kelas, m.kelas_id)
    ringkas = {"hadir": 0, "izin": 0, "sakit": 0, "alpa": 0}
    HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

    # Gabung per tanggal: {tanggal: {masuk: Absensi, pulang: Absensi}}
    by_tgl: dict[date, dict] = {}
    for r in records:
        by_tgl.setdefault(r.tanggal, {})[r.sesi] = r

    detail = []
    for tgl in sorted(by_tgl.keys()):
        recs = by_tgl[tgl]
        rm = recs.get("masuk")
        rp = recs.get("pulang")
        st = rm.status if rm else (rp.status if rp else "-")
        if st in ringkas:
            ringkas[st] += 1
        detail.append({
            "tanggal": tgl.strftime("%d/%m/%Y"),
            "hari": HARI[tgl.weekday()],
            "jam_masuk": rm.waktu.strftime("%H:%M") if rm and rm.waktu else "-",
            "jam_pulang": rp.waktu.strftime("%H:%M") if rp and rp.waktu else "-",
            "status": st,
            "status_letter": STATUS_LETTER.get(st, "-"),
            "telat": str(rm.telat_menit) if rm and rm.telat_menit else "-",
        })
    total = len(detail)
    return {
        "murid": {"id": m.id, "nisn": m.nisn, "nama": m.nama,
                  "kelas_nama": kelas.nama_kelas if kelas else "-",
                  "nama_ortu": m.nama_ortu},
        "bulan": tgl_awal.strftime("%Y-%m"),
        "bulan_label": f"{BULAN_ID[tgl_awal.month - 1]} {tgl_awal.year}",
        "rows": detail,
        "ringkas": ringkas,
        "total": total,
        "pct": f"{ringkas['hadir'] / total * 100:.0f}%" if total else "0%",
    }


@router.get("/cetak.xlsx", response_class=Response)
def cetak_xlsx(kelas_id: int | None = None,
               murid_id: int | None = None,
               dari: date | None = None,
               sampai: date | None = None,
               ringkasan: bool = False,
               db: Session = Depends(get_tenant_db),
               _: dict = Depends(require_permission("absen.scan", "absen.manual", "absen.rekap", "absen.koreksi", "absen.export", "absen.cetak"))):
    """Excel matrix absen: per kelas ATAU per murid + rentang tanggal.

    Kolom: NIS, Nama, Kelas, <tanggal...>, H, I, S, A, Hadir, %.
    """
    if not (kelas_id or murid_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Pilih kelas atau murid dulu")
    dari = dari or (_now_wib().date() - timedelta(days=30))
    sampai = sampai or _now_wib().date()
    if dari > sampai:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Rentang tanggal tidak valid (dari <= sampai)")

    if ringkasan:
        headers, rows = _ringkasan_rows(db, dari, sampai,
                                        kelas_id=kelas_id, murid_id=murid_id)
    else:
        headers, rows = _matrix_rows(db, dari, sampai,
                                     kelas_id=kelas_id, murid_id=murid_id)
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Tidak ada murid untuk filter ini")
    label = f"kelas-{kelas_id}" if kelas_id else f"murid-{murid_id}"
    return Response(
        content=rows_to_xlsx(headers, rows),
        media_type=XLSX_MIME,
        headers={"Content-Disposition":
                 f'attachment; filename="cetak-absen-{label}-{dari}-{sampai}.xlsx"'})


@router.get("/cetak-pdf.pdf", response_class=Response)
def cetak_pdf_kelas(kelas_id: int,
                    dari: date | None = Query(None),
                    sampai: date | None = Query(None),
                    ringkasan: bool = False,
                    db: Session = Depends(get_tenant_db),
                    _: dict = Depends(require_permission("absen.scan", "absen.manual", "absen.rekap", "absen.koreksi", "absen.export", "absen.cetak"))):
    """PDF A4 landscape: matrix absen per KELAS + rentang tanggal.

    Header nama aplikasi + kelas + rentang, tabel matrix status,
    kolom Hadir & %, signature. Tabel otomatis split antar halaman.
    """
    kelas = db.get(Kelas, kelas_id)
    if not kelas:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kelas tidak ditemukan")
    dari = dari or (_now_wib().date() - timedelta(days=30))
    sampai = sampai or _now_wib().date()
    if dari > sampai:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Rentang tanggal tidak valid (dari <= sampai)")

    if ringkasan:
        headers, rows = _ringkasan_rows(db, dari, sampai, kelas_id=kelas_id)
    else:
        headers, rows = _matrix_rows(db, dari, sampai, kelas_id=kelas_id)
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Tidak ada murid aktif di kelas ini")

    st = get_pengaturan(db)
    nama_aplikasi = st["nama_aplikasi"]
    now = _now_wib()

    buf = BytesIO()
    # A4 LANDSCAPE: banyak kolom tanggal (wajib landscape(A4), bukan
    # orientation= — kalau tidak tabel > lebar halaman → terpotong)
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                             topMargin=14 * mm, bottomMargin=14 * mm,
                             leftMargin=10 * mm, rightMargin=10 * mm,
                             title=f"Rekap Absensi Kelas {kelas.nama_kelas}")

    s_judul = ParagraphStyle("judul", fontName="Helvetica-Bold", fontSize=15,
                             textColor=colors.HexColor("#0F766E"), spaceAfter=2)
    s_sub = ParagraphStyle("sub", fontName="Helvetica-Bold", fontSize=11,
                           spaceAfter=10)
    s_sig = ParagraphStyle("sig", fontName="Helvetica", fontSize=8,
                           textColor=colors.HexColor("#555555"), spaceBefore=2)

    story = []
    story.append(Paragraph(nama_aplikasi, s_judul))
    story.append(Paragraph(
        f"{'Ringkasan ' if ringkasan else ''}Rekap Absensi Kelas {kelas.nama_kelas} — "
        f"{dari.strftime('%d/%m/%Y')} s.d. {sampai.strftime('%d/%m/%Y')}",
        s_sub))

    # Ringkasan semester cukup portrait dan jauh lebih hemat kertas.
    if ringkasan:
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                topMargin=14 * mm, bottomMargin=14 * mm,
                                leftMargin=14 * mm, rightMargin=14 * mm,
                                title=f"Ringkasan Absensi Kelas {kelas.nama_kelas}")
        col_widths = [18 * mm, 62 * mm, 18 * mm, 10 * mm, 10 * mm,
                      10 * mm, 10 * mm, 16 * mm, 14 * mm]
        font_size = 8
    else:
        # Matrix semester memakai landscape karena banyak kolom tanggal.
        n_date = len(headers) - 9
        avail_w = 277 * mm
        col_fixed = (18 * mm + 40 * mm + 14 * mm
                     + 4 * 9 * mm + 14 * mm + 12 * mm)
        date_w = max(7 * mm, (avail_w - col_fixed) / max(n_date, 1))
        col_widths = ([18 * mm, 40 * mm, 14 * mm] + [date_w] * n_date
                      + [9 * mm] * 4 + [14 * mm, 12 * mm])
        font_size = 8 if n_date <= 15 else (7 if n_date <= 25 else 6)

    data = [headers] + rows
    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F766E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F1F5F9")]),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Dibuat oleh: {nama_aplikasi}", s_sig))
    story.append(Paragraph(
        f"Dicetak: {now.strftime('%d/%m/%Y %H:%M')} WIB — "
        f"{len(rows)} murid", s_sig))

    doc.build(story)
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition":
                 f'inline; filename="cetak-absen-kelas-{kelas.nama_kelas}.pdf"'})


# ══════════════════════════════════════════════════════════════════════
# Dashboard Absensi — 3 endpoint ringkasan untuk kartu dashboard web.
# Konsisten dengan Cetak Absen: status final per tanggal, prioritas alpa>sakit>izin>hadir.
# ══════════════════════════════════════════════════════════════════════

# Daftar status yang dipakai (sumber kebenaran di model Absensi.status)
_STATUS_HADIR = "hadir"
_STATUS_IZIN = "izin"
_STATUS_SAKIT = "sakit"
_STATUS_ALPA = "alpa"
_PRIORITAS = ["alpa", "sakit", "izin", "hadir"]  # tertinggi ke terendah


def _final_status_per_hari(db: Session, dari: date, sampai: date,
                           kelas_id: int | None = None) -> dict[int, dict[date, str]]:
    """Hitung status FINAL per (murid_id, tanggal) untuk rentang tertentu.

    Menggabungkan semua sesi (masuk/pulang) dengan prioritas non-hadir > hadir,
    sehingga "hadir + pulang = izin" dihitung sebagai izin (lihat Cetak Absen).
    """
    q = db.query(Absensi.murid_id, Absensi.tanggal, Absensi.status).filter(
        Absensi.tanggal >= dari, Absensi.tanggal <= sampai)
    if kelas_id:
        q = q.join(Murid, Murid.id == Absensi.murid_id).filter(Murid.kelas_id == kelas_id)
    present: dict[int, dict] = defaultdict(dict)
    for mid, d, st in q.all():
        cur = present[mid].get(d)
        if cur is None or _PRIORITAS.index(st) < _PRIORITAS.index(cur):
            present[mid][d] = st
    return present


def _jumlah_hsia(st_map: dict[date, str]) -> dict[str, int]:
    return {st: sum(1 for v in st_map.values() if v == st)
            for st in (_STATUS_HADIR, _STATUS_IZIN, _STATUS_SAKIT, _STATUS_ALPA)}


@router.get("/rekap-per-kelas")
def rekap_per_kelas(dari: date | None = Query(None),
                    sampai: date | None = Query(None),
                    db: Session = Depends(get_tenant_db),
                    _: object = Depends(require_permission("absen.rekap", "absen.scan", "absen.manual", "absen.export", "absen.cetak"))):
    """Rekap H/I/S/A + % per kelas untuk rentang tanggal (default: 7 hari terakhir).

    Output diurutkan ASC by kelas_id; frontend pilih top/bottom N sendiri.
    """
    today = date.today()
    if sampai is None:
        sampai = today
    if dari is None:
        dari = sampai - timedelta(days=6)  # 7 hari inclusive
    # clamp bawah dari tahun ajaran (jangan terlalu jauh ke belakang)
    if (sampai - dari).days > 365:
        dari = sampai - timedelta(days=365)

    rows = db.query(Kelas).order_by(Kelas.id).all()
    present = _final_status_per_hari(db, dari, sampai)
    # Group by kelas
    murid_per_kelas = defaultdict(list)
    for m in db.query(Murid).filter(Murid.is_active.is_(True)).all():
        murid_per_kelas[m.kelas_id].append(m.id)

    out = []
    for k in rows:
        mids = murid_per_kelas.get(k.id, [])
        if not mids:
            continue
        agg = {_STATUS_HADIR: 0, _STATUS_IZIN: 0, _STATUS_SAKIT: 0, _STATUS_ALPA: 0}
        for mid in mids:
            j = _jumlah_hsia(present.get(mid, {}))
            for st in agg:
                agg[st] += j[st]
        total_records = sum(agg.values())
        pct = (agg[_STATUS_HADIR] / total_records * 100) if total_records else 0
        out.append({
            "kelas_id": k.id,
            "kelas_nama": k.nama_kelas,
            "hadir": agg[_STATUS_HADIR],
            "izin": agg[_STATUS_IZIN],
            "sakit": agg[_STATUS_SAKIT],
            "alpa": agg[_STATUS_ALPA],
            "total_records": total_records,
            "jumlah_murid": len(mids),
            "persen": round(pct, 1),
            "dari": dari.isoformat(),
            "sampai": sampai.isoformat(),
        })
    return {
        "dari": dari.isoformat(),
        "sampai": sampai.isoformat(),
        "items": out,
    }


@router.get("/rekap-bulan-ini")
def rekap_bulan_ini(bulan: date | None = Query(None, description="Tanggal dalam bulan target"),
                    db: Session = Depends(get_tenant_db),
                    _: object = Depends(require_permission("absen.rekap", "absen.scan", "absen.manual", "absen.export", "absen.cetak"))):
    """Ringkasan H/I/S/A untuk satu bulan kalender (default: bulan berjalan)."""
    today = date.today()
    target = bulan or today
    # Hari pertama & terakhir bulan target
    if target.month == 12:
        first = date(target.year, 12, 1)
        last = date(target.year + 1, 1, 1) - timedelta(days=1)
    else:
        first = date(target.year, target.month, 1)
        last = date(target.year, target.month + 1, 1) - timedelta(days=1)
    # cap di hari ini (jangan query ke masa depan)
    if last > today:
        last = today

    present = _final_status_per_hari(db, first, last)
    agg = {_STATUS_HADIR: 0, _STATUS_IZIN: 0, _STATUS_SAKIT: 0, _STATUS_ALPA: 0}
    for st_map in present.values():
        j = _jumlah_hsia(st_map)
        for st in agg:
            agg[st] += j[st]
    total = sum(agg.values())
    pct = (agg[_STATUS_HADIR] / total * 100) if total else 0
    return {
        "bulan": target.strftime("%Y-%m"),
        "label": target.strftime("%B %Y"),
        "dari": first.isoformat(),
        "sampai": last.isoformat(),
        "hadir": agg[_STATUS_HADIR],
        "izin": agg[_STATUS_IZIN],
        "sakit": agg[_STATUS_SAKIT],
        "alpa": agg[_STATUS_ALPA],
        "total": total,
        "persen": round(pct, 1),
    }


@router.get("/top-alpha")
def top_alpha(bulan: date | None = Query(None, description="Tanggal dalam bulan target"),
              limit: int = Query(5, ge=1, le=50),
              db: Session = Depends(get_tenant_db),
              _: object = Depends(require_permission("absen.rekap", "absen.scan", "absen.manual", "absen.export", "absen.cetak"))):
    """Top-N murid dengan Alpha terbanyak untuk satu bulan (default: bulan berjalan).

    Hanya tampilkan murid dengan alpa > 0 (skip yang 0).
    """
    today = date.today()
    target = bulan or today
    if target.month == 12:
        first = date(target.year, 12, 1)
        last = date(target.year + 1, 1, 1) - timedelta(days=1)
    else:
        first = date(target.year, target.month, 1)
        last = date(target.year, target.month + 1, 1) - timedelta(days=1)
    if last > today:
        last = today

    present = _final_status_per_hari(db, first, last)
    # Hitung alpa per murid; skip 0
    candidates = []
    for mid, st_map in present.items():
        alpa_count = sum(1 for v in st_map.values() if v == _STATUS_ALPA)
        if alpa_count <= 0:
            continue
        candidates.append((mid, alpa_count))
    # Sort descending; ambil top N
    candidates.sort(key=lambda x: (-x[1], x[0]))
    candidates = candidates[:limit]

    # Hydrate data murid + kelas
    mids = [c[0] for c in candidates]
    murid_map = {m.id: m for m in db.query(Murid).filter(Murid.id.in_(mids)).all()} if mids else {}
    kelas_map = {k.id: k for k in db.query(Kelas).filter(Kelas.id.in_({m.kelas_id for m in murid_map.values()})).all()} if murid_map else {}
    out = []
    for mid, alpa_count in candidates:
        m = murid_map.get(mid)
        if not m:
            continue
        k = kelas_map.get(m.kelas_id)
        out.append({
            "murid_id": mid,
            "nisn": m.nisn,
            "nama": m.nama,
            "kelas_id": m.kelas_id,
            "kelas_nama": k.nama_kelas if k else "",
            "alpa": alpa_count,
        })
    return {
        "bulan": target.strftime("%Y-%m"),
        "label": target.strftime("%B %Y"),
        "items": out,
    }
