"""changed string to text for face_reason

Revision ID: fdcf99ea6387
Revises: 753f66e79645
Create Date: 2026-05-23 14:40:41.488943

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "fdcf99ea6387"
down_revision: Union[str, Sequence[str], None] = "753f66e79645"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "tpc_attendance_records",
        "face_review_reason",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "tpc_attendance_records",
        "face_review_reason",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
