"""Backup rutin database platform — global.db + kabeh tenant DB.

Digunakake dening:
- endpoint POST /api/super/backup/run (manual, saka UI superadmin)
- scheduler thread ing main.py (otomatis, miturut setelan jadwal)
"""
import glob
import os
import shutil
import sqlite3
import tarfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import settings
from .db import GlobalSession
from .models import BackupLog

WIB = ZoneInfo("Asia/Jakarta")

BACKEND_DIR = Path(__file__).resolve().parent.parent   # .../backend
DATA_DIR = BACKEND_DIR / "data"
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/home/ubuntu/backups/madrasah"))
DELETED_DIR = BACKUP_DIR / "deleted"   # backup wajib sadurunge tenant dihapus (ora kena retensi)


def _backup_sqlite(src: Path, dst: Path) -> None:
    """Salin DB nganggo SQLite backup API — aman sanajan ana tulisane."""
    s = sqlite3.connect(src)
    try:
        d = sqlite3.connect(dst)
        try:
            s.backup(d)
        finally:
            d.close()
    finally:
        s.close()


def _backup_pg_schema(kode: str, dst: Path) -> None:
    """Backup 1 tenant schema PostgreSQL → file .dump (pg_dump --schema)."""
    import subprocess
    from .config import settings
    cmd = [
        "pg_dump", "-h", "127.0.0.1", "-p", "5432",
        "-U", settings.pg_user, "-d", settings.database_url.split("/")[-1],
        "--schema", kode, "-Fc", "-f", str(dst),
    ]
    env = dict(__import__("os").environ, PGPASSWORD=settings.pg_pass or "")
    subprocess.run(cmd, env=env, check=True, capture_output=True)


def backup_tenant_db(kode: str) -> Path:
    """Backup wajib DB tenant sadurunge dihapus -> backups/deleted/.

    Ngangkat exception yen gagal (delete kudu dibatalake).
    - SQLite: salin file DB (sqlite backup API)
    - PostgreSQL: pg_dump --schema <kode>
    """
    ts = datetime.now(WIB).strftime("%Y%m%d-%H%M%S")
    DELETED_DIR.mkdir(parents=True, exist_ok=True)
    if settings.is_pg:
        dst = DELETED_DIR / f"{kode}-{ts}.dump"
        _backup_pg_schema(kode, dst)
        return dst
    src = DATA_DIR / "tenants" / f"{kode}.db"
    dst = DELETED_DIR / f"{kode}-{ts}.db"
    _backup_sqlite(src, dst)
    return dst


def run_backup(jenis: str = "otomatis", retensi: int = 14) -> dict:
    """Jalankan backup: kabeh DB + .env -> arsip tar.gz; retensi; catet log.

    - SQLite: backup API per file (global.db + tenants/*.db)
    - PostgreSQL: pg_dump per tenant schema + global schema (public)
    """
    ts = datetime.now(WIB).strftime("%Y%m%d-%H%M")
    dest = BACKUP_DIR
    dest.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    files: list[Path] = []

    if settings.is_pg:
        from .models import Tenant
        dbname = settings.database_url.split("/")[-1]
        env = dict(os.environ, PGPASSWORD=settings.pg_pass or "")
        # Global (public schema) — pg_dumpall tidak perlu; dump public saja
        try:
            out = dest / f"global-{ts}.dump"
            subprocess.run(
                ["pg_dump", "-h", "127.0.0.1", "-p", "5432", "-U", settings.pg_user,
                 "-d", dbname, "--schema", "public", "-Fc", "-f", str(out)],
                env=env, check=True, capture_output=True)
            files.append(out)
        except Exception as e:  # noqa: BLE001
            errors.append(f"global: {e}")
        # Per tenant schema
        with GlobalSession() as gs:
            tenants = gs.query(Tenant).all()
        for t in tenants:
            try:
                out = dest / f"{t.kode}-{ts}.dump"
                subprocess.run(
                    ["pg_dump", "-h", "127.0.0.1", "-p", "5432", "-U", settings.pg_user,
                     "-d", dbname, "--schema", t.kode, "-Fc", "-f", str(out)],
                    env=env, check=True, capture_output=True)
                files.append(out)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{t.kode}: {e}")
    else:
        dbs = [Path(DATA_DIR / "global.db")] + sorted(
            Path(p) for p in glob.glob(str(DATA_DIR / "tenants" / "*.db")))
        for db in dbs:
            if not db.exists():
                continue
            out = dest / f"{db.stem}-{ts}.db"
            try:
                _backup_sqlite(db, out)
                files.append(out)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{db.stem}: {e}")

    env = BACKEND_DIR / ".env"
    env_out = dest / f"env-{ts}"
    if env.exists():
        try:
            shutil.copy(env, env_out)
            files.append(env_out)
        except Exception as e:  # noqa: BLE001
            errors.append(f".env: {e}")

    ok = not errors
    arsip = dest / f"madrasah-{ts}.tar.gz"
    ukuran = 0
    nama = ""
    try:
        with tarfile.open(arsip, "w:gz") as tar:
            for f in files:
                tar.add(f, arcname=f.name)
        for f in files:
            f.unlink(missing_ok=True)
        ukuran = arsip.stat().st_size
        nama = arsip.name
    except Exception as e:  # noqa: BLE001
        ok = False
        errors.append(f"arsip: {e}")

    # retensi: simpen N arsip paling anyar
    try:
        olds = sorted(dest.glob("madrasah-*.tar.gz"), reverse=True)
        for f in olds[retensi:]:
            f.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass

    pesan = "; ".join(errors) if errors else "OK"
    with GlobalSession() as gs:
        gs.add(BackupLog(
            waktu=datetime.now(WIB), jenis=jenis,
            status="ok" if ok else "gagal",
            ukuran=ukuran, nama_file=nama, pesan=pesan[:300]))
        gs.commit()

    return {"ok": ok, "nama": nama, "ukuran": ukuran, "pesan": pesan}
