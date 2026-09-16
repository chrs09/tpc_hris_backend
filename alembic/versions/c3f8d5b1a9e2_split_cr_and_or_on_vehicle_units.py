"""split cr and or into separate documents on vehicle units

Revision ID: c3f8d5b1a9e2
Revises: b7e1a2c9f4d6
Create Date: 2026-09-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f8d5b1a9e2'
down_revision: Union[str, Sequence[str], None] = 'b7e1a2c9f4d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The combined cr_or_* columns become CR's own columns -- OR was
    # never actually captured as a separate document before this, so
    # existing data (if any) is treated as the CR.
    op.alter_column(
        "tpc_vehicle_units",
        "cr_or_number",
        new_column_name="cr_number",
        existing_type=sa.String(100),
    )
    op.alter_column(
        "tpc_vehicle_units",
        "cr_or_document_url",
        new_column_name="cr_document_url",
        existing_type=sa.String(500),
    )
    op.alter_column(
        "tpc_vehicle_units",
        "cr_or_expiration_date",
        new_column_name="cr_expiration_date",
        existing_type=sa.Date(),
    )

    op.add_column(
        "tpc_vehicle_units",
        sa.Column("or_number", sa.String(100), nullable=True),
    )
    op.add_column(
        "tpc_vehicle_units",
        sa.Column("or_document_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "tpc_vehicle_units",
        sa.Column("or_expiration_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tpc_vehicle_units", "or_expiration_date")
    op.drop_column("tpc_vehicle_units", "or_document_url")
    op.drop_column("tpc_vehicle_units", "or_number")

    op.alter_column(
        "tpc_vehicle_units",
        "cr_expiration_date",
        new_column_name="cr_or_expiration_date",
        existing_type=sa.Date(),
    )
    op.alter_column(
        "tpc_vehicle_units",
        "cr_document_url",
        new_column_name="cr_or_document_url",
        existing_type=sa.String(500),
    )
    op.alter_column(
        "tpc_vehicle_units",
        "cr_number",
        new_column_name="cr_or_number",
        existing_type=sa.String(100),
    )
