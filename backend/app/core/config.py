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
    
     
    OS_AUTH_URL: Optional[str] = None
    OS_PROJECT_NAME: Optional[str] = None
    OS_USERNAME: Optional[str] = None
    OS_PASSWORD: Optional[str] = None
    OS_USER_DOMAIN_NAME: str = "Default"
    OS_PROJECT_DOMAIN_NAME: str = "Default"
    OS_REGION_NAME: str = "RegionOne"
    OS_NETWORK_NAME: str = "Local network"

     
     
    VM_DEFAULT_USER: str = "student"
     
    VM_DEFAULT_PASSWORD: str = "Pa$$w0rd"

     
    JWT_SECRET_KEY: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    MOODLE_SHARED_SECRET: str = "change-me-in-env"

     
     
     
     
     
    LTI_ISSUER: str = "http://10.77.106.216/moodle"
    LTI_CLIENT_ID: str = "YSjQZukRoG5djXL"   
    LTI_DEPLOYMENT_ID: str = "1"
    LTI_AUTH_LOGIN_URL: str = "http://10.77.106.216/moodle/mod/lti/auth.php"
    LTI_AUTH_TOKEN_URL: str = "http://10.77.106.216/moodle/mod/lti/token.php"
    LTI_KEYSET_URL: str = "http://10.77.106.216/moodle/mod/lti/certs.php"
     
    LTI_FRONTEND_BASE_URL: str = "http://10.77.106.250"
     
    LTI_PRIVATE_KEY_PATH: str = "/app/ssh_keys/lti/tool_private.pem"
    LTI_KEY_ID: str = "kibershluz-tool-key-1"
     
    LTI_GRADE_LAB_ID: int = 3

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()