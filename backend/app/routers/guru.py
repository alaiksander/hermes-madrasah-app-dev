"""CRUD Guru (per tenant) — mung admin + import massal Excel"""
import csv
import io

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..audit import log_action
from ..deps import get_tenant_db, require_permission, require_roles
from ..models import Absensi, Guru, Kelas
from ..schemas import (GuruCreate, GuruOut, GuruPasswordReset, GuruUpdate)
from ..security import hash_password
from ..xlsx_utils import XLSX_MIME, rows_to_xlsx, xlsx_to_rows
router = APIRouter(prefix="/api/guru", tags=["guru"])
router = APIRouter(prefix="/api/guru", tags=["guru"])


@router.get("/template.xlsx", response_class=Response)
def template_guru(_: dict = Depends(require_permission("guru.create", "guru.update", "guru.delete", "guru.reset"))):
    """Template import guru .xlsx — diisi pengguna banjur di-Import."""
    data = [
        ["Contoh Nama Guru", "guru001", "guru1234", "guru"],
        ["Contoh Admin", "admin001", "admin1234", "admin"],
    ]
    return Response(
        content=rows_to_xlsx(["Nama", "Username", "Password", "Role"], data),
        media_type=XLSX_MIME,
        headers={"Content-Disposition":
                 'attachment; filename="template-import-guru.xlsx"'})


@router.post("/import")
async def import_guru(file: UploadFile = File(...),
                      db: Session = Depends(get_tenant_db),
                      _: dict = Depends(require_permission("guru.create", "guru.update", "guru.delete", "guru.reset"))):
    """Import guru massal saka .xlsx/.xls (utawa CSV lawas).

    Kolom: Nama, Username, Password, Role (Password & Role opsional).
    - Password kosong → default "guru1234" (dihitung ing password_default)
    - Role: 'admin' utawa 'guru' (case-insensitive, selaine kuwi → guru)
    - Username sing wis ana dilewati (skip)
    """
    content = await file.read()
    fname = (file.filename or "").lower()
    if fname.endswith((".xlsx", ".xls")):
        headers, rows = xlsx_to_rows(content)
        dict_rows = [dict(zip(headers, r)) for r in rows]
    else:
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        dict_rows = list(reader)
        headers = reader.fieldnames or []

    header_map = {}
    for h in headers:
        key = h.strip().lower().replace("_", " ").replace("-", " ")
        header_map[key] = h

    def cell(row: dict, *aliases: str) -> str:
        for a in aliases:
            if a in header_map:
                return (row.get(header_map[a]) or "").strip()
        return ""

    added = skipped = default_pwd = 0
    errors = []
    for i, raw in enumerate(dict_rows, start=2):
        nama = cell(raw, "nama", "nama lengkap")
        username = cell(raw, "username", "user")
        password = cell(raw, "password", "pw", "pass")
        role = cell(raw, "role", "jabatan")
        if not nama or not username:
            errors.append({"baris": i, "pesan": "Nama/Username kosong"})
            continue
        if db.query(Guru).filter_by(username=username).first():
            skipped += 1
            continue
        if not password:
            password = "guru1234"
            default_pwd += 1
        role_norm = "admin" if role.lower() == "admin" else "guru"
        db.add(Guru(nama=nama, username=username,
                    password_hash=hash_password(password), role=role_norm))
        added += 1
    db.commit()
    return {"ditambahkan": added, "sudah_ada": skipped,
            "password_default": default_pwd, "error": errors}


@router.get("", response_model=list[GuruOut])
def list_guru(db: Session = Depends(get_tenant_db),
              _: dict = Depends(require_permission("guru.create", "guru.update", "guru.delete", "guru.reset"))):
    return db.query(Guru).order_by(Guru.nama).all()


