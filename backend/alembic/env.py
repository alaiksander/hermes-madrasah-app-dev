"""Alembic env — dual mode.

- SQLite (dev): migrate global.db + tiap file tenant (data/tenants/*.db)
- PostgreSQL (prod): schema-per-tenant — global (public) + tiap schema tenant
  di-loop; search_path diarahkan per schema sebelum migrate.

Cara pakai:
  SQLite: alembic upgrade head                        (global)
          alembic upgrade head --name tenant?         (belum — manual per file)
  PG:     alembic -x tenant_kode=mtsn2kudus upgrade head   (satu tenant)
          alembic upgrade head                        (public/global saja)
"""
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy import pool

from alembic import context

# Pastikan backend/ di sys.path (biar bisa import app.*)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.models import GlobalBase, TenantBase  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None  # ditentukan per mode di bawah


def _set_search_path(conn, schema: str) -> None:
    conn.execute(text(f'SET search_path TO "{schema}"'))


def _migrate(engine, schema: str | None, metadata) -> None:
    """Migrate 1 target (schema None = SQLite file / public PG)."""
    global target_metadata
    target_metadata = metadata
    if schema:
        with engine.connect() as conn:
            _set_search_path(conn, schema)
    context.configure(
        connection=engine.connect() if not schema else None,
        target_metadata=metadata,
        compare_type=True,
        render_as_batch=True,  # SQLite ALTER support
    )
    # Offline mode
    if context.is_offline_mode():
        context.run_migrations()
        return


def run_migrations_offline() -> None:
    """Offline mode — cuma global/public (SQL belum jalan)."""
    url = settings.resolved_database_url
    context.configure(url=url, target_metadata=GlobalBase.metadata,
                      literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def _iter_tenant_schemas():
    """Daftar tenant: PG → schema dari global DB; SQLite → file .db."""
    if settings.is_pg:
        from sqlalchemy import inspect
        from app.db import global_engine
        insp = inspect(global_engine)
        for s in insp.get_schema_names():
            if s not in ("public", "information_schema", "pg_catalog",
                         "pg_toast", "pg_temp_1", "pg_toast_temp_1"):
                yield s
    else:
        from pathlib import Path as _P
        from app.config import BASE_DIR
        for p in sorted(_P(BASE_DIR).glob("data/tenants/*.db")):
            yield p.stem


def run_migrations_online() -> None:
    """Online mode: global/public + semua tenant schema."""
    global target_metadata

    # 1. Global (public untuk PG / global.db untuk SQLite)
    if settings.is_pg:
        engine = create_engine(settings.resolved_database_url, poolclass=pool.NullPool)
        target_metadata = GlobalBase.metadata
        with engine.connect() as conn:
            _set_search_path(conn, "public")
            context.configure(connection=conn, target_metadata=GlobalBase.metadata,
                              compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
        engine.dispose()
    else:
        engine = create_engine(settings.resolved_database_url)
        target_metadata = GlobalBase.metadata
        with engine.connect() as conn:
            context.configure(connection=conn, target_metadata=GlobalBase.metadata,
                              compare_type=True, render_as_batch=True)
            with context.begin_transaction():
                context.run_migrations()
        engine.dispose()

    # 2. Semua tenant schema (PG) / file (SQLite)
    for schema in _iter_tenant_schemas():
        if settings.is_pg:
            engine = create_engine(settings.resolved_database_url, poolclass=pool.NullPool)
            target_metadata = TenantBase.metadata
            with engine.connect() as conn:
                _set_search_path(conn, schema)
                context.configure(connection=conn, target_metadata=TenantBase.metadata,
                                  compare_type=True)
                with context.begin_transaction():
                    context.run_migrations()
            engine.dispose()
        else:
            url = settings.tenant_db_url(schema)
            engine = create_engine(url)
            target_metadata = TenantBase.metadata
            with engine.connect() as conn:
                context.configure(connection=conn, target_metadata=TenantBase.metadata,
                                  compare_type=True, render_as_batch=True)
                with context.begin_transaction():
                    context.run_migrations()
            engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
