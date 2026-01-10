"""Output model for generated content."""

from uuid import UUID

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ceq_api.models.base import Base, GUIDString, JSONB, TimestampMixin


class Output(Base, TimestampMixin):
    """
    Output model for generated content.

    Each output is linked to a job and stored in Cloudflare R2.
    """

    __tablename__ = "outputs"

    # References
    job_id: Mapped[UUID] = mapped_column(
        GUIDString(),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        GUIDString(),
        nullable=False,
        index=True,
        comment="Janua user ID",
    )

    # File info
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Original filename",
    )
    file_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="MIME type (image/png, video/mp4, etc.)",
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="File size in bytes",
    )

    # Storage
    storage_uri: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="R2 URI for full output",
    )
    preview_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
        comment="URL for preview/thumbnail",
    )

    # Dimensions (for images and videos)
    width: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Width in pixels",
    )
    height: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Height in pixels",
    )
    duration_seconds: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Duration for video/audio outputs",
    )

    # Metadata
    output_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Output-specific metadata",
    )

    # Publishing
    published_to: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="List of {channel, url, published_at}",
    )

    # Relationships
    job = relationship("Job", back_populates="outputs", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Output {self.id} ({self.file_type})>"
