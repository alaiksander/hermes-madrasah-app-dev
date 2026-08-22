"""Modul Absensi — router utama untuk semua endpoint web modul absensi.

Sub-path: /apps/absensi/<path>
BK dipisah ke /apps/bk/<path> (modul terpisah, lihat bk_web_router).
Jurnal dipisah ke /apps/jurnal/<path> (modul terpisah, lihat jurnal_web_router).
Data dipisah ke /apps/data/<path> (modul terpisah, lihat data_web_router).
"""
from fastapi import APIRouter

from .views import cetak_absen, dashboard, input_manual, kartu_qr, rekap

router = APIRouter(prefix="/absensi", tags=["web-absensi"])

# Sub-modul yang MASIH di bawah /apps/absensi/...
router.include_router(dashboard.router)
router.include_router(rekap.router)
router.include_router(input_manual.router)
router.include_router(kartu_qr.router)
router.include_router(cetak_absen.router)
# NB: `pengaturan`, `role` (akan pindah ke /apps/system/ di task System)
# `bk`, `murid`, `kelas`, `guru`, `tahun-ajaran` sudah dipisah ke router sendiri.

# ── Router Pengampu terpisah (modul sendiri di /apps/pengampu/)
from .views import pengampu as pengampu_views
pengampu_web_router = APIRouter(tags=["web-pengampu"])
pengampu_web_router.include_router(pengampu_views.router)

# ── Router BK terpisah (modul sendiri di /apps/bk/)
from .views import bk as bk_views
bk_web_router = APIRouter(tags=["web-bk"])
bk_web_router.include_router(bk_views.router)

# ── Router Jurnal terpisah (modul sendiri di /apps/jurnal/)
from .views import jurnal as jurnal_views
jurnal_web_router = APIRouter(tags=["web-jurnal"])
jurnal_web_router.include_router(jurnal_views.router)

# ── Router Data (sub-modul) di-include terpisah di main.py
# dengan prefix per-sub: /apps/data/murid, /data/kelas, dll.
# Tiap view tetap tanpa prefix di sini (lihat views/murid.py dst.).