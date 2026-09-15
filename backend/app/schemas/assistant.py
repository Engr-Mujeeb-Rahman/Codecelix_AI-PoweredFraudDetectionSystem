from typing import Any

from pydantic import BaseModel, Field


class AssistantQueryRequest(BaseModel):
    query: str = Field(..., description="Analyst question (e.g. 'Why is this customer suspicious?')")
    customer_id: str | None = None
    transaction_id: str | None = None
    device_id: str | None = None
    investigation_id: str | None = None


class AssistantQueryResponse(BaseModel):
    query: str
    answer: str
    mode: str = Field(description="'llm' or 'deterministic_engine'")
    referenced_data: dict[str, Any] = Field(default_factory=dict)
