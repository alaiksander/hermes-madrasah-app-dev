"""Web UI: Halaman Penugasan Mengajar (admin only) + view guru sendiri.

Routes:
- GET  /madrasah-app/pengampu                — list semua guru (dengan jumlah pengampu)
- GET  /madrasah-app/pengampu/{guru_id}      — detail 1 guru + form bulk edit
- POST /madrasah-app/pengampu/{guru_id}      — submit bulk (replace all)
- POST /madrasah-app/pengampu/{guru_id}/delete/{id} — hapus 1 item
- GET  /madrasah-app/pengampu/me             — pengampu sendiri (guru only)
"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_get, api_post
from ....core.deps import require_login_web, require_permission_web
from ....core.templates import templates

router = APIRouter(prefix="/pengampu")


def _redirect(msg: str, type_: str = "success", path: str = "/madrasah-app/pengampu"):
    return RedirectResponse(
        url=f"{path}?msg={msg.replace(' ', '+')}&type={type_}",
        status_code=303,
    )


async def _kelas_ta_aktif(request: Request) -> list:
    """List kelas tahun ajaran aktif."""
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_list if ta.get("is_active")), None)
    ta_id = tahun_aktif["id"] if tahun_aktif else None
    r = await api_get(request, "/api/kelas", tahun_ajaran_id=ta_id or "")
    return r.json() if r.status_code == 200 else []


@router.get("")
async def pengampu_list(
    request: Request,
    user: dict = Depends(require_permission_web("pengampu.kelola", "pengampu.view")),
):
    """List semua guru + ringkasan penugasan."""
    gurus_r = await api_get(request, "/api/guru")
    gurus = gurus_r.json() if gurus_r.status_code == 200 else []

    # Hitung pengampu per guru (TA aktif dari default filter di API)
    counts = {}
    r_all = await api_get(request, "/api/guru-pengampu", is_active=True)
    if r_all.status_code == 200:
        for p in r_all.json():
            gid = p["guru_id"]
            counts[gid] = counts.get(gid, 0) + 1

    return templates.TemplateResponse(
        request, "pengampu/list.html",
        {"request": request, "user": user, "gurus": gurus, "counts": counts},
    )


@router.get("/me")
async def pengampu_me(
    request: Request,
    user: dict = Depends(require_login_web),
):
    """Penugasan sendiri (guru only)."""
    r = await api_get(request, f"/api/guru-pengampu/guru/{user['id']}")
    pengampu = r.json() if r.status_code == 200 else []
    return templates.TemplateResponse(
        request, "pengampu/me.html",
        {"request": request, "user": user, "pengampu": pengampu},
    )


@router.get("/{guru_id}")
async def pengampu_edit(
    request: Request,
    guru_id: int,
    user: dict = Depends(require_permission_web("pengampu.kelola")),
):
    """Halaman edit pengampu untuk 1 guru — bulk form."""
    # Data guru
    gurus_r = await api_get(request, "/api/guru")
    gurus = gurus_r.json() if gurus_r.status_code == 200 else []
    guru = next((g for g in gurus if g["id"] == guru_id), None)
    if not guru:
        return _redirect("Guru tidak ditemukan", "error")

    # Mapel & kelas aktif
    mapel_r = await api_get(request, "/api/mapel")
    mapel_list = mapel_r.json() if mapel_r.status_code == 200 else []
    kelas_list = await _kelas_ta_aktif(request)

    # TA aktif
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_list if ta.get("is_active")), None)
    if not tahun_aktif:
        return _redirect("Tidak ada tahun ajaran aktif", "error")

    # Pengampu existing (TA aktif)
    r = await api_get(request, "/api/guru-pengampu/guru/" + str(guru_id),
                       tahun_ajaran_id=tahun_aktif["id"])
    pengampu_list = r.json() if r.status_code == 200 else []

    # Build set (mapel_id, kelas_id) untuk checkbox pre-check
    checked = {(p.get("mapel_id"), p["kelas_id"]) for p in pengampu_list if p.get("is_active", True)}

    return templates.TemplateResponse(
        request, "pengampu/edit.html",
        {
            "request": request, "user": user,
            "guru": guru, "mapel_list": mapel_list, "kelas_list": kelas_list,
            "tahun_aktif": tahun_aktif,
            "pengampu_list": pengampu_list,
            "checked": checked,
        },
    )


@router.post("/{guru_id}")
async def pengampu_save(
    request: Request,
    guru_id: int,
    user: dict = Depends(require_permission_web("pengampu.kelola")),
):
    """Submit bulk — replace semua pengampu guru di TA aktif.

    Menerima items_json (JSON-encoded list) dari form baru (multi-select
    + tabel). Backward-compat: juga terima format lama `p_<mapel>_<kelas>`.
    """
    import json as _json
    form = await request.form()
    ta_id = int(form.get("tahun_ajaran_id"))

    items = []
    items_json = form.get("items_json")
    if items_json:
        try:
            raw = _json.loads(items_json)
            for it in raw:
                items.append({
                    "guru_id": guru_id,
                    "mapel_id": it.get("mapel_id"),
                    "kelas_id": int(it.get("kelas_id")),
                    "tahun_ajaran_id": ta_id,
                    "is_wali": bool(it.get("is_wali", False)),
                })
        except (_json.JSONDecodeError, TypeError, ValueError):
            pass
    else:
        # Backward-compat: format lama
        for key in form.keys():
            if key.startswith("p_"):
                parts = key.split("_")
                if len(parts) == 3:
                    try:
                        mapel_id = int(parts[1]) if parts[1] != "0" else None
                        kelas_id = int(parts[2])
                        items.append({
                            "guru_id": guru_id,
                            "mapel_id": mapel_id,
                            "kelas_id": kelas_id,
                            "tahun_ajaran_id": ta_id,
                            "is_wali": mapel_id is None,
                        })
                    except ValueError:
                        pass

    r = await api_post(
        request, "/api/guru-pengampu/bulk",
        json={
            "guru_id": guru_id,
            "tahun_ajaran_id": ta_id,
            "items": items,
        },
    )
    if r.status_code in (200, 201):
        return _redirect(f"Penugasan diperbarui ({len(items)} item)",
                          "success",
                          f"/madrasah-app/pengampu/{guru_id}")
    return _redirect(f"Gagal simpan: {r.text[:80]}", "error",
                     f"/madrasah-app/pengampu/{guru_id}")


@router.post("/{guru_id}/delete/{pengampu_id}")
async def pengampu_delete_one(
    request: Request,
    guru_id: int,
    pengampu_id: int,
    user: dict = Depends(require_permission_web("pengampu.kelola")),
):
    """Hapus 1 item pengampu."""
    from ....core.client import api_delete
    r = await api_delete(request, f"/api/guru-pengampu/{pengampu_id}")
    if r.status_code in (200, 204):
        return _redirect("Item dihapus", "success", f"/madrasah-app/pengampu/{guru_id}")
    return _redirect(f"Gagal hapus: {r.text[:80]}", "error",
                     f"/madrasah-app/pengampu/{guru_id}")
