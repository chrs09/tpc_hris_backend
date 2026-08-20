"""added finance models

Revision ID: 355ec343c98b
Revises: ef5ccfbe8066
Create Date: 2026-08-20 13:20:37.743794

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '355ec343c98b'
down_revision: Union[str, Sequence[str], None] = 'ef5ccfbe8066'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "tpc_finance_expenses",

        # ==============================
        # PRIMARY KEY
        # ==============================

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        # ==============================
        # EXPENSE INFORMATION
        # ==============================

        sa.Column(
            "encoded_date",
            sa.DateTime(),
            nullable=True,
        ),

        sa.Column(
            "posting_period",
            sa.String(length=50),
            nullable=True,
        ),

        sa.Column(
            "date",
            sa.Date(),
            nullable=True,
        ),

        # ==============================
        # REFERENCE
        # ==============================

        sa.Column(
            "po_number",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "supplier",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "receipt_number",
            sa.String(length=100),
            nullable=True,
        ),

        # ==============================
        # RECEIPT IMAGE
        # ==============================

        sa.Column(
            "receipt_image_url",
            sa.String(length=1000),
            nullable=True,
        ),

        # ==============================
        # ITEM DETAILS
        # ==============================

        sa.Column(
            "qty",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            nullable=True,
        ),

        sa.Column(
            "unit",
            sa.String(length=50),
            nullable=True,
        ),

        sa.Column(
            "particulars",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "unit_price",
            sa.Numeric(
                precision=14,
                scale=2,
            ),
            nullable=True,
        ),

        sa.Column(
            "amount",
            sa.Numeric(
                precision=14,
                scale=2,
            ),
            nullable=True,
        ),

        # ==============================
        # ASSIGNMENT
        # ==============================

        sa.Column(
            "responsible",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "additional_details",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "requested_by",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "received_by",
            sa.String(length=255),
            nullable=True,
        ),

        # ==============================
        # ACCOUNTING
        # ==============================

        sa.Column(
            "category",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "account",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),

        # ==============================
        # COUNTERING
        # ==============================

        sa.Column(
            "date_countered",
            sa.Date(),
            nullable=True,
        ),

        sa.Column(
            "counter_number",
            sa.String(length=100),
            nullable=True,
        ),

        # ==============================
        # PAYMENT
        # ==============================

        sa.Column(
            "date_paid",
            sa.Date(),
            nullable=True,
        ),

        sa.Column(
            "bank",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "check_number",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "check_amount",
            sa.Numeric(
                precision=14,
                scale=2,
            ),
            nullable=True,
        ),

        sa.Column(
            "receipt_number_2",
            sa.String(length=100),
            nullable=True,
        ),

        # ==============================
        # ACCOUNTS PAYABLE
        # ==============================

        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="Pending",
        ),

        sa.Column(
            "ap",
            sa.Numeric(
                precision=14,
                scale=2,
            ),
            nullable=True,
        ),

        sa.Column(
            "remarks",
            sa.Text(),
            nullable=True,
        ),

        # ==============================
        # AUDIT
        # ==============================

        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),

        # ==============================
        # CONSTRAINTS
        # ==============================

        sa.PrimaryKeyConstraint("id"),
    )

    # ==============================
    # INDEXES
    # ==============================

    op.create_index(
        "ix_tpc_finance_expenses_id",
        "tpc_finance_expenses",
        ["id"],
        unique=False,
    )

    op.create_index(
        "ix_tpc_finance_expenses_supplier",
        "tpc_finance_expenses",
        ["supplier"],
        unique=False,
    )

    op.create_index(
        "ix_tpc_finance_expenses_status",
        "tpc_finance_expenses",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_tpc_finance_expenses_date",
        "tpc_finance_expenses",
        ["date"],
        unique=False,
    )


def downgrade():
    # ==============================
    # DROP INDEXES
    # ==============================

    op.drop_index(
        "ix_tpc_finance_expenses_date",
        table_name="tpc_finance_expenses",
    )

    op.drop_index(
        "ix_tpc_finance_expenses_status",
        table_name="tpc_finance_expenses",
    )

    op.drop_index(
        "ix_tpc_finance_expenses_supplier",
        table_name="tpc_finance_expenses",
    )

    op.drop_index(
        "ix_tpc_finance_expenses_id",
        table_name="tpc_finance_expenses",
    )

    # ==============================
    # DROP TABLE
    # ==============================

    op.drop_table(
        "tpc_finance_expenses"
    )