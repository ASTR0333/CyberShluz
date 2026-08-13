from types import SimpleNamespace
from unittest.mock import mock_open
import socket

import openstack
import pytest

from app.core.openstack_client import OpenStackClient
from app.core.topology import DeploymentConfig, default_lab3_config


def test_logical_slot_uses_its_openstack_project_name(monkeypatch) -> None:
    connection_kwargs = {}

    def fake_connect(**kwargs):
        connection_kwargs.update(kwargs)
        return object()

    monkeypatch.setattr(openstack, "connect", fake_connect)

    OpenStackClient(project_ref="training-project:slot03").get_project_connection()

    assert connection_kwargs["project_name"] == "training-project"
    assert "project_id" not in connection_kwargs


def test_server_is_created_directly_from_image(monkeypatch) -> None:
    create_server_kwargs = {}

    class FakeCompute:
        def find_server(self, _name):
            return None

        def find_image(self, _name):
            return SimpleNamespace(id="image-id", min_disk=5)

        def find_flavor(self, _name):
            return SimpleNamespace(id="flavor-id", disk=20)

        def get_keypair(self, name):
            return SimpleNamespace(public_key=f"ssh-ed25519 key-for-{name}")

        def create_server(self, **kwargs):
            create_server_kwargs.update(kwargs)
            return SimpleNamespace(id="server-id")

        def get_server(self, _server_id):
            return SimpleNamespace(
                id="server-id",
                status="ACTIVE",
                addresses={"stand-net": [{"OS-EXT-IPS:type": "fixed", "addr": "10.10.0.10"}]}
            )

    class FakeNetwork:
        def get_network(self, _network_id):
            return SimpleNamespace(id="network-id")

    connection = SimpleNamespace(compute=FakeCompute(), network=FakeNetwork())
    client = OpenStackClient()
    monkeypatch.setattr(client, "_connect", lambda: connection)
    monkeypatch.setattr(
        client,
        "_ensure_stand_network",
        lambda *_args: {"network_id": "network-id", "external_network": "Public"},
    )
    monkeypatch.setattr(
        client,
        "_ensure_security_group",
        lambda *_args: SimpleNamespace(name="stand1-sg"),
    )
    monkeypatch.setattr(client, "_assign_floating_ip", lambda *_args: "203.0.113.10")
    monkeypatch.setattr(client, "_prepare_lms_access", lambda *_args: None)
    payload = default_lab3_config().model_dump()
    payload["vms"] = [payload["vms"][0]]
    deployment = DeploymentConfig.model_validate(payload)

    result = client.deploy_lab3_stand(
        "1",
        "admin-key",
        "student-key",
        "admin-private",
        "student-private",
        deployment=deployment,
    )

    assert create_server_kwargs["image_id"] == "image-id"
    assert create_server_kwargs["flavor_id"] == "flavor-id"
    assert "block_device_mapping_v2" not in create_server_kwargs
    assert result["L-MS"]["status"] == "ACTIVE"
    assert result["L-MS"]["floating_ip"] == "203.0.113.10"


def test_all_servers_share_one_build_deadline(monkeypatch) -> None:
    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.now += seconds

    clock = Clock()

    class FakeCompute:
        def find_server(self, _name):
            return None

        def find_image(self, _name):
            return SimpleNamespace(id="image-id", min_disk=5)

        def find_flavor(self, _name):
            return SimpleNamespace(id="flavor-id", disk=20)

        def get_keypair(self, name):
            return SimpleNamespace(public_key=f"ssh-ed25519 key-for-{name}")

        def create_server(self, name, **_kwargs):
            return SimpleNamespace(id=name)

        def get_server(self, server_id):
            return SimpleNamespace(id=server_id, status="BUILD", addresses={})

    class FakeNetwork:
        def get_network(self, _network_id):
            return SimpleNamespace(id="network-id")

    connection = SimpleNamespace(compute=FakeCompute(), network=FakeNetwork(), image=None)
    client = OpenStackClient()
    monkeypatch.setattr(client, "_connect", lambda: connection)
    monkeypatch.setattr(
        client,
        "_ensure_stand_network",
        lambda *_args: {"network_id": "network-id", "external_network": "Public"},
    )
    monkeypatch.setattr(client, "_ensure_security_group", lambda *_args: SimpleNamespace(name="stand1-sg"))
    monkeypatch.setattr("app.core.openstack_client.settings.VM_BUILD_TIMEOUT", 10)
    monkeypatch.setattr("app.core.openstack_client.time.monotonic", clock.monotonic)
    monkeypatch.setattr("app.core.openstack_client.time.sleep", clock.sleep)

    payload = default_lab3_config().model_dump()
    payload["vms"] = payload["vms"][:2]
    deployment = DeploymentConfig.model_validate(payload)

    result = client.deploy_lab3_stand(
        "1",
        "admin-key",
        "student-key",
        "admin-private",
        "student-private",
        deployment=deployment,
    )

    assert clock.now == 10
    assert result["L-MS"]["status"] == "TIMEOUT"
    assert result["L-NFS"]["status"] == "TIMEOUT"


