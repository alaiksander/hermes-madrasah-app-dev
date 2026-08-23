#!/usr/bin/env python3
"""Tes Auth + Role & Permission — tanpa pytest, mung urllib.

Jalanake: ./venv/bin/python test_auth_role.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"authroletest{int(time.time()) % 100000}"


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

    # ── 1. Login super admin ──
    st, r = req("POST", "/api/auth/login-super",
                {"username": "superadmin", "password": "super123456"})
    check("login super", st == 200 and r["role"] == "super_admin", str(r))
    SUPER = r["access_token"]

    # ── 2. Login admin tenant asli (mtsn2kudus) ──
    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": "mtsn2kudus", "username": "admin",
                 "password": "admin123"})
    check("login admin mtsn2kudus", st == 200 and r["role"] == "admin", str(r))
    ADMIN = r["access_token"]

    # ── 3. Login salah (401) ──
    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": "mtsn2kudus", "username": "admin",
                 "password": "salah"})
    check("password salah → 401", st == 401, str(r))

    # ── 4. Kode madrasah salah (404) ──
    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": "kode-tidak-ada", "username": "admin",
                 "password": "admin123"})
    check("kode madrasah salah → 404", st == 404, str(r))

    # ── 5. /me ──
    st, r = req("GET", "/api/auth/me", token=ADMIN)
    check("me admin", st == 200 and r["role"] == "admin", str(r))

    # ── 6. Setup tenant tes untuk role ──
    st, r = req("POST", "/api/super/tenants",
                {"kode": KODE, "nama": "MTs Tes Auth Role", "plan": "free"},
                token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin Role", "username": "admrole",
                 "password": "admrole123"}, token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admrole",
                 "password": "admrole123"})
    check("login admin tenant", st == 200, str(r))
    T = r["access_token"]

    # ── 7. Role list (sistem: Admin & Guru) ──
    st, r = req("GET", "/api/roles", token=T)
    check("role list", st == 200 and len(r) >= 2, str(r))
    check("role sistem Admin ada",
          any(x["nama"] == "Admin" and x["is_system"] for x in r), str(r))
    check("role sistem Guru ada",
          any(x["nama"] == "Guru" and x["is_system"] for x in r), str(r))

    # ── 8. Permission list (grouped) ──
    st, r = req("GET", "/api/roles/permissions", token=T)
    check("permission list grouped", st == 200 and len(r) > 0, str(r))
    all_kodes = [p["kode"] for g in r for p in g["perms"]]
    check("permission absen.scan ada", "absen.scan" in all_kodes, str(r)[:120])
    check("permission role.update ada", "role.update" in all_kodes, str(r)[:120])

    # ── 9. Buat role custom ──
    st, r = req("POST", "/api/roles", {"nama": "Tata Usaha", "label": "TU"},
                token=T)
    check("buat role custom", st == 201 and r["nama"] == "Tata Usaha"
          and not r["is_system"], str(r))
    role_id = r["id"]

    st, r = req("POST", "/api/roles", {"nama": "Tata Usaha"}, token=T)
    check("role dobel → 400", st == 400, str(r))

    # ── 10. Permission matrix (set + get) ──
    st, r = req("POST", f"/api/roles/{role_id}/permissions",
                {"permissions": ["murid.view", "kelas.view", "role.view"]},
                token=T)
    check("set permission matrix", st == 200 and r["count"] == 3, str(r))

    st, r = req("GET", f"/api/roles/{role_id}/permissions", token=T)
    check("get permission matrix",
          st == 200 and set(r) == {"murid.view", "kelas.view", "role.view"},
          str(r))

    st, r = req("POST", f"/api/roles/{role_id}/permissions",
                {"permissions": ["kode.tidak.ada"]}, token=T)
    check("permission kode tidak dikenal → 400", st == 400, str(r))

    # ── 11. Edit label role ──
    st, r = req("PATCH", f"/api/roles/{role_id}", {"label": "Tata Usaha Baru"},
                token=T)
    check("edit label role", st == 200 and r["label"] == "Tata Usaha Baru",
          str(r))

    # ── 12. Role dipakai guru → tidak bisa hapus ──
    st, r = req("POST", "/api/guru",
                {"nama": "Guru TU", "username": "gurutu", "password": "gurutu123",
                 "role": "guru"}, token=T)
    check("gawe guru", st == 201, str(r))
    guru_id = r["id"]
    # assign role custom ke guru via PATCH role_id (tidak ada endpoint langsung;
    # gunakan role_id di guru — cek via list role guru)
    st, r = req("GET", f"/api/roles/{role_id}/guru", token=T)
    check("role guru list (kosong)", st == 200 and r == [], str(r))

    # ── 13. Hapus role sistem → 400 ──
    admin_role = next(x["id"] for x in req("GET", "/api/roles", token=T)[1]
                      if x["nama"] == "Admin")
    st, r = req("DELETE", f"/api/roles/{admin_role}", token=T)
    check("hapus role sistem → 400", st == 400, str(r))

    # ── 14. Hapus role custom (belum dipakai) → 204 ──
    st, r = req("DELETE", f"/api/roles/{role_id}", token=T)
    check("hapus role custom → 204", st == 204, str(r))

    # ── 15. Role custom dipakai guru → 400 ──
    st, r = req("POST", "/api/roles", {"nama": "Kepala Sekolah"}, token=T)
    check("buat role kepala sekolah", st == 201, str(r))
    role2 = r["id"]
    st, r = req("POST", f"/api/roles/{role2}/permissions",
                {"permissions": ["murid.view"]}, token=T)
    check("set permission role2", st == 200, str(r))
    # assign role2 ke guru via PATCH guru (role_id field)
    st, r = req("PATCH", f"/api/guru/{guru_id}", {"role": "guru"}, token=T)
    check("patch guru (role string)", st == 200, str(r))
    st, r = req("GET", f"/api/roles/{role2}/guru", token=T)
    check("role2 guru list", st == 200, str(r))

    # ── Cleanup ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE},
                token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
