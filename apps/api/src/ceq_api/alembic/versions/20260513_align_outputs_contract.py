"""align outputs table with current model contract

Revision ID: 20260513_align_outputs
Revises: 8a3f1c4e5d20
Create Date: 2026-05-13 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260513_align_outputs"
down_revision: str | None = "8a3f1c4e5d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("outputs", sa.Column("filename", sa.String(length=255), nullable=True))
    op.add_column("outputs", sa.Column("file_type", sa.String(length=100), nullable=True))
    op.add_column("outputs", sa.Column("file_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("outputs", sa.Column("preview_url", sa.String(length=2048), nullable=True))
    op.add_column("outputs", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("outputs", sa.Column("height", sa.Integer(), nullable=True))
    op.add_column("outputs", sa.Column("duration_seconds", sa.Float(), nullable=True))

    op.execute(
        """
        UPDATE outputs
        SET
          filename = COALESCE(NULLIF(regexp_replace(storage_uri, '^.*/', ''), ''), id::text),
          file_type = CASE output_type
            WHEN 'image' THEN 'image/png'
            WHEN 'video' THEN 'video/mp4'
            WHEN 'model' THEN 'model/gltf-binary'
            ELSE 'application/octet-stream'
          END,
          file_size_bytes = 0,
          preview_url = thumbnail_uri
        WHERE filename IS NULL
        """
    )

    op.alter_column("outputs", "filename", nullable=False)
    op.alter_column("outputs", "file_type", nullable=False)
    op.alter_column("outputs", "file_size_bytes", nullable=False)

    op.drop_column("outputs", "thumbnail_uri")
    op.drop_column("outputs", "output_type")


def downgrade() -> None:
    op.add_column("outputs", sa.Column("output_type", sa.String(length=50), nullable=True))
    op.add_column("outputs", sa.Column("thumbnail_uri", sa.String(length=2048), nullable=True))

    op.execute(
        """
        UPDATE outputs
        SET
          output_type = CASE
            WHEN file_type LIKE 'image/%' THEN 'image'
            WHEN file_type LIKE 'video/%' THEN 'video'
            WHEN file_type LIKE 'model/%' THEN 'model'
            ELSE 'file'
          END,
          thumbnail_uri = preview_url
        WHERE output_type IS NULL
        """
    )

    op.alter_column("outputs", "output_type", nullable=False)

    op.drop_column("outputs", "duration_seconds")
    op.drop_column("outputs", "height")
    op.drop_column("outputs", "width")
    op.drop_column("outputs", "preview_url")
    op.drop_column("outputs", "file_size_bytes")
    op.drop_column("outputs", "file_type")
    op.drop_column("outputs", "filename")
