import json
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api.v1 import check as check_api
from app.core.models import StandStatusEnum
from app.services.checker_service import CheckResult


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
        self.commits = 0

    def query(self, *_args):
        return FakeQuery(self.stand)

    def commit(self):
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def make_stand(status=StandStatusEnum.READY):
    return SimpleNamespace(
        id=7,
        user_id=42,
        status=status,
        ip_address="203.0.113.10",
        private_key="-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----",
        vm_details=json.dumps(
            {
                "L-MS": {"floating_ip": "203.0.113.10", "ip": "10.16.0.10"},
                "L-NFS": {"floating_ip": "203.0.113.70", "ip": "10.16.0.70"},
                "L-PGSQL": {"floating_ip": "203.0.113.55", "ip": "10.16.0.55"},
                "W-DC": {"ip": "10.16.0.5"},
            }
        ),
        last_check_result=None,
    )


@pytest.mark.asyncio
async def test_successful_check_keeps_stand_ready_and_persists_result(monkeypatch) -> None:
    stand = make_stand()
    request_db = FakeDb(stand)
    background = BackgroundTasks()
    grade_calls = []
    checker_calls = []

    class PassingChecker:
        async def check_stand(self, **kwargs):
            checker_calls.append(kwargs)
            return CheckResult(
                stand_id="7",
                status="PASSED",
                log="all automatic checks passed",
                details={"ssh_accessible": True},
            )

    monkeypatch.setattr(check_api.CheckerService, "from_env", lambda: PassingChecker())
    monkeypatch.setattr(check_api, "SessionLocal", lambda: FakeDb(stand))
    monkeypatch.setattr(check_api, "push_lti_grade", lambda *args, **kwargs: grade_calls.append((args, kwargs)))

    response = await check_api.start_check(
        stand_id=7,
        request=check_api.CheckRequest(manual_confirmations=list(check_api.MANUAL_CHECKS)),
        background_tasks=background,
        db=request_db,
        user={"user_id": 42, "role": "student"},
    )
    await background()

    persisted = json.loads(stand.last_check_result)
    assert response["status"] == "CHECKING"
    assert persisted["status"] == "PASSED"
    assert stand.status == StandStatusEnum.READY
    assert len(grade_calls) == 1
    assert checker_calls[0]["stand_hosts"]["L-NFS"] == {"address": "203.0.113.70"}
    assert checker_calls[0]["stand_hosts"]["L-PGSQL"] == {"address": "203.0.113.55"}


@pytest.mark.asyncio
async def test_check_rejects_stand_that_is_not_ready() -> None:
    stand = make_stand(StandStatusEnum.CLEANING)

    with pytest.raises(HTTPException) as exc_info:
        await check_api.start_check(
            stand_id=7,
            request=check_api.CheckRequest(),
            background_tasks=BackgroundTasks(),
            db=FakeDb(stand),
            user={"user_id": 42, "role": "student"},
        )

    assert exc_info.value.status_code == 409
