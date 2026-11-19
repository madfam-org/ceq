"""Production model: a small directed graph of jobs (RFC 0061)."""

from uuid import UUID

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ceq_api.models.base import JSONB, Base, GUIDString, TimestampMixin


class Production(Base, TimestampMixin):
    """
    A production is a named set of jobs with dependencies between them.

    It holds no status of its own: the state of a production is read from its
    jobs, so the two can never disagree.
    """

    __tablename__ = "productions"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        GUIDString(),
        nullable=False,
        index=True,
        comment="Principal id of the submitting service client",
    )
    client_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Janua client id that submitted it",
    )
    spec: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="The submitted graph, as received",
    )

    def __repr__(self) -> str:
        return f"<Production {self.id} {self.name!r}>"
