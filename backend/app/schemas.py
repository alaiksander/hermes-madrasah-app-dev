"""Pydantic schemas — validasi request/response"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Auth ──────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    kode_madrasah: str = Field(min_length=2, max_length=50)
    username: str
    password: str


class SuperLoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    nama: str
    tenant_kode: str | None = None
    tenant_nama: str | None = None


class UserMe(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    nama: str
    role: str
    tenant_kode: str | None = None
    tenant_nama: str | None = None


# ── Tenant (super admin) ──────────────────────────────────────────────────

class TenantCreate(BaseModel):
    kode: str = Field(min_length=3, max_length=30, pattern=r"^[a-z0-9_-]+$")
    nama: str = Field(min_length=3, max_length=100)
    subdomain: str | None = None
    plan: str = "free"
    max_murid: int | None = Field(default=None, ge=0)
    masa_langganan_hingga: date | None = None


class TenantDeleteRequest(BaseModel):
    """Konfirmasi penghapusan tenant — kode wajib cocok persis (layer proteksi backend)."""
    kode: str = Field(min_length=1, max_length=30)


class TenantUpdate(BaseModel):
    status: str | None = None
    plan: str | None = None
    max_murid: int | None = None
    masa_langganan_hingga: date | None = None
    hapus_masa_langganan: bool = False  # true = set tanpa batas (None)


class TenantAdminCreate(BaseModel):
    nama: str
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)


class TenantAdminReset(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)


class LanggananAlert(BaseModel):
    tenant_id: int
    kode: str
    nama: str
    status: str
    plan: str
    masa_langganan_hingga: date | None
    sisa_hari: int | None
    tingkat: str  # kadaluwarsa | kritis | waspada | info


class DashboardOut(BaseModel):
    tenant_total: int
    tenant_aktif: int
    tenant_suspended: int
    murid_total: int
    guru_total: int
    kelas_total: int
    absen_hari_ini: int
    alert_langganan: list[LanggananAlert]


class HariAbsen(BaseModel):
    tanggal: str
    hadir: int
    izin: int
    sakit: int
    alpa: int


class LoginTerakhir(BaseModel):
    nama: str
    username: str
    role: str
    last_login: str | None


class TenantDetailOut(BaseModel):
    id: int
    kode: str
    nama: str
    status: str
    plan: str
    max_murid: int
    masa_langganan_hingga: date | None
    dibuat: datetime | None
    jumlah_kelas: int
    jumlah_guru: int
    jumlah_admin: int
    jumlah_murid: int
    murid_aktif: int
    absen_total: int
    absen_7_hari: list[HariAbsen]
    login_terakhir: list[LoginTerakhir]


class BackupConfigRequest(BaseModel):
    enabled: bool
    jam: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    retensi: int = Field(default=14, ge=1, le=90)


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kode: str
    nama: str
    subdomain: str | None
    status: str
    plan: str
    max_murid: int | None
    masa_langganan_hingga: date | None
    created_at: datetime
    jumlah_guru: int = 0
    jumlah_murid: int = 0


# ── Kelas ─────────────────────────────────────────────────────────────────

class PindahKelasRequest(BaseModel):
    dari_kelas_id: int
    ke_kelas_id: int


class KelasCreate(BaseModel):
    nama_kelas: str
    wali_guru_id: int | None = None
    tahun_ajaran_id: int | None = None  # default: taun aktif


class KelasUpdate(BaseModel):
    nama_kelas: str | None = None
    wali_guru_id: int | None = None


class KelasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nama_kelas: str
    wali_guru_id: int | None
    jumlah_murid: int = 0
    tahun_ajaran_id: int | None = None
    tahun_ajaran_nama: str | None = None
    wali_guru_nama: str | None = None


# ── Mata Pelajaran ─────────────────────────────────────────────────────────

class MataPelajaranCreate(BaseModel):
    nama: str
    kode: str = ""
    kelompok: str = "umum"


class MataPelajaranUpdate(BaseModel):
    nama: str | None = None
    kode: str | None = None
    kelompok: str | None = None
    is_active: bool | None = None


class MataPelajaranOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nama: str
    kode: str = ""
    kelompok: str = "umum"
    is_active: bool = True


# ── Tahun Ajaran ───────────────────────────────────────────────────────────

class TahunAjaranCreate(BaseModel):
    nama: str = Field(min_length=4, max_length=20)
    tanggal_mulai: date
    tanggal_selesai: date


class TahunAjaranUpdate(BaseModel):
    nama: str | None = Field(default=None, min_length=4, max_length=20)
    tanggal_mulai: date | None = None
    tanggal_selesai: date | None = None
    is_active: bool | None = None


class TahunAjaranOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nama: str
    tanggal_mulai: date
    tanggal_selesai: date
    is_active: bool
    jumlah_kelas: int = 0
    periode: list["PeriodeAkademikOut"] = Field(default_factory=list)


class PeriodeAkademikOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tahun_ajaran_id: int
    kode: str
    nama: str
    tanggal_mulai: date
    tanggal_selesai: date


class PeriodeAkademikUpsert(BaseModel):
    kode: str = Field(pattern="^(ganjil|genap)$")
    nama: str = Field(min_length=3, max_length=50)
    tanggal_mulai: date
    tanggal_selesai: date


# ── Naik Kelas ─────────────────────────────────────────────────────────────

class NaikKelasItem(BaseModel):
    dari_kelas_id: int
    ke_kelas_id: int | None = None      # kelas tujuan sing wis ana
    ke_nama_kelas: str | None = None    # jeneng kelas anyar (digawe otomatis)
    luluskan: bool = False


class NaikKelasRequest(BaseModel):
    tahun_ajaran_id: int
    items: list[NaikKelasItem]


# ── Guru ──────────────────────────────────────────────────────────────────

class GuruCreate(BaseModel):
    nama: str
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)
    role: str = "guru"


class GuruUpdate(BaseModel):
    nama: str | None = None
    username: str | None = Field(default=None, min_length=3, max_length=50)
    role: str | None = None
    is_active: bool | None = None


class GuruPasswordReset(BaseModel):
    password: str = Field(min_length=6)


class GuruOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nama: str
    username: str
    role: str
    is_active: bool
    created_at: datetime


# ── Murid ─────────────────────────────────────────────────────────────────

class MuridCreate(BaseModel):
    nisn: str | None = Field(default=None, pattern=r"^\d{10}$")
    nama: str
    kelas_id: int
    nama_ortu: str | None = None  # legacy: verifikasi portal ortu
    telepon: str | None = None
    nik: str | None = Field(default=None, pattern=r"^\d{16}$")
    tempat_lahir: str | None = None
    tanggal_lahir: date | None = None
    jenis_kelamin: str | None = None  # Laki-laki/Perempuan
    alamat: str | None = None
    nama_ayah_kandung: str | None = None
    nama_ibu_kandung: str | None = None


class MuridUpdate(BaseModel):
    nisn: str | None = Field(default=None, pattern=r"^\d{10}$")
    nama: str | None = None
    kelas_id: int | None = None
    nama_ortu: str | None = None
    telepon: str | None = None
    nik: str | None = Field(default=None, pattern=r"^\d{16}$")
    tempat_lahir: str | None = None
    tanggal_lahir: date | None = None
    jenis_kelamin: str | None = None
    alamat: str | None = None
    nama_ayah_kandung: str | None = None
    nama_ibu_kandung: str | None = None
    is_active: bool | None = None


class MuridOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nisn: str | None
    nama: str
    kelas_id: int
    kelas_nama: str | None = None
    qr_uuid: str
    nama_ortu: str | None
    telepon: str | None
    nik: str | None
    tempat_lahir: str | None
    tanggal_lahir: date | None
    jenis_kelamin: str | None
    alamat: str | None
    nama_ayah_kandung: str | None
    nama_ibu_kandung: str | None
    is_active: bool
    created_at: datetime


class MuridList(BaseModel):
    total: int
    items: list[MuridOut]


# ── Absensi ───────────────────────────────────────────────────────────────

ABSENSI_STATUSES = {"hadir", "izin", "sakit", "alpa"}

class AbsenScanRequest(BaseModel):
    qr_uuid: str


class AbsenManualRequest(BaseModel):
    murid_id: int


class AbsenResult(BaseModel):
    status: str  # "hadir" | "duplikat" | "libur"
    pesan: str
    murid: MuridOut | None = None
    waktu: datetime | None = None
    sesi: str | None = None
    guru_pengabsen: str | None = None
    telat_menit: int | None = None


class AbsenRecord(BaseModel):
    id: int
    murid_id: int
    nisn: str | None = None
    nama: str
    kelas: str
    sesi: str
    status: str = "hadir"
    telat_menit: int | None = None
    tanggal: date
    waktu: datetime
    guru: str


# ── Pengaturan madrasah (jam & hari aktif) ─────────────────────────────────

class PengaturanOut(BaseModel):
    jam_masuk: str = "07:00"
    jam_pulang: str = "13:30"
    hari_aktif: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    nama_aplikasi: str = "Aplikasi Madrasah"
    # Power saving scanner QR (2026-08-12)
    scan_mode: str = "standar"  # standar | hemat | ekstrim
    scan_idle_menit: int = 5     # idle sleep (mode hemat)
    scan_aktif_detik: int = 30   # jendela aktif (mode ekstrim)


class PengaturanUpdate(BaseModel):
    jam_masuk: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    jam_pulang: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    hari_aktif: list[int] | None = Field(default=None, min_length=1, max_length=7)
    nama_aplikasi: str | None = Field(default=None, min_length=1, max_length=60)
    scan_mode: str | None = Field(default=None, pattern=r"^(standar|hemat|ekstrim)$")
    scan_idle_menit: int | None = Field(default=None, ge=1, le=60)
    scan_aktif_detik: int | None = Field(default=None, ge=5, le=300)

    @field_validator("hari_aktif")
    @classmethod
    def _cek_hari(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        if any(d < 1 or d > 7 for d in v):
            raise ValueError("Hari aktif harus 1-7 (1=Senin, 7=Minggu)")
        if len(set(v)) != len(v):
            raise ValueError("Hari aktif tidak boleh duplikat")
        return sorted(v)


class RosterItem(BaseModel):
    murid_id: int
    nisn: str | None = None
    nama: str
    status: str | None = None      # gabung masuk+pulang (None = belum diabsen)
    # Field jam terpisah (sesi pulang 2026-08-15)
    jam_masuk: str | None = None   # "HH:MM" atau None
    jam_pulang: str | None = None  # "HH:MM" atau None
    waktu: datetime | None = None   # legacy (waktu masuk) — kept for compatibility
    guru: str | None = None


class KelasAbsenEntry(BaseModel):
    murid_id: int
    status: str = "hadir"          # hadir/izin/sakit/alpa


class KelasAbsenRequest(BaseModel):
    tanggal: date | None = None    # default: hari ini (WIB server)
    entries: list[KelasAbsenEntry]  # maks 200


class KelasAbsenResult(BaseModel):
    ditambahkan: int
    diubah: int                    # admin override
    sudah_ada: int
    error: list[dict] = []         # [{baris, pesan}]


class AbsenKoreksiRequest(BaseModel):
    """Koreksi absensi oleh admin (override cooldown / salah scan).

    - mode='koreksi': ubah status record yang ada (hadir→izin, dst)
    - mode='tambah_pulang': catat pulang manual (override cooldown,
      mis. siswa pulang awal < 1 jam)
    - mode='hapus': hapus record (salah scan) — hanya sesi 'masuk' yang
      belum punya pasangan pulang bisa dihapus
    """
    murid_id: int
    tanggal: date | None = None    # default: hari ini
    sesi: str = "masuk"            # 'masuk' | 'pulang'
    mode: str = "koreksi"          # 'koreksi' | 'tambah_pulang' | 'hapus'
    status: str | None = None      # untuk koreksi: hadir/izin/sakit/alpa
    waktu: str | None = None       # optional HH:MM override


class RekapPerKelas(BaseModel):
    kelas: str
    total: int
    hadir: int
    izin: int
    sakit: int
    alpa: int
    belum: int                     # total - (hadir+izin+sakit+alpa)


class RekapOut(BaseModel):
    tanggal: date
    total_murid: int
    hadir: int
    izin: int
    sakit: int
    alpa: int
    belum: int
    per_kelas: list[RekapPerKelas] = []


# ── Jurnal Mengajar ──────────────────────────────────────────────────────────

from datetime import time as Time


class JurnalMengajarBase(BaseModel):
    kelas_id: int
    mata_pelajaran: str = Field(..., max_length=80)
    tanggal: date
    jam_mulai: Time
    jam_selesai: Time
    materi: str | None = None
    catatan: str | None = None


class JurnalMengajarCreate(JurnalMengajarBase):
    """Create + auto-populate absensi rows (all murid hadir default)."""
    pass


class JurnalAbsensiUpdate(BaseModel):
    """Update status satu murid di jurnal absensi."""
    status: str = Field(..., pattern="^(hadir|izin|sakit|alpa)$")


class JurnalAbsensiBulkUpdate(BaseModel):
    """Bulk update absensi per-murid untuk satu jurnal."""
    updates: dict[int, str]  # murid_id → status


class JurnalMengajarUpdate(BaseModel):
    """Schema untuk update (PATCH) — guru_id TIDAK boleh diubah."""
    kelas_id: int | None = None
    mata_pelajaran: str | None = None
    tanggal: date | None = None
    jam_mulai: time | None = None
    jam_selesai: time | None = None
    materi: str | None = None
    catatan: str | None = None


class JurnalMengajarOut(JurnalMengajarBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    guru_id: int
    guru_nama: str = ""
    kelas_nama: str = ""
    status: str
    verified_by: int | None = None
    verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    absensi: list[dict] = []  # lazy-loaded summary


class JurnalListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tanggal: date
    kelas_nama: str
    mata_pelajaran: str
    jam_mulai: Time
    jam_selesai: Time
    status: str
    guru_nama: str
    created_at: datetime


# ══════════════════════════════════════════════════════════════════════
# PENILAIAN — schemas modul Penilaian (2026-08-17)
# ══════════════════════════════════════════════════════════════════════

JENIS_PENILAIAN = ("tugas", "sumatif", "asas", "asat")


class MateriPenilaianCreate(BaseModel):
    mapel_id: int
    kelas_id: int | None = None
    jenis: str = "sumatif"          # tugas | sumatif | asas | asat
    nama: str                       # "Sumatif 1", "Tugas 1", "ASAS Ganjil"
    materi: str = ""                # deskripsi materi
    kkpt: int = 70                  # KKTP per materi
    periode_akademik_id: int | None = None


class MateriPenilaianUpdate(BaseModel):
    nama: str | None = None
    materi: str | None = None
    kkpt: int | None = None
    jenis: str | None = None


class MateriPenilaianOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mapel_id: int
    kelas_id: int | None
    jenis: str
    nama: str
    materi: str
    kkpt: int
    guru_id: int
    periode_akademik_id: int | None
    mapel_nama: str | None = None
    kelas_nama: str | None = None
    jumlah_murid: int | None = None
    terisi: int | None = None       # jumlah murid yang sudah dinilai
    rata_rata: float | None = None
    tuntas: int | None = None
    created_at: datetime | None = None


class NilaiBulkCreate(BaseModel):
    """Input nilai sekaligus untuk satu materi (banyak murid)."""
    materi_penilaian_id: int
    entries: list[dict]             # [{"murid_id": 1, "skor": 88}, ...]


class NilaiUpdate(BaseModel):
    skor: int | None = None
    catatan: str | None = None


class NilaiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    materi_penilaian_id: int
    murid_id: int
    skor: int | None
    catatan: str
    murid_nama: str | None = None
    murid_nisn: str | None = None


# ══════════════════════════════════════════════════════════════════════
# TAGIHAN / PEMBAYARAN — schemas modul Pembayaran (2026-08-18)
# ══════════════════════════════════════════════════════════════════════

PERIODE_TAGIHAN = ("bulanan", "sekali", "semester")
STATUS_TAGIHAN = ("belum", "sebagian", "lunas", "ditunda")


class JenisPembayaranCreate(BaseModel):
    nama: str
    deskripsi: str = ""
    nominal: int = 0
    periode: str = "bulanan"          # bulanan | sekali | semester
    jatuh_tempo: int = 10             # tanggal (1-31); sekali → 0
    auto_generate: bool = True        # tagihan rutin tiap bulan
    boleh_cicil: bool = True


class JenisPembayaranUpdate(BaseModel):
    nama: str | None = None
    deskripsi: str | None = None
    nominal: int | None = None
    periode: str | None = None
    jatuh_tempo: int | None = None
    auto_generate: bool | None = None
    boleh_cicil: bool | None = None
    is_active: bool | None = None


class JenisPembayaranOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nama: str
    deskripsi: str
    nominal: int
    periode: str
    jatuh_tempo: int
    auto_generate: bool
    boleh_cicil: bool
    is_active: bool


class TagihanCreate(BaseModel):
    murid_id: int
    jenis_id: int
    periode: str                     # YYYY-MM (atau label semester utk periode semester)
    nominal: int | None = None       # override nominal (default: dari jenis)
    jatuh_tempo: datetime | None = None


class TagihanBayarCreate(BaseModel):
    nominal: int                     # Rp yang dibayar
    metode: str = "cash"             # cash | transfer
    catatan: str = ""


class TagihanKeringananCreate(BaseModel):
    potongan: int                    # Rp keringanan (kasus khusus)
    catatan: str = ""


class TagihanTundaCreate(BaseModel):
    ditunda_sampai: datetime
    catatan: str = ""


class PembayaranOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tagihan_id: int
    nominal: int
    metode: str
    tanggal: datetime
    guru_id: int | None
    catatan: str
    guru_nama: str | None = None


class TagihanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    murid_id: int
    jenis_id: int
    periode: str
    nominal: int
    potongan: int
    jatuh_tempo: datetime | None
    ditunda_sampai: datetime | None
    status: str
    catatan: str
    murid_nama: str | None = None
    murid_nisn: str | None = None
    murid_kelas: str | None = None
    jenis_nama: str | None = None
    jenis_periode: str | None = None
    dibayar: int = 0                 # total terbayar
    sisa: int = 0                    # nominal - potongan - dibayar
    pembayaran: list[PembayaranOut] = []
