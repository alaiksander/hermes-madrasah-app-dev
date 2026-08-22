#!/usr/bin/env python3
"""Tes Superadmin lanjutan — backup files (delete/get), tenant backup,
tenant restore (validasi saja, JANGAN restore data asli) — tanpa pytest.

Jalanake: ./venv/bin/python test_api_superadmin_lanjut.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8013"
KODE = f"suplanjut{int(time.time()) % 100000}"


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


def multipart(path, filename, content, token, ctype="application/octet-stream"):
    boundary = "----tarbeyatest"
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n").encode() + content + \
        f"\r\n--{boundary}--\r\n".encode()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}",
               "Authorization": f"Bearer {token}"}
    rq = urllib.request.Request(BASE + path, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(rq, timeout=20) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, e.read()


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

    # ── Login super ──
    st, r = req("POST", "/api/auth/login-super",
                {"username": "superadmin", "password": "super123456"})
    check("login super", st == 200, str(r))
    SUPER = r["access_token"]

    # ── Backup files: list ──
    st, r = req("GET", "/api/super/backup/files", token=SUPER)
    check("backup files list", st == 200 and isinstance(r, list), str(r)[:120])

    # ── Backup files GET/DELETE: nama tidak valid (regex) → 400 ──
    st, r = req("GET", "/api/super/backup/files/x.tar.gz.bak", token=SUPER)
    check("backup files get nama invalid → 400", st == 400, str(r)[:120])
    st, r = req("DELETE", "/api/super/backup/files/x.tar.gz.bak", token=SUPER)
    check("backup files delete nama invalid → 400", st == 400, str(r)[:120])

    # ── Backup files GET/DELETE: nama valid tapi tidak ada → 404 ──
    st, r = req("GET", "/api/super/backup/files/tidak-ada.tar.gz", token=SUPER)
    check("backup files get tidak ada → 404", st == 404, str(r)[:120])
    st, r = req("DELETE", "/api/super/backup/files/tidak-ada.tar.gz", token=SUPER)
    check("backup files delete tidak ada → 404", st == 404, str(r)[:120])

    # ── Buat tenant test untuk backup/restore ──
    st, r = req("POST", "/api/super/tenants",
                {"kode": KODE, "nama": "MTs Tes Super Lanjut", "plan": "free"},
                token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin SupL", "username": "admsupl",
                 "password": "admsupl123"}, token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "admsupl",
                 "password": "admsupl123"})
    check("login admin tenant", st == 200, str(r))
    T = r["access_token"]

    # ── Isi data tenant test (kelas + murid) supaya restore punya konflik ──
    st, r = req("GET", "/api/tahun-ajaran", token=T)
    TA = r[0]["id"]
    st, r = req("POST", "/api/kelas", {"nama_kelas": "7A", "tahun_ajaran_id": TA},
                token=T)
    check("buat kelas 7A", st == 201, str(r))
    k7 = r["id"]
    st, r = req("POST", "/api/murid",
                {"nisn": "2400000001", "nama": "Siswa SupL", "kelas_id": k7},
                token=T)
    check("buat murid", st == 201, str(r))

    # ── GET /api/super/tenants/{id}/backup (tenant test) ──
    st, r = req("GET", f"/api/super/tenants/{tid}/backup", token=SUPER, raw=True)
    check("tenant backup", st == 200 and isinstance(r, bytes) and len(r) > 0,
          f"st={st} len={len(r) if isinstance(r, bytes) else r}")
    backup_json = r if isinstance(r, bytes) else b"{}"

    # ── GET backup tenant tidak ada → 404 ──
    st, r = req("GET", "/api/super/tenants/999999/backup", token=SUPER)
    check("tenant backup tidak ada → 404", st == 404, str(r)[:120])

    # ── POST restore: file bukan JSON valid → 400 ──
    st, r = multipart(f"/api/super/tenants/{tid}/restore", "x.json",
                      b"not-json", SUPER, "application/json")
    check("restore bukan JSON → 400", st == 400, str(r)[:120])

    # ── POST restore: format tidak dikenali → 400 ──
    st, r = multipart(f"/api/super/tenants/{tid}/restore", "x.json",
                      json.dumps({"format": "salah"}).encode(), SUPER,
                      "application/json")
    check("restore format salah → 400", st == 400, str(r)[:120])

    # ── POST restore: tenant sudah ada data, tanpa force → 409 ──
    st, r = multipart(f"/api/super/tenants/{tid}/restore", "x.json",
                      backup_json, SUPER, "application/json")
    check("restore tanpa force (ada data) → 409", st == 409, str(r)[:120])

    # ── POST restore: tenant tidak ada → 404 ──
    st, r = multipart("/api/super/tenants/999999/restore", "x.json",
                      backup_json, SUPER, "application/json")
    check("restore tenant tidak ada → 404", st == 404, str(r)[:120])

    # ── Cleanup ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE}, token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
