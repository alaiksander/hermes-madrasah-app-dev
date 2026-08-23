"""Aplikasi Madrasah API — entry point.

Backend multi-tenant SaaS (per-tenant database):
- Global DB   : registry tenant + super admin
- Tenant DB   : data saben madrasah (guru, kelas, murid, absensi)
"""
import glob
import os
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .alerts import kirim_startup, run_alert_check
from .config import settings
from .backup import run_backup
from .db import GlobalSession, init_global_db, provision_tenant_db
from .models import BackupLog, BackupSetting
from .routers import (absensi, auth, bk, guru, guru_pengampu, jurnal, kelas,
                      mapel, murid, pengaturan, qr, roles, superadmin,
                      tahun_ajaran)

WIB = ZoneInfo("Asia/Jakarta")

_stop_scheduler = threading.Event()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _migrate_tenant_dbs() -> None:
    """Migrasi ringan kanggo tenant DB sing wis ana.

    - create_all (idempotent): gawe tabel anyar sing durung ana (pengaturan,
      tahun_ajaran)
    - ALTER TABLE ADD COLUMN: kolom anyar ing tabel sing wis ana (aman,
      cek PRAGMA dhisik)
    - Tahun Ajaran: sisipke taun default "2025/2026" yen durung ana, banjur
      kelas dibangun maneh (rebuild) supaya nduwe tahun_ajaran_id +
      unique (tahun_ajaran_id, nama_kelas).
    """
    for db_path in glob.glob(str(DATA_DIR / "tenants" / "*.db")):
        kode = os.path.basename(db_path)[:-3]
        try:
            provision_tenant_db(kode)  # tabel anyar (pengaturan, tahun_ajaran)
            con = sqlite3.connect(db_path)
            try:
                # Kolom telat_menit (fitur lama)
                cols = {r[1] for r in con.execute("PRAGMA table_info(absensi)")}
                if "telat_menit" not in cols:
                    con.execute("ALTER TABLE absensi ADD COLUMN telat_menit INTEGER")
                    con.commit()
                    print(f"[migrasi] +telat_menit -> {kode}")

                # Kolom mapel_id di bk_catatan (2026-08-20): tag mapel untuk
                # insiden yang terkait mapel tertentu (guru mapel scope).
                bkcols = {r[1] for r in con.execute("PRAGMA table_info(bk_catatan)")}
                if "mapel_id" not in bkcols:
                    con.execute("ALTER TABLE bk_catatan ADD COLUMN mapel_id INTEGER")
                    con.commit()
                    print(f"[migrasi] +mapel_id (bk_catatan) -> {kode}")
                    # Index untuk query by mapel
                    con.execute("CREATE INDEX IF NOT EXISTS ix_bk_catatan_mapel_id ON bk_catatan(mapel_id)")
                    con.commit()
                    print(f"[migrasi] +ix_bk_catatan_mapel_id -> {kode}")

                # NIS → NISN (2026-08-17): rename kolom murid.nis → murid.nisn,
                # isi ulang dummy 10 digit utk data lama (NISN opsional, NULL
                # aman utk banyak baris — unique constraint per-barisa).
                mcols = {r[1] for r in con.execute("PRAGMA table_info(murid)")}
                if "nis" in mcols and "nisn" not in mcols:
                    con.execute("ALTER TABLE murid RENAME COLUMN nis TO nisn")
                    # Dummy 10 digit: 2400000001 dst. — hanya utk nilai non-NULL
                    # yang bukan 10 digit (data asli NISN tetap dipertahankan).
                    con.execute("""
                        UPDATE murid SET nisn = printf('%010d', 2400000000 + id)
                        WHERE nisn IS NOT NULL
                          AND (length(nisn) != 10 OR nisn NOT GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]')
                    """)
                    con.commit()
                    print(f"[migrasi] murid.nis -> murid.nisn (dummy 10 digit) -> {kode}")

                # Rebuild tabel murid bila kolom nisn masih NOT NULL (RENAME
                # COLUMN mempertahankan constraint lama) atau tipe masih
                # VARCHAR(30) — NISN wajib nullable + VARCHAR(10).
                minfo = {r[1]: r for r in con.execute("PRAGMA table_info(murid)")}
                m_notnull = minfo.get("nisn", (None, None, None, 1))[3]
                m_type = (minfo.get("nisn") or (None, None, "VARCHAR(30)"))[2]
                if "nisn" in minfo and (m_notnull or m_type.upper() != "VARCHAR(10)"):
                    con.execute("ALTER TABLE murid RENAME TO murid_old")
                    con.execute("""
                        CREATE TABLE murid (
                            id INTEGER NOT NULL PRIMARY KEY,
                            nisn VARCHAR(10),
                            nama VARCHAR(100) NOT NULL,
                            kelas_id INTEGER NOT NULL,
                            qr_uuid VARCHAR(36) NOT NULL,
                            nama_ortu VARCHAR(100),
                            wa_ortu VARCHAR(20),
                            is_active BOOLEAN NOT NULL,
                            created_at DATETIME NOT NULL
                        )
                    """)
                    con.execute("""
                        INSERT INTO murid (id, nisn, nama, kelas_id, qr_uuid,
                                           nama_ortu, wa_ortu, is_active, created_at)
                        SELECT id, nisn, nama, kelas_id, qr_uuid,
                               nama_ortu, wa_ortu, is_active, created_at
                        FROM murid_old
                    """)
                    con.execute("DROP TABLE murid_old")
                    con.execute("CREATE UNIQUE INDEX ix_murid_nisn ON murid (nisn)")
                    con.execute("CREATE INDEX ix_murid_nama ON murid (nama)")
                    con.execute("CREATE INDEX ix_murid_kelas_id ON murid (kelas_id)")
                    con.execute("CREATE UNIQUE INDEX ix_murid_qr_uuid ON murid (qr_uuid)")
                    con.commit()
                    print(f"[migrasi] rebuild murid (nisn nullable) -> {kode}")
                elif "nis" in mcols and "nisn" in mcols:
                    # State aneh (keduanya ada): isi nisn dari nis kalau nisn
                    # masih kosong, lalu drop kolom nis.
                    con.execute("""
                        UPDATE murid SET nisn = printf('%010d', 2400000000 + id)
                        WHERE nisn IS NULL
                    """)
                    con.execute("ALTER TABLE murid DROP COLUMN nis")
                    con.commit()
                    print(f"[migrasi] cleanup nis+nin -> {kode}")

                # EMIS fields (2026-08-17): wa_ortu -> telepon + kolom data
                # EMIS (nik, TTL, JK, alamat, ayah/ibu). ADD COLUMN aman,
                # cek PRAGMA dhisik.
                mcols2 = {r[1] for r in con.execute("PRAGMA table_info(murid)")}
                if "wa_ortu" in mcols2 and "telepon" not in mcols2:
                    con.execute("ALTER TABLE murid RENAME COLUMN wa_ortu TO telepon")
                    con.commit()
                    print(f"[migrasi] murid.wa_ortu -> telepon -> {kode}")
                elif "wa_ortu" in mcols2 and "telepon" in mcols2:
                    con.execute("ALTER TABLE murid DROP COLUMN wa_ortu")
                    con.commit()
                    print(f"[migrasi] cleanup wa_ortu+telepon -> {kode}")
                for col, ddl in (
                    ("nik", "ALTER TABLE murid ADD COLUMN nik VARCHAR(16)"),
                    ("tempat_lahir", "ALTER TABLE murid ADD COLUMN tempat_lahir VARCHAR(60)"),
                    ("tanggal_lahir", "ALTER TABLE murid ADD COLUMN tanggal_lahir DATE"),
                    ("jenis_kelamin", "ALTER TABLE murid ADD COLUMN jenis_kelamin VARCHAR(10)"),
                    ("alamat", "ALTER TABLE murid ADD COLUMN alamat VARCHAR(200)"),
                    ("nama_ayah_kandung", "ALTER TABLE murid ADD COLUMN nama_ayah_kandung VARCHAR(100)"),
                    ("nama_ibu_kandung", "ALTER TABLE murid ADD COLUMN nama_ibu_kandung VARCHAR(100)"),
                ):
                    if col not in mcols2:
                        con.execute(ddl)
                        con.commit()
                        print(f"[migrasi] +{col} -> {kode}")

                # Periode semester dibuat oleh metadata.create_all(); batas
                # semester sengaja tidak ditebak dan diatur admin melalui UI.
                # Tahun Ajaran default
                con.execute("""
                    INSERT INTO tahun_ajaran (nama, tanggal_mulai, tanggal_selesai,
                                              is_active, created_at)
                    SELECT '2025/2026', '2025-07-01', '2026-06-30', 1,
                           datetime('now')
                    WHERE NOT EXISTS (SELECT 1 FROM tahun_ajaran)
                """)
                tahun_id = con.execute(
                    "SELECT id FROM tahun_ajaran ORDER BY id LIMIT 1"
                ).fetchone()[0]

                # Kelas + tahun_ajaran_id (rebuild — unik lawas mung nama_kelas)
                kcols = {r[1] for r in con.execute("PRAGMA table_info(kelas)")}
                if "tahun_ajaran_id" not in kcols:
                    con.execute("ALTER TABLE kelas RENAME TO kelas_old")
                    con.execute("""
                        CREATE TABLE kelas (
                            id INTEGER NOT NULL PRIMARY KEY,
                            nama_kelas VARCHAR(50) NOT NULL,
                            wali_guru_id INTEGER,
                            tahun_ajaran_id INTEGER NOT NULL
                        )
                    """)
                    con.execute(
                        f"INSERT INTO kelas (id, nama_kelas, wali_guru_id, tahun_ajaran_id) "
                        f"SELECT id, nama_kelas, wali_guru_id, {tahun_id} FROM kelas_old"
                    )
                    con.execute("DROP TABLE kelas_old")
                    con.execute("""
                        CREATE UNIQUE INDEX uq_kelas_tahun_nama
                        ON kelas (tahun_ajaran_id, nama_kelas)
                    """)
                    con.execute("""
                        CREATE INDEX ix_kelas_tahun_ajaran_id
                        ON kelas (tahun_ajaran_id)
                    """)
                    con.commit()
                    print(f"[migrasi] kelas+tahun_ajaran -> {kode}")
                else:
                    # Backfill safety: kelas tanpa tahun → taun pisanan
                    con.execute(
                        "UPDATE kelas SET tahun_ajaran_id = ? "
                        "WHERE tahun_ajaran_id IS NULL", (tahun_id,))
                    con.commit()
            finally:
                con.close()
        except Exception as e:  # noqa: BLE001
            print(f"[migrasi] GAGAL {db_path}: {e}")


