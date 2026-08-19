"""Super admin: kelola tenant (onboarding madrasah anyar)"""
import json
import os
import re
import subprocess
import tarfile
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import (APIRouter, Depends, File, HTTPException, Response,
                     UploadFile, status)
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..backup import BACKUP_DIR, DATA_DIR, backup_tenant_db, run_backup
from ..config import settings
from ..db import GlobalSession, global_engine, provision_tenant_db, tenant_session_factory
from ..deps import require_roles
from ..models import (Absensi, AuditLog, BackupLog, BackupSetting,
                      GlobalSetting, Guru, Kelas, Murid, Plan, TahunAjaran,
                      Tenant)
from ..schemas import (BackupConfigRequest, DashboardOut, HariAbsen,
                       LanggananAlert, LoginTerakhir, TenantAdminCreate,
                       TenantAdminReset, TenantCreate, TenantDeleteRequest,
                       TenantDetailOut, TenantOut, TenantUpdate)
from ..security import hash_password

router = APIRouter(prefix="/api/super", tags=["superadmin"])

WIB = ZoneInfo("Asia/Jakarta")


def _log(gs: Session, user: dict, aksi: str, rincian: str = "",
         tenant: str = "") -> None:
    """Catet jejak aksi sensitif superadmin (audit trail)."""
    gs.add(AuditLog(user=user.get("username", "-"), aksi=aksi,
                    rincian=rincian[:300], tenant=tenant))
    gs.commit()


def _get_setting(gs: Session) -> GlobalSetting:
    g = gs.get(GlobalSetting, 1)
    if not g:
        g = GlobalSetting(id=1, nama_aplikasi="Aplikasi Madrasah",
                          maintenance=False)
        gs.add(g)
        gs.commit()
        gs.refresh(g)
    return g


def get_global_db():
    with GlobalSession() as s:
        yield s


def _counts(kode: str) -> tuple[int, int]:
    with tenant_session_factory(kode)() as s:
        return s.query(Guru).count(), s.query(Murid).count()


@router.get("/tenants", response_model=list[TenantOut])
def list_tenants(_: dict = Depends(require_roles("super_admin")),
                 gs: Session = Depends(get_global_db)):
    out = []
    for t in gs.query(Tenant).order_by(Tenant.created_at.desc()).all():
        jg, jm = _counts(t.kode)
        out.append(TenantOut.model_validate(t).model_copy(update={"jumlah_guru": jg, "jumlah_murid": jm}))
    return out


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(data: TenantCreate,
                  user: dict = Depends(require_roles("super_admin")),
                  gs: Session = Depends(get_global_db)):
    """Gawe madrasah anyar + provision database tenant langsung."""
    if gs.query(Tenant).filter_by(kode=data.kode).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Kode madrasah sudah dipakai")
    if data.subdomain and gs.query(Tenant).filter_by(subdomain=data.subdomain).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Subdomain sudah dipakai")

    # max_murid default saka plan (yen ora diisi manual)
    max_murid = data.max_murid
    if max_murid is None and data.plan:
        plan = gs.query(Plan).filter_by(nama=data.plan).first()
        if plan:
            max_murid = plan.max_murid

    t = Tenant(kode=data.kode, nama=data.nama, subdomain=data.subdomain,
               plan=data.plan, max_murid=max_murid,
               masa_langganan_hingga=data.masa_langganan_hingga)
    gs.add(t)
    gs.commit()
    gs.refresh(t)

    provision_tenant_db(t.kode)  # tabel tenant digawe

    # Seed taun ajaran default (data anyar langsung nduwe basis taun)
    with tenant_session_factory(t.kode)() as s:
        if s.query(TahunAjaran).count() == 0:
            s.add(TahunAjaran(nama="2025/2026",
                              tanggal_mulai=date(2025, 7, 1),
                              tanggal_selesai=date(2026, 6, 30),
                              is_active=True))
            s.commit()

    _log(gs, user, "tambah_tenant", f"Gawe {t.nama} ({t.kode}), plan={t.plan}", t.kode)
    return TenantOut.model_validate(t).model_copy(update={"jumlah_guru": 0, "jumlah_murid": 0})


def _tenant_stats(kode: str, tgl: date) -> tuple[int, int, int, int]:
    with tenant_session_factory(kode)() as s:
        guru = s.query(Guru).count()
        murid = s.query(Murid).count()
        kelas = s.query(Kelas).count()
        absen = s.query(Absensi).filter(Absensi.tanggal == tgl).count()
        return guru, murid, kelas, absen


def _tenant_aktivitas(kode: str, bulan_awal: date) -> dict:
    """Metrik aktivitas tenant — 2 query ringan:
    - absen bulan ini (COUNT)
    - tanggal absen terakhir (MAX) + total murid aktif
    """
    try:
        with tenant_session_factory(kode)() as s:
            absen_bulan = s.query(Absensi).filter(
                Absensi.tanggal >= bulan_awal).count()
            last = s.query(Absensi.tanggal).order_by(
                Absensi.tanggal.desc()).first()
            murid_aktif = s.query(Murid).filter(
                Murid.is_active.is_(True)).count()
            return {
                "absen_bulan_ini": absen_bulan,
                "absen_terakhir": last[0].isoformat() if last else None,
                "murid_aktif": murid_aktif,
            }
    except Exception:
        # DB tenant tidak bisa dibuka (korup/hapus) — jangan gagalkan halaman
        return {"absen_bulan_ini": 0, "absen_terakhir": None, "murid_aktif": 0}


