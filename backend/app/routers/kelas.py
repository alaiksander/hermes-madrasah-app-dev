"""CRUD Kelas (per tenant) — tulis: admin; baca: guru/admin + Naik Kelas"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit import log_action
from ..deps import get_tenant_db, require_permission, require_roles
from ..models import Guru, Kelas, Murid, TahunAjaran
from ..schemas import (KelasCreate, KelasOut, KelasUpdate, NaikKelasItem,
                       NaikKelasRequest, PindahKelasRequest)

router = APIRouter(prefix="/api/kelas", tags=["kelas"])


def _tahun_aktif(db: Session) -> TahunAjaran | None:
    return db.query(TahunAjaran).filter(TahunAjaran.is_active.is_(True)).first()


def _to_out(k: Kelas, db: Session) -> KelasOut:
    jm = db.query(Murid).filter(Murid.kelas_id == k.id, Murid.is_active.is_(True)).count()
    t = db.get(TahunAjaran, k.tahun_ajaran_id) if k.tahun_ajaran_id else None
    wali = db.get(Guru, k.wali_guru_id) if k.wali_guru_id else None
    return KelasOut.model_validate(k).model_copy(update={
        "jumlah_murid": jm,
        "tahun_ajaran_nama": t.nama if t else None,
        "wali_guru_nama": wali.nama if wali else None,
    })


def _nama_dobel(db: Session, nama: str, tahun_id: int, skip_id: int | None = None) -> bool:
    q = db.query(Kelas).filter(Kelas.nama_kelas == nama,
                               Kelas.tahun_ajaran_id == tahun_id)
    if skip_id:
        q = q.filter(Kelas.id != skip_id)
    return q.first() is not None


@router.get("/wali-saya", response_model=list[KelasOut])
def kelas_wali_saya(user: dict = Depends(require_permission("kelas.view", "kelas.update", "kelas.naik", "kelas.delete")),
                    db: Session = Depends(get_tenant_db)):
    """Kelas sing wali-e user sing login (taun aktif).

    Mung kelas karo wali_guru_id == user.id — admin ora entuk kabeh kelas
    ing kene (kartu "Kelas Wali" ing Rekap mung kanggo guru wali).
    """
    t = _tahun_aktif(db)
    q = db.query(Kelas).filter(Kelas.wali_guru_id == user["id"])
    if t:
        q = q.filter(Kelas.tahun_ajaran_id == t.id)
    return [_to_out(k, db) for k in q.order_by(Kelas.nama_kelas).all()]


@router.get("/wali-saya/murid")
def kelas_wali_murid(
    user: dict = Depends(require_permission("kelas.view", "kelas.update", "kelas.naik", "kelas.delete", "wali.view")),
    db: Session = Depends(get_tenant_db)):
    """Daftar murid semua kelas wali user login (taun aktif) + ringkasan.

    Dipakai halaman Wali Kelas: per murid → {id, nama, nisn, kelas,
    status SP, alpa bulan ini}. Hanya kelas dengan wali_guru_id == user.id.
    """
    from datetime import date
    from ..models import (Absensi, BkCatatan, BkKategori, BkKonfigurasi,
                          BkPeserta)

    t = _tahun_aktif(db)
    q = db.query(Kelas).filter(Kelas.wali_guru_id == user["id"])
    if t:
        q = q.filter(Kelas.tahun_ajaran_id == t.id)
    kelas_list = q.order_by(Kelas.nama_kelas).all()
    if not kelas_list:
        return {"tahun_ajaran_nama": t.nama if t else None, "kelas": [], "murid": []}

    kelas_ids = [k.id for k in kelas_list]
    murids = (db.query(Murid)
              .filter(Murid.kelas_id.in_(kelas_ids), Murid.is_active.is_(True))
              .order_by(Murid.nama).all())
    murid_ids = [m.id for m in murids]

    # Alpa bulan ini per murid
    now = date.today()
    bulan_awal = now.replace(day=1)
    alpa_map: dict[int, int] = {}
    if murid_ids:
        for mid, in (db.query(Absensi.murid_id)
                     .filter(Absensi.murid_id.in_(murid_ids),
                             Absensi.tanggal >= bulan_awal,
                             Absensi.status == "alpa")
                     .all()):
            alpa_map[mid] = alpa_map.get(mid, 0) + 1

    # Status SP per murid (poin pelanggaran negatif)
    sp_map: dict[int, str] = {}
    if murid_ids:
        konfig = db.get(BkKonfigurasi, 1)
        poin_rows = (db.query(BkPeserta.murid_id,
                              BkKategori.jenis,
                              BkCatatan.poin_snapshot)
                     .join(BkCatatan, BkCatatan.id == BkPeserta.entitas_id)
                     .join(BkKategori, BkKategori.id == BkCatatan.kategori_id)
                     .filter(BkPeserta.murid_id.in_(murid_ids),
                             BkPeserta.entitas == "catatan",
                             BkKategori.jenis == "negatif")
                     .all())
        totals: dict[int, int] = {}
        for mid, _, poin in poin_rows:
            totals[mid] = totals.get(mid, 0) + (poin or 0)
        sp1 = konfig.threshold_sp1 if konfig else 50
        sp2 = konfig.threshold_sp2 if konfig else 100
        sp3 = konfig.threshold_sp3 if konfig else 150
        for mid, total in totals.items():
            if total >= sp3:
                sp_map[mid] = "SP 3"
            elif total >= sp2:
                sp_map[mid] = "SP 2"
            elif total >= sp1:
                sp_map[mid] = "SP 1"
            elif total > 0:
                sp_map[mid] = "Peringatan"

    kelas_nama = {k.id: k.nama_kelas for k in kelas_list}
    murid_out = [{
        "id": m.id, "nama": m.nama, "nisn": m.nisn,
        "kelas_id": m.kelas_id, "kelas_nama": kelas_nama.get(m.kelas_id),
        "alpa_bulan_ini": alpa_map.get(m.id, 0),
        "status_sp": sp_map.get(m.id, "Aman"),
    } for m in murids]

    return {
        "tahun_ajaran_nama": t.nama if t else None,
        "kelas": [{**{k: getattr(kls, k) for k in ("id", "nama_kelas")},
                   "jumlah_murid": sum(1 for m in murids if m.kelas_id == kls.id),
                   "wali_guru_nama": (db.get(Guru, kls.wali_guru_id).nama
                                      if kls.wali_guru_id else None)}
                  for kls in kelas_list],
        "murid": murid_out,
    }


@router.get("", response_model=list[KelasOut])
def list_kelas(tahun_ajaran_id: int | None = None,
               semua: bool = False,
               db: Session = Depends(get_tenant_db),
               _: dict = Depends(require_permission("kelas.view", "kelas.update", "kelas.naik", "kelas.delete"))):
    """Daftar kelas. `tahun_ajaran_id=X` filter taun; tanpa param = kabeh."""
    q = db.query(Kelas)
    if not semua and tahun_ajaran_id is not None:
        q = q.filter(Kelas.tahun_ajaran_id == tahun_ajaran_id)
    return [_to_out(k, db) for k in q.order_by(Kelas.nama_kelas).all()]


@router.post("", response_model=KelasOut, status_code=status.HTTP_201_CREATED)
def create_kelas(data: KelasCreate,
                 db: Session = Depends(get_tenant_db),
                 user: dict = Depends(require_permission("kelas.update", "kelas.naik", "kelas.delete"))):
    if data.tahun_ajaran_id is None:
        t = _tahun_aktif(db)
        if not t:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Buat tahun ajaran dulu di Pengaturan")
        tahun_id = t.id
    else:
        if not db.get(TahunAjaran, data.tahun_ajaran_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tahun ajaran tidak ditemukan")
        tahun_id = data.tahun_ajaran_id
    if _nama_dobel(db, data.nama_kelas, tahun_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Kelas sudah ada di tahun ini")
    if data.wali_guru_id and not db.get(Guru, data.wali_guru_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guru tidak ditemukan")
    k = Kelas(nama_kelas=data.nama_kelas, wali_guru_id=data.wali_guru_id,
              tahun_ajaran_id=tahun_id)
    db.add(k)
    db.commit()
    db.refresh(k)
    log_action(user, "tambah_kelas",
               f"Kelas '{k.nama_kelas}' ditambah (TA id={tahun_id}, wali_guru_id={data.wali_guru_id})")
    return _to_out(k, db)


@router.patch("/{kelas_id}", response_model=KelasOut)
def update_kelas(kelas_id: int, data: KelasUpdate,
                 db: Session = Depends(get_tenant_db),
                 user: dict = Depends(require_permission("kelas.update", "kelas.naik", "kelas.delete"))):
    k = db.get(Kelas, kelas_id)
    if not k:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kelas tidak ditemukan")
    changes = []
    if data.nama_kelas is not None:
        if _nama_dobel(db, data.nama_kelas, k.tahun_ajaran_id, skip_id=k.id):
            raise HTTPException(status.HTTP_409_CONFLICT, "Kelas sudah ada di tahun ini")
        if k.nama_kelas != data.nama_kelas:
            changes.append(f"nama '{k.nama_kelas}' → '{data.nama_kelas}'")
        k.nama_kelas = data.nama_kelas
    if "wali_guru_id" in data.model_fields_set:
        old = k.wali_guru_id
        new = data.wali_guru_id
        if old != new:
            changes.append(f"wali_guru {old} → {new}")
        k.wali_guru_id = new
    db.commit()
    db.refresh(k)
    if changes:
        log_action(user, "ubah_kelas",
                   f"Kelas id={kelas_id} ({k.nama_kelas}): {', '.join(changes)}")
    return _to_out(k, db)


@router.delete("/{kelas_id}")
def delete_kelas(kelas_id: int,
                 db: Session = Depends(get_tenant_db),
                 user: dict = Depends(require_permission("kelas.update", "kelas.naik", "kelas.delete"))):
    k = db.get(Kelas, kelas_id)
    if not k:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kelas tidak ditemukan")
    jm = db.query(Murid).filter(Murid.kelas_id == kelas_id, Murid.is_active.is_(True)).count()
    if jm > 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Kelas masih memiliki {jm} murid aktif — pindahkan dulu")
    nama = k.nama_kelas
    db.delete(k)
    db.commit()
    log_action(user, "hapus_kelas", f"Kelas '{nama}' (id={kelas_id}) dihapus")
    return {"ok": True}


@router.post("/naik-kelas")
def naik_kelas(data: NaikKelasRequest,
               db: Session = Depends(get_tenant_db),
               user: dict = Depends(require_permission("kelas.update", "kelas.naik", "kelas.delete"))):
    """Naik kelas massal berbasis tahun ajaran.

    Saben item: pindah kabeh murid aktif saka kelas sumber menyang kelas
    tujuan (taun anyar) — kelas tujuan digawe otomatis yen durung ana —
    utawa diluluskan (tetep ing kelas lawas, is_active=False).
    """
    tujuan = db.get(TahunAjaran, data.tahun_ajaran_id)
    if not tujuan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tahun ajaran tujuan tidak ditemukan")

    hasil = []
    errors = []
    for i, item in enumerate(data.items, start=1):
        dari = db.get(Kelas, item.dari_kelas_id)
        if not dari:
            errors.append({"item": i, "pesan": "Kelas asal tidak ditemukan"})
            continue
        if dari.tahun_ajaran_id == tujuan.id:
            errors.append({"item": i, "pesan": f"Kelas {dari.nama_kelas} sudah di tahun tujuan"})
            continue

        # Luluskan: murid aktif ditandai lulus, tetep ing kelas lawas
        if item.luluskan:
            n = (db.query(Murid)
                 .filter(Murid.kelas_id == dari.id, Murid.is_active.is_(True))
                 .update({Murid.is_active: False}))
            hasil.append({"dari_kelas": dari.nama_kelas, "ke_kelas": None,
                          "dipindah": 0, "diluluskan": n})
            continue

        # Tujuan: item.ke_kelas_id utawa cari/gawene miturut jeneng
        ke = None
        if item.ke_kelas_id:
            ke = db.get(Kelas, item.ke_kelas_id)
            if not ke or ke.tahun_ajaran_id != tujuan.id:
                errors.append({"item": i, "pesan": "Kelas tujuan tidak valid di tahun ini"})
                continue
        else:
            nama = (item.ke_nama_kelas or "").strip()
            if not nama:
                errors.append({"item": i, "pesan": "Tentukan kelas tujuan atau luluskan"})
                continue
            ke = (db.query(Kelas)
                  .filter(Kelas.tahun_ajaran_id == tujuan.id,
                          Kelas.nama_kelas == nama).first())
            if not ke:
                ke = Kelas(nama_kelas=nama, tahun_ajaran_id=tujuan.id)
                db.add(ke)
                db.flush()

        n = (db.query(Murid)
             .filter(Murid.kelas_id == dari.id, Murid.is_active.is_(True))
             .update({Murid.kelas_id: ke.id}))
        hasil.append({"dari_kelas": dari.nama_kelas, "ke_kelas": ke.nama_kelas,
                      "dipindah": n, "diluluskan": 0})

    db.commit()
    # Audit log summary
    total_dipindah = sum(h.get("dipindah", 0) for h in hasil)
    total_lulus = sum(h.get("diluluskan", 0) for h in hasil)
    log_action(
        user, "naik_kelas",
        f"Naik kelas ke TA '{tujuan.nama}': {len(hasil)} item, "
        f"{total_dipindah} dipindah, {total_lulus} diluluskan"
        + (f", {len(errors)} error" if errors else ""),
    )
    return {"ok": True, "items": hasil, "error": errors}


@router.post("/{kelas_id}/luluskan")
def kelas_luluskan(kelas_id: int,
                   db: Session = Depends(get_tenant_db),
                   user: dict = Depends(require_permission("kelas.update", "kelas.naik", "kelas.delete"))):
    """Luluskan kabeh murid aktif ing kelas (is_active=False, data tetep ana)."""
    k = db.get(Kelas, kelas_id)
    if not k:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kelas tidak ditemukan")
    n = (db.query(Murid)
         .filter(Murid.kelas_id == kelas_id, Murid.is_active.is_(True))
         .update({Murid.is_active: False}))
    db.commit()
    log_action(user, "luluskan_kelas", f"Kelas '{k.nama_kelas}' diluluskan ({n} murid)")
    return {"ok": True, "lulus": n}


@router.post("/pindah")
def kelas_pindah(data: PindahKelasRequest,
                 db: Session = Depends(get_tenant_db),
                 user: dict = Depends(require_permission("kelas.update", "kelas.naik", "kelas.delete"))):
    """Pindah kabeh murid aktif saka siji kelas menyang kelas liya (promosi)."""
    if data.dari_kelas_id == data.ke_kelas_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Kelas asal dan tujuan tidak boleh sama")
    dari = db.get(Kelas, data.dari_kelas_id)
    if not dari:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kelas asal tidak ditemukan")
    ke = db.get(Kelas, data.ke_kelas_id)
    if not ke:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kelas tujuan tidak ditemukan")
    n = (db.query(Murid)
         .filter(Murid.kelas_id == dari.id, Murid.is_active.is_(True))
         .update({Murid.kelas_id: ke.id}))
    db.commit()
    log_action(user, "pindah_kelas", f"{n} murid pindah dari '{dari.nama_kelas}' ke '{ke.nama_kelas}'")
    return {"ok": True, "dipindah": n,
            "dari": dari.nama_kelas, "ke": ke.nama_kelas}
