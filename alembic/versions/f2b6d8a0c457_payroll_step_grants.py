"""payroll step grants

Payroll steps are now ticked per person on the Org Chart (Prepare &
Submit / Approve & Return / Lock & Mark Paid) instead of coming from the
user's role. Everyone who could already edit Payroll keeps preparing it
(gets Prepare & Submit); nobody gets Approve or Lock until it's ticked.

Revision ID: f2b6d8a0c457
Revises: e5a7c9b1d346
Create Date: 2026-10-03
"""

from alembic import op


revision = "f2b6d8a0c457"
down_revision = "e5a7c9b1d346"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        INSERT INTO tpc_employee_module_access (employee_id, module_key, can_edit, granted_by_user_id, created_at)
        SELECT a.employee_id, 'payroll.payroll_prepare', 1, a.granted_by_user_id, NOW()
        FROM tpc_employee_module_access a
        WHERE a.module_key = 'payroll.payroll' AND a.can_edit = 1
          AND NOT EXISTS (
            SELECT 1 FROM tpc_employee_module_access b
            WHERE b.employee_id = a.employee_id AND b.module_key = 'payroll.payroll_prepare'
          )
        """
    )


def downgrade():
    op.execute(
        "DELETE FROM tpc_employee_module_access WHERE module_key IN "
        "('payroll.payroll_prepare', 'payroll.payroll_approve', 'payroll.payroll_release')"
    )
