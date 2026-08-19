"""Konfigurasi aplikasi — maca .env"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


def _resolve_db_url(url: str) -> str:
    """Sqlite path relatif dibenerke supaya absolut marang backend/."""
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        rel = url[len("sqlite:///"):]
        return f"sqlite:///{BASE_DIR / rel}"
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = "dev"
    database_url: str = "sqlite:///data/global.db"
    tenant_db_url_template: str = "sqlite:///data/tenants/{kode}.db"
    jwt_secret: str = "dev-secret"
    jwt_expire_hours: int = 12
    pg_user: str = "madrasah"  # dipakai GRANT schema di provision_tenant_db
    pg_pass: str | None = None  # password PG (dipakai pg_dump backup; aman via .env chmod 600)

    # Alert Telegram Super Admin
    alert_telegram_token: str | None = None
    alert_telegram_chat_id: str | None = None
    alert_disk_pct: int = 80
    alert_ram_pct: int = 12

    @property
    def is_pg(self) -> bool:
        """True kalau database_url PostgreSQL (schema-per-tenant mode)."""
        return self.database_url.startswith("postgresql")

    @property
    def resolved_database_url(self) -> str:
        return _resolve_db_url(self.database_url)

    def tenant_db_url(self, kode: str) -> str:
        """URL DB tenant.

        - SQLite (dev): file per tenant `data/tenants/<kode>.db`
        - PostgreSQL (prod): URL sama dengan global DB — isolasi via SCHEMA
          `<kode>` (schema-per-tenant). search_path di-set di engine (db.py).
        """
        if self.is_pg:
            return self.resolved_database_url
        return _resolve_db_url(self.tenant_db_url_template.format(kode=kode))


settings = Settings()
