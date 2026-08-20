 
import base64
import io
import os
import re
import shlex
import time

import openstack
import urllib3
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from app.core.config import settings
from app.core.topology import DeploymentConfig, default_lab3_config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class CapacityExceededException(Exception):
    pass


class SSHBootstrapError(RuntimeError):
    """The access VM could not be hardened and verified safely."""


class VMProvisioningError(RuntimeError):
    """Nova could not bring every requested VM to ACTIVE within the deadline."""


class OpenStackClient:
    SSH_POLICY_METADATA_KEY = "cybershluz_ssh_policy"
    SSH_POLICY_VERSION = "3"

    def __init__(self, project_ref: str | None = None):
        self._conn = None
        self.project_ref = project_ref

    def _connect(self, project_ref: str | None = None) -> openstack.connection.Connection:
        kwargs = dict(
            auth_url=settings.OS_AUTH_URL,
            username=settings.OS_USERNAME,
            password=settings.OS_PASSWORD,
            user_domain_name=settings.OS_USER_DOMAIN_NAME or "Hackhaton",
            project_domain_name=settings.OS_PROJECT_DOMAIN_NAME or "Hackhaton",
            region_name=settings.OS_REGION_NAME or "RegionOne",
            verify=False,
            interface="public",
            connect_timeout=30,
        )
        target = project_ref or self.project_ref
        if target and ":slot" in target:
            # A logical pool can contain several slots in one OpenStack project.
            kwargs["project_name"] = target.split(":slot", 1)[0]
        elif target:
            kwargs["project_id"] = target
        else:
            kwargs["project_name"] = settings.OS_PROJECT_NAME or "hackhaton_team01"
        return openstack.connect(**kwargs)

    def get_project_connection(self, project_ref: str | None = None) -> openstack.connection.Connection:
        return self._connect(project_ref)

     
    def check_capacity(self, required_vcpus: int = 10) -> float:
        """
        Возвращает прогнозируемую утилизацию кластера (0.0 - 1.0) за миллисекунды.
        """
        try:
            conn = self._connect()
            limits = conn.compute.get_limits()
            
             
            abs_limits = limits.absolute if hasattr(limits, 'absolute') else limits.get('absolute', {})
            
            if isinstance(abs_limits, dict):
                max_cores = abs_limits.get('maxTotalCores', abs_limits.get('max_total_cores', 100))
                used_cores = abs_limits.get('totalCoresUsed', abs_limits.get('total_cores_used', 0))
            else:
                max_cores = getattr(abs_limits, 'maxTotalCores', getattr(abs_limits, 'max_total_cores', 100))
                used_cores = getattr(abs_limits, 'totalCoresUsed', getattr(abs_limits, 'total_cores_used', 0))
            
            if max_cores <= 0 or max_cores == -1:  
                return 0.0
                
            projected_usage = used_cores + required_vcpus
            return float(projected_usage) / float(max_cores)
            
        except Exception as e:
            print(f"[OpenStack] Limits check failed: {e}")
            raise CapacityExceededException(f"Не удалось получить квоты Nova API: {e}")

     
    def get_cluster_utilization(self) -> float:
        return self.check_capacity(required_vcpus=0)

    def get_deployment_catalog(self) -> dict[str, list[str]]:
        """Return selectable OpenStack resources for the deployment form."""
        conn = self._connect()
        return {
            "images": sorted({image.name for image in conn.compute.images() if image.name}),
            "flavors": sorted({flavor.name for flavor in conn.compute.flavors() if flavor.name}),
            "external_networks": sorted(
                {
                    network.name
                    for network in conn.network.networks(is_router_external=True)
                    if network.name
                }
            ),
        }

    def required_vcpus(self, deployment: DeploymentConfig) -> int:
        """Validate catalog selections and calculate quota impact before allocation."""
        conn = self._connect()
        required = 0
        missing_flavors: list[str] = []
        missing_images: list[str] = []
        for vm in deployment.vms:
            if not vm.enabled:
                continue
            if not conn.compute.find_image(vm.image):
                missing_images.append(f"{vm.role}: {vm.image}")
            flavor = conn.compute.find_flavor(vm.flavor)
            if not flavor:
                missing_flavors.append(f"{vm.role}: {vm.flavor}")
                continue
            required += int(flavor.vcpus or 0)
        if missing_images:
            raise ValueError("OpenStack images not found: " + ", ".join(missing_images))
        if missing_flavors:
            raise ValueError("OpenStack flavors not found: " + ", ".join(missing_flavors))
        if not conn.network.find_network(deployment.network.external_network):
            raise ValueError(
                f"External network '{deployment.network.external_network}' was not found"
            )
        return required

     
     
     
     
     
     
    def create_keypair(
        self,
        name: str,
        key_type: str = "ed25519",
        private_key: str | None = None,
    ) -> str:
        """Create or reconcile a keypair without rotating keys on task retries."""
        generated = private_key is None
        if generated:
            private_pem, public_openssh = self._generate_local_keypair(key_type)
        else:
            private_pem = private_key
            public_openssh = self._public_key_from_private(private_pem)
        conn = self._connect()

        existing = conn.compute.find_keypair(name)
        existing_public = getattr(existing, "public_key", "") if existing else ""
        if existing and self._key_identity(existing_public) != self._key_identity(public_openssh):
            try:
                conn.compute.delete_keypair(existing)
            except Exception as e:
                raise RuntimeError(f"Cannot replace OpenStack keypair '{name}': {e}") from e
            existing = None

        if not existing:
            try:
                conn.compute.create_keypair(name=name, public_key=public_openssh)
            except Exception as e:
                if generated and key_type != "rsa":
                    print(f"[OpenStack] upload ed25519 keypair failed ({e}), fallback to RSA")
                    private_pem, public_openssh = self._generate_local_keypair("rsa")
                    conn.compute.create_keypair(name=name, public_key=public_openssh)
                else:
                    raise

         
        key_dir = "/app/ssh_keys"
        key_path = f"{key_dir}/{name}.pem"
        try:
            os.makedirs(key_dir, exist_ok=True)
            with open(key_path, "w") as f:
                f.write(private_pem)
             
            os.chmod(key_path, 0o600)
        except Exception as e:
            print(f"[OpenStack] Warning: Failed to write ssh key to disk: {e}")

        return private_pem

    @staticmethod
    def _key_identity(public_key: str) -> str:
        """Compare OpenSSH keys without depending on an optional comment."""
        return " ".join(public_key.strip().split()[:2])

    @staticmethod
    def _public_key_from_private(private_key: str) -> str:
        key = serialization.load_ssh_private_key(private_key.encode("utf-8"), password=None)
        return key.public_key().public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        ).decode("utf-8")

    @staticmethod
    def _generate_local_keypair(key_type: str = "ed25519") -> tuple[str, str]:
        """Генерирует SSH-keypair локально. Возвращает (private_pem, public_openssh)."""
        if key_type == "rsa":
            priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        else:
            priv = ed25519.Ed25519PrivateKey.generate()

        private_pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        public_openssh = priv.public_key().public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        ).decode("utf-8")

        return private_pem, public_openssh

    def _ensure_stand_network(self, conn, stand_id: str, deployment: DeploymentConfig) -> dict:
        """
        Создаёт ИЗОЛИРОВАННУЮ сеть стенда: своя Neutron-сеть + подсеть 10.10.0.0/24 +
        роутер с внешним шлюзом в `Public`. Это даёт каждому студенту собственный
        L2/L3-сегмент (модель изоляции из ТЗ), а фиксированные IP топологии
        (10.10.0.10/55/70/...) больше не конфликтуют между параллельными стендами.
        Идемпотентно: повторный вызов переиспользует уже созданные объекты.
        """
        net_name = f"stand{stand_id}-net"
        subnet_name = f"stand{stand_id}-subnet"
        router_name = f"stand{stand_id}-router"
        spec = deployment.network

        network = conn.network.find_network(net_name)
        if not network:
            network = conn.network.create_network(
                name=net_name, description=f"Изолированная сеть стенда #{stand_id}"
            )

        subnet = conn.network.find_subnet(subnet_name)
        if not subnet:
            subnet = conn.network.create_subnet(
                name=subnet_name,
                network_id=network.id,
                ip_version=4,
                cidr=spec.cidr,
                gateway_ip=spec.gateway,
                allocation_pools=[{"start": spec.dhcp_start, "end": spec.dhcp_end}],
                dns_nameservers=spec.dns_nameservers,
                enable_dhcp=True,
            )

        router = conn.network.find_router(router_name)
        if not router:
            ext = conn.network.find_network(spec.external_network)
            if not ext:
                raise ValueError(f"External network '{spec.external_network}' was not found")
            gw = {"network_id": ext.id}
            router = conn.network.create_router(name=router_name, external_gateway_info=gw)
            try:
                conn.network.add_interface_to_router(router, subnet_id=subnet.id)
            except Exception as e:
                print(f"[OpenStack] add router interface failed: {e}")

        return {
            "network_id": network.id,
            "subnet_id": subnet.id,
            "router_id": router.id,
            "cidr": spec.cidr,
            "gateway": spec.gateway,
            "dhcp_start": spec.dhcp_start,
            "dhcp_end": spec.dhcp_end,
            "external_network": spec.external_network,
            "name": net_name,
        }

    def _teardown_stand_network(self, conn, stand_id: str):
        """Сносит изолированную сеть стенда (роутер → подсеть → сеть). По имени,
        чтобы работать даже без сохранённых id."""
        errors: list[str] = []
        router = conn.network.find_router(f"stand{stand_id}-router")
        if router:
            try:
                for port in conn.network.ports(device_id=router.id):
                    if port.device_owner and "router_interface" in port.device_owner:
                        for fixed in port.fixed_ips:
                            try:
                                conn.network.remove_interface_from_router(
                                    router, subnet_id=fixed["subnet_id"]
                                )
                            except Exception:
                                pass
            except Exception as e:
                print(f"[OpenStack] router iface teardown failed: {e}")
            try:
                conn.network.update_router(router, external_gateway_info=None)
            except Exception:
                pass
            try:
                conn.network.delete_router(router)
            except Exception as e:
                print(f"[OpenStack] delete router failed: {e}")
                errors.append(f"router: {e}")

        net = conn.network.find_network(f"stand{stand_id}-net")
        if net:
            try:
                conn.network.delete_network(net)
            except Exception as e:
                print(f"[OpenStack] delete network failed: {e}")
                errors.append(f"network: {e}")
        if errors:
            raise RuntimeError("; ".join(errors))

    def deploy_lab3_stand(
        self,
        stand_id: str,
        admin_key_name: str,
        student_key_name: str,
        admin_private_key: str,
        student_private_key: str,
        deployment: DeploymentConfig | None = None,
        progress_cb=None,
        resource_cb=None,
    ) -> dict[str, dict]:
        conn = self._connect()
        deployment = deployment or default_lab3_config()
        topology = deployment.enabled_topology()

         
        if progress_cb:
            progress_cb(28, "Создание изолированной сети стенда...")
        net_info = self._ensure_stand_network(conn, stand_id, deployment)
        network = conn.network.get_network(net_info["network_id"])

        sg = self._ensure_security_group(conn, stand_id, deployment.network.cidr)

        results = {}
        if resource_cb:
            resource_cb(results, net_info)
        total = len(topology)
        for idx, (vm_role, spec) in enumerate(topology.items()):
            vm_name = f"stand{stand_id}-{vm_role}"
            if progress_cb:
                progress_cb(int(30 + 60 * idx / total), f"Создание ВМ {vm_role} ({idx+1}/{total})...")

            existing = conn.compute.find_server(vm_name)
            existing_status = (
                str(getattr(existing, "status", "") or "").upper()
                if existing
                else ""
            )
            existing_metadata = (getattr(existing, "metadata", None) or {}) if existing else {}
            has_current_ssh_policy = (
                str(existing_metadata.get(self.SSH_POLICY_METADATA_KEY, ""))
                == self.SSH_POLICY_VERSION
            )
            if existing and existing_status in ("ACTIVE", "BUILD") and has_current_ssh_policy:
                actual_ip = spec["ip"]
                floating_ip = None
                if existing.addresses:
                    for net_addrs in existing.addresses.values():
                        for addr in net_addrs:
                            if addr.get("OS-EXT-IPS:type") == "fixed":
                                actual_ip = addr["addr"]
                            elif addr.get("OS-EXT-IPS:type") == "floating":
                                floating_ip = addr["addr"]
                
                res = {
                    "server_id": existing.id,
                    "name": vm_name,
                    "expected_ip": spec["ip"],
                    "ip": actual_ip,
                    "status": existing_status,
                }
                if floating_ip:
                    res["floating_ip"] = floating_ip
                
                results[vm_role] = res
                if resource_cb:
                    resource_cb(results, net_info)
                print(f"[OpenStack] {vm_name} already exists ({existing_status}), skipping")
                continue

            if existing:
                # Servers created before SSH policy v3 received raw, rather
                # than Base64-encoded, user_data. Nova still built them, but
                # cloud-init could not create labadmin or install the shared
                # stand key. Recreate those instances on an explicit retry.
                if existing_status in ("ACTIVE", "BUILD") and not has_current_ssh_policy:
                    print(
                        f"[OpenStack] Recreating {vm_name}: obsolete or missing "
                        "SSH bootstrap metadata"
                    )
                conn.compute.delete_server(existing)
                conn.compute.wait_for_delete(existing, wait=120)

            image = conn.compute.find_image(spec["image"])
            if not image:
                raise ValueError(f"Image '{spec['image']}' not found for {vm_role}")

            flavor = conn.compute.find_flavor(spec["flavor"])
            if not flavor:
                raise ValueError(f"Flavor '{spec['flavor']}' not found for {vm_role}")

            admin_pubkey = conn.compute.get_keypair(admin_key_name).public_key
            student_pubkey = conn.compute.get_keypair(student_key_name).public_key
            raw_user_data = self.build_user_data(vm_role, admin_pubkey, student_pubkey)
            # This is the low-level compute Proxy, not Connection.create_server.
            # The Nova API requires this field to be Base64 encoded.
            user_data = base64.b64encode(raw_user_data.encode("utf-8")).decode("ascii")

            server_args = dict(
                name=vm_name,
                flavor_id=flavor.id,
                networks=[{"uuid": network.id, "fixed_ip": spec["ip"]}],
                key_name=admin_key_name,
                security_groups=[{"name": sg.name}],
                user_data=user_data,
                # Make SSH keys and user_data available even when the Neutron
                # metadata proxy is absent or not yet reachable during boot.
                config_drive=True,
                metadata={self.SSH_POLICY_METADATA_KEY: self.SSH_POLICY_VERSION},
            )
            image_details = image
            if getattr(conn, "image", None):
                image_details = conn.image.find_image(spec["image"]) or image
            image_min_disk = int(getattr(image_details, "min_disk", 0) or 0)
            virtual_size = int(getattr(image_details, "virtual_size", 0) or 0)
            virtual_size_gb = (virtual_size + (1024 ** 3) - 1) // (1024 ** 3)
            required_disk = max(image_min_disk, virtual_size_gb)
            flavor_disk = int(getattr(flavor, "disk", 0) or 0)
            if flavor_disk > 0 and flavor_disk >= required_disk:
                # Prefer Nova's direct image boot. The old implementation sent
                # every VM through Cinder, so a volume quota/backend problem
                # left only keypairs and a network behind.
                server_args["image_id"] = image.id
            else:
                # Diskless flavors explicitly require a boot volume.
                server_args["block_device_mapping_v2"] = [
                    {
                        "boot_index": 0,
                        "uuid": image.id,
                        "source_type": "image",
                        "destination_type": "volume",
                        "volume_size": max(20, required_disk),
                        "delete_on_termination": True,
                    }
                ]

            server = conn.compute.create_server(**server_args)

            results[vm_role] = {
                "server_id": server.id,
                "name": vm_name,
                "expected_ip": spec["ip"],
                "status": "BUILD",
            }
            if resource_cb:
                resource_cb(results, net_info)

        # All instances are created before this point, so wait for them under
        # one shared deadline. Waiting up to 600 seconds for each VM in series
        # used to turn one stuck BUILD into a deployment lasting tens of minutes.
        build_timeout = max(1, int(settings.VM_BUILD_TIMEOUT))
        started = time.monotonic()
        deadline = started + build_timeout
        pending = {role for role, info in results.items() if info.get("status") != "ACTIVE"}
        last_errors: dict[str, str] = {}

        while pending and time.monotonic() < deadline:
            for vm_role in list(pending):
                info = results[vm_role]
                try:
                    server = conn.compute.get_server(info["server_id"])
                    server_status = str(getattr(server, "status", "BUILD") or "BUILD").upper()
                    info["status"] = server_status
                    if server_status == "ACTIVE":
                        actual_ip = topology[vm_role]["ip"]
                        for net_addrs in (getattr(server, "addresses", None) or {}).values():
                            for addr in net_addrs:
                                if addr.get("OS-EXT-IPS:type") == "fixed":
                                    actual_ip = addr["addr"]
                                    break
                        info["ip"] = actual_ip
                        pending.remove(vm_role)
                    elif server_status == "ERROR":
                        fault = getattr(server, "fault", None)
                        if fault:
                            info["error"] = str(fault)
                        info["ip"] = info["expected_ip"]
                        pending.remove(vm_role)
                except Exception as exc:
                    # A transient Nova read error is retried within the same
                    # deadline instead of incorrectly marking the VM failed.
                    last_errors[vm_role] = str(exc)

            if resource_cb:
                resource_cb(results, net_info)
            if progress_cb:
                active = sum(1 for info in results.values() if info.get("status") == "ACTIVE")
                elapsed = min(build_timeout, int(time.monotonic() - started))
                progress_cb(
                    int(90 + 4 * active / max(1, total)),
                    f"Ожидание ВМ: {active}/{total} ACTIVE ({elapsed}/{build_timeout} с)...",
                )
            if pending:
                time.sleep(min(5, max(0, deadline - time.monotonic())))

        for vm_role in pending:
            info = results[vm_role]
            info["ip"] = info["expected_ip"]
            info["status"] = "TIMEOUT"
            if vm_role in last_errors:
                info["error"] = last_errors[vm_role]
        if pending and resource_cb:
            resource_cb(results, net_info)

         
         
         
        linux_roles = [role for role in topology if role.upper().startswith("L-")]
        if progress_cb:
            progress_cb(95, "Назначение Floating IP для Linux-ВМ...")

        floating_ip_errors: list[str] = []
        reserved_floating_ips: set[str] = set()
        for vm_role in linux_roles:
            vm_info = results.get(vm_role)
            if vm_info and vm_info["status"] == "ACTIVE":
                try:
                    floating_ip = self._assign_floating_ip(
                        conn,
                        vm_info["server_id"],
                        deployment.network.external_network,
                        reserved_floating_ips,
                    )
                    if floating_ip:
                        vm_info["floating_ip"] = floating_ip
                        print(f"[OpenStack] Floating IP {floating_ip} assigned to {vm_role}")
                        if resource_cb:
                            resource_cb(results, net_info)
                except Exception as e:
                    print(f"[OpenStack] Floating IP assignment failed for {vm_role}: {e}")
                    floating_ip_errors.append(f"{vm_role}: {e}")

                if not vm_info.get("floating_ip"):
                    floating_ip_errors.append(f"{vm_role}: Floating IP не получен")

        if floating_ip_errors:
            raise CapacityExceededException(
                "Не удалось назначить Floating IP всем Linux-ВМ: "
                + "; ".join(dict.fromkeys(floating_ip_errors))
            )

         
         
        for vm_role in linux_roles:
            vm_info = results.get(vm_role)
            if vm_info and vm_info.get("floating_ip"):
                if progress_cb:
                    progress_cb(97, f"Настройка SSH-доступа на {vm_role}...")
                try:
                    self._prepare_lms_access(
                        vm_info["floating_ip"],
                        admin_private_key,
                        student_private_key,
                        progress_cb,
                        vm_role,
                    )
                    vm_info["ssh_bootstrapped"] = True
                except Exception as e:
                    print(f"[OpenStack] SSH bootstrap failed for {vm_role}: {e}")
                    raise SSHBootstrapError(
                        f"{vm_role} did not pass secure SSH bootstrap and key verification: {e}"
                    ) from e

         
         
        results["__network__"] = net_info
        return results

    @staticmethod
    def build_user_data(vm_role: str, admin_pubkey: str, student_pubkey: str) -> str:
        """Build a key-only access policy for Linux and Windows cloud images."""
        if vm_role.upper().startswith("W") or vm_role.upper() == "V-HYPERV":
            return OpenStackClient._build_windows_user_data(admin_pubkey, student_pubkey)
        return OpenStackClient._build_linux_user_data(admin_pubkey, student_pubkey)

    @staticmethod
    def _build_linux_user_data(admin_pubkey: str, student_pubkey: str) -> str:
        return f"""#cloud-config
users:
  - name: labadmin
    shell: /bin/bash
    lock_passwd: true
    ssh_authorized_keys:
      - {admin_pubkey}
  - name: student
    shell: /bin/bash
    lock_passwd: true
    ssh_authorized_keys:
      - {student_pubkey}

ssh_pwauth: false
disable_root: true

write_files:
  - path: /etc/sudoers.d/90-kibershluz-admin
    owner: root:root
    permissions: '0440'
    content: |
      labadmin ALL=(ALL) NOPASSWD:ALL
  - path: /usr/local/sbin/kibershluz-ssh-hardening
    owner: root:root
    permissions: '0700'
    content: |
      #!/bin/sh
      set -eu
      rm -f /etc/sudoers.d/90-student-nopasswd /etc/sudoers.d/*student*
      gpasswd -d student sudo >/dev/null 2>&1 || true
      gpasswd -d student wheel >/dev/null 2>&1 || true
      passwd -l root >/dev/null 2>&1 || true
      passwd -l labadmin >/dev/null 2>&1 || true
      passwd -l student >/dev/null 2>&1 || true
      set_option() {{
        option="$1"
        value="$2"
        if grep -qiE "^[[:space:]]*#?[[:space:]]*$option[[:space:]]+" /etc/ssh/sshd_config; then
          sed -ri "s|^[[:space:]]*#?[[:space:]]*$option[[:space:]]+.*|$option $value|I" /etc/ssh/sshd_config
        else
          printf '%s %s\\n' "$option" "$value" >> /etc/ssh/sshd_config
        fi
      }}
      set_option PermitRootLogin no
      set_option PasswordAuthentication no
      set_option KbdInteractiveAuthentication no
      set_option ChallengeResponseAuthentication no
      set_option PermitEmptyPasswords no
      set_option PubkeyAuthentication yes
      if [ -d /etc/ssh/sshd_config.d ]; then
        printf '%s\\n' 'PermitRootLogin no' 'PasswordAuthentication no' \\
          'KbdInteractiveAuthentication no' 'ChallengeResponseAuthentication no' \\
          'PermitEmptyPasswords no' 'PubkeyAuthentication yes' \\
          > /etc/ssh/sshd_config.d/99-kibershluz.conf
      fi
      sshd -t
      systemctl restart sshd 2>/dev/null || systemctl restart ssh 2>/dev/null || \\
        service sshd restart 2>/dev/null || service ssh restart

runcmd:
  - [ /usr/local/sbin/kibershluz-ssh-hardening ]
"""

    @staticmethod
    def _build_windows_user_data(admin_pubkey: str, student_pubkey: str) -> str:
        return f"""#ps1
$ErrorActionPreference = 'Stop'
$adminPassword = [guid]::NewGuid().ToString() + 'aA1!'
$studentPassword = [guid]::NewGuid().ToString() + 'aA1!'
net user labadmin $adminPassword /add /y
net localgroup Administrators labadmin /add
net user student $studentPassword /add /y
net localgroup Administrators student /delete 2>$null
# W-DC and V-HYPERV have no Floating IP. RDP is therefore reachable only from
# the isolated stand network (normally through an SSH tunnel via L-MS).
Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name fDenyTSConnections -Value 0
Enable-NetFirewallRule -DisplayGroup 'Remote Desktop' -ErrorAction SilentlyContinue
Set-Service -Name TermService -StartupType Automatic -ErrorAction SilentlyContinue
Start-Service -Name TermService -ErrorAction SilentlyContinue

if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {{
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
}}
New-Item -ItemType Directory -Force -Path C:\\Users\\student\\.ssh | Out-Null
Set-Content -Path C:\\Users\\student\\.ssh\\authorized_keys -Value '{student_pubkey}'
icacls C:\\Users\\student\\.ssh /inheritance:r /grant 'student:(OI)(CI)F' /grant 'SYSTEM:(OI)(CI)F' | Out-Null

New-Item -ItemType Directory -Force -Path C:\\ProgramData\\ssh | Out-Null
Set-Content -Path C:\\ProgramData\\ssh\\administrators_authorized_keys -Value '{admin_pubkey}'
icacls C:\\ProgramData\\ssh\\administrators_authorized_keys /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F' | Out-Null

$config = 'C:\\ProgramData\\ssh\\sshd_config'
$content = Get-Content $config -Raw
$options = @{{
    'PasswordAuthentication' = 'no'
    'KbdInteractiveAuthentication' = 'no'
    'PubkeyAuthentication' = 'yes'
    'PermitEmptyPasswords' = 'no'
}}
foreach ($option in $options.Keys) {{
    if ($content -match "(?im)^\\s*#?\\s*$option\\s+.*$") {{
        $content = $content -replace "(?im)^\\s*#?\\s*$option\\s+.*$", "$option $($options[$option])"
    }} else {{
        $content += "`r`n$option $($options[$option])"
    }}
}}
Set-Content -Path $config -Value $content
Set-Service sshd -StartupType Automatic
Restart-Service sshd
"""

    @staticmethod
    def _paramiko_key(private_key: str):
        import paramiko

        for key_class in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
            try:
                return key_class.from_private_key(io.StringIO(private_key))
            except Exception:
                continue
        raise ValueError("Unsupported SSH private key format")

    def _prepare_lms_access(
        self,
        ip: str,
        admin_private_key: str,
        student_private_key: str,
        progress_cb=None,
        vm_role: str = "Linux VM",
    ) -> None:
        """Use cloud-init keys when available, otherwise harden a legacy image."""
        timeout = max(1, int(settings.SSH_BOOTSTRAP_TIMEOUT))
        bootstrap_user = settings.VM_BOOTSTRAP_USER.strip()
        bootstrap_password = settings.VM_BOOTSTRAP_PASSWORD

        def progress(message: str) -> None:
            if progress_cb:
                progress_cb(98, message)

        if bool(bootstrap_user) != bool(bootstrap_password):
            raise SSHBootstrapError(
                "VM_BOOTSTRAP_USER and VM_BOOTSTRAP_PASSWORD must either both be set or both be empty"
            )

        if bootstrap_user:
            # A short probe keeps cloud-init images on the passwordless path.
            # Explicit bootstrap credentials normally mean this is a legacy
            # image, so do not spend 15 seconds retrying a key that is not yet
            # installed before trying the configured password.
            progress(f"Проверка SSH-ключей cloud-init на {vm_role}...")
            try:
                self._verify_lms_access(
                    ip,
                    admin_private_key,
                    student_private_key,
                    max_wait=min(5, timeout),
                    progress_cb=progress,
                )
                return
            except Exception as key_error:
                print(f"[OpenStack] Initial key-only SSH probe failed: {key_error}")

            progress(f"Ожидание резервного SSH bootstrap на {vm_role} (до {timeout} с)...")
            self._bootstrap_legacy_lms_access(
                ip,
                admin_private_key,
                student_private_key,
                max_wait=timeout,
                progress_cb=progress,
            )

            try:
                progress("Проверка установленных ключей labadmin и student...")
                self._verify_lms_access(
                    ip,
                    admin_private_key,
                    student_private_key,
                    max_wait=min(60, timeout),
                    progress_cb=progress,
                )
                return
            except Exception as exc:
                raise SSHBootstrapError(f"post-bootstrap key verification failed: {exc}") from exc

        try:
            progress(f"Ожидание SSH-ключей cloud-init на {vm_role} (до {timeout} с)...")
            self._verify_lms_access(
                ip,
                admin_private_key,
                student_private_key,
                max_wait=timeout,
                progress_cb=progress,
            )
        except Exception as exc:
            raise SSHBootstrapError(
                "key-only SSH failed and legacy password bootstrap is not configured: "
                f"{exc}"
            ) from exc

    def _bootstrap_legacy_lms_access(
        self,
        ip: str,
        admin_private_key: str,
        student_private_key: str,
        max_wait: int,
        progress_cb=None,
    ) -> None:
        """Enter with the Nova key or image password, install keys, then harden SSH."""
        import paramiko
        import socket

        bootstrap_user = settings.VM_BOOTSTRAP_USER.strip()
        bootstrap_password = settings.VM_BOOTSTRAP_PASSWORD
        root_password = settings.VM_BOOTSTRAP_ROOT_PASSWORD or bootstrap_password
        admin_user = settings.VM_ADMIN_USER.strip()
        student_user = settings.VM_STUDENT_USER.strip()
        for username in (bootstrap_user, admin_user, student_user):
            if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
                raise SSHBootstrapError(f"unsafe Linux username in SSH bootstrap configuration: {username!r}")
        if admin_user == student_user:
            raise SSHBootstrapError("VM_ADMIN_USER and VM_STUDENT_USER must be different")

        admin_public = self._public_key_from_private(admin_private_key)
        student_public = self._public_key_from_private(student_private_key)
        admin_key_b64 = base64.b64encode(admin_public.encode("utf-8")).decode("ascii")
        student_key_b64 = base64.b64encode(student_public.encode("utf-8")).decode("ascii")

        started = time.monotonic()
        deadline = started + max_wait
        last_errors: dict[str, Exception] = {}
        client = None
        connected_with = ""
        bootstrap_pkey = self._paramiko_key(admin_private_key)
        auth_methods = [
            ("Nova-injected admin key", {"pkey": bootstrap_pkey}),
            ("legacy password", {"password": bootstrap_password}),
        ]

        def drain_channel(channel, stdout_chunks: list[bytes], stderr_chunks: list[bytes]) -> None:
            """Drain ready data so a full SSH window cannot stall the command."""
            recv_ready = getattr(channel, "recv_ready", lambda: False)
            while recv_ready():
                chunk = channel.recv(4096)
                if not chunk:
                    break
                stdout_chunks.append(chunk)

            recv_stderr_ready = getattr(channel, "recv_stderr_ready", lambda: False)
            while recv_stderr_ready():
                chunk = channel.recv_stderr(4096)
                if not chunk:
                    break
                stderr_chunks.append(chunk)

        def remote_output_tail(stdout_chunks: list[bytes], stderr_chunks: list[bytes]) -> str:
            output = b"".join(stdout_chunks + stderr_chunks).decode(errors="ignore")
            return output.replace("\r", "").strip()[-1000:]

        def wait_for_exit_status(
            channel,
            stage: str,
            command_timeout: int,
            stdout_chunks: list[bytes] | None = None,
            stderr_chunks: list[bytes] | None = None,
        ) -> int:
            """Wait for a remote command under a real wall-clock deadline.

            Paramiko's ``exec_command(timeout=...)`` only configures channel
            socket operations. ``recv_exit_status()`` itself can otherwise
            block forever when sudo, su, PAM or a service command gets stuck.
            """
            stdout_chunks = stdout_chunks if stdout_chunks is not None else []
            stderr_chunks = stderr_chunks if stderr_chunks is not None else []
            command_started = time.monotonic()
            command_deadline = command_started + command_timeout
            last_reported = -1
            while not channel.exit_status_ready():
                drain_channel(channel, stdout_chunks, stderr_chunks)
                now = time.monotonic()
                elapsed = min(command_timeout, int(now - command_started))
                if progress_cb and (last_reported < 0 or elapsed - last_reported >= 5):
                    progress_cb(f"{stage}: {elapsed}/{command_timeout} с")
                    last_reported = elapsed
                if now >= command_deadline:
                    details = remote_output_tail(stdout_chunks, stderr_chunks)
                    channel.close()
                    raise SSHBootstrapError(
                        f"{stage} did not finish within {command_timeout}s"
                        + (f"; remote output: {details}" if details else "")
                    )
                time.sleep(min(1, command_deadline - now))
            drain_channel(channel, stdout_chunks, stderr_chunks)
            return channel.recv_exit_status()

        def wait_for_su_password_prompt(
            channel,
            command_timeout: int,
            stdout_chunks: list[bytes],
            stderr_chunks: list[bytes],
        ) -> None:
            """Do not send typeahead that su may discard while disabling TTY echo."""
            started_waiting = time.monotonic()
            deadline = started_waiting + command_timeout
            while time.monotonic() < deadline:
                drain_channel(channel, stdout_chunks, stderr_chunks)
                output = b"".join(stdout_chunks).decode(errors="ignore").casefold()
                if "password:" in output or "пароль:" in output:
                    return
                if channel.exit_status_ready():
                    rc = channel.recv_exit_status()
                    details = remote_output_tail(stdout_chunks, stderr_chunks)
                    raise SSHBootstrapError(
                        f"su exited with code {rc} before requesting a password: "
                        f"{details or 'no output'}"
                    )
                time.sleep(min(0.1, deadline - time.monotonic()))

            details = remote_output_tail(stdout_chunks, stderr_chunks)
            channel.close()
            raise SSHBootstrapError(
                f"su did not request a password within {command_timeout}s"
                + (f"; remote output: {details}" if details else "")
            )

        while time.monotonic() < deadline:
            if progress_cb:
                elapsed = min(max_wait, int(time.monotonic() - started))
                progress_cb(f"Ожидание SSH bootstrap на Linux-ВМ: {elapsed}/{max_wait} с")
            for auth_name, auth_kwargs in auth_methods:
                candidate = paramiko.SSHClient()
                candidate.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                try:
                    remaining = max(1, deadline - time.monotonic())
                    candidate.connect(
                        hostname=ip,
                        username=bootstrap_user,
                        timeout=min(10, remaining),
                        banner_timeout=min(15, remaining),
                        auth_timeout=min(15, remaining),
                        look_for_keys=False,
                        allow_agent=False,
                        **auth_kwargs,
                    )
                    client = candidate
                    connected_with = auth_name
                    break
                except (paramiko.SSHException, socket.error, EOFError, TimeoutError) as exc:
                    last_errors[auth_name] = exc
                    candidate.close()
            if client is not None:
                break
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(5, remaining))

        if client is None:
            details = "; ".join(f"{name}: {error}" for name, error in last_errors.items())
            raise SSHBootstrapError(
                f"SSH bootstrap to {bootstrap_user}@{ip} was unavailable for {max_wait}s: "
                f"{details or 'no connection attempt completed'}"
            )

        try:
            if progress_cb:
                progress_cb(f"SSH-вход выполнен ({connected_with}). Проверка прав...")
            print(f"[OpenStack] SSH bootstrap connected via {connected_with}")
            _, sudo_stdout, _ = client.exec_command("sudo -n true", timeout=20)
            passwordless_sudo = wait_for_exit_status(
                sudo_stdout.channel,
                "Проверка sudo без пароля",
                20,
            ) == 0
            sudo_args = "{} {} {} {}".format(
                shlex.quote(admin_user),
                shlex.quote(student_user),
                shlex.quote(admin_key_b64),
                shlex.quote(student_key_b64),
            )
            if passwordless_sudo:
                command = f"sudo -n bash -s -- {sudo_args}"
                stdin_prefix = ""
                get_pty = False
            else:
                # Distinguish a password-protected sudo account from a legacy
                # image whose SSH user is deliberately absent from sudoers.
                probe_stdin, probe_stdout, _ = client.exec_command(
                    "sudo -S -p '' true",
                    timeout=20,
                )
                probe_stdin.write(bootstrap_password + "\n")
                probe_stdin.channel.shutdown_write()
                password_sudo = wait_for_exit_status(
                    probe_stdout.channel,
                    "Проверка sudo с паролем",
                    20,
                ) == 0
                if password_sudo:
                    command = f"sudo -S -p '' bash -s -- {sudo_args}"
                    stdin_prefix = bootstrap_password + "\n"
                    get_pty = False
                    elevation_method = "sudo с паролем"
                else:
                    # `su` reads its password from a TTY. The script is sent as
                    # base64 inside the root command so stdin contains only the
                    # password and cannot be consumed by the child shell.
                    script_b64 = base64.b64encode(
                        self._legacy_bootstrap_script().encode("utf-8")
                    ).decode("ascii")
                    root_command = (
                        f"printf %s {shlex.quote(script_b64)} | base64 -d | "
                        f"bash -s -- {sudo_args}"
                    )
                    # Force a stable prompt and wait for it below. Sending the
                    # password immediately is racy: su may flush queued TTY
                    # input while it disables echo before reading the secret.
                    command = f"LC_ALL=C su root -c {shlex.quote(root_command)}"
                    stdin_prefix = root_password + "\n"
                    get_pty = True
                    elevation_method = "su root"

            if passwordless_sudo:
                elevation_method = "sudo без пароля"
            if progress_cb:
                progress_cb(f"Настройка SSH через {elevation_method}...")
            print(f"[OpenStack] Running SSH hardening via {elevation_method}")

            stdin, stdout, stderr = client.exec_command(
                command,
                timeout=90,
                get_pty=get_pty,
            )
            stdout_chunks: list[bytes] = []
            stderr_chunks: list[bytes] = []
            if get_pty:
                wait_for_su_password_prompt(
                    stdout.channel,
                    15,
                    stdout_chunks,
                    stderr_chunks,
                )
            if stdin_prefix:
                stdin.write(stdin_prefix)
                stdin.flush()
            if not get_pty:
                stdin.write(self._legacy_bootstrap_script())
                stdin.flush()
            stdin.channel.shutdown_write()
            rc = wait_for_exit_status(
                stdout.channel,
                f"Настройка SSH через {elevation_method}",
                90,
                stdout_chunks,
                stderr_chunks,
            )
            stdout_chunks.append(stdout.read())
            stderr_chunks.append(stderr.read())
            output = b"".join(stdout_chunks).decode(errors="ignore")[-500:]
            error = b"".join(stderr_chunks).decode(errors="ignore")[-1000:]
            if rc != 0:
                raise SSHBootstrapError(
                    f"legacy SSH hardening failed with exit code {rc}: {error or output or 'no output'}"
                )
        finally:
            client.close()

        print(
            f"[OpenStack] Legacy Linux VM @ {ip} hardened via {connected_with}; "
            "password SSH disabled"
        )

    @staticmethod
    def _legacy_bootstrap_script() -> str:
        return r'''set -Eeuo pipefail
# `su root -c` preserves the SSH user's environment on some legacy images.
# Keep the standard administrative directories ahead of that inherited PATH:
# account-management tools and sshd commonly live in /usr/sbin or /sbin.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin${PATH:+:$PATH}"

admin_user="$1"
student_user="$2"
admin_key="$(printf '%s' "$3" | base64 -d)"
student_key="$(printf '%s' "$4" | base64 -d)"

ensure_user() {
  local username="$1"
  if id "$username" >/dev/null 2>&1; then
    usermod -s /bin/bash "$username"
  else
    useradd --create-home --shell /bin/bash "$username"
  fi
}

install_key() {
  local username="$1" public_key="$2" user_home
  user_home="$(getent passwd "$username" | cut -d: -f6)"
  test -n "$user_home"
  install -d -m 0700 -o "$username" -g "$username" "$user_home/.ssh"
  printf '%s\n' "$public_key" > "$user_home/.ssh/authorized_keys"
  chown "$username:$username" "$user_home/.ssh/authorized_keys"
  chmod 0600 "$user_home/.ssh/authorized_keys"
}

ensure_user "$admin_user"
ensure_user "$student_user"
install_key "$admin_user" "$admin_key"
install_key "$student_user" "$student_key"

printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$admin_user" > "/etc/sudoers.d/90-kibershluz-admin"
chmod 0440 "/etc/sudoers.d/90-kibershluz-admin"
command -v visudo >/dev/null 2>&1 && visudo -cf "/etc/sudoers.d/90-kibershluz-admin"

rm -f "/etc/sudoers.d/90-${student_user}-nopasswd" "/etc/sudoers.d/90-${student_user}"
gpasswd -d "$student_user" sudo >/dev/null 2>&1 || true
gpasswd -d "$student_user" wheel >/dev/null 2>&1 || true
sed -ri "/^[[:space:]]*${student_user}[[:space:]]+ALL[[:space:]]*=.*$/d" /etc/sudoers

passwd -l root >/dev/null 2>&1 || true
passwd -l "$admin_user" >/dev/null 2>&1 || true
passwd -l "$student_user" >/dev/null 2>&1 || true

set_sshd_option() {
  local option="$1" value="$2"
  if grep -qiE "^[[:space:]]*#?[[:space:]]*${option}[[:space:]]+" /etc/ssh/sshd_config; then
    sed -ri "s|^[[:space:]]*#?[[:space:]]*${option}[[:space:]]+.*|${option} ${value}|I" /etc/ssh/sshd_config
  else
    printf '%s %s\n' "$option" "$value" >> /etc/ssh/sshd_config
  fi
}

set_sshd_option PermitRootLogin no
set_sshd_option PasswordAuthentication no
set_sshd_option KbdInteractiveAuthentication no
set_sshd_option ChallengeResponseAuthentication no
set_sshd_option PermitEmptyPasswords no
set_sshd_option PubkeyAuthentication yes

if [ -d /etc/ssh/sshd_config.d ]; then
  printf '%s\n' \
    'PermitRootLogin no' \
    'PasswordAuthentication no' \
    'KbdInteractiveAuthentication no' \
    'ChallengeResponseAuthentication no' \
    'PermitEmptyPasswords no' \
    'PubkeyAuthentication yes' \
    > /etc/ssh/sshd_config.d/99-kibershluz.conf
fi

sshd -t
systemctl reload sshd 2>/dev/null || systemctl reload ssh 2>/dev/null || \
  service sshd reload 2>/dev/null || service ssh reload
printf 'kibershluz-bootstrap-ok\n'
'''

    def _verify_lms_access(
        self,
        ip: str,
        admin_private_key: str,
        student_private_key: str,
        max_wait: int = 240,
        progress_cb=None,
    ) -> None:
        """Verify both roles within one shared deadline and enforce sudo policy."""
        import paramiko
        import socket

        started = time.monotonic()
        deadline = started + max_wait

        def connect(username: str, private_key: str):
            last_error: Exception | None = None
            while time.monotonic() < deadline:
                if progress_cb:
                    elapsed = min(max_wait, int(time.monotonic() - started))
                    progress_cb(f"Проверка SSH-ключа {username}: {elapsed}/{max_wait} с")
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                try:
                    remaining = max(1, deadline - time.monotonic())
                    client.connect(
                        hostname=ip,
                        username=username,
                        pkey=self._paramiko_key(private_key),
                        timeout=min(10, remaining),
                        banner_timeout=min(15, remaining),
                        auth_timeout=min(15, remaining),
                        look_for_keys=False,
                        allow_agent=False,
                    )
                    return client
                except (paramiko.SSHException, socket.error, EOFError, TimeoutError) as exc:
                    last_error = exc
                    client.close()
                    remaining = deadline - time.monotonic()
                    if remaining > 0:
                        time.sleep(min(5, remaining))
            raise RuntimeError(
                f"key-only SSH to {username}@{ip} failed within shared {max_wait}s timeout: {last_error}"
            )

        admin = connect(settings.VM_ADMIN_USER, admin_private_key)
        try:
            if progress_cb:
                progress_cb(f"Проверка sudo для {settings.VM_ADMIN_USER}...")
            _, stdout, stderr = admin.exec_command("sudo -n true", timeout=20)
            if stdout.channel.recv_exit_status() != 0:
                raise RuntimeError(stderr.read().decode(errors="ignore")[:300] or "admin sudo failed")
        finally:
            admin.close()

        student = connect(settings.VM_STUDENT_USER, student_private_key)
        try:
            if progress_cb:
                progress_cb(f"Проверка ограничений для {settings.VM_STUDENT_USER}...")
            _, stdout, _ = student.exec_command("sudo -n true", timeout=20)
            if stdout.channel.recv_exit_status() == 0:
                raise RuntimeError("student unexpectedly has sudo access")
        finally:
            student.close()

    def _ensure_security_group(self, conn, stand_id: str, private_cidr: str) -> object:
        sg_name = f"stand{stand_id}-key-only-sg"
        sg = conn.network.find_security_group(sg_name)
        if not sg:
            sg = conn.network.create_security_group(
                name=sg_name,
                description=f"Key-only external access and private traffic for stand {stand_id}",
            )
        desired_rules = [
            {
                "direction": "ingress",
                "ethertype": "IPv4",
                "protocol": "tcp",
                "port_range_min": port_min,
                "port_range_max": port_max,
                "remote_ip_prefix": "0.0.0.0/0",
            }
            for port_min, port_max in (
                (22, 22),
                (80, 80),
                (443, 443),
                (9877, 9877),
            )
        ]
        desired_rules.extend(
            [
                {
                    "direction": "ingress",
                    "ethertype": "IPv4",
                    "remote_ip_prefix": private_cidr,
                },
                {
                    "direction": "ingress",
                    "ethertype": "IPv4",
                    "protocol": "icmp",
                    "remote_ip_prefix": "0.0.0.0/0",
                },
                {
                    "direction": "egress",
                    "ethertype": "IPv4",
                    "remote_ip_prefix": "0.0.0.0/0",
                },
            ]
        )

        def value(rule, field):
            return rule.get(field) if isinstance(rule, dict) else getattr(rule, field, None)

        def rule_identity(rule) -> tuple:
            direction = str(value(rule, "direction") or "").lower()
            ethertype = str(value(rule, "ethertype") or "IPv4")
            protocol = value(rule, "protocol")
            protocol = None if protocol in (None, "", "any") else str(protocol).lower()
            prefix = value(rule, "remote_ip_prefix")
            if direction == "egress" and ethertype == "IPv4" and not prefix:
                prefix = "0.0.0.0/0"
            return (
                direction,
                ethertype,
                protocol,
                value(rule, "port_range_min"),
                value(rule, "port_range_max"),
                prefix,
            )

        current_rules = getattr(sg, "security_group_rules", None)
        if current_rules is None:
            current_rules = list(conn.network.security_group_rules(security_group_id=sg.id))
        existing = {rule_identity(rule) for rule in current_rules}
        for desired in desired_rules:
            identity = rule_identity(desired)
            if identity in existing:
                continue
            try:
                conn.network.create_security_group_rule(
                    security_group_id=sg.id,
                    **desired,
                )
                existing.add(identity)
            except Exception as exc:
                # SSH without an ingress rule is indistinguishable from a
                # broken floating IP. Do not hide RBAC/quota/API failures.
                raise RuntimeError(
                    f"Cannot create required rule {identity} in security group {sg_name}: {exc}"
                ) from exc
        return sg

    def _assign_floating_ip(
        self,
        conn,
        server_id: str,
        external_network: str = "Public",
        reserved_ips: set[str] | None = None,
    ) -> str:
        """Attach one verified, unique Floating IP to a server.

        Neutron can briefly keep a just-associated address in a ``DOWN`` list.
        A deployment-level reservation set prevents the next Linux VM from
        selecting that same address and moving it away from the previous VM.
        """
        reserved_ips = reserved_ips if reserved_ips is not None else set()
        server = conn.compute.get_server(server_id)
        if server.addresses:
            for net_addrs in server.addresses.values():
                for addr in net_addrs:
                    if addr.get("OS-EXT-IPS:type") == "floating":
                        floating_ip = addr["addr"]
                        if floating_ip in reserved_ips:
                            continue
                        reserved_ips.add(floating_ip)
                        return floating_ip

        ext_net = conn.network.find_network(external_network)
        if not ext_net:
            raise RuntimeError(f"External network '{external_network}' was not found")

        port = None
        for net_addrs in (server.addresses or {}).values():
            for addr in net_addrs:
                if addr.get("OS-EXT-IPS:type") != "fixed":
                    continue
                ports = list(
                    conn.network.ports(
                        device_id=server_id,
                        fixed_ips=f"ip_address={addr['addr']}",
                    )
                )
                if ports:
                    port = ports[0]
                    break
            if port:
                break
        if not port:
            raise RuntimeError(f"Neutron port was not found for server {server_id}")

        def bind_and_verify(fip) -> str:
            updated = conn.network.update_ip(fip, port_id=port.id)
            floating_id = getattr(updated, "id", None) or getattr(fip, "id", None)
            refreshed = conn.network.get_ip(floating_id) if floating_id else updated
            bound_port_id = getattr(refreshed, "port_id", None)
            if bound_port_id != port.id:
                raise RuntimeError(
                    f"Floating IP association was not confirmed for server {server_id}: "
                    f"expected port {port.id}, got {bound_port_id or 'none'}"
                )
            floating_ip = getattr(refreshed, "floating_ip_address", None)
            if not floating_ip:
                floating_ip = getattr(updated, "floating_ip_address", None)
            if not floating_ip:
                floating_ip = getattr(fip, "floating_ip_address", None)
            if not floating_ip:
                raise RuntimeError("Neutron returned a Floating IP without an address")
            reserved_ips.add(floating_ip)
            return floating_ip

        for fip in conn.network.ips(status="DOWN"):
            floating_ip = getattr(fip, "floating_ip_address", None)
            if not floating_ip or floating_ip in reserved_ips:
                continue
            if getattr(fip, "port_id", None):
                continue
            floating_network_id = getattr(fip, "floating_network_id", None)
            if floating_network_id and floating_network_id != ext_net.id:
                continue
            try:
                return bind_and_verify(fip)
            except Exception as exc:
                print(f"[OpenStack] Reuse floating IP {floating_ip} failed: {exc}")
                continue

        try:
            fip = conn.network.create_ip(floating_network_id=ext_net.id)
            return bind_and_verify(fip)
        except Exception as e:
            print(f"[OpenStack] Create floating IP failed: {e}")
        return ""

    def cleanup_lab3_stand(self, stand_id: str):
        conn = self._connect()
        vm_roles = default_lab3_config().enabled_topology()
        errors: list[str] = []
        for vm_role in vm_roles:
            vm_name = f"stand{stand_id}-{vm_role}"
            try:
                server = conn.compute.find_server(vm_name)
                if not server:
                    continue
                if server.addresses:
                    for net_addrs in server.addresses.values():
                        for addr in net_addrs:
                            if addr.get("OS-EXT-IPS:type") == "floating":
                                fip = conn.network.find_ip(addr["addr"])
                                if fip:
                                    conn.network.update_ip(fip, port_id=None)
                                    conn.network.delete_ip(fip)
                conn.compute.delete_server(server)
            except Exception as e:
                print(f"[OpenStack] Cleanup {vm_name} failed: {e}")
                errors.append(f"{vm_name}: {e}")

        for vm_role in vm_roles:
            vm_name = f"stand{stand_id}-{vm_role}"
            try:
                server = conn.compute.find_server(vm_name)
                if server:
                    conn.compute.wait_for_delete(server, wait=120)
            except Exception as exc:
                errors.append(f"wait {vm_name}: {exc}")

        for key_name in (
            f"key-stand{stand_id}-admin",
            f"key-stand{stand_id}-student",
            f"key-stand{stand_id}",  # cleanup compatibility with older stands
        ):
            try:
                keypair = conn.compute.find_keypair(key_name)
                if keypair:
                    conn.compute.delete_keypair(keypair)
            except Exception as exc:
                errors.append(f"keypair {key_name}: {exc}")

        try:
            security_group = conn.network.find_security_group(f"stand{stand_id}-key-only-sg")
            if security_group:
                conn.network.delete_security_group(security_group)
        except Exception as exc:
            errors.append(f"security group: {exc}")

         
        try:
            self._teardown_stand_network(conn, stand_id)
        except Exception as e:
            print(f"[OpenStack] Network teardown failed for stand {stand_id}: {e}")
            errors.append(f"network: {e}")

        if errors:
            raise RuntimeError("Cleanup is incomplete: " + "; ".join(errors))

        for key_name in (
            f"key-stand{stand_id}-admin",
            f"key-stand{stand_id}-student",
            f"key-stand{stand_id}",
        ):
            try:
                os.remove(f"/app/ssh_keys/{key_name}.pem")
            except FileNotFoundError:
                pass

    def cleanup_vm(self, name: str, project_id: str = None):
        conn = self._connect(project_id)
        server = conn.compute.find_server(name)
        if server:
            if server.addresses:
                for net_addrs in server.addresses.values():
                    for addr in net_addrs:
                        if addr.get("OS-EXT-IPS:type") == "floating":
                            fip = conn.network.find_ip(addr["addr"])
                            if fip:
                                try:
                                    conn.network.update_ip(fip, port_id=None)
                                except Exception:
                                    pass
                                conn.network.delete_ip(fip)
            conn.compute.delete_server(server)
            conn.compute.wait_for_delete(server)
