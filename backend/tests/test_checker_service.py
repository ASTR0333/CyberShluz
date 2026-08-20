import json
import os
from pathlib import Path

from app.services.checker_service import CheckerService


def test_inventory_connects_to_linux_floating_ips_directly(tmp_path: Path) -> None:
    key_path = tmp_path / "stand.pem"
    key_path.write_text("private-key", encoding="utf-8")
    inventory_path = CheckerService._write_inventory(
        {
            "L-MS": {"address": "203.0.113.10"},
            "L-NFS": {"address": "203.0.113.70"},
            "L-PGSQL": {"address": "203.0.113.55"},
            "W-DC": {"address": "10.10.0.5", "proxy_jump": "203.0.113.10"},
        },
        "labadmin",
        str(key_path),
    )
    try:
        inventory = json.loads(Path(inventory_path).read_text(encoding="utf-8"))
        nfs = inventory["all"]["children"]["nfs"]["hosts"]["l-nfs"]
        assert nfs["ansible_host"] == "203.0.113.70"
        assert "ansible_ssh_common_args" not in nfs
        assert nfs["expected_hostname"] == "l-nfs.cyberprotect.test"
        wdc = inventory["all"]["children"]["wdc"]["hosts"]["w-dc"]
        assert wdc["ansible_host"] == "10.10.0.5"
        assert wdc["ansible_shell_type"] == "powershell"
        assert "ProxyJump=labadmin@203.0.113.10" in wdc["ansible_ssh_common_args"]
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


def test_ansible_parser_does_not_hide_one_failed_hostname() -> None:
    stdout = json.dumps(
        {
            "plays": [
                {
                    "play": {"name": "Lab 3"},
                    "tasks": [
                        {
                            "task": {"name": "1.1 Hostname точно соответствует роли"},
                            "hosts": {
                                "l-ms": {"failed": True, "msg": "wrong hostname"},
                                "l-nfs": {"changed": False},
                                "l-pgsql": {"changed": False},
                            },
                        }
                    ],
                }
            ]
        },
        ensure_ascii=False,
    )

    result = CheckerService()._parse_ansible_json(stdout, "", 2)

    assert result["status"] == "FAILED"
    assert result["details"]["hostname_ok"] is False


def test_nfs_storage_task_does_not_overwrite_firewall_result() -> None:
    stdout = json.dumps(
        {
            "plays": [
                {
                    "play": {"name": "Lab 3"},
                    "tasks": [
                        {
                            "task": {"name": "3.1 На L-NFS открыты firewall-порты Acronis"},
                            "hosts": {"l-nfs": {"failed": True}},
                        },
                        {
                            "task": {"name": "3.4 Каталог управляемого хранилища /BackupL существует"},
                            "hosts": {"l-nfs": {"changed": False}},
                        },
                    ],
                }
            ]
        },
        ensure_ascii=False,
    )

    result = CheckerService()._parse_ansible_json(stdout, "", 2)

    assert result["details"]["firewall_ok"] is False
    assert result["details"]["storage_directory_ok"] is True


def test_ansible_parser_reports_windows_service_result() -> None:
    stdout = json.dumps(
        {
            "plays": [
                {
                    "play": {"name": "Lab 3 W-DC"},
                    "tasks": [
                        {
                            "task": {"name": "2.2 Требуемые Windows-службы запущены на W-DC"},
                            "hosts": {"w-dc": {"failed": True, "msg": "Elasticsearch"}},
                        }
                    ],
                }
            ]
        },
        ensure_ascii=False,
    )

    result = CheckerService()._parse_ansible_json(stdout, "", 2)

    assert result["status"] == "FAILED"
    assert result["details"]["windows_services_active"] is False
