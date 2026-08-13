from app.tasks.deploy import _update_task_state_safely


def test_result_backend_failure_does_not_escape() -> None:
    class Task:
        def update_state(self, **_kwargs):
            raise ConnectionError("redis is unavailable")

    _update_task_state_safely(Task(), state="DEPLOYING", meta={"progress": 5})


def test_manual_failure_metadata_is_not_published() -> None:
    calls = []

    class Task:
        def update_state(self, **kwargs):
            calls.append(kwargs)

    _update_task_state_safely(Task(), state="FAILURE", meta={"error": "broken"})

    assert calls == []
