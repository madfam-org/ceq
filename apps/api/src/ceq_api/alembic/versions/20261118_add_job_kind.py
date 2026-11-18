"""add job kind, make jobs.workflow_id nullable

RFC 0061 (the cinematic production pipeline) gives every job a kind. Until now
every job was a ComfyUI graph, so ``jobs.workflow_id`` was NOT NULL. The new
kinds (capture, edit, export) are CPU jobs with no workflow.

Safe to apply while the previous API version is still serving (the PreSync
migration job runs before the Deployments roll): ``kind`` has a server default,
so an old pod's INSERT that does not name the column yields ``comfy``, and every
existing row reads as ``comfy``. Relaxing NOT NULL does not affect a writer that
always sets ``workflow_id``.

The list in ``ck_jobs_kind`` is frozen here on purpose: a migration must not
change meaning when ``ceq_api.job_kinds`` later grows. Adding a kind is a new
migration that replaces the constraint.

Downgrade restores NOT NULL and therefore fails, deliberately, if any
non-comfy job row exists; remove or archive those rows first.

Revision ID: 20261118_job_kind
Revises: 20260901_brand_dam
Create Date: 2026-11-18 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261118_job_kind"
down_revision: str | None = "20260901_brand_dam"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JOB_KINDS = (
    "comfy",
    "capture.journey",
    "capture.stage",
    "capture.page",
    "edit",
    "export",
)


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "kind",
            sa.String(length=32),
            nullable=False,
            server_default="comfy",
            comment="Job kind (closed set, see ceq_api.job_kinds)",
        ),
    )
    op.create_index(op.f("ix_jobs_kind"), "jobs", ["kind"], unique=False)
    op.alter_column(
        "jobs",
        "workflow_id",
        existing_type=sa.UUID(),
        nullable=True,
        comment="ComfyUI workflow; null for non-comfy kinds",
    )
    op.create_check_constraint(
        "ck_jobs_kind",
        "jobs",
        "kind IN ({})".format(", ".join(f"'{kind}'" for kind in JOB_KINDS)),
    )
    op.create_check_constraint(
        "ck_jobs_comfy_has_workflow",
        "jobs",
        "kind <> 'comfy' OR workflow_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_jobs_comfy_has_workflow", "jobs", type_="check")
    op.drop_constraint("ck_jobs_kind", "jobs", type_="check")
    op.alter_column(
        "jobs",
        "workflow_id",
        existing_type=sa.UUID(),
        nullable=False,
        comment=None,
    )
    op.drop_index(op.f("ix_jobs_kind"), table_name="jobs")
    op.drop_column("jobs", "kind")
