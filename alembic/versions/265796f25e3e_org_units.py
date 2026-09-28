"""org units

Revision ID: 265796f25e3e
Revises: 0f0774d1e572
Create Date: 2026-09-28

"""
import json
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '265796f25e3e'
down_revision: Union[str, Sequence[str], None] = '0f0774d1e572'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Starting chart: Owner -> Admins -> (HR, IT, Trip Management ->
# Coordinator -> Drivers). Superadmin can reshape it on the Org Chart page.
SEED = [
    # key, name, parent key, positions, roles
    ("owner", "Owner", None, [], ["superadmin"]),
    ("admins", "Admins", "owner", [], ["admin"]),
    ("hr", "HR", "admins", ["HR Admin", "Payroll & Billing"], []),
    ("it", "IT", "admins", ["IT"], []),
    ("trips", "Trip Management", "admins", [], ["coordinator_admin"]),
    ("coordinator", "Coordinator", "trips", ["Coordinator"], ["coordinator"]),
    ("drivers", "Drivers", "coordinator", ["Driver", "Wingvan Driver"], ["driver"]),
]


def upgrade() -> None:
    """Organizational chart units (see app/models/org_unit.py)."""
    op.create_table(
        'tpc_org_units',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('head_user_id', sa.Integer(), nullable=True),
        sa.Column('member_positions', sa.Text(), nullable=True),
        sa.Column('member_roles', sa.Text(), nullable=True),
        sa.Column('member_departments', sa.Text(), nullable=True),
        sa.Column('member_employee_ids', sa.Text(), nullable=True),
        sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['tpc_org_units.id']),
        sa.ForeignKeyConstraint(['head_user_id'], ['tpc_users.id']),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['tpc_users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tpc_org_units_id'), 'tpc_org_units', ['id'])
    op.create_index(op.f('ix_tpc_org_units_parent_id'), 'tpc_org_units', ['parent_id'])

    conn = op.get_bind()
    ids = {}
    now = datetime.utcnow()
    for order, (key, name, parent, positions, roles) in enumerate(SEED):
        result = conn.execute(
            sa.text(
                "INSERT INTO tpc_org_units (name, parent_id, sort_order, "
                "member_positions, member_roles, member_departments, "
                "member_employee_ids, updated_at) VALUES (:name, :parent, "
                ":order, :positions, :roles, '[]', '[]', :now)"
            ),
            {
                "name": name,
                "parent": ids.get(parent),
                "order": order,
                "positions": json.dumps(positions),
                "roles": json.dumps(roles),
                "now": now,
            },
        )
        ids[key] = result.lastrowid


def downgrade() -> None:
    op.drop_index(op.f('ix_tpc_org_units_parent_id'), table_name='tpc_org_units')
    op.drop_index(op.f('ix_tpc_org_units_id'), table_name='tpc_org_units')
    op.drop_table('tpc_org_units')
