"""drop hris.leave module grant

Leave approvals now come only from the Org Chart (a unit with Leave
ticked), so the assignable HRIS -> Leave Requests tick is gone. Remove
its saved rows so saving someone's access doesn't send an unknown key.

Revision ID: a3c7e9f1b268
Revises: f2b6d8a0c457
Create Date: 2026-10-03
"""

from alembic import op


revision = "a3c7e9f1b268"
down_revision = "f2b6d8a0c457"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DELETE FROM tpc_employee_module_access WHERE module_key = 'hris.leave'")


def downgrade():
    # The removed grants can't be restored.
    pass
