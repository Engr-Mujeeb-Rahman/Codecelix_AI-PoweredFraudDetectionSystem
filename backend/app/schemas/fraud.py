from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    transaction_id: str
    customer_id: str
    title: str
    reason: str | None
    severity: str
    status: str
    assigned_to: str | None
    resolved_at: datetime | None
    created_at: datetime


class AlertCreate(BaseModel):
    transaction_id: str
    title: str
    reason: str | None = None
    severity: str = "medium"


class AlertUpdate(BaseModel):
    status: str | None = None
    assigned_to: str | None = None
    severity: str | None = None


class InvestigationCreate(BaseModel):
    transaction_id: str
    notes: str | None = None


class InvestigationUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    conclusion: str | None = None


class InvestigationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    transaction_id: str
    customer_id: str
    analyst_id: str | None
    status: str
    notes: str | None
    conclusion: str | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class ModelFeedbackCreate(BaseModel):
    alert_id: str | None = None
    transaction_id: str | None = None
    feedback_label: str
    comment: str | None = None


class ModelFeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    alert_id: str | None
    transaction_id: str | None
    feedback_label: str
    comment: str | None
    created_by: str | None
    created_at: datetime


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    report_type: str
    title: str
    period_start: datetime | None
    period_end: datetime | None
    status: str
    format: str
    payload: str | None
    created_by: str | None
    created_at: datetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str | None
    user_email: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    detail: str | None
    ip: str | None
    created_at: datetime
