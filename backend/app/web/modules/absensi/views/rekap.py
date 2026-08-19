"""Rekap absensi view: daily rekap per kelas + filter tanggal + detail per kelas."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_get, api_get_raw, api_post
from ....core.deps import require_login_web
from ....core.templates import templates

router = APIRouter()


def _redirect(msg: str, type_: str = "success", path: str = "/madrasah-app/absensi/rekap"):
    return RedirectResponse(
        url=f"{path}?msg={msg.replace(' ', '+')}&type={type_}",
        status_code=303,
    )


@router.get("/rekap")
async def rekap_list(
    request: Request,
    tanggal: str | None = None,
    kelas_id: int | None = None,
    user: dict = Depends(require_login_web),
):
    """Rekap absensi per kelas untuk tanggal tertentu.

    Default: hari ini, semua kelas.
    """
    # Parse tanggal (default hari ini)
    try:
        if tanggal:
            tgl = datetime.strptime(tanggal, "%Y-%m-%d").date()
        else:
            tgl = date.today()
    except ValueError:
        return _redirect("Format tanggal tidak valid", "error")

    # Ambil daftar kelas (TA aktif)
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_ajaran_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_ajaran_list if ta.get("is_active")), None)
    tahun_aktif_id = tahun_aktif["id"] if tahun_aktif else None

    kelas_r = await api_get(request, "/api/kelas", tahun_ajaran_id=tahun_aktif_id or "")
    kelas_list = kelas_r.json() if kelas_r.status_code == 200 else []

    # Ambil rekap dari API
    rekap_r = await api_get(
        request,
        "/api/absensi/rekap",
        tanggal=tgl.isoformat(),
    )
    rekap_data = rekap_r.json() if rekap_r.status_code == 200 else {}

    # Filter per kelas kalau ada
    by_kelas = {}
    if kelas_id:
        for entry in rekap_data.get("items", []):
            if entry.get("kelas_id") == kelas_id:
                by_kelas[entry["kelas_id"]] = entry
    else:
        for entry in rekap_data.get("items", []):
            by_kelas[entry["kelas_id"]] = entry

    # Stats per kelas
    kelas_with_stats = []
    total_murid = 0
    total_hadir = 0
    total_sakit = 0
    total_izin = 0
    total_alpa = 0
    for k in kelas_list:
        stats = by_kelas.get(k["id"], {})
        n_murid = stats.get("jumlah_murid", k.get("jumlah_murid", 0))
        n_hadir = stats.get("hadir", 0)
        n_sakit = stats.get("sakit", 0)
        n_izin = stats.get("izin", 0)
        n_alpa = stats.get("alpa", 0)

        kelas_with_stats.append({
            **k,
            "n_murid": n_murid,
            "n_hadir": n_hadir,
            "n_sakit": n_sakit,
            "n_izin": n_izin,
            "n_alpa": n_alpa,
            "n_belum": max(0, n_murid - n_hadir - n_sakit - n_izin - n_alpa),
        })
        total_murid += n_murid
        total_hadir += n_hadir
        total_sakit += n_sakit
        total_izin += n_izin
        total_alpa += n_alpa

    # Yesterday for navigation
    yesterday = (tgl - timedelta(days=1)).isoformat()
    tomorrow = (tgl + timedelta(days=1)).isoformat()

    return templates.TemplateResponse(
        request,
        "rekap/list.html",
        {
            "user": user,
            "kelas_list": kelas_with_stats,
            "tgl": tgl,
            "tgl_str": tgl.isoformat(),
            "yesterday": yesterday,
            "tomorrow": tomorrow,
            "kelas_id": kelas_id,
            "is_today": tgl == date.today(),
            "total_murid": total_murid,
            "total_hadir": total_hadir,
            "total_sakit": total_sakit,
            "total_izin": total_izin,
            "total_alpa": total_alpa,
        },
    )


@router.get("/rekap-detail")
async def rekap_detail(
    request: Request,
    kelas_id: int = Query(...),
    tanggal: str | None = None,
    user: dict = Depends(require_login_web),
):
    """Detail rekap per kelas (roster + status H/I/S/A)."""
    # Parse tanggal
    try:
        tgl = datetime.strptime(tanggal, "%Y-%m-%d").date() if tanggal else date.today()
    except ValueError:
        return _redirect("Format tanggal tidak valid", "error")

    # Ambil data kelas dari list (no GET single endpoint)
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_ajaran_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_ajaran_list if ta.get("is_active")), None)
    tahun_aktif_id = tahun_aktif["id"] if tahun_aktif else None

    kelas_list_r = await api_get(request, "/api/kelas", tahun_ajaran_id=tahun_aktif_id or "")
    kelas_list = kelas_list_r.json() if kelas_list_r.status_code == 200 else []
    kelas = next((k for k in kelas_list if k["id"] == kelas_id), None)
    if not kelas:
        return _redirect("Kelas tidak ditemukan", "error")

    # Ambil roster kelas untuk tanggal ini
    roster_r = await api_get(
        request,
        f"/api/absensi/kelas/{kelas_id}",
        tanggal=tgl.isoformat(),
    )
    roster = roster_r.json() if roster_r.status_code == 200 else []

    # Hitung statistik
    n_hadir = sum(1 for r in roster if r.get("status") == "hadir")
    n_izin = sum(1 for r in roster if r.get("status") == "izin")
    n_sakit = sum(1 for r in roster if r.get("status") == "sakit")
    n_alpa = sum(1 for r in roster if r.get("status") == "alpa")
    n_belum = sum(1 for r in roster if not r.get("status"))

    # Yesterday / tomorrow
    yesterday = (tgl - timedelta(days=1)).isoformat()
    tomorrow = (tgl + timedelta(days=1)).isoformat()

    return templates.TemplateResponse(
        request,
        "rekap/detail.html",
        {
            "user": user,
            "kelas": kelas,
            "roster": roster,
            "tgl": tgl,
            "tgl_str": tgl.isoformat(),
            "yesterday": yesterday,
            "tomorrow": tomorrow,
            "is_today": tgl == date.today(),
            "n_hadir": n_hadir,
            "n_izin": n_izin,
            "n_sakit": n_sakit,
            "n_alpa": n_alpa,
            "n_belum": n_belum,
            "total": len(roster),
        },
    )


@router.post("/rekap-detail")
async def rekap_detail_submit(
    request: Request,
    kelas_id: int = Form(...),
    tanggal: str = Form(...),
    entries: list[str] = Form([]),  # entries[i]=murid_id:status
    user: dict = Depends(require_login_web),
):
    """Bulk update absensi per kelas (back-fill hari yang sudah lewat)."""
    # Parse entries dari form: entries[i] = "murid_id:status"
    parsed_entries = []
    for entry in entries:
        if ":" in entry:
            mid_s, status = entry.split(":", 1)
            if mid_s.isdigit() and status in ("hadir", "izin", "sakit", "alpa"):
                parsed_entries.append({
                    "murid_id": int(mid_s),
                    "status": status,
                })

    if not parsed_entries:
        return _redirect("Tidak ada perubahan", "error")

    payload = {
        "tanggal": tanggal,
        "entries": parsed_entries,
    }
    r = await api_post(request, f"/api/absensi/kelas/{kelas_id}", json=payload)
    if r.status_code == 200:
        try:
            result = r.json()
            ditambahkan = result.get("ditambahkan", 0)
            diubah = result.get("diubah", 0)
            msg_parts = []
            if ditambahkan:
                msg_parts.append(f"{ditambahkan} ditambah")
            if diubah:
                msg_parts.append(f"{diubah} diubah")
            msg = "Berhasil: " + ", ".join(msg_parts) if msg_parts else "Tidak ada perubahan"
            return _redirect(msg)
        except Exception:
            return _redirect("Berhasil disimpan")
    detail = "Gagal menyimpan"
    try:
        detail = r.json().get("detail", detail)
    except Exception:
        pass
    return _redirect(detail, "error")