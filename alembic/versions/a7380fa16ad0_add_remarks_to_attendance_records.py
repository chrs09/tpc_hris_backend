"""add remarks to attendance records

Revision ID: a7380fa16ad0
Revises: 028db704ff06
Create Date: 2026-06-10 14:53:23.374971

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7380fa16ad0'
down_revision: Union[str, Sequence[str], None] = '028db704ff06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "tpc_attendance_records",
        sa.Column(
            "remarks",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column(
        "tpc_attendance_records",
        "remarks",
    )