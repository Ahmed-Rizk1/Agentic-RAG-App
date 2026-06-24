import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin, new_uuid


class RiskReport(TimestampMixin, Base):
    __tablename__ = "risk_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    overall_score: Mapped[str] = mapped_column(String(10), nullable=False)  # low, medium, high
    risks: Mapped[dict] = mapped_column(JSONB, nullable=False)

    document: Mapped["Document"] = relationship(back_populates="risk_reports")  # noqa: F821


class LLMLog(Base):
    __tablename__ = "llm_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    workflow: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(
        String, server_default="now()", nullable=False
    )


class ProposalDraft(TimestampMixin, Base):
    __tablename__ = "proposal_drafts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    scope_understanding: Mapped[str] = mapped_column(Text, nullable=False)
    compliance_section: Mapped[str] = mapped_column(Text, nullable=False)
    required_deliverables: Mapped[str] = mapped_column(Text, nullable=False)

    document: Mapped["Document"] = relationship(back_populates="proposals")  # noqa: F821

