"""Dashboard modul absensi — stats card + 3 section ringkasan.

Section:
- Stat cards ringkas (hadir hari ini, total murid, dll.)
- Rekap per Kelas 7 hari (top 3 + bottom 3 by persen kehadiran)
- Rekap Bulan Ini (H/I/S/A + %)
- Top Murid Alpha per Bulan (> 0 saja)
"""
from datetime import date
from fastapi import APIRouter, Depends, Request

from ....core.client import api_get
from ....core.deps import require_login_web, require_permission_web
from ....core.templates import _DAY_NAMES, _MONTH_NAMES, templates

router = APIRouter()


@router.get("/dashboard")
async def dashboard_page(
    request: Request,
    user: dict = Depends(require_permission_web("absen.rekap", "absen.scan", "absen.manual")),
):
    """Dashboard utama modul absensi. Stats + 3 section ringkasan."""
    # Fetch semua data via API existing (forward dengan Authorization dari cookie).
    # Tiap request disimpan status-nya agar template bisa tampilkan empty state kalau error.
    murid_r = await api_get(request, "/api/murid", limit=0)
    guru_r = await api_get(request, "/api/guru")
    kelas_r = await api_get(request, "/api/kelas")
    absen_r = await api_get(request, "/api/absensi/hari-ini")
    rekap_kelas_r = await api_get(request, "/api/absensi/rekap-per-kelas")
    rekap_bulan_r = await api_get(request, "/api/absensi/rekap-bulan-ini")
    top_alpha_r = await api_get(request, "/api/absensi/top-alpha")

    # Parse safely (default kosong/0 kalau endpoint error)
    def _safe_json(r):
        try:
            return r.json() if r.status_code == 200 else None
        except Exception:
            return None

    total_murid = (_safe_json(murid_r) or {}).get("total", 0)
    # Guru: endpoint admin-only — guru biasa dapat 403, tampilkan "—" (bukan 0)
    guru_data = _safe_json(guru_r)
    total_guru = len(guru_data) if guru_data is not None else None
    total_kelas = len(_safe_json(kelas_r) or [])
    absensi_list = _safe_json(absen_r) or []
    hadir_count = sum(1 for a in absensi_list if a.get("status") == "hadir")

    # Rekap per kelas → top 3 + bottom 3 by persen kehadiran.
    # Sort desc by persen untuk top, asc untuk bottom.
    # Exclude top dari bottom agar tidak overlap (kalau total kelas < 6,
    # bottom3 akan kurang dari 3 — empty state ditampilkan kalau kosong).
    rekap_kelas = (_safe_json(rekap_kelas_r) or {}).get("items") or []
    # Filter dulu: hanya kelas yang punya data (>=1 absensi)
    with_data = [k for k in rekap_kelas if k.get("total_records", 0) > 0]
    sorted_top = sorted(with_data, key=lambda x: (-x.get("persen", 0), x.get("kelas_nama", "")))
    top3 = sorted_top[:3]
    # Bottom = kelas dengan data, exclude yang sudah di top3
    sorted_bottom = sorted(with_data, key=lambda x: (x.get("persen", 0), x.get("kelas_nama", "")))
    bottom_pool = [k for k in sorted_bottom if k not in top3]
    bottom3 = bottom_pool[:3]

    # Rekap bulan ini
    rekap_bulan = _safe_json(rekap_bulan_r) or {}

    # Top alpha
    top_alpha = (_safe_json(top_alpha_r) or {}).get("items") or []

    # Pengampu (khusus role guru) — untuk tampil di dashboard ringkas
    pengampu_count = 0
    pengampu_list = []
    if user.get("role") == "guru":
        pengampu_r = await api_get(request, f"/api/guru-pengampu/guru/{user['id']}")
        if pengampu_r.status_code == 200:
            pengampu_list = pengampu_r.json()
            pengampu_count = len(pengampu_list)

    # Tanggal hari ini untuk header
    t = date.today()
    today = f"{_DAY_NAMES[t.weekday()]}, {t.day} {_MONTH_NAMES[t.month]} {t.year}"

    ctx = {
        "user": user,
        "total_murid": total_murid,
        "total_guru": total_guru,
        "total_kelas": total_kelas,
        "hadir_count": hadir_count,
        "absensi_count": len(absensi_list),
        "today": today,
        "top3": top3,
        "bottom3": bottom3,
        "rekap_bulan": rekap_bulan,
        "top_alpha": top_alpha,
        "pengampu_count": pengampu_count,
        "pengampu_list": pengampu_list,
    }
    return templates.TemplateResponse(request, "absensi/dashboard.html", ctx)