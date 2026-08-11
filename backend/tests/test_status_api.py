import asyncio
from datetime import datetime, timedelta, timezone
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
        deployment_progress=45,
        deployment_message="Ожидание ВМ: 2/5 ACTIVE",
        deployment_error=None,
        deployment_updated_at=datetime.now(timezone.utc),
    )

    def redis_unavailable(_task_id):
        raise ConnectionError("redis is unavailable")

    monkeypatch.setattr(status_api.celery_app.backend, "get_task_meta", redis_unavailable)

    response = asyncio.run(
        status_api.get_status("7", db=FakeDb(stand), user={"user_id": 42, "role": "student"})
    )

    assert response.stand_id == "7"
    assert response.status == "DEPLOYING"
    assert response.message == "Ожидание ВМ: 2/5 ACTIVE"
    assert response.progress == 45


def test_status_uses_persisted_failure_when_redis_is_unavailable(monkeypatch) -> None:
    stand = SimpleNamespace(
        id=8,
        user_id=42,
        status=StandStatusEnum.DEPLOYING,
        ip_address=None,
        expires_at=None,
        frozen_until=None,
        vm_details=None,
        network_details=None,
        deployment_progress=90,
        deployment_message="Ожидание ВМ",
        deployment_error="L-MS=ERROR",
        deployment_updated_at=object(),
    )

    monkeypatch.setattr(
        status_api.celery_app.backend,
        "get_task_meta",
        lambda _task_id: (_ for _ in ()).throw(ConnectionError("redis is unavailable")),
    )

    response = asyncio.run(
        status_api.get_status("8", db=FakeDb(stand), user={"user_id": 42, "role": "student"})
    )

    assert response.status == "FAILED"
    assert response.message == "L-MS=ERROR"
    assert response.progress == 90


def test_stale_deployment_is_reported_as_failed(monkeypatch) -> None:
    stand = SimpleNamespace(
        id=9,
        user_id=42,
        status=StandStatusEnum.DEPLOYING,
        ip_address=None,
        expires_at=None,
        frozen_until=None,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        vm_details=None,
        network_details=None,
        deployment_progress=30,
        deployment_message="Создание ВМ",
        deployment_error=None,
        deployment_updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    monkeypatch.setattr(
        status_api.celery_app.backend,
        "get_task_meta",
        lambda _task_id: {"status": "DEPLOYING", "result": {}},
    )

    response = asyncio.run(
        status_api.get_status("9", db=FakeDb(stand), user={"user_id": 42, "role": "student"})
    )

    assert response.status == "FAILED"
    assert "давно не обновлял" in response.message
