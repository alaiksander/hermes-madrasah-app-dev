"""Manajemen tenant untuk superadmin web panel."""
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import RedirectResponse

from ....core.client import (api_delete, api_get, api_patch, api_post,
                             api_post_multipart, api_put)
from ....core.deps import require_super_admin_web
from ....core.templates import templates
from ....core.auth import get_token_from_request
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
    kontak_nama: str = Form(""),
    kontak_email: str = Form(""),
    kontak_telepon: str = Form(""),
    alamat: str = Form(""),
    user: dict = Depends(require_super_admin_web),
):
    """Buat tenant baru."""
    r = await api_post(
        request,
        "/api/super/tenants",
        json={"nama": nama, "kode": kode, "plan": plan or "",
              "max_murid": max_murid or None,
              "kontak_nama": kontak_nama or None,
              "kontak_email": kontak_email or None,
              "kontak_telepon": kontak_telepon or None,
              "alamat": alamat or None},
    )
    if r.status_code in (200, 201):
        created = r.json() if r.content else {}
        _audit(
            user,
            "tambah_tenant_web",
            f"Tenant '{nama}' ({kode}) dibuat via panel superadmin; "
            f"id={created.get('id', '?')}",
        )
        return _redirect("/apps/superadmin/tenants",
                         f"Tenant '{nama}' berhasil dibuat")
    detail = "Gagal membuat tenant"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/apps/superadmin/tenants", detail, "error")


@router.get("/tenants/{tenant_id}")
async def tenants_detail(
    request: Request,
    tenant_id: int,
    user: dict = Depends(require_super_admin_web),
):
    """Detail tenant: info + kesehatan + admin list (satu halaman)."""
    tenant, err = await _get_tenant_or_redirect(request, tenant_id)
    if err:
        return err

    admins_r = await api_get(request, f"/api/super/tenants/{tenant_id}/admins", semua=True)
    admins = admins_r.json() if admins_r.status_code == 200 else []

    k_r = await api_get(request, f"/api/super/tenants/{tenant_id}/kesehatan")
    k = k_r.json() if k_r.status_code == 200 else {}

    snap_r = await api_get(request, f"/api/super/tenants/{tenant_id}/snapshots")
    snapshots = snap_r.json() if snap_r.status_code == 200 else []

    cfg_r = await api_get(request, f"/api/super/tenants/{tenant_id}/snapshot-config")
    snap_cfg = cfg_r.json() if cfg_r.status_code == 200 else {}

    return templates.TemplateResponse(
        request,
        "superadmin/tenants/detail.html",
        {"user": user, "tenant": tenant, "admins": admins, "k": k,
         "snapshots": snapshots, "snap_cfg": snap_cfg},
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
        return None, _redirect("/apps/superadmin/tenants",
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
    kontak_nama: str = Form(""),
    kontak_email: str = Form(""),
    kontak_telepon: str = Form(""),
    alamat: str = Form(""),
    user: dict = Depends(require_super_admin_web),
):
    """Update tenant — status pakai enum (trial/active/suspended)."""
    payload: dict = {
        "nama": nama,
        "plan": plan or None,
        "max_murid": max_murid or None,
        "status": status,
        "kontak_nama": kontak_nama or None,
        "kontak_email": kontak_email or None,
        "kontak_telepon": kontak_telepon or None,
        "alamat": alamat or None,
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
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}",
                         "Tenant diperbarui")
    detail = "Gagal update"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/apps/superadmin/tenants/{tenant_id}", detail, "error")


@router.post("/tenants/{tenant_id}/admin")
async def tenants_create_admin(
    request: Request,
    tenant_id: int,
    nama: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("guru"),
    user: dict = Depends(require_super_admin_web),
):
    """Buat akun user baru di tenant (role guru/admin)."""
    r = await api_post(
        request,
        f"/api/super/tenants/{tenant_id}/admin",
        json={"nama": nama, "username": username, "password": password, "role": role},
    )
    if r.status_code in (200, 201):
        _audit(user, "tambah_user_tenant_web",
               f"User '{username}' ({nama}) role={role} dibuat untuk tenant id={tenant_id}")
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}",
                         f"User '{username}' berhasil dibuat")
    detail = "Gagal membuat user"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/apps/superadmin/tenants/{tenant_id}", detail, "error")


