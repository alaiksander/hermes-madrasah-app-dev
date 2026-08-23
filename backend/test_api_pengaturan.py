#!/usr/bin/env python3
"""Tes Pengaturan — GET/PUT pengaturan, tahun-ajaran periode, health — tanpa pytest.

Jalanake: ./venv/bin/python test_api_pengaturan.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"apipeng{int(time.time()) % 100000}"


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

    # ── Health (public) ──
    st, r = req("GET", "/api/health")
    check("health", st == 200 and r["status"] == "ok", str(r))

    # ── Setup tenant + admin ──
    st, r = req("POST", "/api/auth/login-super",
                {"username": "superadmin", "password": "super123456"})
    check("login super", st == 200, str(r))
    SUPER = r["access_token"]

    st, r = req("POST", "/api/super/tenants",
                {"kode": KODE, "nama": "MTs Tes Pengaturan", "plan": "free"},
                token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin Peng", "username": "admpeng",
                 "password": "admpeng123"}, token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admpeng",
                 "password": "admpeng123"})
    check("login admin tenant", st == 200, str(r))
    T = r["access_token"]

    # ── Pengaturan GET ──
    st, r = req("GET", "/api/pengaturan", token=T)
    check("get pengaturan", st == 200 and "jam_masuk" in r, str(r)[:120])

    # ── Pengaturan PUT ──
    st, r = req("PUT", "/api/pengaturan",
                {"jam_masuk": "07:30", "jam_pulang": "14:00",
                 "hari_aktif": [1, 2, 3, 4, 5], "nama_aplikasi": "MTs Tes Peng"},
                token=T)
    check("put pengaturan", st == 200 and r["jam_masuk"] == "07:30", str(r)[:120])
    st, r = req("GET", "/api/pengaturan", token=T)
    check("get pengaturan updated", st == 200 and r["jam_masuk"] == "07:30",
          str(r)[:120])

    # ── Tahun ajaran periode ──
    st, r = req("GET", "/api/tahun-ajaran", token=T)
    TA = r[0]["id"]
    st, r = req("GET", f"/api/tahun-ajaran/{TA}/periode", token=T)
    check("get periode", st == 200 and isinstance(r, list), str(r)[:120])

    st, r = req("PUT", f"/api/tahun-ajaran/{TA}/periode", {
        "kode": "ganjil", "nama": "Semester Ganjil",
        "tanggal_mulai": "2025-07-01", "tanggal_selesai": "2025-12-31",
    }, token=T)
    check("put periode", st == 200 and r["kode"] == "ganjil", str(r)[:120])
    st, r = req("GET", f"/api/tahun-ajaran/{TA}/periode", token=T)
    check("get periode after put", st == 200 and len(r) == 1, str(r)[:120])

    # periode tumpang tindih → 400
    st, r = req("PUT", f"/api/tahun-ajaran/{TA}/periode", {
        "kode": "genap", "nama": "Semester Genap",
        "tanggal_mulai": "2025-08-01", "tanggal_selesai": "2026-06-30",
    }, token=T)
    check("periode tumpang tindih → 400", st == 400, str(r)[:120])

    # ── Cleanup ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE}, token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
