#!/usr/bin/env python3
"""Seed: super admin + pilot tenant MTs N 2 Kudus + data contoh.

Jalanake saka folder backend/:  ./venv/bin/python -m app.seed
Idempotent — aman dijalanake bola-bali.
"""
import uuid

from app.db import GlobalSession, init_global_db, provision_tenant_db, tenant_session_factory
from app.models import Guru, Kelas, Murid, SuperAdmin, Tenant
from app.security import hash_password

TENANT_KODE = "mtsn2kudus"


def seed() -> None:
    init_global_db()

    # ── global: super admin + tenant ────────────────────────────────────
    with GlobalSession() as gs:
        if not gs.query(SuperAdmin).filter_by(username="superadmin").first():
            gs.add(SuperAdmin(username="superadmin",
                              password_hash=hash_password("super123456"),
                              nama="Super Admin Platform"))
            print("+ Super admin: superadmin / super123456")

        tenant = gs.query(Tenant).filter_by(kode=TENANT_KODE).first()
        if not tenant:
            tenant = Tenant(kode=TENANT_KODE, nama="MTs Negeri 2 Kudus",
                            status="active", plan="pilot", max_murid=1000)
            gs.add(tenant)
            gs.commit()
            gs.refresh(tenant)
            provision_tenant_db(tenant.kode)
            print(f"+ Tenant pilot: {TENANT_KODE} (database digawe)")
        else:
            print(f"= Tenant wis ana: {TENANT_KODE}")

    # ── tenant: guru, kelas, murid contoh ───────────────────────────────
    with tenant_session_factory(TENANT_KODE)() as s:
        if not s.query(Guru).filter_by(username="admin").first():
            s.add(Guru(nama="Bu Sari (Admin)", username="admin",
                       password_hash=hash_password("admin123"), role="admin"))
            print("+ Admin: admin / admin123")
        if not s.query(Guru).filter_by(username="guru1").first():
            s.add(Guru(nama="Pak Ahmad (Piket)", username="guru1",
                       password_hash=hash_password("guru1234"), role="guru"))
            print("+ Guru: guru1 / guru1234")
        s.commit()

        kelas_map: dict[str, int] = {}
        for nama in ["7A", "7B", "8A", "8B", "9A", "9B"]:
            k = s.query(Kelas).filter_by(nama_kelas=nama).first()
            if not k:
                k = Kelas(nama_kelas=nama)
                s.add(k)
                s.flush()
            kelas_map[nama] = k.id
        s.commit()

        if s.query(Murid).count() == 0:
            nisn = 2400000001
            for kn, kid in kelas_map.items():
                for i in range(4):
                    nm = f"Murid Contoh {kn}-{i + 1}"
                    s.add(Murid(nisn=str(nisn), nama=nm, kelas_id=kid,
                                qr_uuid=str(uuid.uuid4()),
                                nama_ortu=f"Ortu {nm}",
                                telepon="6281234567890"))
                    nisn += 1
            s.commit()
            print("+ Murid contoh: 24 murid (4 x 6 kelas)")
        else:
            print("= Murid wis ana, ora digawe maneh")

    print("SEED DONE ✅")


if __name__ == "__main__":
    seed()
