import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import console
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


def make_stand(server_id: str = "608db750-e7dd-4c04-8ef0-c5ffaccc6336"):
    return SimpleNamespace(
        id=7,
        user_id=42,
        status=StandStatusEnum.READY,
        vm_details=json.dumps({"W-DC": {"server_id": server_id}}),
    )


def test_console_link_uses_owned_stand_wdc_uuid(monkeypatch) -> None:
    monkeypatch.setattr(
        console.settings,
        "OS_DASHBOARD_URL",
        "https://edu.cyber-infrastructure.ru:8800/",
    )

    response = console.create_console_link(
        "7",
        db=FakeDb(make_stand()),
        user={"user_id": 42, "role": "student"},
    )

    assert response == {
        "launch_url": (
            "https://edu.cyber-infrastructure.ru:8800/compute/servers/instances/"
            "608db750-e7dd-4c04-8ef0-c5ffaccc6336/console"
        ),
        "server_id": "608db750-e7dd-4c04-8ef0-c5ffaccc6336",
    }


def test_console_link_rejects_invalid_wdc_uuid() -> None:
    with pytest.raises(HTTPException) as exc_info:
        console.create_console_link(
            "7",
            db=FakeDb(make_stand("not-a-uuid")),
            user={"user_id": 42, "role": "student"},
        )

    assert exc_info.value.status_code == 409
    assert "UUID W-DC" in exc_info.value.detail
