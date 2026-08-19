"""baseline tenant

Revision ID: b1a2c3d4e5f6
Revises: 54a8e1e51b67
Create Date: 2026-08-17 12:10:00.000000

Baseline schema tenant — semua tabel dibuat via `provision_tenant_db`
(create_all) sebagai source of truth. Migration ini hanya penanda supaya
perubahan schema MASA DEPAN bisa di-track via Alembic.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '54a8e1e51b67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
