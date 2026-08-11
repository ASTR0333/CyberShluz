import asyncio
from types import SimpleNamespace

from app.api.v1 import status as status_api
from app.core.models import StandStatusEnum


class FakeQuery:
    def __init__(self, stand):
        self.stand = stand

    def filter(self, *_args):
        return self

    def first(self):
        return self.stand


class FakeDb:
    def __init__(self, stand):
        self.stand = stand

    def query(self, *_args):
        return FakeQuery(self.stand)


def test_status_falls_back_to_database_when_redis_is_unavailable(monkeypatch) -> None:
    stand = SimpleNamespace(
        id=7,
        user_id=42,
        status=StandStatusEnum.DEPLOYING,
        ip_address=None,
        expires_at=None,
        frozen_until=None,
        vm_details=None,
        network_details=None,
    )

    def redis_unavailable(_task_id):
        raise ConnectionError("redis is unavailable")

    monkeypatch.setattr(status_api.celery_app.backend, "get_task_meta", redis_unavailable)

    response = asyncio.run(
        status_api.get_status("7", db=FakeDb(stand), user={"user_id": 42, "role": "student"})
    )

    assert response.stand_id == "7"
    assert response.status == "DEPLOYING"
    assert response.message == ""
