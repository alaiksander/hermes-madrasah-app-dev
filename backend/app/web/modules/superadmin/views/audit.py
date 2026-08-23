"""Audit global superadmin — semua log di semua tenant."""
from fastapi import APIRouter, Depends, Query, Request, Response

from ....core.client import api_get, api_get_raw
from ....core.deps import require_super_admin_web
from ....core.templates import templates

router = APIRouter()


@router.get("/audit")
async def superadmin_audit(
    request: Request,
    tanggal_dari: str | None = None,
    tanggal_sampai: str | None = None,
    tenant: str | None = None,
    offset: int = Query(0),
    user: dict = Depends(require_super_admin_web),
):
    """Halaman audit trail global (semua tenant) untuk superadmin."""
    params = {"limit": 50, "offset": offset}
    if tanggal_dari:
        params["tanggal_dari"] = tanggal_dari
    if tanggal_sampai:
        params["tanggal_sampai"] = tanggal_sampai

    r = await api_get(request, "/api/super/audit", **params)
    data = r.json() if r.status_code == 200 else {"total": 0, "items": []}
    items = data.get("items", [])
    total = data.get("total", 0)

    # Filter client-side by tenant (data ringan, max 50/halaman)
    if tenant:
        items = [i for i in items if tenant in (i.get("tenant") or "")]

    return templates.TemplateResponse(
        request,
        "superadmin/audit.html",
        {
            "user": user,
            "items": items,
            "total": total,
            "offset": offset,
            "limit": 50,
            "has_next": offset + len(items) < total,
            "has_prev": offset > 0,
            "tanggal_dari": tanggal_dari or "",
            "tanggal_sampai": tanggal_sampai or "",
            "tenant": tenant or "",
        },
    )


def _audit_export_params(tanggal_dari: str | None,
                         tanggal_sampai: str | None,
                         tenant: str | None) -> dict:
    params = {}
    if tanggal_dari:
        params["tanggal_dari"] = tanggal_dari
    if tanggal_sampai:
        params["tanggal_sampai"] = tanggal_sampai
    if tenant:
        params["tenant"] = tenant
    return params


@router.get("/audit/export.csv")
async def superadmin_audit_export_csv(
    request: Request,
    tanggal_dari: str | None = None,
    tanggal_sampai: str | None = None,
    tenant: str | None = None,
    _: dict = Depends(require_super_admin_web),
):
    """Export audit trail global ke CSV (forward ke API)."""
    content = await api_get_raw(request, "/api/super/audit/export.csv",
                                **_audit_export_params(
                                    tanggal_dari, tanggal_sampai, tenant))
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit.csv"'},
    )


@router.get("/audit/export.xlsx")
async def superadmin_audit_export_xlsx(
    request: Request,
    tanggal_dari: str | None = None,
    tanggal_sampai: str | None = None,
    tenant: str | None = None,
    _: dict = Depends(require_super_admin_web),
):
    """Export audit trail global ke Excel (forward ke API)."""
    content = await api_get_raw(request, "/api/super/audit/export.xlsx",
                                **_audit_export_params(
                                    tanggal_dari, tanggal_sampai, tenant))
    return Response(
        content=content,
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"),
        headers={"Content-Disposition": 'attachment; filename="audit.xlsx"'},
    )