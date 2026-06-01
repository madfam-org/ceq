"""add credit ledger

Revision ID: 20260601_credit_ledger
Revises: 20260514_outputs_unique
Create Date: 2026-06-01 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260601_credit_ledger"
down_revision: str | None = "20260514_outputs_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credit_ledger_entries",
        sa.Column("user_id", sa.UUID(), nullable=False, comment="Janua user ID whose balance this entry affects"),
        sa.Column("org_id", sa.UUID(), nullable=True, comment="Janua organization ID, when present"),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("output_id", sa.UUID(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False, comment="Positive grants/refunds, negative debits"),
        sa.Column("transaction_type", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column(
            "idempotency_key",
            sa.String(length=255),
            nullable=False,
            comment="Stable caller-provided key preventing duplicate ledger entries",
        ),
        sa.Column("ledger_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["output_id"], ["outputs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_credit_ledger_idempotency_key"),
    )
    op.create_index(op.f("ix_credit_ledger_entries_user_id"), "credit_ledger_entries", ["user_id"], unique=False)
    op.create_index(op.f("ix_credit_ledger_entries_org_id"), "credit_ledger_entries", ["org_id"], unique=False)
    op.create_index(op.f("ix_credit_ledger_entries_job_id"), "credit_ledger_entries", ["job_id"], unique=False)
    op.create_index(op.f("ix_credit_ledger_entries_output_id"), "credit_ledger_entries", ["output_id"], unique=False)
    op.create_index(
        op.f("ix_credit_ledger_entries_transaction_type"),
        "credit_ledger_entries",
        ["transaction_type"],
        unique=False,
    )
    op.create_index("ix_credit_ledger_user_created", "credit_ledger_entries", ["user_id", "created_at"], unique=False)
    op.create_index("ix_credit_ledger_org_created", "credit_ledger_entries", ["org_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_credit_ledger_org_created", table_name="credit_ledger_entries")
    op.drop_index("ix_credit_ledger_user_created", table_name="credit_ledger_entries")
    op.drop_index(op.f("ix_credit_ledger_entries_transaction_type"), table_name="credit_ledger_entries")
    op.drop_index(op.f("ix_credit_ledger_entries_output_id"), table_name="credit_ledger_entries")
    op.drop_index(op.f("ix_credit_ledger_entries_job_id"), table_name="credit_ledger_entries")
    op.drop_index(op.f("ix_credit_ledger_entries_org_id"), table_name="credit_ledger_entries")
    op.drop_index(op.f("ix_credit_ledger_entries_user_id"), table_name="credit_ledger_entries")
    op.drop_table("credit_ledger_entries")
