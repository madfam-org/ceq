"""Asset model for models, LoRAs, VAEs, embeddings."""

from uuid import UUID

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ceq_api.models.base import Base, TimestampMixin


class Asset(Base, TimestampMixin):
    """
    Asset model representing ML models, LoRAs, VAEs, and embeddings.

    Stored in Cloudflare R2 bucket.
    """

    __tablename__ = "assets"

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="checkpoint | lora | vae | embedding | controlnet",
    )

    # Storage
    storage_uri: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="R2 URI (r2://bucket/key)",
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="SHA256 hash",
    )

    # Metadata
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    preview_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    asset_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Model-specific metadata (base model, triggers, etc.)",
    )

    # Ownership
    user_id: Mapped[UUID] = mapped_column(
        nullable=False,
        index=True,
        comment="Janua user ID",
    )
    org_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
        index=True,
        comment="Janua organization ID",
    )

    # Visibility
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Soft delete flag",
    )

    def __repr__(self) -> str:
        return f"<Asset {self.name} ({self.asset_type})>"
