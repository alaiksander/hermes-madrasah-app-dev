"""Manajemen tenant untuk superadmin web panel."""
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_delete, api_get, api_patch, api_post
from ....core.deps import require_super_admin_web
from ....core.templates import templates
from .....audit import log_action


def _audit(user: dict, aksi: str, rincian: str) -> None:
    """Audit aksi mutasi superadmin tanpa mengganggu response utama."""
    log_action(user, aksi, rincian, tenant="")


# Semua mutasi di view ini memanggil _audit setelah API berhasil.

router = APIRouter()


def _redirect(path: str, msg: str = "", type_: str = "success"):
    # Sanitasi: msg bisa dict/list dari API error → convert ke string aman
    if not isinstance(msg, str):
        if isinstance(msg, dict):
            msg = msg.get("detail", str(msg))
        else:
            msg = str(msg)
    suffix = f"?msg={msg.replace(' ', '+')}&type={type_}" if msg else ""
    return RedirectResponse(f"{path}{suffix}", status_code=303)


@router.get("/tenants")
async def tenants_list(
    request: Request,
    q: str | None = None,
    plan: str | None = None,
    user: dict = Depends(require_super_admin_web),
):
    """List semua tenant."""
    r = await api_get(request, "/api/super/tenants")
    tenants = r.json() if r.status_code == 200 else []

    # Filter client-side (Fuse-like, sederhana)
    if q:
        ql = q.lower()
        tenants = [t for t in tenants if ql in t.get("nama", "").lower()
                   or ql in t.get("kode", "").lower()]
    if plan:
        tenants = [t for t in tenants if t.get("plan") == plan]

    return templates.TemplateResponse(
        request,
        "superadmin/tenants/list.html",
        {"user": user, "tenants": tenants, "q": q or "", "plan": plan or ""},
    )


@router.get("/tenants/baru")
async def tenants_form_baru(
    request: Request,
    user: dict = Depends(require_super_admin_web),
):
    """Form tambah tenant."""
    plans_r = await api_get(request, "/api/super/plans")
    plans = plans_r.json() if plans_r.status_code == 200 else []
    return templates.TemplateResponse(
        request,
        "superadmin/tenants/form.html",
        {"user": user, "tenant": None, "plans": plans, "form_title": "Tambah Tenant"},
    )


@router.post("/tenants")
async def tenants_create(
    request: Request,
    nama: str = Form(...),
    kode: str = Form(...),
    plan: str = Form(""),
    max_murid: int = Form(0),
    user: dict = Depends(require_super_admin_web),
):
    """Buat tenant baru."""
    r = await api_post(
        request,
        "/api/super/tenants",
        json={"nama": nama, "kode": kode, "plan": plan or "",
              "max_murid": max_murid or None},
    )
    if r.status_code in (200, 201):
        created = r.json() if r.content else {}
        _audit(
            user,
            "tambah_tenant_web",
            f"Tenant '{nama}' ({kode}) dibuat via panel superadmin; "
            f"id={created.get('id', '?')}",
        )
        return _redirect("/madrasah-app/superadmin/tenants",
                         f"Tenant '{nama}' berhasil dibuat")
    detail = "Gagal membuat tenant"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/madrasah-app/superadmin/tenants", detail, "error")


@router.get("/tenants/{tenant_id}")
async def tenants_detail(
    request: Request,
    tenant_id: int,
    user: dict = Depends(require_super_admin_web),
):
    """Detail tenant: info + admin list."""
    tenant, err = await _get_tenant_or_redirect(request, tenant_id)
    if err:
        return err

    admins_r = await api_get(request, f"/api/super/tenants/{tenant_id}/admins")
    admins = admins_r.json() if admins_r.status_code == 200 else []

    return templates.TemplateResponse(
        request,
        "superadmin/tenants/detail.html",
        {"user": user, "tenant": tenant, "admins": admins},
    )


async def _get_tenant_or_redirect(request: Request, tenant_id: int):
    """Ambil tenant dari detail API, fallback ke list. Return (tenant, error_redirect)."""
    r = await api_get(request, f"/api/super/tenants/{tenant_id}/detail")
    if r.status_code == 200:
        return r.json(), None
    list_r = await api_get(request, "/api/super/tenants")
    tenants = list_r.json() if list_r.status_code == 200 else []
    tenant = next((t for t in tenants if t.get("id") == tenant_id), None)
    if not tenant:
        return None, _redirect("/madrasah-app/superadmin/tenants",
                               "Tenant tidak ditemukan", "error")
    return tenant, None


