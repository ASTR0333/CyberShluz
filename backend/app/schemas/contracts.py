from pydantic import BaseModel, field_serializer
from typing import Optional, List
from datetime import datetime, timezone


class DeployRequest(BaseModel):
    user_id: str
    lab_id: int
    role: str = "student"


class DeployResponse(BaseModel):
    stand_id: str
    project_id: str
    status: str = "PENDING"
    message: str


class StatusResponse(BaseModel):
    stand_id: str
    status: str
    ip_address: Optional[str] = None
    expires_at: Optional[datetime] = None
    frozen_until: Optional[datetime] = None
    message: Optional[str] = ""
    vms: Optional[dict] = None

    @field_serializer("expires_at", "frozen_until")
    def _serialize_utc(self, dt: Optional[datetime]) -> Optional[str]:
         
         
         
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()


class PubkeyRequest(BaseModel):
    public_key: str


class FreezeRequest(BaseModel):
    reason: str = "Техническая поддержка — студент запросил помощь"


class FreezeResponse(BaseModel):
    stand_id: str
    status: str = "FREEZE"
    frozen_until: Optional[str] = None


class CheckRequest(BaseModel):
    lab_template: str = "lab03_cyber"
    checks: Optional[List[str]] = None


class CheckResponse(BaseModel):
    stand_id: str
    check_task_id: str
    status: str = "CHECKING"


class CheckResultResponse(BaseModel):
    status: str
    log: str
    details: Optional[dict] = None


class CleanupResponse(BaseModel):
    stand_id: str
    status: str = "CLEANING"
    message: str = "Очередь на очистку"
