"""trip review: a returned trip can be handed to a coordinator to fix

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7

Also drops returned_from (from a2b3c4d5e6f7): Finance returning a trip
was dropped -- only Office returns trips.
Create Date: 2026-11-13
"""

import sqlalchemy as sa
from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None

T = "tpc_trip_finance_reviews"


def upgrade() -> None:
    op.drop_column(T, "returned_from")
    op.add_column(T, sa.Column("resolver_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_review_resolver", T, "tpc_users", ["resolver_user_id"], ["id"])
    op.add_column(T, sa.Column("resolver_note", sa.String(1000), nullable=True))
    op.add_column(T, sa.Column("resolver_assigned_by_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_review_resolver_by", T, "tpc_users", ["resolver_assigned_by_user_id"], ["id"]
    )
    op.add_column(T, sa.Column("resolver_assigned_at", sa.DateTime(), nullable=True))
    op.add_column(T, sa.Column("resolved_at", sa.DateTime(), nullable=True))
    op.add_column(T, sa.Column("resolved_note", sa.String(1000), nullable=True))


def downgrade() -> None:
    op.drop_column(T, "resolved_note")
    op.drop_column(T, "resolved_at")
    op.drop_column(T, "resolver_assigned_at")
    op.drop_constraint("fk_review_resolver_by", T, type_="foreignkey")
    op.drop_column(T, "resolver_assigned_by_user_id")
    op.drop_column(T, "resolver_note")
    op.drop_constraint("fk_review_resolver", T, type_="foreignkey")
    op.drop_column(T, "resolver_user_id")
    op.add_column(T, sa.Column("returned_from", sa.String(20), nullable=True))
