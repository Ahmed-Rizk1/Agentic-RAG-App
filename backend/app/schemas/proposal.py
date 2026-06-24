import uuid
from datetime import datetime
from pydantic import BaseModel


class ProposalDraftResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    executive_summary: str
    scope_understanding: str
    compliance_section: str
    required_deliverables: str
    created_at: datetime

    model_config = {"from_attributes": True}
