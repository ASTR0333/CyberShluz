import json

from app.api.v1 import pubkey as pubkey_api
from app.api.v1.pubkey import _linux_targets, _push_pubkey_to_linux_hosts


def test_linux_targets_include_every_l_prefixed_vm() -> None:
    vm_details = json.dumps(
        {
            "L-MS": {"ip": "10.10.0.10", "floating_ip": "203.0.113.10"},
            "l-nfs": {"expected_ip": "10.10.0.70", "floating_ip": "203.0.113.70"},
            "L-PGSQL": {"ip": "10.10.0.55", "floating_ip": "203.0.113.55"},
            "W-DC": {"ip": "10.10.0.5"},
        }
    )

    assert _linux_targets(vm_details) == [
        ("L-MS", "203.0.113.10"),
        ("l-nfs", "203.0.113.70"),
        ("L-PGSQL", "203.0.113.55"),
    ]


def test_linux_targets_fall_back_to_lms_for_old_stands() -> None:
    assert _linux_targets(None) == [("L-MS", None)]
    assert _linux_targets("not-json") == [("L-MS", None)]


def test_pubkey_is_installed_over_each_linux_floating_ip(monkeypatch) -> None:
    connections = []
    installations = []

    class Client:
        def __init__(self, address):
            self.address = address
            self.closed = False

        def close(self):
            self.closed = True

    class Key:
        def get_fingerprint(self):
            return b"test"

    clients = {}

    def connect(address, user, pkey, max_wait):
        client = Client(address)
        clients[address] = client
        connections.append((address, user, pkey, max_wait))
        return client

    monkeypatch.setattr(pubkey_api, "_load_pkey", lambda _key: Key())
    monkeypatch.setattr(pubkey_api, "_connect_with_key", connect)
    monkeypatch.setattr(
        pubkey_api,
        "_install_pubkey",
        lambda client, key, role: installations.append((client.address, key, role)),
    )

    _push_pubkey_to_linux_hosts(
        "203.0.113.10",
        "admin-private-key",
        "ssh-ed25519 student-key",
        [
            ("L-MS", "203.0.113.10"),
            ("L-NFS", "203.0.113.70"),
            ("L-PGSQL", "203.0.113.55"),
        ],
        max_wait=1,
    )

    assert [call[0] for call in connections] == [
        "203.0.113.10",
        "203.0.113.70",
        "203.0.113.55",
    ]
    assert [item[2] for item in installations] == ["L-MS", "L-NFS", "L-PGSQL"]
    assert all(client.closed for client in clients.values())
