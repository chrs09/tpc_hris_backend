"""add employee custom module access flag

Revision ID: 770fca07ca9f
Revises: f21756c7a466
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '770fca07ca9f'
down_revision: Union[str, Sequence[str], None] = 'f21756c7a466'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Distinguishes "never configured, fall back to role defaults" from
    # "deliberately restricted to zero modules" -- both look like an
    # empty EmployeeModuleAccess set otherwise. See
    # app/models/employees.py / app/api/employee_module_access.py.
    op.add_column(
        "tpc_employees",
        sa.Column(
            "has_custom_module_access",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("tpc_employees", "has_custom_module_access")