@router.get("/tenant-aktivitas")
def tenant_aktivitas(_: dict = Depends(require_roles("super_admin")),
                     gs: Session = Depends(get_global_db)):
    """Aktivitas semua tenant untuk superadmin.

    Per tenant: last_active_at (login heartbeat) + absen bulan ini +
    tanggal absen terakhir + murid aktif + status aktivitas (aktif/
    jarang/tidak aktif) berdasarkan ambang 14 hari.
    """
    tenants = gs.query(Tenant).order_by(Tenant.nama).all()
    now = datetime.now(WIB)
    bulan_awal = now.date().replace(day=1)
    AMBANG = 14  # hari — >14 hari non-aktif = 'tidak aktif'

    items = []
    for t in tenants:
        st = _tenant_aktivitas(t.kode, bulan_awal)
        # Gabung heartbeat + absensi (paling baru)
        last = st["absen_terakhir"]
        last_active = None
        if t.last_active_at:
            last_active = t.last_active_at.strftime("%d/%m/%Y %H:%M")
            last_active_dt = t.last_active_at.replace(tzinfo=None)
        elif last:
            last_active = last
            last_active_dt = datetime.strptime(last, "%Y-%m-%d")
        else:
            last_active_dt = None

        if last_active_dt:
            sisa = (now.replace(tzinfo=None) - last_active_dt).days
            if sisa <= 14:
                status = "aktif"
            elif sisa <= 30:
                status = "jarang"
            else:
                status = "tidak_aktif"
        else:
            status = "tidak_aktif"  # belum pernah aktivitas

        items.append({
            "id": t.id,
            "kode": t.kode,
            "nama": t.nama,
            "status_tenant": t.status,
            "plan": t.plan,
            "last_active_at": last_active,
            "absen_bulan_ini": st["absen_bulan_ini"],
            "absen_terakhir": last,
            "murid_aktif": st["murid_aktif"],
            "status_aktivitas": status,
            "created_at": t.created_at.strftime("%d/%m/%Y") if t.created_at else "-",
        })

    # Statistik ringkas
    aktif = sum(1 for i in items if i["status_aktivitas"] == "aktif")
    jarang = sum(1 for i in items if i["status_aktivitas"] == "jarang")
    tidak = sum(1 for i in items if i["status_aktivitas"] == "tidak_aktif")

    return {
        "items": items,
        "ringkas": {"aktif": aktif, "jarang": jarang, "tidak_aktif": tidak,
                    "total": len(items)},
        "ambang": AMBANG,
    }


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(_: dict = Depends(require_roles("super_admin")),
              gs: Session = Depends(get_global_db)):
    """Ringkesan platform + peringatan langganan (kadaluwarsa/kritis/waspada/info)."""
    tenants = gs.query(Tenant).order_by(Tenant.created_at).all()
    tgl = datetime.now(WIB).date()

    tenant_total = len(tenants)
    tenant_aktif = sum(1 for t in tenants if t.status == "active")
    tenant_suspended = sum(1 for t in tenants if t.status == "suspended")
    guru_total = murid_total = kelas_total = absen_hari_ini = 0
    for t in tenants:
        g, m, k, a = _tenant_stats(t.kode, tgl)
        guru_total += g
        murid_total += m
        kelas_total += k
        absen_hari_ini += a

    alerts: list[LanggananAlert] = []
    for t in tenants:
        if t.masa_langganan_hingga is None:
            continue  # tanpa batas — aman
        sisa = (t.masa_langganan_hingga - tgl).days
        if sisa < 0:
            tingkat = "kadaluwarsa"
        elif sisa <= 3:
            tingkat = "kritis"
        elif sisa <= 7:
            tingkat = "waspada"
        elif sisa <= 30:
            tingkat = "info"
        else:
            continue
        alerts.append(LanggananAlert(
            tenant_id=t.id, kode=t.kode, nama=t.nama, status=t.status,
            plan=t.plan, masa_langganan_hingga=t.masa_langganan_hingga,
            sisa_hari=sisa, tingkat=tingkat))
    alerts.sort(key=lambda a: (a.sisa_hari is None, a.sisa_hari))

    return DashboardOut(
        tenant_total=tenant_total, tenant_aktif=tenant_aktif,
        tenant_suspended=tenant_suspended, murid_total=murid_total,
        guru_total=guru_total, kelas_total=kelas_total,
        absen_hari_ini=absen_hari_ini, alert_langganan=alerts)


@router.post("/tenants/{tenant_id}/reset-password")
def reset_tenant_password(tenant_id: int, data: TenantAdminReset,
                          user: dict = Depends(require_roles("super_admin")),
                          gs: Session = Depends(get_global_db)):
    """Reset password akun (admin/guru) ing tenant — kanggo lali password."""
    t = gs.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    with tenant_session_factory(t.kode)() as s:
        g = s.query(Guru).filter(Guru.username == data.username).first()
        if not g:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                f"Akun '{data.username}' tidak ditemukan")
        g.password_hash = hash_password(data.password)
        s.commit()
        nama = g.nama
    _log(gs, user, "reset_password", f"Reset password {data.username} ({t.nama})", t.kode)
    return {"ok": True, "kode": t.kode, "nama": nama, "username": data.username}


