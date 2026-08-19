"""Kartu QR — cetak per kelas (massal) & per anak (individual).

Menu baru di grup Absensi (2026-08-15, keputusan Mr.):
- QR adalah alat absensi → pindah dari halaman Murid ke menu Kartu QR
- Tab 1: Per Kelas (massal, layout A4 2×5)
- Tab 2: Per Anak (search + preview single card)
- Route lama /qr-print & /murid/{id}/qr-card redirect ke sini
"""
import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, Response

from ....core.client import api_get, api_get_raw
from ....core.deps import require_permission_web
from ....core.templates import templates

router = APIRouter()


def _split_name(nama: str) -> list[str]:
    """Bagi nama jadi maks 2 baris seimbang (untuk preview HTML).

    Konsisten dengan _balanced_lines di routers/qr.py (PDF): nama >18
    karakter dipecah di titik word-boundary dengan selisih panjang
    terkecil. Nama pendek tetap 1 baris.
    """
    if len(nama) <= 18:
        return [nama]
    words = nama.split()
    if len(words) <= 1:
        return [nama]
    best = None
    for i in range(1, len(words)):
        l1 = " ".join(words[:i])
        l2 = " ".join(words[i:])
        diff = abs(len(l1) - len(l2))
        if best is None or diff < best[0]:
            best = (diff, l1, l2)
    if best:
        return [best[1], best[2]]
    return [nama]


async def _kelas_by_ta_aktif(request: Request):
    """Ambil kelas hanya untuk tahun ajaran AKTIF."""
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_ajaran_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_ajaran_list if ta.get("is_active")), None)
    tahun_aktif_id = tahun_aktif["id"] if tahun_aktif else None

    kelas_r = await api_get(request, "/api/kelas", tahun_ajaran_id=tahun_aktif_id or "")
    kelas_list = kelas_r.json() if kelas_r.status_code == 200 else []
    return kelas_list, tahun_aktif


@router.get("/kartu-qr")
async def kartu_qr(
    request: Request,
    tab: str = Query("kelas"),  # 'kelas' | 'anak'
    kelas_id: int | None = None,
    q: str | None = None,
    murid_id: int | None = None,
    user: dict = Depends(require_permission_web("murid.qr")),
):
    """Halaman Kartu QR — 2 tab (default: Per Kelas)."""
    kelas_list, tahun_aktif = await _kelas_by_ta_aktif(request)

    murid_list = []
    selected_murid = None
    if tab == "anak":
        # Tab Per Anak: search murid (nama/NIS)
        if q and len(q.strip()) >= 2:
            murid_r = await api_get(request, "/api/murid", q=q.strip(), per_page=50)
            if murid_r.status_code == 200:
                murid_list = murid_r.json().get("items", [])
        elif murid_id:
            # Langsung buka murid tertentu (dari redirect /murid/{id}/qr-card)
            r = await api_get(request, f"/api/murid/{murid_id}")
            if r.status_code == 200:
                selected_murid = r.json()
                selected_murid["nama_baris"] = _split_name(selected_murid.get("nama", ""))
            else:
                murid_r = await api_get(request, "/api/murid", per_page=20)
                if murid_r.status_code == 200:
                    murid_list = murid_r.json().get("items", [])

    # Tab Per Kelas: ambil roster kalau kelas dipilih
    roster = []
    if tab == "kelas" and kelas_id:
        murid_r = await api_get(request, "/api/murid", kelas_id=kelas_id, per_page=200)
        if murid_r.status_code == 200:
            roster = murid_r.json().get("items", [])
            for m in roster:
                m["nama_baris"] = _split_name(m.get("nama", ""))

    return templates.TemplateResponse(
        request,
        "kartu_qr.html",
        {
            "user": user,
            "tab": tab,
            "kelas_list": kelas_list,
            "selected_kelas_id": kelas_id,
            "roster": roster,
            "q": q or "",
            "murid_list": murid_list,
            "selected_murid": selected_murid,
            "tahun_aktif_nama": tahun_aktif.get("nama") if tahun_aktif else None,
        },
    )


@router.get("/kartu-qr/pdf")
async def kartu_qr_pdf_kelas(
    request: Request,
    kelas_id: int = Query(...),
    user: dict = Depends(require_permission_web("murid.qr")),
):
    """Download PDF kartu QR massal per kelas."""
    try:
        content = await api_get_raw(
            request, "/api/murid/qr-pdf.pdf", kelas_id=kelas_id
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return RedirectResponse(
                "/madrasah-app/absensi/kartu-qr?tab=kelas&msg=Kelas+tidak+ditemukan&type=error",
                status_code=303,
            )
        raise
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="qr-kelas-{kelas_id}.pdf"'},
    )


@router.get("/kartu-qr/murid/{mid}/pdf")
async def kartu_qr_pdf_anak(
    request: Request,
    mid: int,
    user: dict = Depends(require_permission_web("murid.qr")),
):
    """Download PDF kartu QR satu murid."""
    try:
        content = await api_get_raw(request, f"/api/murid/{mid}/qr.pdf")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return RedirectResponse(
                f"/madrasah-app/absensi/kartu-qr?tab=anak&murid_id={mid}&msg=Murid+tidak+ditemukan&type=error",
                status_code=303,
            )
        raise
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="qr-{mid}.pdf"'},
    )


# ── Redirect route lama (biar link lama tidak 404) ─────────────────────

@router.get("/qr-print")
async def qr_print_redirect():
    """Route lama — redirect ke Kartu QR tab Per Kelas."""
    return RedirectResponse(
        "/madrasah-app/absensi/kartu-qr?tab=kelas", status_code=301
    )


@router.get("/murid/{mid}/qr-card")
async def qr_card_redirect(mid: int):
    """Route lama — redirect ke Kartu QR tab Per Anak."""
    return RedirectResponse(
        f"/madrasah-app/absensi/kartu-qr?tab=anak&murid_id={mid}", status_code=301
    )