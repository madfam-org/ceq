"""Client (tenant) model for the multi-tenant brand-asset DAM.

A ``Client`` is the tenant root of the curated brand-asset layer: the client
organization whose brand book ceq holds as system-of-record (e.g. "Crea Tu
Mundo"). It is deliberately distinct from ceq's per-principal scratch ``Asset``
model — brand data is durable, curated, and tenant-scoped, not user-scratch.

Tenancy binding (the security-critical decision)
------------------------------------------------
The tenant a caller belongs to is derived from the **Janua token**, never from
the URL. ``janua_org_id`` maps a Janua organization/tenant claim
(``JanuaUser.org_id``, populated from the token's ``org_id``/``tenant_id``
claim) to exactly one ``Client`` row. Every brand-kit route resolves the caller's
``Client`` from ``user.org_id`` and scopes all reads/writes to it, so a caller
authenticated for tenant A can never name tenant B's client_id in a path/query
and read across the boundary. This mirrors the acervo repo's contract: the
tenant comes from auth, and no route names a tenant in its path.
"""

from uuid import UUID

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ceq_api.models.base import Base, GUIDString, TimestampMixin


class Client(Base, TimestampMixin):
    """A tenant/client organization whose brand book ceq curates.

    One ``Client`` per Janua organization. The ``janua_org_id`` binding is what
    turns a token into a tenant scope — it is unique so a Janua org resolves to
    exactly one client, and indexed because every brand-kit request looks the
    client up by it on the hot path.
    """

    __tablename__ = "brand_clients"

    # Janua organization/tenant this client maps to. This is the ONLY tenant
    # key the API trusts — it comes from the verified token's org claim, and a
    # caller cannot supply it via the URL. Unique so a Janua org has at most one
    # brand client; nullable=False because a client with no tenant binding could
    # never be reached (and must never be reachable by a tenant-less caller).
    janua_org_id: Mapped[UUID] = mapped_column(
        GUIDString(),
        nullable=False,
        unique=True,
        index=True,
        comment="Janua organization/tenant ID this client is bound to (from the token, not the URL)",
    )

    # Stable human-facing key used in R2 key layout and logs (e.g. "crea-tu-mundo").
    # Slug is derived server-side from the display name at creation and is unique
    # so brand-kit object keys never collide across tenants.
    slug: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        unique=True,
        index=True,
        comment="URL/storage-safe stable key, e.g. 'crea-tu-mundo'",
    )

    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable client/org name, e.g. 'Crea Tu Mundo'",
    )

    # Soft-deactivation instead of destructive delete. A deactivated client's
    # brand data is retained (source-of-record durability) but the API refuses
    # new writes and hides it from active listings.
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Soft-deactivation flag; brand data is retained when False",
    )

    # A client owns its brand kits. Kept append-only at the API layer (versions
    # accrue; nothing is destructively replaced).
    brand_kits: Mapped[list["BrandKit"]] = relationship(  # noqa: F821
        "BrandKit",
        back_populates="client",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Client {self.slug} ({self.display_name})>"
