"""cash advance deduction options and terms

Revision ID: e035ad757d2c
Revises: c1994f1cbc51
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e035ad757d2c'
down_revision: Union[str, Sequence[str], None] = 'c1994f1cbc51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Preset deduction amounts superadmin makes available -- drivers pick
    # from this list on mobile instead of typing a free amount. See
    # app/models/cash_advance_deduction_option.py.
    op.create_table(
        "tpc_cash_advance_deduction_options",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tpc_cash_advance_deduction_options_id"),
        "tpc_cash_advance_deduction_options",
        ["id"],
        unique=False,
    )

    # Cash advance terms & conditions text -- always a single row (id=1).
    # See app/models/cash_advance_terms.py.
    op.create_table(
        "tpc_cash_advance_terms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["tpc_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tpc_cash_advance_terms_id"),
        "tpc_cash_advance_terms",
        ["id"],
        unique=False,
    )

    # Link requests to the option they were filed against, and record
    # terms acknowledgement.
    op.add_column(
        "tpc_cash_advance_requests",
        sa.Column("deduction_option_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tpc_cash_advance_requests",
        sa.Column(
            "terms_accepted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "tpc_cash_advance_requests",
        sa.Column("terms_accepted_at", sa.DateTime(), nullable=True),
    )
    op.create_foreign_key(
        "fk_cash_advance_requests_deduction_option_id",
        "tpc_cash_advance_requests",
        "tpc_cash_advance_deduction_options",
        ["deduction_option_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_cash_advance_requests_deduction_option_id",
        "tpc_cash_advance_requests",
        type_="foreignkey",
    )
    op.drop_column("tpc_cash_advance_requests", "terms_accepted_at")
    op.drop_column("tpc_cash_advance_requests", "terms_accepted")
    op.drop_column("tpc_cash_advance_requests", "deduction_option_id")

    op.drop_index(
        op.f("ix_tpc_cash_advance_terms_id"), table_name="tpc_cash_advance_terms"
    )
    op.drop_table("tpc_cash_advance_terms")

    op.drop_index(
        op.f("ix_tpc_cash_advance_deduction_options_id"),
        table_name="tpc_cash_advance_deduction_options",
    )
    op.drop_table("tpc_cash_advance_deduction_options")
