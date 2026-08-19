"""Role & Permission Management — UI Builder (Fase 3).

Halaman admin tenant untuk mengelola role custom + permission matrix.
- list: daftar role (sistem + custom)
- new: form buat role
- matrix: edit permission role (checkbox per kategori)
- delete: hapus role (kecuali sistem + jika ada guru)
"""
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse

from ....core.client import api_get, api_post, api_patch, api_delete
from ....core.deps import require_permission_web
from ....core.templates import templates

router = APIRouter(tags=["role-web"])


@router.get("")
async def role_list(request: Request,
                    user: dict = Depends(require_permission_web("role.view"))):
    """List semua role + count permission."""
    r = await api_get(request, "/api/roles")
    roles = r.json() if r.status_code == 200 else []
    return templates.TemplateResponse(
        request, "role/list.html",
        {"user": user, "roles": roles, "err": None})


@router.get("/new")
async def role_new(request: Request,
                   user: dict = Depends(require_permission_web("role.update"))):
    """Form create role."""
    return templates.TemplateResponse(
        request, "role/form.html",
        {"user": user, "role": None, "err": None})


@router.post("/new")
async def role_create(request: Request,
                      user: dict = Depends(require_permission_web("role.update"))):
    """Submit form create role."""
    form = await request.form()
    nama = (form.get("nama") or "").strip()
    label = (form.get("label") or "").strip()
    r = await api_post(request, "/api/roles", {"nama": nama, "label": label})
    if r.status_code in (200, 201):
        return RedirectResponse(
            "/madrasah-app/system/role", status_code=status.HTTP_303_SEE_OTHER)
    err = r.json().get("detail") if r.status_code >= 400 else None
    return templates.TemplateResponse(
        request, "role/form.html",
        {"user": user, "role": {"nama": nama, "label": label}, "err": err},
        status_code=r.status_code)


@router.get("/{role_id:int}/matrix")
async def role_matrix(request: Request, role_id: int,
                      user: dict = Depends(require_permission_web("role.view"))):
    """Halaman matrix: edit permission role (grouped by kategori)."""
    roles_r = await api_get(request, "/api/roles")
    if roles_r.status_code != 200:
        return RedirectResponse("/madrasah-app/system/role", status_code=303)
    roles = roles_r.json()
    role = next((r for r in roles if r["id"] == role_id), None)
    if not role:
        return templates.TemplateResponse(
            request, "error.html",
            {"user": user, "status_code": 404, "message": "Role tidak ditemukan"},
            status_code=404)

    perms_r = await api_get(request, "/api/roles/permissions")
    groups = perms_r.json() if perms_r.status_code == 200 else []
    total_perms = sum(len(g.get("perms", [])) for g in groups)

    selected_r = await api_get(request, f"/api/roles/{role_id}/permissions")
    selected = set(selected_r.json() if selected_r.status_code == 200 else [])

    gurus_r = await api_get(request, f"/api/roles/{role_id}/guru")
    gurus = gurus_r.json() if gurus_r.status_code == 200 else []

    return templates.TemplateResponse(
        request, "role/matrix.html",
        {"user": user, "role": role, "groups": groups,
         "selected": selected, "gurus": gurus, "total_perms": total_perms,
         "err": None})


@router.post("/{role_id:int}/matrix")
async def role_matrix_save(request: Request, role_id: int,
                           user: dict = Depends(require_permission_web("role.update"))):
    """Submit matrix: update permission role (atomic replace)."""
    form = await request.form()
    codes = list(form.getlist("permission"))
    r = await api_post(request, f"/api/roles/{role_id}/permissions",
                       {"permissions": codes})
    if r.status_code == 200:
        return RedirectResponse(
            f"/madrasah-app/system/role/{role_id}/matrix?ok=1",
            status_code=status.HTTP_303_SEE_OTHER)
    err = r.json().get("detail") if r.status_code >= 400 else "Gagal menyimpan"
    return templates.TemplateResponse(
        request, "role/matrix.html",
        {"user": user, "role": {"id": role_id}, "groups": [],
         "selected": set(codes), "gurus": [], "err": err},
        status_code=r.status_code)


@router.get("/{role_id:int}/edit")
async def role_edit(request: Request, role_id: int,
                    user: dict = Depends(require_permission_web("role.view"))):
    """Form edit label role."""
    roles_r = await api_get(request, "/api/roles")
    roles = roles_r.json() if roles_r.status_code == 200 else []
    role = next((r for r in roles if r["id"] == role_id), None)
    if not role:
        return templates.TemplateResponse(
            request, "error.html",
            {"user": user, "status_code": 404, "message": "Role tidak ditemukan"},
            status_code=404)
    return templates.TemplateResponse(
        request, "role/form.html",
        {"user": user, "role": role, "err": None})


@router.post("/{role_id:int}/edit")
async def role_update(request: Request, role_id: int,
                      user: dict = Depends(require_permission_web("role.update"))):
    """Submit form edit role."""
    form = await request.form()
    label = (form.get("label") or "").strip()
    r = await api_patch(request, f"/api/roles/{role_id}", {"label": label})
    if r.status_code == 200:
        return RedirectResponse(
            "/madrasah-app/system/role", status_code=status.HTTP_303_SEE_OTHER)
    err = r.json().get("detail") if r.status_code >= 400 else None
    return templates.TemplateResponse(
        request, "role/form.html",
        {"user": user, "role": {"id": role_id, "label": label}, "err": err},
        status_code=r.status_code)


@router.post("/{role_id:int}/delete")
async def role_delete(request: Request, role_id: int,
                      user: dict = Depends(require_permission_web("role.update"))):
    """Hapus role (kecuali sistem + jika ada guru)."""
    r = await api_delete(request, f"/api/roles/{role_id}")
    if r.status_code == 204:
        return RedirectResponse(
            "/madrasah-app/system/role", status_code=status.HTTP_303_SEE_OTHER)
    # Show error (simplified: back to list with flash)
    err = r.json().get("detail") if r.status_code >= 400 else "Gagal"
    roles_r = await api_get(request, "/api/roles")
    roles = roles_r.json() if roles_r.status_code == 200 else []
    return templates.TemplateResponse(
        request, "role/list.html",
        {"user": user, "roles": roles, "err": err},
        status_code=r.status_code)
