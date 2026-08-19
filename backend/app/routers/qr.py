"""QR Code: generate PNG + PDF (per murid / batch per kelas)"""
import io

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from ..deps import get_tenant_db, require_permission, require_roles
from ..models import Kelas, Murid

router = APIRouter(prefix="/api/murid", tags=["qr"])

PAGE_W, PAGE_H = A4
COLS, ROWS = 2, 5  # 10 kartu per halaman A4
MARGIN = 10 * mm
CELL_W = (PAGE_W - 2 * MARGIN) / COLS
CELL_H = (PAGE_H - 2 * MARGIN) / ROWS
# Zona teks 20mm: nama (1-2 baris) + kelas + NIS — semuanya SAMA
# (Helvetica-Bold 10, hitam) sesuai permintaan Mr. QR sedikit lebih kecil.
TEXT_ZONE = 20 * mm
QR_SIZE = min(CELL_W, CELL_H) - 22 * mm
NAME_MAX_LINES = 2


def _qr_image(qr_uuid: str) -> ImageReader:
    img = qrcode.make(qr_uuid, box_size=12, border=1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def _wrap_text(c: canvas.Canvas, text: str, font: str, size: float,
               max_width: float, max_lines: int = NAME_MAX_LINES) -> list[str]:
    """Wrap teks jadi maks N baris (word-boundary + ellipsis).

    drawCentredString TIDAK wrap — nama panjang overflow. Fungsi ini
    memecah kata per baris sesuai lebar sel, max 2 baris, baris
    terakhir ditambah '…' kalau masih kepanjangan.
    """
    words = text.split()
    lines: list[str] = []
    cur = ""
    truncated = False
    for w in words:
        test = f"{cur} {w}".strip()
        if c.stringWidth(test, font, size) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
        if len(lines) >= max_lines:
            truncated = True
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if lines and len(lines) == max_lines:
        # Cek masih ada sisa kata yang tidak masuk
        joined = " ".join(lines)
        truncated = truncated or joined != " ".join(words)

    # Baris terakhir + ellipsis HANYA kalau text masih kepanjangan
    if lines and truncated:
        last = lines[-1]
        while last and c.stringWidth(last + "…", font, size) > max_width:
            last = last[:-1]
        lines[-1] = last + "…" if last else "…"

    return [ln for ln in lines if ln]


def _balanced_lines(c: canvas.Canvas, text: str, font: str, size: float,
                    max_width: float) -> list[str]:
    """Pecah teks jadi 2 baris SEIMBANG (word-boundary).

    Dipakai untuk nama yang muat 1 baris TAPI terlalu memanjang (>68%
    lebar sel) — secara visual lebih rapi di 2 baris. Titik pecah dipilih
    agar selisih lebar kedua baris minimal.
    """
    words = text.split()
    if len(words) <= 1:
        return [text]
    best = None
    for i in range(1, len(words)):
        l1 = " ".join(words[:i])
        l2 = " ".join(words[i:])
        w1 = c.stringWidth(l1, font, size)
        w2 = c.stringWidth(l2, font, size)
        if w1 <= max_width and w2 <= max_width:
            diff = abs(w1 - w2)
            if best is None or diff < best[0]:
                best = (diff, l1, l2)
    if best:
        return [best[1], best[2]]
    return _wrap_text(c, text, font, size, max_width)


def _draw_card(c: canvas.Canvas, x: float, y_bottom: float, murid: Murid, kelas_nama: str) -> None:
    """Siji kartu: QR (tengah) + Nama/Kelas/NIS — semua SAMA (bold 10, hitam)."""
    qr_x = x + (CELL_W - QR_SIZE) / 2
    qr_y = y_bottom + TEXT_ZONE + (CELL_H - TEXT_ZONE - QR_SIZE) / 2
    c.drawImage(_qr_image(murid.qr_uuid), qr_x, qr_y, width=QR_SIZE, height=QR_SIZE)

    # Nama — 1 baris kalau pendek; 2 baris seimbang kalau memanjang (>68%)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("Helvetica-Bold", 10)
    max_name_w = CELL_W - 4 * mm
    if c.stringWidth(murid.nama, "Helvetica-Bold", 10) > max_name_w * 0.68:
        name_lines = _balanced_lines(c, murid.nama, "Helvetica-Bold", 10,
                                     max_name_w)
    else:
        name_lines = [murid.nama]

    # Semua baris: Nama (1-2) + Kelas + NISN — font & warna SAMA
    nisn_label = f"NISN: {murid.nisn}" if murid.nisn else ""
    lines = [ln for ln in (name_lines + [kelas_nama, nisn_label]) if ln]
    line_h = 4.2 * mm
    top = y_bottom + TEXT_ZONE - 1.5 * mm
    for i, ln in enumerate(reversed(lines)):
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(x + CELL_W / 2, top - i * line_h, ln)


def _qr_pdf(murids: list[Murid], kelas_nama: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"QR Card — {kelas_nama}")
    for i, m in enumerate(murids):
        col = i % COLS
        row = (i // COLS) % ROWS
        if col == 0 and row == 0 and i > 0:
            c.showPage()
        x = MARGIN + col * CELL_W
        y_bottom = PAGE_H - MARGIN - (row + 1) * CELL_H
        _draw_card(c, x, y_bottom, m, kelas_nama)
    c.save()
    return buf.getvalue()


@router.get("/qr-pdf.pdf", response_class=Response)
def qr_pdf_per_kelas(kelas_id: int = Query(...),
                     db: Session = Depends(get_tenant_db),
                     _: dict = Depends(require_permission("murid.qr"))):
    """PDF QR Card batch: kabeh murid aktif siji kelas (10 kartu/halaman A4)."""
    kelas = db.get(Kelas, kelas_id)
    if not kelas:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kelas tidak ditemukan")
    murids = (db.query(Murid).filter(Murid.kelas_id == kelas_id,
                                     Murid.is_active.is_(True))
              .order_by(Murid.nisn).all())
    if not murids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Tidak ada murid aktif di kelas ini")
    fname = f"qr-{kelas.nama_kelas.replace(' ', '-')}.pdf"
    return Response(content=_qr_pdf(murids, kelas.nama_kelas),
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/{murid_id}/qr.pdf", response_class=Response)
def qr_pdf_per_murid(murid_id: int,
                     db: Session = Depends(get_tenant_db),
                     _: dict = Depends(require_permission("murid.qr"))):
    """PDF QR Card siji murid."""
    m = db.get(Murid, murid_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Murid tidak ditemukan")
    kelas = db.get(Kelas, m.kelas_id)
    return Response(content=_qr_pdf([m], kelas.nama_kelas if kelas else "-"),
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="qr-{m.nisn or m.id}.pdf"'})


@router.get("/{murid_id}/qr.png", response_class=Response)
def murid_qr_png(murid_id: int,
                 db: Session = Depends(get_tenant_db),
                 _: dict = Depends(require_permission("murid.qr", "absen.scan", "absen.manual"))):
    """PNG QR Card murid — isi cuma UUID, ora ana data pribadi."""
    m = db.get(Murid, murid_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Murid tidak ditemukan")

    img = qrcode.make(m.qr_uuid, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Content-Disposition": f'inline; filename="qr-{m.nisn or m.id}.png"'})
