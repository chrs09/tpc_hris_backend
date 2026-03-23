"""create employee related tables

Revision ID: c853921c2599
Revises: 73abfa74a6ab
Create Date: 2026-03-17 17:14:09.985962

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c853921c2599"
down_revision: Union[str, Sequence[str], None] = "73abfa74a6ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # =========================
    # EMPLOYEE DOCUMENTS
    # =========================
    op.create_table(
        "tpc_employee_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(100)),
        sa.Column("file_path", sa.String(255)),
        sa.Column(
            "uploaded_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["tpc_employees.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_emp_docs_employee_id", "tpc_employee_documents", ["employee_id"]
    )

    # =========================
    # EDUCATION
    # =========================
    op.create_table(
        "tpc_employee_education",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(50)),
        sa.Column("institution", sa.String(150)),
        sa.Column("degree", sa.String(150)),
        sa.Column("year_from", sa.String(10)),
        sa.Column("year_to", sa.String(10)),
        sa.Column("skills", sa.String(255)),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["tpc_employees.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_emp_edu_employee_id", "tpc_employee_education", ["employee_id"])

    # =========================
    # EMERGENCY
    # =========================
    op.create_table(
        "tpc_employee_emergency_contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("contact_name", sa.String(150)),
        sa.Column("relationship_type", sa.String(100)),
        sa.Column("contact_number", sa.String(50)),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["tpc_employees.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_emp_emergency_employee_id",
        "tpc_employee_emergency_contacts",
        ["employee_id"],
    )

    # =========================
    # EMPLOYMENT HISTORY
    # =========================
    op.create_table(
        "tpc_employee_employment_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("company_name", sa.String(150)),
        sa.Column("position", sa.String(150)),
        sa.Column("date_from", sa.Date()),
        sa.Column("date_to", sa.Date()),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["tpc_employees.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_emp_history_employee_id", "tpc_employee_employment_history", ["employee_id"]
    )

    # =========================
    # FAMILY (1-1)
    # =========================
    op.create_table(
        "tpc_employee_family_details",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("spouse_name", sa.String(150)),
        sa.Column("father_name", sa.String(150)),
        sa.Column("mother_name", sa.String(150)),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["tpc_employees.id"], ondelete="CASCADE"
        ),
    )

    # =========================
    # GOVERNMENT (1-1)
    # =========================
    op.create_table(
        "tpc_employee_government_details",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("sss_number", sa.String(50)),
        sa.Column("philhealth_number", sa.String(50)),
        sa.Column("pagibig_number", sa.String(50)),
        sa.Column("tin_number", sa.String(50)),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["tpc_employees.id"], ondelete="CASCADE"
        ),
    )

    # =========================
    # PERSONAL (1-1)
    # =========================
    op.create_table(
        "tpc_employee_personal_details",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("birthday", sa.Date()),
        sa.Column("birthplace", sa.String(150)),
        sa.Column("gender", sa.String(50)),
        sa.Column("civil_status", sa.String(50)),
        sa.Column("religion", sa.String(100)),
        sa.Column("citizenship", sa.String(100)),
        sa.Column("height", sa.String(50)),
        sa.Column("weight", sa.String(50)),
        sa.Column("language", sa.String(100)),
        sa.Column("contact_number", sa.String(50)),
        sa.Column("current_address", sa.String(255)),
        sa.Column("provincial_address", sa.String(255)),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["tpc_employees.id"], ondelete="CASCADE"
        ),
    )

    # =========================
    # REFERENCES
    # =========================
    op.create_table(
        "tpc_employee_references",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(150)),
        sa.Column("occupation", sa.String(150)),
        sa.Column("address", sa.String(255)),
        sa.Column("contact", sa.String(50)),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["tpc_employees.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_emp_ref_employee_id", "tpc_employee_references", ["employee_id"]
    )
    # ### end Alembic commands ###


def downgrade() -> None:

    op.drop_index("ix_emp_ref_employee_id", table_name="tpc_employee_references")
    op.drop_index(
        "ix_emp_history_employee_id", table_name="tpc_employee_employment_history"
    )
    op.drop_index(
        "ix_emp_emergency_employee_id", table_name="tpc_employee_emergency_contacts"
    )
    op.drop_index("ix_emp_edu_employee_id", table_name="tpc_employee_education")
    op.drop_index("ix_emp_docs_employee_id", table_name="tpc_employee_documents")

    op.drop_table("tpc_employee_references")
    op.drop_table("tpc_employee_personal_details")
    op.drop_table("tpc_employee_government_details")
    op.drop_table("tpc_employee_family_details")
    op.drop_table("tpc_employee_employment_history")
    op.drop_table("tpc_employee_emergency_contacts")
    op.drop_table("tpc_employee_education")
    op.drop_table("tpc_employee_documents")
    # ### end Alembic commands ###
