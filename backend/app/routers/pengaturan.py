"""Pengaturan madrasah (per-tenant): jam masuk/pulang + hari aktif."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..deps import get_tenant_db, require_permission
from ..models import Pengaturan
from ..schemas import PengaturanOut, PengaturanUpdate

router = APIRouter(prefix="/api/pengaturan", tags=["pengaturan"])

KEY_JAM_MASUK = "jam_masuk"
KEY_JAM_PULANG = "jam_pulang"
KEY_HARI_AKTIF = "hari_aktif"
KEY_NAMA_APLIKASI = "nama_aplikasi"
KEY_SCAN_MODE = "scan_mode"
KEY_SCAN_IDLE = "scan_idle_menit"
KEY_SCAN_AKTIF = "scan_aktif_detik"

DEFAULTS: dict[str, str] = {
    KEY_JAM_MASUK: "07:00",
    KEY_JAM_PULANG: "13:30",
    KEY_HARI_AKTIF: "1,2,3,4,5",
    KEY_NAMA_APLIKASI: "Aplikasi Madrasah",
    KEY_SCAN_MODE: "standar",
    KEY_SCAN_IDLE: "5",
    KEY_SCAN_AKTIF: "30",
}


def get_pengaturan(db: Session) -> dict:
    """Baca setelan madrasah (default yen durung ana)."""
    rows = {p.key: p.value for p in db.query(Pengaturan).all()}
    return {
        "jam_masuk": rows.get(KEY_JAM_MASUK, DEFAULTS[KEY_JAM_MASUK]),
        "jam_pulang": rows.get(KEY_JAM_PULANG, DEFAULTS[KEY_JAM_PULANG]),
        "hari_aktif": [int(d) for d in rows.get(KEY_HARI_AKTIF, DEFAULTS[KEY_HARI_AKTIF]).split(",") if d],
        "nama_aplikasi": rows.get(KEY_NAMA_APLIKASI, DEFAULTS[KEY_NAMA_APLIKASI]),
        "scan_mode": rows.get(KEY_SCAN_MODE, DEFAULTS[KEY_SCAN_MODE]),
        "scan_idle_menit": int(rows.get(KEY_SCAN_IDLE, DEFAULTS[KEY_SCAN_IDLE])),
        "scan_aktif_detik": int(rows.get(KEY_SCAN_AKTIF, DEFAULTS[KEY_SCAN_AKTIF])),
    }


def set_pengaturan(db: Session, data: PengaturanUpdate) -> None:
    """Simpen mung field sing dikirim (partial update)."""
    keys = {
        "jam_masuk": KEY_JAM_MASUK,
        "jam_pulang": KEY_JAM_PULANG,
        "hari_aktif": KEY_HARI_AKTIF,
        "nama_aplikasi": KEY_NAMA_APLIKASI,
        "scan_mode": KEY_SCAN_MODE,
        "scan_idle_menit": KEY_SCAN_IDLE,
        "scan_aktif_detik": KEY_SCAN_AKTIF,
    }
    for field, key in keys.items():
        if field not in data.model_fields_set:
            continue
        value = getattr(data, field)
        if field == "hari_aktif":
            value = ",".join(str(d) for d in value)
        row = db.get(Pengaturan, key)
        if row:
            row.value = value
        else:
            db.add(Pengaturan(key=key, value=value))
    db.commit()


@router.get("", response_model=PengaturanOut)
def pengaturan_get(db: Session = Depends(get_tenant_db),
                   _: dict = Depends(require_permission("pengaturan.view", "pengaturan.update"))):
    return PengaturanOut(**get_pengaturan(db))


@router.put("", response_model=PengaturanOut)
def pengaturan_put(data: PengaturanUpdate,
                   db: Session = Depends(get_tenant_db),
                   _: dict = Depends(require_permission("pengaturan.update"))):
    set_pengaturan(db, data)
    return PengaturanOut(**get_pengaturan(db))
