from __future__ import annotations

from ipaddress import IPv4Address, IPv4Network
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


VMRole = Literal["L-MS", "L-NFS", "L-PGSQL", "W-DC", "V-HYPERV"]


class NetworkDeploymentSpec(BaseModel):
    cidr: str = "10.0.0.0/24"
    gateway: str = "10.0.0.1"
    dhcp_start: str = "10.0.0.100"
    dhcp_end: str = "10.0.0.200"
    dns_nameservers: list[str] = Field(default_factory=lambda: ["8.8.8.8", "1.1.1.1"])
    external_network: str = "public"

    @model_validator(mode="after")
    def validate_addresses(self) -> "NetworkDeploymentSpec":
        network = IPv4Network(self.cidr, strict=True)
        gateway = IPv4Address(self.gateway)
        dhcp_start = IPv4Address(self.dhcp_start)
        dhcp_end = IPv4Address(self.dhcp_end)

        for label, address in (
            ("gateway", gateway),
            ("dhcp_start", dhcp_start),
            ("dhcp_end", dhcp_end),
        ):
            if address not in network or address in (network.network_address, network.broadcast_address):
                raise ValueError(f"{label} must be a usable address inside {network}")
        if dhcp_start > dhcp_end:
            raise ValueError("dhcp_start must not be greater than dhcp_end")
        if dhcp_start <= gateway <= dhcp_end:
            raise ValueError("gateway must not overlap the DHCP allocation pool")
        if not self.external_network.strip():
            raise ValueError("external_network must not be empty")
        for dns in self.dns_nameservers:
            IPv4Address(dns)
        return self


class VMDeploymentSpec(BaseModel):
    role: VMRole
    image: str = Field(min_length=1, max_length=255)
    flavor: str = Field(min_length=1, max_length=255)
    ip: str
    enabled: bool = True

    @field_validator("image", "flavor")
    @classmethod
    def strip_resource_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("resource name must not be empty")
        return value

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, value: str) -> str:
        return str(IPv4Address(value))


class DeploymentConfig(BaseModel):
    network: NetworkDeploymentSpec = Field(default_factory=NetworkDeploymentSpec)
    vms: list[VMDeploymentSpec]

    @model_validator(mode="after")
    def validate_topology(self) -> "DeploymentConfig":
        enabled = [vm for vm in self.vms if vm.enabled]
        roles = [vm.role for vm in enabled]
        if not enabled:
            raise ValueError("at least one VM must be enabled")
        if len(roles) != len(set(roles)):
            raise ValueError("VM roles must be unique")
        if "L-MS" not in roles:
            raise ValueError("L-MS is required because it is the access and management VM")

        network = IPv4Network(self.network.cidr, strict=True)
        reserved = {
            network.network_address,
            network.broadcast_address,
            IPv4Address(self.network.gateway),
        }
        dhcp_start = IPv4Address(self.network.dhcp_start)
        dhcp_end = IPv4Address(self.network.dhcp_end)
        addresses: list[IPv4Address] = []
        for vm in enabled:
            address = IPv4Address(vm.ip)
            if address not in network or address in reserved:
                raise ValueError(f"{vm.role} IP must be a usable address inside {network}")
            if dhcp_start <= address <= dhcp_end:
                raise ValueError(f"{vm.role} IP must not overlap the DHCP allocation pool")
            addresses.append(address)
        if len(addresses) != len(set(addresses)):
            raise ValueError("enabled VMs must have unique IP addresses")
        return self

    def enabled_topology(self) -> dict[str, dict[str, str]]:
        return {
            vm.role: {"image": vm.image, "flavor": vm.flavor, "ip": vm.ip}
            for vm in self.vms
            if vm.enabled
        }


def default_lab3_config(external_network: str = "public") -> DeploymentConfig:
    """Defaults from the Lab 3 topology document."""
    return DeploymentConfig(
        network=NetworkDeploymentSpec(external_network=external_network),
        vms=[
            VMDeploymentSpec(
                role="L-MS",
                image="2_TMP_L-MS_Debian11.11_09.2025.qcow2",
                flavor="small",
                ip="10.0.0.10",
            ),
            VMDeploymentSpec(
                role="L-NFS",
                image="2_TMP_L-NFS_CentOS7_08.2025.qcow2",
                flavor="start",
                ip="10.0.0.70",
            ),
            VMDeploymentSpec(
                role="L-PGSQL",
                image="2_TMP_L-PGSQL_CentOS7_08.2025.qcow2",
                flavor="start",
                ip="10.0.0.55",
            ),
            VMDeploymentSpec(
                role="W-DC",
                image="2_TMP_W-DC_WinSrvStd19_10.2025.qcow2",
                flavor="medium",
                ip="10.0.0.5",
            ),
            VMDeploymentSpec(
                role="V-HYPERV",
                image="2_TMP_V-HYPERV_WinSrvStd19_10.2025.qcow2",
                flavor="large",
                ip="10.0.0.65",
            ),
        ]
    )
