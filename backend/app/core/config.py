from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
     
    DATABASE_URL: str = "postgresql://lab_admin:lab_secret_123@localhost:5432/lab_orchestrator"
    
     
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    
     
    APP_ENV: str = "development"
    APP_NAME: str = "Lab Orchestrator API"
    APP_VERSION: str = "0.1.0"
    
     
    DEFAULT_TTL_HOURS: int = 2
    FREEZE_DURATION_HOURS: int = 24
    
     
    MAX_CLUSTER_UTILIZATION: float = 0.90
    ENABLE_MOCK_CHECKS: bool = False
    
     
    OS_AUTH_URL: Optional[str] = None
    OS_PROJECT_NAME: Optional[str] = None
    OS_USERNAME: Optional[str] = None
    OS_PASSWORD: Optional[str] = None
    OS_USER_DOMAIN_NAME: str = "Default"
    OS_PROJECT_DOMAIN_NAME: str = "Default"
    OS_REGION_NAME: str = "RegionOne"
    OS_NETWORK_NAME: str = "public"

     
     
    VM_ADMIN_USER: str = "labadmin"
    VM_STUDENT_USER: str = "student"
    # Optional one-time credentials for legacy images without cloud-init.
    # The password is used only to install per-role SSH keys and is disabled
    # before a stand is marked READY.
    VM_BOOTSTRAP_USER: str = ""
    VM_BOOTSTRAP_PASSWORD: str = ""
    SSH_BOOTSTRAP_TIMEOUT: int = 240

     
    JWT_SECRET_KEY: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    MOODLE_SHARED_SECRET: str = "change-me-in-env"

     
     
     
     
     
    LTI_ISSUER: str = ""
    LTI_CLIENT_ID: str = ""
    LTI_DEPLOYMENT_ID: str = "1"
    LTI_AUTH_LOGIN_URL: str = ""
    LTI_AUTH_TOKEN_URL: str = ""
    LTI_KEYSET_URL: str = ""
     
    LTI_FRONTEND_BASE_URL: str = ""
     
    LTI_PRIVATE_KEY_PATH: str = "/app/ssh_keys/lti/tool_private.pem"
    LTI_KEY_ID: str = "kibershluz-tool-key-1"
     
    LTI_GRADE_LAB_ID: int = 3

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
