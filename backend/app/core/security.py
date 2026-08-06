from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import os

 
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev_secret_change_me_in_prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "120"))

security = HTTPBearer(auto_error=False)

class UserRole:
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {**data, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется JWT-токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен истёк",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

def require_role(*roles: str):
    """Depends-функция для проверки роли пользователя"""
    def role_checker(payload: dict = Depends(verify_token)):
        user_role = payload.get("role")
        if user_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Доступ запрещён. Требуются роли: {', '.join(roles)}"
            )
        return payload
    return role_checker

 
get_current_user = verify_token
require_student = require_role(UserRole.STUDENT, UserRole.TEACHER, UserRole.ADMIN)
require_teacher = require_role(UserRole.TEACHER, UserRole.ADMIN)


def assert_stand_owner_or_teacher(payload: dict, stand_user_id: int | None) -> None:
    """
    Если запрашивающий — student, его user_id обязан совпадать с владельцем стенда.
    Teacher/admin может трогать любой стенд.
    """
    role = payload.get("role")
    if role in (UserRole.TEACHER, UserRole.ADMIN):
        return
    requester_id = int(payload.get("user_id", 0))
    if not stand_user_id or requester_id != int(stand_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Этот стенд принадлежит другому пользователю",
        )