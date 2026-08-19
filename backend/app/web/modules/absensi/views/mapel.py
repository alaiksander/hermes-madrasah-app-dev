"""Mata Pelajaran view: list + form tambah/edit + hapus."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_delete, api_get, api_patch, api_post
from ....core.deps import require_permission_web, require_login_web
from ....core.templates import templates

router = APIRouter(tags=["web-data-mapel"])


def _redirect(msg: str, type_: str = "success", path: str = "/madrasah-app/data/mapel"):
    return RedirectResponse(
        url=f"{path}?msg={msg.replace(' ', '+')}&type={type_}",
        status_code=303,
    )


@router.get("")
async def mapel_list(
    request: Request,
    user: dict = Depends(require_permission_web("mapel.view", "mapel.create", "mapel.update", "mapel.delete")),
):
    """Daftar mata pelajaran (semua, termasuk non-aktif)."""
    r = await api_get(request, "/api/mapel")
    mapel_list = r.json() if r.status_code == 200 else []
    return templates.TemplateResponse(
        request,
        "mapel/list.html",
        {
            "user": user,
            "mapel_list": mapel_list,
        },
    )


@router.get("/baru")
async def mapel_baru(
    request: Request,
    user: dict = Depends(require_permission_web("mapel.view")),
):
    """Form tambah mata pelajaran (admin only)."""
    return templates.TemplateResponse(
        request,
        "mapel/form.html",
        {
            "user": user,
            "mapel": None,
            "form_title": "Tambah Mata Pelajaran",
            "form_action": "/madrasah-app/data/mapel",
        },
    )


@router.post("")
async def mapel_create(
    request: Request,
    nama: str = Form(...),
    kode: str = Form(""),
    kelompok: str = Form("umum"),
    user: dict = Depends(require_permission_web("mapel.view", "mapel.create", "mapel.update", "mapel.delete")),
):
    """Submit form tambah mapel."""
    payload = {
        "nama": nama.strip(),
        "kode": kode.strip(),
        "kelompok": kelompok.strip() or "umum",
    }
    r = await api_post(request, "/api/mapel", json=payload)
    if r.status_code in (200, 201):
        return _redirect(f"Mata pelajaran {nama.strip()} berhasil ditambahkan")
    detail = "Gagal menambahkan mata pelajaran"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return templates.TemplateResponse(
        request,
        "mapel/form.html",
        {
            "user": user,
            "mapel": payload,
            "form_title": "Tambah Mata Pelajaran",
            "form_action": "/madrasah-app/data/mapel",
            "error": detail,
        },
        status_code=400,
    )


@router.get("/{mid}/edit")
async def mapel_edit(
    request: Request,
    mid: int,
    user: dict = Depends(require_permission_web("mapel.view")),
):
    """Form edit mapel (admin only)."""
    list_r = await api_get(request, "/api/mapel")
    if list_r.status_code != 200:
        return _redirect("Gagal memuat data mapel", "error")
    mapel = next((m for m in list_r.json() if m["id"] == mid), None)
    if not mapel:
        return _redirect("Mata pelajaran tidak ditemukan", "error")
    return templates.TemplateResponse(
        request,
        "mapel/form.html",
        {
            "user": user,
            "mapel": mapel,
            "form_title": "Edit Mata Pelajaran",
            "form_action": f"/madrasah-app/data/mapel/{mid}",
        },
    )


@router.post("/{mid}")
async def mapel_update(
    request: Request,
    mid: int,
    nama: str = Form(...),
    kode: str = Form(""),
    kelompok: str = Form("umum"),
    is_active: str = Form("on"),
    user: dict = Depends(require_permission_web("mapel.view", "mapel.create", "mapel.update", "mapel.delete")),
):
    """Submit form edit mapel."""
    payload = {
        "nama": nama.strip(),
        "kode": kode.strip(),
        "kelompok": kelompok.strip() or "umum",
        "is_active": is_active == "on",
    }
    r = await api_patch(request, f"/api/mapel/{mid}", json=payload)
    if r.status_code == 200:
        return _redirect(f"Mata pelajaran {nama.strip()} berhasil diperbarui")
    detail = "Gagal memperbarui mata pelajaran"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")


@router.post("/{mid}/hapus")
async def mapel_hapus(
    request: Request,
    mid: int,
    user: dict = Depends(require_permission_web("mapel.view", "mapel.create", "mapel.update", "mapel.delete")),
):
    """Hapus mapel (admin only)."""
    r = await api_delete(request, f"/api/mapel/{mid}")
    if r.status_code == 200:
        return _redirect("Mata pelajaran berhasil dihapus")
    detail = "Gagal menghapus mata pelajaran"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")
