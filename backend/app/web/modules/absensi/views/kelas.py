"""Kelas view: list + form + detail + naik kelas wizard."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_delete, api_get, api_get_raw, api_patch, api_post
from ....core.deps import get_current_user_web, require_login_web, require_permission_web
from ....core.templates import templates

router = APIRouter(tags=["web-data-kelas"])


def _redirect(msg: str, type_: str = "success", path: str = "/madrasah-app/data/kelas"):
    return RedirectResponse(
        url=f"{path}?msg={msg.replace(' ', '+')}&type={type_}",
        status_code=303,
    )


@router.get("")
async def kelas_list(
    request: Request,
    tahun_ajaran_id: int | None = None,
    user: dict = Depends(require_permission_web("kelas.view", "kelas.create", "kelas.update", "kelas.delete", "kelas.naik")),
):
    """Daftar kelas. Filter by tahun ajaran (default: aktif)."""
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_ajaran_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_ajaran_list if ta.get("is_active")), None)
    if tahun_ajaran_id is None and tahun_aktif:
        tahun_ajaran_id = tahun_aktif["id"]

    params = {}
    if tahun_ajaran_id:
        params["tahun_ajaran_id"] = tahun_ajaran_id
    kelas_r = await api_get(request, "/api/kelas", **params)
    kelas_list = kelas_r.json() if kelas_r.status_code == 200 else []

    # Ambil data guru untuk dropdown wali kelas
    guru_r = await api_get(request, "/api/guru")
    guru_list = guru_r.json() if guru_r.status_code == 200 else []

    return templates.TemplateResponse(
        request,
        "kelas/list.html",
        {
            "user": user,
            "kelas_list": kelas_list,
            "guru_list": guru_list,
            "tahun_ajaran_list": tahun_ajaran_list,
            "tahun_aktif_id": tahun_aktif["id"] if tahun_aktif else None,
            "tahun_aktif_nama": tahun_aktif["nama"] if tahun_aktif else "",
            "tahun_ajaran_id": tahun_ajaran_id,
        },
    )


@router.get("/baru")
async def kelas_baru(
    request: Request,
    user: dict = Depends(require_permission_web("kelas.view")),
):
    """Form tambah kelas baru (admin only)."""
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_ajaran_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_ajaran_list if ta.get("is_active")), None)
    guru_r = await api_get(request, "/api/guru")
    guru_list = guru_r.json() if guru_r.status_code == 200 else []
    return templates.TemplateResponse(
        request,
        "kelas/form.html",
        {
            "user": user,
            "kelas": None,
            "guru_list": guru_list,
            "tahun_ajaran_list": tahun_ajaran_list,
            "tahun_aktif_id": tahun_aktif["id"] if tahun_aktif else None,
            "form_title": "Tambah Kelas",
            "form_action": "/madrasah-app/data/kelas",
        },
    )


@router.post("")
async def kelas_create(
    request: Request,
    nama_kelas: str = Form(...),
    wali_guru_id: str = Form(""),
    tahun_ajaran_id: str = Form(""),
    user: dict = Depends(require_permission_web("kelas.view", "kelas.create", "kelas.update", "kelas.delete", "kelas.naik")),
):
    """Submit form tambah kelas."""
    payload = {
        "nama_kelas": nama_kelas.strip(),
        "wali_guru_id": int(wali_guru_id) if wali_guru_id else None,
        "tahun_ajaran_id": int(tahun_ajaran_id) if tahun_ajaran_id else None,
    }
    r = await api_post(request, "/api/kelas", json=payload)
    if r.status_code in (200, 201):
        return _redirect(f"Kelas {nama_kelas} berhasil ditambahkan")
    detail = "Gagal menambahkan kelas"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    ta_r = await api_get(request, "/api/tahun-ajaran")
    guru_r = await api_get(request, "/api/guru")
    return templates.TemplateResponse(
        request,
        "kelas/form.html",
        {
            "user": user,
            "kelas": {"nama_kelas": nama_kelas, "wali_guru_id": wali_guru_id,
                      "tahun_ajaran_id": tahun_ajaran_id},
            "guru_list": guru_r.json() if guru_r.status_code == 200 else [],
            "tahun_ajaran_list": ta_r.json() if ta_r.status_code == 200 else [],
            "tahun_aktif_id": int(tahun_ajaran_id) if tahun_ajaran_id else None,
            "form_title": "Tambah Kelas",
            "form_action": "/madrasah-app/data/kelas",
            "error": detail,
        },
        status_code=400,
    )


@router.get("/{kid}")
async def kelas_detail(
    request: Request,
    kid: int,
    tahun_ajaran_id: int | None = None,
    user: dict = Depends(require_login_web),
):
    """Detail kelas: roster + filter Lulus/Aktif + aksi.

    Catatan: API existing tidak punya GET /api/kelas/{id}, jadi kita ambil
    dari list dan filter by id (efisien karena data kecil, max ~30 kelas).
    """
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_ajaran_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_ajaran_list if ta.get("is_active")), None)

    # Ambil list kelas (semua TA), cari by id
    list_r = await api_get(request, "/api/kelas")
    if list_r.status_code != 200:
        return _redirect("Gagal memuat data kelas", "error")
    all_kelas = list_r.json()
    kelas = next((k for k in all_kelas if k["id"] == kid), None)
    if not kelas:
        return _redirect("Kelas tidak ditemukan", "error")

    # Ambil roster (semua status)
    params = {"kelas_id": kid, "per_page": 200}
    murid_r = await api_get(request, "/api/murid", **params)
    semua_murid = murid_r.json() if murid_r.status_code == 200 else []
    items = semua_murid.get("items", [])

    return templates.TemplateResponse(
        request,
        "kelas/detail.html",
        {
            "user": user,
            "kelas": kelas,
            "tahun_ajaran_list": tahun_ajaran_list,
            "tahun_aktif": tahun_aktif,
            "items": items,
            "all_count": len(items),
            "active_count": sum(1 for m in items if m.get("is_active")),
            "lulus_count": sum(1 for m in items if not m.get("is_active")),
        },
    )


@router.get("/{kid}/edit")
async def kelas_edit(
    request: Request,
    kid: int,
    user: dict = Depends(require_permission_web("kelas.view")),
):
    """Form edit kelas (admin only).

    Ambil data dari list (no GET single endpoint di API existing).
    """
    list_r = await api_get(request, "/api/kelas")
    if list_r.status_code != 200:
        return _redirect("Gagal memuat data kelas", "error")
    kelas = next((k for k in list_r.json() if k["id"] == kid), None)
    if not kelas:
        return _redirect("Kelas tidak ditemukan", "error")

    ta_r = await api_get(request, "/api/tahun-ajaran")
    guru_r = await api_get(request, "/api/guru")
    return templates.TemplateResponse(
        request,
        "kelas/form.html",
        {
            "user": user,
            "kelas": kelas,
            "guru_list": guru_r.json() if guru_r.status_code == 200 else [],
            "tahun_ajaran_list": ta_r.json() if ta_r.status_code == 200 else [],
            "tahun_aktif_id": None,
            "form_title": "Edit Kelas",
            "form_action": f"/madrasah-app/data/kelas/{kid}",
        },
    )


@router.post("/{kid}")
async def kelas_update(
    request: Request,
    kid: int,
    nama_kelas: str = Form(...),
    wali_guru_id: str = Form(""),
    tahun_ajaran_id: str = Form(""),
    user: dict = Depends(require_permission_web("kelas.view", "kelas.create", "kelas.update", "kelas.delete", "kelas.naik")),
):
    """Submit form edit kelas."""
    payload = {
        "nama_kelas": nama_kelas.strip(),
        "wali_guru_id": int(wali_guru_id) if wali_guru_id else None,
    }
    r = await api_patch(request, f"/api/kelas/{kid}", json=payload)
    if r.status_code == 200:
        return _redirect(f"Kelas {nama_kelas} berhasil diperbarui")
    detail = "Gagal memperbarui kelas"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")


@router.post("/{kid}/hapus")
async def kelas_hapus(
    request: Request,
    kid: int,
    user: dict = Depends(require_permission_web("kelas.view", "kelas.create", "kelas.update", "kelas.delete", "kelas.naik")),
):
    """Hapus kelas (admin only). Gagal kalau masih ada murid aktif."""
    r = await api_delete(request, f"/api/kelas/{kid}")
    if r.status_code == 200:
        return _redirect("Kelas berhasil dihapus")
    detail = "Gagal menghapus kelas"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")


@router.post("/{kid}/luluskan")
async def kelas_luluskan(
    request: Request,
    kid: int,
    user: dict = Depends(require_permission_web("kelas.view", "kelas.create", "kelas.update", "kelas.delete", "kelas.naik")),
):
    """Luluskan semua murid aktif di kelas (admin only)."""
    r = await api_post(request, f"/api/kelas/{kid}/luluskan")
    if r.status_code == 200:
        try:
            n = r.json().get("lulus", 0)
            return _redirect(f"{n} murid berhasil diluluskan")
        except Exception:
            return _redirect("Siswa diluluskan")
    detail = "Gagal meluluskan"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")


# ── Naik Kelas Wizard ────────────────────────────────────────────────


@router.get("/naik-kelas")
async def naik_kelas_wizard(
    request: Request,
    user: dict = Depends(require_permission_web("kelas.view")),
):
    """Wizard naik kelas: pilih TA tujuan + mapping kelas."""
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_ajaran_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_ajaran_list if ta.get("is_active")), None)

    # Default TA sumber = tahun ajaran aktif, TA tujuan = tahun ajaran aktif juga
    # User bisa pilih manual
    if tahun_aktif:
        sumber_id = str(tahun_aktif["id"])
    else:
        sumber_id = ""

    # Ambil kelas dari TA sumber
    kelas_sumber_r = await api_get(request, "/api/kelas",
                                    tahun_ajaran_id=sumber_id)
    kelas_sumber = kelas_sumber_r.json() if kelas_sumber_r.status_code == 200 else []

    # Ambil semua kelas (untuk TA tujuan)
    kelas_all_r = await api_get(request, "/api/kelas")
    kelas_all = kelas_all_r.json() if kelas_all_r.status_code == 200 else []

    return templates.TemplateResponse(
        request,
        "kelas/naik_kelas.html",
        {
            "user": user,
            "tahun_ajaran_list": tahun_ajaran_list,
            "tahun_aktif_id": tahun_aktif["id"] if tahun_aktif else None,
            "sumber_id": sumber_id,
            "tujuan_id": str(tahun_aktif["id"]) if tahun_aktif else "",
            "kelas_sumber": kelas_sumber,
            "kelas_all": kelas_all,
            "preview": None,
        },
    )


@router.post("/naik-kelas-preview")
async def naik_kelas_preview(
    request: Request,
    tahun_ajaran_id_sumber: int = Form(...),
    tahun_ajaran_id_tujuan: int = Form(...),
    user: dict = Depends(require_permission_web("kelas.view", "kelas.create", "kelas.update", "kelas.delete", "kelas.naik")),
):
    """Preview mapping sebelum commit."""
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_ajaran_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_ajaran_list if ta.get("is_active")), None)
    kelas_sumber_r = await api_get(request, "/api/kelas",
                                    tahun_ajaran_id=tahun_ajaran_id_sumber)
    kelas_sumber = kelas_sumber_r.json() if kelas_sumber_r.status_code == 200 else []
    kelas_all_r = await api_get(request, "/api/kelas")
    kelas_all = kelas_all_r.json() if kelas_all_r.status_code == 200 else []

    # Default mapping: increment numeric suffix (7A → 8A)
    # atau pass ke tujuan kalau di TA tujuan belum ada
    sumber_by_id = {k["id"]: k for k in kelas_sumber}
    tujuan_by_id = {k["id"]: k for k in kelas_all if k.get("tahun_ajaran_id") == tahun_ajaran_id_tujuan}
    tujuan_by_nama = {k["nama_kelas"]: k for k in tujuan_by_id.values()}

    import re
    def _next_name(name: str) -> str:
        m = re.match(r"^(\d+)", name)
        if m:
            return str(int(m.group(1)) + 1) + name[m.end():]
        return name + " (lanjut)"

    items = []
    for k in kelas_sumber:
        suggested = _next_name(k["nama_kelas"])
        # Cek apakah ada di TA tujuan
        existing = tujuan_by_nama.get(suggested)
        items.append({
            "sumber_id": k["id"],
            "sumber_nama": k["nama_kelas"],
            "sumber_jumlah": k.get("jumlah_murid", 0),
            "suggested_nama": suggested,
            "tujuan_id": existing["id"] if existing else None,
            "tujuan_nama": suggested,
            "tujuan_exists": existing is not None,
            "luluskan": re.match(r"^9", k["nama_kelas"]) is not None,  # kelas 9 = lulus
        })

    return templates.TemplateResponse(
        request,
        "kelas/naik_kelas.html",
        {
            "user": user,
            "tahun_ajaran_list": tahun_ajaran_list,
            "tahun_aktif_id": tahun_aktif["id"] if tahun_aktif else None,
            "sumber_id": str(tahun_ajaran_id_sumber),
            "tujuan_id": str(tahun_ajaran_id_tujuan),
            "kelas_sumber": kelas_sumber,
            "kelas_all": kelas_all,
            "preview": {"items": items, "tujuan_ta": next(
                (ta for ta in tahun_ajaran_list if ta["id"] == tahun_ajaran_id_tujuan), None)},
        },
    )


@router.post("/naik-kelas-commit")
async def naik_kelas_commit(
    request: Request,
    tahun_ajaran_id_tujuan: int = Form(...),
    user: dict = Depends(require_permission_web("kelas.view", "kelas.create", "kelas.update", "kelas.delete", "kelas.naik")),
):
    """Commit naik kelas dari form submission."""
    form_data = await request.form()
    items = []
    i = 0
    while f"items[{i}][dari_kelas_id]" in form_data:
        items.append({
            "dari_kelas_id": int(form_data[f"items[{i}][dari_kelas_id]"]),
            "ke_kelas_id": int(form_data[f"items[{i}][ke_kelas_id]"]) if form_data.get(f"items[{i}][ke_kelas_id]") else None,
            "ke_nama_kelas": form_data.get(f"items[{i}][ke_nama_kelas]", ""),
            "luluskan": form_data.get(f"items[{i}][luluskan]") == "true",
        })
        i += 1

    if not items:
        return _redirect("Tidak ada kelas untuk dinaikkan", "error")

    payload = {"tahun_ajaran_id": tahun_ajaran_id_tujuan, "items": items}
    r = await api_post(request, "/api/kelas/naik-kelas", json=payload)

    if r.status_code == 200:
        try:
            result = r.json()
            dipindah = sum(it.get("dipindah", 0) for it in result.get("items", []))
            diluluskan = sum(it.get("diluluskan", 0) for it in result.get("items", []))
            msg = f"Naik kelas selesai: {dipindah} dipindah, {diluluskan} diluluskan"
            if result.get("error"):
                msg += f", {len(result['error'])} error"
            return _redirect(msg)
        except Exception:
            return _redirect("Naik kelas selesai")
    detail = "Gagal naik kelas"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")