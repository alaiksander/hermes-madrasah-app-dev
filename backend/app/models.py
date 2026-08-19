"""Model database — GLOBAL (registry tenant) + TENANT (data per madrasah).

Pemisahan tegas:
- GlobalBase  -> tabel Tenant, SuperAdmin (database global)
- TenantBase  -> tabel Guru, Kelas, Murid, Absensi, LogWA (siji database per madrasah)
"""
from datetime import date, datetime, time, timezone

from sqlalchemy import (Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer,
                        LargeBinary, String, Text, Time, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GlobalBase(DeclarativeBase):
    pass


class TenantBase(DeclarativeBase):
    pass


# ── GLOBAL ────────────────────────────────────────────────────────────────

class Tenant(GlobalBase):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kode: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # mis. "mtsn2kudus"
    nama: Mapped[str] = mapped_column(String(150))
    subdomain: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(Enum("trial", "active", "suspended", native_enum=False, name="tenant_status"),
                                        default="trial")
    plan: Mapped[str] = mapped_column(String(30), default="free")
    max_murid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    masa_langganan_hingga: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                            nullable=True)


class SuperAdmin(GlobalBase):
    __tablename__ = "super_admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    nama: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BackupSetting(GlobalBase):
    """Setelan jadwal backup rutin (siji baris, id=1)."""
    __tablename__ = "backup_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    jam: Mapped[str] = mapped_column(String(5), default="02:00")
    retensi: Mapped[int] = mapped_column(Integer, default=14)


class BackupLog(GlobalBase):
    """Riwayat backup (otomatis/manual)."""
    __tablename__ = "backup_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    waktu: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    jenis: Mapped[str] = mapped_column(String(10), default="otomatis")
    status: Mapped[str] = mapped_column(String(10), default="ok")
    ukuran: Mapped[int] = mapped_column(Integer, default=0)
    nama_file: Mapped[str] = mapped_column(String(200), default="")
    pesan: Mapped[str] = mapped_column(String(300), default="")


