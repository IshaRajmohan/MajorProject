"""Initial Person A schema: users, cases, entities.

Revision ID: 001_person_a
Revises:
Create Date: 2026-09-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_person_a"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("org", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "cases",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_number", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_number"),
    )
    op.create_index("ix_cases_case_number", "cases", ["case_number"], unique=True)

    op.create_table(
        "entities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entities_case_id", "entities", ["case_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_entities_case_id", table_name="entities")
    op.drop_table("entities")
    op.drop_index("ix_cases_case_number", table_name="cases")
    op.drop_table("cases")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
