#!/usr/bin/env python3
"""Tes Absensi — input manual (H/I/S/A), rekap, kartu QR — tanpa pytest.

Jalanake: ./venv/bin/python test_absensi.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"absensitest{int(time.time()) % 100000}"


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

    # ── Setup tenant + admin + guru ──
    st, r = req("POST", "/api/auth/login-super",
                {"username": "superadmin", "password": "super123456"})
    check("login super", st == 200, str(r))
    SUPER = r["access_token"]

    st, r = req("POST", "/api/super/tenants",
                {"kode": KODE, "nama": "MTs Tes Absensi", "plan": "free"},
                token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin Abs", "username": "admabs",
                 "password": "admabs123"}, token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admabs",
                 "password": "admabs123"})
    check("login admin tenant", st == 200, str(r))
    T = r["access_token"]

    st, r = req("POST", "/api/guru",
                {"nama": "Guru Absen", "username": "guruabsen",
                 "password": "guruabsen123", "role": "guru"}, token=T)
    check("buat guru", st == 201, str(r))
    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "guruabsen",
                 "password": "guruabsen123"})
    check("login guru", st == 200, str(r))
    G = r["access_token"]

    # ── Kelas + murid ──
    st, r = req("GET", "/api/tahun-ajaran", token=T)
    TA = r[0]["id"]
    st, r = req("POST", "/api/kelas", {"nama_kelas": "7A", "tahun_ajaran_id": TA},
                token=T)
    check("buat kelas 7A", st == 201, str(r))
    k7 = r["id"]
    st, r = req("POST", "/api/kelas", {"nama_kelas": "8A", "tahun_ajaran_id": TA},
                token=T)
    check("buat kelas 8A", st == 201, str(r))
    k8 = r["id"]

    murid_ids = []
    for i in range(4):
        st, r = req("POST", "/api/murid",
                    {"nisn": f"24000000{i+1:02d}", "nama": f"Siswa Abs {i+1}",
                     "kelas_id": k7, "nama_ortu": "Bpk Ortu",
                     "telepon": "6281234567801"}, token=T)
        check(f"buat murid {i+1}", st == 201, str(r))
        murid_ids.append(r["id"])
    st, r = req("POST", "/api/murid",
                {"nisn": "2400000005", "nama": "Siswa Abs 5", "kelas_id": k8},
                token=T)
    check("buat murid kelas 8", st == 201, str(r))
    murid8 = r["id"]

    # ── Input absensi manual per kelas (H/I/S/A) ──
    TGL = "2026-07-28"
    st, r = req("POST", f"/api/absensi/kelas/{k7}", {
        "tanggal": TGL,
        "entries": [
            {"murid_id": murid_ids[0], "status": "hadir"},
            {"murid_id": murid_ids[1], "status": "izin"},
            {"murid_id": murid_ids[2], "status": "sakit"},
            {"murid_id": murid_ids[3], "status": "alpa"},
            {"murid_id": 99999, "status": "hadir"},
            {"murid_id": murid_ids[0], "status": "alpa"},
            {"murid_id": murid_ids[0], "status": "bolos"},
        ],
    }, token=G)
    check("bulk absen: 4 ditambah", st == 200 and r["ditambahkan"] == 4, str(r))
    check("bulk absen: error 2 (murid/status)", st == 200 and len(r["error"]) == 2,
          str(r))

    # ── Rekap ──
    st, r = req("GET", f"/api/absensi/rekap?tanggal={TGL}", token=T)
    check("rekap: 1H 1I 1S 1A", st == 200 and r["hadir"] == 1 and r["izin"] == 1
          and r["sakit"] == 1 and r["alpa"] == 1, str(r))
    check("rekap: belum = total - 4",
          st == 200 and r["belum"] == r["total_murid"] - 4, str(r))

    # ── Roster kelas ──
    st, r = req("GET", f"/api/absensi/kelas/{k7}?tanggal={TGL}", token=T)
    check("roster kelas 7A = 4", st == 200 and len(r) == 4, str(r))

    # ── Admin override ──
    st, r = req("POST", f"/api/absensi/kelas/{k7}", {
        "tanggal": TGL,
        "entries": [{"murid_id": murid_ids[0], "status": "alpa"}],
    }, token=T)
    check("admin override (diubah)", st == 200 and r["diubah"] == 1, str(r))

    # ── Koreksi admin ──
    st, r = req("POST", "/api/absensi/koreksi",
                {"murid_id": murid_ids[1], "tanggal": TGL, "sesi": "masuk",
                 "mode": "koreksi", "status": "hadir"}, token=T)
    check("koreksi izin→hadir", st == 200 and r["status"] == "koreksi", str(r))

    # ── Export CSV ──
    st, r = req("GET", f"/api/absensi/export.csv?tanggal={TGL}", token=T, raw=True)
    body = r.decode("utf-8", errors="replace") if isinstance(r, bytes) else str(r)
    check("export harian label Hadir/Sakit/Alpa",
          "Hadir" in body and "Sakit" in body and "Alpa" in body, "")

    # ── Kartu QR generate (PNG) ──
    st, r = req("GET", f"/api/murid/{murid_ids[0]}/qr.png", token=T, raw=True)
    check("PNG QR card", st == 200 and isinstance(r, bytes)
          and r[:8] == b"\x89PNG\r\n\x1a\n", f"header={r[:8]!r}")

    # ── Scan QR (hari ini — mungkin libur, hanya cek status code) ──
    st, r = req("POST", "/api/absensi/scan", {"qr_uuid": "uuid-salah"}, token=G)
    check("scan QR tidak dikenal → 404", st == 404, str(r))

    # ── Cleanup ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE},
                token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
