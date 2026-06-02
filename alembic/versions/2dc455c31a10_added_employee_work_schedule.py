"""added employee work schedule

Revision ID: 2dc455c31a10
Revises: 23c73cfe9021
Create Date: 2026-06-01 15:20:03.902679

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2dc455c31a10'
down_revision: Union[str, Sequence[str], None] = '23c73cfe9021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "tpc_schedule_templates",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),

        sa.Column(
            "name",
            sa.String(length=100),
            nullable=False,
            unique=True,
        ),

        sa.Column(
            "description",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column("monday_in", sa.Time(), nullable=True),
        sa.Column("monday_out", sa.Time(), nullable=True),

        sa.Column("tuesday_in", sa.Time(), nullable=True),
        sa.Column("tuesday_out", sa.Time(), nullable=True),

        sa.Column("wednesday_in", sa.Time(), nullable=True),
        sa.Column("wednesday_out", sa.Time(), nullable=True),

        sa.Column("thursday_in", sa.Time(), nullable=True),
        sa.Column("thursday_out", sa.Time(), nullable=True),

        sa.Column("friday_in", sa.Time(), nullable=True),
        sa.Column("friday_out", sa.Time(), nullable=True),

        sa.Column("saturday_in", sa.Time(), nullable=True),
        sa.Column("saturday_out", sa.Time(), nullable=True),

        sa.Column("sunday_in", sa.Time(), nullable=True),
        sa.Column("sunday_out", sa.Time(), nullable=True),

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
    )

    op.add_column(
        "tpc_employees",
        sa.Column(
            "schedule_template_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_employee_schedule_template",
        "tpc_employees",
        "tpc_schedule_templates",
        ["schedule_template_id"],
        ["id"],
    )

    op.create_index(
        "ix_employee_schedule_template",
        "tpc_employees",
        ["schedule_template_id"],
    )


def downgrade():
    op.drop_index(
        "ix_employee_schedule_template",
        table_name="tpc_employees",
    )

    op.drop_constraint(
        "fk_employee_schedule_template",
        "tpc_employees",
        type_="foreignkey",
    )

    op.drop_column(
        "tpc_employees",
        "schedule_template_id",
    )

    op.drop_table(
        "tpc_schedule_templates",
    )