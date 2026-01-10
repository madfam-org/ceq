"""Output model for generated content."""

from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ceq_api.models.base import Base, TimestampMixin


class Output(Base, TimestampMixin):
    """
    Output model for generated content.

    Each output is linked to a job and stored in Cloudflare R2.
    """

    __tablename__ = "outputs"

    # References
    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        nullable=False,
        index=True,
        comment="Janua user ID",
    )

    # Content type
    output_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="image | video | model",
    )

    # Storage
    storage_uri: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="R2 URI for full output",
    )
    thumbnail_uri: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
        comment="R2 URI for thumbnail",
    )

    # Metadata
    output_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Output-specific metadata (dimensions, duration, etc.)",
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
        return f"<Output {self.id} ({self.output_type})>"