@router.get("/tenants/{tenant_id}/backup")
def backup_tenant(tenant_id: int,
                  _: dict = Depends(require_roles("super_admin")),
                  gs: Session = Depends(get_global_db)):
    """Backup data tenant (kelas, guru, murid, absensi) minangka file JSON."""
    t = gs.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    with tenant_session_factory(t.kode)() as s:
        payload = {
            "format": "madrasah-backup-v1",
            "dibuat": datetime.now(WIB).isoformat(),
            "kode": t.kode,
            "nama": t.nama,
            "plan": t.plan,
            "kelas": [{"id": k.id, "nama_kelas": k.nama_kelas}
                      for k in s.query(Kelas).order_by(Kelas.id).all()],
            "guru": [{"id": g.id, "nama": g.nama, "username": g.username,
                      "password_hash": g.password_hash, "role": g.role,
                      "is_active": g.is_active}
                     for g in s.query(Guru).order_by(Guru.id).all()],
            "murid": [{"id": m.id, "nisn": m.nisn, "nama": m.nama,
                       "kelas_id": m.kelas_id, "nama_ortu": m.nama_ortu,
                       "telepon": m.telepon, "qr_uuid": m.qr_uuid,
                       "is_active": m.is_active}
                      for m in s.query(Murid).order_by(Murid.id).all()],
            "absensi": [{"id": a.id, "murid_id": a.murid_id, "sesi": a.sesi,
                         "tanggal": a.tanggal.isoformat(),
                         "waktu": a.waktu.isoformat(), "status": a.status,
                         "guru_id": a.guru_id}
                        for a in s.query(Absensi).order_by(Absensi.id).all()],
        }
    fname = f"backup-{t.kode}-{datetime.now(WIB):%Y%m%d-%H%M}.json"
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/tenants/{tenant_id}/restore")
def restore_tenant(tenant_id: int,
                   file: UploadFile = File(...),
                   force: bool = False,
                   user: dict = Depends(require_roles("super_admin")),
                   gs: Session = Depends(get_global_db)):
    """Restore data saka file backup. Yen tenant wis ana data, butuh force=true."""
    t = gs.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    raw = file.file.read()
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "File bukan backup yang valid (JSON rusak)")
    if data.get("format") != "madrasah-backup-v1":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Format backup tidak dikenali")

    with tenant_session_factory(t.kode)() as s:
        if s.query(Murid).count() or s.query(Guru).count():
            if not force:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Madrasah sudah punya data — kirim ulang dengan force=true "
                    "untuk mengganti seluruh data")
            s.query(Absensi).delete()
            s.query(Murid).delete()
            s.query(Guru).delete()
            s.query(Kelas).delete()
            s.flush()

        # peta id lawas -> anyar (kelas & murid & guru)
        id_kelas = {}
        for k in data.get("kelas", []):
            nk = Kelas(nama_kelas=k["nama_kelas"])
            s.add(nk)
            s.flush()
            id_kelas[k["id"]] = nk.id
        id_guru = {}
        for g in data.get("guru", []):
            ng = Guru(nama=g["nama"], username=g["username"],
                      password_hash=g["password_hash"], role=g["role"],
                      is_active=bool(g.get("is_active", True)))
            s.add(ng)
            s.flush()
            id_guru[g["id"]] = ng.id
        id_murid = {}
        for m in data.get("murid", []):
            nm = Murid(nisn=m.get("nisn") or m.get("nis"), nama=m["nama"],
                       kelas_id=id_kelas.get(m["kelas_id"]),
                       nama_ortu=m.get("nama_ortu"),
                       telepon=m.get("telepon") or m.get("wa_ortu"),
                       qr_uuid=m.get("qr_uuid"), is_active=bool(m.get("is_active", True)))
            s.add(nm)
            s.flush()
            id_murid[m["id"]] = nm.id
        for a in data.get("absensi", []):
            s.add(Absensi(
                murid_id=id_murid.get(a["murid_id"]),
                sesi=a.get("sesi", "masuk"),
                tanggal=date.fromisoformat(a["tanggal"]),
                waktu=datetime.fromisoformat(a["waktu"]),
                status=a.get("status", "hadir"),
                guru_id=id_guru.get(a.get("guru_id")),
            ))
        s.commit()
        n_kelas = len(data.get("kelas", []))
        n_guru = len(data.get("guru", []))
        n_murid = len(data.get("murid", []))
        n_abs = len(data.get("absensi", []))

    _log(gs, user, "restore_tenant",
         f"Restore {t.nama} ({t.kode}): {n_kelas} kelas, {n_guru} guru, "
         f"{n_murid} murid, {n_abs} absensi", t.kode)
    return {"ok": True, "kode": t.kode,
            "jumlah": {"kelas": n_kelas, "guru": n_guru,
                       "murid": n_murid, "absensi": n_abs}}


@router.get("/backup")
def backup_info(_: dict = Depends(require_roles("super_admin")),
                gs: Session = Depends(get_global_db)):
    """Setelan jadwal + riwayat backup."""
    st = gs.query(BackupSetting).first()
    if not st:
        st = BackupSetting(enabled=False, jam="02:00", retensi=14)
        gs.add(st)
        gs.commit()
    riwayat = [{"waktu": l.waktu.isoformat(), "jenis": l.jenis,
                "status": l.status, "ukuran": l.ukuran,
                "nama_file": l.nama_file, "pesan": l.pesan}
               for l in gs.query(BackupLog).order_by(BackupLog.waktu.desc())
                         .limit(20).all()]
    return {"config": {"enabled": st.enabled, "jam": st.jam,
                       "retensi": st.retensi}, "riwayat": riwayat}


