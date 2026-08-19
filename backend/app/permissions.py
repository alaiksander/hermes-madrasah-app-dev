import time

"""Seed permission matrix (Fase-1).

Setiap permission punya kode (string) yang dipakai di endpoint + view
untuk check. Backward-compat: role 'admin' / 'guru' di-check dulu;
role custom pakai role_id + role_permissions table.

Daftar permission ini jadi sumber kebenaran satu-satunya. Tambah
endpoint baru? Tambah kode di sini juga.
"""

# (kode, kategori, label) — sumber tunggal
PERMISSIONS = [
    # ── Absensi (scan & input)
    ("absen.scan", "absen", "Scan QR absensi"),
    ("absen.manual", "absen", "Input absen manual per kelas"),
    ("absen.koreksi", "absen", "Koreksi absen (admin: override cooldown)"),
    ("absen.rekap", "absen", "Lihat rekap harian"),
    ("absen.export", "absen", "Export Excel/PDF rekap"),
    ("absen.cetak", "absen", "Cetak absen (per kelas/murid)"),

    # ── Murid
    ("murid.view", "murid", "Lihat daftar & detail murid"),
    ("murid.create", "murid", "Tambah murid"),
    ("murid.update", "murid", "Edit data murid"),
    ("murid.delete", "murid", "Hapus/arsipkan murid"),
    ("murid.import", "murid", "Import Excel"),
    ("murid.qr", "murid", "Cetak kartu QR"),

    # ── Guru
    ("guru.view", "guru", "Lihat daftar guru"),
    ("guru.create", "guru", "Tambah guru"),
    ("guru.update", "guru", "Edit guru"),
    ("guru.delete", "guru", "Hapus/arsipkan guru"),
    ("guru.reset", "guru", "Reset password guru"),

    # ── Kelas
    ("kelas.view", "kelas", "Lihat daftar kelas"),
    ("kelas.create", "kelas", "Tambah kelas"),
    ("kelas.update", "kelas", "Edit kelas (wali, dll)"),
    ("kelas.delete", "kelas", "Hapus kelas"),
    ("kelas.naik", "kelas", "Naik/luluskan kelas"),

    # ── Mata Pelajaran
    ("mapel.view", "mata_pelajaran", "Lihat daftar mata pelajaran"),
    ("mapel.create", "mata_pelajaran", "Tambah mata pelajaran"),
    ("mapel.update", "mata_pelajaran", "Edit mata pelajaran"),
    ("mapel.delete", "mata_pelajaran", "Hapus mata pelajaran"),

    # ── Tahun ajaran
    ("ta.view", "tahun_ajaran", "Lihat daftar tahun ajaran"),
    ("ta.create", "tahun_ajaran", "Tambah tahun ajaran"),
    ("ta.update", "tahun_ajaran", "Edit/aktifkan tahun ajaran"),

    # ── Pengaturan
    ("pengaturan.view", "pengaturan", "Lihat pengaturan"),
    ("pengaturan.update", "pengaturan", "Edit pengaturan (jam, hari, hub)"),

    # ── Role & permission (admin only)
    ("role.view", "role", "Lihat daftar role"),
    ("role.update", "role", "Edit role & permission matrix"),

    # ── Bimbingan Konseling (BK)
    ("bk.view", "bk", "Lihat data BK"),
    ("bk.catatan", "bk", "Catat perkembangan"),
    ("bk.sesi", "bk", "Catat sesi konseling"),
    ("bk.export", "bk", "Export laporan BK"),
    ("bk.monitor", "bk", "Monitor absensi + catatan"),
    ("bk.master", "bk", "Kelola master kategori & pelanggaran"),
    # Jurnal Mengajar
    ("jurnal.view", "jurnal", "Lihat jurnal mengajar"),
    ("jurnal.input", "jurnal", "Input / edit jurnal sendiri"),
    ("jurnal.verify", "jurnal", "Verifikasi jurnal guru lain"),
    ("jurnal.export", "jurnal", "Export laporan jurnal (Excel/PDF)"),

    # ── Wali Kelas (perwalian)
    ("wali.view", "wali", "Lihat kelas perwalian & riwayat murid"),

    # ── Penilaian (nilai tugas/sumatif/ASAS/ASAT)
    ("penilaian.view", "penilaian", "Lihat data penilaian"),
    ("penilaian.input", "penilaian", "Input / edit nilai"),
    ("penilaian.export", "penilaian", "Export rekap nilai / RDM"),

    # ── Pembayaran / Tagihan
    ("tagihan.view", "pembayaran", "Lihat tagihan & pembayaran"),
    ("tagihan.input", "pembayaran", "Input pembayaran (lunas/cicil), keringanan, penundaan"),
    ("tagihan.kelola", "pembayaran", "Kelola jenis pembayaran & generate tagihan"),
]

# Default permission per role legacy (backfill awal)
ROLE_DEFAULT_PERMISSIONS = {
    "admin": [p[0] for p in PERMISSIONS],   # semua
    "guru": [
        "absen.scan", "absen.manual", "absen.rekap",
        "murid.view",
        "kelas.view", "ta.view",
        "jurnal.view", "jurnal.input", "jurnal.export",
        "mapel.view",
        "wali.view",
        "penilaian.view", "penilaian.input",
        "tagihan.view",
    ],
}


def seed_permissions(db) -> int:
    """Idempotent: insert permissions kalau belum ada. Return jumlah baru."""
    from .models import Permission
    existing = {p.kode for p in db.query(Permission).all()}
    added = 0
    for kode, kategori, label in PERMISSIONS:
        if kode not in existing:
            db.add(Permission(kode=kode, kategori=kategori, label=label))
            added += 1
    db.commit()
    return added


def seed_default_roles(db) -> tuple[int, int]:
    """Idempotent: buat role Admin & Guru kalau belum ada + assign permissions.
    Set role_id di guru agar permission matrix berlaku.
    Return (roles_created, guru_assigned).
    Retry jika SQLite transient lock."""
    from .models import Role, RolePermission, Guru
    # Retry max 3x untuk sqlite "database is locked"
    for attempt in range(3):
        try:
            return _seed_default_roles_inner(db)
        except Exception as e:
            if "locked" in str(e).lower() and attempt < 2:
                db.rollback()
                time.sleep(0.1 * (attempt + 1))
                continue
            raise


def _seed_default_roles_inner(db) -> tuple[int, int]:
    from .models import Permission, Role, RolePermission, Guru

    existing = {r.nama: r for r in db.query(Role).all()}
    roles_created = 0

    for legacy, nama, label in (("admin", "Admin", "Administrator"),
                                 ("guru", "Guru", "Guru / Pengajar")):
        if nama not in existing:
            role = Role(nama=nama, label=label, is_system=True,
                        legacy_role=legacy)
            db.add(role)
            db.flush()
            existing[nama] = role
            roles_created += 1
        else:
            existing[nama].legacy_role = legacy
            existing[nama].is_system = True
        # Assign permission default
        role = existing[nama]
        for kode in ROLE_DEFAULT_PERMISSIONS[legacy]:
            p = db.query(Permission).filter_by(kode=kode).first()
            if p and not db.query(RolePermission).filter_by(
                    role_id=role.id, permission_id=p.id).first():
                db.add(RolePermission(role_id=role.id, permission_id=p.id))

    # Set role_id di guru (backfill)
    guru_assigned = 0
    for g in db.query(Guru).all():
        if g.role_id is None:
            role = existing.get("Admin" if g.role == "admin" else "Guru")
            if role:
                g.role_id = role.id
                guru_assigned += 1

    db.commit()
    return roles_created, guru_assigned
