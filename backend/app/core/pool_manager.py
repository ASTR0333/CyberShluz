 
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone
from typing import Optional

from app.core.models import RoleEnum, Stand, StandStatusEnum, User

class PoolManager:
    """
    PoolManager - Логика пула с атомарной блокировкой. 
    Использует with_for_update() для безопасного выделения стендов.
    """
    def __init__(self, db: Session):
        self.db = db

    def allocate_stand(self, lms_user_id: str, role: RoleEnum) -> Optional[Stand]:
        """
        Выделяет свободный стенд из пула для пользователя.
        """
        try:
             
            user = self.db.query(User).filter(User.lms_id == lms_user_id).first()
            if not user:
                user = User(lms_id=lms_user_id, role=role)
                self.db.add(user)
                self.db.commit()
                self.db.refresh(user)

             
            stand = (
                self.db.query(Stand)
                .filter(Stand.status == StandStatusEnum.FREE)
                .with_for_update(skip_locked=True)  
                .first()
            )

            if not stand:
                return None  

             
            stand.user_id = user.id
            stand.status = StandStatusEnum.DEPLOYING
            stand.created_at = datetime.now(timezone.utc)
             
             
             
            stand.expires_at = None
            stand.frozen_until = None
            stand.ip_address = None  

            self.db.commit()
            self.db.refresh(stand)
            return stand

        except SQLAlchemyError as e:
            self.db.rollback()
             
            print(f"Error allocating stand: {e}")
            return None

    def release_stand(self, stand_id: int) -> bool:
        """
        Освобождает стенд, переводит его в статус CLEANING.
        (Очистка в КИ будет происходить асинхронно).
        """
        try:
            stand = (
                self.db.query(Stand)
                .filter(Stand.id == stand_id)
                .with_for_update()
                .first()
            )

            if not stand or stand.status in [StandStatusEnum.FREE, StandStatusEnum.CLEANING]:
                return False

            stand.status = StandStatusEnum.CLEANING
             
            self.db.commit()
            return True

        except SQLAlchemyError as e:
            self.db.rollback()
            print(f"Error releasing stand: {e}")
            return False

    def mark_stand_as_free(self, stand_id: int) -> bool:
        """
        Функция для завершения очистки.
        Переводит стенд из CLEANING в FREE и стирает все следы ВМ.
        """
        try:
            stand = self.db.query(Stand).filter(Stand.id == stand_id).first()
            if stand and stand.status == StandStatusEnum.CLEANING:
                stand.status = StandStatusEnum.FREE
                stand.user_id = None
                stand.ip_address = None
                stand.private_key = None   
                stand.vm_details = None    
                stand.lti_context = None   
                stand.expires_at = None
                stand.frozen_until = None
                self.db.commit()
                return True
            return False
        except SQLAlchemyError:
            self.db.rollback()
            return False