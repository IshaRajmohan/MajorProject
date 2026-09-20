"""Task 3: case RBAC — document visibility + citizen submissions.

Revision ID: t3rbac0003
Revises: t2data0002
Create Date: 2026-09-21

Adds the two Task-3 schema pieces that are not expressible with the Task 1
tables alone:

* ``documents.visibility`` — ``INTERNAL | CITIZEN_VISIBLE`` (native enum
  ``document_visibility``). Existing rows default to INTERNAL; only an
  assigned COURT user may set CITIZEN_VISIBLE (enforced in rbac.py).
* ``submissions`` — citizen text submissions that stay PENDING (no
  extraction, no CAMS) until an assigned COURT user reviews them. Approval
  feeds the text through the normal pipeline and links the created
  ``documents`` row; rejection only changes the status.

RBAC itself (case_access, case_role, capabilities, resource filtering) needs
no new tables: it is enforced in rbac.py + main.py on top of ``case_access``.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "t3rbac0003"
down_revision: Union[str, None] = "t2data0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

document_visibility = postgresql.ENUM(
    "INTERNAL", "CITIZEN_VISIBLE", name="document_visibility", create_type=False
)
submission_status = postgresql.ENUM(
    "PENDING", "APPROVED", "REJECTED", name="submission_status", create_type=False
)


def upgrade() -> None:
    op.execute("CREATE TYPE document_visibility AS ENUM ('INTERNAL','CITIZEN_VISIBLE')")
    op.execute("CREATE TYPE submission_status AS ENUM ('PENDING','APPROVED','REJECTED')")

    # ---- documents: explicit visibility ----
    op.add_column(
        "documents",
        sa.Column(
            "visibility",
            document_visibility,
            nullable=False,
            server_default="INTERNAL",
        ),
    )

    # ---- submissions (citizen → COURT review workflow) ----
    op.create_table(
        "submissions",
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status", submission_status, nullable=False, server_default="PENDING"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.document_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("submission_id"),
    )
    op.create_index(
        "ix_submissions_case_status", "submissions", ["case_id", "status"], unique=False
    )
    op.create_index(
        "ix_submissions_submitted_by", "submissions", ["submitted_by"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_submissions_submitted_by", table_name="submissions")
    op.drop_index("ix_submissions_case_status", table_name="submissions")
    op.drop_table("submissions")

    op.drop_column("documents", "visibility")

    op.execute("DROP TYPE submission_status")
    op.execute("DROP TYPE document_visibility")
