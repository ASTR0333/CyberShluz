"""
Аутентификация для веб-интерфейса.

В кейсе два пользователя жёстко зашиты:
- admin   / Pa$$w0rd   → роль teacher (полный доступ)
- student / Pa$$w0rd   → роль student (только свой стенд)

Логин через POST /api/v1/auth/login. В ответ JWT, который фронт хранит в
localStorage и шлёт в заголовке Authorization: Bearer <token>.

Для LMS Moodle есть отдельный поток через HMAC-подпись (moodle.py),
он не пересекается с web-логином.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models import RoleEnum, User
from app.core.security import (
    UserRole,
    create_access_token,
    get_current_user,
)

router = APIRouter()


 
 
 
 
LOCAL_USERS: dict[str, dict] = {
    "admin": {
        "password": "Pa$$w0rd",
        "role": UserRole.TEACHER,
        "display_name": "Администратор",
    },
    "student": {
        "password": "Pa$$w0rd",
        "role": UserRole.STUDENT,
        "display_name": "Студент",
    },
}


 
 
 
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    display_name: str
    user_id: int


class MeResponse(BaseModel):
    username: str
    role: str
    display_name: str
    user_id: int


 
 
 
@router.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="Войти как admin или student (хардкод-учётки кейса)",
)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user_def = LOCAL_USERS.get(payload.username.strip().lower())
    if not user_def or user_def["password"] != payload.password:
         
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )

     
    role_enum = RoleEnum.TEACHER if user_def["role"] == UserRole.TEACHER else RoleEnum.STUDENT
    db_user = db.query(User).filter(User.lms_id == payload.username.lower()).first()
    if not db_user:
        db_user = User(lms_id=payload.username.lower(), role=role_enum)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

    token = create_access_token(
        data={
            "sub": payload.username.lower(),
            "role": user_def["role"],
            "user_id": db_user.id,
        },
        expires_delta=timedelta(hours=12),
    )

    return LoginResponse(
        access_token=token,
        username=payload.username.lower(),
        role=user_def["role"],
        display_name=user_def["display_name"],
        user_id=db_user.id,
    )


@router.get(
    "/auth/me",
    response_model=MeResponse,
    summary="Кто я (проверка JWT)",
)
def me(payload: dict = Depends(get_current_user)):
    username = payload.get("sub", "")
    user_def = LOCAL_USERS.get(username, {})
    return MeResponse(
        username=username,
        role=payload.get("role", ""),
        display_name=user_def.get("display_name", username),
        user_id=int(payload.get("user_id", 0)),
    )
