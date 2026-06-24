import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


# Import all models so relationships resolve correctly.
# This must happen after Base is defined.
from app.models.user import User  # noqa: E402, F401
from app.models.project import Project  # noqa: E402, F401
from app.models.document import Document, DocumentMetadata  # noqa: E402, F401
from app.models.chunk import Chunk  # noqa: E402, F401
from app.models.chat import ChatSession, Message  # noqa: E402, F401
from app.models.llm_log import RiskReport, LLMLog, ProposalDraft  # noqa: E402, F401

