"""Template model for pre-built ComfyUI workflows."""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ceq_api.models.base import JSONB, Base, TimestampMixin


class Template(Base, TimestampMixin):
    """
    Template model for pre-built workflows.

    Templates are curated workflows that users can fork or run directly.
    """

    __tablename__ = "templates"

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="social | video | 3d | utility",
    )

    # Workflow definition
    workflow_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="ComfyUI workflow in API format",
    )
    input_schema: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="JSON Schema for workflow inputs",
    )

    # Display
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    thumbnail_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    preview_urls: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Requirements
    model_requirements: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Required model names",
    )
    vram_requirement_gb: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=16,
        comment="Minimum VRAM in GB",
    )

    # Stats
    fork_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<Template {self.name} ({self.category})>"
