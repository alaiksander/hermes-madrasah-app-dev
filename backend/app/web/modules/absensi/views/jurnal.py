"""Jurnal Mengajar — UI web (Jinja2 + HTMX).

Route order matters for FastAPI/Starlette:
  1. /riwayat       (harus SEBELUM /{jurnal_id} — sonst "riwayat" di-cast ke int)
  2. /input          (sebelum /{jurnal_id})
  3. /{jurnal_id}    (catch-all, setelah yang spesifik)
  4. /{jurnal_id}/edit  (harus SEBELUM /{jurnal_id} karena lebih spesifik)
"""
from datetime import date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_get, api_get_raw, api_post
from ....core.deps import require_login_web
from ....core.templates import templates

router = APIRouter(prefix="/jurnal", tags=["jurnal-web"])
WIB = ZoneInfo("Asia/Jakarta")


def _today() -> date:
    from datetime import datetime
    return datetime.now(WIB).date()


# ── Dashboard ─────────────────────────────────────────────────────────────

@router.get("")
async def jurnal_dashboard(request: Request,
                            user: dict = Depends(require_login_web)):
    """Dashboard jurnal: statistik pribadi (guru) atau semua (admin)."""
    dari = f"{_today().year}-{_today().month:02d}-01"
    sampai = str(_today())

    r_stats = await api_get(request, f"/api/jurnal/stats/bulan-ini")
    stats = r_stats.json() if r_stats.status_code == 200 else {}

    r_list = await api_get(request, f"/api/jurnal?dari={dari}&sampai={sampai}")
    jurnal_list = r_list.json() if r_list.status_code == 200 else []

    return templates.TemplateResponse(
        "jurnal/dashboard.html",
        {"request": request, "user": user,
         "stats": stats, "jurnal_list": jurnal_list,
         "dari": dari, "sampai": sampai},
    )


# ── Riwayat (SEBELUM /{jurnal_id}) ────────────────────────────────────────

# ── Export (halaman pilihan sebelum download) ─────────────────────────────

@router.get("/export")
async def jurnal_export_page(request: Request,
                             dari: str | None = None,
                             sampai: str | None = None,
                             kelas_id: int | None = None,
                             user: dict = Depends(require_login_web)):
    """Halaman pilihan export: periode + kelas + status + rekap absensi.

    Bukan download langsung — user pilih opsi, lalu klik Export Excel/PDF.
    """
    # Kelas: hanya tahun ajaran aktif
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_list if ta.get("is_active")), None)
    ta_id = tahun_aktif["id"] if tahun_aktif else None
    r_kelas = await api_get(request, "/api/kelas", tahun_ajaran_id=ta_id or "")
    kelas_list = r_kelas.json() if r_kelas.status_code == 200 else []

    return templates.TemplateResponse(
        "jurnal/export.html",
        {"request": request, "user": user,
         "kelas_list": kelas_list,
         "filter_dari": dari, "filter_sampai": sampai,
         "filter_kelas_id": kelas_id},
    )


@router.get("/export-xlsx")
async def jurnal_export_xlsx(request: Request,
                             dari: str | None = None,
                             sampai: str | None = None,
                             kelas_id: str | None = None,
                             status: str | None = None,
                             rekap_absensi: str | None = "true",
                             user: dict = Depends(require_login_web)):
    """Export jurnal Excel (proxy ke API)."""
    from fastapi.responses import Response
    params = []
    if dari:
        params.append(f"dari={dari}")
    if sampai:
        params.append(f"sampai={sampai}")
    if kelas_id and kelas_id.strip().isdigit():
        params.append(f"kelas_id={kelas_id.strip()}")
    if status:
        params.append(f"status={status}")
    params.append(f"rekap_absensi={rekap_absensi or 'true'}")
    q = "&".join(params)
    url = f"/api/jurnal/export.xlsx?{q}" if q else "/api/jurnal/export.xlsx"
    content = await api_get_raw(request, url)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="jurnal-mengajar.xlsx"'},
    )


