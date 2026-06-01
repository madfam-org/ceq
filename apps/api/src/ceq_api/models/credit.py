"""Credit ledger models for commercial metering."""

from enum import StrEnum
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ceq_api.models.base import JSONB, Base, GUIDString, TimestampMixin


class CreditLedgerType(StrEnum):
    """Supported credit ledger entry types."""

    GRANT = "grant"
    DEBIT = "debit"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


class CreditLedgerEntry(Base, TimestampMixin):
    """
    Append-only credit ledger entry.

    Amounts are integer credits. Positive values add credits; negative values
    consume credits. Every entry must carry an idempotency key so retries do not
    double-grant or double-charge.
    """

    __tablename__ = "credit_ledger_entries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_credit_ledger_idempotency_key"),
        Index("ix_credit_ledger_user_created", "user_id", "created_at"),
        Index("ix_credit_ledger_org_created", "org_id", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        GUIDString(),
        nullable=False,
        index=True,
        comment="Janua user ID whose balance this entry affects",
    )
    org_id: Mapped[UUID | None] = mapped_column(
        GUIDString(),
        nullable=True,
        index=True,
        comment="Janua organization ID, when present",
    )
    job_id: Mapped[UUID | None] = mapped_column(
        GUIDString(),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    output_id: Mapped[UUID | None] = mapped_column(
        GUIDString(),
        ForeignKey("outputs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Positive grants/refunds, negative debits",
    )
    transaction_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Stable caller-provided key preventing duplicate ledger entries",
    )
    ledger_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    job = relationship("Job", lazy="selectin")
    output = relationship("Output", lazy="selectin")
