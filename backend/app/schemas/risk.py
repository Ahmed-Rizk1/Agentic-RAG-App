import uuid
from datetime import datetime

from pydantic import BaseModel


class RiskItem(BaseModel):
    category: str
    severity: str  # low, medium, high
    description: str
    evidence: str
    page: int | None = None


class RiskReportResponse(BaseModel):
    id: uuid.UUID
    overall_score: str
    risks: list[RiskItem]
    created_at: datetime

    model_config = {"from_attributes": True}
