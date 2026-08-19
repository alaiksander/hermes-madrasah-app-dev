"""Portal Orang Tua — rekap absensi bulanan anak via NIS + nama ortu.

Publik (tanpa login): /madrasah-app/ortu
- Form verifikasi: NIS + Nama Orang Tua
- Setelah valid: rekap bulan berjalan + dropdown pilih bulan
- Data dari API /api/absensi/ortu/rekap (tenant-scoped)
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_get
from ....core.templates import templates, _MONTH_NAMES

router = APIRouter()

API_BASE = "http://127.0.0.1:8010"


@router.get("/ortu")
async def ortu_page(
    request: Request,
    kode: str | None = None,
    nisn: str | None = Query(None, alias="nisn"),
    nama_ortu: str | None = None,
    bulan: str | None = None,
):
    """Halaman portal orang tua — form verifikasi + rekap."""
    err = None
    data = None

    # Kalau ada param → coba verifikasi
    if nisn and nama_ortu and kode:
        r = await api_get(
            request,
            "/api/absensi/ortu/rekap",
            kode=kode.strip(),
            nisn=nisn.strip(),
            nama_ortu=nama_ortu.strip(),
            bulan=bulan or "",
        )
        if r.status_code == 200:
            data = r.json()
        elif r.status_code == 401:
            err = "Nama orang tua tidak cocok. Periksa kembali."
        elif r.status_code == 404:
            err = "NISN tidak ditemukan."
        else:
            err = "Terjadi kesalahan. Coba lagi."

    # Bulan tersedia: 12 bulan terakhir (dropdown)
    now = datetime.now(ZoneInfo("Asia/Jakarta"))
    bulan_list = []
    for i in range(12):
        y = now.year
        m = now.month - i
        while m <= 0:
            m += 12
            y -= 1
        bulan_list.append({"kode": f"{y:04d}-{m:02d}",
                           "label": f"{_MONTH_NAMES[m]} {y}"})

    return templates.TemplateResponse(
        request,
        "ortu.html",
        {
            "user": None,  # publik — tanpa sidebar admin
            "err": err,
            "data": data,
            "kode": kode or "",
            "nisn": nisn or "",
            "nama_ortu": nama_ortu or "",
            "bulan_list": bulan_list,
            "bulan_terpilih": (data or {}).get("bulan", bulan or ""),
        },
    )


@router.get("/ortu/{bulan}/rekap")
async def ortu_rekap_bulan(
    request: Request,
    bulan: str,
    kode: str = Query(...),
    nisn: str = Query(..., alias="nisn"),
    nama_ortu: str = Query(...),
):
    """Redirect ke halaman ortu dengan bulan dipilih (biar URL bersih)."""
    return RedirectResponse(
        f"/madrasah-app/ortu?kode={kode}&nisn={nisn}&nama_ortu={nama_ortu}&bulan={bulan}",
        status_code=303,
    )