def test_saved_private_key_is_reused_without_rotating_openstack_keypair(monkeypatch) -> None:
    private_key, public_key = OpenStackClient._generate_local_keypair()

    class FakeCompute:
        def __init__(self):
            self.deleted = []
            self.created = []

        def find_keypair(self, _name):
            return SimpleNamespace(name="existing", public_key=public_key + " old-comment")

        def delete_keypair(self, keypair):
            self.deleted.append(keypair)

        def create_keypair(self, **kwargs):
            self.created.append(kwargs)

    compute = FakeCompute()
    client = OpenStackClient()
    monkeypatch.setattr(client, "_connect", lambda: SimpleNamespace(compute=compute))
    monkeypatch.setattr("builtins.open", mock_open())
    monkeypatch.setattr("os.makedirs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("os.chmod", lambda *_args, **_kwargs: None)

    result = client.create_keypair("key-stand1-admin", private_key=private_key)

    assert result == private_key
    assert compute.deleted == []
    assert compute.created == []


def test_legacy_access_falls_back_to_password_bootstrap(monkeypatch) -> None:
    client = OpenStackClient()
    verification_attempts = []
    bootstrap_calls = []

    def verify(*args, **kwargs):
        verification_attempts.append((args, kwargs))
        if len(verification_attempts) == 1:
            raise RuntimeError("keys are not installed yet")

    monkeypatch.setattr("app.core.openstack_client.settings.VM_BOOTSTRAP_USER", "student")
    monkeypatch.setattr("app.core.openstack_client.settings.VM_BOOTSTRAP_PASSWORD", "secret")
    monkeypatch.setattr("app.core.openstack_client.settings.SSH_BOOTSTRAP_TIMEOUT", 90)
    monkeypatch.setattr(client, "_verify_lms_access", verify)
    monkeypatch.setattr(
        client,
        "_bootstrap_legacy_lms_access",
        lambda *args, **kwargs: bootstrap_calls.append((args, kwargs)),
    )

    client._prepare_lms_access("203.0.113.10", "admin-private", "student-private")

    assert len(verification_attempts) == 2
    assert verification_attempts[0][1]["max_wait"] == 15
    assert verification_attempts[1][1]["max_wait"] == 60
    assert bootstrap_calls[0][1]["max_wait"] == 90


def test_legacy_bootstrap_prefers_nova_key_and_handles_passwordless_sudo(monkeypatch) -> None:
    client = OpenStackClient()
    admin_private, _ = OpenStackClient._generate_local_keypair()
    student_private, _ = OpenStackClient._generate_local_keypair()
    connect_calls = []
    commands = []
    script_input = []

    class Stream:
        def __init__(self, status=0):
            self.channel = SimpleNamespace(recv_exit_status=lambda: status)

        def read(self):
            return b""

    class Stdin:
        def __init__(self):
            self.channel = SimpleNamespace(shutdown_write=lambda: None)

        def write(self, value):
            script_input.append(value)

    class FakeSSHClient:
        def set_missing_host_key_policy(self, _policy):
            pass

        def connect(self, **kwargs):
            connect_calls.append(kwargs)

        def exec_command(self, command, **_kwargs):
            commands.append(command)
            if command == "sudo -n true":
                return None, Stream(0), Stream(0)
            return Stdin(), Stream(0), Stream(0)

        def close(self):
            pass

    monkeypatch.setattr("app.core.openstack_client.settings.VM_BOOTSTRAP_USER", "student")
    monkeypatch.setattr("app.core.openstack_client.settings.VM_BOOTSTRAP_PASSWORD", "rejected-password")
    monkeypatch.setattr("app.core.openstack_client.settings.VM_ADMIN_USER", "labadmin")
    monkeypatch.setattr("app.core.openstack_client.settings.VM_STUDENT_USER", "student")
    monkeypatch.setattr("paramiko.SSHClient", FakeSSHClient)
    monkeypatch.setattr(client, "_paramiko_key", lambda _key: object())

    client._bootstrap_legacy_lms_access(
        "203.0.113.10",
        admin_private,
        student_private,
        max_wait=10,
    )

    assert "pkey" in connect_calls[0]
    assert "password" not in connect_calls[0]
    assert commands[1].startswith("sudo -n bash -s --")
    assert script_input == [client._legacy_bootstrap_script()]


def test_key_verification_uses_one_shared_timeout(monkeypatch) -> None:
    client = OpenStackClient()

    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.now += seconds

    clock = Clock()

    class Stream:
        def __init__(self, status=0):
            self.channel = SimpleNamespace(recv_exit_status=lambda: status)

        def read(self):
            return b""

    class FakeSSHClient:
        def set_missing_host_key_policy(self, _policy):
            pass

        def connect(self, **kwargs):
            if kwargs["username"] == "labadmin":
                clock.now += 6
                return
            raise socket.timeout("student key is not ready")

        def exec_command(self, *_args, **_kwargs):
            return None, Stream(0), Stream(0)

        def close(self):
            pass

    monkeypatch.setattr("app.core.openstack_client.time.monotonic", clock.monotonic)
    monkeypatch.setattr("app.core.openstack_client.time.sleep", clock.sleep)
    monkeypatch.setattr("paramiko.SSHClient", FakeSSHClient)
    monkeypatch.setattr(client, "_paramiko_key", lambda _key: object())
    monkeypatch.setattr("app.core.openstack_client.settings.VM_ADMIN_USER", "labadmin")
    monkeypatch.setattr("app.core.openstack_client.settings.VM_STUDENT_USER", "student")

    with pytest.raises(RuntimeError, match="shared 10s timeout"):
        client._verify_lms_access("203.0.113.10", "admin-private", "student-private", max_wait=10)

    assert clock.now == 10