@router.put("/backup/config")
def backup_config(data: BackupConfigRequest,
                  user: dict = Depends(require_roles("super_admin")),
                  gs: Session = Depends(get_global_db)):
    """Simpen setelan jadwal backup rutin."""
    st = gs.query(BackupSetting).first()
    if not st:
        st = BackupSetting()
    st.enabled = data.enabled
    st.jam = data.jam
    st.retensi = data.retensi
    gs.add(st)
    gs.commit()
    _log(gs, user, "ubah_backup_config",
         f"enabled={data.enabled}, jam={data.jam}, retensi={data.retensi}")
    return {"ok": True, "config": {"enabled": st.enabled, "jam": st.jam,
                                   "retensi": st.retensi}}


@router.post("/backup/run")
def backup_run(user: dict = Depends(require_roles("super_admin")),
               gs: Session = Depends(get_global_db)):
    """Backup langsung (manual) — kabeh DB + .env -> arsip."""
    st = gs.query(BackupSetting).first()
    retensi = st.retensi if st else 14
    res = run_backup("manual", retensi)
    _log(gs, user, "backup_manual", f"nama={res.get('nama')}, ok={res.get('ok')}")
    return res


def _safe_backup_path(nama: str) -> Path:
    """Validasi nama file backup — nolak path traversal."""
    if not re.fullmatch(r"[\w.\-]+\.tar\.gz", nama):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nama file tidak valid")
    p = BACKUP_DIR / nama
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File backup tidak ditemukan")
    return p


@router.get("/backup/files")
def backup_files(_: dict = Depends(require_roles("super_admin"))):
    """Daftar arsip backup (madrasah-*.tar.gz) sing ana ing server."""
    out = []
    for f in sorted(BACKUP_DIR.glob("madrasah-*.tar.gz"), reverse=True):
        st = f.stat()
        out.append({"nama": f.name, "ukuran": st.st_size,
                    "tanggal": datetime.fromtimestamp(st.st_mtime, WIB)
                    .isoformat(timespec="minutes")})
    return out


@router.get("/backup/files/{nama}")
def backup_download(nama: str,
                    _: dict = Depends(require_roles("super_admin"))):
    """Download arsip backup."""
    path = _safe_backup_path(nama)
    return FileResponse(path, media_type="application/gzip", filename=nama)


@router.delete("/backup/files/{nama}")
def backup_file_delete(nama: str,
                       user: dict = Depends(require_roles("super_admin")),
                       gs: Session = Depends(get_global_db)):
    """Hapus arsip backup — aman: validasi path traversal + audit log.

    Proteksi berlapis:
    1. `_safe_backup_path` — regex `[\\w.\\-]+\\.tar\\.gz` + cek file ada di BACKUP_DIR
    2. Hanya file di BACKUP_DIR (bukan subfolder, bukan symlink luar)
    3. Audit log tercatat siapa + file mana + ukuran
    """
    path = _safe_backup_path(nama)
    if not path.is_file() or path.is_symlink():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "File backup tidak valid untuk dihapus")
    ukuran = path.stat().st_size
    path.unlink(missing_ok=True)

    _log(gs, user, "hapus_backup",
         f"Arsip {nama} dihapus ({ukuran}B)")
    return {"ok": True, "nama": nama, "ukuran": ukuran}


@router.post("/backup/upload")
def backup_upload(file: UploadFile = File(...),
                  user: dict = Depends(require_roles("super_admin")),
                  gs: Session = Depends(get_global_db)):
    """Upload arsip backup .tar.gz dari komputer lain.

    Validasi: magic bytes gzip + ukuran maks 100MB. Nama file disanitasi
    (timestamp server, TIDAK trust filename user) — aman untuk restore.
    """
    content = file.file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "File backup maksimal 100MB")
    if content[:2] != b"\x1f\x8b":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Bukan file .tar.gz valid (magic bytes gzip tidak cocok)")

    ts = datetime.now(WIB).strftime("%Y%m%d-%H%M")
    nama = f"madrasah-{ts}-upload.tar.gz"
    # Hindari bentrok kalau upload 2x dalam 1 menit
    n = 1
    while (BACKUP_DIR / nama).exists():
        nama = f"madrasah-{ts}-upload-{n}.tar.gz"
        n += 1

    dest = BACKUP_DIR / nama
    dest.write_bytes(content)

    _log(gs, user, "upload_backup",
         f"Upload arsip dari komputer: {nama} ({len(content)}B)")
    return {"ok": True, "nama_file": nama, "ukuran": len(content)}


