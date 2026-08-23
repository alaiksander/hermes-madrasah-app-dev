#!/usr/bin/env python3
"""Tes Superadmin ops — dashboard, branding, settings, plans, server-status,
audit, tenant-aktivitas, alerts, backup (config/files), logo — tanpa pytest.

Jalanake: ./venv/bin/python test_api_superadmin.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"apisup{int(time.time()) % 100000}"


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

    # ── 1. Login super admin ──
    st, r = req("POST", "/api/auth/login-super",
                {"username": "superadmin", "password": "super123456"})
    check("login super", st == 200 and r["role"] == "super_admin", str(r))
    SUPER = r["access_token"]

    # ── 2. Dashboard ──
    st, r = req("GET", "/api/super/dashboard", token=SUPER)
    check("dashboard", st == 200 and r["tenant_total"] >= 1, str(r)[:120])

    # ── 3. Branding public ──
    st, r = req("GET", "/api/super/branding")
    check("branding public", st == 200 and "nama" in r, str(r))

    # ── 4. Settings ──
    st, r = req("GET", "/api/super/settings", token=SUPER)
    check("get settings", st == 200 and "nama_aplikasi" in r, str(r))
    old_nama = r["nama_aplikasi"]
    st, r = req("PUT", "/api/super/settings",
                {"nama_aplikasi": "Aplikasi Super Test", "maintenance": False},
                token=SUPER)
    check("put settings", st == 200 and r["nama_aplikasi"] == "Aplikasi Super Test",
          str(r))
    st, r = req("PUT", "/api/super/settings", {"nama_aplikasi": old_nama},
                token=SUPER)
    check("balikkan settings", st == 200, str(r))

    # ── 5. Plans ──
    st, r = req("GET", "/api/super/plans", token=SUPER)
    check("list plans", st == 200 and len(r) >= 1, str(r)[:120])

    # ── 6. Server status ──
    st, r = req("GET", "/api/super/server-status", token=SUPER)
    check("server-status", st == 200 and "ram" in r, str(r)[:120])

    # ── 7. Audit ──
    st, r = req("GET", "/api/super/audit", token=SUPER)
    check("audit", st == 200 and "items" in r, str(r)[:120])
    st, r = req("GET", "/api/super/audit/tenant", token=SUPER)
    check("audit/tenant", st == 200 and "items" in r, str(r)[:120])

    # ── 8. Tenant aktivitas ──
    st, r = req("GET", "/api/super/tenant-aktivitas", token=SUPER)
    check("tenant-aktivitas", st == 200 and "items" in r, str(r)[:120])

    # ── 9. Alerts status ──
    st, r = req("GET", "/api/super/alerts/status", token=SUPER)
    check("alerts/status", st == 200, str(r)[:120])

    # ── 10. Backup info + files ──
    st, r = req("GET", "/api/super/backup", token=SUPER)
    check("backup info", st == 200 and "config" in r, str(r)[:120])
    st, r = req("GET", "/api/super/backup/files", token=SUPER)
    check("backup files", st == 200 and isinstance(r, list), str(r)[:120])

    # ── 11. Backup config (PUT) ──
    st, r = req("PUT", "/api/super/backup/config",
                {"enabled": False, "jam": "02:00", "retensi": 14}, token=SUPER)
    check("backup config", st == 200 and r["ok"], str(r))

    # ── 12. Alerts check + test (jangan kirim ke data asli — cek status) ──
    st, r = req("POST", "/api/super/alerts/check", token=SUPER)
    check("alerts/check", st == 200, str(r)[:120])
    st, r = req("POST", "/api/super/alerts/test", token=SUPER)
    check("alerts/test", st == 200, str(r)[:120])

    # ── 13. Plans CRUD (buat plan test, patch, delete) ──
    plan_nama = f"plan{int(time.time()) % 100000}"
    st, r = req("POST", "/api/super/plans",
                {"nama": plan_nama, "label": "Plan Test", "max_murid": 10,
                 "max_guru": 5, "fitur": ["a", "b"]}, token=SUPER)
    check("buat plan", st == 201 and r["nama"] == plan_nama, str(r))
    plan_id = r["id"]
    st, r = req("PATCH", f"/api/super/plans/{plan_id}", {"label": "Plan Test Baru"},
                token=SUPER)
    check("patch plan", st == 200 and r["label"] == "Plan Test Baru", str(r))
    st, r = req("DELETE", f"/api/super/plans/{plan_id}", token=SUPER)
    check("delete plan", st == 200 and r["ok"], str(r))

    # ── 14. Logo settings (upload/delete/get) ──
    # upload logo PNG dummy
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    boundary = "----tarbeyatest"
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="logo.png"\r\n'
            f"Content-Type: image/png\r\n\r\n").encode() + png + \
        f"\r\n--{boundary}--\r\n".encode()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}",
               "Authorization": f"Bearer {SUPER}"}
    rq = urllib.request.Request(BASE + "/api/super/settings/logo", data=body,
                                headers=headers, method="POST")
    try:
        with urllib.request.urlopen(rq, timeout=20) as resp:
            st = resp.status
            r = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        st = e.code
        r = e.read()
    check("upload logo", st == 200 and r.get("ok"), str(r)[:120])

    st, r = req("GET", "/api/super/settings/logo", raw=True)
    check("get logo", st == 200 and isinstance(r, bytes) and len(r) > 0,
          f"st={st} len={len(r) if isinstance(r, bytes) else r}")

    st, r = req("DELETE", "/api/super/settings/logo", token=SUPER)
    check("delete logo", st == 200 and r["ok"], str(r))

    # ── 15. Endpoint berbahaya — cek hanya ada (jangan jalankan ke data asli) ──
    # backup/run: jangan jalankan — cek validasi (body kosong → 422/405)
    st, r = req("POST", "/api/super/backup/run", token=SUPER)
    check("backup/run endpoint ada (tidak 404)", st != 404, f"st={st} {str(r)[:80]}")
    # restore: cek validasi nama_file tidak valid → 400 (bukan jalankan restore)
    st, r = req("POST", "/api/super/backup/restore", {"nama_file": "x.tar.gz"},
                token=SUPER)
    check("backup/restore validasi (bukan 500)", st in (400, 404),
          f"st={st} {str(r)[:80]}")
    # upload: cek validasi magic bytes (bukan gzip → 400)
    boundary = "----tarbeyatest"
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="x.tar.gz"\r\n'
            f"Content-Type: application/gzip\r\n\r\n").encode() + b"notgzip" + \
        f"\r\n--{boundary}--\r\n".encode()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}",
               "Authorization": f"Bearer {SUPER}"}
    rq = urllib.request.Request(BASE + "/api/super/backup/upload", data=body,
                                headers=headers, method="POST")
    try:
        with urllib.request.urlopen(rq, timeout=20) as resp:
            st = resp.status
            r = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        st = e.code
        r = e.read()
    check("backup/upload validasi (bukan 500)", st == 400, f"st={st} {str(r)[:80]}")

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
