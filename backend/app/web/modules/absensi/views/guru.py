"""Guru view: list + form + edit + reset password + arsipkan."""
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response

from ....core.client import api_delete, api_get, api_get_raw, api_patch, api_post
from ....core.deps import require_permission_web, require_login_web
from ....core.templates import templates

router = APIRouter(tags=["web-data-guru"])


def _redirect(msg: str, type_: str = "success", path: str = "/madrasah-app/data/guru"):
    return RedirectResponse(
        url=f"{path}?msg={msg.replace(' ', '+')}&type={type_}",
        status_code=303,
    )


@router.get("")
async def guru_list(
    request: Request,
    user: dict = Depends(require_permission_web("guru.view")),
):
    """Daftar semua guru + admin (admin only)."""
    r = await api_get(request, "/api/guru")
    guru_list = r.json() if r.status_code == 200 else []

    # Wali kelas: hanya tahun ajaran aktif, tampilkan NAMA kelasnya
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_ajaran_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_ajaran_list if ta.get("is_active")), None)
    kelas_params = {}
    if tahun_aktif:
        kelas_params["tahun_ajaran_id"] = tahun_aktif["id"]
    kelas_r = await api_get(request, "/api/kelas", **kelas_params)
    kelas_list = kelas_r.json() if kelas_r.status_code == 200 else []

    wali_map: dict[int, list[str]] = {}
    for k in kelas_list:
        wid = k.get("wali_guru_id")
        if wid:
            wali_map.setdefault(wid, []).append(k.get("nama_kelas", ""))

    for g in guru_list:
        g["kelas_wali_list"] = sorted(wali_map.get(g["id"], []))

    return templates.TemplateResponse(
        request,
        "guru/list.html",
        {
            "user": user,
            "guru_list": guru_list,
            "current_user_id": user["id"],
        },
    )


@router.get("/baru")
async def guru_baru(
    request: Request,
    user: dict = Depends(require_permission_web("guru.view")),
):
    """Form tambah guru/admin baru (admin only)."""
    return templates.TemplateResponse(
        request,
        "guru/form.html",
        {
            "user": user,
            "guru": None,
            "form_title": "Tambah Guru",
            "form_action": "/madrasah-app/data/guru",
            "show_password": True,
            "is_self": False,
        },
    )


@router.post("")
async def guru_create(
    request: Request,
    nama: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("guru"),
    user: dict = Depends(require_permission_web("guru.view", "guru.create", "guru.update", "guru.delete", "guru.reset")),
):
    """Submit form tambah guru/admin."""
    payload = {
        "nama": nama.strip(),
        "username": username.strip(),
        "password": password,
        "role": role,
    }
    r = await api_post(request, "/api/guru", json=payload)
    if r.status_code in (200, 201):
        return _redirect(f"Guru {nama} berhasil ditambahkan")
    detail = "Gagal menambah guru"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return templates.TemplateResponse(
        request,
        "guru/form.html",
        {
            "user": user,
            "guru": payload,
            "form_title": "Tambah Guru",
            "form_action": "/madrasah-app/data/guru",
            "show_password": True,
            "is_self": False,
            "error": detail,
        },
        status_code=400,
    )


@router.get("/{gid}/edit")
async def guru_edit(
    request: Request,
    gid: int,
    user: dict = Depends(require_permission_web("guru.view")),
):
    """Form edit guru/admin (admin only)."""
    list_r = await api_get(request, "/api/guru")
    if list_r.status_code != 200:
        return _redirect("Gagal memuat data guru", "error")
    guru = next((g for g in list_r.json() if g["id"] == gid), None)
    if not guru:
        return _redirect("Guru tidak ditemukan", "error")

    return templates.TemplateResponse(
        request,
        "guru/form.html",
        {
            "user": user,
            "guru": guru,
            "form_title": "Edit Guru",
            "form_action": f"/madrasah-app/data/guru/{gid}",
            "show_password": False,
            "is_self": gid == user["id"],
        },
    )


@router.post("/{gid}")
async def guru_update(
    request: Request,
    gid: int,
    nama: str = Form(...),
    username: str = Form(...),
    role: str = Form("guru"),
    user: dict = Depends(require_permission_web("guru.view", "guru.create", "guru.update", "guru.delete", "guru.reset")),
):
    """Submit form edit guru."""
    payload = {
        "nama": nama.strip(),
        "username": username.strip(),
        "role": role,
    }
    r = await api_patch(request, f"/api/guru/{gid}", json=payload)
    if r.status_code == 200:
        return _redirect(f"Data guru {nama} diperbarui")
    detail = "Gagal memperbarui guru"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")


@router.post("/{gid}/reset-password")
async def guru_reset_password(
    request: Request,
    gid: int,
    new_password: str = Form(...),
    user: dict = Depends(require_permission_web("guru.view", "guru.create", "guru.update", "guru.delete", "guru.reset")),
):
    """Reset password guru (admin only)."""
    payload = {"password": new_password}
    r = await api_post(request, f"/api/guru/{gid}/reset-password", json=payload)
    if r.status_code == 200:
        return _redirect("Password berhasil direset")
    detail = "Gagal reset password"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")


@router.post("/{gid}/aktifkan")
async def guru_aktifkan(
    request: Request,
    gid: int,
    user: dict = Depends(require_permission_web("guru.view", "guru.create", "guru.update", "guru.delete", "guru.reset")),
):
    """Aktifkan kembali guru yang diarsipkan."""
    r = await api_patch(request, f"/api/guru/{gid}", json={"is_active": True})
    if r.status_code == 200:
        return _redirect("Guru diaktifkan kembali")
    detail = "Gagal mengaktifkan"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")


