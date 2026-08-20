import json

from app.api.v1.pubkey import _linux_targets


def test_linux_targets_include_every_l_prefixed_vm() -> None:
    vm_details = json.dumps(
        {
            "L-MS": {"ip": "10.10.0.10"},
            "l-nfs": {"expected_ip": "10.10.0.70"},
            "L-PGSQL": {"ip": "10.10.0.55"},
            "W-DC": {"ip": "10.10.0.5"},
        }
    )

    assert _linux_targets(vm_details) == [
        ("L-MS", "10.10.0.10"),
        ("l-nfs", "10.10.0.70"),
        ("L-PGSQL", "10.10.0.55"),
    ]


def test_linux_targets_fall_back_to_lms_for_old_stands() -> None:
    assert _linux_targets(None) == [("L-MS", None)]
    assert _linux_targets("not-json") == [("L-MS", None)]
