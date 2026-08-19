"""Modul web superadmin — panel manajemen platform.

Prefix: /superadmin (di-mount di /madrasah-app/superadmin)
Semua endpoint WAJIB pakai require_super_admin_web (bukan require_admin_web)
supaya tenant admin TIDAK bisa akses.
"""
from fastapi import APIRouter

from .views import dashboard, tenants, audit, plans, settings, backup, alerts, aktivitas

router = APIRouter(prefix="/superadmin", tags=["web-superadmin"])

router.include_router(dashboard.router)
router.include_router(tenants.router)
router.include_router(audit.router)
router.include_router(plans.router)
router.include_router(settings.router)
router.include_router(backup.router)
router.include_router(alerts.router)
router.include_router(aktivitas.router)
