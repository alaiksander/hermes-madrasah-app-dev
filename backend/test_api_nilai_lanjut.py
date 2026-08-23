#!/usr/bin/env python3
"""Tes Nilai Lanjut — siswa materi, rekap, patch nilai, patch/delete materi — tanpa pytest.

Jalanake: ./venv/bin/python test_api_nilai_lanjut.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"apinil{int(time.time()) % 100000}"


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
                {"kode": KODE, "nama": "MTs Tes Nilai Lanjut", "plan": "free"},
                token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin Nilai", "username": "admnil2",
                 "password": "admnil2123"}, token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admnil2",
                 "password": "admnil2123"})
    check("login admin tenant", st == 200, str(r))
    T = r["access_token"]

    # ── Kelas + mapel + murid ──
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
    murid_ids = []
    for i in range(2):
        st, r = req("POST", "/api/murid",
                    {"nisn": f"24000000{i+1:02d}", "nama": f"Siswa N {i+1}",
                     "kelas_id": k7}, token=T)
        check(f"buat murid {i+1}", st == 201, str(r))
        murid_ids.append(r["id"])

    # ── Materi + input nilai ──
    st, r = req("POST", "/api/nilai/materi",
                {"mapel_id": mapel_id, "kelas_id": k7, "jenis": "tugas",
                 "nama": "Tugas 1", "kkpt": 70}, token=T)
    check("buat materi", st == 201, str(r))
    materi_id = r["id"]
    st, r = req("POST", "/api/nilai/bulk", {
        "materi_penilaian_id": materi_id,
        "entries": [{"murid_id": murid_ids[0], "skor": 90},
                    {"murid_id": murid_ids[1], "skor": 60}],
    }, token=T)
    check("input nilai bulk", st == 200 and r["disimpan"] == 2, str(r))

    # ── Siswa materi ──
    st, r = req("GET", f"/api/nilai/materi/{materi_id}/siswa", token=T)
    check("siswa materi", st == 200 and len(r["siswa"]) == 2, str(r))
    n1 = next(x for x in r["siswa"] if x["murid_id"] == murid_ids[1])

    # ── Rekap ──
    st, r = req("GET", f"/api/nilai/rekap?kelas_id={k7}", token=T)
    check("rekap nilai", st == 200 and len(r["murid"]) == 2, str(r)[:120])
    m0 = next(x for x in r["murid"] if x["murid_id"] == murid_ids[0])
    check("rata-rata murid 1 = 90", m0["rata_rata"] == 90.0, str(m0))
    m1 = next(x for x in r["murid"] if x["murid_id"] == murid_ids[1])
    check("status murid 2 Perlu Perbaikan", m1["status"] == "Perlu Perbaikan",
          str(m1))

    # ── Patch nilai per baris ──
    st, r = req("PATCH", f"/api/nilai/{n1['nilai_id']}", {"skor": 85}, token=T)
    check("patch nilai", st == 200 and r["skor"] == 85, str(r))
    st, r = req("PATCH", f"/api/nilai/{n1['nilai_id']}", {"skor": 150}, token=T)
    check("patch nilai skor > 100 → 400", st == 400, str(r))

    # ── Patch materi ──
    st, r = req("PATCH", f"/api/nilai/materi/{materi_id}",
                {"kkpt": 75, "nama": "Tugas 1 Revisi"}, token=T)
    check("patch materi", st == 200 and r["kkpt"] == 75, str(r))
    st, r = req("PATCH", f"/api/nilai/materi/{materi_id}", {"kkpt": 150}, token=T)
    check("patch materi kkpt > 100 → 400", st == 400, str(r))

    # ── Delete materi ──
    st, r = req("DELETE", f"/api/nilai/materi/{materi_id}", token=T)
    check("delete materi", st == 200 and r["ok"], str(r))
    st, r = req("GET", f"/api/nilai/materi/{materi_id}/siswa", token=T)
    check("siswa materi setelah hapus → 404", st == 404, str(r))

    # ── Cleanup ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE}, token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
