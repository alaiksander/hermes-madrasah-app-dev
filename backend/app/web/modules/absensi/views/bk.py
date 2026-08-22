"""Bimbingan Konseling (BK) — UI untuk admin/guru BK.

Halaman:
- /absensi/bk/                  → Dashboard BK (ringkasan + top pelanggaran)
- /absensi/bk/catatan           → Daftar catatan (filterable)
- /absensi/bk/catatan/new       → Form buat catatan
- /absensi/bk/catatan/{id}/edit → Form edit catatan
- /absensi/bk/sesi              → Daftar sesi konseling
- /absensi/bk/sesi/new          → Form buat sesi
- /absensi/bk/rekap             → Rekap poin (leaderboard pelanggaran)
- /absensi/bk/monitor/{murid_id} → Monitor profil BK per murid
- /absensi/bk/master            → Master kategori & pelanggaran
- /absensi/bk/konfigurasi       → Setelan BK (threshold SP, dll.)
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse

from ....core.client import api_delete, api_get, api_patch, api_post, api_put
from ....core.deps import require_permission_web, require_login_web
from ....core.templates import templates

router = APIRouter(prefix="/bk", tags=["bk-web"])

WIB = ZoneInfo("Asia/Jakarta")


def _today() -> date:
    return datetime.now(WIB).date()


# ── Dashboard ─────────────────────────────────────────────────────────────

@router.get("")
async def bk_dashboard(request: Request,
                        user: dict = Depends(require_login_web)):
    """Ringkasan BK (bulan ini): total catatan, sesi, top pelanggaran."""
    r = await api_get(request, "/api/bk/dashboard")
    data = r.json() if r.status_code == 200 else {}
    today = _today()
    return templates.TemplateResponse(
        request, "bk/dashboard.html",
        {"user": user, "data": data, "today": today.isoformat(),
         "err": None})


# ── Catatan ───────────────────────────────────────────────────────────────

async def _catatan_form_context(request, user, data, err=None, edit_id=None):
    """Helper: build context for catatan form (with optional error)."""
    from ....core.client import api_get
    kr = await api_get(request, "/api/bk/kategori")
    kategori = kr.json() if kr.status_code == 200 else []
    mr = await api_get(request, "/api/murid", per_page=200)
    murid = mr.json().get("items", []) if mr.status_code == 200 else []
    pelanggaran = []
    if data.get("kategori_id"):
        try:
            pr = await api_get(request, "/api/bk/pelanggaran",
                                kategori_id=int(data["kategori_id"]))
        except Exception:
            pr = type("R", (), {"status_code": 500})()
        if pr.status_code == 200:
            pelanggaran = pr.json()
    # Mapel options: untuk admin semua mapel; untuk guru cuma yang dia ampu.
    is_admin = user.get("role") in ("admin", "super_admin")
    mapel_options = []
    if is_admin:
        mpr = await api_get(request, "/api/mapel")
        for mp in (mpr.json() if mpr.status_code == 200 else []):
            mapel_options.append({"id": mp["id"], "nama": mp["nama"]})
    else:
        # Guru: cuma mapel yang dia ampu di TA aktif
        pr = await api_get(request, f"/api/guru-pengampu/guru/{user.get('id')}")
        if pr.status_code == 200:
            seen = set()
            for p in pr.json():
                if p.get("mapel_id") and p["mapel_id"] not in seen:
                    seen.add(p["mapel_id"])
                    mapel_options.append({
                        "id": p["mapel_id"],
                        "nama": p.get("mapel_nama") or f"Mapel {p['mapel_id']}",
                    })
    catatan = dict(data) if not edit_id else {"id": edit_id, **data}
    return {
        "user": user, "kategori": kategori, "murid": murid,
        "pelanggaran": pelanggaran, "catatan": catatan, "err": err,
        "mapel_options": mapel_options, "is_admin": is_admin,
    }


@router.get("/catatan")
async def catatan_list(request: Request,
                       user: dict = Depends(require_login_web),
                       murid_id: int | None = None,
                       kategori_id: int | None = None,
                       dari: str | None = None,
                       sampai: str | None = None):
    """List catatan BK (filterable)."""
    r = await api_get(request, "/api/bk/catatan",
                       per_page=200,
                       murid_id=murid_id or 0,
                       kategori_id=kategori_id or 0,
                       dari=dari or "",
                       sampai=sampai or "")
    rows = r.json() if r.status_code == 200 else []
    kr = await api_get(request, "/api/bk/kategori")
    kategori = kr.json() if kr.status_code == 200 else []
    return templates.TemplateResponse(
        request, "bk/catatan_list.html",
        {"user": user, "rows": rows, "kategori": kategori,
         "filter_kategori_id": kategori_id,
         "filter_dari": dari, "filter_sampai": sampai,
         "err": None})


@router.get("/catatan/new")
async def catatan_new(request: Request,
                      user: dict = Depends(require_login_web),
                      murid_id: int | None = None):
    """Form catatan baru."""
    ctx = await _catatan_form_context(
        request, user,
        {"preselected_murid_id": murid_id} if murid_id else {})
    return templates.TemplateResponse(request, "bk/catatan_form.html", ctx)


@router.post("/catatan/new")
async def catatan_create(request: Request,
                         user: dict = Depends(require_login_web)):
    """Submit form catatan baru."""
    form = await request.form()
    murid_ids_raw = form.getlist("murid_ids")
    murid_ids = [int(m) for m in murid_ids_raw if m.isdigit()]
    payload = {
        "murid_ids": murid_ids,
        "kategori_id": int(form.get("kategori_id") or 0),
        "judul": (form.get("judul") or "").strip(),
        "isi": (form.get("isi") or "").strip(),
        "tingkat": form.get("tingkat") or None,
    }
    # Mapel insiden (optional untuk admin, required untuk guru — divalidasi di backend)
    if form.get("mapel_id"):
        payload["mapel_id"] = int(form.get("mapel_id"))
    if not payload["murid_ids"] or not payload["kategori_id"] or not payload["judul"]:
        ctx = await _catatan_form_context(
            request, user, payload,
            err="Minimal 1 murid, kategori, dan judul wajib diisi")
        return templates.TemplateResponse(
            request, "bk/catatan_form.html", ctx, status_code=400)
    if form.get("pelanggaran_id"):
        payload["pelanggaran_id"] = int(form.get("pelanggaran_id"))
    if form.get("tanggal"):
        payload["tanggal"] = form.get("tanggal")
    r = await api_post(request, "/api/bk/catatan", payload)
    if r.status_code in (200, 201):
        return RedirectResponse(
            "/madrasah-app/bk/catatan", status_code=303)
    ctx = await _catatan_form_context(
        request, user, payload, err=(r.json().get("detail") or "Gagal"))
    return templates.TemplateResponse(
        request, "bk/catatan_form.html", ctx, status_code=400)


@router.get("/catatan/{id}/edit")
async def catatan_edit(request: Request, id: int,
                      user: dict = Depends(require_login_web)):
    """Form edit catatan."""
    rows_r = await api_get(request, "/api/bk/catatan", per_page=500)
    rows = rows_r.json() if rows_r.status_code == 200 else []
    catatan = next((r for r in rows if r["id"] == id), None)
    if not catatan:
        return templates.TemplateResponse(
            request, "error.html",
            {"user": user, "status_code": 404, "message": "Catatan tidak ditemukan"},
            status_code=404)
    ctx = await _catatan_form_context(request, user, catatan, edit_id=id)
    return templates.TemplateResponse(request, "bk/catatan_form.html", ctx)


@router.post("/catatan/{id}/edit")
async def catatan_update(request: Request, id: int,
                         user: dict = Depends(require_login_web)):
    """Submit form edit."""
    form = await request.form()
    payload = {
        "judul": (form.get("judul") or "").strip(),
        "isi": (form.get("isi") or "").strip(),
        "tingkat": form.get("tingkat") or None,
    }
    if form.get("tanggal"):
        payload["tanggal"] = form.get("tanggal")
    if form.get("pelanggaran_id"):
        payload["pelanggaran_id"] = int(form.get("pelanggaran_id"))
    r = await api_patch(request, f"/api/bk/catatan/{id}", payload)
    if r.status_code == 200:
        return RedirectResponse(
            "/madrasah-app/bk/catatan", status_code=303)
    ctx = await _catatan_form_context(
        request, user, payload, err=(r.json().get("detail") or "Gagal"),
        edit_id=id)
    return templates.TemplateResponse(
        request, "bk/catatan_form.html", ctx, status_code=400)


@router.post("/catatan/{id}/delete")
async def catatan_delete(request: Request, id: int,
                         user: dict = Depends(require_login_web)):
    """Hapus catatan."""
    await api_delete(request, f"/api/bk/catatan/{id}")
    return RedirectResponse(
        "/madrasah-app/bk/catatan", status_code=303)


# ── Sesi ──────────────────────────────────────────────────────────────────

async def _sesi_form_context(request, user, data, err=None, edit_id=None):
    mr = await api_get(request, "/api/murid", per_page=200)
    murid = mr.json().get("items", []) if mr.status_code == 200 else []
    sesi = dict(data) if not edit_id else {"id": edit_id, **data}
    return {"user": user, "murid": murid, "sesi": sesi, "err": err}


@router.get("/sesi")
async def sesi_list(request: Request,
                    user: dict = Depends(require_login_web),
                    dari: str | None = None,
                    sampai: str | None = None):
    r = await api_get(request, "/api/bk/sesi", dari=dari or "", sampai=sampai or "")
    rows = r.json() if r.status_code == 200 else []
    return templates.TemplateResponse(
        request, "bk/sesi_list.html",
        {"user": user, "rows": rows,
         "filter_dari": dari, "filter_sampai": sampai,
         "err": None})


@router.get("/sesi/new")
async def sesi_new(request: Request,
                   user: dict = Depends(require_login_web),
                   murid_id: int | None = None):
    ctx = await _sesi_form_context(
        request, user,
        {"preselected_murid_id": murid_id} if murid_id else {})
    return templates.TemplateResponse(request, "bk/sesi_form.html", ctx)


@router.post("/sesi/new")
async def sesi_create(request: Request,
                      user: dict = Depends(require_login_web)):
    form = await request.form()
    peserta_ids_raw = form.getlist("peserta_ids")
    peserta_ids = [int(m) for m in peserta_ids_raw if m.isdigit()]
    payload = {
        "peserta_ids": peserta_ids,
        "topik": (form.get("topik") or "").strip(),
        "tempat": (form.get("tempat") or "Ruang BK").strip(),
        "hasil": (form.get("hasil") or "").strip(),
        "tindak_lanjut": (form.get("tindak_lanjut") or "").strip(),
    }
    if not payload["topik"]:
        ctx = await _sesi_form_context(
            request, user, payload, err="Topik wajib diisi")
        return templates.TemplateResponse(
            request, "bk/sesi_form.html", ctx, status_code=400)
    if form.get("murid_id"):
        payload["murid_id"] = int(form.get("murid_id"))
    if form.get("tanggal"):
        payload["tanggal"] = form.get("tanggal")
    if form.get("berikutnya_tanggal"):
        payload["berikutnya_tanggal"] = form.get("berikutnya_tanggal")
    r = await api_post(request, "/api/bk/sesi", payload)
    if r.status_code in (200, 201):
        return RedirectResponse(
            "/madrasah-app/bk/sesi", status_code=303)
    ctx = await _sesi_form_context(
        request, user, payload, err=(r.json().get("detail") or "Gagal"))
    return templates.TemplateResponse(
        request, "bk/sesi_form.html", ctx, status_code=400)


@router.get("/sesi/{id}/edit")
async def sesi_edit(request: Request, id: int,
                   user: dict = Depends(require_login_web)):
    rows_r = await api_get(request, "/api/bk/sesi")
    rows = rows_r.json() if rows_r.status_code == 200 else []
    sesi = next((r for r in rows if r["id"] == id), None)
    if not sesi:
        return templates.TemplateResponse(
            request, "error.html",
            {"user": user, "status_code": 404, "message": "Sesi tidak ditemukan"},
            status_code=404)
    ctx = await _sesi_form_context(request, user, sesi, edit_id=id)
    return templates.TemplateResponse(request, "bk/sesi_form.html", ctx)


@router.post("/sesi/{id}/edit")
async def sesi_update(request: Request, id: int,
                      user: dict = Depends(require_login_web)):
    form = await request.form()
    peserta_ids_raw = form.getlist("peserta_ids")
    peserta_ids = [int(m) for m in peserta_ids_raw if m.isdigit()]
    payload = {
        "peserta_ids": peserta_ids,
        "topik": (form.get("topik") or "").strip(),
        "tempat": (form.get("tempat") or "Ruang BK").strip(),
        "hasil": (form.get("hasil") or "").strip(),
        "tindak_lanjut": (form.get("tindak_lanjut") or "").strip(),
    }
    if form.get("tanggal"):
        payload["tanggal"] = form.get("tanggal")
    if form.get("berikutnya_tanggal"):
        payload["berikutnya_tanggal"] = form.get("berikutnya_tanggal")
    if form.get("murid_id"):
        payload["murid_id"] = int(form.get("murid_id"))
    r = await api_patch(request, f"/api/bk/sesi/{id}", payload)
    if r.status_code == 200:
        return RedirectResponse(
            "/madrasah-app/bk/sesi", status_code=303)
    ctx = await _sesi_form_context(
        request, user, payload, err=(r.json().get("detail") or "Gagal"),
        edit_id=id)
    return templates.TemplateResponse(
        request, "bk/sesi_form.html", ctx, status_code=400)


@router.post("/sesi/{id}/delete")
async def sesi_delete(request: Request, id: int,
                      user: dict = Depends(require_login_web)):
    await api_delete(request, f"/api/bk/sesi/{id}")
    return RedirectResponse(
        "/madrasah-app/bk/sesi", status_code=303)


# ── Rekap poin (leaderboard) ─────────────────────────────────────────────

@router.get("/rekap")
async def rekap_poin(request: Request,
                     user: dict = Depends(require_login_web),
                     kelas_id: int | None = None,
                     dari: str | None = None,
                     sampai: str | None = None):
    r = await api_get(request, "/api/bk/rekap-poin",
                       per_page=200,
                       kelas_id=kelas_id or 0,
                       dari=dari or "",
                       sampai=sampai or "")
    rows = r.json() if r.status_code == 200 else []
    klr = await api_get(request, "/api/kelas")
    kelas = klr.json() if klr.status_code == 200 else []
    return templates.TemplateResponse(
        request, "bk/rekap.html",
        {"user": user, "rows": rows, "kelas": kelas,
         "filter_kelas_id": kelas_id,
         "filter_dari": dari, "filter_sampai": sampai,
         "err": None})


# ── Monitor per murid ────────────────────────────────────────────────────

@router.get("/monitor/{murid_id}")
async def monitor_murid(request: Request, murid_id: int,
                        user: dict = Depends(require_login_web),
                        dari: str | None = None,
                        sampai: str | None = None):
    r = await api_get(request, f"/api/bk/monitor/{murid_id}",
                       dari=dari or "", sampai=sampai or "")
    if r.status_code != 200:
        return templates.TemplateResponse(
            request, "error.html",
            {"user": user, "status_code": r.status_code,
             "message": (r.json().get("detail") or "Gagal")},
            status_code=r.status_code)
    data = r.json()
    return templates.TemplateResponse(
        request, "bk/monitor.html",
        {"user": user, "data": data,
         "filter_dari": dari, "filter_sampai": sampai,
         "err": None})


# ── Master (kategori & pelanggaran) ─────────────────────────────────────

@router.get("/master")
async def master(request: Request,
                 user: dict = Depends(require_permission_web("bk.master", "bk.view", "bk.catatan", "bk.sesi", "bk.export", "bk.monitor"))):
    """Halaman master: list kategori + list pelanggaran per kategori."""
    kr = await api_get(request, "/api/bk/kategori")
    kategori = kr.json() if kr.status_code == 200 else []
    pr = await api_get(request, "/api/bk/pelanggaran")
    all_pel = pr.json() if pr.status_code == 200 else []
    by_kat: dict[int, list] = {}
    for p in all_pel:
        by_kat.setdefault(p["kategori_id"], []).append(p)
    return templates.TemplateResponse(
        request, "bk/master.html",
        {"user": user, "kategori": kategori, "by_kat": by_kat,
         "err": None})


@router.post("/kategori/new")
async def master_kategori_new(request: Request,
                              user: dict = Depends(require_permission_web("bk.master", "bk.view", "bk.catatan", "bk.sesi", "bk.export", "bk.monitor"))):
    form = await request.form()
    poin_raw = form.get("poin") or ""
    poin = int(poin_raw) if poin_raw.isdigit() else None
    await api_post(request, "/api/bk/kategori",
                   {"nama": form.get("nama", "").strip(),
                    "jenis": form.get("jenis", "netral"),
                    "warna": form.get("warna", "zinc"),
                    "poin": poin,
                    "urutan": int(form.get("urutan") or 0)})
    return RedirectResponse(
        "/madrasah-app/bk/master", status_code=303)


@router.post("/kategori/{id}/delete")
async def master_kategori_delete(request: Request, id: int,
                                 user: dict = Depends(require_permission_web("bk.master", "bk.view", "bk.catatan", "bk.sesi", "bk.export", "bk.monitor"))):
    await api_delete(request, f"/api/bk/kategori/{id}")
    return RedirectResponse(
        "/madrasah-app/bk/master", status_code=303)


@router.post("/kategori/{id}/edit")
async def master_kategori_edit(request: Request, id: int,
                               user: dict = Depends(require_permission_web("bk.master", "bk.view", "bk.catatan", "bk.sesi", "bk.export", "bk.monitor"))):
    form = await request.form()
    payload = {"nama": form.get("nama", "").strip()}
    if form.get("jenis"):
        payload["jenis"] = form.get("jenis")
        # Warna otomatis mengikuti jenis (kalau user tidak set manual)
        payload["warna"] = {"negatif": "red", "positif": "green", "netral": "blue"}.get(form.get("jenis"), "zinc")
    elif form.get("warna"):
        payload["warna"] = form.get("warna")
    await api_patch(request, f"/api/bk/kategori/{id}", payload)
    return RedirectResponse(
        "/madrasah-app/bk/master", status_code=303)


@router.post("/pelanggaran/new")
async def master_pelanggaran_new(request: Request,
                                 user: dict = Depends(require_permission_web("bk.master", "bk.view", "bk.catatan", "bk.sesi", "bk.export", "bk.monitor"))):
    form = await request.form()
    kat = int(form.get("kategori_id") or 0)
    # API butuh kategori_id sebagai query param (bukan di body JSON)
    await api_post(request, "/api/bk/pelanggaran",
                   {"nama": form.get("nama", "").strip(),
                    "poin": int(form.get("poin") or 0),
                    "tingkat": form.get("tingkat") or None,
                    "urutan": int(form.get("urutan") or 0)},
                   kategori_id=kat)
    return RedirectResponse(
        "/madrasah-app/bk/master", status_code=303)


@router.post("/pelanggaran/{id}/delete")
async def master_pelanggaran_delete(request: Request, id: int,
                                    user: dict = Depends(require_permission_web("bk.master", "bk.view", "bk.catatan", "bk.sesi", "bk.export", "bk.monitor"))):
    await api_delete(request, f"/api/bk/pelanggaran/{id}")
    return RedirectResponse(
        "/madrasah-app/bk/master", status_code=303)


@router.post("/pelanggaran/{id}/edit")
async def master_pelanggaran_edit(request: Request, id: int,
                                  user: dict = Depends(require_permission_web("bk.master", "bk.view", "bk.catatan", "bk.sesi", "bk.export", "bk.monitor"))):
    form = await request.form()
    payload = {"nama": form.get("nama", "").strip()}
    if form.get("poin") is not None and form.get("poin") != "":
        payload["poin"] = int(form.get("poin"))
    if form.get("tingkat"):
        payload["tingkat"] = form.get("tingkat")
    await api_patch(request, f"/api/bk/pelanggaran/{id}", payload)
    return RedirectResponse(
        "/madrasah-app/bk/master", status_code=303)


# ── Konfigurasi ──────────────────────────────────────────────────────────

@router.get("/konfigurasi")
async def konfigurasi_get(request: Request,
                          user: dict = Depends(require_permission_web("bk.view"))):
    r = await api_get(request, "/api/bk/konfigurasi")
    data = r.json() if r.status_code == 200 else {}
    return templates.TemplateResponse(
        request, "bk/konfigurasi.html",
        {"user": user, "data": data, "err": None})


@router.post("/konfigurasi")
async def konfigurasi_post(request: Request,
                           user: dict = Depends(require_permission_web("bk.master", "bk.view", "bk.catatan", "bk.sesi", "bk.export", "bk.monitor"))):
    form = await request.form()
    payload = {}
    for k in ("threshold_sp1", "threshold_sp2", "threshold_sp3"):
        v = form.get(k)
        if v and v.isdigit():
            payload[k] = int(v)
    if form.get("periode_reset"):
        payload["periode_reset"] = form.get("periode_reset")
    if form.get("catatan"):
        payload["catatan"] = form.get("catatan")
    await api_put(request, "/api/bk/konfigurasi", payload)
    return RedirectResponse(
        "/madrasah-app/bk/konfigurasi?ok=1", status_code=303)
