"""Pembayaran / Tagihan — UI web (Jinja2 + HTMX).

Alur: /pembayaran (daftar tagihan per kelas/periode)
      /pembayaran/jenis (master jenis pembayaran + generate)
      /pembayaran/{tagihan_id} (detail + bayar + keringanan + tunda)
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from ....core.client import api_delete, api_get, api_get_raw, api_patch, api_post
from ....core.deps import require_login_web
from ....core.templates import templates

router = APIRouter(prefix="/pembayaran", tags=["pembayaran-web"])
BULAN_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


def _bulan_list() -> list[dict]:
    """12 bulan terakhir: [{value: 'YYYY-MM', label}]."""
    import datetime
    now = datetime.date.today()
    out = []
    for i in range(11, -1, -1):
        y, m = now.year, now.month - i
        while m <= 0:
            m += 12
            y -= 1
        out.append({"value": f"{y:04d}-{m:02d}",
                    "label": f"{BULAN_ID[m-1]} {y}"})
    return out


async def _kelas_ta_aktif(request: Request) -> list:
    """Kelas hanya tahun ajaran aktif."""
    ta_r = await api_get(request, "/api/tahun-ajaran")
    tahun_list = ta_r.json() if ta_r.status_code == 200 else []
    tahun_aktif = next((ta for ta in tahun_list if ta.get("is_active")), None)
    ta_id = tahun_aktif["id"] if tahun_aktif else None
    r = await api_get(request, "/api/kelas", tahun_ajaran_id=ta_id or "")
    return r.json() if r.status_code == 200 else []


# ── Dashboard tagihan ────────────────────────────────────────────────────

@router.get("")
async def pembayaran_dashboard(request: Request,
                               kelas_id: int | None = None,
                               periode: str | None = None,
                               status: str | None = None,
                               user: dict = Depends(require_login_web)):
    """Daftar tagihan (filter kelas/periode/status)."""
    import datetime
    today = datetime.date.today()
    periode = periode or f"{today.year:04d}-{today.month:02d}"

    params = [f"periode={periode}"]
    if kelas_id:
        params.append(f"kelas_id={kelas_id}")
    if status:
        params.append(f"status={status}")
    r = await api_get(request, f"/api/tagihan?{'&'.join(params)}")
    tagihan = r.json() if r.status_code == 200 else []
    r_rk = await api_get(request,
                         f"/api/tagihan/rekap-kelas?periode={periode}"
                         + (f"&kelas_id={kelas_id}" if kelas_id else ""))
    rekap = r_rk.json() if r_rk.status_code == 200 else []
    kelas_list = await _kelas_ta_aktif(request)

    return templates.TemplateResponse(
        "pembayaran/dashboard.html",
        {"request": request, "user": user,
         "tagihan": tagihan, "rekap": rekap,
         "kelas_list": kelas_list, "bulan_list": _bulan_list(),
         "filter_kelas_id": kelas_id, "filter_periode": periode,
         "filter_status": status},
    )


# ── Master jenis pembayaran ───────────────────────────────────────────────

@router.get("/jenis")
async def jenis_list(request: Request,
                     user: dict = Depends(require_login_web)):
    """Master jenis pembayaran + tombol generate."""
    r = await api_get(request, "/api/tagihan/jenis")
    jenis = r.json() if r.status_code == 200 else []
    return templates.TemplateResponse(
        "pembayaran/jenis.html",
        {"request": request, "user": user, "jenis": jenis,
         "bulan_list": _bulan_list()},
    )


@router.post("/jenis")
async def jenis_create(request: Request,
                       user: dict = Depends(require_login_web)):
    """Buat jenis pembayaran."""
    form = await request.form()
    body = {
        "nama": form.get("nama", "").strip(),
        "deskripsi": form.get("deskripsi", "").strip(),
        "nominal": int(form.get("nominal", 0) or 0),
        "periode": form.get("periode", "bulanan"),
        "jatuh_tempo": int(form.get("jatuh_tempo", 10) or 10),
        "auto_generate": form.get("auto_generate") == "on",
        "boleh_cicil": form.get("boleh_cicil") == "on",
    }
    r = await api_post(request, "/api/tagihan/jenis", body)
    if r.status_code in (200, 201):
        return RedirectResponse("/madrasah-app/pembayaran/jenis?ok=1",
                                status_code=303)
    return RedirectResponse("/madrasah-app/pembayaran/jenis?err=1",
                            status_code=303)


@router.post("/jenis/{jenis_id}/toggle")
async def jenis_toggle(request: Request, jenis_id: int,
                       user: dict = Depends(require_login_web)):
    """Aktif/nonaktifkan jenis."""
    await api_post(request, f"/api/tagihan/jenis/{jenis_id}/toggle", None)
    return RedirectResponse("/madrasah-app/pembayaran/jenis", status_code=303)


@router.post("/generate")
async def generate(request: Request,
                   user: dict = Depends(require_login_web)):
    """Generate tagihan bulanan untuk periode tertentu."""
    form = await request.form()
    periode = form.get("periode", "")
    jenis_id = form.get("jenis_id") or None
    url = f"/api/tagihan/generate?periode={periode}"
    if jenis_id:
        url += f"&jenis_id={jenis_id}"
    r = await api_post(request, url, None)
    if r.status_code == 200:
        d = r.json()
        msg = f"Generate OK: {d.get('total_baru', 0)} tagihan baru "
        msg += "· ".join(d.get("rincian", []))
        return RedirectResponse(f"/madrasah-app/pembayaran/jenis?ok={msg}",
                                status_code=303)
    return RedirectResponse("/madrasah-app/pembayaran/jenis?err=1",
                            status_code=303)


# ── Input Cepat (bulk) ────────────────────────────────────────────────────

@router.get("/input-cepat")
async def input_cepat_page(request: Request,
                           kelas_id: int | None = None,
                           periode: str | None = None,
                           status: str | None = None,
                           user: dict = Depends(require_login_web)):
    """Input cepat: tabel murid per kelas, isi nominal langsung per baris."""
    import datetime
    today = datetime.date.today()
    periode = periode or f"{today.year:04d}-{today.month:02d}"

    params = [f"periode={periode}"]
    if kelas_id:
        params.append(f"kelas_id={kelas_id}")
    if status:
        params.append(f"status={status}")
    r = await api_get(request, f"/api/tagihan?{'&'.join(params)}")
    tagihan = r.json() if r.status_code == 200 else []
    jenis_r = await api_get(request, "/api/tagihan/jenis")
    jenis = jenis_r.json() if jenis_r.status_code == 200 else []
    kelas_list = await _kelas_ta_aktif(request)

    return templates.TemplateResponse(
        "pembayaran/input_cepat.html",
        {"request": request, "user": user,
         "tagihan": tagihan, "jenis": jenis,
         "kelas_list": kelas_list, "bulan_list": _bulan_list(),
         "filter_kelas_id": kelas_id, "filter_periode": periode,
         "filter_status": status},
    )


@router.post("/input-cepat/simpan")
async def input_cepat_simpan(request: Request,
                             user: dict = Depends(require_login_web)):
    """Simpan pembayaran massal (bulk) — body JSON dari JS."""
    import json
    body = await request.body()
    try:
        entries = json.loads(body or b"[]")
    except json.JSONDecodeError:
        entries = []
    r = await api_post(request, "/api/tagihan/bulk-bayar", entries, raw_json=True)
    if r.status_code == 200:
        d = r.json()
        return RedirectResponse(
            f"/madrasah-app/pembayaran/input-cepat?ok={d.get('ok', 0)}"
            + (f"&gagal={len(d.get('gagal', []))}" if d.get("gagal") else ""),
            status_code=303)
    return RedirectResponse("/madrasah-app/pembayaran/input-cepat?err=1",
                            status_code=303)


# ── Laporan + Export Excel ────────────────────────────────────────────────

@router.get("/laporan")
async def laporan_page(request: Request,
                       kelas_id: int | None = None,
                       periode: str | None = None,
                       status: str | None = None,
                       user: dict = Depends(require_login_web)):
    """Laporan rekap tagihan + tombol export Excel."""
    import datetime
    today = datetime.date.today()
    periode = periode or f"{today.year:04d}-{today.month:02d}"

    params = [f"periode={periode}"]
    if kelas_id:
        params.append(f"kelas_id={kelas_id}")
    if status:
        params.append(f"status={status}")
    r = await api_get(request, f"/api/tagihan?{'&'.join(params)}")
    tagihan = r.json() if r.status_code == 200 else []
    r_rk = await api_get(request, f"/api/tagihan/rekap-kelas?periode={periode}"
                         + (f"&kelas_id={kelas_id}" if kelas_id else ""))
    rekap = r_rk.json() if r_rk.status_code == 200 else []

    # Ringkasan total
    total_nominal = sum(t["nominal"] for t in tagihan)
    total_terbayar = sum(t["dibayar"] for t in tagihan)
    total_sisa = max(total_nominal - total_terbayar, 0)
    lunas = sum(1 for t in tagihan if t["status"] == "lunas")
    kelas_list = await _kelas_ta_aktif(request)

    return templates.TemplateResponse(
        "pembayaran/laporan.html",
        {"request": request, "user": user,
         "tagihan": tagihan, "rekap": rekap,
         "total_nominal": total_nominal, "total_terbayar": total_terbayar,
         "total_sisa": total_sisa, "total_lunas": lunas,
         "kelas_list": kelas_list, "bulan_list": _bulan_list(),
         "filter_kelas_id": kelas_id, "filter_periode": periode,
         "filter_status": status},
    )


@router.get("/laporan/export")
async def laporan_export(request: Request,
                         kelas_id: int | None = None,
                         periode: str | None = None,
                         status: str | None = None,
                         user: dict = Depends(require_login_web)):
    """Export rekap tagihan Excel (proxy ke API)."""
    from fastapi.responses import Response
    params = []
    if kelas_id:
        params.append(f"kelas_id={kelas_id}")
    if periode:
        params.append(f"periode={periode}")
    if status:
        params.append(f"status={status}")
    q = "&".join(params)
    url = f"/api/tagihan/export.xlsx?{q}" if q else "/api/tagihan/export.xlsx"
    content = await api_get_raw(request, url)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="rekap-tagihan.xlsx"'},
    )

# ── Detail tagihan: bayar / keringanan / tunda ───────────────────────────

@router.get("/{tagihan_id}")
async def tagihan_detail(request: Request, tagihan_id: int,
                         user: dict = Depends(require_login_web)):
    """Detail tagihan + riwayat pembayaran + aksi."""
    r = await api_get(request, f"/api/tagihan/{tagihan_id}")
    if r.status_code != 200:
        return RedirectResponse("/madrasah-app/pembayaran", status_code=303)
    t = r.json()
    return templates.TemplateResponse(
        "pembayaran/detail.html",
        {"request": request, "user": user, "t": t},
    )


@router.post("/{tagihan_id}/bayar")
async def tagihan_bayar(request: Request, tagihan_id: int,
                        user: dict = Depends(require_login_web)):
    """Input pembayaran (lunas/cicil)."""
    form = await request.form()
    body = {
        "nominal": int(form.get("nominal", 0) or 0),
        "metode": form.get("metode", "cash"),
        "catatan": form.get("catatan", "").strip(),
    }
    r = await api_post(request, f"/api/tagihan/{tagihan_id}/bayar", body)
    if r.status_code == 200:
        return RedirectResponse(f"/madrasah-app/pembayaran/{tagihan_id}?ok=1",
                                status_code=303)
    return RedirectResponse(
        f"/madrasah-app/pembayaran/{tagihan_id}?err=" + r.text[:80],
        status_code=303)


@router.post("/{tagihan_id}/keringanan")
async def tagihan_keringanan(request: Request, tagihan_id: int,
                             user: dict = Depends(require_login_web)):
    """Keringanan: potongan Rp."""
    form = await request.form()
    body = {
        "potongan": int(form.get("potongan", 0) or 0),
        "catatan": form.get("catatan", "").strip(),
    }
    r = await api_post(request, f"/api/tagihan/{tagihan_id}/keringanan", body)
    if r.status_code == 200:
        return RedirectResponse(f"/madrasah-app/pembayaran/{tagihan_id}?ok=1",
                                status_code=303)
    return RedirectResponse(
        f"/madrasah-app/pembayaran/{tagihan_id}?err=" + r.text[:80],
        status_code=303)


@router.post("/{tagihan_id}/tunda")
async def tagihan_tunda(request: Request, tagihan_id: int,
                        user: dict = Depends(require_login_web)):
    """Penundaan jatuh tempo."""
    form = await request.form()
    sampai = form.get("ditunda_sampai", "")
    if sampai:
        body = {"ditunda_sampai": f"{sampai}T00:00:00",
                "catatan": form.get("catatan", "").strip()}
        r = await api_post(request, f"/api/tagihan/{tagihan_id}/tunda", body)
        if r.status_code == 200:
            return RedirectResponse(f"/madrasah-app/pembayaran/{tagihan_id}?ok=1",
                                    status_code=303)
    return RedirectResponse(
        f"/madrasah-app/pembayaran/{tagihan_id}?err=tunda",
        status_code=303)


@router.post("/{tagihan_id}/hapus")
async def tagihan_hapus(request: Request, tagihan_id: int,
                        user: dict = Depends(require_login_web)):
    """Hapus tagihan (kasus salah generate)."""
    await api_delete(request, f"/api/tagihan/{tagihan_id}")
    return RedirectResponse("/madrasah-app/pembayaran", status_code=303)
