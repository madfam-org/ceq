"""Job model for workflow execution tracking."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ceq_api.models.base import Base, GUIDString, JSONB, TimestampMixin


class JobStatus(str, Enum):
    """Job execution status."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(Base, TimestampMixin):
    """
    Job model for tracking workflow executions.

    Each job represents a single execution of a workflow with specific parameters.
    """

    __tablename__ = "jobs"

    # References
    workflow_id: Mapped[UUID] = mapped_column(
        GUIDString(),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        GUIDString(),
        nullable=False,
        index=True,
        comment="Janua user ID",
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=JobStatus.QUEUED.value,
        index=True,
    )
    progress: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="0.0 to 1.0",
    )
    current_node: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Currently executing node ID",
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Input/Output
    input_params: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Input parameters for this run",
    )
    output_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Execution metadata (timings, vram, etc.)",
    )

    # Execution options
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="0-10, higher = more urgent",
    )
    webhook_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
        comment="URL to POST results",
    )

    # Timing
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Worker info
    worker_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Worker that processed this job",
    )
    gpu_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    cold_start_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Relationships
    workflow = relationship("Workflow", back_populates="jobs", lazy="selectin")
    outputs = relationship("Output", back_populates="job", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Job {self.id} ({self.status})>"
