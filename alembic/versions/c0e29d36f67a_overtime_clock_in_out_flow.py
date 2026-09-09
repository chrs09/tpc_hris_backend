"""overtime clock-in/clock-out flow

Revision ID: c0e29d36f67a
Revises: 5fc5465cdbe4
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c0e29d36f67a'
down_revision: Union[str, Sequence[str], None] = '5fc5465cdbe4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # time_out/computed_hours are now only filled in once the employee
    # clocks out of the overtime -- a request exists (visible to the head)
    # from clock-in time onward with both still null.
    op.alter_column(
        "tpc_overtime_requests", "time_out", existing_type=sa.Time(), nullable=True
    )
    op.alter_column(
        "tpc_overtime_requests",
        "computed_hours",
        existing_type=sa.Float(),
        nullable=True,
    )
    op.add_column(
        "tpc_overtime_requests",
        sa.Column("selfie_photo_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tpc_overtime_requests", "selfie_photo_url")
    op.alter_column(
        "tpc_overtime_requests",
        "computed_hours",
        existing_type=sa.Float(),
        nullable=False,
    )
    op.alter_column(
        "tpc_overtime_requests", "time_out", existing_type=sa.Time(), nullable=False
    )
