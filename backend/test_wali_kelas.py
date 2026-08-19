#!/usr/bin/env python3
"""Tes Wali Kelas — tanpa pytest, mung urllib.

Jalanake: ./venv/bin/python test_wali_kelas.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8010"
KODE = f"walitest{int(time.time()) % 100000}"


def req(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


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

    # Setup tenant + admin + 2 guru
    st, r = req("POST", "/api/auth/login-super",
                {"username": "superadmin", "password": "super123456"})
    check("login super", st == 200, str(r))
    SUPER = r["access_token"]

    st, r = req("POST", "/api/super/tenants",
                {"kode": KODE, "nama": "MTs Tes Wali", "plan": "free"}, token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin Tes", "username": "admwali", "password": "admwali123"},
                token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admwali", "password": "admwali123"})
    check("login admin", st == 200, str(r))
    ADMIN = r["access_token"]

    st, r = req("POST", "/api/guru",
                {"nama": "Bu Siti Wali", "username": "wali1", "password": "wali1234",
                 "role": "guru"}, token=ADMIN)
    check("gawe guru wali", st == 201, str(r))
    wali_id = r["id"]
    st, r = req("POST", "/api/guru",
                {"nama": "Pak Budi Biasa", "username": "gurubiasa", "password": "guru1234",
                 "role": "guru"}, token=ADMIN)
    check("gawe guru biasa", st == 201, str(r))
    biasa_id = r["id"]

    # ── Edit guru ──
    st, r = req("PATCH", f"/api/guru/{biasa_id}",
                {"nama": "Pak Budi Diubah", "role": "admin"}, token=ADMIN)
    check("edit nama + role guru", st == 200 and r["nama"] == "Pak Budi Diubah"
          and r["role"] == "admin", str(r))
    st, r = req("PATCH", f"/api/guru/{biasa_id}",
                {"username": "wali1"}, token=ADMIN)
    check("username dobel → 409", st == 409, str(r))
    st, r = req("PATCH", f"/api/guru/{biasa_id}",
                {"username": "gurubiasa2"}, token=ADMIN)
    check("ganti username", st == 200 and r["username"] == "gurubiasa2", str(r))
    # balekke (biar login guru biasa tetep ana)
    st, r = req("PATCH", f"/api/guru/{biasa_id}",
                {"username": "gurubiasa", "role": "guru"}, token=ADMIN)
    check("balekke username + role", st == 200, str(r))

    # ── Manajemen admin (superadmin) ──
    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin Dua", "username": "adm2", "password": "adm2pass123"},
                token=SUPER)
    check("gawe admin kapindho", st == 201, str(r))
    st, r = req("GET", f"/api/super/tenants/{tid}/admins", token=SUPER)
    adm2 = next(a["id"] for a in r if a["username"] == "adm2")

    st, r = req("GET", f"/api/super/tenants/{tid}/admins", token=SUPER)
    check("daftar admin = 2", st == 200 and len(r) == 2, str(r))

    st, r = req("GET", f"/api/super/tenants/{tid}/admins?semua=true", token=SUPER)
    check("semua akun (admin+guru)", st == 200 and len(r) == 4, str(r))

    st, r = req("PATCH", f"/api/super/tenants/{tid}/admins/{adm2}",
                {"nama": "Admin Dua Baru"}, token=SUPER)
    check("edit nama admin", st == 200 and r["nama"] == "Admin Dua Baru", str(r))

    st, r = req("PATCH", f"/api/super/tenants/{tid}/admins/{adm2}",
                {"role": "guru"}, token=SUPER)
    check("turune admin → guru (masih 2 admin)", st == 200 and r["role"] == "guru", str(r))
    st, r = req("PATCH", f"/api/super/tenants/{tid}/admins/{adm2}",
                {"role": "admin"}, token=SUPER)
    check("balekke role admin", st == 200, str(r))

    st, r = req("PATCH", f"/api/super/tenants/{tid}/admins/{adm2}",
                {"is_active": False}, token=SUPER)
    check("nonaktifake admin (masih 2)", st == 200 and r["is_active"] is False, str(r))
    st, r = req("PATCH", f"/api/super/tenants/{tid}/admins/{adm2}",
                {"is_active": True}, token=SUPER)
    check("aktifake maneh", st == 200, str(r))

    st, r = req("DELETE", f"/api/super/tenants/{tid}/admins/{adm2}", token=SUPER)
    check("hapus admin kapindho", st == 200, str(r))

    # Proteksi admin pungkasan
    st, r = req("DELETE", f"/api/super/tenants/{tid}/admins/1", token=SUPER)
    check("hapus admin pungkasan → 400", st == 400, str(r))
    st, r = req("PATCH", f"/api/super/tenants/{tid}/admins/1",
                {"role": "guru"}, token=SUPER)
    check("turune admin pungkasan → 400", st == 400, str(r))
    st, r = req("PATCH", f"/api/super/tenants/{tid}/admins/1",
                {"is_active": False}, token=SUPER)
    check("nonaktifake admin pungkasan → 400", st == 400, str(r))
    # admin ora iso ngubah role dhewe
    admin_me = req("GET", "/api/auth/me", token=ADMIN)[1]
    st, r = req("PATCH", f"/api/guru/{admin_me['id']}",
                {"role": "guru"}, token=ADMIN)
    check("admin ora iso ngubah role dhewe → 400", st == 400, str(r))

    st, r = req("GET", "/api/tahun-ajaran", token=ADMIN)
    TA = r[0]["id"]

    # 1. Gawe kelas karo wali
    st, r = req("POST", "/api/kelas",
                {"nama_kelas": "7A", "wali_guru_id": wali_id, "tahun_ajaran_id": TA},
                token=ADMIN)
    check("gawe kelas + wali", st == 201 and r["wali_guru_nama"] == "Bu Siti Wali", str(r))
    kelas_id = r["id"]

    # 2. Kelas tanpa wali → wali_guru_nama None
    st, r = req("POST", "/api/kelas", {"nama_kelas": "7B", "tahun_ajaran_id": TA},
                token=ADMIN)
    check("kelas tanpa wali", st == 201 and r["wali_guru_nama"] is None, str(r))

    # 3. wali-saya kanggo guru wali
    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "wali1", "password": "wali1234"})
    check("login guru wali", st == 200, str(r))
    WALI = r["access_token"]

    st, r = req("GET", "/api/kelas/wali-saya", token=WALI)
    check("wali-saya: kelas wali", st == 200 and [k["nama_kelas"] for k in r] == ["7A"], str(r))

    # 4. wali-saya kanggo guru biasa → kosong
    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "gurubiasa", "password": "guru1234"})
    check("login guru biasa", st == 200, str(r))
    BIASA = r["access_token"]
    st, r = req("GET", "/api/kelas/wali-saya", token=BIASA)
    check("wali-saya guru biasa kosong", st == 200 and r == [], str(r))

    # 5. Admin ora wali → wali-saya kosong (kartu Rekap ora katon)
    st, r = req("GET", "/api/kelas/wali-saya", token=ADMIN)
    check("wali-saya admin kosong (ora wali kelas)",
          st == 200 and r == [], str(r))

    # 5b. Admin sing didadikake wali → wali-saya isi
    st, r = req("PATCH", f"/api/kelas/{kelas_id}", {"wali_guru_id": None}, token=ADMIN)
    admin_id = req("GET", "/api/auth/me", token=ADMIN)[1]["id"]
    st, r = req("PATCH", f"/api/kelas/{kelas_id}", {"wali_guru_id": admin_id}, token=ADMIN)
    check("admin didadikake wali", st == 200 and r["wali_guru_nama"] == "Admin Tes", str(r))
    st, r = req("GET", "/api/kelas/wali-saya", token=ADMIN)
    check("wali-saya admin (dadi wali) isi",
          st == 200 and [k["nama_kelas"] for k in r] == ["7A"], str(r))
    # balekke wali menyang Bu Siti kanggo kasus 6
    st, r = req("PATCH", f"/api/kelas/{kelas_id}", {"wali_guru_id": wali_id}, token=ADMIN)

    # 6. Ganti wali → wali-saya pindah
    guru_list = req("GET", "/api/guru", token=ADMIN)[1]
    biasa_id = next(g["id"] for g in guru_list if g["username"] == "gurubiasa")
    st, r = req("PATCH", f"/api/kelas/{kelas_id}", {"wali_guru_id": biasa_id}, token=ADMIN)
    check("ganti wali kelas", st == 200 and r["wali_guru_nama"] == "Pak Budi Diubah", str(r))
    st, r = req("GET", "/api/kelas/wali-saya", token=WALI)
    check("wali lawas ora nduwe kelas maneh", st == 200 and r == [], str(r))
    st, r = req("GET", "/api/kelas/wali-saya", token=BIASA)
    check("wali anyar entuk kelas", st == 200 and [k["nama_kelas"] for k in r] == ["7A"], str(r))

    # 7. Bisa dikosongke (tanpa wali)
    st, r = req("PATCH", f"/api/kelas/{kelas_id}", {"wali_guru_id": None}, token=ADMIN)
    check("kosongke wali", st == 200 and r["wali_guru_nama"] is None, str(r))

    # Cleanup
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE}, token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
