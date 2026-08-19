"""Identitas & Pemeliharaan — nama aplikasi, logo, mode maintenance."""
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response

from ....core.client import api_delete, api_get, api_post, api_post_multipart, api_put
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


@router.get("/settings")
async def settings_page(
    request: Request,
    user: dict = Depends(require_super_admin_web),
):
    """Halaman Identitas & Pemeliharaan."""
    r = await api_get(request, "/api/super/settings")
    data = r.json() if r.status_code == 200 else {}
    return templates.TemplateResponse(
        request,
        "superadmin/settings.html",
        {
            "user": user,
            "nama_aplikasi": data.get("nama_aplikasi", ""),
            "maintenance": bool(data.get("maintenance", False)),
            "logo_ada": bool(data.get("logo", False)),
        },
    )


@router.post("/settings")
async def settings_update(
    request: Request,
    nama_aplikasi: str = Form(...),
    maintenance: str = Form(""),
    user: dict = Depends(require_super_admin_web),
):
    """Update nama aplikasi + mode maintenance."""
    r = await api_put(
        request,
        "/api/super/settings",
        json={
            "nama_aplikasi": nama_aplikasi,
            "maintenance": maintenance == "on",
        },
    )
    if r.status_code == 200:
        _audit(user, "ubah_setting_platform_web",
               f"nama='{nama_aplikasi}', maintenance={maintenance == 'on'}")
        return _redirect("/madrasah-app/superadmin/settings",
                         "Pengaturan platform disimpan")
    detail = "Gagal menyimpan"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/madrasah-app/superadmin/settings", detail, "error")


@router.post("/settings/logo")
async def settings_logo_upload(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(require_super_admin_web),
):
    """Upload logo platform (PNG/JPG/WebP, max 10MB)."""
    r = await api_post_multipart(
        request,
        "/api/super/settings/logo",
        files={"file": (file.filename or "logo", file.file.read(),
                        file.content_type or "application/octet-stream")},
    )
    if r.status_code == 200:
        _audit(user, "upload_logo_web",
               f"Logo platform diganti ({file.filename or 'unknown'})")
        return _redirect("/madrasah-app/superadmin/settings", "Logo berhasil diunggah")
    detail = "Gagal upload logo"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/madrasah-app/superadmin/settings", detail, "error")


@router.get("/settings/logo-preview")
async def settings_logo_preview(
    request: Request,
    user: dict = Depends(require_super_admin_web),
):
    """Proxy logo untuk preview di halaman settings."""
    r = await api_get(request, "/api/super/settings/logo")
    if r.status_code != 200:
        return Response(status_code=404)
    return Response(
        content=r.content,
        media_type=r.headers.get("content-type", "image/png"),
    )


@router.post("/settings/logo/hapus")
async def settings_logo_delete(
    request: Request,
    user: dict = Depends(require_super_admin_web),
):
    """Hapus logo platform."""
    r = await api_delete(request, "/api/super/settings/logo", json={})
    if r.status_code == 200:
        _audit(user, "hapus_logo_web", "Logo platform dihapus")
        return _redirect("/madrasah-app/superadmin/settings", "Logo dihapus")
    detail = "Gagal menghapus logo"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/madrasah-app/superadmin/settings", detail, "error")