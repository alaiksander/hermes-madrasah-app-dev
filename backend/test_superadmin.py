#!/usr/bin/env python3
"""Tes Superadmin — CRUD tenant, GlobalSetting nama_aplikasi, user superadmin —
tanpa pytest.

Jalanake: ./venv/bin/python test_superadmin.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"supertest{int(time.time()) % 100000}"


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

    # ── 2. List tenant (mtsn2kudus ada) ──
    st, r = req("GET", "/api/super/tenants", token=SUPER)
    check("list tenant", st == 200 and any(t["kode"] == "mtsn2kudus" for t in r),
          str(r)[:120])

    # ── 3. CRUD tenant ──
    st, r = req("POST", "/api/super/tenants",
                {"kode": KODE, "nama": "MTs Tes Super", "plan": "free"},
                token=SUPER)
    check("buat tenant", st == 201 and r["kode"] == KODE, str(r))
    tid = r["id"]

    st, r = req("POST", "/api/super/tenants",
                {"kode": KODE, "nama": "Dobel", "plan": "free"}, token=SUPER)
    check("tenant dobel → 409", st == 409, str(r))

    st, r = req("PATCH", f"/api/super/tenants/{tid}",
                {"status": "trial", "plan": "free", "max_murid": 500}, token=SUPER)
    check("update tenant", st == 200 and r["status"] == "trial"
          and r["max_murid"] == 500, str(r))

    st, r = req("GET", f"/api/super/tenants/{tid}/detail", token=SUPER)
    check("detail tenant", st == 200 and r["kode"] == KODE, str(r))

    # ── 4. Buat admin tenant ──
    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin Super", "username": "admsuper",
                 "password": "admsuper123"}, token=SUPER)
    check("buat admin tenant", st == 201, str(r))

    st, r = req("GET", f"/api/super/tenants/{tid}/admins", token=SUPER)
    check("list admin tenant", st == 200 and len(r) == 1, str(r))

    # ── 5. Login admin tenant baru ──
    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admsuper",
                 "password": "admsuper123"})
    check("login admin tenant baru", st == 200, str(r))

    # ── 6. GlobalSetting nama_aplikasi ──
    st, r = req("GET", "/api/super/settings", token=SUPER)
    check("get settings", st == 200 and "nama_aplikasi" in r, str(r))
    old_nama = r["nama_aplikasi"]

    st, r = req("PUT", "/api/super/settings",
                {"nama_aplikasi": "Aplikasi Madrasah Test", "maintenance": False},
                token=SUPER)
    check("update nama_aplikasi", st == 200
          and r["nama_aplikasi"] == "Aplikasi Madrasah Test", str(r))

    st, r = req("GET", "/api/super/settings", token=SUPER)
    check("get settings updated", st == 200
          and r["nama_aplikasi"] == "Aplikasi Madrasah Test", str(r))

    # ── 7. Branding public ──
    st, r = req("GET", "/api/super/branding")
    check("branding public", st == 200 and r["nama"] == "Aplikasi Madrasah Test",
          str(r))

    # ── 8. User superadmin (me) ──
    st, r = req("GET", "/api/auth/me", token=SUPER)
    check("me superadmin", st == 200 and r["role"] == "super_admin", str(r))

    # ── 9. Dashboard superadmin ──
    st, r = req("GET", "/api/super/dashboard", token=SUPER)
    check("dashboard superadmin", st == 200 and r["tenant_total"] >= 1, str(r))

    # ── 10. Plans ──
    st, r = req("GET", "/api/super/plans", token=SUPER)
    check("list plans", st == 200 and len(r) >= 1, str(r))

    # ── 11. Reset password admin tenant ──
    st, r = req("POST", f"/api/super/tenants/{tid}/reset-password",
                {"username": "admsuper", "password": "admsuper456"}, token=SUPER)
    check("reset password admin", st == 200 and r["ok"], str(r))
    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admsuper",
                 "password": "admsuper456"})
    check("login dengan password baru", st == 200, str(r))

    # ── 12. Hapus tenant (kode konfirmasi) ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": "salah"},
                token=SUPER)
    check("hapus tenant kode salah → 400", st == 400, str(r))
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE},
                token=SUPER)
    check("hapus tenant", st == 200 and r["ok"], str(r))

    # ── 13. Balikkan nama_aplikasi ──
    st, r = req("PUT", "/api/super/settings", {"nama_aplikasi": old_nama},
                token=SUPER)
    check("balikkan nama_aplikasi", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
