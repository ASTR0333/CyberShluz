 
import io
import os
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


class OpenStackClient:
    def __init__(self):
        self._conn = None

    def _connect(self, project_id: str = None) -> openstack.connection.Connection:
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
        if project_id:
            kwargs["project_id"] = project_id
        else:
            kwargs["project_name"] = settings.OS_PROJECT_NAME or "hackhaton_team01"
        return openstack.connect(**kwargs)

    def get_project_connection(self, project_id: str = None) -> openstack.connection.Connection:
        return self._connect(project_id)

     
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
        """Resolve selected flavors and calculate the quota impact before allocation."""
        conn = self._connect()
        required = 0
        missing: list[str] = []
        for vm in deployment.vms:
            if not vm.enabled:
                continue
            flavor = conn.compute.find_flavor(vm.flavor)
            if not flavor:
                missing.append(f"{vm.role}: {vm.flavor}")
                continue
            required += int(flavor.vcpus or 0)
        if missing:
            raise ValueError("OpenStack flavors not found: " + ", ".join(missing))
        return required

     
     
     
     
     
     
    def create_keypair(self, name: str, key_type: str = "ed25519") -> str:
        private_pem, public_openssh = self._generate_local_keypair(key_type)
        conn = self._connect()

         
         
         
        existing = conn.compute.find_keypair(name)
        if existing:
            try:
                conn.compute.delete_keypair(existing)
            except Exception as e:
                raise RuntimeError(f"Cannot replace OpenStack keypair '{name}': {e}") from e

        try:
            conn.compute.create_keypair(name=name, public_key=public_openssh)
        except Exception as e:
             
             
            if key_type != "rsa":
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
        Создаёт ИЗОЛИРОВАННУЮ сеть стенда: своя Neutron-сеть + подсеть 10.0.0.0/24 +
        роутер с внешним шлюзом в `public`. Это даёт каждому студенту собственный
        L2/L3-сегмент (модель изоляции из ТЗ), а фиксированные IP топологии
        (10.0.0.10/55/70/...) больше не конфликтуют между параллельными стендами.
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
        total = len(topology)
        for idx, (vm_role, spec) in enumerate(topology.items()):
            vm_name = f"stand{stand_id}-{vm_role}"
            if progress_cb:
                progress_cb(int(30 + 60 * idx / total), f"Создание ВМ {vm_role} ({idx+1}/{total})...")

            existing = conn.compute.find_server(vm_name)
            if existing and existing.status in ("ACTIVE", "BUILD"):
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
                    "status": existing.status,
                }
                if floating_ip:
                    res["floating_ip"] = floating_ip
                
                results[vm_role] = res
                print(f"[OpenStack] {vm_name} already exists ({existing.status}), skipping")
                continue

            image = conn.compute.find_image(spec["image"])
            if not image:
                raise ValueError(f"Image '{spec['image']}' not found for {vm_role}")

             
            glance_image = conn.image.find_image(spec["image"])
            image_min_disk = (glance_image.min_disk if glance_image else 0) or 0

            flavor = conn.compute.find_flavor(spec["flavor"])
            if not flavor:
                raise ValueError(f"Flavor '{spec['flavor']}' not found for {vm_role}")

             
             
            vol_size = max(20, image_min_disk)

            bdm = [{
                "boot_index": 0,
                "uuid": image.id,
                "source_type": "image",
                "destination_type": "volume",
                "volume_size": vol_size,
                "delete_on_termination": True,
            }]

             
             
            admin_pubkey = conn.compute.get_keypair(admin_key_name).public_key
            student_pubkey = conn.compute.get_keypair(student_key_name).public_key
            user_data = self.build_user_data(vm_role, admin_pubkey, student_pubkey)

            server = conn.compute.create_server(
                name=vm_name,
                flavor_id=flavor.id,
                networks=[{"uuid": network.id, "fixed_ip": spec["ip"]}],
                key_name=admin_key_name,
                security_groups=[{"name": sg.name}],
                block_device_mapping_v2=bdm,
                user_data=user_data,
            )

            results[vm_role] = {
                "server_id": server.id,
                "name": vm_name,
                "expected_ip": spec["ip"],
                "status": "BUILD",
            }

        for vm_role, info in results.items():
            if info.get("status") == "ACTIVE":
                continue
            try:
                server_obj = conn.compute.get_server(info["server_id"])
                server = conn.compute.wait_for_server(server_obj, status="ACTIVE", wait=600)
                actual_ip = topology[vm_role]["ip"]
                if server.addresses:
                    for net_addrs in server.addresses.values():
                        for addr in net_addrs:
                            if addr.get("OS-EXT-IPS:type") == "fixed":
                                actual_ip = addr["addr"]
                                break
                info["ip"] = actual_ip
                info["status"] = "ACTIVE"
            except Exception as e:
                print(f"[OpenStack] Wait for {vm_role} failed: {e}")
                info["ip"] = info["expected_ip"]
                info["status"] = "ERROR"

         
         
         
        if progress_cb:
            progress_cb(95, "Назначение Floating IP для L-MS...")

        for vm_role in ["L-MS"]:
            vm_info = results.get(vm_role)
            if vm_info and vm_info["status"] == "ACTIVE":
                try:
                    floating_ip = self._assign_floating_ip(
                        conn,
                        vm_info["server_id"],
                        deployment.network.external_network,
                    )
                    if floating_ip:
                        vm_info["floating_ip"] = floating_ip
                        print(f"[OpenStack] Floating IP {floating_ip} assigned to {vm_role}")
                except Exception as e:
                    print(f"[OpenStack] Floating IP assignment failed for {vm_role}: {e}")

         
         
        for vm_role in ["L-MS"]:
            vm_info = results.get(vm_role)
            if vm_info and vm_info.get("floating_ip"):
                if progress_cb:
                    progress_cb(97, f"Настройка SSH-доступа на {vm_role}...")
                try:
                    self._verify_lms_access(
                        vm_info["floating_ip"],
                        admin_private_key,
                        student_private_key,
                    )
                    vm_info["ssh_bootstrapped"] = True
                except Exception as e:
                    print(f"[OpenStack] SSH bootstrap failed for {vm_role}: {e}")
                    raise RuntimeError(
                        "L-MS did not pass key-only SSH verification; "
                        "the image must contain cloud-init and OpenSSH"
                    ) from e

         
         
        results["__network__"] = net_info
        return results

    @staticmethod
    def build_user_data(vm_role: str, admin_pubkey: str, student_pubkey: str) -> str:
        """Build a key-only access policy for Linux and Windows cloud images."""
        if vm_role in {"W-DC", "V-HYPERV"}:
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
Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name fDenyTSConnections -Value 1
Disable-NetFirewallRule -DisplayGroup 'Remote Desktop' -ErrorAction SilentlyContinue

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

    def _verify_lms_access(
        self,
        ip: str,
        admin_private_key: str,
        student_private_key: str,
        max_wait: int = 240,
    ) -> None:
        """Fail closed unless both roles work and only the admin can use sudo."""
        import paramiko
        import socket

        def connect(username: str, private_key: str):
            deadline = time.time() + max_wait
            last_error: Exception | None = None
            while time.time() < deadline:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                try:
                    client.connect(
                        hostname=ip,
                        username=username,
                        pkey=self._paramiko_key(private_key),
                        timeout=10,
                        banner_timeout=15,
                        auth_timeout=15,
                        look_for_keys=False,
                        allow_agent=False,
                    )
                    return client
                except (paramiko.SSHException, socket.error, EOFError, TimeoutError) as exc:
                    last_error = exc
                    client.close()
                    time.sleep(5)
            raise RuntimeError(f"key-only SSH to {username}@{ip} failed: {last_error}")

        admin = connect("labadmin", admin_private_key)
        try:
            _, stdout, stderr = admin.exec_command("sudo -n true", timeout=20)
            if stdout.channel.recv_exit_status() != 0:
                raise RuntimeError(stderr.read().decode(errors="ignore")[:300] or "admin sudo failed")
        finally:
            admin.close()

        student = connect("student", student_private_key)
        try:
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
        rules = [
            (22, 22, "tcp"),
            (80, 80, "tcp"),
            (443, 443, "tcp"),
            (9877, 9877, "tcp"),
        ]
        for port_min, port_max, proto in rules:
            try:
                conn.network.create_security_group_rule(
                    security_group_id=sg.id,
                    direction="ingress",
                    ethertype="IPv4",
                    protocol=proto,
                    port_range_min=port_min,
                    port_range_max=port_max,
                    remote_ip_prefix="0.0.0.0/0",
                )
            except Exception:
                pass
        try:
            conn.network.create_security_group_rule(
                security_group_id=sg.id,
                direction="ingress",
                ethertype="IPv4",
                remote_ip_prefix=private_cidr,
            )
        except Exception:
            pass
        try:
            conn.network.create_security_group_rule(
                security_group_id=sg.id,
                direction="ingress",
                ethertype="IPv4",
                protocol="icmp",
                remote_ip_prefix="0.0.0.0/0",
            )
        except Exception:
            pass
        return sg

    def _assign_floating_ip(self, conn, server_id: str, external_network: str = "public") -> str:
        server = conn.compute.get_server(server_id)
        if server.addresses:
            for net_addrs in server.addresses.values():
                for addr in net_addrs:
                    if addr.get("OS-EXT-IPS:type") == "floating":
                        return addr["addr"]

        for fip in conn.network.ips(status="DOWN"):
            try:
                server = conn.compute.get_server(server_id)
                port = None
                for net_addrs in server.addresses.values():
                    for addr in net_addrs:
                        if addr.get("OS-EXT-IPS:type") == "fixed":
                            ports = list(conn.network.ports(
                                device_id=server_id,
                                fixed_ips=f"ip_address={addr['addr']}"
                            ))
                            if ports:
                                port = ports[0]
                                break
                    if port:
                        break
                if port:
                    conn.network.update_ip(fip, port_id=port.id)
                    return fip.floating_ip_address
            except Exception:
                continue

        ext_net = conn.network.find_network(external_network)
        if ext_net:
            try:
                fip = conn.network.create_ip(floating_network_id=ext_net.id)
                server = conn.compute.get_server(server_id)
                port = None
                for net_addrs in server.addresses.values():
                    for addr in net_addrs:
                        if addr.get("OS-EXT-IPS:type") == "fixed":
                            ports = list(conn.network.ports(
                                device_id=server_id,
                                fixed_ips=f"ip_address={addr['addr']}"
                            ))
                            if ports:
                                port = ports[0]
                                break
                    if port:
                        break
                if port:
                    conn.network.update_ip(fip, port_id=port.id)
                    return fip.floating_ip_address
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
