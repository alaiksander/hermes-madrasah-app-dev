"""Penilaian view: halaman input nilai + rekap per kelas.

Alur: /penilaian (daftar materi, filter kelas/mapel/jenis)
      → /penilaian/materi/{id} (input nilai per siswa)
      → /penilaian/rekap?kelas_id= (rekap + export RDM)
Akses: permission penilaian.view / penilaian.input.
"""
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_get, api_post, api_patch, api_delete, api_get_raw
from ....core.deps import require_login_web, require_permission_web
from ....core.templates import templates

router = APIRouter(tags=["web-penilaian"])

JENIS_LABEL = {
    "tugas": "Tugas",
    "sumatif": "Sumatif",
    "asas": "ASAS",
    "asat": "ASAT",
}


def _redirect(msg: str, type_: str = "success", path: str = "/madrasah-app/penilaian"):
    return RedirectResponse(
        url=f"{path}?msg={msg.replace(' ', '+')}&type={type_}",
        status_code=303,
    )


@router.get("")
async def penilaian_list(
    request: Request,
    kelas_id: int | None = None,
    mapel_id: int | None = None,
    jenis: str | None = None,
    user: dict = Depends(require_permission_web("penilaian.view", "penilaian.input", "penilaian.export")),
):
    """Daftar materi penilaian (filter kelas/mapel/jenis)."""
    # Kelas: hanya tahun ajaran aktif
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_ajaran_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_ajaran_list if ta.get("is_active")), None)
    kelas_params = {}
    if tahun_aktif:
        kelas_params["tahun_ajaran_id"] = tahun_aktif["id"]
    kelas_r = await api_get(request, "/api/kelas", **kelas_params)
    kelas_list = kelas_r.json() if kelas_r.status_code == 200 else []
    mapel_r = await api_get(request, "/api/mapel")
    mapel_list = mapel_r.json() if mapel_r.status_code == 200 else []

    params = {}
    if kelas_id:
        params["kelas_id"] = kelas_id
    if mapel_id:
        params["mapel_id"] = mapel_id
    if jenis:
        params["jenis"] = jenis
    materi_r = await api_get(request, "/api/nilai/materi", **params)
    materi_list = materi_r.json() if materi_r.status_code == 200 else []

    return templates.TemplateResponse(
        request,
        "penilaian/list.html",
        {
            "user": user,
            "materi_list": materi_list,
            "kelas_list": kelas_list,
            "mapel_list": mapel_list,
            "jenis_label": JENIS_LABEL,
            "kelas_id": kelas_id,
            "mapel_id": mapel_id,
            "jenis": jenis,
        },
    )


@router.get("/baru")
async def penilaian_baru(
    request: Request,
    user: dict = Depends(require_permission_web("penilaian.input")),
):
    """Form buat materi penilaian baru."""
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_ajaran_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_ajaran_list if ta.get("is_active")), None)
    kelas_params = {}
    if tahun_aktif:
        kelas_params["tahun_ajaran_id"] = tahun_aktif["id"]
    kelas_r = await api_get(request, "/api/kelas", **kelas_params)
    mapel_r = await api_get(request, "/api/mapel")
    return templates.TemplateResponse(
        request,
        "penilaian/form.html",
        {
            "user": user,
            "kelas_list": kelas_r.json() if kelas_r.status_code == 200 else [],
            "mapel_list": mapel_r.json() if mapel_r.status_code == 200 else [],
            "materi": None,
            "jenis_label": JENIS_LABEL,
        },
    )


@router.post("")
async def penilaian_create(
    request: Request,
    mapel_id: int = Form(...),
    kelas_id: int | None = Form(None),
    jenis: str = Form("sumatif"),
    nama: str = Form(...),
    materi: str = Form(""),
    kkpt: int = Form(70),
    user: dict = Depends(require_permission_web("penilaian.input")),
):
    r = await api_post(request, "/api/nilai/materi", json={
        "mapel_id": mapel_id, "kelas_id": kelas_id, "jenis": jenis,
        "nama": nama.strip(), "materi": materi.strip(), "kkpt": kkpt,
    })
    if r.status_code not in (200, 201):
        return _redirect(f"Gagal: {r.text[:120]}", "error")
    data = r.json()
    return _redirect(f"Materi penilaian '{data.get('nama')}' dibuat",
                     "success", f"/madrasah-app/penilaian/materi/{data.get('id')}")


