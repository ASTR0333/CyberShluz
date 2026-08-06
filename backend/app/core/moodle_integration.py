import hmac
import hashlib
import os
import logging
from typing import Optional
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

class MoodleIntegration:
    """
    REST-шлюз для интеграции с Moodle.
    Поддерживает:
    - Валидацию запросов через HMAC-подпись
    - Маппинг course_id → domain_id КИ
    - Маппинг user_id → project_id КИ
    """
    
    def __init__(self, moodle_secret: str, course_mapping: dict[str, str]):
        self.moodle_secret = moodle_secret.encode()
        self.course_mapping = course_mapping   
    
    def verify_signature(self, payload: str, signature: str) -> bool:
        """Проверка HMAC-подписи запроса от Moodle"""
        expected = hmac.new(
            self.moodle_secret,
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    
    def get_domain_id(self, course_id: str) -> Optional[str]:
        """Маппинг course_id Moodle → domain_id КИ"""
        domain = self.course_mapping.get(course_id)
        if not domain:
            logger.warning(f"[MOODLE] Unknown course_id: {course_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Курс {course_id} не настроен в КИ"
            )
        return domain
    
    def get_project_for_user(self, user_id: str, domain_id: str) -> str:
        """
        Маппинг user_id Moodle → project_id КИ.
        В проде: запрос к БД проектов, закреплённых за пользователем.
        Сейчас: детерминированная генерация для демо.
        """
         
        project_hash = hashlib.sha256(f"{user_id}:{domain_id}".encode()).hexdigest()[:12]
        return f"proj-{domain_id}-{project_hash}"
    
    @classmethod
    def from_env(cls) -> "MoodleIntegration":
        """Создание из переменных окружения"""
        secret = os.getenv("MOODLE_SHARED_SECRET", "dev_secret_change_me")
        mapping_str = os.getenv("MOODLE_COURSE_MAPPING", "{}")
        import json
        mapping = json.loads(mapping_str)
        return cls(moodle_secret=secret, course_mapping=mapping)


 
_moodle: Optional[MoodleIntegration] = None

def get_moodle_integration() -> MoodleIntegration:
    global _moodle
    if _moodle is None:
        _moodle = MoodleIntegration.from_env()
    return _moodle