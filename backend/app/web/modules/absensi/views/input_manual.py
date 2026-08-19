"""Input Manual view: bulk per kelas (H/I/S/A) + individual fallback."""
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_get, api_post
from ....core.deps import require_login_web, require_permission_web
from ....core.templates import templates

router = APIRouter()


def _redirect(msg: str, type_: str = "success", path: str = "/madrasah-app/absensi/input-manual"):
    return RedirectResponse(
        url=f"{path}?msg={msg.replace(' ', '+')}&type={type_}",
        status_code=303,
    )


@router.get("/input-manual")
async def input_manual_bulk(
    request: Request,
    kelas_id: int | None = None,
    tanggal: str | None = None,
    tab: str = Query("bulk"),  # 'bulk' atau 'individual'
    q: str | None = None,
    user: dict = Depends(require_login_web),
):
    """Halaman input absen dengan 2 tab: bulk per kelas + individual."""
    # Ambil kelas TA aktif
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_ajaran_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_ajaran_list if ta.get("is_active")), None)
    tahun_aktif_id = tahun_aktif["id"] if tahun_aktif else None

    kelas_r = await api_get(request, "/api/kelas", tahun_ajaran_id=tahun_aktif_id or "")
    kelas_list = kelas_r.json() if kelas_r.status_code == 200 else []

    # Default kelas: kalau ada, pakai yang pertama
    if not kelas_id and kelas_list:
        kelas_id = kelas_list[0]["id"]

    # Parse tanggal
    from datetime import date as date_cls, datetime
    if tanggal:
        try:
            tgl = datetime.strptime(tanggal, "%Y-%m-%d").date()
        except ValueError:
            tgl = date_cls.today()
    else:
        tgl = date_cls.today()

    # ===== Tab Bulk =====
    roster = []
    if tab == "bulk" and kelas_id:
        roster_r = await api_get(
            request,
            f"/api/absensi/kelas/{kelas_id}",
            tanggal=tgl.isoformat(),
        )
        if roster_r.status_code == 200:
            roster = roster_r.json()

    # ===== Tab Individual =====
    murid_results = []
    if tab == "individual" and q and len(q.strip()) >= 2:
        params = {"q": q.strip(), "per_page": 30}
        murid_r = await api_get(request, "/api/murid", **params)
        if murid_r.status_code == 200:
            murid_results = murid_r.json().get("items", [])

    return templates.TemplateResponse(
        request,
        "input_manual/list.html",
        {
            "user": user,
            "tab": tab,
            "kelas_list": kelas_list,
            "kelas_id": kelas_id,
            "tgl_str": tgl.isoformat(),
            "roster": roster,
            "q": q or "",
            "murid_results": murid_results,
        },
    )


@router.post("/input-manual/bulk")
async def input_manual_bulk_submit(
    request: Request,
    kelas_id: int = Form(...),
    tanggal: str = Form(...),
    entries: list[str] = Form([]),  # entries[i] = "murid_id:status"
    user: dict = Depends(require_login_web),
):
    """Submit bulk absen per kelas."""
    parsed = []
    for entry in entries:
        if ":" in entry:
            mid_s, status = entry.split(":", 1)
            if mid_s.isdigit() and status in ("hadir", "izin", "sakit", "alpa"):
                parsed.append({"murid_id": int(mid_s), "status": status})

    if not parsed:
        return _redirect("Tidak ada perubahan", "error")

    payload = {"tanggal": tanggal, "entries": parsed}
    r = await api_post(request, f"/api/absensi/kelas/{kelas_id}", json=payload)
    if r.status_code == 200:
        try:
            result = r.json()
            ditambahkan = result.get("ditambahkan", 0)
            diubah = result.get("diubah", 0)
            sudah_ada = result.get("sudah_ada", 0)
            parts = []
            if ditambahkan:
                parts.append(f"{ditambahkan} ditambah")
            if diubah:
                parts.append(f"{diubah} diubah")
            if sudah_ada:
                parts.append(f"{sudah_ada} sudah ada")
            msg = "Berhasil: " + ", ".join(parts) if parts else "Tidak ada perubahan"
            return RedirectResponse(
                url=f"/madrasah-app/absensi/input-manual?tab=bulk&kelas_id={kelas_id}&tanggal={tanggal}&msg={msg.replace(' ', '+')}&type=success",
                status_code=303,
            )
        except Exception:
            return RedirectResponse(
                url=f"/madrasah-app/absensi/input-manual?tab=bulk&kelas_id={kelas_id}&tanggal={tanggal}&msg=Berhasil&type=success",
                status_code=303,
            )
    detail = "Gagal menyimpan"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return RedirectResponse(
        url=f"/madrasah-app/absensi/input-manual?tab=bulk&kelas_id={kelas_id}&tanggal={tanggal}&msg={detail.replace(' ', '+')}&type=error",
        status_code=303,
    )


@router.post("/input-manual")
async def input_manual_individual_submit(
    request: Request,
    murid_id: int = Form(...),
    q: str = Form(""),
    user: dict = Depends(require_login_web),
):
    """Submit tandai hadir individual (fallback)."""
    payload = {"murid_id": murid_id}
    r = await api_post(request, "/api/absensi/manual", json=payload)
    if r.status_code in (200, 201):
        try:
            data = r.json()
            msg = data.get("pesan", "Berhasil")
        except Exception:
            msg = "Berhasil dicatat"
        return RedirectResponse(
            url=f"/madrasah-app/absensi/input-manual?tab=individual&q={q}&msg={msg.replace(' ', '+')}&type=success",
            status_code=303,
        )
    detail = "Gagal mencatat"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return RedirectResponse(
        url=f"/madrasah-app/absensi/input-manual?tab=individual&q={q}&msg={detail.replace(' ', '+')}&type=error",
        status_code=303,
    )