@router.post("/backup/restore")
def backup_restore(data: dict,
                   user: dict = Depends(require_roles("super_admin")),
                   gs: Session = Depends(get_global_db)):
    """Restore platform saka arsip backup.

    Aman: (1) backup kondisi saiki dhisik (pre-restore), (2) ngganti
    global.db + tenant DB + .env saka arsip, (3) restart service.
    """
    nama = str(data.get("nama_file", ""))
    path = _safe_backup_path(nama)

    # 1. Safety: backup kondisi saiki dhisik
    run_backup("pre-restore", 14)

    # 2. Extract + replace
    restored: list[str] = []
    with tarfile.open(path, "r:gz") as tar:
        for m in tar.getmembers():
            base = Path(m.name).name
            if base == "global.db":
                dst = DATA_DIR / "global.db"
            elif base.endswith(".db"):
                dst = DATA_DIR / "tenants" / base
            elif base.startswith("env-"):
                dst = Path(__file__).resolve().parent.parent / ".env"
            else:
                continue
            if m.isfile():
                src = tar.extractfile(m)
                if src is None:
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                with open(dst, "wb") as out:
                    out.write(src.read())
                # WAL mode: file -wal/-shm lawas kudu dibusak — yen ora,
                # SQLite nyoba "recover" saka WAL lawas → korupsi
                for suffix in ("-wal", "-shm"):
                    stale = Path(str(dst) + suffix)
                    stale.unlink(missing_ok=True)
                restored.append(dst.name)

    # 3. Restart service (delayed, supaya response kelar dhisik)
    try:
        subprocess.Popen(
            ["setsid", "bash", "-c",
             "sleep 2 && sudo systemctl restart madrasah-backend"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
    except Exception:  # noqa: BLE001
        pass

    _log(gs, user, "restore_backup",
         f"Restore saka {nama}: {len(restored)} file ({', '.join(restored[:5])})")
    return {"ok": True, "nama": nama,
            "restored": restored,
            "pesan": "Data diganti saka arsip — service restart otomatis (±5 dtk). "
                     "Koneksi bakal kepotong sedhela."}


@router.get("/alerts/status")
def alerts_status(_: dict = Depends(require_roles("super_admin"))):
    """Status konfigurasi alert Telegram (disetel? ambang? kapan cek pungkasan)."""
    from ..alerts import status as alert_status
    return alert_status()


@router.get("/server-status")
def server_status(_: dict = Depends(require_roles("super_admin"))):
    """Status server: RAM, disk, swap, uptime, load, ukuran DB, backup pungkasan."""
    from ..alerts import server_status as ss
    return ss()


@router.post("/alerts/check")
def alerts_check(_: dict = Depends(require_roles("super_admin"))):
    """Jalankan cek saiki — kirim mung yen ana masalah anyar/pulih."""
    from ..alerts import run_alert_check
    return run_alert_check()


@router.post("/alerts/test")
def alerts_test(_: dict = Depends(require_roles("super_admin"))):
    """Kirim pesen uji coba (memastikan bot + chat_id bener)."""
    from ..alerts import send_telegram
    return send_telegram("✅ *Uji notifikasi Madrasah Platform* — "
                         "alert superadmin aktif lan bot berfungsi.")


@router.delete("/tenants/{tenant_id}")
def tenant_delete(tenant_id: int, body: TenantDeleteRequest,
                  user: dict = Depends(require_roles("super_admin")),
                  gs: Session = Depends(get_global_db)):
    """Hapus tenant PERMANEN — 2 lapis proteksi backend:
    L4: kode konfirmasi kudu cocok persis
    L5: backup wajib sadurunge hapus (gagal -> delete dibatalake)
    """
    t = gs.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Madrasah tidak ditemukan")
    if body.kode != t.kode:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Kode konfirmasi salah — penghapusan dibatalkan")

    # L5: backup wajib
    backup_nama = ""
    try:
        dst = backup_tenant_db(t.kode)
        backup_nama = dst.name
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"Backup gagal ({e}) — penghapusan dibatalkan")

    # Hapus file DB tenant (+ WAL/SHM lawas) — PostgreSQL: DROP SCHEMA
    if settings.is_pg:
        from sqlalchemy import text
        with global_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{t.kode}" CASCADE'))
    else:
        db_file = DATA_DIR / "tenants" / f"{t.kode}.db"
        db_file.unlink(missing_ok=True)
        Path(str(db_file) + "-wal").unlink(missing_ok=True)
        Path(str(db_file) + "-shm").unlink(missing_ok=True)

    # Catet log delete (jejak recovery)
    gs.add(BackupLog(waktu=datetime.now(ZoneInfo("Asia/Jakarta")), jenis="delete",
                     status="ok", ukuran=0, nama_file=backup_nama,
                     pesan=f"Tenant {t.kode} ({t.nama}) dihapus — backup: {backup_nama}"))
    _log(gs, user, "hapus_tenant", f"Hapus {t.nama} ({t.kode}) — backup {backup_nama}",
         t.kode)
    gs.delete(t)
    gs.commit()
    return {"ok": True, "backup": backup_nama}


@router.get("/tenants/{tenant_id}/detail", response_model=TenantDetailOut)
def tenant_detail(tenant_id: int,
                  _: dict = Depends(require_roles("super_admin")),
                  gs: Session = Depends(get_global_db)):
    """Detail siji tenant: profil, statistik, absen 7 dina, login terakhir."""
    t = gs.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")

    tgl_now = datetime.now(WIB).date()
    start = tgl_now - timedelta(days=6)
    with tenant_session_factory(t.kode)() as s:
        jumlah_kelas = s.query(Kelas).count()
        jumlah_guru = s.query(Guru).count()
        jumlah_admin = s.query(Guru).filter(Guru.role == "admin").count()
        jumlah_murid = s.query(Murid).count()
        murid_aktif = s.query(Murid).filter(Murid.is_active.is_(True)).count()
        absen_total = s.query(Absensi).count()

        rows = (s.query(Absensi.tanggal, Absensi.status, func.count())
                .filter(Absensi.tanggal >= start)
                .group_by(Absensi.tanggal, Absensi.status).all())
        per_day: dict[date, dict[str, int]] = {
            start + timedelta(days=i): {"hadir": 0, "izin": 0, "sakit": 0, "alpa": 0}
            for i in range(7)
        }
        for tgl, st, n in rows:
            if tgl in per_day and st in per_day[tgl]:
                per_day[tgl][st] = n
        absen_7_hari = [
            HariAbsen(tanggal=d.isoformat(), **per_day[d])
            for d in sorted(per_day)
        ]

        logins = [LoginTerakhir(
            nama=g.nama, username=g.username, role=g.role,
            last_login=g.last_login.isoformat() if g.last_login else None)
            for g in s.query(Guru).filter(Guru.last_login.isnot(None))
                      .order_by(Guru.last_login.desc()).limit(5).all()]

    return TenantDetailOut(
        id=t.id, kode=t.kode, nama=t.nama, status=t.status, plan=t.plan,
        max_murid=t.max_murid, masa_langganan_hingga=t.masa_langganan_hingga,
        dibuat=t.created_at, jumlah_kelas=jumlah_kelas, jumlah_guru=jumlah_guru,
        jumlah_admin=jumlah_admin, jumlah_murid=jumlah_murid,
        murid_aktif=murid_aktif, absen_total=absen_total,
        absen_7_hari=absen_7_hari, login_terakhir=logins)


@router.patch("/tenants/{tenant_id}", response_model=TenantOut)
def update_tenant(tenant_id: int, data: TenantUpdate,
                  user: dict = Depends(require_roles("super_admin")),
                  gs: Session = Depends(get_global_db)):
    t = gs.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    if data.status is not None:
        t.status = data.status
    if data.plan is not None:
        t.plan = data.plan
    if data.max_murid is not None:
        t.max_murid = data.max_murid
    if data.hapus_masa_langganan:
        t.masa_langganan_hingga = None
    elif data.masa_langganan_hingga is not None:
        t.masa_langganan_hingga = data.masa_langganan_hingga
    gs.commit()
    gs.refresh(t)
    jg, jm = _counts(t.kode)
    _log(gs, user, "ubah_tenant",
         f"status={t.status}, plan={t.plan}, max_murid={t.max_murid}, "
         f"langganan={t.masa_langganan_hingga}", t.kode)
    return TenantOut.model_validate(t).model_copy(update={"jumlah_guru": jg, "jumlah_murid": jm})


@router.post("/tenants/{tenant_id}/admin", status_code=status.HTTP_201_CREATED)
def create_tenant_admin(tenant_id: int, data: TenantAdminCreate,
                        user: dict = Depends(require_roles("super_admin")),
                        gs: Session = Depends(get_global_db)):
    """Super admin gawe akun ADMIN ing tenant (madrasah)."""
    t = gs.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    with tenant_session_factory(t.kode)() as s:
        if s.query(Guru).filter_by(username=data.username).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "Username sudah dipakai")
        s.add(Guru(nama=data.nama, username=data.username,
                   password_hash=hash_password(data.password), role="admin"))
        s.commit()
    _log(gs, user, "tambah_admin", f"Gawe admin {data.username} ({t.nama})", t.kode)
    return {"ok": True, "kode": t.kode, "nama": data.nama, "username": data.username,
            "role": "admin"}