@router.get("/tenants/{tenant_id}/edit")
async def tenants_edit_form(
    request: Request,
    tenant_id: int,
    user: dict = Depends(require_super_admin_web),
):
    """Form edit tenant."""
    tenant, err = await _get_tenant_or_redirect(request, tenant_id)
    if err:
        return err
    plans_r = await api_get(request, "/api/super/plans")
    plans = plans_r.json() if plans_r.status_code == 200 else []
    return templates.TemplateResponse(
        request,
        "superadmin/tenants/form.html",
        {"user": user, "tenant": tenant, "plans": plans,
         "form_title": f"Edit Tenant {tenant.get('nama', '')}"},
    )


@router.post("/tenants/{tenant_id}")
async def tenants_update(
    request: Request,
    tenant_id: int,
    nama: str = Form(...),
    plan: str = Form(""),
    max_murid: int = Form(0),
    status: str = Form("trial"),
    masa_langganan_hingga: str = Form(""),
    hapus_langganan: str = Form(""),
    user: dict = Depends(require_super_admin_web),
):
    """Update tenant — status pakai enum (trial/active/suspended)."""
    payload: dict = {
        "nama": nama,
        "plan": plan or None,
        "max_murid": max_murid or None,
        "status": status,
    }
    if hapus_langganan == "on":
        payload["hapus_masa_langganan"] = True
    elif masa_langganan_hingga:
        payload["masa_langganan_hingga"] = masa_langganan_hingga

    r = await api_patch(request, f"/api/super/tenants/{tenant_id}", json=payload)
    if r.status_code == 200:
        _audit(
            user,
            "ubah_tenant_web",
            f"Tenant id={tenant_id} diperbarui via panel superadmin; "
            f"nama='{nama}', plan='{plan}', status={status}",
        )
        return _redirect(f"/madrasah-app/superadmin/tenants/{tenant_id}",
                         "Tenant diperbarui")
    detail = "Gagal update"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/madrasah-app/superadmin/tenants/{tenant_id}", detail, "error")


@router.post("/tenants/{tenant_id}/admin")
async def tenants_create_admin(
    request: Request,
    tenant_id: int,
    nama: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    user: dict = Depends(require_super_admin_web),
):
    """Buat akun admin baru di tenant (tenant baru wajib punya admin pertama)."""
    r = await api_post(
        request,
        f"/api/super/tenants/{tenant_id}/admin",
        json={"nama": nama, "username": username, "password": password},
    )
    if r.status_code in (200, 201):
        _audit(user, "tambah_admin_tenant_web",
               f"Admin '{username}' ({nama}) dibuat untuk tenant id={tenant_id}")
        return _redirect(f"/madrasah-app/superadmin/tenants/{tenant_id}",
                         f"Admin '{username}' berhasil dibuat")
    detail = "Gagal membuat admin"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/madrasah-app/superadmin/tenants/{tenant_id}", detail, "error")


@router.post("/tenants/{tenant_id}/admins/{guru_id}/toggle")
async def tenants_admin_toggle(
    request: Request,
    tenant_id: int,
    guru_id: int,
    user: dict = Depends(require_super_admin_web),
):
    """Toggle aktif/nonaktif akun admin tenant."""
    r = await api_get(request, f"/api/super/tenants/{tenant_id}/admins", semua=True)
    admins = r.json() if r.status_code == 200 else []
    target = next((a for a in admins if a.get("id") == guru_id), None)
    if not target:
        return _redirect(f"/madrasah-app/superadmin/tenants/{tenant_id}",
                         "Akun tidak ditemukan", "error")
    new_state = not target.get("is_active", True)

    r2 = await api_patch(
        request,
        f"/api/super/tenants/{tenant_id}/admins/{guru_id}",
        json={"is_active": new_state},
    )
    if r2.status_code == 200:
        _audit(user, "toggle_admin_tenant_web",
               f"Admin '{target.get('username')}' di tenant id={tenant_id} → "
               f"{'aktif' if new_state else 'nonaktif'}")
        return _redirect(f"/madrasah-app/superadmin/tenants/{tenant_id}",
                         f"Admin '{target.get('username')}' {'diaktifkan' if new_state else 'dinonaktifkan'}")
    detail = "Gagal mengubah status"
    try:
        detail = r2.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/madrasah-app/superadmin/tenants/{tenant_id}", detail, "error")


