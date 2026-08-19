"""Tahun Ajaran view: list + form + set aktif + hapus."""
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_delete, api_get, api_patch, api_post, api_put
from ....core.deps import require_permission_web, require_login_web
from ....core.templates import templates

router = APIRouter(tags=["web-data-tahun-ajaran"])


def _redirect(msg: str, type_: str = "success", path: str = "/madrasah-app/data/tahun-ajaran"):
    return RedirectResponse(
        url=f"{path}?msg={msg.replace(' ', '+')}&type={type_}",
        status_code=303,
    )


@router.get("")
async def tahun_ajaran_list(
    request: Request,
    user: dict = Depends(require_permission_web("ta.view")),
):
    """Daftar tahun ajaran (admin only — guru cukup pakai API via dropdown)."""
    r = await api_get(request, "/api/tahun-ajaran")
    tahun_list = r.json() if r.status_code == 200 else []
    return templates.TemplateResponse(
        request,
        "tahun_ajaran/list.html",
        {
            "user": user,
            "tahun_list": tahun_list,
        },
    )


@router.get("/baru")
async def tahun_ajaran_baru(
    request: Request,
    user: dict = Depends(require_permission_web("ta.view")),
):
    """Form tambah tahun ajaran baru (admin only)."""
    return templates.TemplateResponse(
        request,
        "tahun_ajaran/form.html",
        {
            "user": user,
            "tahun": None,
            "form_title": "Tambah Tahun Ajaran",
            "form_action": "/madrasah-app/data/tahun-ajaran",
            "default_mulai": None,
            "default_selesai": None,
        },
    )


@router.post("")
async def tahun_ajaran_create(
    request: Request,
    nama: str = Form(...),
    tanggal_mulai: str = Form(...),
    tanggal_selesai: str = Form(...),
    user: dict = Depends(require_permission_web("ta.view", "ta.create", "ta.update")),
):
    """Submit form tambah tahun ajaran."""
    payload = {
        "nama": nama.strip(),
        "tanggal_mulai": tanggal_mulai,
        "tanggal_selesai": tanggal_selesai,
    }
    r = await api_post(request, "/api/tahun-ajaran", json=payload)
    if r.status_code in (200, 201):
        return _redirect(f"Tahun ajaran {nama} berhasil ditambahkan")
    detail = "Gagal menambahkan tahun ajaran"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return templates.TemplateResponse(
        request,
        "tahun_ajaran/form.html",
        {
            "user": user,
            "tahun": payload,
            "form_title": "Tambah Tahun Ajaran",
            "form_action": "/madrasah-app/data/tahun-ajaran",
            "default_mulai": tanggal_mulai,
            "default_selesai": tanggal_selesai,
            "error": detail,
        },
        status_code=400,
    )


@router.get("/{ta_id}/edit")
async def tahun_ajaran_edit(
    request: Request,
    ta_id: int,
    user: dict = Depends(require_permission_web("ta.view")),
):
    """Form edit tahun ajaran (admin only)."""
    r = await api_get(request, "/api/tahun-ajaran")
    if r.status_code != 200:
        return _redirect("Gagal memuat data", "error")
    tahun = next((t for t in r.json() if t["id"] == ta_id), None)
    if not tahun:
        return _redirect("Tahun ajaran tidak ditemukan", "error")

    return templates.TemplateResponse(
        request,
        "tahun_ajaran/form.html",
        {
            "user": user,
            "tahun": tahun,
            "form_title": "Edit Tahun Ajaran",
            "form_action": f"/madrasah-app/data/tahun-ajaran/{ta_id}",
            "default_mulai": tahun.get("tanggal_mulai"),
            "default_selesai": tahun.get("tanggal_selesai"),
        },
    )


@router.post("/{ta_id}")
async def tahun_ajaran_update(
    request: Request,
    ta_id: int,
    nama: str = Form(...),
    tanggal_mulai: str = Form(...),
    tanggal_selesai: str = Form(...),
    user: dict = Depends(require_permission_web("ta.view", "ta.create", "ta.update")),
):
    """Submit form edit tahun ajaran."""
    payload = {
        "nama": nama.strip(),
        "tanggal_mulai": tanggal_mulai,
        "tanggal_selesai": tanggal_selesai,
    }
    r = await api_patch(request, f"/api/tahun-ajaran/{ta_id}", json=payload)
    if r.status_code == 200:
        return _redirect(f"Tahun ajaran {nama} diperbarui")
    detail = "Gagal memperbarui"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")


@router.post("/{ta_id}/aktifkan")
async def tahun_ajaran_aktifkan(
    request: Request,
    ta_id: int,
    user: dict = Depends(require_permission_web("ta.view", "ta.create", "ta.update")),
):
    """Set tahun ajaran sebagai aktif (admin only)."""
    payload = {"is_active": True}
    r = await api_patch(request, f"/api/tahun-ajaran/{ta_id}", json=payload)
    if r.status_code == 200:
        return _redirect("Tahun ajaran diaktifkan (lainnya dimatikan)")
    detail = "Gagal mengaktifkan"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")


@router.get("/{ta_id}/periode")
async def tahun_ajaran_periode(request: Request, ta_id: int,
                               user: dict = Depends(require_permission_web("ta.view"))):
    r = await api_get(request, "/api/tahun-ajaran")
    tahun = next((t for t in r.json() if t["id"] == ta_id), None) if r.status_code == 200 else None
    if not tahun:
        return _redirect("Tahun ajaran tidak ditemukan", "error")
    p = await api_get(request, f"/api/tahun-ajaran/{ta_id}/periode")
    periode = p.json() if p.status_code == 200 else []
    return templates.TemplateResponse(request, "tahun_ajaran/periode.html",
                                      {"user": user, "tahun": tahun, "periode": periode})


@router.post("/{ta_id}/periode")
async def tahun_ajaran_periode_save(request: Request, ta_id: int,
                                    kode: str = Form(...), nama: str = Form(...),
                                    tanggal_mulai: str = Form(...),
                                    tanggal_selesai: str = Form(...),
                                    user: dict = Depends(require_permission_web("ta.view", "ta.create", "ta.update"))):
    r = await api_put(request, f"/api/tahun-ajaran/{ta_id}/periode", json={
        "kode": kode, "nama": nama.strip(),
        "tanggal_mulai": tanggal_mulai, "tanggal_selesai": tanggal_selesai,
    })
    if r.status_code == 200:
        return _redirect("Periode semester berhasil disimpan", path=f"/madrasah-app/data/tahun-ajaran/{ta_id}/periode")
    try:
        detail = r.json().get("detail", "Gagal menyimpan periode semester")
    except Exception:
        detail = "Gagal menyimpan periode semester"
    return _redirect(detail, "error", f"/madrasah-app/data/tahun-ajaran/{ta_id}/periode")


@router.post("/{ta_id}/hapus")
async def tahun_ajaran_hapus(
    request: Request,
    ta_id: int,
    user: dict = Depends(require_permission_web("ta.view", "ta.create", "ta.update")),
):
    """Hapus tahun ajaran (admin only). Gagal kalau masih ada kelas."""
    r = await api_delete(request, f"/api/tahun-ajaran/{ta_id}")
    if r.status_code == 200:
        return _redirect("Tahun ajaran dihapus")
    detail = "Gagal menghapus"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")