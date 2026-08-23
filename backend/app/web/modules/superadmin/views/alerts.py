"""Notifikasi Super Admin — alert Telegram: status, cek, uji."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_get, api_post
from ....core.deps import require_super_admin_web
from ....core.templates import templates
from .....audit import log_action

router = APIRouter()


def _audit(user: dict, aksi: str, rincian: str) -> None:
    log_action(user, aksi, rincian, tenant="")


def _redirect(path: str, msg: str = "", type_: str = "success"):
    if not isinstance(msg, str):
        if isinstance(msg, dict):
            msg = msg.get("detail", str(msg))
        else:
            msg = str(msg)
    suffix = f"?msg={msg.replace(' ', '+')}&type={type_}" if msg else ""
    return RedirectResponse(f"{path}{suffix}", status_code=303)


@router.get("/alerts")
async def alerts_page(
    request: Request,
    user: dict = Depends(require_super_admin_web),
):
    """Halaman status notifikasi super admin."""
    r = await api_get(request, "/api/super/alerts/status")
    st = r.json() if r.status_code == 200 else {}

    return templates.TemplateResponse(
        request,
        "superadmin/alerts.html",
        {"user": user, "st": st},
    )


@router.post("/alerts/check")
async def alerts_check(
    request: Request,
    user: dict = Depends(require_super_admin_web),
):
    """Jalankan cek alert sekarang (kirim hanya kalau ada masalah baru/pulih)."""
    r = await api_post(request, "/api/super/alerts/check", json={})
    if r.status_code == 200:
        data = r.json()
        kirim = data.get("kirim") or []
        pesan = data.get("pesan", "Cek selesai")
        if kirim:
            msg = f"Cek selesai — {len(kirim)} notifikasi dikirim"
        else:
            msg = pesan
        _audit(user, "alerts_check_web", msg)
        return _redirect("/apps/superadmin/alerts", msg)
    detail = "Gagal menjalankan cek"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/apps/superadmin/alerts", detail, "error")


@router.post("/alerts/test")
async def alerts_test(
    request: Request,
    user: dict = Depends(require_super_admin_web),
):
    """Kirim pesan uji coba ke Telegram (pastikan bot + chat_id benar)."""
    r = await api_post(request, "/api/super/alerts/test", json={})
    if r.status_code == 200:
        data = r.json()
        pesan = data.get("pesan", "Uji dikirim")
        _audit(user, "alerts_test_web", f"Uji notifikasi: {pesan}")
        return _redirect("/apps/superadmin/alerts", pesan)
    detail = "Gagal mengirim uji"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/apps/superadmin/alerts", detail, "error")


@router.post("/alerts/config")
async def alerts_config(
    request: Request,
    user: dict = Depends(require_super_admin_web),
):
    """Simpan konfigurasi bot Telegram (token + chat_id) via form."""
    form = await request.form()
    hapus = bool(form.get("hapus"))
    token = "" if hapus else str(form.get("token") or "").strip()
    chat_id = "" if hapus else str(form.get("chat_id") or "").strip()
    r = await api_post(request, "/api/super/alerts/config",
                       json={"token": token, "chat_id": chat_id})
    if r.status_code == 200:
        data = r.json()
        disetel = data.get("disetel", False)
        if hapus:
            msg = "Konfigurasi bot Telegram dihapus — fallback ke .env"
        else:
            msg = ("Konfigurasi bot Telegram disimpan — notifikasi aktif"
                   if disetel else
                   "Konfigurasi disimpan (token/chat_id kosong — fallback .env)")
        _audit(user, "alerts_config_web", msg)
        return _redirect("/apps/superadmin/alerts", msg)
    detail = "Gagal menyimpan konfigurasi"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/apps/superadmin/alerts", detail, "error")