@router.get("/materi/{materi_id}")
async def penilaian_materi_detail(
    request: Request,
    materi_id: int,
    user: dict = Depends(require_permission_web("penilaian.view", "penilaian.input")),
):
    """Form input nilai per siswa untuk satu materi."""
    r = await api_get(request, f"/api/nilai/materi/{materi_id}/siswa")
    if r.status_code != 200:
        return templates.TemplateResponse(
            request, "error.html",
            {"status_code": r.status_code, "message": "Materi penilaian tidak ditemukan."},
            status_code=r.status_code)
    data = r.json()
    return templates.TemplateResponse(
        request,
        "penilaian/input.html",
        {"user": user, "data": data, "jenis_label": JENIS_LABEL},
    )


@router.post("/materi/{materi_id}/simpan")
async def penilaian_materi_simpan(
    request: Request,
    materi_id: int,
    user: dict = Depends(require_permission_web("penilaian.input")),
):
    """Simpan nilai bulk dari form (skor per murid_id)."""
    form = await request.form()
    entries = []
    for key, val in form.items():
        if key.startswith("skor_"):
            mid = int(key.split("_", 1)[1])
            v = str(val).strip()
            skor = int(v) if v else None
            if skor is not None and not (0 <= skor <= 100):
                return _redirect(f"Nilai murid id={mid} harus 0-100", "error",
                                 f"/madrasah-app/penilaian/materi/{materi_id}")
            entries.append({"murid_id": mid, "skor": skor})
    if not entries:
        return _redirect("Tidak ada nilai diisi", "error",
                         f"/madrasah-app/penilaian/materi/{materi_id}")
    r = await api_post(request, "/api/nilai/bulk", json={
        "materi_penilaian_id": materi_id, "entries": entries})
    if r.status_code != 200:
        return _redirect(f"Gagal simpan: {r.text[:120]}", "error",
                         f"/madrasah-app/penilaian/materi/{materi_id}")
    data = r.json()
    return _redirect(f"{data.get('disimpan')} nilai tersimpan", "success",
                     f"/madrasah-app/penilaian/materi/{materi_id}")


@router.post("/materi/{materi_id}/hapus")
async def penilaian_materi_hapus(
    request: Request,
    materi_id: int,
    user: dict = Depends(require_permission_web("penilaian.input")),
):
    r = await api_delete(request, f"/api/nilai/materi/{materi_id}")
    return _redirect("Materi penilaian dihapus", "success")


@router.get("/rekap")
async def penilaian_rekap(
    request: Request,
    kelas_id: int | None = Query(None),
    mapel_id: int | None = None,
    user: dict = Depends(require_permission_web("penilaian.view", "penilaian.input", "penilaian.export")),
):
    """Rekap nilai per kelas. Tanpa kelas_id → auto-pilih kelas pertama TA aktif."""
    # Kelas: hanya tahun ajaran aktif
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_ajaran_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_ajaran_list if ta.get("is_active")), None)
    kelas_params = {}
    if tahun_aktif:
        kelas_params["tahun_ajaran_id"] = tahun_aktif["id"]
    kelas_r = await api_get(request, "/api/kelas", **kelas_params)
    kelas_list = kelas_r.json() if kelas_r.status_code == 200 else []

    if kelas_id is None and kelas_list:
        kelas_id = kelas_list[0]["id"]  # default kelas pertama TA aktif
    if kelas_id is None:
        return templates.TemplateResponse(
            request, "penilaian/rekap.html",
            {"user": user, "data": {"kelas_nama": "—", "materi": [], "murid": []},
             "kelas_list": [], "mapel_list": [], "kelas_id": None, "mapel_id": None,
             "jenis_label": JENIS_LABEL, "no_kelas": True})

    params = {"kelas_id": kelas_id}
    if mapel_id:
        params["mapel_id"] = mapel_id
    r = await api_get(request, "/api/nilai/rekap", **params)
    if r.status_code != 200:
        return templates.TemplateResponse(
            request, "error.html",
            {"status_code": r.status_code, "message": "Kelas tidak ditemukan."},
            status_code=r.status_code)
    data = r.json()
    mapel_r = await api_get(request, "/api/mapel")
    mapel_list = mapel_r.json() if mapel_r.status_code == 200 else []
    return templates.TemplateResponse(
        request,
        "penilaian/rekap.html",
        {
            "user": user,
            "data": data,
            "kelas_list": kelas_list,
            "mapel_list": mapel_list,
            "kelas_id": kelas_id,
            "mapel_id": mapel_id,
            "jenis_label": JENIS_LABEL,
        },
    )


@router.get("/export-rdm")
async def penilaian_export_rdm(
    request: Request,
    kelas_id: int = Query(...),
    user: dict = Depends(require_permission_web("penilaian.export", "penilaian.view")),
):
    """Export rekap nilai format RDM (Excel)."""
    from fastapi.responses import Response
    content = await api_get_raw(request, "/api/nilai/export-rdm", kelas_id=kelas_id)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="rekap-nilai-rdm-kelas-{kelas_id}.xlsx"'},
    )