class GlobalSetting(GlobalBase):
    """Setelan global platform (siji baris, id=1)."""
    __tablename__ = "global_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nama_aplikasi: Mapped[str] = mapped_column(String(100), default="Aplikasi Madrasah")
    maintenance: Mapped[bool] = mapped_column(Boolean, default=False)
    logo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class AuditLog(GlobalBase):
    """Jejak aksi sensitif superadmin (sapa + kapan + apa)."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    waktu: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped[str] = mapped_column(String(50))
    aksi: Mapped[str] = mapped_column(String(100))
    rincian: Mapped[str] = mapped_column(String(300), default="")
    tenant: Mapped[str] = mapped_column(String(50), default="")


class Plan(GlobalBase):
    """Definisi paket/plan lan kuotane (max_murid None = tanpa batas)."""
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nama: Mapped[str] = mapped_column(String(30), unique=True)
    label: Mapped[str] = mapped_column(String(50), default="")
    max_murid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_guru: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fitur: Mapped[str] = mapped_column(String(500), default="")  # komma-separated


# ── TENANT ────────────────────────────────────────────────────────────────

class Guru(TenantBase):
    __tablename__ = "guru"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nama: Mapped[str] = mapped_column(String(100))
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    # Role "guru"/"admin" bawaan (legacy, di-backfill ke role permission).
    # Untuk role custom, pakai role_id (FK ke Role).
    role: Mapped[str] = mapped_column(String(30), default="guru")
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"),
                                               nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    kelas_wali: Mapped[list["Kelas"]] = relationship(back_populates="wali_guru")
    role_def: Mapped["Role | None"] = relationship(back_populates="guru")


class Role(TenantBase):
    """Role custom per tenant (Fase-1 permission matrix)."""
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nama: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(100), default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    # 'admin' / 'guru' — backward-compat untuk query require_roles()
    legacy_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan")
    guru: Mapped[list["Guru"]] = relationship(back_populates="role_def")


class Permission(TenantBase):
    """Permission atomik (per-tenant, copy dari global seed)."""
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kode: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    kategori: Mapped[str] = mapped_column(String(30), default="")
    label: Mapped[str] = mapped_column(String(100), default="")

    roles: Mapped[list["RolePermission"]] = relationship(
        back_populates="permission", cascade="all, delete-orphan")


class RolePermission(TenantBase):
    """Many-to-many: role <-> permission."""
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"),
                                         primary_key=True, index=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id"),
                                                primary_key=True, index=True)

    role: Mapped[Role] = relationship(back_populates="permissions")
    permission: Mapped[Permission] = relationship(back_populates="roles")


class MataPelajaran(TenantBase):
    """Master mata pelajaran — lintas tahun ajaran, dipakai di Jurnal Mengajar."""
    __tablename__ = "mata_pelajaran"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nama: Mapped[str] = mapped_column(String(100), index=True)
    kode: Mapped[str] = mapped_column(String(20), default="")
    kelompok: Mapped[str] = mapped_column(
        String(30), default="umum",
        comment="umum | keagamaan | muatan_lokal | keterampilan")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TahunAjaran(TenantBase):
    """Tahun ajaran — basis pengelolaan data (kelas per tahun)."""
    __tablename__ = "tahun_ajaran"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nama: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # "2025/2026"
    tanggal_mulai: Mapped[date] = mapped_column(Date)
    tanggal_selesai: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    kelas: Mapped[list["Kelas"]] = relationship(back_populates="tahun_ajaran")
    periode: Mapped[list["PeriodeAkademik"]] = relationship(
        back_populates="tahun_ajaran", cascade="all, delete-orphan")


class PeriodeAkademik(TenantBase):
    """Periode semester yang dikonfigurasi eksplisit per tahun ajaran."""
    __tablename__ = "periode_akademik"
    __table_args__ = (
        UniqueConstraint("tahun_ajaran_id", "kode", name="uq_periode_ta_kode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tahun_ajaran_id: Mapped[int] = mapped_column(
        ForeignKey("tahun_ajaran.id", ondelete="CASCADE"), index=True)
    kode: Mapped[str] = mapped_column(String(20))  # ganjil / genap
    nama: Mapped[str] = mapped_column(String(50))
    tanggal_mulai: Mapped[date] = mapped_column(Date)
    tanggal_selesai: Mapped[date] = mapped_column(Date)

    tahun_ajaran: Mapped[TahunAjaran] = relationship(back_populates="periode")


class Kelas(TenantBase):
    __tablename__ = "kelas"
    __table_args__ = (
        UniqueConstraint("tahun_ajaran_id", "nama_kelas",
                         name="uq_kelas_tahun_nama"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nama_kelas: Mapped[str] = mapped_column(String(50), index=True)
    wali_guru_id: Mapped[int | None] = mapped_column(ForeignKey("guru.id"), nullable=True)
    tahun_ajaran_id: Mapped[int] = mapped_column(ForeignKey("tahun_ajaran.id"),
                                                 index=True)

    tahun_ajaran: Mapped[TahunAjaran] = relationship(back_populates="kelas")
    wali_guru: Mapped[Guru | None] = relationship(back_populates="kelas_wali")
    murid: Mapped[list["Murid"]] = relationship(back_populates="kelas")


class Murid(TenantBase):
    __tablename__ = "murid"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nisn: Mapped[str | None] = mapped_column(String(10), unique=True, index=True, nullable=True)  # NISN Kemenag (10 digit, opsional)
    nama: Mapped[str] = mapped_column(String(100), index=True)
    kelas_id: Mapped[int] = mapped_column(ForeignKey("kelas.id"), index=True)
    qr_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)  # isi QR Card
    # Field EMIS (2026-08-17): selaras RDM/EMIS Kemenag
    nik: Mapped[str | None] = mapped_column(String(16), nullable=True)  # NIK KTP (16 digit)
    tempat_lahir: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tanggal_lahir: Mapped[date | None] = mapped_column(Date, nullable=True)
    jenis_kelamin: Mapped[str | None] = mapped_column(String(10), nullable=True)  # Laki-laki/Perempuan
    alamat: Mapped[str | None] = mapped_column(String(200), nullable=True)
    telepon: Mapped[str | None] = mapped_column(String(20), nullable=True)  # No telepon murid (ex-wa_ortu)
    nama_ayah_kandung: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nama_ibu_kandung: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nama_ortu: Mapped[str | None] = mapped_column(String(100), nullable=True)  # legacy: verifikasi portal ortu
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    kelas: Mapped[Kelas] = relationship(back_populates="murid")
    absensi: Mapped[list["Absensi"]] = relationship(back_populates="murid")


class Absensi(TenantBase):
    __tablename__ = "absensi"
    __table_args__ = (
        UniqueConstraint("murid_id", "sesi", "tanggal", name="uq_absensi_murid_sesi_tanggal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    murid_id: Mapped[int] = mapped_column(ForeignKey("murid.id"), index=True)
    guru_id: Mapped[int] = mapped_column(ForeignKey("guru.id"))
    sesi: Mapped[str] = mapped_column(Enum("masuk", "pulang", native_enum=False, name="absensi_sesi"), default="masuk")
    status: Mapped[str] = mapped_column(
        Enum("hadir", "izin", "sakit", "alpa", native_enum=False, name="absensi_status"),
        default="hadir", nullable=False)
    telat_menit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tanggal: Mapped[date] = mapped_column(Date, index=True)  # tanggal lokal WIB
    waktu: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    murid: Mapped[Murid] = relationship(back_populates="absensi")
    log_wa: Mapped[list["LogWA"]] = relationship(back_populates="absensi")


class LogWA(TenantBase):
    __tablename__ = "log_wa"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    absensi_id: Mapped[int] = mapped_column(ForeignKey("absensi.id"), index=True)
    wa_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(Enum("pending", "sent", "failed", native_enum=False, name="wa_status"),
                                        default="pending")
    error_msg: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    absensi: Mapped[Absensi] = relationship(back_populates="log_wa")


# ══════════════════════════════════════════════════════════════════════
# JURNAL MENGAJAR — Modul Jurnal (fase 1: 2026-08-16)
#
# Kontrak:
# - JurnalMengajar: 1 entri per sesi mengajar (kelas + MP + tanggal + jam).
# - JurnalAbsensi: absensi per-murid untuk sesi tersebut (perjam, pisah dari absensi harian).
# - Akses: guru (input sendiri), admin/guru BK/wali kelas (view all / kelasnya).
# ══════════════════════════════════════════════════════════════════════

class JurnalMengajar(TenantBase):
    __tablename__ = "jurnal_mengajar"
    __table_args__ = (
        Index("ix_jurnal_tanggal_guru", "tanggal", "guru_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guru_id: Mapped[int] = mapped_column(ForeignKey("guru.id"), index=True)
    kelas_id: Mapped[int] = mapped_column(ForeignKey("kelas.id"), index=True)
    mata_pelajaran: Mapped[str] = mapped_column(String(80), nullable=False)
    tanggal: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    jam_mulai: Mapped[time] = mapped_column(Time, nullable=False)
    jam_selesai: Mapped[time] = mapped_column(Time, nullable=False)
    materi: Mapped[str | None] = mapped_column(Text, nullable=True)
    catatan: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Status alur kerja: draft (belum lengkap) → submitted (sudah disubmit guru)
    # → verified (sudah dicek admin). Absensi hanya terkunci setelah verified.
    status: Mapped[str] = mapped_column(
        Enum("draft", "submitted", "verified", native_enum=False, name="jurnal_status"),
        default="draft", nullable=False)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("guru.id"),
                                                      nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                            nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                      default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                      default=utcnow,
                                                      onupdate=utcnow)

    guru: Mapped[Guru] = relationship(foreign_keys=[guru_id])
    kelas: Mapped[Kelas] = relationship()
    verifier: Mapped[Guru | None] = relationship(foreign_keys=[verified_by])
    absensi: Mapped[list["JurnalAbsensi"]] = relationship(
        back_populates="jurnal", cascade="all, delete-orphan")


class JurnalAbsensi(TenantBase):
    """Absensi per-murid untuk satu jurnal mengajar (perjam, pisah dari absensi harian)."""

    __tablename__ = "jurnal_absensi"
    __table_args__ = (
        UniqueConstraint("jurnal_id", "murid_id", name="uq_jurnal_absensi_jurnal_murid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jurnal_id: Mapped[int] = mapped_column(
        ForeignKey("jurnal_mengajar.id", ondelete="CASCADE"),
        index=True)
    murid_id: Mapped[int] = mapped_column(ForeignKey("murid.id"), index=True)
    status: Mapped[str] = mapped_column(
        Enum("hadir", "izin", "sakit", "alpa", native_enum=False, name="jurnal_absensi_status"),
        default="hadir", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                      default=utcnow)

    jurnal: Mapped[JurnalMengajar] = relationship(back_populates="absensi")
    murid: Mapped[Murid] = relationship()


class Pengaturan(TenantBase):
    """Setelan madrasah per-tenant (key-value) — jam & hari aktif."""
    __tablename__ = "pengaturan"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class BkKategori(TenantBase):
    """Kategori catatan BK: Pelanggaran, Prestasi, Konseling, dll.

    `poin` NULL = kelompok non-poin (mis. Konseling). Diisi = kelompok
    yang item-itemnya punya poin (untuk pelanggaran / prestasi).
    """
    __tablename__ = "bk_kategori"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nama: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    # 'positif' / 'negatif' / 'netral'
    jenis: Mapped[str] = mapped_column(String(20), default="netral")
    warna: Mapped[str] = mapped_column(String(20), default="zinc")
    # Bobot default untuk pelanggaran (NULL = bukan pelanggaran)
    poin: Mapped[int | None] = mapped_column(Integer, nullable=True)
    urutan: Mapped[int] = mapped_column(Integer, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BkPelanggaran(TenantBase):
    """Item pelanggaran / prestasi spesifik. Milik kategori.

    `tingkat` ringa/sedang/berat — hanya untuk pelanggaran.
    `poin` adalah bobot yg dihitung ke total pelanggaran siswa.
    """
    __tablename__ = "bk_pelanggaran"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kategori_id: Mapped[int] = mapped_column(ForeignKey("bk_kategori.id"),
                                              index=True)
    nama: Mapped[str] = mapped_column(String(100))
    poin: Mapped[int] = mapped_column(Integer, default=0)
    tingkat: Mapped[str | None] = mapped_column(String(20), nullable=True)
    urutan: Mapped[int] = mapped_column(Integer, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    kategori: Mapped["BkKategori"] = relationship()


class BkCatatan(TenantBase):
    """Catatan perkembangan per kejadian (multi-murid via BkPeserta).

    `murid_id` LEGACY — gunakan BkPeserta untuk siswa terkait.
    `pelanggaran_id` NULL = catatan biasa (konseling, kasus, prestasi).
    `poin_snapshot` = poin pada saat catatan dibuat (denormalized, agar
    histori tidak berubah kalau poin default diubah).
    """
    __tablename__ = "bk_catatan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # LEGACY: murid_id (nullable, dipertahankan untuk backward-compat)
    murid_id: Mapped[int | None] = mapped_column(
        ForeignKey("murid.id"), nullable=True, index=True)
    kategori_id: Mapped[int] = mapped_column(ForeignKey("bk_kategori.id"),
                                              index=True)
    pelanggaran_id: Mapped[int | None] = mapped_column(
        ForeignKey("bk_pelanggaran.id"), nullable=True, index=True)
    judul: Mapped[str] = mapped_column(String(150))
    isi: Mapped[str] = mapped_column(Text, default="")
    tanggal: Mapped[date] = mapped_column(Date, index=True)
    # 'ringan' / 'sedang' / 'berat' (untuk pelanggaran)
    tingkat: Mapped[str | None] = mapped_column(String(20), nullable=True)
    poin_snapshot: Mapped[int] = mapped_column(Integer, default=0)
    dibuat_oleh: Mapped[int] = mapped_column(ForeignKey("guru.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    murid: Mapped["Murid"] = relationship()
    kategori: Mapped["BkKategori"] = relationship()
    pelanggaran: Mapped["BkPelanggaran | None"] = relationship()
    peserta: Mapped[list["BkPeserta"]] = relationship(
        primaryjoin="and_(BkPeserta.entitas=='catatan', foreign(BkPeserta.entitas_id)==BkCatatan.id)",
        viewonly=True, cascade="all, delete-orphan")
    guru: Mapped["Guru"] = relationship()


class BkSesi(TenantBase):
    """Sesi konseling 1-on-1 (atau multi-murid via BkPesertaSesi)."""
    __tablename__ = "bk_sesi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # LEGACY: murid_id (nullable, untuk backward-compat)
    murid_id: Mapped[int | None] = mapped_column(ForeignKey("murid.id"),
                                                  nullable=True, index=True)
    tanggal: Mapped[date] = mapped_column(Date, index=True)
    tempat: Mapped[str] = mapped_column(String(100), default="Ruang BK")
    topik: Mapped[str] = mapped_column(String(150))
    hasil: Mapped[str] = mapped_column(Text, default="")
    tindak_lanjut: Mapped[str] = mapped_column(Text, default="")
    berikutnya_tanggal: Mapped[date | None] = mapped_column(Date, nullable=True)
    guru_id: Mapped[int] = mapped_column(ForeignKey("guru.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    murid: Mapped["Murid | None"] = relationship()
    guru: Mapped["Guru"] = relationship()
    peserta: Mapped[list["BkPeserta"]] = relationship(
        primaryjoin="and_(BkPeserta.entitas=='sesi', foreign(BkPeserta.entitas_id)==BkSesi.id)",
        viewonly=True, cascade="all, delete-orphan")


class BkKonfigurasi(TenantBase):
    """Setelan BK per tenant (satu baris, id=1)."""
    __tablename__ = "bk_konfigurasi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Threshold SP (custom). Default 20/50/100.
    threshold_sp1: Mapped[int] = mapped_column(Integer, default=20)
    threshold_sp2: Mapped[int] = mapped_column(Integer, default=50)
    threshold_sp3: Mapped[int] = mapped_column(Integer, default=100)
    # 'semester' / 'tahun_ajaran' (untuk filter rekap)
    periode_reset: Mapped[str] = mapped_column(String(20), default="semester")
    # Diperbarui oleh admin via UI (nama BK, dsb.)
    catatan: Mapped[str] = mapped_column(String(200), default="")


class BkPeserta(TenantBase):
    """Connector table — many-to-many antara catatan/sesi ↔ murid.

    `entitas` = 'catatan' | 'sesi'
    `entitas_id` = FK ke BkCatatan atau BkSesi (polimorfik, simple).
    `murid_id` = FK ke Murid.

    Index di (entitas, entitas_id) untuk query cepat.
    """
    __tablename__ = "bk_peserta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entitas: Mapped[str] = mapped_column(String(20), index=True)
    entitas_id: Mapped[int] = mapped_column(Integer, index=True)
    murid_id: Mapped[int] = mapped_column(ForeignKey("murid.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    murid: Mapped["Murid"] = relationship()


# ══════════════════════════════════════════════════════════════════════
# PENILAIAN — Modul Penilaian (2026-08-17)
#
# Kontrak:
# - MateriPenilaian: 1 entri per materi penilaian (mapel + nama + KKTP).
#   KKTP per MATERI (keputusan user 2026-08-17).
# - Nilai: 1 baris per murid per materi penilaian.
#   `jenis` = 'tugas' | 'sumatif' | 'asas' | 'asat'
# - Ekspor RDM: format NISN + nama + nilai per jenis (tanpa NIS — kita
#   tidak punya NIS, pakai NISN sebagai identitas murid).
# ══════════════════════════════════════════════════════════════════════

class MateriPenilaian(TenantBase):
    """Master materi/komponen penilaian per mapel (KKTP per materi)."""
    __tablename__ = "materi_penilaian"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mapel_id: Mapped[int] = mapped_column(ForeignKey("mata_pelajaran.id"), index=True)
    kelas_id: Mapped[int | None] = mapped_column(ForeignKey("kelas.id"), nullable=True, index=True)
    jenis: Mapped[str] = mapped_column(Enum("tugas", "sumatif", "asas", "asat",
                                            native_enum=False, name="nilai_jenis"),
                                       default="sumatif", index=True)
    nama: Mapped[str] = mapped_column(String(150))       # "Sumatif 1", "Tugas 1", "ASAS Ganjil"
    materi: Mapped[str] = mapped_column(String(255), default="")   # deskripsi materi
    kkpt: Mapped[int] = mapped_column(Integer, default=70)         # KKTP per materi
    guru_id: Mapped[int] = mapped_column(ForeignKey("guru.id"), index=True)
    periode_akademik_id: Mapped[int | None] = mapped_column(
        ForeignKey("periode_akademik.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    mapel: Mapped["MataPelajaran"] = relationship()
    kelas: Mapped["Kelas | None"] = relationship()


class Nilai(TenantBase):
    """Nilai per murid per materi penilaian."""
    __tablename__ = "nilai"
    __table_args__ = (
        Index("ix_nilai_materi_murid", "materi_penilaian_id", "murid_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    materi_penilaian_id: Mapped[int] = mapped_column(
        ForeignKey("materi_penilaian.id"), index=True)
    murid_id: Mapped[int] = mapped_column(ForeignKey("murid.id"), index=True)
    skor: Mapped[int | None] = mapped_column(Integer, nullable=True)   # NULL = belum diisi
    catatan: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    materi: Mapped[MateriPenilaian] = relationship()
    murid: Mapped["Murid"] = relationship()


class JenisPembayaran(TenantBase):
    """Master jenis pembayaran (SPP, uang kegiatan, seragam, dll)."""

    __tablename__ = "jenis_pembayaran"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nama: Mapped[str] = mapped_column(String(100), nullable=False)
    deskripsi: Mapped[str] = mapped_column(String(255), default="")
    nominal: Mapped[int] = mapped_column(Integer, default=0)        # Rp
    periode: Mapped[str] = mapped_column(                           # bulanan | sekali | semester
        String(10), default="bulanan")
    jatuh_tempo: Mapped[int] = mapped_column(Integer, default=10)   # tanggal (1-31); sekali → 0
    auto_generate: Mapped[bool] = mapped_column(Boolean, default=True)  # tagihan rutiin tiap bulan
    boleh_cicil: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tagihan: Mapped[list["Tagihan"]] = relationship(back_populates="jenis")


class Tagihan(TenantBase):
    """Tagihan per murid per periode (bulan). Status = derived dari pembayaran."""

    __tablename__ = "tagihan"
    __table_args__ = (
        Index("ix_tagihan_murid_periode", "murid_id", "periode", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    murid_id: Mapped[int] = mapped_column(ForeignKey("murid.id"), index=True)
    jenis_id: Mapped[int] = mapped_column(
        ForeignKey("jenis_pembayaran.id"), index=True)
    periode: Mapped[str] = mapped_column(String(7), default="")   # YYYY-MM (bulan tagihan)
    nominal: Mapped[int] = mapped_column(Integer, default=0)      # Rp (bisa diubah keringanan)
    potongan: Mapped[int] = mapped_column(Integer, default=0)     # Rp keringanan kasus khusus
    jatuh_tempo: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True)                   # tanggal jatuh tempo
    ditunda_sampai: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True)                   # penundaan
    status: Mapped[str] = mapped_column(                          # belum | sebagian | lunas | ditunda
        String(10), default="belum", index=True)
    catatan: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    murid: Mapped["Murid"] = relationship()
    jenis: Mapped[JenisPembayaran] = relationship(back_populates="tagihan")
    pembayaran: Mapped[list["Pembayaran"]] = relationship(
        back_populates="tagihan", cascade="all, delete-orphan")


class Pembayaran(TenantBase):
    """Transaksi bayar (lunas / cicilan) untuk satu tagihan."""

    __tablename__ = "pembayaran"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tagihan_id: Mapped[int] = mapped_column(
        ForeignKey("tagihan.id", ondelete="CASCADE"), index=True)
    nominal: Mapped[int] = mapped_column(Integer, default=0)      # Rp yang dibayar
    metode: Mapped[str] = mapped_column(String(20), default="cash")  # cash | transfer
    tanggal: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True)
    guru_id: Mapped[int | None] = mapped_column(
        ForeignKey("guru.id"), nullable=True)                     # operator yang input
    catatan: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tagihan: Mapped[Tagihan] = relationship(back_populates="pembayaran")
    guru: Mapped["Guru | None"] = relationship()

