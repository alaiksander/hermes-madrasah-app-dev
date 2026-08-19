"""Jinja2Templates setup untuk web panel.

Path absolut dipakai supaya aman walau cwd berubah.
Custom filter untuk format tanggal Indonesia + warna status absensi.
Template loader melihat:
- web/templates/         (shared: base.html, login.html, _components/)
- web/modules/*/templates/  (per-modul: modules/absensi/templates/, dst)
"""
from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader

WEB_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = WEB_DIR / "templates"
MODULES_TEMPLATES_DIR = WEB_DIR / "modules"
STATIC_DIR = WEB_DIR / "static"

# Loader: shared templates + semua modules/<modul>/templates/
_loaders = [FileSystemLoader(str(TEMPLATES_DIR))]
if MODULES_TEMPLATES_DIR.exists():
    for mod_dir in MODULES_TEMPLATES_DIR.iterdir():
        tpl_dir = mod_dir / "templates"
        if tpl_dir.is_dir():
            _loaders.append(FileSystemLoader(str(tpl_dir)))

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
# Ganti loader dengan ChoiceLoader agar mencari di shared + modul
templates.env.loader = ChoiceLoader(_loaders)


# ── Custom filters ──────────────────────────────────────────────────────

_DAY_NAMES = {
    0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis",
    4: "Jumat", 5: "Sabtu", 6: "Minggu",
}
_MONTH_NAMES = {
    1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
    5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
    9: "September", 10: "Oktober", 11: "November", 12: "Desember",
}


def _format_date_id(value) -> str:
    """Render tanggal ISO (YYYY-MM-DD) atau date object → Indonesia."""
    if not value:
        return ""
    from datetime import date, datetime
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            return value
    return f"{_DAY_NAMES[value.weekday()]}, {value.day} {_MONTH_NAMES[value.month]} {value.year}"


def _format_datetime_id(value) -> str:
    """Render datetime → 'Senin, 14 Agustus 2026 09:30 WIB'."""
    if not value:
        return ""
    from datetime import datetime
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    return (f"{_DAY_NAMES[value.weekday()]}, {value.day} "
            f"{_MONTH_NAMES[value.month]} {value.year} "
            f"{value.strftime('%H:%M')}")


_STATUS_COLORS = {
    "hadir": "green",
    "izin": "blue",
    "sakit": "amber",
    "alpa": "gray",
}


def _status_color(value: str) -> str:
    """Map status absensi ke Tailwind color name."""
    return _STATUS_COLORS.get((value or "").lower(), "gray")


templates.env.filters["format_date_id"] = _format_date_id
templates.env.filters["format_datetime_id"] = _format_datetime_id
def _has_perm(current_user, kode):
    """Jinja global: cek permission user untuk hide menu/aksi.

    Urutan lookup (PENTING — role custom MENANG atas role string):
    1. role_id ada → lookup DB RolePermission (role custom yang di-assign admin)
    2. role == admin → True semua
    3. role == guru → ROLE_DEFAULT_PERMISSIONS
    """
    if not current_user:
        return False
    role = current_user.get("role")
    role_id = current_user.get("role_id")

    # Role custom (di-assign via Role Manager) → permission dari DB
    if role_id:
        try:
            from app.db import tenant_session_factory
            from app.models import Permission, RolePermission
            kode_tenant = current_user.get("tenant_kode")
            if not kode_tenant:
                return False
            with tenant_session_factory(kode_tenant)() as s:
                p_obj = s.query(Permission).filter_by(kode=kode).first()
                if not p_obj:
                    return False
                return s.query(RolePermission).filter_by(
                    role_id=role_id, permission_id=p_obj.id).first() is not None
        except Exception:
            return False

    if role == "admin":
        return True
    if role == "super_admin":
        return True
    if role == "guru":
        from app.permissions import ROLE_DEFAULT_PERMISSIONS
        return kode in ROLE_DEFAULT_PERMISSIONS["guru"]
    return False


def _has_any_perm(current_user, *kodes):
    """Jinja global: True kalau user punya minimal satu dari kode permission.

    Dipakai untuk guard grup sidebar (auto-hide kalau semua submenu mati).
    """
    return any(_has_perm(current_user, k) for k in kodes)


templates.env.globals["has_perm"] = _has_perm
templates.env.globals["has_any_perm"] = _has_any_perm

# Backward-compat: cek apakah menu tertentu visible untuk role
def _is_admin(current_user):
    return current_user and current_user.get("role") in ("admin", "super_admin")


def _get_nama_aplikasi(current_user) -> str:
    """Jinja global: nama aplikasi sesuai setelan SUPERADMIN (GlobalSetting).

    Baca GlobalSetting.id=1 (nama_aplikasi) dari DB global — di-set via
    panel superadmin → Identitas & Pemeliharaan. Fallback: Pengaturan
    per-tenant (key 'nama_aplikasi'), lalu default 'Aplikasi Madrasah'.
    """
    try:
        from app.db import GlobalSession
        from app.models import GlobalSetting
        with GlobalSession() as s:
            g = s.get(GlobalSetting, 1)
            if g and g.nama_aplikasi:
                return g.nama_aplikasi
    except Exception:
        pass
    if not current_user or not current_user.get("tenant_kode"):
        return "Aplikasi Madrasah"
    try:
        from app.db import tenant_session_factory
        from app.models import Pengaturan
        kode_tenant = current_user.get("tenant_kode")
        with tenant_session_factory(kode_tenant)() as s:
            row = s.query(Pengaturan).filter_by(key="nama_aplikasi").first()
            return row.value if row and row.value else "Aplikasi Madrasah"
    except Exception:
        return "Aplikasi Madrasah"


templates.env.globals["get_nama_aplikasi"] = _get_nama_aplikasi


templates.env.globals["is_admin"] = _is_admin

templates.env.filters["format_date_id"] = _format_date_id
templates.env.filters["format_datetime_id"] = _format_datetime_id
templates.env.filters["status_color"] = _status_color