def _backup_scheduler() -> None:
    """Cek saben menit: jadwal backup otomatis miturut setelan superadmin."""
    while not _stop_scheduler.is_set():
        try:
            with GlobalSession() as gs:
                st = gs.query(BackupSetting).first()
                if st and st.enabled:
                    now = datetime.now(WIB)
                    if now.strftime("%H:%M") == st.jam:
                        mulai_hari = datetime(now.year, now.month, now.day)
                        done = (gs.query(BackupLog)
                                .filter(BackupLog.jenis == "otomatis",
                                        BackupLog.waktu >= mulai_hari)
                                .first())
                        if not done:
                            run_backup("otomatis", st.retensi)
        except Exception:  # noqa: BLE001 — scheduler aja mati amarga siji error
            pass
        _stop_scheduler.wait(60)


def _alert_scheduler() -> None:
    """Cek saben 15 menit: disk/RAM/backup/langganan → alert Telegram superadmin."""
    while not _stop_scheduler.is_set():
        try:
            run_alert_check()
        except Exception:  # noqa: BLE001 — scheduler aja mati amarga siji error
            pass
        _stop_scheduler.wait(15 * 60)


def _snapshot_scheduler() -> None:
    """Cek saben menit: snapshot otomatis per tenant miturut setelan."""
    from .backup import create_tenant_snapshot
    from .models import SnapshotLog, Tenant
    while not _stop_scheduler.is_set():
        try:
            with GlobalSession() as gs:
                now = datetime.now(WIB)
                mulai_hari = datetime(now.year, now.month, now.day)
                tenants = (gs.query(Tenant)
                           .filter(Tenant.snapshot_otomatis_enabled.is_(True))
                           .all())
                for t in tenants:
                    jam = t.snapshot_otomatis_jam or "02:00"
                    if now.strftime("%H:%M") != jam:
                        continue
                    # cegah dobel di hari yang sama
                    done = (gs.query(SnapshotLog)
                            .filter(SnapshotLog.tenant_id == t.id,
                                    SnapshotLog.jenis == "otomatis",
                                    SnapshotLog.waktu >= mulai_hari)
                            .first())
                    if done:
                        continue
                    try:
                        path = create_tenant_snapshot(t.kode)
                        gs.add(SnapshotLog(tenant_id=t.id, kode=t.kode,
                                           nama=t.nama, file=path.name,
                                           ukuran=path.stat().st_size,
                                           user="otomatis", jenis="otomatis"))
                        gs.commit()
                    except Exception:  # noqa: BLE001
                        gs.rollback()
        except Exception:  # noqa: BLE001
            pass
        _stop_scheduler.wait(60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_global_db()
    # Migrasi legacy SQLite (ALTER TABLE + PRAGMA) HANYA untuk mode SQLite.
    # PostgreSQL schema-per-tenant: schema baru dibuat bersih via provision_tenant_db.
    if not settings.is_pg:
        _migrate_tenant_dbs()
    _stop_scheduler.clear()
    threading.Thread(target=_backup_scheduler, daemon=True).start()
    threading.Thread(target=_alert_scheduler, daemon=True).start()
    threading.Thread(target=_snapshot_scheduler, daemon=True).start()
    try:
        kirim_startup()
    except Exception:  # noqa: BLE001
        pass
    yield
    _stop_scheduler.set()


app = FastAPI(
    title="Aplikasi Madrasah API",
    version="0.1.0",
    description="Absensi QR multi-madrasah — Phase 1",
    lifespan=lifespan,
    # Production: matikan Swagger UI / OpenAPI (jangan bocor endpoint ke publik).
    # Dev: biarkan aktif untuk tes manual.
    docs_url=("/docs" if not settings.is_prod else None),
    redoc_url=("/redoc" if not settings.is_prod else None),
    openapi_url=("/openapi.json" if not settings.is_prod else None),
)

# CORS: dev = wildcard; production = whitelist domain resmi.
if settings.is_prod:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://vps.alaiksander.my.id",
            "http://103.92.214.198",
            "http://127.0.0.1",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ── Web panel (Jinja2 + HTMX) ──────────────────────────────────────
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.exceptions import HTTPException as StarletteHTTPException

from .web.core.templates import STATIC_DIR as WEB_STATIC_DIR, templates
app.mount("/apps/static", StaticFiles(directory=str(WEB_STATIC_DIR)), name="web-static")

from .web.shared_routes import router as web_shared_router
app.include_router(web_shared_router, prefix="/apps")

from .web.modules.absensi import (pengampu_web_router, router as
                                       absensi_web_router)
app.include_router(absensi_web_router, prefix="/apps")
app.include_router(pengampu_web_router, prefix="/apps")

from .web.modules.absensi import bk_web_router, jurnal_web_router
app.include_router(bk_web_router, prefix="/apps")
app.include_router(jurnal_web_router, prefix="/apps")

from .web.modules.absensi.views.murid import router as murid_router
from .web.modules.absensi.views.kelas import router as kelas_router
from .web.modules.absensi.views.guru import router as guru_router
from .web.modules.absensi.views.tahun_ajaran import router as ta_router
from .web.modules.absensi.views.mapel import router as mapel_router
app.include_router(murid_router, prefix="/apps/data/murid")
app.include_router(kelas_router, prefix="/apps/data/kelas")
app.include_router(guru_router, prefix="/apps/data/guru")
app.include_router(ta_router, prefix="/apps/data/tahun-ajaran")
app.include_router(mapel_router, prefix="/apps/data/mapel")

# ── Router System (sub-modul) — di-include dengan prefix /apps/system/<x>
from .web.modules.absensi.views.pengaturan import router as pengaturan_router
from .web.modules.absensi.views.role import router as role_router
app.include_router(pengaturan_router, prefix="/apps/system/pengaturan")
app.include_router(role_router, prefix="/apps/system/role")

from .web.modules.absensi.views.ortu import router as ortu_web_router
app.include_router(ortu_web_router, prefix="/apps")

# ── Router Wali Kelas (menu perwalian) — /apps/wali-kelas
from .web.modules.absensi.views.wali import router as wali_web_router
app.include_router(wali_web_router, prefix="/apps/wali-kelas")

# ── Router Penilaian (API) — /api/nilai/*
from .routers.nilai import router as nilai_api_router
app.include_router(nilai_api_router)

# ── Router Tagihan (API) — /api/tagihan/*
from .routers.tagihan import router as tagihan_api_router
app.include_router(tagihan_api_router)

# ── Router Penilaian (web) — /apps/penilaian
from .web.modules.absensi.views.nilai import router as nilai_web_router
app.include_router(nilai_web_router, prefix="/apps/penilaian")

# ── Router Pembayaran (web) — /apps/pembayaran
from .web.modules.absensi.views.tagihan import router as tagihan_web_router
app.include_router(tagihan_web_router, prefix="/apps")

# ── 301 redirect legacy: /apps/absensi/bk/* → /apps/bk/*
# Pakai path '{suffix:path}' agar catch semua sub-path (catatan, sesi, dll.).
# Setelah MR yakin semua link internal sudah ke URL baru, redirect bisa dihapus.
@app.get("/apps/absensi/bk", include_in_schema=False)
@app.get("/apps/absensi/bk/{suffix:path}", include_in_schema=False)
async def legacy_bk_redirect(suffix: str = ""):
    target = f"/apps/bk/{suffix}" if suffix else "/apps/bk"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(target, status_code=301)

# ── 301 redirect legacy: /apps/absensi/{murid,kelas,guru,tahun-ajaran}/* → /apps/data/<x>/*
@app.get("/apps/absensi/murid", include_in_schema=False)
@app.get("/apps/absensi/murid/{suffix:path}", include_in_schema=False)
async def legacy_murid_redirect(suffix: str = ""):
    target = f"/apps/data/murid/{suffix}" if suffix else "/apps/data/murid"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(target, status_code=301)

@app.get("/apps/absensi/kelas", include_in_schema=False)
@app.get("/apps/absensi/kelas/{suffix:path}", include_in_schema=False)
async def legacy_kelas_redirect(suffix: str = ""):
    target = f"/apps/data/kelas/{suffix}" if suffix else "/apps/data/kelas"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(target, status_code=301)

@app.get("/apps/absensi/guru", include_in_schema=False)
@app.get("/apps/absensi/guru/{suffix:path}", include_in_schema=False)
async def legacy_guru_redirect(suffix: str = ""):
    target = f"/apps/data/guru/{suffix}" if suffix else "/apps/data/guru"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(target, status_code=301)

@app.get("/apps/absensi/tahun-ajaran", include_in_schema=False)
@app.get("/apps/absensi/tahun-ajaran/{suffix:path}", include_in_schema=False)
async def legacy_ta_redirect(suffix: str = ""):
    target = f"/apps/data/tahun-ajaran/{suffix}" if suffix else "/apps/data/tahun-ajaran"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(target, status_code=301)

# ── 301 redirect legacy: /apps/absensi/{pengaturan,role}/* → /apps/system/<x>/*
@app.get("/apps/absensi/pengaturan", include_in_schema=False)
@app.get("/apps/absensi/pengaturan/{suffix:path}", include_in_schema=False)
async def legacy_pengaturan_redirect(suffix: str = ""):
    target = f"/apps/system/pengaturan/{suffix}" if suffix else "/apps/system/pengaturan"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(target, status_code=301)

@app.get("/apps/absensi/role", include_in_schema=False)
@app.get("/apps/absensi/role/{suffix:path}", include_in_schema=False)
async def legacy_role_redirect(suffix: str = ""):
    target = f"/apps/system/role/{suffix}" if suffix else "/apps/system/role"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(target, status_code=301)

from .web.modules.superadmin import router as superadmin_web_router
app.include_router(superadmin_web_router, prefix="/apps")

# ── CSRF protection (Origin/Referer check untuk POST /apps/*) ──
from .web.core.csrf import csrf_middleware
app.middleware("http")(csrf_middleware)


from .web.core.deps import _RedirectToLogin, handle_login_redirect
app.add_exception_handler(_RedirectToLogin, handle_login_redirect)

# ── Custom 404/405/500 untuk path /apps/* ────────────────────
@app.exception_handler(StarletteHTTPException)
async def web_panel_http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Render halaman error friendly untuk semua error HTTP di /apps/*.

    PENTING: Kalau path BUKAN /apps/*, return default JSON error
    supaya tidak break API JSON existing (Flutter).
    """
    if not request.url.path.startswith("/apps"):
        # Default behavior untuk path lain — return JSON
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    # 401 → redirect ke login (UX lebih baik daripada halaman error)
    if exc.status_code == 401:
        from urllib.parse import quote
        from fastapi.responses import RedirectResponse
        next_path = quote(request.url.path, safe="")
        return RedirectResponse(
            f"/apps/login?next={next_path}",
            status_code=303,
        )

    status_messages = {
        401: "Anda perlu login untuk mengakses halaman ini.",
        403: "Anda tidak memiliki akses ke halaman ini.",
        404: "Halaman tidak ditemukan. Cek URL atau kembali ke beranda.",
        405: "Metode tidak diizinkan untuk halaman ini.",
        500: "Terjadi kesalahan server. Silakan coba lagi.",
    }
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": exc.status_code,
            "message": status_messages.get(exc.status_code, str(exc.detail)),
        },
        status_code=exc.status_code,
    )

# Urutan penting: qr (path spesifik /qr-pdf.pdf, /{id}/qr.png) SADURUNGE murid (/{murid_id})
for r in (auth.router, superadmin.router, kelas.router, tahun_ajaran.router,
          guru.router, guru_pengampu.router, roles.router, qr.router,
          murid.router, absensi.router, bk.router, jurnal.router, mapel.router,
          pengaturan.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "madrasah-api"}
