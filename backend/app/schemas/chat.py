import uuid
from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: uuid.UUID | None = None
    document_ids: list[uuid.UUID] | None = None


class SourceInfo(BaseModel):
    page: int | None
    snippet: str
    chunk_id: uuid.UUID | None = None


class ChatSessionResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    sources: list[SourceInfo] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
