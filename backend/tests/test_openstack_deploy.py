import base64
from types import SimpleNamespace
from unittest.mock import mock_open
import socket

import openstack
import pytest

from app.core.openstack_client import OpenStackClient, SSHBootstrapError
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


def test_linux_servers_get_direct_floating_ips_and_ssh_bootstrap(monkeypatch) -> None:
    create_server_calls = []
    floating_ip_calls = []
    bootstrap_calls = []

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
            create_server_calls.append(kwargs)
            return SimpleNamespace(id=kwargs["name"])

        def get_server(self, server_id):
            return SimpleNamespace(
                id=server_id,
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
        lambda *_args: SimpleNamespace(id="stand1-sg-id", name="stand1-sg"),
    )
    def assign_floating_ip(_conn, server_id, _external_network, _reserved_ips):
        floating_ip_calls.append(server_id)
        return {
            "stand1-L-MS": "203.0.113.10",
            "stand1-L-NFS": "203.0.113.70",
            "stand1-L-PGSQL": "203.0.113.55",
        }[server_id]

    monkeypatch.setattr(client, "_assign_floating_ip", assign_floating_ip)
    monkeypatch.setattr(
        client,
        "_prepare_lms_access",
        lambda ip, _admin, _student, _progress, role: bootstrap_calls.append((role, ip)),
    )
    payload = default_lab3_config().model_dump()
    payload["vms"] = payload["vms"][:3]
    deployment = DeploymentConfig.model_validate(payload)

    result = client.deploy_lab3_stand(
        "1",
        "admin-key",
        "student-key",
        "admin-private",
        "student-private",
        deployment=deployment,
    )

    assert all(call["image_id"] == "image-id" for call in create_server_calls)
    assert all(call["flavor_id"] == "flavor-id" for call in create_server_calls)
    assert all("block_device_mapping_v2" not in call for call in create_server_calls)
    assert all(call["config_drive"] is True for call in create_server_calls)
    assert all(
        call["metadata"] == {"cybershluz_ssh_policy": "3"}
        for call in create_server_calls
    )
    decoded_user_data = [
        base64.b64decode(call["user_data"], validate=True).decode("utf-8")
        for call in create_server_calls
    ]
    assert all(data.startswith("#cloud-config") for data in decoded_user_data)
    assert all("name: labadmin" in data for data in decoded_user_data)
    assert floating_ip_calls == ["stand1-L-MS", "stand1-L-NFS", "stand1-L-PGSQL"]
    assert result["L-MS"]["floating_ip"] == "203.0.113.10"
    assert result["L-NFS"]["floating_ip"] == "203.0.113.70"
    assert result["L-PGSQL"]["floating_ip"] == "203.0.113.55"
    assert bootstrap_calls == [
        ("L-MS", "203.0.113.10"),
        ("L-NFS", "203.0.113.70"),
        ("L-PGSQL", "203.0.113.55"),
    ]


def test_active_server_with_obsolete_ssh_policy_is_recreated(monkeypatch) -> None:
    stale = SimpleNamespace(
        id="stale-lms",
        name="stand1-L-MS",
        status="ACTIVE",
        metadata={},
        addresses={"stand-net": [{"OS-EXT-IPS:type": "fixed", "addr": "10.10.0.10"}]},
    )

    class FakeCompute:
        def __init__(self):
            self.deleted = []
            self.created = []

        def find_server(self, _name):
            return stale

        def delete_server(self, server):
            self.deleted.append(server.id)

        def wait_for_delete(self, _server, wait):
            assert wait == 120

        def find_image(self, _name):
            return SimpleNamespace(id="image-id", min_disk=5)

        def find_flavor(self, _name):
            return SimpleNamespace(id="flavor-id", disk=20)

        def get_keypair(self, name):
            return SimpleNamespace(public_key=f"ssh-ed25519 key-for-{name}")

        def create_server(self, **kwargs):
            self.created.append(kwargs)
            return SimpleNamespace(id="replacement-lms")

        def get_server(self, server_id):
            assert server_id == "replacement-lms"
            return SimpleNamespace(
                id=server_id,
                status="ACTIVE",
                addresses={
                    "stand-net": [
                        {"OS-EXT-IPS:type": "fixed", "addr": "10.10.0.10"},
                    ]
                },
            )

    class FakeNetwork:
        def get_network(self, _network_id):
            return SimpleNamespace(id="network-id")

    compute = FakeCompute()
    connection = SimpleNamespace(compute=compute, network=FakeNetwork(), image=None)
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
        lambda *_args: SimpleNamespace(id="stand1-sg-id", name="stand1-sg"),
    )
    monkeypatch.setattr(client, "_assign_floating_ip", lambda *_args: "203.0.113.10")
    monkeypatch.setattr(client, "_prepare_lms_access", lambda *_args: None)
    payload = default_lab3_config().model_dump()
    payload["vms"] = payload["vms"][:1]

    result = client.deploy_lab3_stand(
        "1",
        "shared-admin-key",
        "shared-student-key",
        "admin-private",
        "student-private",
        deployment=DeploymentConfig.model_validate(payload),
    )

    assert compute.deleted == ["stale-lms"]
    assert len(compute.created) == 1
    assert compute.created[0]["key_name"] == "shared-admin-key"
    assert compute.created[0]["metadata"] == {"cybershluz_ssh_policy": "3"}
    assert result["L-MS"]["ssh_bootstrapped"] is True


