#!/usr/bin/env python3
"""Tes BK lanjutan — dashboard, list pelanggaran, create pelanggaran — tanpa pytest.

Jalanake: ./venv/bin/python test_api_bk_lanjut.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"bklanjut{int(time.time()) % 100000}"


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
                {"kode": KODE, "nama": "MTs Tes BK Lanjut", "plan": "free"},
                token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin BKL", "username": "admbkl",
                 "password": "admbkl123"}, token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admbkl",
                 "password": "admbkl123"})
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
                {"nisn": "2400000001", "nama": "Siswa BKL", "kelas_id": k7},
                token=T)
    check("buat murid", st == 201, str(r))
    m1 = r["id"]

    # ── Kategori + pelanggaran ──
    st, r = req("POST", "/api/bk/kategori",
                {"nama": "Terlambat", "jenis": "negatif", "poin": 20, "urutan": 1},
                token=T)
    check("buat kategori", st == 201, str(r))
    kat = r["id"]

    st, r = req("POST", f"/api/bk/pelanggaran?kategori_id={kat}",
                {"nama": "Terlambat 15 menit", "poin": 30, "tingkat": "ringan"},
                token=T)
    check("buat pelanggaran", st == 201 and r["poin"] == 30, str(r))
    pel_id = r["id"]

    st, r = req("GET", f"/api/bk/pelanggaran?kategori_id={kat}", token=T)
    check("list pelanggaran", st == 200 and len(r) >= 1, str(r))
    st, r = req("GET", "/api/bk/pelanggaran", token=T)
    check("list pelanggaran (semua)", st == 200 and isinstance(r, list), str(r)[:120])

    # ── Dashboard ──
    st, r = req("GET", "/api/bk/dashboard", token=T)
    check("dashboard BK", st == 200 and "ringkasan" in r, str(r)[:120])
    check("dashboard punya top_pelanggaran",
          st == 200 and "top_pelanggaran" in r, str(r)[:120])

    # ── Cleanup ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE}, token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
