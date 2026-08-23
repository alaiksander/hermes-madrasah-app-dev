#!/usr/bin/env python3
"""Tes Export/Cetak lanjutan — absensi cetak-pdf/cetak.json/cetak.xlsx,
export.csv/export.xlsx, murid qr-pdf/lulus, nilai export-rdm/rekap,
tagihan export.xlsx/rekap-kelas — tanpa pytest.

Jalanake: ./venv/bin/python test_api_export_lanjut.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"apiexpl{int(time.time()) % 100000}"


def req(method, path, body=None, token=None, raw=False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            content = resp.read()
            if raw:
                return resp.status, content
            if not content:
                return resp.status, None
            return resp.status, json.loads(content)
    except urllib.error.HTTPError as e:
        content = e.read()
        try:
            return e.code, json.loads(content)
        except Exception:
            return e.code, content


def main():
    ok = fail = 0

    def check(name, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  OK  {name}")
        else:
            fail += 1
            print(f"  FAIL {name} — {detail}")

    # ── Setup tenant + admin ──
    st, r = req("POST", "/api/auth/login-super",
                {"username": "superadmin", "password": "super123456"})
    check("login super", st == 200, str(r))
    SUPER = r["access_token"]

    st, r = req("POST", "/api/super/tenants",
                {"kode": KODE, "nama": "MTs Tes Export Lanjut", "plan": "free"},
                token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin ExpL", "username": "admexpl",
                 "password": "admexpl123"}, token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admexpl",
                 "password": "admexpl123"})
    check("login admin tenant", st == 200, str(r))
    T = r["access_token"]

    # ── Data dasar: TA, kelas, mapel, guru, murid ──
    st, r = req("GET", "/api/tahun-ajaran", token=T)
    TA = r[0]["id"]
    st, r = req("POST", "/api/kelas", {"nama_kelas": "7A", "tahun_ajaran_id": TA},
                token=T)
    check("buat kelas 7A", st == 201, str(r))
    k7 = r["id"]
    st, r = req("POST", "/api/mapel", {"nama": "Matematika", "kode": "MTK"},
                token=T)
    check("buat mapel", st == 201, str(r))
    mapel_id = r["id"]
    st, r = req("POST", "/api/guru",
                {"nama": "Guru ExpL", "username": "guruexpl",
                 "password": "guruexpl123", "role": "guru"}, token=T)
    check("buat guru", st == 201, str(r))
    murid_ids = []
    for i in range(2):
        st, r = req("POST", "/api/murid",
                    {"nisn": f"24000000{i+1:02d}", "nama": f"Siswa ExpL {i+1}",
                     "kelas_id": k7, "nama_ortu": "Bpk Ortu",
                     "telepon": "6281234567801"}, token=T)
        check(f"buat murid {i+1}", st == 201, str(r))
        murid_ids.append(r["id"])

    # ── Absensi ──
    TGL = "2026-07-28"
    st, r = req("POST", f"/api/absensi/kelas/{k7}", {
        "tanggal": TGL,
        "entries": [{"murid_id": murid_ids[0], "status": "hadir"},
                    {"murid_id": murid_ids[1], "status": "sakit"}],
    }, token=T)
    check("input absen", st == 200, str(r))

    # ── Absensi cetak-pdf / cetak.json / cetak.xlsx ──
    st, r = req("GET", f"/api/absensi/cetak-pdf.pdf?kelas_id={k7}", token=T, raw=True)
    check("absensi cetak-pdf.pdf", st == 200 and isinstance(r, bytes)
          and r[:4] == b"%PDF", f"st={st} head={r[:4] if isinstance(r, bytes) else r}")
    st, r = req("GET", f"/api/absensi/cetak.json?kelas_id={k7}", token=T)
    check("absensi cetak.json", st == 200 and "rows" in r, str(r)[:120])
    st, r = req("GET", f"/api/absensi/cetak.xlsx?kelas_id={k7}", token=T, raw=True)
    check("absensi cetak.xlsx", st == 200 and isinstance(r, bytes) and len(r) > 100,
          f"st={st} len={len(r) if isinstance(r, bytes) else r}")

    # ── Absensi export.csv / export.xlsx ──
    st, r = req("GET", f"/api/absensi/export.csv?tanggal={TGL}", token=T, raw=True)
    check("absensi export.csv", st == 200 and isinstance(r, bytes) and len(r) > 0,
          f"st={st} len={len(r) if isinstance(r, bytes) else r}")
    st, r = req("GET", f"/api/absensi/export.xlsx?tanggal={TGL}", token=T, raw=True)
    check("absensi export.xlsx", st == 200 and isinstance(r, bytes) and len(r) > 100,
          f"st={st} len={len(r) if isinstance(r, bytes) else r}")

    # ── Murid qr-pdf ──
    st, r = req("GET", f"/api/murid/qr-pdf.pdf?kelas_id={k7}", token=T, raw=True)
    check("murid qr-pdf.pdf", st == 200 and isinstance(r, bytes) and r[:4] == b"%PDF",
          f"st={st} head={r[:4] if isinstance(r, bytes) else r}")

    # ── Nilai: materi + bulk + rekap + export-rdm ──
    st, r = req("POST", "/api/nilai/materi",
                {"mapel_id": mapel_id, "kelas_id": k7, "jenis": "tugas",
                 "nama": "Tugas 1", "kkpt": 70}, token=T)
    check("buat materi", st == 201, str(r))
    materi_id = r["id"]
    st, r = req("POST", "/api/nilai/bulk", {
        "materi_penilaian_id": materi_id,
        "entries": [{"murid_id": murid_ids[0], "skor": 85},
                    {"murid_id": murid_ids[1], "skor": 60}],
    }, token=T)
    check("input nilai bulk", st == 200 and r["disimpan"] == 2, str(r))
    st, r = req("GET", f"/api/nilai/rekap?kelas_id={k7}", token=T)
    check("nilai rekap", st == 200 and "murid" in r and len(r["murid"]) == 2,
          str(r)[:120])
    st, r = req("GET", f"/api/nilai/export-rdm?kelas_id={k7}", token=T, raw=True)
    check("nilai export-rdm", st == 200 and isinstance(r, bytes) and len(r) > 100,
          f"st={st} len={len(r) if isinstance(r, bytes) else r}")

    # ── Tagihan: jenis + generate + export.xlsx + rekap-kelas ──
    st, r = req("POST", "/api/tagihan/jenis",
                {"nama": "SPP", "nominal": 100000, "periode": "bulanan",
                 "jatuh_tempo": 10, "auto_generate": True, "boleh_cicil": True},
                token=T)
    check("buat jenis SPP", st == 201, str(r))
    st, r = req("POST", "/api/tagihan/generate?tingkat=7&periode=2026-08", token=T)
    check("generate tagihan", st == 200 and r["total_baru"] == 2, str(r))
    st, r = req("GET", "/api/tagihan/export.xlsx?periode=2026-08", token=T, raw=True)
    check("tagihan export.xlsx", st == 200 and isinstance(r, bytes) and len(r) > 100,
          f"st={st} len={len(r) if isinstance(r, bytes) else r}")
    st, r = req("GET", "/api/tagihan/rekap-kelas?periode=2026-08", token=T)
    check("tagihan rekap-kelas", st == 200 and isinstance(r, list) and len(r) >= 1,
          str(r)[:120])

    # ── Murid lulus (luluskan kelas dulu) ──
    st, r = req("POST", f"/api/kelas/{k7}/luluskan", token=T)
    check("luluskan kelas", st == 200 and r["lulus"] == 2, str(r))
    st, r = req("GET", f"/api/murid/lulus?kelas_nama=7A&tahun_ajaran_id={TA}", token=T)
    check("murid lulus", st == 200 and r.get("jumlah") == 2, str(r)[:120])
    st, r = req("GET", "/api/murid/lulus?kelas_nama=7A", token=T)
    check("murid lulus (tanpa TA)", st == 200 and isinstance(r, list), str(r)[:120])

    # ── Cleanup ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE}, token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
