"""ticket number

Revision ID: a268343d1c91
Revises: c944c0576de1
Create Date: 2026-09-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a268343d1c91'
down_revision: Union[str, Sequence[str], None] = 'c944c0576de1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds Ticket.ticket_no ("TKT-2026-0001", sequential per year) and
    numbers existing tickets in creation order. Existing tickets with no
    assignee, or assigned to whoever created them, are handed to the IT
    employee (Employee.position = "IT") -- the same rule new tickets
    follow."""
    op.add_column(
        'tpc_tickets', sa.Column('ticket_no', sa.String(length=20), nullable=True)
    )

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, created_at FROM tpc_tickets ORDER BY created_at, id")
    ).fetchall()
    counters = {}
    for ticket_id, created_at in rows:
        year = (created_at.year if created_at else 2026)
        counters[year] = counters.get(year, 0) + 1
        conn.execute(
            sa.text("UPDATE tpc_tickets SET ticket_no = :no WHERE id = :id"),
            {"no": f"TKT-{year}-{counters[year]:04d}", "id": ticket_id},
        )

    it_user = conn.execute(
        sa.text(
            "SELECT u.id FROM tpc_users u "
            "JOIN tpc_employees e ON e.id = u.employee_id "
            "WHERE UPPER(TRIM(e.position)) = 'IT' AND u.is_active = 1 "
            "ORDER BY u.id LIMIT 1"
        )
    ).scalar()
    if it_user:
        conn.execute(
            sa.text(
                "UPDATE tpc_tickets SET assigned_to_user_id = :it "
                "WHERE assigned_to_user_id IS NULL "
                "OR assigned_to_user_id = created_by_user_id"
            ),
            {"it": it_user},
        )

    op.create_index(
        op.f('ix_tpc_tickets_ticket_no'), 'tpc_tickets', ['ticket_no'], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_tpc_tickets_ticket_no'), table_name='tpc_tickets')
    op.drop_column('tpc_tickets', 'ticket_no')
