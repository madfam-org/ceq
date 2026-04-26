"""add feature_interest table

Revision ID: 8a3f1c4e5d20
Revises: 0d39ee97cdbd
Create Date: 2026-04-25 12:00:00.000000

Adds the `feature_interest` table backing the InterestGate component
(POST /v1/interest/). Captures email + feature_key tuples plus an optional
JSON wishlist, while monetization is still in WTP-discovery mode.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8a3f1c4e5d20"
down_revision: str | None = "0d39ee97cdbd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_interest",
        sa.Column(
            "email",
            sa.String(length=320),
            nullable=False,
            comment="User-provided email (lowercased, trimmed before insert).",
        ),
        sa.Column(
            "feature_key",
            sa.String(length=64),
            nullable=False,
            comment="Feature identifier, e.g. premium_render | training_access | team_seats.",
        ),
        sa.Column(
            "wishlist",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Free-form structured wishlist; up to 2000 chars when stored as text.",
        ),
        sa.Column(
            "janua_user_id",
            sa.String(length=64),
            nullable=True,
            comment="Janua subject ID when the user is signed in.",
        ),
        sa.Column(
            "source_page",
            sa.String(length=255),
            nullable=True,
            comment="Page/component that triggered the gate.",
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_feature_interest_email"),
        "feature_interest",
        ["email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feature_interest_feature_key"),
        "feature_interest",
        ["feature_key"],
        unique=False,
    )
    op.create_index(
        "ix_feature_interest_email_feature",
        "feature_interest",
        ["email", "feature_key"],
        unique=False,
    )
    op.create_index(
        "ix_feature_interest_feature_created",
        "feature_interest",
        ["feature_key", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_feature_interest_feature_created", table_name="feature_interest")
    op.drop_index("ix_feature_interest_email_feature", table_name="feature_interest")
    op.drop_index(op.f("ix_feature_interest_feature_key"), table_name="feature_interest")
    op.drop_index(op.f("ix_feature_interest_email"), table_name="feature_interest")
    op.drop_table("feature_interest")
