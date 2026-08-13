import pytest
from pydantic import ValidationError

from app.core.topology import DeploymentConfig, default_lab3_config


def test_default_topology_matches_lab_document() -> None:
    config = default_lab3_config()
    by_role = config.enabled_topology()

    assert by_role["L-MS"] == {
        "image": "2_TMP_L-MS_Debian11.11_09.2025.qcow2",
        "flavor": "small",
        "ip": "10.10.0.10",
    }
    assert config.network.cidr == "10.10.0.0/24"
    assert config.network.gateway == "10.10.0.1"
    assert config.network.dhcp_start == "10.10.0.100"
    assert config.network.dhcp_end == "10.10.0.200"
    assert config.network.external_network == "Public"
    assert by_role["L-NFS"]["flavor"] == "tiny"
    assert by_role["L-PGSQL"]["flavor"] == "tiny"
    assert by_role["W-DC"]["flavor"] == "medium"
    assert by_role["V-HYPERV"]["flavor"] == "large"

    assert by_role["L-NFS"]["image"] == "2_TMP_L-NFS_CentOS7_08.2025.qcow2"
    assert by_role["L-PGSQL"]["image"] == "2_TMP_L-PGSQL_CentOS7_08.2025.qcow2"
    assert by_role["W-DC"]["image"] == "2_TMP_W-DC_WinSrvStd19_10.2025.qcow2"
    assert by_role["V-HYPERV"]["image"] == "2_TMP_V-HYPERV_WinSrvStd19_10.2025.qcow2"


def test_vm_address_cannot_overlap_dhcp_pool() -> None:
    payload = default_lab3_config().model_dump()
    payload["vms"][0]["ip"] = "10.10.0.150"

    with pytest.raises(ValidationError, match="DHCP allocation pool"):
        DeploymentConfig.model_validate(payload)


def test_vm_addresses_must_be_unique() -> None:
    payload = default_lab3_config().model_dump()
    payload["vms"][1]["ip"] = payload["vms"][0]["ip"]

    with pytest.raises(ValidationError, match="unique IP addresses"):
        DeploymentConfig.model_validate(payload)


def test_lms_is_required_for_access() -> None:
    payload = default_lab3_config().model_dump()
    payload["vms"][0]["enabled"] = False

    with pytest.raises(ValidationError, match="L-MS is required"):
        DeploymentConfig.model_validate(payload)