@router.get("/export-pdf")
async def jurnal_export_pdf(request: Request,
                            dari: str | None = None,
                            sampai: str | None = None,
                            kelas_id: str | None = None,
                            status: str | None = None,
                            rekap_absensi: str | None = "true",
                            user: dict = Depends(require_login_web)):
    """Export jurnal PDF (proxy ke API)."""
    from fastapi.responses import Response
    params = []
    if dari:
        params.append(f"dari={dari}")
    if sampai:
        params.append(f"sampai={sampai}")
    if kelas_id and kelas_id.strip().isdigit():
        params.append(f"kelas_id={kelas_id.strip()}")
    if status:
        params.append(f"status={status}")
    params.append(f"rekap_absensi={rekap_absensi or 'true'}")
    q = "&".join(params)
    url = f"/api/jurnal/export.pdf?{q}" if q else "/api/jurnal/export.pdf"
    content = await api_get_raw(request, url)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="jurnal-mengajar.pdf"'},
    )


@router.get("/riwayat")
async def jurnal_riwayat(request: Request,
                          dari: str | None = None,
                          sampai: str | None = None,
                          kelas_id: int | None = None,
                          user: dict = Depends(require_login_web)):
    """Daftar riwayat jurnal dengan filter."""
    params = []
    if dari:
        params.append(f"dari={dari}")
    if sampai:
        params.append(f"sampai={sampai}")
    if kelas_id:
        params.append(f"kelas_id={kelas_id}")
    q = "&".join(params)
    url = f"/api/jurnal?{q}" if q else "/api/jurnal"
    r_list = await api_get(request, url)
    jurnal_list = r_list.json() if r_list.status_code == 200 else []
    r_kelas = await api_get(request, "/api/kelas")
    kelas_list = r_kelas.json() if r_kelas.status_code == 200 else []
    return templates.TemplateResponse(
        "jurnal/riwayat.html",
        {"request": request, "user": user,
         "jurnal_list": jurnal_list, "kelas_list": kelas_list,
         "filter_dari": dari, "filter_sampai": sampai,
         "filter_kelas_id": kelas_id},
    )


# ── Input Jurnal (SEBELUM /{jurnal_id}) ───────────────────────────────────

@router.get("/input")
async def jurnal_input(request: Request,
                       user: dict = Depends(require_login_web)):
    """Form input jurnal mengajar baru."""
    r = await api_get(request, "/api/kelas")
    kelas_list = r.json() if r.status_code == 200 else []
    r_mapel = await api_get(request, "/api/mapel", aktif_saja=True)
    mapel_list = r_mapel.json() if r_mapel.status_code == 200 else []
    return templates.TemplateResponse(
        "jurnal/input.html",
        {"request": request, "user": user,
         "kelas_list": kelas_list, "mapel_list": mapel_list,
         "today": str(_today())},
    )


@router.post("/input")
async def jurnal_input_submit(request: Request,
                               user: dict = Depends(require_login_web)):
    """Proses submit form input jurnal → redirect ke detail."""
    form = await request.form()
    mapel_id = form.get("mapel_id")
    # Ambil nama mapel dari master (wajib pilih dari dropdown)
    nama_mapel = ""
    if mapel_id:
        r = await api_get(request, "/api/mapel", aktif_saja=True)
        mapel_list = r.json() if r.status_code == 200 else []
        nama_mapel = next(
            (m["nama"] for m in mapel_list if str(m["id"]) == str(mapel_id)), "")
    data = {
        "kelas_id": int(form.get("kelas_id")),
        "mata_pelajaran": nama_mapel,
        "tanggal": str(form.get("tanggal")),
        "jam_mulai": str(form.get("jam_mulai")),
        "jam_selesai": str(form.get("jam_selesai")),
        "materi": form.get("materi", "").strip() or None,
        "catatan": form.get("catatan", "").strip() or None,
    }
    r = await api_post(request, "/api/jurnal", data)
    if r.status_code in (200, 201):
        result = r.json()
        jurnal_id = result.get("id")
        return RedirectResponse(f"/madrasah-app/jurnal/{jurnal_id}", status_code=303)
    return RedirectResponse(f"/madrasah-app/jurnal/input", status_code=303)


