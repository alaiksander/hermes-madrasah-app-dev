"""Pengaturan view: hub + 3 sub-halaman (umum, jam-hari, scan-mode).

Path sudah di-strip dari prefix '/pengaturan' — di-include dengan prefix
'/madrasah-app/system/pengaturan' di main.py (lihat modul System).
"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_get, api_get_raw, api_patch, api_put
from ....core.deps import require_permission_web
from ....core.templates import templates

router = APIRouter(tags=["web-system-pengaturan"])


def _redirect(msg: str, type_: str = "success", path: str = "/madrasah-app/system/pengaturan"):
    return RedirectResponse(
        url=f"{path}?msg={msg.replace(' ', '+')}&type={type_}",
        status_code=303,
    )


async def _load_pengaturan(request: Request) -> dict:
    """Helper: ambil data pengaturan dari API."""
    r = await api_get(request, "/api/pengaturan")
    return r.json() if r.status_code == 200 else {
        "jam_masuk": "07:00",
        "jam_pulang": "13:30",
        "hari_aktif": [1, 2, 3, 4, 5],
        "nama_aplikasi": "Aplikasi Madrasah",
        "scan_mode": "standar",
        "scan_idle_menit": 5,
        "scan_aktif_detik": 30,
    }


@router.get("")
async def pengaturan_hub(
    request: Request,
    user: dict = Depends(require_permission_web("pengaturan.view", "pengaturan.update")),
):
    """Halaman utama Pengaturan (admin only) — 3 menu sub-halaman.

    Note: '/pengaturan' tetap ada sebagai hub. Sidebar sekarang:
    - Umum → grup Sistem (identitas aplikasi)
    - Jam & Hari, Scan Mode → grup Absensi (operasional absensi)
    """
    settings = await _load_pengaturan(request)
    return templates.TemplateResponse(
        request,
        "pengaturan/hub.html",
        {
            "user": user,
            "settings": settings,
        },
    )


# ── Sub-halaman: Jam & Hari ──────────────────────────────────────────


@router.get("/jam-hari")
async def pengaturan_jam_hari(
    request: Request,
    user: dict = Depends(require_permission_web("pengaturan.view", "pengaturan.update")),
):
    """Form edit Jam Masuk/Pulang + Hari Aktif."""
    settings = await _load_pengaturan(request)
    return templates.TemplateResponse(
        request,
        "pengaturan/jam_hari.html",
        {
            "user": user,
            "settings": settings,
        },
    )


@router.post("/jam-hari")
async def pengaturan_jam_hari_save(
    request: Request,
    jam_masuk: str = Form(...),
    jam_pulang: str = Form(...),
    hari_aktif: list[str] = Form([]),
    user: dict = Depends(require_permission_web("pengaturan.update")),
):
    """Submit form jam & hari."""
    hari_list = [int(h) for h in hari_aktif if h.isdigit()]
    payload = {
        "jam_masuk": jam_masuk,
        "jam_pulang": jam_pulang,
        "hari_aktif": hari_list,
    }
    r = await api_put(request, "/api/pengaturan", json=payload)
    if r.status_code == 200:
        return _redirect("Pengaturan jam & hari disimpan")
    detail = "Gagal menyimpan"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")


# ── Sub-halaman 3: Scan Mode ─────────────────────────────────────────


SCAN_MODE_DESCRIPTIONS = {
    "standar": "Mode normal — scanner aktif terus saat guru masuk aplikasi.",
    "hemat": "Scanner idle setelah beberapa menit tanpa aktivitas, hemat baterai.",
    "ekstrim": "Scanner auto-off setelah idle, hanya aktif di jam-jam absensi.",
}


@router.get("/scan-mode")
async def pengaturan_scan_mode(
    request: Request,
    user: dict = Depends(require_permission_web("pengaturan.view", "pengaturan.update")),
):
    """Form edit Scan Mode + idle/aktif duration."""
    settings = await _load_pengaturan(request)
    return templates.TemplateResponse(
        request,
        "pengaturan/scan_mode.html",
        {
            "user": user,
            "settings": settings,
            "scan_mode_descriptions": SCAN_MODE_DESCRIPTIONS,
        },
    )


@router.post("/scan-mode")
async def pengaturan_scan_mode_save(
    request: Request,
    scan_mode: str = Form("standar"),
    scan_idle_menit: int = Form(5),
    scan_aktif_detik: int = Form(30),
    user: dict = Depends(require_permission_web("pengaturan.update")),
):
    """Submit form scan mode."""
    if scan_mode not in SCAN_MODE_DESCRIPTIONS:
        return _redirect("Mode scan tidak valid", "error")
    if scan_idle_menit < 1 or scan_idle_menit > 60:
        return _redirect("Idle menit harus 1-60", "error")
    if scan_aktif_detik < 5 or scan_aktif_detik > 300:
        return _redirect("Aktif detik harus 5-300", "error")

    payload = {
        "scan_mode": scan_mode,
        "scan_idle_menit": scan_idle_menit,
        "scan_aktif_detik": scan_aktif_detik,
    }
    r = await api_put(request, "/api/pengaturan", json=payload)
    if r.status_code == 200:
        return _redirect("Pengaturan scan mode disimpan")
    detail = "Gagal menyimpan"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")