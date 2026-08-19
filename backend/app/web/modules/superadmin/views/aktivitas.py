"""Aktivitas Tenant — superadmin lihat tenant paling aktif / tidak aktif."""
from fastapi import APIRouter, Depends, Request

from ....core.client import api_get
from ....core.deps import require_super_admin_web
from ....core.templates import templates

router = APIRouter()


@router.get("/aktivitas")
async def aktivitas_page(
    request: Request,
    user: dict = Depends(require_super_admin_web),
):
    """Halaman Aktivitas Tenant."""
    r = await api_get(request, "/api/super/tenant-aktivitas")
    data = r.json() if r.status_code == 200 else {"items": [], "ringkas": {}}

    # Urutkan: yang paling baru aktif di atas
    def sort_key(item):
        return item.get("last_active_at") or ""

    items = sorted(data.get("items", []), key=sort_key, reverse=True)

    return templates.TemplateResponse(
        request,
        "superadmin/aktivitas.html",
        {
            "user": user,
            "items": items,
            "ringkas": data.get("ringkas", {}),
            "ambang": data.get("ambang", 14),
        },
    )