# ── Detail Jurnal ──────────────────────────────────────────────────────────

@router.get("/{jurnal_id}")
async def jurnal_detail(jurnal_id: int,
                        request: Request,
                        user: dict = Depends(require_login_web)):
    """Detail jurnal + absensi per-murid (inline editable)."""
    r = await api_get(request, f"/api/jurnal/{jurnal_id}")
    if r.status_code != 200:
        return RedirectResponse("/madrasah-app/jurnal/", status_code=303)
    jurnal = r.json()
    return templates.TemplateResponse(
        "jurnal/detail.html",
        {"request": request, "user": user, "jurnal": jurnal},
    )


@router.post("/{jurnal_id}/submit")
async def jurnal_submit(jurnal_id: int,
                         request: Request,
                         user: dict = Depends(require_login_web)):
    """Submit jurnal (draft → submitted)."""
    await api_post(request, f"/api/jurnal/{jurnal_id}/submit", {})
    return RedirectResponse(f"/madrasah-app/jurnal/{jurnal_id}", status_code=303)


@router.post("/{jurnal_id}/absensi")
async def jurnal_absensi_update(jurnal_id: int,
                                  request: Request,
                                  user: dict = Depends(require_login_web)):
    """Bulk update absensi murid untuk jurnal ini."""
    form = await request.form()
    updates = {}
    for key, val in form.multi_items():
        if key.startswith("absen_"):
            murid_id = int(key.replace("absen_", ""))
            updates[murid_id] = val
    await api_post(request, f"/api/jurnal/{jurnal_id}/absensi",
                   {"updates": updates})
    return RedirectResponse(f"/madrasah-app/jurnal/{jurnal_id}", status_code=303)


# ── Edit Jurnal (SEBELUM /{jurnal_id} untuk /edit path) ────────────────────

@router.get("/{jurnal_id}/edit")
async def jurnal_edit(jurnal_id: int,
                       request: Request,
                       user: dict = Depends(require_login_web)):
    """Form edit jurnal."""
    r = await api_get(request, f"/api/jurnal/{jurnal_id}")
    if r.status_code != 200:
        return RedirectResponse("/madrasah-app/jurnal/", status_code=303)
    jurnal = r.json()
    r_kelas = await api_get(request, "/api/kelas")
    kelas_list = r_kelas.json() if r_kelas.status_code == 200 else []
    r_mapel = await api_get(request, "/api/mapel", aktif_saja=True)
    mapel_list = r_mapel.json() if r_mapel.status_code == 200 else []
    return templates.TemplateResponse(
        "jurnal/edit.html",
        {"request": request, "user": user,
         "jurnal": jurnal, "kelas_list": kelas_list,
         "mapel_list": mapel_list},
    )


@router.post("/{jurnal_id}/edit")
async def jurnal_edit_submit(jurnal_id: int,
                              request: Request,
                              user: dict = Depends(require_login_web)):
    """Proses submit edit jurnal."""
    form = await request.form()
    mapel_id = form.get("mapel_id")
    nama_mapel = ""
    if mapel_id:
        r = await api_get(request, "/api/mapel", aktif_saja=True)
        mapel_list = r.json() if r.status_code == 200 else []
        nama_mapel = next(
            (m["nama"] for m in mapel_list if str(m["id"]) == str(mapel_id)), "")
    data = {
        "kelas_id": int(form.get("kelas_id")),
        "mata_pelajaran": nama_mapel,
        "tanggal": str(form.get("tanggal")),
        "jam_mulai": str(form.get("jam_mulai")),
        "jam_selesai": str(form.get("jam_selesai")),
        "materi": form.get("materi", "").strip() or None,
        "catatan": form.get("catatan", "").strip() or None,
    }
    r = await api_post(request, f"/api/jurnal/{jurnal_id}", data)
    if r.status_code == 200:
        result = r.json()
        j_id = result.get("id")
        return RedirectResponse(f"/madrasah-app/jurnal/{j_id}", status_code=303)
    return RedirectResponse(f"/madrasah-app/jurnal/{jurnal_id}/edit", status_code=303)