@router.post("", response_model=GuruOut, status_code=status.HTTP_201_CREATED)
def create_guru(data: GuruCreate,
                db: Session = Depends(get_tenant_db),
                user: dict = Depends(require_permission("guru.create", "guru.update", "guru.delete", "guru.reset"))):
    if db.query(Guru).filter_by(username=data.username).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Username sudah dipakai")
    if data.role not in ("guru", "admin"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Role harus 'guru' atau 'admin'")
    g = Guru(nama=data.nama, username=data.username,
             password_hash=hash_password(data.password), role=data.role)
    db.add(g)
    db.commit()
    db.refresh(g)
    log_action(user, "tambah_guru",
               f"Guru '{g.nama}' (username={g.username}, role={g.role}) ditambah")
    return g


@router.patch("/{guru_id}", response_model=GuruOut)
def update_guru(guru_id: int, data: GuruUpdate,
                db: Session = Depends(get_tenant_db),
                user: dict = Depends(require_permission("guru.create", "guru.update", "guru.delete", "guru.reset"))):
    g = db.get(Guru, guru_id)
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guru tidak ditemukan")
    changes = []
    if data.nama is not None and g.nama != data.nama:
        changes.append(f"nama '{g.nama}' → '{data.nama}'")
        g.nama = data.nama
    if data.username is not None and data.username != g.username:
        if db.query(Guru).filter(Guru.username == data.username,
                                 Guru.id != guru_id).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "Username sudah dipakai")
        changes.append(f"username '{g.username}' → '{data.username}'")
        g.username = data.username
    if data.role is not None:
        if data.role not in ("guru", "admin"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Role tidak valid")
        if data.role != g.role and g.id == user["id"]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Tidak dapat mengubah role akun sendiri")
        if data.role != g.role:
            changes.append(f"role '{g.role}' → '{data.role}'")
        g.role = data.role
    if data.is_active is not None:
        if data.is_active is False and g.id == user["id"]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Tidak dapat menonaktifkan akun sendiri")
        if data.is_active is False and g.role == "admin":
            aktif = db.query(Guru).filter(Guru.role == "admin",
                                          Guru.is_active.is_(True)).count()
            if aktif <= 1:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    "Minimal harus ada satu admin aktif")
        if data.is_active != g.is_active:
            changes.append(f"is_active {g.is_active} → {data.is_active}")
        g.is_active = data.is_active
    db.commit()
    db.refresh(g)
    if changes:
        log_action(user, "ubah_guru",
                   f"Guru id={guru_id} ({g.username}): {', '.join(changes)}")
    return g


@router.post("/{guru_id}/reset-password")
def reset_password(guru_id: int, data: GuruPasswordReset,
                   db: Session = Depends(get_tenant_db),
                   user: dict = Depends(require_permission("guru.create", "guru.update", "guru.delete", "guru.reset"))):
    g = db.get(Guru, guru_id)
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guru tidak ditemukan")
    g.password_hash = hash_password(data.password)
    db.commit()
    log_action(user, "reset_password_guru",
               f"Password guru '{g.nama}' (id={guru_id}) direset oleh admin")
    return {"ok": True}


@router.delete("/{guru_id}")
def deactivate_guru(guru_id: int,
                    db: Session = Depends(get_tenant_db),
                    user: dict = Depends(require_permission("guru.create", "guru.update", "guru.delete", "guru.reset"))):
    """Soft-delete: is_active=False. Wali kelas sing nunjuk guru iki dibalekne null."""
    g = db.get(Guru, guru_id)
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guru tidak ditemukan")
    g.is_active = False
    n_kelas = 0
    for k in db.query(Kelas).filter_by(wali_guru_id=guru_id).all():
        k.wali_guru_id = None
        n_kelas += 1
    db.commit()
    log_action(user, "hapus_guru",
               f"Guru '{g.nama}' (id={guru_id}) diarsipkan, "
               f"{n_kelas} kelas wali dikosongkan")
    return {"ok": True}


@router.delete("/{guru_id}/permanen")
def delete_guru_permanen(guru_id: int,
                         body: dict = Body(...),
                         db: Session = Depends(get_tenant_db),
                         user: dict = Depends(require_permission("guru.create", "guru.update", "guru.delete", "guru.reset"))):
    """Hapus guru PERMANEN — hanya untuk guru yang sudah diarsip.

    Proteksi (backend, bukan hanya UI):
    - Konfirmasi wajib: body.konfirmasi harus sama dengan username guru
    - Absensi.guru_id NOT NULL → kalau ada data absensi, TOLAK
    - Kelas.wali_guru_id → kosongkan dulu (guru arsip sudah dikosongkan saat soft-delete)
    """
    g = db.get(Guru, guru_id)
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guru tidak ditemukan")

    if body.get("konfirmasi", "").strip() != g.username:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Konfirmasi username tidak cocok — penghapusan dibatalkan")

    if g.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Arsipkan guru dulu sebelum menghapus permanen")

    # Proteksi FK: absensi
    n_absen = db.query(Absensi).filter(Absensi.guru_id == guru_id).count()
    if n_absen > 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Guru punya {n_absen} data absensi — tidak bisa dihapus permanen. "
            "Biarkan sebagai arsip.")

    # Kelas wali (harusnya sudah null saat arsip — pastikan lagi)
    n_kelas = 0
    for k in db.query(Kelas).filter_by(wali_guru_id=guru_id).all():
        k.wali_guru_id = None
        n_kelas += 1

    nama = g.nama
    username = g.username
    db.delete(g)
    db.commit()
    log_action(user, "hapus_guru_permanen",
               f"Guru '{nama}' ({username}, id={guru_id}) dihapus permanen, "
               f"{n_kelas} kelas wali dikosongkan")
    return {"ok": True, "nama": nama}
