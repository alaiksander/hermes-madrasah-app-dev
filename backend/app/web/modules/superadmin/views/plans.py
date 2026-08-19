"""Manajemen plan/paket untuk superadmin web panel."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_delete, api_get, api_patch, api_post
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


@router.get("/plans")
async def plans_list(
    request: Request,
    user: dict = Depends(require_super_admin_web),
):
    """List semua plan."""
    r = await api_get(request, "/api/super/plans")
    plans = r.json() if r.status_code == 200 else []
    return templates.TemplateResponse(
        request,
        "superadmin/plans/list.html",
        {"user": user, "plans": plans},
    )


@router.get("/plans/baru")
async def plans_form_baru(
    request: Request,
    user: dict = Depends(require_super_admin_web),
):
    """Form tambah plan."""
    return templates.TemplateResponse(
        request,
        "superadmin/plans/form.html",
        {"user": user, "plan": None, "form_title": "Tambah Plan"},
    )


@router.post("/plans")
async def plans_create(
    request: Request,
    nama: str = Form(...),
    label: str = Form(""),
    max_murid: int = Form(0),
    max_guru: int = Form(0),
    fitur: str = Form(""),
    user: dict = Depends(require_super_admin_web),
):
    """Buat plan baru."""
    fitur_list = [f.strip() for f in fitur.split("\n") if f.strip()]
    r = await api_post(
        request,
        "/api/super/plans",
        json={
            "nama": nama.strip().lower(),
            "label": label.strip(),
            "max_murid": max_murid or None,
            "max_guru": max_guru or None,
            "fitur": fitur_list,
        },
    )
    if r.status_code in (200, 201):
        _audit(user, "tambah_plan_web", f"Plan '{nama.strip().lower()}' dibuat")
        return _redirect("/madrasah-app/superadmin/plans",
                         f"Plan '{nama.strip().lower()}' berhasil dibuat")
    detail = "Gagal membuat plan"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/madrasah-app/superadmin/plans", detail, "error")


@router.get("/plans/{plan_id}/edit")
async def plans_edit_form(
    request: Request,
    plan_id: int,
    user: dict = Depends(require_super_admin_web),
):
    """Form edit plan."""
    r = await api_get(request, "/api/super/plans")
    plans = r.json() if r.status_code == 200 else []
    plan = next((p for p in plans if p.get("id") == plan_id), None)
    if not plan:
        return _redirect("/madrasah-app/superadmin/plans",
                         "Plan tidak ditemukan", "error")
    return templates.TemplateResponse(
        request,
        "superadmin/plans/form.html",
        {"user": user, "plan": plan, "form_title": f"Edit Plan {plan.get('nama')}"},
    )


@router.post("/plans/{plan_id}")
async def plans_update(
    request: Request,
    plan_id: int,
    label: str = Form(""),
    max_murid: int = Form(0),
    max_guru: int = Form(0),
    fitur: str = Form(""),
    user: dict = Depends(require_super_admin_web),
):
    """Update plan (nama tidak bisa diubah — itu identitas unik)."""
    fitur_list = [f.strip() for f in fitur.split("\n") if f.strip()]
    r = await api_patch(
        request,
        f"/api/super/plans/{plan_id}",
        json={
            "label": label.strip(),
            "max_murid": max_murid or None,
            "max_guru": max_guru or None,
            "fitur": fitur_list,
        },
    )
    if r.status_code == 200:
        _audit(user, "ubah_plan_web", f"Plan id={plan_id} diperbarui")
        return _redirect("/madrasah-app/superadmin/plans", "Plan diperbarui")
    detail = "Gagal update plan"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/madrasah-app/superadmin/plans", detail, "error")


@router.post("/plans/{plan_id}/hapus")
async def plans_delete(
    request: Request,
    plan_id: int,
    user: dict = Depends(require_super_admin_web),
):
    """Hapus plan (ditolak backend kalau dipakai tenant)."""
    r = await api_delete(
        request,
        f"/api/super/plans/{plan_id}",
        json={},
    )
    if r.status_code == 200:
        _audit(user, "hapus_plan_web", f"Plan id={plan_id} dihapus")
        return _redirect("/madrasah-app/superadmin/plans", "Plan dihapus")
    detail = "Gagal menghapus plan"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/madrasah-app/superadmin/plans", detail, "error")