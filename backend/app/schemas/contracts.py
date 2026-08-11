from pydantic import BaseModel, Field, field_serializer
from typing import Literal, Optional, List
from datetime import datetime, timezone

from app.core.topology import DeploymentConfig


class DeployRequest(BaseModel):
    user_id: str
    lab_id: Literal[3]
    role: str = "student"
    deployment: Optional[DeploymentConfig] = None


class DeploymentOptionsResponse(BaseModel):
    default: DeploymentConfig
    images: List[str] = Field(default_factory=list)
    flavors: List[str] = Field(default_factory=list)
    external_networks: List[str] = Field(default_factory=list)
    catalog_error: Optional[str] = None


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
    progress: Optional[int] = None
    vms: Optional[dict] = None
    network: Optional[dict] = None

    @field_serializer("expires_at", "frozen_until")
    def _serialize_utc(self, dt: Optional[datetime]) -> Optional[str]:
         
         
         
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()


class StandSummaryResponse(BaseModel):
    stand_id: str
    status: str
    ip_address: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    @field_serializer("expires_at", "created_at")
    def _serialize_summary_utc(self, dt: Optional[datetime]) -> Optional[str]:
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
    lab_template: str = Field(default="lab03_cyber", pattern=r"^[a-z0-9_]+$")
    manual_confirmations: List[str] = Field(default_factory=list)


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