@router.post("/tenants/{tenant_id}/admins/{guru_id}/toggle")
async def tenants_admin_toggle(
    request: Request,
    tenant_id: int,
    guru_id: int,
    user: dict = Depends(require_super_admin_web),
):
    """Toggle aktif/nonaktif akun user tenant."""
    r = await api_get(request, f"/api/super/tenants/{tenant_id}/admins", semua=True)
    admins = r.json() if r.status_code == 200 else []
    target = next((a for a in admins if a.get("id") == guru_id), None)
    if not target:
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}",
                         "Akun tidak ditemukan", "error")
    new_state = not target.get("is_active", True)

    r2 = await api_patch(
        request,
        f"/api/super/tenants/{tenant_id}/admins/{guru_id}",
        json={"is_active": new_state},
    )
    if r2.status_code == 200:
        _audit(user, "toggle_user_tenant_web",
               f"User '{target.get('username')}' di tenant id={tenant_id} → "
               f"{'aktif' if new_state else 'nonaktif'}")
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}",
                         f"User '{target.get('username')}' {'diaktifkan' if new_state else 'dinonaktifkan'}")
    detail = "Gagal mengubah status"
    try:
        detail = r2.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/apps/superadmin/tenants/{tenant_id}", detail, "error")


@router.post("/tenants/{tenant_id}/admins/{guru_id}/edit")
async def tenants_admin_edit(
    request: Request,
    tenant_id: int,
    guru_id: int,
    nama: str = Form(...),
    role: str = Form("guru"),
    user: dict = Depends(require_super_admin_web),
):
    """Edit nama & role akun user tenant."""
    r = await api_patch(
        request,
        f"/api/super/tenants/{tenant_id}/admins/{guru_id}",
        json={"nama": nama, "role": role},
    )
    if r.status_code == 200:
        _audit(user, "edit_user_tenant_web",
               f"User id={guru_id} di tenant id={tenant_id} diedit (nama='{nama}', role={role})")
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}",
                         f"User id={guru_id} diperbarui")
    detail = "Gagal edit akun"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/apps/superadmin/tenants/{tenant_id}", detail, "error")


@router.post("/tenants/{tenant_id}/admins/{guru_id}/reset-password")
async def tenants_admin_reset_password(
    request: Request,
    tenant_id: int,
    guru_id: int,
    password: str = Form(...),
    user: dict = Depends(require_super_admin_web),
):
    """Reset password akun user tenant (by guru_id)."""
    r = await api_post(
        request,
        f"/api/super/tenants/{tenant_id}/admins/{guru_id}/reset-password",
        json={"username": "", "password": password},
    )
    if r.status_code == 200:
        data = r.json()
        _audit(user, "reset_password_user_web",
               f"Password user id={guru_id} di tenant id={tenant_id} direset")
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}",
                         f"Password user id={guru_id} direset")
    detail = "Gagal reset password"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/apps/superadmin/tenants/{tenant_id}", detail, "error")


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
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}",
                         "Akun dihapus")
    detail = "Gagal menghapus akun"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/apps/superadmin/tenants/{tenant_id}", detail, "error")


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
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}", detail, "error")

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


@router.post("/tenants/{tenant_id}/restore")
async def tenants_restore(
    request: Request,
    tenant_id: int,
    file: UploadFile = File(...),
    force: str = Form(""),
    user: dict = Depends(require_super_admin_web),
):
    """Restore data tenant dari file backup JSON yang diupload."""
    content = await file.read()
    if not content:
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}",
                         "File backup kosong", "error")
    import httpx
    token = get_token_from_request(request)
    headers = {"Authorization": f"Bearer {token}"}
    r = await api_post_multipart(
        request,
        f"/api/super/tenants/{tenant_id}/restore",
        files={"file": (file.filename or "backup.json", content,
                        "application/json")},
        data={"force": "true" if force == "on" else "false"},
    )
    if r.status_code == 200:
        _audit(user, "restore_tenant_web",
               f"Restore tenant id={tenant_id} dari file upload")
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}",
                         "Data tenant berhasil direstore")
    detail = "Gagal restore"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/apps/superadmin/tenants/{tenant_id}", detail, "error")


