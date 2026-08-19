"""Seed default Bimbingan Konseling (BK) untuk tenant baru.

Dipanggil sebagai bagian dari _ensure_tenant_seeded() (Fase-1 permission).
Master default: 5 kategori + 10 pelanggaran + 5 prestasi.
"""

# (kategori_nama, jenis, warna, poin_default_kategori, urutan)
BK_KATEGORI = [
    ("Pelanggaran", "negatif", "red", None, 1),
    ("Prestasi", "positif", "green", None, 2),
    ("Konseling", "netral", "blue", None, 3),
    ("Kasus Khusus", "negatif", "orange", None, 4),
    ("Catatan Positif", "positif", "emerald", None, 5),
]

# (kategori_nama, nama_pelanggaran, poin, tingkat)
# Tingkat: 'ringan' / 'sedang' / 'berat' (None untuk non-poin)
BK_PELANGGARAN = [
    ("Pelanggaran", "Terlambat masuk", 5, "ringan"),
    ("Pelanggaran", "Tidak mengerjakan PR", 10, "ringan"),
    ("Pelanggaran", "Rbut di kelas", 10, "ringan"),
    ("Pelanggaran", "Seragam tidak lengkap", 5, "ringan"),
    ("Pelanggaran", "Keluar kelas tanpa izin", 15, "sedang"),
    ("Pelanggaran", "Bolos", 20, "sedang"),
    ("Pelanggaran", "Tidak masuk tanpa keterangan", 10, "ringan"),
    ("Pelanggaran", "Berkelahi", 50, "berat"),
    ("Pelanggaran", "Membully", 75, "berat"),
    ("Pelanggaran", "Merokok di lingkungan sekolah", 100, "berat"),
]

# (kategori_nama, nama_prestasi, poin, tingkat)
BK_PRESTASI = [
    ("Prestasi", "Juara kelas", 50, None),
    ("Prestasi", "Juara lomba akademik", 30, None),
    ("Prestasi", "Juara lomba non-akademik", 20, None),
    ("Prestasi", "Aktif bertanya", 5, "ringan"),
    ("Prestasi", "Membantu teman", 10, "ringan"),
]


def seed_bk_defaults(db) -> tuple[int, int, int]:
    """Idempotent: insert BK kategori + pelanggaran + prestasi kalau belum ada.

    Return (kategori_added, pelanggaran_added, prestasi_added).
    """
    from .models import BkKategori, BkPelanggaran

    # Skip kalau sudah seeded (cek kategori sistem)
    existing_kategori = {k.nama for k in db.query(BkKategori).all()}
    if any(k.is_system for k in db.query(BkKategori).filter_by(is_system=True).all()):
        # Sudah ter-seed, skip total
        return (0, 0, 0)

    kat_added = 0
    kategori_map: dict[str, int] = {}

    for nama, jenis, warna, poin, urutan in BK_KATEGORI:
        if nama not in existing_kategori:
            k = BkKategori(nama=nama, jenis=jenis, warna=warna,
                            poin=poin, urutan=urutan, is_system=True)
            db.add(k)
            db.flush()
            kat_added += 1
        else:
            k = db.query(BkKategori).filter_by(nama=nama).first()
        kategori_map[nama] = k.id

    existing_pelanggaran = {p.nama for p in db.query(BkPelanggaran).all()}
    pel_added = 0
    for kat_nama, nama, poin, tingkat in BK_PELANGGARAN:
        if nama not in existing_pelanggaran:
            db.add(BkPelanggaran(
                kategori_id=kategori_map[kat_nama],
                nama=nama, poin=poin, tingkat=tingkat,
                is_system=True
            ))
            pel_added += 1

    existing_pres = {p.nama for p in db.query(BkPelanggaran).all()}
    pres_added = 0
    for kat_nama, nama, poin, tingkat in BK_PRESTASI:
        if nama not in existing_pres:
            db.add(BkPelanggaran(
                kategori_id=kategori_map[kat_nama],
                nama=nama, poin=poin, tingkat=tingkat,
                is_system=True
            ))
            pres_added += 1

    # Konfigurasi default (1 baris)
    from .models import BkKonfigurasi
    if not db.get(BkKonfigurasi, 1):
        db.add(BkKonfigurasi(id=1))

    db.commit()
    return (kat_added, pel_added, pres_added)
