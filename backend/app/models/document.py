import enum
import uuid

from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, NUMERIC
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin, new_uuid


class DocumentStatus(str, enum.Enum):
    uploading = "uploading"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class DocumentType(str, enum.Enum):
    tender = "tender"
    contract = "contract"
    rfp = "rfp"
    procurement = "procurement"
    unknown = "unknown"


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"), default=DocumentStatus.uploading, nullable=False, index=True
    )
    doc_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type"), default=DocumentType.unknown
    )
    processing_error: Mapped[str | None] = mapped_column(Text)

    project: Mapped["Project"] = relationship(back_populates="documents")  # noqa: F821
    metadata_record: Mapped["DocumentMetadata | None"] = relationship(
        back_populates="document", cascade="all, delete-orphan", uselist=False
    )
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")  # noqa: F821
    risk_reports: Mapped[list["RiskReport"]] = relationship(back_populates="document", cascade="all, delete-orphan")  # noqa: F821
    proposals: Mapped[list["ProposalDraft"]] = relationship(back_populates="document", cascade="all, delete-orphan")  # noqa: F821


class DocumentMetadata(Base):
    __tablename__ = "document_metadata"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    organization_name: Mapped[str | None] = mapped_column(String(500))
    tender_number: Mapped[str | None] = mapped_column(String(255))
    submission_deadline: Mapped[str | None] = mapped_column(String(255))
    budget_amount: Mapped[float | None] = mapped_column(NUMERIC(15, 2))
    budget_currency: Mapped[str | None] = mapped_column(String(10))
    certifications: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    language: Mapped[str | None] = mapped_column(String(10))
    raw_extraction: Mapped[dict | None] = mapped_column(JSONB)

    document: Mapped["Document"] = relationship(back_populates="metadata_record")
