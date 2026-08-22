#!/usr/bin/env python3
"""Tes Nilai PATCH — buat materi + input nilai bulk, lalu PATCH /api/nilai/{id}
(koreksi skor/catatan) — tanpa pytest.

Jalanake: ./venv/bin/python test_api_nilai_patch.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"nilpatch{int(time.time()) % 100000}"


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
                {"kode": KODE, "nama": "MTs Tes Nilai Patch", "plan": "free"},
                token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin NilPatch", "username": "admnilpatch",
                 "password": "admnilpatch123"}, token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admnilpatch",
                 "password": "admnilpatch123"})
    check("login admin tenant", st == 200, str(r))
    T = r["access_token"]

    # ── Data dasar ──
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
    st, r = req("POST", "/api/murid",
                {"nisn": "2400000001", "nama": "Siswa Patch", "kelas_id": k7},
                token=T)
    check("buat murid", st == 201, str(r))
    m1 = r["id"]

    # ── Materi + input nilai ──
    st, r = req("POST", "/api/nilai/materi",
                {"mapel_id": mapel_id, "kelas_id": k7, "jenis": "tugas",
                 "nama": "Tugas 1", "kkpt": 70}, token=T)
    check("buat materi", st == 201, str(r))
    materi_id = r["id"]
    st, r = req("POST", "/api/nilai/bulk", {
        "materi_penilaian_id": materi_id,
        "entries": [{"murid_id": m1, "skor": 80}],
    }, token=T)
    check("input nilai bulk", st == 200 and r["disimpan"] == 1, str(r))

    # ── Ambil nilai_id dari siswa_materi ──
    st, r = req("GET", f"/api/nilai/materi/{materi_id}/siswa", token=T)
    check("siswa materi", st == 200 and len(r["siswa"]) == 1, str(r)[:120])
    nilai_id = r["siswa"][0]["nilai_id"]
    check("nilai_id ada", nilai_id is not None, str(r))

    # ── PATCH nilai ──
    st, r = req("PATCH", f"/api/nilai/{nilai_id}", {"skor": 95, "catatan": "Bagus"},
                token=T)
    check("patch nilai skor+catatan", st == 200 and r["skor"] == 95
          and r["catatan"] == "Bagus", str(r))
    st, r = req("PATCH", f"/api/nilai/{nilai_id}", {"skor": 88}, token=T)
    check("patch nilai skor saja", st == 200 and r["skor"] == 88, str(r))
    st, r = req("PATCH", f"/api/nilai/{nilai_id}", {"catatan": "Perlu perbaikan"},
                token=T)
    check("patch nilai catatan saja", st == 200
          and r["catatan"] == "Perlu perbaikan", str(r))

    # ── Validasi: skor di luar 0-100 → 400 ──
    st, r = req("PATCH", f"/api/nilai/{nilai_id}", {"skor": 150}, token=T)
    check("patch skor >100 → 400", st == 400, str(r)[:120])

    # ── Validasi: nilai_id tidak ada → 404 ──
    st, r = req("PATCH", "/api/nilai/999999", {"skor": 50}, token=T)
    check("patch nilai tidak ada → 404", st == 404, str(r)[:120])

    # ── Cleanup ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE}, token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
