"""Modul Absensi — router utama untuk semua endpoint web modul absensi.

Sub-path: /madrasah-app/absensi/<path>
BK dipisah ke /madrasah-app/bk/<path> (modul terpisah, lihat bk_web_router).
Jurnal dipisah ke /madrasah-app/jurnal/<path> (modul terpisah, lihat jurnal_web_router).
Data dipisah ke /madrasah-app/data/<path> (modul terpisah, lihat data_web_router).
"""
from fastapi import APIRouter

from .views import cetak_absen, dashboard, input_manual, kartu_qr, rekap

router = APIRouter(prefix="/absensi", tags=["web-absensi"])

# Sub-modul yang MASIH di bawah /madrasah-app/absensi/...
router.include_router(dashboard.router)
router.include_router(rekap.router)
router.include_router(input_manual.router)
router.include_router(kartu_qr.router)
router.include_router(cetak_absen.router)
# NB: `pengaturan`, `role` (akan pindah ke /madrasah-app/system/ di task System)
# `bk`, `murid`, `kelas`, `guru`, `tahun-ajaran` sudah dipisah ke router sendiri.

# ── Router Pengampu terpisah (modul sendiri di /madrasah-app/pengampu/)
from .views import pengampu as pengampu_views
pengampu_web_router = APIRouter(tags=["web-pengampu"])
pengampu_web_router.include_router(pengampu_views.router)

# ── Router BK terpisah (modul sendiri di /madrasah-app/bk/)
from .views import bk as bk_views
bk_web_router = APIRouter(tags=["web-bk"])
bk_web_router.include_router(bk_views.router)

# ── Router Jurnal terpisah (modul sendiri di /madrasah-app/jurnal/)
from .views import jurnal as jurnal_views
jurnal_web_router = APIRouter(tags=["web-jurnal"])
jurnal_web_router.include_router(jurnal_views.router)

# ── Router Data (sub-modul) di-include terpisah di main.py
# dengan prefix per-sub: /madrasah-app/data/murid, /data/kelas, dll.
# Tiap view tetap tanpa prefix di sini (lihat views/murid.py dst.).