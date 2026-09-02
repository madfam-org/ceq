"""BrandAsset model — a single binary file inside a client's brand kit.

Mirrors the storage shape of ceq's existing ``Asset`` (``storage_uri``,
``size_bytes``, ``checksum``, ``content_type``) but is **tenant-scoped and
curated** rather than per-principal scratch: it belongs to a :class:`BrandKit`
(and, transitively, a :class:`Client`), not to a ``user_id``. The bytes live in
the same Cloudflare R2 bucket, reached through the shared ``StorageClient``.

R2 key layout (tenant-scoped, versioned)
----------------------------------------
    brand-kits/{client_slug}/{kit_version}/{kind}/{asset_id}_{filename}

The client slug fences tenants apart in the object namespace, the kit version
lets a version's assets be reasoned about as a set, and ``kind`` groups by role.
The ``asset_id`` prefix guarantees uniqueness even for identical filenames.
"""

from uuid import UUID

from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ceq_api.models.base import JSONB, Base, GUIDString, TimestampMixin

# Recognized asset roles. Kept permissive (validated at the router, not the DB)
# so a new role does not require a migration — a brand book is an evolving thing.
BRAND_ASSET_KINDS = (
    "logo-primary",
    "logo-inverse",
    "logo-mark",
    "logo-wordmark",
    "font",
    "guideline-pdf",
    "photo",
    "icon",
    "other",
)


class BrandAsset(Base, TimestampMixin):
    """A binary brand file (logo, font, guideline PDF, photo) stored in R2.

    Belongs to a :class:`BrandKit`; the ``client_id`` is denormalized onto the
    row so tenant-scoped queries and the ownership fence never need to join
    through the kit. Both are set from the resolved tenant at upload time.
    """

    __tablename__ = "brand_assets"

    # Owning kit. FK with CASCADE so assets do not outlive their kit row.
    brand_kit_id: Mapped[UUID] = mapped_column(
        GUIDString(),
        ForeignKey("brand_kits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning BrandKit",
    )
    # Denormalized tenant for a cheap, join-free ownership fence. Always equals
    # the owning kit's client_id; set from the Janua-resolved tenant, not the URL.
    client_id: Mapped[UUID] = mapped_column(
        GUIDString(),
        ForeignKey("brand_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning tenant (denormalized from the kit for join-free scoping)",
    )

    # Logical role of this file within the kit (see BRAND_ASSET_KINDS).
    kind: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
        comment="Role: logo-primary | logo-inverse | font | guideline-pdf | photo | ...",
    )
    # Optional colorway/variant discriminator (e.g. "dark", "light", "mono").
    # Lets a kit hold the same logical kind in several colorways.
    variant: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True,
        comment="Optional colorway/variant, e.g. 'dark' | 'light' | 'mono'",
    )

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Sanitized original filename (display + download name)",
    )

    # --- Storage (mirrors Asset) ---------------------------------------------
    storage_uri: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="R2 URI (r2://bucket/key)",
    )
    content_type: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="application/octet-stream",
        comment="MIME type of the stored bytes",
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="SHA256 hash of the uploaded bytes",
    )

    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Soft-deactivation, never destructive delete — brand history is retained.
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Soft-deactivation flag; asset row + bytes are retained when False",
    )

    brand_kit: Mapped["BrandKit"] = relationship(  # noqa: F821
        "BrandKit",
        back_populates="assets",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<BrandAsset {self.kind} {self.filename} (kit={self.brand_kit_id})>"
