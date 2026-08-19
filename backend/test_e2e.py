#!/usr/bin/env python3
"""Test end-to-end API madrasah — tanpa pytest, mung urllib.

Jalanake: ./venv/bin/python test_e2e.py
"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8010"

TEST_TENANT_KODE = f"mtstest{int(time.time()) % 100000}"


def req(method: str, path: str, body=None, token=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            content = resp.read()
            return resp.status, content if raw else json.loads(content)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main():
    ok = fail = 0

    def check(name, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  ✅ {name}")
        else:
            fail += 1
            print(f"  ❌ {name} — {detail}")

    print("1) Super admin")
    st, r = req("POST", "/api/auth/login-super", {"username": "superadmin", "password": "super123456"})
    check("login super", st == 200 and r["role"] == "super_admin", str(r))
    SUPER = r["access_token"]

    st, r = req("GET", "/api/super/tenants", token=SUPER)
    check("daftar tenant", st == 200 and len(r) == 1 and r[0]["kode"] == "mtsn2kudus", str(r))
    check("count tenant", st == 200 and r[0]["jumlah_murid"] == 24, str(r))

    st, r = req("POST", "/api/super/tenants", {"kode": TEST_TENANT_KODE, "nama": "MTs N 1 Kudus", "plan": "free"}, token=SUPER)
    check("gawe tenant anyar + provision db", st == 201, str(r))
    tid = r["id"]

    st, r = req("PATCH", f"/api/super/tenants/{tid}", {"status": "trial", "plan": "free"}, token=SUPER)
    check("update status tenant", st == 200 and r["status"] == "trial", str(r))

    print("\n2) Login tenant (MTs N 2 Kudus)")
    st, r = req("POST", "/api/auth/login", {"kode_madrasah": "mtsn2kudus", "username": "admin", "password": "admin123"})
    check("login admin", st == 200 and r["role"] == "admin", str(r))
    ADMIN = r["access_token"]

    st, r = req("POST", "/api/auth/login", {"kode_madrasah": "mtsn2kudus", "username": "guru1", "password": "guru1234"})
    check("login guru", st == 200 and r["role"] == "guru", str(r))
    GURU = r["access_token"]

    st, r = req("POST", "/api/auth/login", {"kode_madrasah": "mtsn2kudus", "username": "admin", "password": "salah"})
    check("password salah ditolak", st == 401, str(r))

    st, r = req("GET", "/api/auth/me", token=ADMIN)
    check("me admin", st == 200 and r["tenant_nama"] == "MTs Negeri 2 Kudus", str(r))

    print("\n3) Data master")
    st, r = req("GET", "/api/kelas", token=GURU)
    check("guru baca kelas", st == 200 and len(r) == 6, str(r))

    st, r = req("POST", "/api/kelas", {"nama_kelas": "7C"}, token=GURU)
    check("guru ora bisa gawe kelas (403)", st == 403, str(r))

    st, r = req("POST", "/api/kelas", {"nama_kelas": "7C"}, token=ADMIN)
    check("admin gawe kelas", st == 201, str(r))

    st, r = req("POST", "/api/murid", {"nis": "24101", "nama": "Andi Pratama", "kelas_id": 1,
                                       "nama_ortu": "Bpk Budi", "wa_ortu": "6281234567801"}, token=ADMIN)
    check("gawe murid anyar + qr_uuid", st == 201 and r["qr_uuid"], str(r))
    andi_qr = r["qr_uuid"]

    st, r = req("GET", "/api/murid?q=Andi", token=GURU)
    check("cari murid by nama", st == 200 and r["total"] == 1 and r["items"][0]["nama"] == "Andi Pratama", str(r))

    print("\n4) Absensi")
    st, r = req("POST", "/api/absensi/scan", {"qr_uuid": andi_qr}, token=GURU)
    check("scan QR → hadir", st == 200 and r["status"] == "hadir", str(r))
    andi_id = r["murid"]["id"]

    st, r = req("POST", "/api/absensi/scan", {"qr_uuid": andi_qr}, token=GURU)
    check("scan dobel → duplikat", st == 200 and r["status"] == "duplikat", str(r))

    st, r = req("POST", "/api/absensi/scan", {"qr_uuid": "uuid-salah"}, token=GURU)
    check("QR ora dikenal → 404", st == 404, str(r))

    st, r = req("GET", "/api/murid?per_page=5", token=ADMIN)
    murid2 = r["items"][1]["id"]
    st, r = req("POST", "/api/absensi/manual", {"murid_id": murid2}, token=ADMIN)
    check("absen manual (fallback)", st == 200 and r["status"] == "hadir", str(r))

    st, r = req("GET", "/api/absensi/hari-ini", token=GURU)
    check("daftar hari ini", st == 200 and len(r) == 2, str(r))

    st, r = req("GET", "/api/absensi/rekap", token=ADMIN)
    check("rekap: total 25, hadir 2", st == 200 and r["total_murid"] == 25 and r["hadir"] == 2, str(r))
    check("rekap rinci per kelas", st == 200 and len(r["per_kelas"]) >= 6, str(r))

    print("\n5) QR Card")
    st, r = req("GET", f"/api/murid/{andi_id}/qr.png", token=ADMIN, raw=True)
    check("PNG QR card", st == 200 and isinstance(r, bytes) and r[:8] == b"\x89PNG\r\n\x1a\n",
          f"header={r[:8]!r}")

    print("\n6) Isolasi tenant")
    st, r = req("POST", "/api/auth/login", {"kode_madrasah": TEST_TENANT_KODE, "username": "admin", "password": "admin123"})
    check("tenant anyar durung nduwe user (401)", st == 401, str(r))

    print("\n7) Absen per kelas manual (S/I/A)")
    TGL = "2026-07-28"  # tanggal tes sing resik
    st, r = req("GET", "/api/absensi/kelas/2?tanggal=" + TGL, token=GURU)
    check("roster kelas 7B kosong", st == 200 and len(r) == 4 and all(i["status"] is None for i in r), str(r)[:120])

    st, r = req("POST", "/api/absensi/kelas/2", {
        "tanggal": TGL,
        "entries": [
            {"murid_id": 5, "status": "hadir"},
            {"murid_id": 6, "status": "izin"},
            {"murid_id": 7, "status": "sakit"},
            {"murid_id": 8, "status": "alpa"},
            {"murid_id": 999, "status": "hadir"},   # ora ana / bukan kelas iki
            {"murid_id": 6, "status": "alpa"},      # duplikat → dedupe
            {"murid_id": 5, "status": "bolos"},     # status ora valid → error
        ],
    }, token=GURU)
    check("guru bulk absen: 4 ditambah", st == 200 and r["ditambahkan"] == 4, str(r))
    check("guru: error murid/status", st == 200 and len(r["error"]) == 2, str(r))

    st, r = req("POST", "/api/absensi/kelas/2", {
        "tanggal": TGL,
        "entries": [{"murid_id": 5, "status": "alpa"}],
    }, token=GURU)
    check("guru ora bisa override (sudah_ada)", st == 200 and r["sudah_ada"] == 1 and r["diubah"] == 0, str(r))

    st, r = req("POST", "/api/absensi/kelas/2", {
        "tanggal": TGL,
        "entries": [{"murid_id": 5, "status": "alpa"}],
    }, token=ADMIN)
    check("admin override (diubah)", st == 200 and r["diubah"] == 1 and r["sudah_ada"] == 0, str(r))

    st, r = req("GET", "/api/absensi/rekap?tanggal=" + TGL, token=ADMIN)
    check("rekap S/I/A: 0H 1I 1S 2A, belum=total-4",
          st == 200 and r["hadir"] == 0 and r["izin"] == 1 and r["sakit"] == 1
          and r["alpa"] == 2 and r["belum"] == r["total_murid"] - 4, str(r))

    st, r = req("GET", "/api/absensi/export.csv?tanggal=" + TGL, token=ADMIN, raw=True)
    body = r.decode("utf-8", errors="replace") if isinstance(r, bytes) else str(r)
    check("export harian label Izin/Sakit/Alpa",
          "Izin" in body and "Sakit" in body and "Alpa" in body, "")

    st, r = req("GET", "/api/absensi/export.csv?dari=" + TGL + "&sampai=" + TGL, token=ADMIN, raw=True)
    body = r.decode("utf-8", errors="replace") if isinstance(r, bytes) else str(r)
    check("export matrix huruf H/I/S/A",
          "I," in body and "S," in body and "A," in body, "")

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