@router.post("/tenants/{tenant_id}/admins/{guru_id}/hapus")
async def tenants_admin_delete(
    request: Request,
    tenant_id: int,
    guru_id: int,
    user: dict = Depends(require_super_admin_web),
):
    """Hapus akun admin tenant."""
    r = await api_delete(
        request,
        f"/api/super/tenants/{tenant_id}/admins/{guru_id}",
        json={},
    )
    if r.status_code == 200:
        _audit(user, "hapus_admin_tenant_web",
               f"Admin id={guru_id} dihapus dari tenant id={tenant_id}")
        return _redirect(f"/madrasah-app/superadmin/tenants/{tenant_id}",
                         "Akun dihapus")
    detail = "Gagal menghapus akun"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/madrasah-app/superadmin/tenants/{tenant_id}", detail, "error")


@router.get("/tenants/{tenant_id}/backup")
async def tenants_backup(
    request: Request,
    tenant_id: int,
    user: dict = Depends(require_super_admin_web),
):
    """Download backup data tenant (JSON)."""
    from fastapi.responses import Response

    r = await api_get(request, f"/api/super/tenants/{tenant_id}/backup")
    if r.status_code != 200:
        detail = "Gagal membuat backup"
        try:
            detail = r.json().get("detail", detail)
        except Exception:
            pass
        return _redirect(f"/madrasah-app/superadmin/tenants/{tenant_id}", detail, "error")

    # Ambil nama file dari Content-Disposition header backend
    fname = "backup.json"
    cd = r.headers.get("content-disposition", "")
    if "filename=" in cd:
        fname = cd.split("filename=")[-1].strip('"')

    _audit(user, "backup_tenant_web",
           f"Backup tenant id={tenant_id} diunduh ({fname})")
    return Response(
        content=r.content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/tenants/{tenant_id}/reset-password")
async def tenants_reset_password(
    request: Request,
    tenant_id: int,
    username: str = Form(...),
    password: str = Form(...),
    user: dict = Depends(require_super_admin_web),
):
    """Reset password akun admin tenant (butuh username)."""
    r = await api_post(
        request,
        f"/api/super/tenants/{tenant_id}/reset-password",
        json={"username": username, "password": password},
    )
    if r.status_code == 200:
        _audit(
            user,
            "reset_password_tenant_web",
            f"Password admin '{username}' untuk tenant id={tenant_id} direset via panel superadmin",
        )
        return _redirect(f"/madrasah-app/superadmin/tenants/{tenant_id}",
                         f"Password '{username}' direset")
    detail = "Gagal reset password"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/madrasah-app/superadmin/tenants/{tenant_id}", detail, "error")


@router.post("/tenants/{tenant_id}/hapus")
async def tenants_delete(
    request: Request,
    tenant_id: int,
    konfirmasi: str = Form(...),
    user: dict = Depends(require_super_admin_web),
):
    """Hapus tenant (perlu ketik NAMA untuk konfirmasi)."""
    tenant, err = await _get_tenant_or_redirect(request, tenant_id)
    if err:
        return err

    if konfirmasi.strip() != tenant.get("nama", ""):
        return _redirect(f"/madrasah-app/superadmin/tenants/{tenant_id}",
                         "Nama tidak cocok — tenant tidak dihapus", "error")

    # API delete butuh body {"kode": tenant_kode} (TenantDeleteRequest)
    del_r = await api_delete(
        request,
        f"/api/super/tenants/{tenant_id}",
        json={"kode": tenant.get("kode", "")},
    )
    if del_r.status_code == 200:
        _audit(
            user,
            "hapus_tenant_web",
            f"Tenant '{tenant.get('nama')}' ({tenant.get('kode', '')}) id={tenant_id} dihapus via panel superadmin",
        )
        return _redirect("/madrasah-app/superadmin/tenants",
                         f"Tenant '{tenant.get('nama')}' dihapus")
    detail = "Gagal hapus"
    try:
        detail = del_r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/madrasah-app/superadmin/tenants/{tenant_id}", detail, "error")
