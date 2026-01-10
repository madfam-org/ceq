"""Workflow model for user-created ComfyUI workflows."""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ceq_api.models.base import Base, GUIDString, JSONB, TimestampMixin


class Workflow(Base, TimestampMixin):
    """
    Workflow model for user-created or forked workflows.

    Each workflow contains a ComfyUI workflow definition and input schema.
    """

    __tablename__ = "workflows"

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Workflow definition
    workflow_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="ComfyUI workflow in API format",
    )
    input_schema: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="JSON Schema for workflow inputs",
    )

    # Metadata
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Ownership
    user_id: Mapped[UUID] = mapped_column(
        GUIDString(),
        nullable=False,
        index=True,
        comment="Janua user ID",
    )
    org_id: Mapped[UUID | None] = mapped_column(
        GUIDString(),
        nullable=True,
        index=True,
        comment="Janua organization ID",
    )

    # Template origin (if forked)
    template_id: Mapped[UUID | None] = mapped_column(
        GUIDString(),
        ForeignKey("templates.id", ondelete="SET NULL"),
        nullable=True,
        comment="Original template if forked",
    )

    # Visibility
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Soft delete flag",
    )

    # Relationships
    template = relationship("Template", lazy="selectin")
    jobs = relationship("Job", back_populates="workflow", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Workflow {self.name}>"