@router.post("/tenants/{tenant_id}/snapshots")
async def tenants_snapshot_create(
    request: Request,
    tenant_id: int,
    user: dict = Depends(require_super_admin_web),
):
    """Buat snapshot manual."""
    r = await api_post(request, f"/api/super/tenants/{tenant_id}/snapshots", json={})
    if r.status_code == 200:
        data = r.json()
        _audit(user, "buat_snapshot_web",
               f"Snapshot tenant id={tenant_id} ({data.get('file')})")
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}",
                         "Snapshot berhasil dibuat")
    detail = "Gagal membuat snapshot"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/apps/superadmin/tenants/{tenant_id}", detail, "error")


@router.post("/tenants/{tenant_id}/snapshots/{snap_id}/rollback")
async def tenants_snapshot_rollback(
    request: Request,
    tenant_id: int,
    snap_id: int,
    user: dict = Depends(require_super_admin_web),
):
    """Rollback tenant ke snapshot tertentu."""
    r = await api_post(request,
                       f"/api/super/tenants/{tenant_id}/snapshots/{snap_id}/rollback",
                       json={})
    if r.status_code == 200:
        _audit(user, "rollback_snapshot_web",
               f"Rollback tenant id={tenant_id} ke snapshot {snap_id}")
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}",
                         "Rollback berhasil")
    detail = "Gagal rollback"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/apps/superadmin/tenants/{tenant_id}", detail, "error")


@router.post("/tenants/{tenant_id}/snapshots/{snap_id}/hapus")
async def tenants_snapshot_delete(
    request: Request,
    tenant_id: int,
    snap_id: int,
    user: dict = Depends(require_super_admin_web),
):
    """Hapus snapshot."""
    r = await api_delete(
        request,
        f"/api/super/tenants/{tenant_id}/snapshots/{snap_id}",
        json={},
    )
    if r.status_code == 200:
        _audit(user, "hapus_snapshot_web",
               f"Hapus snapshot {snap_id} dari tenant id={tenant_id}")
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}",
                         "Snapshot dihapus")
    detail = "Gagal hapus snapshot"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/apps/superadmin/tenants/{tenant_id}", detail, "error")


@router.post("/tenants/{tenant_id}/snapshot-config")
async def tenants_snapshot_config(
    request: Request,
    tenant_id: int,
    enabled: str = Form(""),
    jam: str = Form("02:00"),
    user: dict = Depends(require_super_admin_web),
):
    """Setel konfigurasi snapshot otomatis."""
    r = await api_put(
        request,
        f"/api/super/tenants/{tenant_id}/snapshot-config",
        json={"enabled": enabled == "on", "jam": jam},
    )
    if r.status_code == 200:
        _audit(user, "set_snapshot_config_web",
               f"Snapshot otomatis tenant id={tenant_id}: {jam}")
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}",
                         "Konfigurasi snapshot otomatis disimpan")
    detail = "Gagal menyimpan konfigurasi"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/apps/superadmin/tenants/{tenant_id}", detail, "error")


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
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}",
                         f"Password '{username}' direset")
    detail = "Gagal reset password"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/apps/superadmin/tenants/{tenant_id}", detail, "error")


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
        return _redirect(f"/apps/superadmin/tenants/{tenant_id}",
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
        return _redirect("/apps/superadmin/tenants",
                         f"Tenant '{tenant.get('nama')}' dihapus")
    detail = "Gagal hapus"
    try:
        detail = del_r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(f"/apps/superadmin/tenants/{tenant_id}", detail, "error")
