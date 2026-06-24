import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin, new_uuid


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="projects")  # noqa: F821
    documents: Mapped[list["Document"]] = relationship(back_populates="project", cascade="all, delete-orphan")  # noqa: F821
    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="project", cascade="all, delete-orphan")  # noqa: F821