def test_security_group_reconciles_required_ssh_and_egress_rules() -> None:
    created_rules = []

    class FakeNetwork:
        def find_security_group(self, _name):
            return SimpleNamespace(
                id="sg-id",
                name="stand1-key-only-sg",
                security_group_rules=[],
            )

        def create_security_group_rule(self, **kwargs):
            created_rules.append(kwargs)
            return SimpleNamespace(**kwargs)

    client = OpenStackClient()
    sg = client._ensure_security_group(
        SimpleNamespace(network=FakeNetwork()),
        "1",
        "10.10.0.0/24",
    )

    assert sg.id == "sg-id"
    assert any(
        rule["direction"] == "ingress"
        and rule.get("protocol") == "tcp"
        and rule.get("port_range_min") == 22
        and rule.get("remote_ip_prefix") == "0.0.0.0/0"
        for rule in created_rules
    )
    assert any(
        rule["direction"] == "egress"
        and rule.get("remote_ip_prefix") == "0.0.0.0/0"
        for rule in created_rules
    )


def test_floating_ip_is_not_reused_while_neutron_still_reports_it_down() -> None:
    class FakeCompute:
        def get_server(self, server_id):
            fixed_ip = "10.10.0.10" if server_id == "lms" else "10.10.0.70"
            return SimpleNamespace(
                id=server_id,
                addresses={
                    "stand-net": [
                        {"OS-EXT-IPS:type": "fixed", "addr": fixed_ip},
                    ]
                },
            )

    class FakeNetwork:
        def __init__(self):
            self.available = SimpleNamespace(
                id="fip-1",
                floating_ip_address="203.0.113.10",
                floating_network_id="public-id",
                port_id=None,
            )
            self.created = []
            self.bindings = {}

        def find_network(self, _name):
            return SimpleNamespace(id="public-id")

        def ports(self, device_id, **_kwargs):
            return [SimpleNamespace(id=f"port-{device_id}")]

        def ips(self, **_kwargs):
            # Simulate an eventually consistent DOWN listing: even after the
            # first bind it keeps returning the same stale resource.
            return [self.available]

        def create_ip(self, floating_network_id):
            fip = SimpleNamespace(
                id=f"fip-{len(self.created) + 2}",
                floating_ip_address=f"203.0.113.{20 + len(self.created)}",
                floating_network_id=floating_network_id,
                port_id=None,
            )
            self.created.append(fip)
            return fip

        def update_ip(self, fip, port_id):
            self.bindings[fip.id] = port_id
            return SimpleNamespace(**{**vars(fip), "port_id": port_id})

        def get_ip(self, floating_id):
            candidates = [self.available, *self.created]
            fip = next(item for item in candidates if item.id == floating_id)
            return SimpleNamespace(
                **{**vars(fip), "port_id": self.bindings.get(floating_id)}
            )

    network = FakeNetwork()
    connection = SimpleNamespace(compute=FakeCompute(), network=network)
    client = OpenStackClient()
    reserved_ips = set()

    lms_ip = client._assign_floating_ip(connection, "lms", "Public", reserved_ips)
    nfs_ip = client._assign_floating_ip(connection, "nfs", "Public", reserved_ips)

    assert lms_ip == "203.0.113.10"
    assert nfs_ip == "203.0.113.20"
    assert network.bindings == {"fip-1": "port-lms", "fip-2": "port-nfs"}
    assert reserved_ips == {"203.0.113.10", "203.0.113.20"}


def test_windows_user_data_enables_rdp_only_for_tunnelled_private_access() -> None:
    user_data = OpenStackClient.build_user_data(
        "W-DC",
        "ssh-ed25519 admin-key",
        "ssh-ed25519 student-key",
    )

    assert "fDenyTSConnections -Value 0" in user_data
    assert "Enable-NetFirewallRule -DisplayGroup 'Remote Desktop'" in user_data
    assert "Start-Service -Name TermService" in user_data
    assert "Disable-NetFirewallRule -DisplayGroup 'Remote Desktop'" not in user_data


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
    monkeypatch.setattr(
        client,
        "_ensure_security_group",
        lambda *_args: SimpleNamespace(id="stand1-sg-id", name="stand1-sg"),
    )
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
    assert verification_attempts[0][1]["max_wait"] == 5
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
            self.channel = SimpleNamespace(
                exit_status_ready=lambda: True,
                recv_exit_status=lambda: status,
            )

        def read(self):
            return b""

    class Stdin:
        def __init__(self):
            self.channel = SimpleNamespace(shutdown_write=lambda: None)

        def write(self, value):
            script_input.append(value)

        def flush(self):
            pass

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


