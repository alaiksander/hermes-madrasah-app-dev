"""Backup & Pemulihan global — jadwal otomatis, backup manual, riwayat, restore."""
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response

from ....core.client import api_delete, api_get, api_post, api_post_multipart, api_put
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


@router.get("/backup")
async def backup_page(
    request: Request,
    user: dict = Depends(require_super_admin_web),
):
    """Halaman backup: config + riwayat + daftar file."""
    info_r = await api_get(request, "/api/super/backup")
    info = info_r.json() if info_r.status_code == 200 else {}
    files_r = await api_get(request, "/api/super/backup/files")
    files = files_r.json() if files_r.status_code == 200 else []

    return templates.TemplateResponse(
        request,
        "superadmin/backup.html",
        {
            "user": user,
            "config": info.get("config", {}),
            "riwayat": info.get("riwayat", []),
            "files": files,
        },
    )


@router.post("/backup/config")
async def backup_config_update(
    request: Request,
    enabled: str = Form(""),
    jam: str = Form("02:00"),
    retensi: int = Form(14),
    user: dict = Depends(require_super_admin_web),
):
    """Simpan jadwal backup otomatis."""
    r = await api_put(
        request,
        "/api/super/backup/config",
        json={"enabled": enabled == "on", "jam": jam, "retensi": retensi},
    )
    if r.status_code == 200:
        _audit(user, "ubah_backup_config_web",
               f"enabled={enabled == 'on'}, jam={jam}, retensi={retensi}")
        return _redirect("/madrasah-app/superadmin/backup",
                         "Jadwal backup disimpan")
    detail = "Gagal menyimpan jadwal"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/madrasah-app/superadmin/backup", detail, "error")


@router.post("/backup/run")
async def backup_run_now(
    request: Request,
    user: dict = Depends(require_super_admin_web),
):
    """Jalankan backup manual sekarang."""
    r = await api_post(request, "/api/super/backup/run", json={})
    if r.status_code == 200:
        data = r.json()
        nama = data.get("nama", "")
        _audit(user, "backup_manual_web", f"Backup manual: {nama}")
        return _redirect("/madrasah-app/superadmin/backup",
                         f"Backup selesai: {nama}")
    detail = "Gagal backup"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/madrasah-app/superadmin/backup", detail, "error")


@router.get("/backup/download/{nama}")
async def backup_download(
    request: Request,
    nama: str,
    user: dict = Depends(require_super_admin_web),
):
    """Download arsip backup."""
    from urllib.parse import quote

    r = await api_get(request, f"/api/super/backup/files/{nama}")
    if r.status_code != 200:
        detail = "File tidak ditemukan"
        try:
            detail = r.json().get("detail", detail)
        except Exception:
            pass
        return _redirect("/madrasah-app/superadmin/backup", detail, "error")
    return Response(
        content=r.content,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{nama}"'},
    )


@router.post("/backup/delete/{nama}")
async def backup_file_delete(
    request: Request,
    nama: str,
    konfirmasi: str = Form(...),
    user: dict = Depends(require_super_admin_web),
):
    """Hapus arsip backup — konfirmasi wajib ketik nama file persis."""
    from urllib.parse import quote

    if konfirmasi.strip() != nama:
        return _redirect("/madrasah-app/superadmin/backup",
                         "Nama file tidak cocok — backup tidak dihapus", "error")

    r = await api_delete(request, f"/api/super/backup/files/{quote(nama)}", json={})
    if r.status_code == 200:
        _audit(user, "hapus_backup_web", f"Arsip {nama} dihapus")
        return _redirect("/madrasah-app/superadmin/backup",
                         f"Backup {nama} dihapus")
    detail = "Gagal menghapus backup"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/madrasah-app/superadmin/backup", detail, "error")


@router.post("/backup/restore-upload")
async def backup_restore_upload(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(require_super_admin_web),
):
    """Restore dari file backup yang DIUPLOAD dari komputer lain.

    Alur: upload ke server (validasi gzip + ukuran) → restore otomatis.
    """
    content = await file.read()
    if not content:
        return _redirect("/madrasah-app/superadmin/backup",
                         "File kosong — pilih file backup", "error")

    # 1. Upload ke backend (validasi + simpan ke BACKUP_DIR)
    r = await api_post_multipart(
        request,
        "/api/super/backup/upload",
        files={"file": (file.filename or "backup.tar.gz", content,
                        file.content_type or "application/gzip")},
    )
    if r.status_code != 200:
        detail = "Gagal upload file"
        try:
            detail = r.json().get("detail", detail)
        except Exception:
            pass
        return _redirect("/madrasah-app/superadmin/backup", detail, "error")

    data = r.json()
    nama = data.get("nama_file", "")

    # 2. Restore otomatis dari file yang baru diupload
    rr = await api_post(
        request,
        "/api/super/backup/restore",
        json={"nama_file": nama},
    )
    if rr.status_code == 200:
        rdata = rr.json()
        restored = len(rdata.get("restored", []))
        _audit(user, "restore_backup_upload_web",
               f"Restore dari upload {file.filename or nama}: {restored} file")
        return _redirect(
            "/madrasah-app/superadmin/backup",
            f"Upload + restore selesai ({nama}, {restored} file) — "
            "service restart otomatis (±5 detik)",
        )
    detail = "Gagal restore"
    try:
        detail = rr.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/madrasah-app/superadmin/backup", detail, "error")


@router.post("/backup/restore")
async def backup_restore(
    request: Request,
    nama_file: str = Form(...),
    konfirmasi: str = Form(...),
    user: dict = Depends(require_super_admin_web),
):
    """Restore platform dari arsip (konfirmasi ketik nama file).

    PENTING: operasi DESTRUKTIF — service restart otomatis setelah restore.
    """
    if konfirmasi.strip() != nama_file.strip():
        return _redirect("/madrasah-app/superadmin/backup",
                         "Nama file tidak cocok — restore dibatalkan", "error")

    r = await api_post(
        request,
        "/api/super/backup/restore",
        json={"nama_file": nama_file.strip()},
    )
    if r.status_code == 200:
        data = r.json()
        _audit(user, "restore_backup_web",
               f"Restore dari {nama_file}: {len(data.get('restored', []))} file")
        return _redirect(
            "/madrasah-app/superadmin/backup",
            f"Restore dari {nama_file} — service restart otomatis (±5 detik)",
        )
    detail = "Gagal restore"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect("/madrasah-app/superadmin/backup", detail, "error")