from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AlertReview(BaseModel):
    status: str
    note: str | None = None


class RuleCondition(BaseModel):
    field: str
    op: str = Field(description="One of: ==, !=, >, <, >=, <=, in, contains")
    value: Any


class RuleBase(BaseModel):
    name: str
    description: str | None = None
    rule_type: str = "threshold"
    conditions: Any  # dict, list, or JSON string
    action: str = "increase_risk"
    score_impact: float = 20.0
    severity: str = "medium"
    is_active: bool = True


class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    rule_type: str | None = None
    conditions: Any | None = None
    action: str | None = None
    score_impact: float | None = None
    severity: str | None = None
    is_active: bool | None = None


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    rule_type: str
    conditions: Any
    action: str
    score_impact: float
    severity: str
    is_active: bool
    created_by: str | None
    created_at: datetime
    updated_at: datetime
