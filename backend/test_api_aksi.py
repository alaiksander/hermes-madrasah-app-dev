#!/usr/bin/env python3
"""Tes Aksi Khusus — pindah/luluskan kelas, wali-saya/murid, reset-password &
hapus permanen guru, guru-pengampu bulk, tagihan bulk-bayar/toggle/keringanan/tunda
— tanpa pytest.

Jalanake: ./venv/bin/python test_api_aksi.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"apiaksi{int(time.time()) % 100000}"


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

    # ── Setup tenant + admin + guru ──
    st, r = req("POST", "/api/auth/login-super",
                {"username": "superadmin", "password": "super123456"})
    check("login super", st == 200, str(r))
    SUPER = r["access_token"]

    st, r = req("POST", "/api/super/tenants",
                {"kode": KODE, "nama": "MTs Tes Aksi", "plan": "free"},
                token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin Aksi", "username": "admaksi",
                 "password": "admaksi123"}, token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admaksi",
                 "password": "admaksi123"})
    check("login admin tenant", st == 200, str(r))
    T = r["access_token"]

    # ── Data dasar ──
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
    st, r = req("POST", "/api/mapel", {"nama": "Matematika", "kode": "MTK"},
                token=T)
    check("buat mapel", st == 201, str(r))
    mapel_id = r["id"]
    st, r = req("POST", "/api/guru",
                {"nama": "Guru Aksi", "username": "guruaksi",
                 "password": "guruaksi123", "role": "guru"}, token=T)
    check("buat guru", st == 201, str(r))
    guru_id = r["id"]
    st, r = req("POST", "/api/guru",
                {"nama": "Guru Hapus", "username": "guruhapus",
                 "password": "guruhapus123", "role": "guru"}, token=T)
    check("buat guru hapus", st == 201, str(r))
    guru_hapus = r["id"]
    st, r = req("POST", "/api/murid",
                {"nisn": "2400000001", "nama": "Siswa Aksi", "kelas_id": k7},
                token=T)
    check("buat murid", st == 201, str(r))
    m1 = r["id"]

    # ── Kelas pindah ──
    st, r = req("POST", "/api/kelas/pindah",
                {"dari_kelas_id": k7, "ke_kelas_id": k8}, token=T)
    check("pindah kelas", st == 200 and r["dipindah"] == 1, str(r))
    st, r = req("POST", "/api/kelas/pindah",
                {"dari_kelas_id": k7, "ke_kelas_id": k7}, token=T)
    check("pindah kelas sama → 400", st == 400, str(r))

    # ── Kelas luluskan ──
    st, r = req("POST", f"/api/kelas/{k8}/luluskan", token=T)
    check("luluskan kelas", st == 200 and r["lulus"] == 1, str(r))

    # ── Wali-saya murid (admin tidak punya kelas wali → kosong) ──
    st, r = req("GET", "/api/kelas/wali-saya/murid", token=T)
    check("wali-saya/murid", st == 200 and "murid" in r, str(r)[:120])

    # ── Guru reset-password ──
    st, r = req("POST", f"/api/guru/{guru_id}/reset-password",
                {"password": "baru123"}, token=T)
    check("reset password guru", st == 200 and r["ok"], str(r))
    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "guruaksi",
                 "password": "baru123"})
    check("login guru password baru", st == 200, str(r))

    # ── Guru hapus permanen ──
    st, r = req("DELETE", f"/api/guru/{guru_hapus}", token=T)
    check("soft-delete guru", st == 200 and r["ok"], str(r))
    st, r = req("DELETE", f"/api/guru/{guru_hapus}/permanen",
                {"konfirmasi": "salah"}, token=T)
    check("hapus permanen konfirmasi salah → 400", st == 400, str(r))
    st, r = req("DELETE", f"/api/guru/{guru_hapus}/permanen",
                {"konfirmasi": "guruhapus"}, token=T)
    check("hapus permanen guru", st == 200 and r["ok"], str(r))

    # ── Guru-pengampu bulk ──
    st, r = req("POST", "/api/guru-pengampu/bulk", {
        "guru_id": guru_id, "tahun_ajaran_id": TA,
        "items": [{"guru_id": guru_id, "mapel_id": mapel_id, "kelas_id": k7,
                   "tahun_ajaran_id": TA, "is_wali": False}],
    }, token=T)
    check("guru-pengampu bulk", st == 200 and len(r) == 1, str(r))
    st, r = req("GET", f"/api/guru-pengampu/guru/{guru_id}", token=T)
    check("guru-pengampu per guru", st == 200 and len(r) == 1, str(r))

    # ── Tagihan: jenis + generate ──
    st, r = req("POST", "/api/murid",
                {"nisn": "2400000002", "nama": "Siswa Bayar", "kelas_id": k8},
                token=T)
    check("buat murid bayar", st == 201, str(r))
    st, r = req("POST", "/api/tagihan/jenis",
                {"nama": "SPP", "nominal": 100000, "periode": "bulanan",
                 "jatuh_tempo": 10, "auto_generate": True, "boleh_cicil": True},
                token=T)
    check("buat jenis SPP", st == 201, str(r))
    spp_id = r["id"]
    st, r = req("POST", "/api/tagihan/generate?tingkat=8&periode=2026-08", token=T)
    check("generate tagihan", st == 200 and r["total_baru"] == 1, str(r))
    st, r = req("GET", "/api/tagihan?periode=2026-08", token=T)
    tagihan = r[0]

    # ── Toggle jenis ──
    st, r = req("POST", f"/api/tagihan/jenis/{spp_id}/toggle", token=T)
    check("toggle jenis", st == 200 and r["is_active"] is False, str(r))
    st, r = req("POST", f"/api/tagihan/jenis/{spp_id}/toggle", token=T)
    check("toggle jenis balik", st == 200 and r["is_active"] is True, str(r))

    # ── Keringanan ──
    st, r = req("POST", f"/api/tagihan/{tagihan['id']}/keringanan",
                {"potongan": 20000, "catatan": "Beasiswa"}, token=T)
    check("keringanan", st == 200 and r["potongan"] == 20000, str(r))

    # ── Tunda ──
    st, r = req("POST", f"/api/tagihan/{tagihan['id']}/tunda",
                {"ditunda_sampai": "2026-09-15", "catatan": "Tunda"}, token=T)
    check("tunda", st == 200 and r["status"] == "ditunda", str(r))

    # ── Bulk bayar ──
    st, r = req("POST", "/api/tagihan/bulk-bayar",
                [{"tagihan_id": tagihan["id"], "nominal": 80000, "metode": "cash"}],
                token=T)
    check("bulk-bayar", st == 200 and r["ok"] == 1, str(r))
    st, r = req("POST", "/api/tagihan/bulk-bayar", [], token=T)
    check("bulk-bayar kosong → 400", st == 400, str(r))

    # ── Cleanup ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE}, token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
