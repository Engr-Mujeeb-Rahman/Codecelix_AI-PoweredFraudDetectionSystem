from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertReview(BaseModel):
    status: str
    note: str | None = None
