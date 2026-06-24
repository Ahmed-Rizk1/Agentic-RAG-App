import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin, new_uuid

EMBEDDING_DIM = 1024  # BGE-M3


class Chunk(TimestampMixin, Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    start_char: Mapped[int | None] = mapped_column(Integer)
    end_char: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    # tsvector for BM25 — generated column handled by migration SQL
    # tsv is created via raw SQL in the migration since SQLAlchemy doesn't natively
    # support GENERATED ALWAYS AS for tsvector well across all dialects.

    document: Mapped["Document"] = relationship(back_populates="chunks")  # noqa: F821
