"""Person C ODFS versions + twin version pointer.

Revision ID: 003_person_c_odfs
Revises: 002_person_c
Create Date: 2026-09-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_person_c_odfs"
down_revision: Union[str, None] = "002_person_c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "twin_state",
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_unique_constraint(
        "uq_fact_keys_case_entity_name",
        "fact_keys",
        ["case_id", "entity_id", "fact_name"],
    )
    op.create_table(
        "twin_state_versions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("twin_state_id", sa.String(), nullable=False),
        sa.Column("fact_key_id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_observation_id", sa.String(), nullable=True),
        sa.Column("sync_decision_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fact_key_id", "version", name="uq_twin_versions_fact_version"),
    )
    op.create_index("ix_twin_state_versions_twin_state_id", "twin_state_versions", ["twin_state_id"])
    op.create_index("ix_twin_state_versions_fact_key_id", "twin_state_versions", ["fact_key_id"])
    op.create_index("ix_twin_state_versions_case_id", "twin_state_versions", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_twin_state_versions_case_id", table_name="twin_state_versions")
    op.drop_index("ix_twin_state_versions_fact_key_id", table_name="twin_state_versions")
    op.drop_index("ix_twin_state_versions_twin_state_id", table_name="twin_state_versions")
    op.drop_table("twin_state_versions")
    op.drop_constraint("uq_fact_keys_case_entity_name", "fact_keys", type_="unique")
    op.drop_column("twin_state", "version")
