"""Dashboard superadmin — statistik platform."""
from fastapi import APIRouter, Depends, Request

from ....core.client import api_get
from ....core.deps import require_super_admin_web
from ....core.templates import templates

router = APIRouter()


@router.get("/dashboard")
async def superadmin_dashboard(
    request: Request,
    user: dict = Depends(require_super_admin_web),
):
    """Dashboard superadmin: ringkasan platform."""
    # Tenant list (untuk statistik)
    tenants_r = await api_get(request, "/api/super/tenants")
    tenants = tenants_r.json() if tenants_r.status_code == 200 else []

    # Dashboard stats dari API existing
    dash_r = await api_get(request, "/api/super/dashboard")
    dash = dash_r.json() if dash_r.status_code == 200 else {}

    # Server status
    server_r = await api_get(request, "/api/super/server-status")
    server = server_r.json() if server_r.status_code == 200 else {}

    # Alert status
    alerts_r = await api_get(request, "/api/super/alerts/status")
    alerts = alerts_r.json() if alerts_r.status_code == 200 else {}

    # Aktivitas tenant (ringkas untuk stat card)
    akt_r = await api_get(request, "/api/super/tenant-aktivitas")
    aktivitas = akt_r.json() if akt_r.status_code == 200 else {}

    return templates.TemplateResponse(
        request,
        "superadmin/dashboard.html",
        {
            "user": user,
            "tenants": tenants,
            "dash": dash,
            "server": server,
            "alerts": alerts,
            "aktivitas": aktivitas,
        },
    )