def _admin_aktif_count(s: Session) -> int:
    return s.query(Guru).filter(Guru.role == "admin",
                                Guru.is_active.is_(True)).count()


@router.get("/tenants/{tenant_id}/admins")
def tenant_admins(tenant_id: int, semua: bool = False,
                  _: dict = Depends(require_roles("super_admin")),
                  gs: Session = Depends(get_global_db)):
    """Daftar akun (admin utawa kabeh guru) siji tenant."""
    t = gs.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    with tenant_session_factory(t.kode)() as s:
        q = s.query(Guru).order_by(Guru.role.desc(), Guru.nama)
        if not semua:
            q = q.filter(Guru.role == "admin")
        return [{"id": g.id, "nama": g.nama, "username": g.username,
                 "role": g.role, "is_active": g.is_active,
                 "last_login": g.last_login.isoformat() if g.last_login else None}
                for g in q.all()]


@router.patch("/tenants/{tenant_id}/admins/{guru_id}")
def tenant_admin_update(tenant_id: int, guru_id: int, data: dict,
                        user: dict = Depends(require_roles("super_admin")),
                        gs: Session = Depends(get_global_db)):
    """Ubah akun tenant: nama, role, is_active — karo proteksi admin pungkasan."""
    t = gs.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    with tenant_session_factory(t.kode)() as s:
        g = s.get(Guru, guru_id)
        if not g:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Akun tidak ditemukan")

        if data.get("nama") is not None:
            g.nama = str(data["nama"]).strip() or g.nama

        if data.get("role") is not None:
            role = str(data["role"])
            if role not in ("guru", "admin"):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Role tidak valid")
            if role == "guru" and g.role == "admin" and _admin_aktif_count(s) <= 1:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Minimal harus ada satu admin aktif — ubah role admin liya dhisik")
            g.role = role

        if data.get("is_active") is not None:
            v = bool(data["is_active"])
            if not v and g.role == "admin" and _admin_aktif_count(s) <= 1:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Minimal harus ada satu admin aktif — ora bisa nonaktifake admin pungkasan")
            g.is_active = v

        s.commit()
        s.refresh(g)
        out = {"id": g.id, "nama": g.nama, "username": g.username, "role": g.role,
               "is_active": g.is_active,
               "last_login": g.last_login.isoformat() if g.last_login else None}

    _log(gs, user, "ubah_admin",
         f"{data.get('nama') and 'nama' or ''} "
         f"{'role→' + str(data.get('role')) if data.get('role') else ''} "
         f"{'is_active→' + str(data.get('is_active')) if data.get('is_active') is not None else ''} "
         f"({g.username} @ {t.kode})".strip(), t.kode)
    return out


