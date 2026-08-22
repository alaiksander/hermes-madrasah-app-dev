#!/usr/bin/env python3
"""Tes Pembayaran — CRUD jenis, generate tagihan per tingkat (7/8/9), bayar,
cicil, keringanan, status lunas — tanpa pytest.

Jalanake: ./venv/bin/python test_pembayaran.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"bayartest{int(time.time()) % 100000}"


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
                {"kode": KODE, "nama": "MTs Tes Bayar", "plan": "free"},
                token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin Bayar", "username": "admbayar",
                 "password": "admbayar123"}, token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admbayar",
                 "password": "admbayar123"})
    check("login admin tenant", st == 200, str(r))
    T = r["access_token"]

    # ── Kelas tingkat 7/8/9 + murid ──
    st, r = req("GET", "/api/tahun-ajaran", token=T)
    TA = r[0]["id"]
    kelas = {}
    for tkt in ("7", "8", "9"):
        st, r = req("POST", "/api/kelas",
                    {"nama_kelas": f"{tkt}A", "tahun_ajaran_id": TA}, token=T)
        check(f"buat kelas {tkt}A", st == 201, str(r))
        kelas[tkt] = r["id"]
    murid_ids = {}
    for tkt in ("7", "8", "9"):
        st, r = req("POST", "/api/murid",
                    {"nisn": f"24000000{tkt}1", "nama": f"Siswa {tkt}",
                     "kelas_id": kelas[tkt]}, token=T)
        check(f"buat murid {tkt}", st == 201, str(r))
        murid_ids[tkt] = r["id"]

    # ── CRUD jenis pembayaran ──
    st, r = req("POST", "/api/tagihan/jenis",
                {"nama": "SPP", "deskripsi": "SPP bulanan", "nominal": 100000,
                 "periode": "bulanan", "jatuh_tempo": 10, "auto_generate": True,
                 "boleh_cicil": True}, token=T)
    check("buat jenis SPP", st == 201 and r["nama"] == "SPP", str(r))
    spp_id = r["id"]

    st, r = req("POST", "/api/tagihan/jenis",
                {"nama": "Seragam", "nominal": 200000, "periode": "sekali",
                 "jatuh_tempo": 0, "auto_generate": False, "boleh_cicil": False},
                token=T)
    check("buat jenis Seragam", st == 201, str(r))
    seragam_id = r["id"]

    st, r = req("POST", "/api/tagihan/jenis",
                {"nama": "X", "nominal": 1000, "periode": "invalid"}, token=T)
    check("periode invalid → 400", st == 400, str(r))

    st, r = req("PATCH", f"/api/tagihan/jenis/{spp_id}", {"nominal": 120000},
                token=T)
    check("edit jenis nominal", st == 200 and r["nominal"] == 120000, str(r))

    st, r = req("GET", "/api/tagihan/jenis", token=T)
    check("list jenis = 2", st == 200 and len(r) == 2, str(r))

    # ── Generate tagihan per tingkat (7/8/9) ──
    st, r = req("POST", "/api/tagihan/generate?tingkat=7&periode=2026-08",
                token=T)
    check("generate tagihan tingkat 7", st == 200 and r["total_baru"] == 1,
          str(r))
    st, r = req("POST", "/api/tagihan/generate?tingkat=8&periode=2026-08",
                token=T)
    check("generate tagihan tingkat 8", st == 200 and r["total_baru"] == 1,
          str(r))
    st, r = req("POST", "/api/tagihan/generate?tingkat=9&periode=2026-08",
                token=T)
    check("generate tagihan tingkat 9", st == 200 and r["total_baru"] == 1,
          str(r))

    # Idempotent
    st, r = req("POST", "/api/tagihan/generate?tingkat=7&periode=2026-08",
                token=T)
    check("generate idempotent (0 baru)", st == 200 and r["total_baru"] == 0,
          str(r))

    # ── List tagihan ──
    st, r = req("GET", "/api/tagihan?periode=2026-08", token=T)
    check("list tagihan = 3", st == 200 and len(r) == 3, str(r))
    tagihan7 = next(x for x in r if x["murid_nisn"] == "2400000071")
    tagihan8 = next(x for x in r if x["murid_nisn"] == "2400000081")
    tagihan9 = next(x for x in r if x["murid_nisn"] == "2400000091")

    # ── Bayar lunas (tingkat 7) ──
    st, r = req("POST", f"/api/tagihan/{tagihan7['id']}/bayar",
                {"nominal": 120000, "metode": "cash"}, token=T)
    check("bayar lunas", st == 200 and r["status"] == "lunas", str(r))

    # ── Cicil (tingkat 8) ──
    st, r = req("POST", f"/api/tagihan/{tagihan8['id']}/bayar",
                {"nominal": 50000, "metode": "cash"}, token=T)
    check("bayar cicil", st == 200 and r["status"] == "sebagian", str(r))
    st, r = req("POST", f"/api/tagihan/{tagihan8['id']}/bayar",
                {"nominal": 70000, "metode": "transfer"}, token=T)
    check("bayar cicil lunas", st == 200 and r["status"] == "lunas", str(r))

    # ── Keringanan (tingkat 9) ──
    st, r = req("POST", f"/api/tagihan/{tagihan9['id']}/keringanan",
                {"potongan": 20000, "catatan": "Beasiswa"}, token=T)
    check("keringanan", st == 200 and r["potongan"] == 20000, str(r))
    st, r = req("POST", f"/api/tagihan/{tagihan9['id']}/bayar",
                {"nominal": 100000, "metode": "cash"}, token=T)
    check("bayar setelah keringanan → lunas",
          st == 200 and r["status"] == "lunas", str(r))

    # ── Rekap kelas ──
    st, r = req("GET", "/api/tagihan/rekap-kelas?periode=2026-08", token=T)
    check("rekap kelas", st == 200 and len(r) == 3, str(r))

    # ── Tagihan manual (jenis sekali) ──
    st, r = req("POST", "/api/tagihan",
                {"murid_id": murid_ids["7"], "jenis_id": seragam_id,
                 "periode": "2026-09"}, token=T)
    check("buat tagihan manual", st == 201, str(r))
    manual_id = r["id"]
    st, r = req("POST", f"/api/tagihan/{manual_id}/bayar",
                {"nominal": 100000, "metode": "cash"}, token=T)
    check("jenis tidak boleh cicil → 400", st == 400, str(r))
    st, r = req("POST", f"/api/tagihan/{manual_id}/bayar",
                {"nominal": 200000, "metode": "cash"}, token=T)
    check("bayar penuh seragam", st == 200 and r["status"] == "lunas", str(r))

    # ── Hapus tagihan ──
    st, r = req("DELETE", f"/api/tagihan/{manual_id}", token=T)
    check("hapus tagihan", st == 200 and r["ok"], str(r))

    # ── Cleanup ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE},
                token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
