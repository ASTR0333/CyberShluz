from types import SimpleNamespace

import openstack

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
            return SimpleNamespace(id="server-id")

        def wait_for_server(self, _server, status, wait):
            assert status == "ACTIVE"
            assert wait == 600
            return SimpleNamespace(
                addresses={"stand-net": [{"OS-EXT-IPS:type": "fixed", "addr": "10.0.0.10"}]}
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
        lambda *_args: {"network_id": "network-id", "external_network": "public"},
    )
    monkeypatch.setattr(
        client,
        "_ensure_security_group",
        lambda *_args: SimpleNamespace(name="stand1-sg"),
    )
    monkeypatch.setattr(client, "_assign_floating_ip", lambda *_args: "203.0.113.10")
    monkeypatch.setattr(client, "_verify_lms_access", lambda *_args: None)
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
