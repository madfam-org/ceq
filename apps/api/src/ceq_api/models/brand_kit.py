"""BrandKit model — a client's brand book as structured source-of-truth.

This is the *queryable, non-binary* half of the DAM: named color tokens,
typography, logo-variant references, and usage guidelines. The binary bytes
(logo PNG/SVG, font files, guideline PDFs) live in :class:`BrandAsset`, stored
in R2 like ceq's existing ``Asset``.

Consumer contract
------------------
MAP, crea-frontend, and ceq's own ``/v1/render`` pipeline align on brand by
pulling the resolved token document (see ``GET /v1/brand-kits/{id}/tokens``).
That export is built from the structured columns below, so their shapes are a
public-ish contract — hence the thorough field-by-field documentation. A
consumer must be able to pull a *named* token (``palette.brand``,
``typography.heading.family``, ``logos.primary`` -> a resolvable asset), not
just an opaque blob.

Versioning choice (documented trade-off)
----------------------------------------
A brand book changes over time and an alignment should be able to pin a known
brand version. Full append-only row history (a ``brand_kit_versions`` table
snapshotting every edit) is heavier than this milestone needs, so this model
uses a **monotonic ``version`` integer + soft update**: ``PATCH`` bumps
``version`` and updates the structured columns in place, and consumers that must
pin record the ``version`` they aligned against. ``version`` is exposed in the
token export so a pin is meaningful. Full per-edit history is a deliberate
deferral, not an oversight — the ``version`` counter is the seam a future
history table would hang off without changing the read contract.
"""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ceq_api.models.base import JSONB, Base, GUIDString, TimestampMixin


class BrandKit(Base, TimestampMixin):
    """A client's brand book as structured, tenant-scoped source-of-truth.

    One client may hold several kits (e.g. a primary brand plus a sub-brand),
    each identified within the tenant by :attr:`name`. Access is always scoped
    to the owning :attr:`client_id`, which is resolved from the caller's Janua
    org — never from the URL.
    """

    __tablename__ = "brand_kits"
    __table_args__ = (
        # A kit name is unique *within a client*, not globally — two tenants may
        # both have a kit called "Primary". This is what lets a consumer address
        # a kit by (tenant, name) if it ever needs to, without cross-tenant clash.
        UniqueConstraint("client_id", "name", name="uq_brand_kit_client_name"),
    )

    # Owning tenant. FK to brand_clients so a kit cannot outlive its client, and
    # indexed because every list/read filters by it. This column — resolved from
    # the token — is the tenant fence for the whole kit and its assets.
    client_id: Mapped[UUID] = mapped_column(
        GUIDString(),
        ForeignKey("brand_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning tenant (Client). Resolved from the Janua token, never the URL.",
    )

    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="Kit name, unique within the client (e.g. 'Primary', 'Kids Sub-brand')",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Monotonic version. Starts at 1, bumped on every structured PATCH. Pinnable
    # by consumers; surfaced in the token export.
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Monotonic brand-book version; bumped on each structured update",
    )

    # --- Structured brand data (JSONB; shapes are the consumer contract) ------
    #
    # palette: named color tokens keyed by ROLE, so a consumer pulls
    #   palette["brand"] rather than guessing a hex. Recommended roles:
    #     brand, brandStrong, accent, accentSoft, ink, surface, bg, muted,
    #     ok, warn, danger
    #   Each value is either a hex string ("#7C5CFF") or a light/dark object
    #   ({"light": "#...", "dark": "#..."}) where the token differs by theme.
    #   The token export normalizes both forms (see routers/brand_kits.py).
    palette: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Named color tokens: role -> hex | {light,dark}. Consumer-addressable.",
    )

    # typography: font roles -> family/weights/scale.
    #   {"heading": {"family": "Space Grotesk", "weights": [500, 700],
    #                "fallback": "sans-serif"},
    #    "body":    {"family": "Inter", "weights": [400, 600]},
    #    "mono":    {"family": "JetBrains Mono", "weights": [400]},
    #    "scale":   {"base": 16, "ratio": 1.25}}   # optional type scale
    typography: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Font roles (heading/body/mono) -> family, weights, optional scale.",
    )

    # logos: logical logo variant -> the BrandAsset that realizes it.
    #   {"primary":  "<brand_asset_id>",
    #    "inverse":  "<brand_asset_id>",
    #    "mark":     "<brand_asset_id>",
    #    "wordmark": "<brand_asset_id>"}
    #   Values are BrandAsset ids (as strings). The token export resolves each id
    #   to a presigned/public URL so consumers get a fetchable logo without
    #   knowing R2 layout. Stored as ids (not URLs) so a re-uploaded asset does
    #   not require rewriting the kit — the URL is resolved fresh on export.
    logos: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Logical logo variant -> BrandAsset id. Resolved to URLs on export.",
    )

    # guidelines: structured usage rules + freeform notes.
    #   {"clear_space": "1x cap-height on all sides",
    #    "min_size_px": 24,
    #    "tagline": "Crea tu mundo",
    #    "voice": "Playful, direct, second-person",
    #    "do":   ["Use on dark surfaces", ...],
    #    "dont": ["Never recolor the mark", ...],
    #    "notes": "Freeform prose the structured fields don't capture."}
    guidelines: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Usage rules: clear_space, min_size, tagline, voice, do/dont, notes.",
    )

    # Soft-deactivation. A deactivated kit is retained but hidden from active
    # listings and refused for writes — no destructive delete of brand history.
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Soft-deactivation flag; kit data is retained when False",
    )

    client: Mapped["Client"] = relationship(  # noqa: F821
        "Client",
        back_populates="brand_kits",
        lazy="selectin",
    )
    assets: Mapped[list["BrandAsset"]] = relationship(  # noqa: F821
        "BrandAsset",
        back_populates="brand_kit",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<BrandKit {self.name} v{self.version} (client={self.client_id})>"
