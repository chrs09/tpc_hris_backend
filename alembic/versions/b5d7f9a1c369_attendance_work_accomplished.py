"""attendance work accomplished

What the employee worked on, typed at time out, and whether they left
out the photo/video proof (that sends the time out to their immediate
head for review). Asked only of people whose head's Org Chart unit
ticks "Work accomplished". The proof itself is a FileModel row
(document_type WORK_PROOF).

Revision ID: b5d7f9a1c369
Revises: a3c7e9f1b268
Create Date: 2026-10-05
"""

from alembic import op
import sqlalchemy as sa


revision = "b5d7f9a1c369"
down_revision = "a3c7e9f1b268"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tpc_attendance_records", sa.Column("work_accomplished", sa.Text(), nullable=True))
    op.add_column("tpc_attendance_records", sa.Column("work_proof_missing", sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column("tpc_attendance_records", "work_proof_missing")
    op.drop_column("tpc_attendance_records", "work_accomplished")
