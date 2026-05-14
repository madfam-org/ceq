"""add outputs job/storage idempotency constraint

Revision ID: 20260514_outputs_unique
Revises: 20260513_align_outputs
Create Date: 2026-05-14 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260514_outputs_unique"
down_revision: str | None = "20260513_align_outputs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked_outputs AS (
          SELECT
            id,
            ROW_NUMBER() OVER (
              PARTITION BY job_id, storage_uri
              ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
            ) AS row_number
          FROM outputs
        )
        DELETE FROM outputs
        WHERE id IN (
          SELECT id
          FROM ranked_outputs
          WHERE row_number > 1
        )
        """
    )
    op.create_unique_constraint(
        "uq_outputs_job_storage_uri",
        "outputs",
        ["job_id", "storage_uri"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_outputs_job_storage_uri",
        "outputs",
        type_="unique",
    )
