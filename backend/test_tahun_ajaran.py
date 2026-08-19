#!/usr/bin/env python3
"""Tes Tahun Ajaran + Naik Kelas — tanpa pytest, mung urllib.

Jalanake: ./venv/bin/python test_tahun_ajaran.py
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8010"
KODE = f"tatajartest{int(time.time()) % 100000}"


def req(method, path, body=None, token=None, raw=False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            content = resp.read()
            return resp.status, content if raw else json.loads(content)
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

    # 0. Setup: super login → tenant tes + admin
    st, r = req("POST", "/api/auth/login-super",
                {"username": "superadmin", "password": "super123456"})
    check("login super", st == 200, str(r))
    SUPER = r["access_token"]

    st, r = req("POST", "/api/super/tenants",
                {"kode": KODE, "nama": "MTs Tes TA", "plan": "free"}, token=SUPER)
    check("gawe tenant tes", st == 201, str(r))
    tid = r["id"]

    st, r = req("POST", f"/api/super/tenants/{tid}/admin",
                {"nama": "Admin Tes", "username": "adminta", "password": "adminta123"},
                token=SUPER)
    check("gawe admin tenant", st == 201, str(r))

    st, r = req("POST", "/api/auth/login",
                {"kode_madrasah": KODE, "username": "adminta", "password": "adminta123"})
    check("login admin tenant", st == 200, str(r))
    T = r["access_token"]

    # 1. Tahun ajaran default (auto-seed)
    st, r = req("GET", "/api/tahun-ajaran", token=T)
    check("taun default 2025/2026 aktif",
          st == 200 and len(r) == 1 and r[0]["nama"] == "2025/2026"
          and r[0]["is_active"], str(r))
    TA1 = r[0]["id"]

    # 2. Gawe taun anyar → auto aktif
    st, r = req("POST", "/api/tahun-ajaran",
                {"nama": "2026/2027", "tanggal_mulai": "2026-07-01",
                 "tanggal_selesai": "2027-06-30"}, token=T)
    check("gawe taun anyar", st == 201 and r["is_active"], str(r))
    TA2 = r["id"]
    st, r = req("GET", "/api/tahun-ajaran", token=T)
    check("taun lawas ora aktif maneh",
          next(x["is_active"] for x in r if x["id"] == TA1) is False
          and next(x["is_active"] for x in r if x["id"] == TA2) is True, str(r))

    # 3. Kelas per taun — jeneng bisa dobel antar taun, ora ing taun padha
    st, r = req("POST", "/api/kelas", {"nama_kelas": "7A", "tahun_ajaran_id": TA1}, token=T)
    check("kelas 7A (2025/2026)", st == 201 and r["tahun_ajaran_nama"] == "2025/2026", str(r))
    k7a = r["id"]
    st, r = req("POST", "/api/kelas", {"nama_kelas": "9A", "tahun_ajaran_id": TA1}, token=T)
    check("kelas 9A (2025/2026)", st == 201, str(r))
    k9a = r["id"]
    st, r = req("POST", "/api/kelas", {"nama_kelas": "7A", "tahun_ajaran_id": TA2}, token=T)
    check("kelas 7A (2026/2027) — dobel jeneng antar taun OK", st == 201, str(r))
    st, r = req("POST", "/api/kelas", {"nama_kelas": "7A", "tahun_ajaran_id": TA2}, token=T)
    check("kelas dobel ing taun padha → 409", st == 409, str(r))

    # 4. Murid ing 7A lan 9A
    st, r = req("POST", "/api/murid", {"nis": "71101", "nama": "Siswa Naik",
                                       "kelas_id": k7a}, token=T)
    check("murid ing 7A", st == 201, str(r))
    st, r = req("POST", "/api/murid", {"nis": "91101", "nama": "Siswa Lulus",
                                       "kelas_id": k9a}, token=T)
    check("murid ing 9A", st == 201, str(r))

    # 5. Filter kelas per taun
    st, r = req("GET", f"/api/kelas?tahun_ajaran_id={TA1}", token=T)
    check("filter kelas taun 1", st == 200 and {k["nama_kelas"] for k in r} == {"7A", "9A"}, str(r))
    st, r = req("GET", f"/api/kelas?tahun_ajaran_id={TA2}", token=T)
    check("filter kelas taun 2", st == 200 and {k["nama_kelas"] for k in r} == {"7A"}, str(r))

    # 6. Naik Kelas: 7A→(gawe)8A taun 2, 9A→lulus
    st, r = req("POST", "/api/kelas/naik-kelas",
                {"tahun_ajaran_id": TA2, "items": [
                    {"dari_kelas_id": k7a, "ke_nama_kelas": "8A"},
                    {"dari_kelas_id": k9a, "luluskan": True},
                ]}, token=T)
    check("naik kelas: 7A→8A + 9A lulus",
          st == 200 and r["items"][0]["dipindah"] == 1
          and r["items"][1]["diluluskan"] == 1, str(r))

    # 7. Verifikasi: murid pindah + lulus
    st, r = req("GET", "/api/murid?q=Siswa%20Naik", token=T)
    check("murid saiki ing taun 2 (8A)",
          st == 200 and r["total"] == 1 and r["items"][0]["kelas_nama"] == "8A", str(r)[:160])
    st, r = req("GET", "/api/murid?q=Siswa%20Lulus&semua=true", token=T)
    check("murid lulus katon liwat semua=true",
          st == 200 and r["total"] == 1 and r["items"][0]["is_active"] is False, str(r)[:160])
    st, r = req("GET", "/api/murid?q=Siswa%20Lulus", token=T)
    check("murid lulus ilang saka daftar normal", st == 200 and r["total"] == 0, str(r))

    # 8. Kelas 8A otomatis digawe ing taun 2
    st, r = req("GET", f"/api/kelas?tahun_ajaran_id={TA2}", token=T)
    check("8A otomatis ana ing taun 2",
          st == 200 and "8A" in {k["nama_kelas"] for k in r}, str(r))

    # 9. Hapus taun sing isih nduwe kelas → 409
    st, r = req("DELETE", f"/api/tahun-ajaran/{TA2}", token=T)
    check("delete taun karo kelas → 409", st == 409, str(r))

    # 10. Admin bisa jadikake taun lawas aktif maneh
    st, r = req("PATCH", f"/api/tahun-ajaran/{TA1}", {"is_active": True}, token=T)
    check("aktifke taun lawas", st == 200 and r["is_active"], str(r))

    # ── cleanup: hapus tenant tes (backup wajib + kode konfirmasi) ──
    st, r = req("DELETE", f"/api/super/tenants/{tid}", {"kode": KODE}, token=SUPER)
    check("hapus tenant tes", st == 200, str(r))

    print(f"\n{'=' * 40}\nHASIL: {ok} pass, {fail} fail")


if __name__ == "__main__":
    main()
