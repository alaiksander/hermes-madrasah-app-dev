"""Ekstrakurikuler — web views."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_delete, api_get, api_post
from ....core.deps import require_permission_web
from ....core.templates import templates

router = APIRouter(tags=["web-ekskul"])


def _redirect(msg: str, type_: str = "success", path: str = "/apps/ekskul"):
    return RedirectResponse(
        url=f"{path}?msg={msg.replace(' ', '+')}&type={type_}",
        status_code=303,
    )


@router.get("")
async def ekskul_list(
    request: Request,
    user: dict = Depends(require_permission_web("ekskul.view")),
):
    r = await api_get(request, "/api/ekskul")
    ekskul_list = r.json() if r.status_code == 200 else []
    return templates.TemplateResponse(
        request, "ekskul/list.html",
        {"user": user, "ekskul_list": ekskul_list},
    )


@router.get("/tambah")
async def ekskul_baru(
    request: Request,
    user: dict = Depends(require_permission_web("ekskul.kelola")),
):
    guru_r = await api_get(request, "/api/guru")
    guru_list = guru_r.json() if guru_r.status_code == 200 else []
    return templates.TemplateResponse(
        request, "ekskul/form.html",
        {"user": user, "ekskul": None, "guru_list": guru_list,
         "form_title": "Tambah Ekskul", "form_action": "/apps/ekskul"},
    )


@router.post("")
async def ekskul_create(
    request: Request,
    nama: str = Form(...),
    pembina_guru_id: str = Form(""),
    deskripsi: str = Form(""),
    kuota: int = Form(0),
    hari: str = Form(""),
    jam_mulai: str = Form(""),
    jam_selesai: str = Form(""),
    is_wajib: str = Form(""),
    wajib_tingkat: str = Form(""),
    user: dict = Depends(require_permission_web("ekskul.kelola")),
):
    payload = {
        "nama": nama.strip(),
        "pembina_guru_id": int(pembina_guru_id) if pembina_guru_id else None,
        "deskripsi": deskripsi or None,
        "kuota": kuota,
        "hari": hari or None,
        "jam_mulai": jam_mulai or None,
        "jam_selesai": jam_selesai or None,
        "is_wajib": is_wajib == "1",
        "wajib_tingkat": wajib_tingkat or None,
    }
    r = await api_post(request, "/api/ekskul", json=payload)
    if r.status_code not in (200, 201):
        return templates.TemplateResponse(
            request, "ekskul/form.html",
            {"user": user, "ekskul": payload, "guru_list": [],
             "form_title": "Tambah Ekskul", "form_action": "/apps/ekskul",
             "error": r.text[:200]})
    return _redirect("Ekskul berhasil ditambah")


@router.get("/{ekskul_id}")
async def ekskul_detail(
    request: Request,
    ekskul_id: int,
    user: dict = Depends(require_permission_web("ekskul.view")),
):
    r = await api_get(request, f"/api/ekskul/{ekskul_id}")
    if r.status_code != 200:
        return _redirect("Ekskul tidak ditemukan", "error")
    ekskul = r.json()
    anggota_r = await api_get(request, f"/api/ekskul/{ekskul_id}/anggota")
    anggota = anggota_r.json() if anggota_r.status_code == 200 else []
    kegiatan_r = await api_get(request, f"/api/ekskul/{ekskul_id}/kegiatan")
    kegiatan = kegiatan_r.json() if kegiatan_r.status_code == 200 else []
    murid_r = await api_get(request, "/api/murid")
    murid_data = murid_r.json() if murid_r.status_code == 200 else {}
    # API murid: {total, items:[...]} — ekstrak items
    murid_list = murid_data.get("items", murid_data if isinstance(murid_data, list) else [])
    import json as _json
    return templates.TemplateResponse(
        request, "ekskul/detail.html",
        {"user": user, "ekskul": ekskul, "anggota": anggota,
         "kegiatan": kegiatan, "murid_list": murid_list,
         "murid_list_json": _json.dumps(murid_list)},
    )


@router.post("/{ekskul_id}/masukkan-tingkat")
async def anggota_bulk_tingkat(
    request: Request,
    ekskul_id: int,
    tingkat: str = Form(...),
    user: dict = Depends(require_permission_web("ekskul.kelola")),
):
    r = await api_post(request, f"/api/ekskul/{ekskul_id}/masukkan-tingkat",
                       json={"tingkat": tingkat})
    d = r.json() if r.status_code in (200, 201) else {}
    n = d.get("ditambahkan", 0)
    return _redirect(f"{n} murid ditambahkan", path=f"/apps/ekskul/{ekskul_id}")


@router.post("/{ekskul_id}/anggota")
async def anggota_add(
    request: Request,
    ekskul_id: int,
    murid_id: int = Form(...),
    user: dict = Depends(require_permission_web("ekskul.kelola")),
):
    await api_post(request, f"/api/ekskul/{ekskul_id}/anggota",
                   json={"murid_id": murid_id})
    return _redirect("Anggota ditambahkan", path=f"/apps/ekskul/{ekskul_id}")


@router.post("/{ekskul_id}/anggota/{anggota_id}/hapus")
async def anggota_remove(
    request: Request,
    ekskul_id: int,
    anggota_id: int,
    user: dict = Depends(require_permission_web("ekskul.kelola")),
):
    await api_delete(request, f"/api/ekskul/{ekskul_id}/anggota/{anggota_id}")
    return _redirect("Anggota dihapus", path=f"/apps/ekskul/{ekskul_id}")


@router.post("/{ekskul_id}/kegiatan")
async def kegiatan_add(
    request: Request,
    ekskul_id: int,
    tanggal: str = Form(...),
    topik: str = Form(""),
    user: dict = Depends(require_permission_web("ekskul.kelola")),
):
    await api_post(request, f"/api/ekskul/{ekskul_id}/kegiatan",
                   json={"tanggal": tanggal, "topik": topik or None})
    return _redirect("Kegiatan ditambahkan", path=f"/apps/ekskul/{ekskul_id}")


@router.post("/{ekskul_id}/kegiatan/{kegiatan_id}/presensi")
async def presensi_input(
    request: Request,
    ekskul_id: int,
    kegiatan_id: int,
    hadir: list[int] = Form([]),
    user: dict = Depends(require_permission_web("ekskul.presensi")),
):
    await api_post(request, f"/api/ekskul/{ekskul_id}/kegiatan/{kegiatan_id}/presensi",
                   json={"hadir": hadir})
    return _redirect("Presensi disimpan", path=f"/apps/ekskul/{ekskul_id}")