@router.delete("/tenants/{tenant_id}/admins/{guru_id}")
def tenant_admin_delete(tenant_id: int, guru_id: int,
                        user: dict = Depends(require_roles("super_admin")),
                        gs: Session = Depends(get_global_db)):
    """Hapus akun tenant — proteksi: admin pungkasan ora bisa dihapus."""
    t = gs.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    with tenant_session_factory(t.kode)() as s:
        g = s.get(Guru, guru_id)
        if not g:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Akun tidak ditemukan")
        if g.role == "admin" and _admin_aktif_count(s) <= 1:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Minimal harus ada satu admin aktif — ora bisa hapus admin pungkasan")
        username = g.username
        s.delete(g)
        s.commit()

    _log(gs, user, "hapus_admin", f"Hapus akun {username} ({t.kode})", t.kode)
    return {"ok": True, "username": username}


@router.delete("/tenants/{tenant_id}")
def suspend_tenant(tenant_id: int,
                   _: dict = Depends(require_roles("super_admin")),
                   gs: Session = Depends(get_global_db)):
    """Soft-suspend: data ora dibusak, login diblokir."""
    t = gs.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    t.status = "suspended"
    gs.commit()
    return {"ok": True, "kode": t.kode, "status": t.status}


# ── Setelan platform (branding + maintenance) ─────────────────────────────

@router.get("/settings")
def get_platform_settings(_: dict = Depends(require_roles("super_admin")),
                          gs: Session = Depends(get_global_db)):
    g = _get_setting(gs)
    return {"nama_aplikasi": g.nama_aplikasi,
            "maintenance": g.maintenance,
            "logo": g.logo is not None}


@router.put("/settings")
def put_platform_settings(data: dict,
                          user: dict = Depends(require_roles("super_admin")),
                          gs: Session = Depends(get_global_db)):
    g = _get_setting(gs)
    if data.get("nama_aplikasi") is not None:
        g.nama_aplikasi = str(data["nama_aplikasi"]).strip() or "Aplikasi Madrasah"
    if data.get("maintenance") is not None:
        g.maintenance = bool(data["maintenance"])
    gs.commit()
    _log(gs, user, "ubah_setting_platform",
         f"nama='{g.nama_aplikasi}', maintenance={g.maintenance}")
    return {"nama_aplikasi": g.nama_aplikasi,
            "maintenance": g.maintenance,
            "logo": g.logo is not None}


@router.post("/settings/logo")
def upload_logo(file: UploadFile = File(...),
                user: dict = Depends(require_roles("super_admin")),
                gs: Session = Depends(get_global_db)):
    """Upload logo platform (png/jpg/webp, maks 10MB).

    Validasi nganggo MAGIC BYTES (bukan content_type) — browser Android
    asring ngirim application/octet-stream nalika milih saka Photos/Drive,
    padahal isi-e PNG/JPG sing bener.
    """
    content = file.file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Logo maksimal 10MB")
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        fmt = "PNG"
    elif content[:3] == b"\xff\xd8\xff":
        fmt = "JPEG"
    elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        fmt = "WebP"
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Format logo: PNG/JPG/WebP")
    g = _get_setting(gs)
    g.logo = content
    gs.commit()
    _log(gs, user, "upload_logo", f"Logo diganti ({fmt}, {len(content)}B)")
    return {"ok": True, "ukuran": len(content)}


@router.delete("/settings/logo")
def delete_logo(user: dict = Depends(require_roles("super_admin")),
                gs: Session = Depends(get_global_db)):
    g = _get_setting(gs)
    g.logo = None
    gs.commit()
    _log(gs, user, "hapus_logo", "Logo platform dibusak")
    return {"ok": True}


@router.get("/settings/logo")
def get_logo(gs: Session = Depends(get_global_db)):
    """Logo platform (public — kanggo layar login)."""
    g = gs.get(GlobalSetting, 1)
    if not g or not g.logo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Logo belum diatur")
    return Response(content=g.logo, media_type="image/png")


@router.get("/branding")
def branding(gs: Session = Depends(get_global_db)):
    """Info branding public (nama + logo ana/ora) — kanggo layar login."""
    g = gs.get(GlobalSetting, 1)
    return {"nama": g.nama_aplikasi if g else "Aplikasi Madrasah",
            "logo": bool(g and g.logo)}


# ── Audit trail ───────────────────────────────────────────────────────────

