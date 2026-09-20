"""Task 1: auth + case-RBAC foundation (users, cases, case_access).

Revision ID: t1auth0001
Revises:
Create Date: 2026-09-21

PostgreSQL is authoritative for these three tables only. Case content
(documents, observations, twin facts, conflicts, history, provenance) remains
in the JSON FileRepository and is intentionally not migrated here.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "t1auth0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Shared enum types. Created explicitly above; tables reference them with
# create_type=False so alembic does not try to re-create them per table.
system_role = postgresql.ENUM(
    "ADMIN", "COURT", "POLICE", "LAWYER", "FORENSIC", "CITIZEN",
    name="system_role",
    create_type=False,
)
access_status = postgresql.ENUM(
    "ACTIVE", "REVOKED",
    name="access_status",
    create_type=False,
)


def upgrade() -> None:
    op.execute("CREATE TYPE system_role AS ENUM ('ADMIN','COURT','POLICE','LAWYER','FORENSIC','CITIZEN')")
    op.execute("CREATE TYPE access_status AS ENUM ('ACTIVE','REVOKED')")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("system_role", system_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_number", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("case_type", sa.String(length=128), nullable=True),
        sa.Column(
            "case_status",
            sa.String(length=64),
            nullable=False,
            server_default="OPEN",
        ),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("court_name", sa.String(length=256), nullable=True),
        sa.Column("next_hearing_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cases_case_number", "cases", ["case_number"], unique=True)

    op.create_table(
        "case_access",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_role", system_role, nullable=False),
        sa.Column(
            "status",
            access_status,
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "case_id", name="uq_case_access_user_case"),
    )
    op.create_index(
        "ix_case_access_case_status", "case_access", ["case_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_case_access_case_status", table_name="case_access")
    op.drop_table("case_access")
    op.drop_index("ix_cases_case_number", table_name="cases")
    op.drop_table("cases")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.execute("DROP TYPE access_status")
    op.execute("DROP TYPE system_role")
