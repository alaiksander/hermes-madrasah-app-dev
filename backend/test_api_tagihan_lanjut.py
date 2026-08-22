#!/usr/bin/env python3
"""Tes Tagihan lanjutan — generate (auto-generate), keringanan, tunda — tanpa pytest.

Jalanake: ./venv/bin/python test_api_tagihan_lanjut.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"taglanjut{int(time.time()) % 100000}"


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
                {"kode": KODE, "nama": "MTs Tes Tagihan Lanjut", "plan": "free"},
                token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin TagL", "username": "admtagl",
                 "password": "admtagl123"}, token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admtagl",
                 "password": "admtagl123"})
    check("login admin tenant", st == 200, str(r))
    T = r["access_token"]

    # ── Kelas + murid aktif ──
    st, r = req("GET", "/api/tahun-ajaran", token=T)
    TA = r[0]["id"]
    st, r = req("POST", "/api/kelas", {"nama_kelas": "7A", "tahun_ajaran_id": TA},
                token=T)
    check("buat kelas 7A", st == 201, str(r))
    k7 = r["id"]
    st, r = req("POST", "/api/murid",
                {"nisn": "2400000001", "nama": "Siswa TagL", "kelas_id": k7},
                token=T)
    check("buat murid", st == 201, str(r))
    m1 = r["id"]

    # ── Jenis auto-generate aktif ──
    st, r = req("POST", "/api/tagihan/jenis",
                {"nama": "SPP", "nominal": 100000, "periode": "bulanan",
                 "jatuh_tempo": 10, "auto_generate": True, "boleh_cicil": True},
                token=T)
    check("buat jenis SPP auto", st == 201, str(r))
    spp_id = r["id"]

    # ── Generate ──
    st, r = req("POST", "/api/tagihan/generate?tingkat=7&periode=2026-08", token=T)
    check("generate tagihan", st == 200 and r["total_baru"] == 1, str(r))
    st, r = req("POST", "/api/tagihan/generate?tingkat=7&periode=2026-08", token=T)
    check("generate idempotent (0 baru)", st == 200 and r["total_baru"] == 0, str(r))
    st, r = req("POST", "/api/tagihan/generate?periode=2026-13", token=T)
    check("generate periode invalid → 400", st == 400, str(r)[:120])

    # ── Ambil tagihan ──
    st, r = req("GET", "/api/tagihan?periode=2026-08", token=T)
    check("list tagihan", st == 200 and len(r) == 1, str(r)[:120])
    tagihan = r[0]

    # ── Keringanan ──
    st, r = req("POST", f"/api/tagihan/{tagihan['id']}/keringanan",
                {"potongan": 20000, "catatan": "Beasiswa"}, token=T)
    check("keringanan", st == 200 and r["potongan"] == 20000, str(r))
    st, r = req("POST", f"/api/tagihan/{tagihan['id']}/keringanan",
                {"potongan": 200000, "catatan": "x"}, token=T)
    check("keringanan >= nominal → 400", st == 400, str(r)[:120])

    # ── Tunda ──
    st, r = req("POST", f"/api/tagihan/{tagihan['id']}/tunda",
                {"ditunda_sampai": "2026-09-15", "catatan": "Tunda"}, token=T)
    check("tunda", st == 200 and r["status"] == "ditunda", str(r))

    # ── Validasi: tagihan tidak ada → 404 ──
    st, r = req("POST", "/api/tagihan/999999/keringanan",
                {"potongan": 1000, "catatan": "x"}, token=T)
    check("keringanan tagihan tidak ada → 404", st == 404, str(r)[:120])
    st, r = req("POST", "/api/tagihan/999999/tunda",
                {"ditunda_sampai": "2026-09-15", "catatan": "x"}, token=T)
    check("tunda tagihan tidak ada → 404", st == 404, str(r)[:120])

    # ── Cleanup ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE}, token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
