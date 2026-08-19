"""Helper audit trail — untuk logging aksi sensitif (admin sekolah + superadmin)."""
from datetime import datetime, timezone
from typing import Optional

from .db import GlobalSession
from .models import AuditLog


def log_action(user: dict, aksi: str, rincian: str = "", tenant: Optional[str] = None) -> None:
    """Catet jejak aksi sensitif ke AuditLog (global table).

    Dipanggil dari:
    - superadmin endpoint (aksi platform)
    - admin sekolah endpoint (aksi sensitif di tenant: tambah kelas, guru, dll)

    Args:
        user: dict dari get_current_user (punya 'username', 'tenant_kode', 'role')
        aksi: kode aksi singkat, e.g. 'tambah_kelas', 'hapus_guru'
        rincian: deskripsi detail, max 300 char (auto-truncate)
        tenant: override tenant_kode (default: dari user dict)

    Returns: None (audit log committed, tidak raise exception agar tidak ganggu flow utama)
    """
    try:
        tenant_kode = tenant if tenant is not None else user.get("tenant_kode", "") or ""
        username = user.get("username", "-")
        with GlobalSession() as s:
            s.add(AuditLog(
                user=username,
                aksi=aksi[:100],
                rincian=rincian[:300],
                tenant=tenant_kode,
            ))
            s.commit()
    except Exception as e:
        # Audit log gagal TIDAK boleh menggangu flow utama
        # (mis. DB down, dsb) — log ke stderr dan skip
        import sys
        print(f"[audit] Failed to log action {aksi!r}: {e}", file=sys.stderr)