@router.get("/audit")
def audit_logs(limit: int = 50, offset: int = 0,
               tanggal_dari: str | None = None,
               tanggal_sampai: str | None = None,
               _: dict = Depends(require_roles("super_admin")),
               gs: Session = Depends(get_global_db)):
    """Jejak aksi sensitif superadmin — paling anyar dhisik.

    Pagination offset + filter tanggal WIB (YYYY-MM-DD); waktu balik
    wis dikonversi menyang WIB (+7) kanggo tampilan.
    """
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    q = gs.query(AuditLog)
    if tanggal_dari or tanggal_sampai:
        try:
            tz = ZoneInfo("Asia/Jakarta")
            if tanggal_dari:
                start = datetime.combine(
                    date.fromisoformat(tanggal_dari), time.min, tzinfo=tz)
                q = q.filter(AuditLog.waktu >=
                             start.astimezone(UTC).replace(tzinfo=None))
            if tanggal_sampai:
                end = datetime.combine(
                    date.fromisoformat(tanggal_sampai) + timedelta(days=1),
                    time.min, tzinfo=tz)
                q = q.filter(AuditLog.waktu <
                             end.astimezone(UTC).replace(tzinfo=None))
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Format tanggal salah (YYYY-MM-DD)")
    total = q.count()
    rows = (q.order_by(AuditLog.waktu.desc())
            .offset(offset).limit(limit).all())

    def _wib(dt: datetime) -> str:
        return (dt + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M")

    return {"total": total,
            "items": [{"id": r.id, "waktu": _wib(r.waktu),
                       "user": r.user, "aksi": r.aksi,
                       "rincian": r.rincian, "tenant": r.tenant}
                      for r in rows]}


@router.get("/audit/tenant")
def audit_logs_tenant(limit: int = 50, offset: int = 0,
                      tanggal_dari: str | None = None,
                      tanggal_sampai: str | None = None,
                      user: dict = Depends(require_roles("admin", "super_admin")),
                      gs: Session = Depends(get_global_db)):
    """Audit trail untuk admin sekolah (Q4) — auto-filter by tenant.

    Admin sekolah hanya bisa melihat audit log milik tenant-nya sendiri.
    Superadmin bisa melihat semua tenant (tenant_kode = None).
    """
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    q = gs.query(AuditLog)
    # Filter by tenant
    if user.get("role") == "super_admin":
        # superadmin: optional filter via query param
        pass  # no filter
    elif user.get("tenant_kode"):
        q = q.filter(AuditLog.tenant == user["tenant_kode"])
    else:
        # admin tanpa tenant_kode (tidak seharusnya terjadi)
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Tenant tidak dikenali")

    if tanggal_dari or tanggal_sampai:
        try:
            tz = ZoneInfo("Asia/Jakarta")
            if tanggal_dari:
                start = datetime.combine(
                    date.fromisoformat(tanggal_dari), time.min, tzinfo=tz)
                q = q.filter(AuditLog.waktu >=
                             start.astimezone(UTC).replace(tzinfo=None))
            if tanggal_sampai:
                end = datetime.combine(
                    date.fromisoformat(tanggal_sampai) + timedelta(days=1),
                    time.min, tzinfo=tz)
                q = q.filter(AuditLog.waktu <
                             end.astimezone(UTC).replace(tzinfo=None))
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Format tanggal salah (YYYY-MM-DD)")
    total = q.count()
    rows = (q.order_by(AuditLog.waktu.desc())
            .offset(offset).limit(limit).all())

    def _wib(dt: datetime) -> str:
        return (dt + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M")

    return {"total": total,
            "items": [{"id": r.id, "waktu": _wib(r.waktu),
                       "user": r.user, "aksi": r.aksi,
                       "rincian": r.rincian, "tenant": r.tenant}
                      for r in rows]}


# ── Paket / Plan ──────────────────────────────────────────────────────────

def _plan_out(p: Plan) -> dict:
    return {"id": p.id, "nama": p.nama, "label": p.label,
            "max_murid": p.max_murid, "max_guru": p.max_guru,
            "fitur": [f.strip() for f in p.fitur.split(",") if f.strip()]}


@router.get("/plans")
def list_plans(_: dict = Depends(require_roles("super_admin")),
               gs: Session = Depends(get_global_db)):
    return [_plan_out(p) for p in gs.query(Plan).order_by(Plan.id).all()]


@router.post("/plans", status_code=status.HTTP_201_CREATED)
def create_plan(data: dict,
                user: dict = Depends(require_roles("super_admin")),
                gs: Session = Depends(get_global_db)):
    nama = str(data.get("nama", "")).strip().lower()
    if not nama:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nama plan wajib diisi")
    if gs.query(Plan).filter_by(nama=nama).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Plan sudah ada")
    p = Plan(nama=nama, label=str(data.get("label", "")).strip(),
             max_murid=data.get("max_murid"),
             max_guru=data.get("max_guru"),
             fitur=", ".join(str(f).strip() for f in data.get("fitur", []) if str(f).strip()))
    gs.add(p)
    gs.commit()
    gs.refresh(p)
    _log(gs, user, "tambah_plan", f"Plan '{nama}' digawe")
    return _plan_out(p)


@router.patch("/plans/{plan_id}")
def update_plan(plan_id: int, data: dict,
                user: dict = Depends(require_roles("super_admin")),
                gs: Session = Depends(get_global_db)):
    p = gs.get(Plan, plan_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan tidak ditemukan")
    if data.get("label") is not None:
        p.label = str(data["label"]).strip()
    if data.get("max_murid") is not None:
        p.max_murid = int(data["max_murid"])
    if data.get("max_guru") is not None:
        p.max_guru = int(data["max_guru"])
    if data.get("fitur") is not None:
        p.fitur = ", ".join(str(f).strip() for f in data["fitur"] if str(f).strip())
    gs.commit()
    _log(gs, user, "ubah_plan", f"Plan '{p.nama}' diperbarui")
    return _plan_out(p)


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: int,
                user: dict = Depends(require_roles("super_admin")),
                gs: Session = Depends(get_global_db)):
    p = gs.get(Plan, plan_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan tidak ditemukan")
    dipakai = gs.query(Tenant).filter_by(plan=p.nama).count()
    if dipakai:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Plan dipakai {dipakai} madrasah — ora bisa dihapus")
    gs.delete(p)
    gs.commit()
    _log(gs, user, "hapus_plan", f"Plan '{p.nama}' dibusak")
    return {"ok": True}
