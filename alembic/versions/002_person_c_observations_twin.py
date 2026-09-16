"""Person C schema: observations, twin, CAMS config.

Revision ID: 002_person_c
Revises: 001_person_a
Create Date: 2026-09-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_person_c"
down_revision: Union[str, None] = "001_person_a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fact_keys",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("fact_name", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fact_keys_case_id", "fact_keys", ["case_id"])
    op.create_index("ix_fact_keys_entity_id", "fact_keys", ["entity_id"])

    op.create_table(
        "observations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("fact_key_id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("source_role", sa.String(length=20), nullable=False),
        sa.Column("candidate_value", sa.JSON(), nullable=False),
        sa.Column("event_time", sa.DateTime(), nullable=True),
        sa.Column("ingestion_time", sa.DateTime(), nullable=False),
        sa.Column("extraction_reliability", sa.Float(), nullable=False),
        sa.Column("raw_source_ref", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_observations_fact_key_id", "observations", ["fact_key_id"])
    op.create_index("ix_observations_case_id", "observations", ["case_id"])

    op.create_table(
        "twin_state",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("fact_key_id", sa.String(), nullable=False),
        sa.Column("current_value", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_observation_id", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fact_key_id"),
    )
    op.create_index("ix_twin_state_case_id", "twin_state", ["case_id"])
    op.create_index("ix_twin_state_fact_key_id", "twin_state", ["fact_key_id"], unique=True)

    op.create_table(
        "sync_decisions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("fact_key_id", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("winning_observation_id", sa.String(), nullable=True),
        sa.Column("candidates_snapshot", sa.JSON(), nullable=False),
        sa.Column("c1", sa.Float(), nullable=False),
        sa.Column("c2", sa.Float(), nullable=True),
        sa.Column("tau", sa.Float(), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("explanation", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_decisions_fact_key_id", "sync_decisions", ["fact_key_id"])

    op.create_table(
        "source_authority_rules",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("fact_type", sa.String(length=120), nullable=False),
        sa.Column("source_role", sa.String(length=20), nullable=False),
        sa.Column("authority_score", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "cams_config",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=True),
        sa.Column("weight_authority", sa.Float(), nullable=False),
        sa.Column("weight_temporal", sa.Float(), nullable=False),
        sa.Column("weight_corroboration", sa.Float(), nullable=False),
        sa.Column("weight_extraction", sa.Float(), nullable=False),
        sa.Column("tau", sa.Float(), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("cams_config")
    op.drop_table("source_authority_rules")
    op.drop_index("ix_sync_decisions_fact_key_id", table_name="sync_decisions")
    op.drop_table("sync_decisions")
    op.drop_index("ix_twin_state_fact_key_id", table_name="twin_state")
    op.drop_index("ix_twin_state_case_id", table_name="twin_state")
    op.drop_table("twin_state")
    op.drop_index("ix_observations_case_id", table_name="observations")
    op.drop_index("ix_observations_fact_key_id", table_name="observations")
    op.drop_table("observations")
    op.drop_index("ix_fact_keys_entity_id", table_name="fact_keys")
    op.drop_index("ix_fact_keys_case_id", table_name="fact_keys")
    op.drop_table("fact_keys")
