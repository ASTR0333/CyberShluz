import json
import os
from pathlib import Path

from app.services.checker_service import CheckerService


def test_inventory_uses_lms_as_bastion(tmp_path: Path) -> None:
    key_path = tmp_path / "stand.pem"
    key_path.write_text("private-key", encoding="utf-8")
    inventory_path = CheckerService._write_inventory(
        {
            "L-MS": {"address": "203.0.113.10"},
            "L-NFS": {"address": "10.10.0.70", "proxy_jump": "203.0.113.10"},
            "L-PGSQL": {"address": "10.10.0.55", "proxy_jump": "203.0.113.10"},
        },
        "labadmin",
        str(key_path),
    )
    try:
        inventory = json.loads(Path(inventory_path).read_text(encoding="utf-8"))
        nfs = inventory["all"]["children"]["nfs"]["hosts"]["l-nfs"]
        assert nfs["ansible_host"] == "10.10.0.70"
        assert "ProxyJump=labadmin@203.0.113.10" in nfs["ansible_ssh_common_args"]
        assert nfs["expected_hostname"] == "l-nfs.cyberprotect.test"
    finally:
        os.unlink(inventory_path)


def test_ansible_parser_fails_when_nfs_is_unreachable() -> None:
    stdout = json.dumps(
        {
            "plays": [
                {
                    "play": {"name": "Lab 3"},
                    "tasks": [
                        {
                            "task": {"name": "3.2 Модуль ядра snapapi загружен на L-NFS"},
                            "hosts": {"l-nfs": {"unreachable": True, "msg": "timeout"}},
                        }
                    ],
                }
            ]
        },
        ensure_ascii=False,
    )

    result = CheckerService()._parse_ansible_json(stdout, "", 4)

    assert result["status"] == "FAILED"
    assert result["details"]["ssh_accessible"] is False
    assert result["details"]["snapapi_loaded"] is False
