"""FeatureInterest model — captures user interest in gated/upcoming features.

Used by the InterestGate pattern: instead of putting a paywall in front of a
"Pro" feature when monetization isn't enabled yet, we collect the user's email
+ optional wishlist text. This generates Willingness-To-Pay (WTP) signal that
later informs pricing and feature prioritization.

Once paid checkout is wired up, the gate flips from `<InterestGate>` → real
billing; existing rows in this table become the warm waitlist to migrate.
"""

from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ceq_api.models.base import JSONB, Base, TimestampMixin


class FeatureInterest(Base, TimestampMixin):
    """One row per (email, feature_key) pair. Indexed for upsert lookup."""

    __tablename__ = "feature_interest"

    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        index=True,
        comment="User-provided email (lowercased, trimmed before insert).",
    )
    feature_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Feature identifier, e.g. premium_render | training_access | team_seats.",
    )
    wishlist: Mapped[dict | list | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Free-form structured wishlist — accepts list[str], dict, or "
            "{'text': '...'} for raw textarea input. Up to 2000 chars when text."
        ),
    )
    janua_user_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Janua subject ID when the user is signed in. Nullable for anon capture.",
    )
    source_page: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Page/component that triggered the gate (e.g. 'templates/3d').",
    )

    __table_args__ = (
        # Composite index on (email, feature_key) — supports the upsert lookup
        # in the POST handler. Not unique because the request endpoint enforces
        # idempotency in code (returns 200 on duplicate) and we may want to
        # tolerate eventual schema drift.
        Index("ix_feature_interest_email_feature", "email", "feature_key"),
        Index("ix_feature_interest_feature_created", "feature_key", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<FeatureInterest {self.email} -> {self.feature_key}>"
