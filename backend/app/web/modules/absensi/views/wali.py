"""Wali Kelas view: halaman perwalian guru wali.

Alur: /wali-kelas (daftar kelas wali) → /wali-kelas/{kelas_id} (daftar
murid) → /wali-kelas/murid/{id}?bulan=YYYY-MM (riwayat komposit).
Akses: permission wali.view (guru default punya; admin semua).
"""
from fastapi import APIRouter, Depends, Query, Request

from ....core.client import api_get
from ....core.deps import require_login_web, require_permission_web
from ....core.templates import templates

router = APIRouter(tags=["web-wali-kelas"])

_MONTH_NAMES = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
                "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


@router.get("")
async def wali_dashboard(
    request: Request,
    user: dict = Depends(require_permission_web("wali.view", "kelas.view")),
):
    """Daftar kelas wali milik user login + semua murid perwalian."""
    r = await api_get(request, "/api/kelas/wali-saya/murid")
    data = r.json() if r.status_code == 200 else {"kelas": [], "murid": []}

    # Kelas kosong → tampilkan pesan ramah (guru bukan wali)
    return templates.TemplateResponse(
        request,
        "wali/dashboard.html",
        {
            "user": user,
            "tahun_ajaran_nama": data.get("tahun_ajaran_nama"),
            "kelas_list": data.get("kelas", []),
            "murid_list": data.get("murid", []),
        },
    )


@router.get("/{kelas_id}")
async def wali_kelas_detail(
    request: Request,
    kelas_id: int,
    user: dict = Depends(require_permission_web("wali.view", "kelas.view")),
):
    """Daftar murid satu kelas perwalian (ringkasan alpa + status SP)."""
    r = await api_get(request, "/api/kelas/wali-saya/murid")
    data = r.json() if r.status_code == 200 else {"kelas": [], "murid": []}
    kelas = next((k for k in data.get("kelas", []) if k.get("id") == kelas_id), None)
    if not kelas:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"status_code": 404, "message": "Kelas wali tidak ditemukan."},
            status_code=404,
        )
    murid_kelas = [m for m in data.get("murid", []) if m.get("kelas_id") == kelas_id]
    return templates.TemplateResponse(
        request,
        "wali/kelas.html",
        {
            "user": user,
            "kelas": kelas,
            "murid_list": murid_kelas,
            "tahun_ajaran_nama": data.get("tahun_ajaran_nama"),
        },
    )


@router.get("/murid/{murid_id}")
async def wali_murid_detail(
    request: Request,
    murid_id: int,
    bulan: str | None = Query(None),  # YYYY-MM
    user: dict = Depends(require_permission_web("wali.view", "kelas.view")),
):
    """Riwayat komposit satu murid perwalian (absensi + BK + placeholder)."""
    params = {"bulan": bulan} if bulan else {}
    r = await api_get(request, f"/api/murid/{murid_id}/riwayat", **params)
    if r.status_code != 200:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"status_code": r.status_code, "message": "Riwayat murid tidak ditemukan."},
            status_code=r.status_code,
        )
    data = r.json()

    # Dropdown bulan: 12 bulan terakhir
    from datetime import date
    from datetime import datetime
    now = date.today()
    bulan_list = []
    for i in range(12):
        y = now.year
        m = now.month - i
        while m <= 0:
            m += 12
            y -= 1
        bulan_list.append({
            "kode": f"{y:04d}-{m:02d}",
            "label": f"{_MONTH_NAMES[m - 1]} {y}",
        })

    return templates.TemplateResponse(
        request,
        "wali/murid.html",
        {
            "user": user,
            "data": data,
            "bulan_list": bulan_list,
            "bulan_terpilih": data.get("bulan", bulan or ""),
        },
    )
