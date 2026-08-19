"""Cetak Absen — menu admin: per kelas / per siswa + periode dinamis.

Periode:
- semester : memakai periode_akademik (Semester Gasal/Genap) -> ringkasan H/I/S/A
- bulan    : pilihan bulan dalam tahun ajaran aktif -> matrix bulanan
- rentang  : pilihan tanggal bebas -> matrix/detail

Preview A4 (HTML printable) + tombol Cetak/Download PDF & Excel.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, Response

from ....core.client import api_get, api_get_raw
from ....core.deps import require_login_web
from ....core.templates import templates

router = APIRouter()

BULAN_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


async def _kelas_ta_aktif(request: Request) -> tuple[list, dict | None]:
    """Kelas hanya untuk tahun ajaran AKTIF."""
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_list if ta.get("is_active")), None)
    ta_id = tahun_aktif["id"] if tahun_aktif else None
    kelas_r = await api_get(request, "/api/kelas", tahun_ajaran_id=ta_id or "")
    kelas_list = kelas_r.json() if kelas_r.status_code == 200 else []
    return kelas_list, tahun_aktif

async def _periode_ta(request: Request, ta_id: int | None) -> list:
    """Periode semester (ganjil/genap) milik tahun ajaran aktif."""
    if not ta_id:
        return []
    r = await api_get(request, f"/api/tahun-ajaran/{ta_id}/periode")
    return r.json() if r.status_code == 200 else []


def _bulan_list(ta: dict | None) -> list[dict]:
    """Bulan dalam rentang tahun ajaran aktif: [{value: 'YYYY-MM', label}]. """
    if not ta:
        return []
    try:
        mulai = date.fromisoformat(ta["tanggal_mulai"])
        selesai = date.fromisoformat(ta["tanggal_selesai"])
    except (KeyError, ValueError, TypeError):
        return []
    out = []
    y, m = mulai.year, mulai.month
    while (y, m) <= (selesai.year, selesai.month):
        out.append({"value": f"{y:04d}-{m:02d}", "label": f"{BULAN_ID[m - 1]} {y}"})
        m += 1
        if m == 13:
            m = 1
            y += 1
    return out


def _awal_akhir_bulan(bln: str) -> tuple[date, date]:
    y = int(bln[:4])
    m = int(bln[5:7])
    akhir = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
    return date(y, m, 1), akhir


@router.get("/cetak-absen")
async def cetak_absen(
    request: Request,
    mode: str = Query("kelas"),  # 'kelas' | 'murid'
    kelas_id: str | None = Query(None),
    murid_id: str | None = Query(None),
    q: str | None = None,
    periode: str = Query("semester"),  # 'semester' | 'bulan' | 'rentang'
    periode_id: str | None = Query(None),
    bulan: str | None = None,
    dari: str | None = None,
    sampai: str | None = None,
    user: dict = Depends(require_login_web),
):
    """Halaman Cetak Absen — form + preview A4.

    `kelas_id` / `murid_id` / `periode_id` diterima sebagai string lalu
    di-parse manual: nilai kosong (""), invalid, atau absen → None (bukan 422).
    Ini mencegah FastAPI int_parsing 422 saat form mengirim field kosong.
    """

    def _to_int(v: str | None) -> int | None:
        if v in (None, ""):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    kelas_id = _to_int(kelas_id)
    murid_id = _to_int(murid_id)
    periode_id = _to_int(periode_id)

    kelas_list, tahun_aktif = await _kelas_ta_aktif(request)
    ta_id = tahun_aktif["id"] if tahun_aktif else None
    periode_list = await _periode_ta(request, ta_id)
    bulan_list = _bulan_list(tahun_aktif)

    err = None
    tgl_dari = tgl_sampai = None

    if periode == "semester":
        sel = next((p for p in periode_list if p["id"] == periode_id), None)
        if not sel and periode_list:
            sel = periode_list[0]
            periode_id = sel["id"]
        if sel:
            tgl_dari = date.fromisoformat(sel["tanggal_mulai"])
            tgl_sampai = date.fromisoformat(sel["tanggal_selesai"])
    elif periode == "bulan":
        if not bulan:
            today = date.today().strftime("%Y-%m")
            bulan = today if any(b["value"] == today for b in bulan_list) else (
                bulan_list[0]["value"] if bulan_list else None)
        if bulan:
            tgl_dari, tgl_sampai = _awal_akhir_bulan(bulan)
    else:  # rentang
        try:
            tgl_dari = date.fromisoformat(dari) if dari else None
            tgl_sampai = date.fromisoformat(sampai) if sampai else None
        except ValueError:
            err = "Format tanggal tidak valid"

    if tgl_dari and tgl_sampai and tgl_dari > tgl_sampai:
        err = "Tanggal 'dari' harus sebelum atau sama dengan 'sampai'"
    if not err and not (tgl_dari and tgl_sampai):
        # Fallback: rentang 30 hari terakhir
        tgl_sampai = date.today()
        tgl_dari = tgl_sampai - timedelta(days=30)
        periode = "rentang"

    ringkasan = periode == "semester" and mode == "kelas"

    # Cari murid (mode murid) — dropdown Choices.js semua murid aktif
    murid_list = []
    selected_murid = None
    if mode == "murid":
        r = await api_get(request, "/api/murid", per_page=200, semua=True)
        if r.status_code == 200:
            murid_list = r.json().get("items", [])
        if murid_id:
            selected_murid = next((m for m in murid_list if m["id"] == murid_id), None)
            if not selected_murid:
                r2 = await api_get(request, f"/api/murid/{murid_id}")
                if r2.status_code == 200:
                    selected_murid = r2.json()

    # Cek parameter preview lengkap
    can_preview = not err and (
        (mode == "kelas" and kelas_id) or (mode == "murid" and murid_id)
    ) and tgl_dari and tgl_sampai

    # Ambil data preview (HTML A4 — bukan iframe PDF)
    preview = None
    if can_preview:
        if mode == "kelas":
            r = await api_get(
                request,
                "/api/absensi/cetak.json",
                kelas_id=kelas_id,
                dari=tgl_dari.isoformat(),
                sampai=tgl_sampai.isoformat(),
                ringkasan=ringkasan,
            )
            if r.status_code == 200:
                preview = r.json()
            else:
                err = "Tidak ada data absensi untuk filter ini"
                can_preview = False
        else:
            r = await api_get(
                request,
                f"/api/absensi/murid/{murid_id}/rincian",
                dari=tgl_dari.isoformat(),
                sampai=tgl_sampai.isoformat(),
            )
            if r.status_code == 200:
                preview = r.json()
            else:
                err = "Tidak ada data absensi untuk filter ini"
                can_preview = False

    return templates.TemplateResponse(
        request,
        "cetak_absen.html",
        {
            "user": user,
            "mode": mode,
            "kelas_list": kelas_list,
            "selected_kelas_id": kelas_id,
            "murid_id": murid_id,
            "q": q or "",
            "murid_list": murid_list,
            "selected_murid": selected_murid,
            "periode": periode,
            "periode_list": periode_list,
            "selected_periode_id": periode_id,
            "bulan": bulan or "",
            "bulan_list": bulan_list,
            "ringkasan": ringkasan,
            "dari": tgl_dari.isoformat() if tgl_dari else "",
            "sampai": tgl_sampai.isoformat() if tgl_sampai else "",
            "err": err,
            "can_preview": can_preview,
            "preview": preview,
            "dicetak_at": datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d/%m/%Y %H:%M"),
            "tahun_aktif_nama": tahun_aktif.get("nama") if tahun_aktif else None,
        },
    )


@router.get("/cetak-absen/pdf")
async def cetak_absen_pdf(
    request: Request,
    mode: str = Query(...),
    kelas_id: str | None = Query(None),
    murid_id: str | None = Query(None),
    dari: str | None = None,
    sampai: str | None = None,
    ringkasan: bool = False,
    user: dict = Depends(require_login_web),
):
    """Proxy PDF: per murid → /api/absensi/pdf/{id}; per kelas → /cetak-pdf.pdf."""
    def _to_int(v: str | None) -> int | None:
        if v in (None, ""):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    kelas_id = _to_int(kelas_id)
    murid_id = _to_int(murid_id)

    params = {}
    if dari:
        params["dari"] = dari
    if sampai:
        params["sampai"] = sampai
    if ringkasan:
        params["ringkasan"] = True

    if mode == "murid" and murid_id:
        path = f"/api/absensi/pdf/{murid_id}"
    elif mode == "kelas" and kelas_id:
        path = "/api/absensi/cetak-pdf.pdf"
        params["kelas_id"] = kelas_id
    else:
        return RedirectResponse("/madrasah-app/absensi/cetak-absen", status_code=303)

    content = await api_get_raw(request, path, **params)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=cetak-absen.pdf"},
    )


@router.get("/cetak-absen/xlsx")
async def cetak_absen_xlsx(
    request: Request,
    mode: str = Query(...),
    kelas_id: str | None = Query(None),
    murid_id: str | None = Query(None),
    dari: str | None = None,
    sampai: str | None = None,
    ringkasan: bool = False,
    user: dict = Depends(require_login_web),
):
    """Download Excel matrix absen (per kelas / per murid + rentang)."""
    def _to_int(v: str | None) -> int | None:
        if v in (None, ""):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    kelas_id = _to_int(kelas_id)
    murid_id = _to_int(murid_id)

    params = {}
    if dari:
        params["dari"] = dari
    if sampai:
        params["sampai"] = sampai
    if ringkasan:
        params["ringkasan"] = True
    if mode == "kelas" and kelas_id:
        params["kelas_id"] = kelas_id
    elif mode == "murid" and murid_id:
        params["murid_id"] = murid_id
    else:
        return RedirectResponse("/madrasah-app/absensi/cetak-absen", status_code=303)

    r = await api_get_raw(request, "/api/absensi/cetak.xlsx", **params)
    return Response(
        content=r,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=cetak-absen.xlsx"},
    )
