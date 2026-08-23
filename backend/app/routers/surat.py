"""Router Surat Menyurat — modul Tata Usaha.

Arsip surat masuk/keluar + disposisi. Lampiran = link URL (Google Drive dll),
dirender sebagai iframe embed di detail view. Permission-driven.
"""
from datetime import date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..audit import log_action
from ..deps import get_tenant_db, require_permission
from ..models import Surat
from ..xlsx_utils import XLSX_MIME, rows_to_xlsx

router = APIRouter(prefix="/api/surat", tags=["Surat Menyurat"])
WIB = ZoneInfo("Asia/Jakarta")


class SuratCreate(BaseModel):
    jenis: str  # masuk | keluar
    nomor_agenda: str
    tanggal: date
    dari_kepada: str
    perihal: str
    isi: str | None = None
    lampiran: str | None = None  # URL link (Google Drive dll)
    status: str = "draft"
    disposisi_kepada: str | None = None
    disposisi_catatan: str | None = None


class SuratUpdate(BaseModel):
    jenis: str | None = None
    nomor_agenda: str | None = None
    tanggal: str | None = None
    dari_kepada: str | None = None
    perihal: str | None = None
    isi: str | None = None
    lampiran: str | None = None
    status: str | None = None
    disposisi_kepada: str | None = None
    disposisi_catatan: str | None = None


class DisposisiCreate(BaseModel):
    kepada: str
    catatan: str | None = None


def _validate_url(url: str | None) -> str | None:
    """Lampiran harus URL http(s):// (bukan path lokal)."""
    if not url:
        return None
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(400, "Lampiran harus berupa link http(s)://")
    if len(url) > 500:
        raise HTTPException(400, "Link lampiran maksimal 500 karakter")
    return url


def _surat_out(s: Surat) -> dict:
    return {
        "id": s.id,
        "jenis": s.jenis,
        "nomor_agenda": s.nomor_agenda,
        "tanggal": s.tanggal.isoformat(),
        "dari_kepada": s.dari_kepada,
        "perihal": s.perihal,
        "isi": s.isi,
        "lampiran": s.lampiran,
        "status": s.status,
        "disposisi_kepada": s.disposisi_kepada,
        "disposisi_catatan": s.disposisi_catatan,
        "created_by": s.created_by,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("")
def surat_list(
    jenis: str | None = Query(None, description="masuk | keluar"),
    status: str | None = Query(None),
    q: str | None = Query(None, description="cari perihal/dari/nomor"),
    db: Session = Depends(get_tenant_db),
    _: dict = Depends(require_permission("surat.view")),
):
    query = db.query(Surat)
    if jenis:
        query = query.filter(Surat.jenis == jenis)
    if status:
        query = query.filter(Surat.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Surat.perihal.ilike(like)) | (Surat.dari_kepada.ilike(like))
            | (Surat.nomor_agenda.ilike(like)))
    surat = query.order_by(Surat.tanggal.desc(), Surat.id.desc()).all()
    return [_surat_out(s) for s in surat]


@router.post("")
def surat_create(
    data: SuratCreate,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("surat.create")),
):
    surat = Surat(
        jenis=data.jenis,
        nomor_agenda=data.nomor_agenda,
        tanggal=data.tanggal,
        dari_kepada=data.dari_kepada,
        perihal=data.perihal,
        isi=data.isi,
        lampiran=_validate_url(data.lampiran),
        status=data.status,
        disposisi_kepada=data.disposisi_kepada,
        disposisi_catatan=data.disposisi_catatan,
        created_by=user.get("id"),
    )
    db.add(surat)
    db.commit()
    db.refresh(surat)
    log_action(user, f"surat_create {surat.nomor_agenda}")
    return _surat_out(surat)


@router.get("/export.xlsx", response_class=Response)
def surat_export(
    jenis: str | None = Query(None),
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("surat.export")),
):
    """Export daftar surat ke Excel."""
    query = db.query(Surat)
    if jenis:
        query = query.filter(Surat.jenis == jenis)
    surat = query.order_by(Surat.tanggal.desc()).all()
    rows = [[s.nomor_agenda, s.tanggal.isoformat(), s.jenis,
             s.dari_kepada, s.perihal, s.status, s.disposisi_kepada or ""]
            for s in surat]
    xlsx = rows_to_xlsx(
        ["No. Agenda", "Tanggal", "Jenis", "Dari/Kepada", "Perihal",
         "Status", "Disposisi"], rows)
    log_action(user, f"surat_export ({len(surat)} surat)")
    return Response(content=xlsx, media_type=XLSX_MIME,
                    headers={"Content-Disposition": 'attachment; filename="surat.xlsx"'})


@router.get("/{surat_id}")
def surat_detail(
    surat_id: int,
    db: Session = Depends(get_tenant_db),
    _: dict = Depends(require_permission("surat.view")),
):
    s = db.get(Surat, surat_id)
    if not s:
        raise HTTPException(404, "Surat tidak ditemukan")
    return _surat_out(s)


@router.patch("/{surat_id}")
def surat_update(
    surat_id: int,
    data: SuratUpdate,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("surat.update")),
):
    s = db.get(Surat, surat_id)
    if not s:
        raise HTTPException(404, "Surat tidak ditemukan")
    upd = data.model_dump(exclude_unset=True)
    if "tanggal" in upd and upd["tanggal"]:
        upd["tanggal"] = date.fromisoformat(upd["tanggal"])
    if "lampiran" in upd:
        upd["lampiran"] = _validate_url(upd["lampiran"])
    for k, v in upd.items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    log_action(user, f"surat_update {s.nomor_agenda}")
    return _surat_out(s)


@router.delete("/{surat_id}")
def surat_delete(
    surat_id: int,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("surat.delete")),
):
    s = db.get(Surat, surat_id)
    if not s:
        raise HTTPException(404, "Surat tidak ditemukan")
    db.delete(s)
    db.commit()
    log_action(user, f"surat_delete {s.nomor_agenda}")
    return {"ok": True}


@router.post("/{surat_id}/disposisi")
def surat_disposisi(
    surat_id: int,
    data: DisposisiCreate,
    db: Session = Depends(get_tenant_db),
    user: dict = Depends(require_permission("surat.disposisi")),
):
    s = db.get(Surat, surat_id)
    if not s:
        raise HTTPException(404, "Surat tidak ditemukan")
    s.disposisi_kepada = data.kepada
    s.disposisi_catatan = data.catatan
    db.commit()
    db.refresh(s)
    log_action(user, f"surat_disposisi {s.nomor_agenda} -> {data.kepada}")
    return _surat_out(s)
