#!/usr/bin/env python3
"""Tes Detail Absensi & Murid — rincian per murid, rekap ortu publik, pdf, rekap
bulan/kelas/top-alpha, riwayat, qr.pdf, lulus — tanpa pytest.

Jalanake: ./venv/bin/python test_api_absensi_detail.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"apiabd{int(time.time()) % 100000}"


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

    # ── Setup tenant + admin + guru ──
    st, r = req("POST", "/api/auth/login-super",
                {"username": "superadmin", "password": "super123456"})
    check("login super", st == 200, str(r))
    SUPER = r["access_token"]

    st, r = req("POST", "/api/super/tenants",
                {"kode": KODE, "nama": "MTs Tes Abs Detail", "plan": "free"},
                token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin Abs", "username": "admdet",
                 "password": "admdet123"}, token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admdet",
                 "password": "admdet123"})
    check("login admin tenant", st == 200, str(r))
    T = r["access_token"]

    # ── Kelas + murid ──
    st, r = req("GET", "/api/tahun-ajaran", token=T)
    TA = r[0]["id"]
    st, r = req("POST", "/api/kelas", {"nama_kelas": "7A", "tahun_ajaran_id": TA},
                token=T)
    check("buat kelas 7A", st == 201, str(r))
    k7 = r["id"]
    st, r = req("POST", "/api/murid",
                {"nisn": "2400000001", "nama": "Siswa Detail",
                 "kelas_id": k7, "nama_ortu": "Bpk Ortu",
                 "telepon": "6281234567801"}, token=T)
    check("buat murid", st == 201, str(r))
    m1 = r["id"]
    # murid lulus (non-aktif) di kelas lain
    st, r = req("POST", "/api/kelas", {"nama_kelas": "8A", "tahun_ajaran_id": TA},
                token=T)
    k8 = r["id"]
    st, r = req("POST", "/api/murid", {"nisn": "2400000002", "nama": "Siswa Lulus",
                                       "kelas_id": k8}, token=T)
    m2 = r["id"]

    # ── Input absen ──
    TGL = "2026-07-28"
    st, r = req("POST", f"/api/absensi/kelas/{k7}", {
        "tanggal": TGL,
        "entries": [{"murid_id": m1, "status": "hadir"},
                    {"murid_id": m1, "status": "sakit"}],
    }, token=T)
    check("input absen", st == 200, str(r))

    # ── Rincian murid ──
    st, r = req("GET", f"/api/absensi/murid/{m1}/rincian", token=T)
    check("rincian murid", st == 200 and "murid" in r and "rows" in r, str(r)[:120])

    # ── Ortu rekap (public — butuh kode, nisn, nama_ortu) ──
    from urllib.parse import quote
    st, r = req("GET", f"/api/absensi/ortu/rekap?kode={KODE}&nisn=2400000001"
                f"&nama_ortu={quote('Bpk Ortu')}&bulan=2026-07")
    check("ortu rekap", st == 200 and "murid" in r, str(r)[:120])
    # nisn salah → 404
    st, r = req("GET", f"/api/absensi/ortu/rekap?kode={KODE}&nisn=000&nama_ortu=X")
    check("ortu rekap nisn salah → 404", st == 404, str(r))
    # nama ortu salah → 401
    st, r = req("GET", f"/api/absensi/ortu/rekap?kode={KODE}&nisn=2400000001"
                f"&nama_ortu={quote('Salah')}")
    check("ortu rekap nama ortu salah → 401", st == 401, str(r))

    # ── PDF per murid ──
    st, r = req("GET", f"/api/absensi/pdf/{m1}", token=T, raw=True)
    check("absensi pdf murid", st == 200 and isinstance(r, bytes)
          and r[:4] == b"%PDF", f"st={st} head={r[:4] if isinstance(r, bytes) else r}")

    # ── Rekap bulan ini ──
    st, r = req("GET", "/api/absensi/rekap-bulan-ini", token=T)
    check("rekap-bulan-ini", st == 200 and "bulan" in r, str(r)[:120])

    # ── Rekap per kelas ──
    st, r = req("GET", "/api/absensi/rekap-per-kelas", token=T)
    check("rekap-per-kelas", st == 200 and "items" in r, str(r)[:120])

    # ── Top alpha ──
    st, r = req("GET", "/api/absensi/top-alpha", token=T)
    check("top-alpha", st == 200, str(r)[:120])

    # ── Riwayat murid ──
    st, r = req("GET", f"/api/murid/{m1}/riwayat", token=T)
    check("riwayat murid", st == 200 and "murid" in r, str(r)[:120])

    # ── QR PDF murid ──
    st, r = req("GET", f"/api/murid/{m1}/qr.pdf", token=T, raw=True)
    check("murid qr.pdf", st == 200 and isinstance(r, bytes) and r[:4] == b"%PDF",
          f"st={st} head={r[:4] if isinstance(r, bytes) else r}")

    # ── Murid lulus ──
    st, r = req("POST", f"/api/kelas/{k8}/luluskan", token=T)
    check("luluskan kelas 8A", st == 200 and r["lulus"] == 1, str(r))
    st, r = req("GET", "/api/murid/lulus?kelas_nama=8A", token=T)
    check("murid lulus", st == 200 and isinstance(r, list), str(r)[:120])
    st, r = req("GET", f"/api/murid/lulus?kelas_nama=8A&tahun_ajaran_id={TA}", token=T)
    check("murid lulus per ta", st == 200 and r["jumlah"] == 1, str(r)[:120])

    # ── Cleanup ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE}, token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
