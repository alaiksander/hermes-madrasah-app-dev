"""Backfill guru_pengampu dari MateriPenilaian existing.

Dipanggil sekali saat deploy tabel guru_pengampu baru. Idempotent —
kalau tuple (guru, mapel, kelas, tahun_ajaran) sudah ada, skip.

Logika:
- Ambil semua (guru_id, mapel_id, kelas_id) DISTINCT dari materi_penilaian
- Pakai tahun_ajaran aktif (is_active=1) sebagai default
- Kalau tidak ada TA aktif, fallback ke TA terbaru
- Insert ke guru_pengampu dengan is_wali=0, is_active=1
"""
from sqlalchemy import select, text
from app.db import global_engine, GlobalSession, init_global_db
from app.models import GuruPengampu, MateriPenilaian, TahunAjaran, Tenant


def backfill_all_tenants() -> dict:
    """Backfill untuk semua tenant. Return {kode: inserted_count}."""
    init_global_db()
    with GlobalSession() as s:
        tenants = s.query(Tenant).all()
        results = {}
        for t in tenants:
            inserted = backfill_one_tenant(t.kode)
            results[t.kode] = inserted
        return results


def backfill_one_tenant(kode: str) -> int:
    """Backfill untuk 1 tenant. Return jumlah inserted."""
    from app.db import tenant_session_factory
    from app.models import Guru, MataPelajaran, Kelas
    with tenant_session_factory(kode)() as db:
        # Tentukan TA target
        ta = db.query(TahunAjaran).filter(
            TahunAjaran.is_active.is_(True)
        ).order_by(TahunAjaran.id.desc()).first()
        if not ta:
            ta = db.query(TahunAjaran).order_by(TahunAjaran.id.desc()).first()
        if not ta:
            print(f"  [skip] {kode}: tidak ada tahun ajaran")
            return 0
        ta_id = ta.id

        # Sumber: DISTINCT tuple dari materi_penilaian
        tuples = db.execute(text('''
            SELECT DISTINCT guru_id, mapel_id, kelas_id
            FROM materi_penilaian
            WHERE guru_id IS NOT NULL
              AND mapel_id IS NOT NULL
              AND kelas_id IS NOT NULL
        ''')).fetchall()
        if not tuples:
            print(f"  [skip] {kode}: tidak ada materi")
            return 0

        inserted = 0
        for guru_id, mapel_id, kelas_id in tuples:
            existing = db.query(GuruPengampu).filter_by(
                guru_id=guru_id, mapel_id=mapel_id,
                kelas_id=kelas_id, tahun_ajaran_id=ta_id
            ).first()
            if existing:
                continue
            db.add(GuruPengampu(
                guru_id=guru_id, mapel_id=mapel_id,
                kelas_id=kelas_id, tahun_ajaran_id=ta_id,
                is_wali=False, is_active=True,
            ))
            inserted += 1
        db.commit()
        print(f"  [ok] {kode}: inserted={inserted} (TA={ta.nama})")
        return inserted


if __name__ == "__main__":
    results = backfill_all_tenants()
    print("=== Summary ===")
    for kode, n in results.items():
        print(f"  {kode}: {n}")
