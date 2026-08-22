"""Manajemen engine + session — global DB lan per-tenant DB.

Strategi multi-tenant (sesuai PRD):
- Dev:  global.db + siji file SQLite per tenant (data/tenants/<kode>.db)
- Prod: PostgreSQL schema-per-tenant — 1 server PG, tiap tenant = 1 schema
        `<kode>`; search_path di-set otomatis per engine.
"""
import re

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import GlobalBase, GlobalSetting, Plan, TenantBase

_connect_args = {"check_same_thread": False}


def _set_wal(dbapi_connection, _record) -> None:
    """SQLite WAL mode — baca+tulis bebarengan luwih lancar (aman)."""
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
    except Exception:  # noqa: BLE001 — non-sqlite (Postgres) ora ana pragma iki
        pass


def _sanitize_schema(kode: str) -> str:
    """Amankan nama schema PG — mung alphanumeric + underscore (mencegah SQL injection via kode tenant)."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", kode)


def _set_search_path(dbapi_connection, _record, kode: str) -> None:
    """PostgreSQL: SET search_path per tenant engine → schema <kode>."""
    cursor = dbapi_connection.cursor()
    cursor.execute(f'SET search_path TO "{_sanitize_schema(kode)}"')
    cursor.close()


def _new_engine(url: str, kode: str | None = None):
    # PENTING (PG schema-per-tenant): tenant engine WAJIB punya pool TERPISAH.
    # Kalau pakai URL sama (global vs tenant), SQLAlchemy SHARE koneksi pool →
    # search_path global (public) bocor ke query tenant. NullPool = tiap koneksi
    # baru → event connect (SET search_path) selalu jalan.
    poolclass = None
    pool_kwargs = {}
    if url.startswith("postgresql") and kode is not None:
        from sqlalchemy.pool import NullPool
        poolclass = NullPool
    elif url.startswith("sqlite"):
        # SQLite: WAL mode (via event connect) + pool di-tuning — default
        # (5+10, timeout 30s) SERING penuh saat login burst/request paralel,
        # gejalanya QueuePool limit reached + timeout 30s (lihat P-WEB-89).
        # pool_size lebih tinggi dari jumlah koneksi konkuren yang mungkin;
        # SQLite WAL mengizinkan baca paralel, tulis serial per DB.
        pool_kwargs = {
            "pool_size": 10,
            "max_overflow": 20,
            "pool_timeout": 10,     # fail fast, jangan hang 30s
            "pool_recycle": 300,    # SQLite connection kadaluarsa cepat
            "pool_pre_ping": True,
        }
    else:
        # PG global (public schema) — pool dengan ukuran eksplisit.
        # VPS kecil (2 vCPU/3.8GB RAM): pool 5 + overflow 10 default SERING penuh
        # saat login burst (web form POST + redirect = 2 request simultan).
        # Naikkan pool_size + pre_ping + recycle supaya login burst aman.
        pool_kwargs = {
            "pool_size": 10,        # default 5 → 10 (handle concurrent users)
            "max_overflow": 20,      # default 10 → 20 (spike tolerance)
            "pool_timeout": 10,     # default 30 → 10 (fail fast, jangan hang 30s)
            "pool_recycle": 1800,   # reconnect tiap 30 menit (PG idle timeout protection)
            "pool_pre_ping": True,  # cek koneksi valid sebelum pakai
        }

    engine = create_engine(
        url,
        connect_args=_connect_args if url.startswith("sqlite") else {},
        poolclass=poolclass,
        **pool_kwargs,
    )
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _set_wal)
    elif kode is not None:
        # PG schema-per-tenant: set search_path saat koneksi dibuka
        event.listen(engine, "connect",
                     lambda c, r, k=kode: _set_search_path(c, r, k))
    return engine


global_engine = _new_engine(settings.resolved_database_url)
GlobalSession = sessionmaker(bind=global_engine, autoflush=False, expire_on_commit=False)

_tenant_engines: dict[str, object] = {}


def get_tenant_engine(kode: str):
    """Engine per tenant — di-cache supaya ora digawe maneh terus-terusan.

    - SQLite: engine file per tenant (data/tenants/<kode>.db)
    - PostgreSQL: engine ke 1 server PG + search_path=<kode> (schema-per-tenant)
    """
    if kode not in _tenant_engines:
        _tenant_engines[kode] = _new_engine(settings.tenant_db_url(kode), kode=kode)
    return _tenant_engines[kode]


def tenant_session_factory(kode: str) -> sessionmaker[Session]:
    return sessionmaker(bind=get_tenant_engine(kode), autoflush=False, expire_on_commit=False)


def provision_tenant_db(kode: str) -> None:
    """Gawe schema + tabel tenant — idempotent.

    - SQLite: create_all langsung (file otomatis dibuat engine)
    - PostgreSQL: CREATE SCHEMA IF NOT EXISTS <kode> + create_all
    """
    if settings.is_pg:
        with global_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{_sanitize_schema(kode)}"'))
        # GRANT schema ke user madrasah (supaya bisa create table di dalamnya)
        with global_engine.begin() as conn:
            conn.execute(text(
                f'GRANT ALL ON SCHEMA "{_sanitize_schema(kode)}" TO {settings.pg_user}'))
        TenantBase.metadata.create_all(get_tenant_engine(kode))
    else:
        TenantBase.metadata.create_all(get_tenant_engine(kode))


def init_global_db() -> None:
    GlobalBase.metadata.create_all(global_engine)
    with GlobalSession() as s:
        # Setelan global (siji baris id=1)
        if s.get(GlobalSetting, 1) is None:
            s.add(GlobalSetting(id=1, nama_aplikasi="Aplikasi Madrasah",
                                maintenance=False))
        # Plan default (mung yen tabel kosong)
        if s.query(Plan).count() == 0:
            s.add_all([
                Plan(nama="free", label="Free",
                     max_murid=50, max_guru=10,
                     fitur="1 madrasah, 50 murid, export Excel"),
                Plan(nama="pilot", label="Pilot",
                     max_murid=200, max_guru=30,
                     fitur="200 murid, export PDF, rekap lanjutan"),
                Plan(nama="pro", label="Pro",
                     max_murid=None, max_guru=None,
                     fitur="Tanpa batas, semua fitur, prioritas"),
            ])
        s.commit()