@router.post("/{gid}/hapus")
async def guru_hapus(
    request: Request,
    gid: int,
    user: dict = Depends(require_permission_web("guru.view", "guru.create", "guru.update", "guru.delete", "guru.reset")),
):
    """Arsipkan guru (soft-delete). Wali kelas dikosongkan."""
    if gid == user["id"]:
        return _redirect("Tidak dapat menonaktifkan akun sendiri", "error")
    r = await api_delete(request, f"/api/guru/{gid}")
    if r.status_code == 200:
        return _redirect("Guru berhasil diarsipkan")
    detail = "Gagal mengarsipkan guru"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")


@router.post("/{gid}/hapus-permanen")
async def guru_hapus_permanen(
    request: Request,
    gid: int,
    konfirmasi: str = Form(...),
    user: dict = Depends(require_permission_web("guru.view", "guru.create", "guru.update", "guru.delete", "guru.reset")),
):
    """Hapus guru PERMANEN — konfirmasi ketik username.

    Hanya untuk guru yang sudah diarsip. Ditolak kalau punya data absensi.
    """
    r = await api_delete(
        request,
        f"/api/guru/{gid}/permanen",
        json={"konfirmasi": konfirmasi.strip()},
    )
    if r.status_code == 200:
        from .....audit import log_action
        log_action(user, "hapus_guru_permanen_web",
                   f"Guru id={gid} dihapus permanen (konfirmasi '{konfirmasi}')")
        return _redirect("Guru dihapus permanen")
    detail = "Gagal menghapus guru"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")


@router.get("/guru-template-xlsx")
async def guru_template(
    request: Request,
    user: dict = Depends(require_permission_web("guru.view")),
):
    """Download template import guru (admin only).

    PENTING: pakai dash `/guru-template-xlsx` untuk hindari conflict
    dengan `/guru/{guru_id}` parameterized route.
    """
    content = await api_get_raw(request, "/api/guru/template.xlsx")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="template-import-guru.xlsx"'},
    )


@router.get("/guru-import")
async def guru_import_page(
    request: Request,
    user: dict = Depends(require_permission_web("guru.view")),
):
    """Halaman import guru dari Excel (admin only)."""
    return templates.TemplateResponse(
        request,
        "guru/import.html",
        {
            "user": user,
            "preview": None,
        },
    )


@router.post("/guru-import-preview")
async def guru_import_preview(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(require_permission_web("guru.view", "guru.create", "guru.update", "guru.delete", "guru.reset")),
):
    """Preview import guru (client-side parse via openpyxl)."""
    import io
    import openpyxl

    contents = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "guru/import.html",
            {
                "user": user,
                "preview": None,
                "error": f"File bukan Excel valid: {e}",
            },
            status_code=400,
        )

    if not rows:
        return templates.TemplateResponse(
            request,
            "guru/import.html",
            {"user": user, "preview": None, "error": "File Excel kosong"},
            status_code=400,
        )

    # Parse rows
    headers = [str(h or "").strip().lower() for h in rows[0]]
    norm = [h.replace("_", " ").replace("-", " ").strip() for h in headers]
    header_map = {
        "nama": "nama", "nama lengkap": "nama",
        "username": "username", "user": "username",
        "password": "password", "pw": "password",
        "role": "role", "jabatan": "role",
    }
    field_names = [header_map.get(h, h) for h in norm]

    # Cek username duplikat dengan existing
    existing_r = await api_get(request, "/api/guru")
    existing_usernames = {g["username"] for g in (existing_r.json() if existing_r.status_code == 200 else [])}

    items = []
    for r_idx, row in enumerate(rows[1:], start=2):
        if all(c is None or str(c).strip() == "" for c in row):
            continue
        item = {}
        for f_name, cell in zip(field_names, row):
            if f_name:
                item[f_name] = str(cell or "").strip()
        if not item.get("nama") and not item.get("username"):
            continue
        errors = []
        if not item.get("nama"):
            errors.append("Nama kosong")
        if not item.get("username"):
            errors.append("Username kosong")
        elif item["username"] in existing_usernames:
            errors.append("Username sudah ada")
        if item.get("role") and item["role"].lower() not in ("guru", "admin", ""):
            errors.append("Role harus 'guru' atau 'admin'")
        item["_row"] = r_idx
        item["_errors"] = errors
        item["_valid"] = len(errors) == 0
        item["_password_default"] = not item.get("password")
        items.append(item)

    return templates.TemplateResponse(
        request,
        "guru/import.html",
        {
            "user": user,
            "preview": {
                "filename": file.filename or "import.xlsx",
                "items": items,
                "total": len(items),
                "valid": sum(1 for it in items if it["_valid"]),
                "error_count": sum(1 for it in items if not it["_valid"]),
            },
            "raw_bytes": contents,
        },
    )


@router.post("/guru-import")
async def guru_import_commit(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(require_permission_web("guru.view", "guru.create", "guru.update", "guru.delete", "guru.reset")),
):
    """Commit import guru (forward ke API existing)."""
    contents = await file.read()
    import httpx
    async with httpx.AsyncClient(timeout=60) as c:
        token = request.cookies.get("madrasah_app_token")
        r = await c.post(
            "http://127.0.0.1:8010/api/guru/import",
            files={"file": (file.filename or "import.xlsx", contents,
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )

    if r.status_code == 200:
        try:
            result = r.json()
            added = result.get("ditambahkan", 0)
            skipped = result.get("sudah_ada", 0)
            msg = f"Import selesai: {added} ditambah, {skipped} dilewati"
            if result.get("error"):
                msg += f", {len(result['error'])} error"
            return _redirect(msg)
        except Exception:
            return _redirect("Import selesai")
    detail = "Gagal import"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")