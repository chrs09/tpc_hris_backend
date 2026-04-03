"""add applicant onboarding tables

Revision ID: 4db3d4187a58
Revises: 9cae0cba54bc
Create Date: 2026-04-01 17:20:25.636069
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4db3d4187a58"
down_revision: Union[str, Sequence[str], None] = "9cae0cba54bc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------
    # tpc_applicants: add onboarding link / tracking fields
    # ---------------------------------------------------------
    op.add_column(
        "tpc_applicants",
        sa.Column("onboarding_token", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "tpc_applicants",
        sa.Column("onboarding_token_expires_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "tpc_applicants",
        sa.Column("onboarding_link_sent_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "tpc_applicants",
        sa.Column("onboarding_submitted_at", sa.DateTime(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_tpc_applicants_onboarding_token",
        "tpc_applicants",
        ["onboarding_token"],
    )

    # ---------------------------------------------------------
    # tpc_applicant_onboarding
    # ---------------------------------------------------------
    op.create_table(
        "tpc_applicant_onboarding",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("applicant_id", sa.Integer(), nullable=False),

        # basic
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=150), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("position", sa.String(length=150), nullable=True),
        sa.Column("date_hired", sa.Date(), nullable=True),

        # personal
        sa.Column("birthday", sa.Date(), nullable=True),
        sa.Column("birthplace", sa.String(length=150), nullable=True),
        sa.Column("gender", sa.String(length=50), nullable=True),
        sa.Column("civil_status", sa.String(length=50), nullable=True),
        sa.Column("religion", sa.String(length=100), nullable=True),
        sa.Column("citizenship", sa.String(length=100), nullable=True),
        sa.Column("height", sa.String(length=50), nullable=True),
        sa.Column("weight", sa.String(length=50), nullable=True),
        sa.Column("language", sa.String(length=100), nullable=True),
        sa.Column("contact_number", sa.String(length=50), nullable=True),
        sa.Column("current_address", sa.String(length=255), nullable=True),
        sa.Column("provincial_address", sa.String(length=255), nullable=True),

        # family
        sa.Column("spouse_name", sa.String(length=150), nullable=True),
        sa.Column("father_name", sa.String(length=150), nullable=True),
        sa.Column("mother_name", sa.String(length=150), nullable=True),

        # emergency
        sa.Column("emergency_contact_name", sa.String(length=150), nullable=True),
        sa.Column("emergency_contact_number", sa.String(length=50), nullable=True),
        sa.Column("emergency_relationship", sa.String(length=100), nullable=True),

        # government
        sa.Column("sss", sa.String(length=50), nullable=True),
        sa.Column("philhealth", sa.String(length=50), nullable=True),
        sa.Column("pagibig", sa.String(length=50), nullable=True),
        sa.Column("tin", sa.String(length=50), nullable=True),

        # tracking
        sa.Column("is_submitted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),

        sa.ForeignKeyConstraint(
            ["applicant_id"],
            ["tpc_applicants.id"],
            name="fk_tpc_applicant_onboarding_applicant_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("applicant_id", name="uq_tpc_applicant_onboarding_applicant_id"),
    )

    op.create_index(
        "ix_tpc_applicant_onboarding_id",
        "tpc_applicant_onboarding",
        ["id"],
        unique=False,
    )

    # ---------------------------------------------------------
    # tpc_applicant_education
    # ---------------------------------------------------------
    op.create_table(
        "tpc_applicant_education",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("applicant_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=100), nullable=True),
        sa.Column("institution", sa.String(length=255), nullable=True),
        sa.Column("degree", sa.String(length=255), nullable=True),
        sa.Column("year_from", sa.String(length=20), nullable=True),
        sa.Column("year_to", sa.String(length=20), nullable=True),
        sa.Column("skills", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["applicant_id"],
            ["tpc_applicants.id"],
            name="fk_tpc_applicant_education_applicant_id",
            ondelete="CASCADE",
        ),
    )

    op.create_index(
        "ix_tpc_applicant_education_id",
        "tpc_applicant_education",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_tpc_applicant_education_applicant_id",
        "tpc_applicant_education",
        ["applicant_id"],
        unique=False,
    )

    # ---------------------------------------------------------
    # tpc_applicant_employment_history
    # ---------------------------------------------------------
    op.create_table(
        "tpc_applicant_employment_history",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("applicant_id", sa.Integer(), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("position", sa.String(length=150), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["applicant_id"],
            ["tpc_applicants.id"],
            name="fk_tpc_applicant_employment_history_applicant_id",
            ondelete="CASCADE",
        ),
    )

    op.create_index(
        "ix_tpc_applicant_employment_history_id",
        "tpc_applicant_employment_history",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_tpc_applicant_employment_history_applicant_id",
        "tpc_applicant_employment_history",
        ["applicant_id"],
        unique=False,
    )

    # ---------------------------------------------------------
    # tpc_applicant_references
    # ---------------------------------------------------------
    op.create_table(
        "tpc_applicant_references",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("applicant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=True),
        sa.Column("occupation", sa.String(length=150), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("contact", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ["applicant_id"],
            ["tpc_applicants.id"],
            name="fk_tpc_applicant_references_applicant_id",
            ondelete="CASCADE",
        ),
    )

    op.create_index(
        "ix_tpc_applicant_references_id",
        "tpc_applicant_references",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_tpc_applicant_references_applicant_id",
        "tpc_applicant_references",
        ["applicant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tpc_applicant_references_applicant_id", table_name="tpc_applicant_references")
    op.drop_index("ix_tpc_applicant_references_id", table_name="tpc_applicant_references")
    op.drop_table("tpc_applicant_references")

    op.drop_index(
        "ix_tpc_applicant_employment_history_applicant_id",
        table_name="tpc_applicant_employment_history",
    )
    op.drop_index(
        "ix_tpc_applicant_employment_history_id",
        table_name="tpc_applicant_employment_history",
    )
    op.drop_table("tpc_applicant_employment_history")

    op.drop_index("ix_tpc_applicant_education_applicant_id", table_name="tpc_applicant_education")
    op.drop_index("ix_tpc_applicant_education_id", table_name="tpc_applicant_education")
    op.drop_table("tpc_applicant_education")

    op.drop_index("ix_tpc_applicant_onboarding_id", table_name="tpc_applicant_onboarding")
    op.drop_table("tpc_applicant_onboarding")

    op.drop_constraint("uq_tpc_applicants_onboarding_token", "tpc_applicants", type_="unique")
    op.drop_column("tpc_applicants", "onboarding_submitted_at")
    op.drop_column("tpc_applicants", "onboarding_link_sent_at")
    op.drop_column("tpc_applicants", "onboarding_token_expires_at")
    op.drop_column("tpc_applicants", "onboarding_token")