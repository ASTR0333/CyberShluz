from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum

class RoleEnum(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"

class StandStatusEnum(str, Enum):
    FREE = "FREE"
    PENDING = "PENDING"
    DEPLOYING = "DEPLOYING"
    READY = "READY"
    FREEZE = "FREEZE"
    CLEANING = "CLEANING"

class UserBase(BaseModel):
    lms_id: str
    role: RoleEnum = RoleEnum.STUDENT

class UserCreate(UserBase):
    pass

class User(UserBase):
    id: int
    class Config:
        from_attributes = True

class ProjectBase(BaseModel):
    openstack_project_id: str
    name: str
    network_id: str

class Project(ProjectBase):
    id: int
    class Config:
        from_attributes = True

class StandBase(BaseModel):
    status: StandStatusEnum = StandStatusEnum.FREE

class StandCreate(StandBase):
    project_id: int

class Stand(StandBase):
    id: int
    project_id: int
    user_id: Optional[int] = None
    ip_address: Optional[str] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    frozen_until: Optional[datetime] = None
    class Config:
        from_attributes = True

class DeployRequest(BaseModel):
    lms_user_id: str
    lab_id: int
    role: RoleEnum = RoleEnum.STUDENT

class DeployResponse(BaseModel):
    stand_id: int
    project_id: int
    status: StandStatusEnum
    message: str

class FreezeRequest(BaseModel):
    reason: str
