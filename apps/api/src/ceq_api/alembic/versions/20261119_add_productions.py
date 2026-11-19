"""add productions and the job columns that tie a job to one

RFC 0061: a production is a small directed graph of jobs. This adds the
``productions`` table and four nullable-or-defaulted columns on ``jobs``.

Safe while the previous API version is serving: every new ``jobs`` column is
nullable or has a server default, so an older pod's INSERT is unaffected, and
no existing row changes meaning (``production_id`` null = a job on its own).

Revision ID: 20261119_productions
Revises: 20261118_job_kind
Create Date: 2026-11-19 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20261119_productions"
down_revision: str | None = "20261118_job_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fail fast instead of queueing behind an open transaction on `jobs`.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.create_table(
        "productions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column(
            "spec",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_productions_user_id", "productions", ["user_id"])
    op.create_index("ix_productions_client_id", "productions", ["client_id"])

    op.add_column("jobs", sa.Column("production_id", sa.UUID(), nullable=True))
    op.add_column("jobs", sa.Column("step", sa.String(length=64), nullable=True))
    op.add_column(
        "jobs",
        sa.Column(
            "depends_on",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "jobs", sa.Column("released_at", sa.DateTime(timezone=True), nullable=True)
    )
    # NOT VALID: no existing row has a production_id, so there is nothing to
    # check, and skipping the scan keeps the lock on `jobs` short.
    op.create_foreign_key(
        "fk_jobs_production_id",
        "jobs",
        "productions",
        ["production_id"],
        ["id"],
        ondelete="CASCADE",
        postgresql_not_valid=True,
    )
    op.execute("ALTER TABLE jobs VALIDATE CONSTRAINT fk_jobs_production_id")
    # Partial: only production jobs are ever looked up this way.
    op.create_index(
        "ix_jobs_production_id",
        "jobs",
        ["production_id"],
        postgresql_where=sa.text("production_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_production_id", table_name="jobs")
    op.drop_constraint("fk_jobs_production_id", "jobs", type_="foreignkey")
    op.drop_column("jobs", "released_at")
    op.drop_column("jobs", "depends_on")
    op.drop_column("jobs", "step")
    op.drop_column("jobs", "production_id")
    op.drop_index("ix_productions_client_id", table_name="productions")
    op.drop_index("ix_productions_user_id", table_name="productions")
    op.drop_table("productions")
