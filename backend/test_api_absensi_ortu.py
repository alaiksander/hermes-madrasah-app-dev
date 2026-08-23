#!/usr/bin/env python3
"""Tes Absensi Ortu — rekap publik (GET /api/absensi/ortu/rekap, tanpa login,
butuh query param kode=NISN+nama_ortu) — tanpa pytest.

Jalanake: ./venv/bin/python test_api_absensi_ortu.py
"""
import json
import time
import urllib.parse
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"absortu{int(time.time()) % 100000}"


def req(method, path, body=None, token=None, raw=False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
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
                {"kode": KODE, "nama": "MTs Tes Abs Ortu", "plan": "free"},
                token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin AbsOrtu", "username": "admabsortu",
                 "password": "admabsortu123"}, token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admabsortu",
                 "password": "admabsortu123"})
    check("login admin tenant", st == 200, str(r))
    T = r["access_token"]

    # ── Kelas + murid + absensi ──
    st, r = req("GET", "/api/tahun-ajaran", token=T)
    TA = r[0]["id"]
    st, r = req("POST", "/api/kelas", {"nama_kelas": "7A", "tahun_ajaran_id": TA},
                token=T)
    check("buat kelas 7A", st == 201, str(r))
    k7 = r["id"]
    NISN = "2400000001"
    ORTU = "Bpk Ahmad"
    st, r = req("POST", "/api/murid",
                {"nisn": NISN, "nama": "Siswa Ortu", "kelas_id": k7,
                 "nama_ortu": ORTU, "telepon": "6281234567801"}, token=T)
    check("buat murid", st == 201, str(r))
    m1 = r["id"]

    TGL = "2026-07-28"
    st, r = req("POST", f"/api/absensi/kelas/{k7}", {
        "tanggal": TGL,
        "entries": [{"murid_id": m1, "status": "hadir"}],
    }, token=T)
    check("input absen", st == 200, str(r))

    # ── Rekap ortu publik (tanpa token) ──
    q = f"kode={urllib.parse.quote(KODE)}&nisn={NISN}&nama_ortu={urllib.parse.quote(ORTU)}"
    st, r = req("GET", f"/api/absensi/ortu/rekap?{q}")
    check("ortu/rekap valid", st == 200 and r["murid"]["nisn"] == NISN
          and "rows" in r, str(r)[:160])

    # ── Validasi: nama ortu salah → 401 ──
    q = f"kode={urllib.parse.quote(KODE)}&nisn={NISN}&nama_ortu=OrangLain"
    st, r = req("GET", f"/api/absensi/ortu/rekap?{q}")
    check("ortu/rekap nama ortu salah → 401", st == 401, str(r)[:120])

    # ── Validasi: nisn tidak ada → 404 ──
    q = f"kode={urllib.parse.quote(KODE)}&nisn=999999&nama_ortu={urllib.parse.quote(ORTU)}"
    st, r = req("GET", f"/api/absensi/ortu/rekap?{q}")
    check("ortu/rekap nisn tidak ada → 404", st == 404, str(r)[:120])

    # ── Validasi: bulan salah format → 400 ──
    q = f"kode={urllib.parse.quote(KODE)}&nisn={NISN}&nama_ortu={urllib.parse.quote(ORTU)}&bulan=2026-13"
    st, r = req("GET", f"/api/absensi/ortu/rekap?{q}")
    check("ortu/rekap bulan invalid → 400", st == 400, str(r)[:120])

    # ── Cleanup ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE}, token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
