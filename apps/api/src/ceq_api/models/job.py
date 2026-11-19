"""Job model for workflow execution tracking."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from ceq_api.job_kinds import DEFAULT_JOB_KIND, JOB_KINDS, validate_job_kind
from ceq_api.models.base import JSONB, Base, GUIDString, TimestampMixin


class JobStatus(StrEnum):
    """Job execution status."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(Base, TimestampMixin):
    """
    Job model for tracking executions.

    A job has a ``kind`` (see ``ceq_api.job_kinds``). A ``comfy`` job is a single
    execution of a workflow with specific parameters and always has a
    ``workflow_id``. The other kinds (RFC 0061: capture, edit, export) are not
    ComfyUI graphs and carry no workflow.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "kind IN ({})".format(", ".join(f"'{k}'" for k in JOB_KINDS)),
            name="ck_jobs_kind",
        ),
        # The guarantee the old NOT NULL gave, kept for the kind it applied to.
        CheckConstraint(
            "kind <> 'comfy' OR workflow_id IS NOT NULL",
            name="ck_jobs_comfy_has_workflow",
        ),
    )

    # What this job is, and therefore which worker capability can run it.
    kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DEFAULT_JOB_KIND,
        server_default=DEFAULT_JOB_KIND,
        comment="Job kind (closed set, see ceq_api.job_kinds)",
    )

    # References
    workflow_id: Mapped[UUID | None] = mapped_column(
        GUIDString(),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="ComfyUI workflow; null for non-comfy kinds",
    )
    user_id: Mapped[UUID] = mapped_column(
        GUIDString(),
        nullable=False,
        index=True,
        comment="Janua user ID",
    )

    # Production membership (RFC 0061). All null/empty for a job submitted on
    # its own, which is every job that predates productions.
    production_id: Mapped[UUID | None] = mapped_column(
        GUIDString(),
        ForeignKey("productions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    step: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Name of this job within its production",
    )
    depends_on: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="Step names in the same production that must complete first",
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When a production job was put on its queue; null while it waits on a step",
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

    @validates("kind")
    def _validate_kind(self, _key: str, value: str) -> str:
        """Reject a kind outside the closed set before it reaches the database."""
        return validate_job_kind(value)

    def __repr__(self) -> str:
        return f"<Job {self.id} {self.kind} ({self.status})>"
