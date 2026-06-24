import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.document import DocumentStatus, DocumentType


class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    status: DocumentStatus
    doc_type: DocumentType
    page_count: int | None
    file_size_bytes: int
    processing_error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentMetadataResponse(BaseModel):
    organization_name: str | None
    tender_number: str | None
    submission_deadline: str | None
    budget_amount: float | None
    budget_currency: str | None
    certifications: list[str] | None
    language: str | None

    model_config = {"from_attributes": True}


class DocumentDetailResponse(BaseModel):
    id: uuid.UUID
    filename: str
    status: DocumentStatus
    doc_type: DocumentType
    page_count: int | None
    file_size_bytes: int
    processing_error: str | None
    metadata: DocumentMetadataResponse | None
    created_at: datetime

    model_config = {"from_attributes": True}
