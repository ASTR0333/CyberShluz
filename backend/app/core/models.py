from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum
from .database import Base

class RoleEnum(str, enum.Enum):
    STUDENT = "student"
    TEACHER = "teacher"

class StandStatusEnum(str, enum.Enum):
    FREE = "FREE"
    PENDING = "PENDING"
    DEPLOYING = "DEPLOYING"
    READY = "READY"
    FREEZE = "FREEZE"
    CLEANING = "CLEANING"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    lms_id = Column(String, unique=True, index=True, nullable=False)
    role = Column(Enum(RoleEnum), default=RoleEnum.STUDENT)
    ssh_private_key = Column(String, nullable=True)
     
     
    lti_context = Column(Text, nullable=True)
    
    stands = relationship("Stand", back_populates="owner")

class Project(Base):
    """
    Предсозданный проект (домен) в КИ.
    """
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    openstack_project_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    network_id = Column(String, nullable=False)
    
    stands = relationship("Stand", back_populates="project")

class Stand(Base):
    """
    Машина состояний (Стенд), привязанная к проекту и пользователю.
    """
    __tablename__ = "stands"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  
    
    status = Column(Enum(StandStatusEnum), default=StandStatusEnum.FREE, nullable=False)
    ip_address = Column(String, nullable=True)
    # Teacher/admin key. It is never exposed to a student.
    private_key = Column(String, nullable=True)
    # Service key for the unprivileged browser/Ansible session.
    student_private_key = Column(String, nullable=True)
    vm_details = Column(Text, nullable=True)
    network_details = Column(Text, nullable=True)  
    last_check_result = Column(Text, nullable=True)  
    lti_context = Column(Text, nullable=True)  

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True)
    frozen_until = Column(DateTime, nullable=True)
    
    project = relationship("Project", back_populates="stands")
    owner = relationship("User", back_populates="stands")
