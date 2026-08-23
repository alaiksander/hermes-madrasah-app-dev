"""Surat Menyurat — web views (Tata Usaha)."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_delete, api_get, api_patch, api_post
from ....core.deps import require_permission_web
from ....core.templates import templates

router = APIRouter(tags=["web-tata-usaha"])


def _redirect(msg: str, type_: str = "success", path: str = "/apps/tata-usaha"):
    return RedirectResponse(
        url=f"{path}?msg={msg.replace(' ', '+')}&type={type_}",
        status_code=303,
    )


@router.get("")
async def surat_list(
    request: Request,
    jenis: str = "masuk",
    q: str = "",
    user: dict = Depends(require_permission_web("surat.view")),
):
    """Daftar surat (tab masuk/keluar)."""
    params = {"jenis": jenis}
    if q:
        params["q"] = q
    r = await api_get(request, "/api/surat", **params)
    surat_list = r.json() if r.status_code == 200 else []
    return templates.TemplateResponse(
        request,
        "surat/list.html",
        {"user": user, "surat_list": surat_list, "jenis": jenis, "q": q},
    )


@router.get("/tambah")
async def surat_baru(
    request: Request,
    user: dict = Depends(require_permission_web("surat.create")),
):
    """Form tambah surat."""
    return templates.TemplateResponse(
        request,
        "surat/form.html",
        {"user": user, "surat": None, "form_title": "Tambah Surat",
         "form_action": "/apps/tata-usaha"},
    )


@router.post("")
async def surat_create(
    request: Request,
    jenis: str = Form(...),
    nomor_agenda: str = Form(...),
    tanggal: str = Form(...),
    dari_kepada: str = Form(...),
    perihal: str = Form(...),
    isi: str = Form(""),
    lampiran: str = Form(""),
    status: str = Form("draft"),
    user: dict = Depends(require_permission_web("surat.create")),
):
    """Submit form tambah surat."""
    payload = {
        "jenis": jenis,
        "nomor_agenda": nomor_agenda.strip(),
        "tanggal": tanggal,
        "dari_kepada": dari_kepada.strip(),
        "perihal": perihal.strip(),
        "isi": isi,
        "lampiran": lampiran.strip() or None,
        "status": status,
    }
    r = await api_post(request, "/api/surat", json=payload)
    if r.status_code not in (200, 201):
        return templates.TemplateResponse(
            request, "surat/form.html",
            {"user": user, "surat": payload, "form_title": "Tambah Surat",
             "form_action": "/apps/tata-usaha", "error": r.text[:200]})
    return _redirect("Surat berhasil ditambah")


@router.get("/{surat_id}")
async def surat_detail(
    request: Request,
    surat_id: int,
    user: dict = Depends(require_permission_web("surat.view")),
):
    """Detail surat + lampiran (iframe) + disposisi."""
    r = await api_get(request, f"/api/surat/{surat_id}")
    if r.status_code != 200:
        return _redirect("Surat tidak ditemukan", "error")
    surat = r.json()
    return templates.TemplateResponse(
        request,
        "surat/detail.html",
        {"user": user, "surat": surat},
    )


@router.post("/{surat_id}/disposisi")
async def surat_disposisi(
    request: Request,
    surat_id: int,
    kepada: str = Form(...),
    catatan: str = Form(""),
    user: dict = Depends(require_permission_web("surat.disposisi")),
):
    """Submit disposisi."""
    await api_post(request, f"/api/surat/{surat_id}/disposisi",
                   json={"kepada": kepada, "catatan": catatan})
    return _redirect("Disposisi disimpan", path=f"/apps/tata-usaha/{surat_id}")


@router.post("/{surat_id}/hapus")
async def surat_delete(
    request: Request,
    surat_id: int,
    user: dict = Depends(require_permission_web("surat.delete")),
):
    await api_delete(request, f"/api/surat/{surat_id}")
    return _redirect("Surat dihapus")
