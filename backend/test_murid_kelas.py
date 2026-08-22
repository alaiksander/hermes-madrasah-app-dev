#!/usr/bin/env python3
"""Tes Murid + Kelas + Mapel + Guru + Pengampu + Tahun Ajaran — tanpa pytest.

Jalanake: ./venv/bin/python test_murid_kelas.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"muridkelastest{int(time.time()) % 100000}"


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
                {"kode": KODE, "nama": "MTs Tes Murid Kelas", "plan": "free"},
                token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin MK", "username": "admmk",
                 "password": "admmk123"}, token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admmk",
                 "password": "admmk123"})
    check("login admin tenant", st == 200, str(r))
    T = r["access_token"]

    # ── Tahun ajaran default ──
    st, r = req("GET", "/api/tahun-ajaran", token=T)
    check("tahun ajaran default", st == 200 and len(r) == 1, str(r))
    TA = r[0]["id"]

    # ── Kelas tingkat 7/8/9 ──
    st, r = req("POST", "/api/kelas", {"nama_kelas": "7A", "tahun_ajaran_id": TA},
                token=T)
    check("buat kelas 7A", st == 201 and r["nama_kelas"] == "7A", str(r))
    k7 = r["id"]
    st, r = req("POST", "/api/kelas", {"nama_kelas": "8A", "tahun_ajaran_id": TA},
                token=T)
    check("buat kelas 8A", st == 201, str(r))
    k8 = r["id"]
    st, r = req("POST", "/api/kelas", {"nama_kelas": "9A", "tahun_ajaran_id": TA},
                token=T)
    check("buat kelas 9A", st == 201, str(r))
    k9 = r["id"]

    st, r = req("POST", "/api/kelas", {"nama_kelas": "7A", "tahun_ajaran_id": TA},
                token=T)
    check("kelas dobel → 409", st == 409, str(r))

    st, r = req("GET", "/api/kelas", token=T)
    check("list kelas = 3", st == 200 and len(r) == 3, str(r))

    # ── Mapel ──
    st, r = req("POST", "/api/mapel", {"nama": "Matematika", "kode": "MTK",
                                       "kelompok": "umum"}, token=T)
    check("buat mapel", st == 201 and r["nama"] == "Matematika", str(r))
    mapel_id = r["id"]
    st, r = req("POST", "/api/mapel", {"nama": "Bahasa Indonesia", "kode": "BIN"},
                token=T)
    check("buat mapel 2", st == 201, str(r))
    mapel2 = r["id"]
    st, r = req("POST", "/api/mapel", {"nama": "Matematika"}, token=T)
    check("mapel dobel → 409", st == 409, str(r))
    st, r = req("PATCH", f"/api/mapel/{mapel_id}", {"nama": "Matematika Lanjut"},
                token=T)
    check("edit mapel", st == 200 and r["nama"] == "Matematika Lanjut", str(r))

    # ── Guru ──
    st, r = req("POST", "/api/guru",
                {"nama": "Pak Guru A", "username": "gurua", "password": "gurua123",
                 "role": "guru"}, token=T)
    check("buat guru", st == 201 and r["role"] == "guru", str(r))
    guru_id = r["id"]
    st, r = req("POST", "/api/guru",
                {"nama": "Bu Guru B", "username": "gurub", "password": "gurub123",
                 "role": "guru"}, token=T)
    check("buat guru 2", st == 201, str(r))
    guru2 = r["id"]
    st, r = req("POST", "/api/guru",
                {"nama": "Dobel", "username": "gurua", "password": "gurua123",
                 "role": "guru"}, token=T)
    check("username dobel → 409", st == 409, str(r))
    st, r = req("PATCH", f"/api/guru/{guru_id}", {"nama": "Pak Guru A Baru"},
                token=T)
    check("edit guru", st == 200 and r["nama"] == "Pak Guru A Baru", str(r))

    # ── Pengampu (guru × mapel × kelas) ──
    st, r = req("POST", "/api/guru-pengampu",
                {"guru_id": guru_id, "mapel_id": mapel_id, "kelas_id": k7,
                 "tahun_ajaran_id": TA, "is_wali": False}, token=T)
    check("buat pengampu", st == 201 and r["guru_nama"] == "Pak Guru A Baru",
          str(r))
    pengampu_id = r["id"]
    st, r = req("POST", "/api/guru-pengampu",
                {"guru_id": guru_id, "mapel_id": mapel_id, "kelas_id": k7,
                 "tahun_ajaran_id": TA, "is_wali": False}, token=T)
    check("pengampu dobel → 409", st == 409, str(r))
    st, r = req("GET", "/api/guru-pengampu?guru_id=" + str(guru_id), token=T)
    check("list pengampu guru", st == 200 and len(r) == 1, str(r))
    st, r = req("DELETE", f"/api/guru-pengampu/{pengampu_id}", token=T)
    check("hapus pengampu → 204", st == 204, str(r))

    # ── Murid CRUD ──
    st, r = req("POST", "/api/murid",
                {"nisn": "2400000001", "nama": "Siswa Satu", "kelas_id": k7,
                 "nama_ortu": "Bpk Ortu", "telepon": "6281234567801"}, token=T)
    check("buat murid + qr_uuid", st == 201 and r["qr_uuid"], str(r))
    m1 = r["id"]
    qr1 = r["qr_uuid"]
    st, r = req("POST", "/api/murid",
                {"nisn": "2400000002", "nama": "Siswa Dua", "kelas_id": k8},
                token=T)
    check("buat murid 2", st == 201, str(r))
    m2 = r["id"]
    st, r = req("POST", "/api/murid",
                {"nisn": "2400000001", "nama": "Dobel", "kelas_id": k7}, token=T)
    check("nisn dobel → 409", st == 409, str(r))

    st, r = req("GET", "/api/murid?q=Siswa", token=T)
    check("cari murid", st == 200 and r["total"] == 2, str(r))

    st, r = req("PATCH", f"/api/murid/{m1}", {"nama": "Siswa Satu Baru"},
                token=T)
    check("edit murid", st == 200 and r["nama"] == "Siswa Satu Baru", str(r))

    st, r = req("GET", f"/api/murid/{m1}", token=T)
    check("get murid", st == 200 and r["id"] == m1, str(r))

    # ── Soft-delete murid ──
    st, r = req("DELETE", f"/api/murid/{m1}", token=T)
    check("soft-delete murid", st == 200 and r["ok"], str(r))
    st, r = req("GET", "/api/murid?q=Siswa", token=T)
    check("murid soft-deleted tidak muncul", st == 200 and r["total"] == 1,
          str(r))
    st, r = req("GET", "/api/murid?q=Siswa&semua=true", token=T)
    check("murid soft-deleted muncul via semua=true",
          st == 200 and r["total"] == 2, str(r))

    # ── Hapus kelas dengan murid → 400 ──
    st, r = req("DELETE", f"/api/kelas/{k8}", token=T)
    check("hapus kelas berisi murid → 400", st == 400, str(r))

    # ── Hapus mapel ──
    st, r = req("DELETE", f"/api/mapel/{mapel2}", token=T)
    check("hapus mapel", st == 200 and r["ok"], str(r))

    # ── Cleanup ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE},
                token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