def test_legacy_bootstrap_uses_su_when_ssh_user_is_not_in_sudoers(monkeypatch) -> None:
    client = OpenStackClient()
    admin_private, _ = OpenStackClient._generate_local_keypair()
    student_private, _ = OpenStackClient._generate_local_keypair()
    commands = []
    command_options = []
    stdin_writes = []
    su_events = []

    class Stream:
        def __init__(self, status=0):
            self.channel = SimpleNamespace(
                exit_status_ready=lambda: True,
                recv_exit_status=lambda: status,
            )

        def read(self):
            return b""

    class Stdin:
        def __init__(self, command, channel=None):
            self.command = command
            self.channel = channel or SimpleNamespace(shutdown_write=lambda: None)

        def write(self, value):
            stdin_writes.append((self.command, value))
            if self.command.startswith("LC_ALL=C su root -c "):
                su_events.append("password_written")
                self.channel.finished = True

        def flush(self):
            pass

    class SuChannel:
        finished = False
        prompt_ready = True

        def recv_ready(self):
            return self.prompt_ready

        def recv(self, _size):
            self.prompt_ready = False
            su_events.append("prompt_read")
            return b"Password: "

        def recv_stderr_ready(self):
            return False

        def exit_status_ready(self):
            return self.finished

        def recv_exit_status(self):
            return 0

        def shutdown_write(self):
            pass

    su_channel = SuChannel()

    class FakeSSHClient:
        def set_missing_host_key_policy(self, _policy):
            pass

        def connect(self, **_kwargs):
            pass

        def exec_command(self, command, **kwargs):
            commands.append(command)
            command_options.append(kwargs)
            if command == "sudo -n true":
                return None, Stream(1), Stream(0)
            if command == "sudo -S -p '' true":
                return Stdin(command), Stream(1), Stream(0)
            assert command.startswith("LC_ALL=C su root -c ")
            stream = Stream(0)
            stream.channel = su_channel
            return Stdin(command, su_channel), stream, Stream(0)

        def close(self):
            pass

    monkeypatch.setattr("app.core.openstack_client.settings.VM_BOOTSTRAP_USER", "student")
    monkeypatch.setattr("app.core.openstack_client.settings.VM_BOOTSTRAP_PASSWORD", "ssh-password")
    monkeypatch.setattr("app.core.openstack_client.settings.VM_BOOTSTRAP_ROOT_PASSWORD", "root-password")
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

    assert commands[0] == "sudo -n true"
    assert commands[1] == "sudo -S -p '' true"
    assert commands[2].startswith("LC_ALL=C su root -c ")
    assert command_options[2]["get_pty"] is True
    assert su_events == ["prompt_read", "password_written"]
    assert stdin_writes == [
        ("sudo -S -p '' true", "ssh-password\n"),
        (commands[2], "root-password\n"),
    ]


def test_legacy_bootstrap_stops_when_remote_sudo_hangs(monkeypatch) -> None:
    client = OpenStackClient()
    admin_private, _ = OpenStackClient._generate_local_keypair()
    student_private, _ = OpenStackClient._generate_local_keypair()

    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.now += seconds

    clock = Clock()

    class HangingChannel:
        closed = False

        def exit_status_ready(self):
            return False

        def close(self):
            self.closed = True

    hanging_channel = HangingChannel()

    class Stream:
        channel = hanging_channel

    class FakeSSHClient:
        def set_missing_host_key_policy(self, _policy):
            pass

        def connect(self, **_kwargs):
            pass

        def exec_command(self, command, **_kwargs):
            assert command == "sudo -n true"
            return None, Stream(), Stream()

        def close(self):
            pass

    monkeypatch.setattr("app.core.openstack_client.time.monotonic", clock.monotonic)
    monkeypatch.setattr("app.core.openstack_client.time.sleep", clock.sleep)
    monkeypatch.setattr("app.core.openstack_client.settings.VM_BOOTSTRAP_USER", "student")
    monkeypatch.setattr("app.core.openstack_client.settings.VM_BOOTSTRAP_PASSWORD", "secret")
    monkeypatch.setattr("app.core.openstack_client.settings.VM_ADMIN_USER", "labadmin")
    monkeypatch.setattr("app.core.openstack_client.settings.VM_STUDENT_USER", "student")
    monkeypatch.setattr("paramiko.SSHClient", FakeSSHClient)
    monkeypatch.setattr(client, "_paramiko_key", lambda _key: object())

    with pytest.raises(SSHBootstrapError, match="did not finish within 20s"):
        client._bootstrap_legacy_lms_access(
            "203.0.113.10",
            admin_private,
            student_private,
            max_wait=10,
        )

    assert clock.now == 20
    assert hanging_channel.closed is True


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
