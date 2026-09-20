"""Task 2: migrate all runtime case/CAMS structured data to PostgreSQL.

Revision ID: t2data0002
Revises: t1auth0001
Create Date: 2026-09-21

Adds documents, observations, twin_facts, conflicts, sync_history,
provenance and uploads (upload metadata; file bytes stay on disk).
``cases.id`` (UUID) is the internal FK everywhere; ``cases.case_number``
stays the external identifier (e.g. CASE-001).

Also alters ``cases``: adds ``description`` + ``is_demo`` and replaces the
unique case_number index with UniqueConstraint(case_number, is_demo) so a
demo case and a real case may share a case_number without collision.

JSON FileRepository is removed from the runtime path; old files under
data/ are intentionally left on disk and are never read by the app.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "t2data0002"
down_revision: Union[str, None] = "t1auth0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- cases: description + is_demo, composite unique case_number ----
    op.add_column(
        "cases", sa.Column("description", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "cases",
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.drop_index("ix_cases_case_number", table_name="cases")
    op.create_unique_constraint(
        "uq_cases_case_number_demo", "cases", ["case_number", "is_demo"]
    )
    op.create_index("ix_cases_case_number", "cases", ["case_number"], unique=False)

    # ---- documents ----
    op.create_table(
        "documents",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False, server_default="unknown"),
        sa.Column("source_type", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column("title", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "ingestion_time",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("extractor", sa.String(length=128), nullable=True),
        sa.Column("extractor_note", sa.Text(), nullable=True),
        sa.Column("ocr", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_id"),
    )
    op.create_index("ix_documents_case", "documents", ["case_id"], unique=False)

    # ---- observations (append-only) ----
    op.create_table(
        "observations",
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fact_key", sa.String(length=128), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=False, server_default="unknown"),
        sa.Column("source_type", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column(
            "event_time",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "ingestion_time",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "extraction_reliability",
            sa.Float(),
            nullable=False,
            server_default="0.7",
        ),
        sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="recorded"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.document_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("observation_id"),
    )
    op.create_index("ix_observations_case", "observations", ["case_id"], unique=False)
    op.create_index(
        "ix_observations_case_fact", "observations", ["case_id", "fact_key"], unique=False
    )

    # ---- twin_facts (current Digital Twin state) ----
    op.create_table(
        "twin_facts",
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fact_key", sa.String(length=128), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="unresolved"
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "supporting_observation_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("case_id", "fact_key"),
    )
    op.create_index("ix_twin_facts_case", "twin_facts", ["case_id"], unique=False)

    # ---- conflicts (unresolved/abstained facts) ----
    op.create_table(
        "conflicts",
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fact_key", sa.String(length=128), nullable=False),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="unresolved"
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("previous_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("C1", sa.Float(), nullable=True),
        sa.Column("C2", sa.Float(), nullable=True),
        sa.Column("margin", sa.Float(), nullable=True),
        sa.Column("candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("case_id", "fact_key"),
    )
    op.create_index("ix_conflicts_case", "conflicts", ["case_id"], unique=False)

    # ---- sync_history (append-only CAMS decisions) ----
    op.create_table(
        "sync_history",
        sa.Column("history_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fact_key", sa.String(length=128), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("decided", sa.Boolean(), nullable=False),
        sa.Column("selected_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("previous_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "unresolved", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("C1", sa.Float(), nullable=True),
        sa.Column("C2", sa.Float(), nullable=True),
        sa.Column("margin", sa.Float(), nullable=True),
        sa.Column("tau", sa.Float(), nullable=True),
        sa.Column("delta", sa.Float(), nullable=True),
        sa.Column("weights", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "supporting_observation_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("trigger_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trigger_observation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("history_id"),
    )
    op.create_index(
        "ix_sync_history_case_seq", "sync_history", ["case_id", "seq"], unique=False
    )

    # ---- provenance (append-only) ----
    op.create_table(
        "provenance",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fact_key", sa.String(length=128), nullable=False),
        sa.Column("history_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["history_id"], ["sync_history.history_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"], ["observations.observation_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_provenance_case_fact", "provenance", ["case_id", "fact_key"], unique=False
    )

    # ---- uploads (metadata; file bytes stay on disk) ----
    op.create_table(
        "uploads",
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False, server_default="unknown"),
        sa.Column("source_type", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column(
            "original_filename", sa.String(length=512), nullable=False, server_default=""
        ),
        sa.Column(
            "stored_filename", sa.String(length=512), nullable=False, server_default=""
        ),
        sa.Column("case_upload_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("stakeholder_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("extracted_text_path", sa.Text(), nullable=True),
        sa.Column("bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ocr_method", sa.String(length=128), nullable=True),
        sa.Column("ocr_note", sa.Text(), nullable=True),
        sa.Column(
            "saved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("upload_id"),
    )
    op.create_index("ix_uploads_case", "uploads", ["case_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_uploads_case", table_name="uploads")
    op.drop_table("uploads")

    op.drop_index("ix_provenance_case_fact", table_name="provenance")
    op.drop_table("provenance")

    op.drop_index("ix_sync_history_case_seq", table_name="sync_history")
    op.drop_table("sync_history")

    op.drop_index("ix_conflicts_case", table_name="conflicts")
    op.drop_table("conflicts")

    op.drop_index("ix_twin_facts_case", table_name="twin_facts")
    op.drop_table("twin_facts")

    op.drop_index("ix_observations_case_fact", table_name="observations")
    op.drop_index("ix_observations_case", table_name="observations")
    op.drop_table("observations")

    op.drop_index("ix_documents_case", table_name="documents")
    op.drop_table("documents")

    # ---- cases: revert alterations ----
    op.drop_index("ix_cases_case_number", table_name="cases")
    op.drop_constraint("uq_cases_case_number_demo", "cases", type_="unique")
    op.create_index("ix_cases_case_number", "cases", ["case_number"], unique=True)
    op.drop_column("cases", "is_demo")
    op.drop_column("cases", "description")
