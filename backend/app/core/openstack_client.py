 
import os
import time

import openstack
import urllib3
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from app.core.config import settings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LAB3_TOPOLOGY = {
    "L-MS": {
        "image": "LAB2_TMP_L-MS/Debian11.11",
        "ip": "10.0.0.10",
        "flavor": "edu 2x2",
    },
    "L-NFS": {
        "image": "LAB2_TMP_L-NFS",
        "ip": "10.0.0.70",
        "flavor": "edu 2x2",
    },
    "L-PGSQL": {
        "image": "LAB2_TMP_L-PGSQL",
        "ip": "10.0.0.55",
        "flavor": "edu 2x2",
    },
    "W-DC": {
        "image": "LAB2_TMP_W-DC",
        "ip": "10.0.0.5",
        "flavor": "edu 4x4",
    },
    "V-HYPERV": {
        "image": "LAB2_TMP_V-HYPERV",
        "ip": "10.0.0.65",
        "flavor": "edu 4x4",
    },
}


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

     
     
     
     
     
     
    def create_keypair(self, name: str, key_type: str = "ed25519") -> str:
        private_pem, public_openssh = self._generate_local_keypair(key_type)
        conn = self._connect()

         
         
         
        existing = conn.compute.find_keypair(name)
        if existing:
            try:
                conn.compute.delete_keypair(existing)
            except Exception as e:
                print(f"[OpenStack] delete keypair failed: {e}")
                name = f"{name}-{int(time.time())}"

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

    def _ensure_stand_network(
        self, conn, stand_id: str, cidr: str = "10.0.0.0/24", gateway: str = "10.0.0.1"
    ) -> dict:
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
                cidr=cidr,
                gateway_ip=gateway,
                dns_nameservers=["8.8.8.8", "1.1.1.1"],
                enable_dhcp=True,
            )

        router = conn.network.find_router(router_name)
        if not router:
            ext = conn.network.find_network("public")
            gw = {"network_id": ext.id} if ext else None
            router = conn.network.create_router(name=router_name, external_gateway_info=gw)
            try:
                conn.network.add_interface_to_router(router, subnet_id=subnet.id)
            except Exception as e:
                print(f"[OpenStack] add router interface failed: {e}")

        return {
            "network_id": network.id,
            "subnet_id": subnet.id,
            "router_id": router.id,
            "cidr": cidr,
            "name": net_name,
        }

    def _teardown_stand_network(self, conn, stand_id: str):
        """Сносит изолированную сеть стенда (роутер → подсеть → сеть). По имени,
        чтобы работать даже без сохранённых id."""
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

        net = conn.network.find_network(f"stand{stand_id}-net")
        if net:
            try:
                conn.network.delete_network(net)
            except Exception as e:
                print(f"[OpenStack] delete network failed: {e}")

    def deploy_lab3_stand(self, stand_id: str, key_name: str, progress_cb=None) -> dict[str, dict]:
        conn = self._connect()

         
        if progress_cb:
            progress_cb(28, "Создание изолированной сети стенда...")
        net_info = self._ensure_stand_network(conn, stand_id)
        network = conn.network.get_network(net_info["network_id"])

        sg = self._ensure_security_group(conn)

        results = {}
        total = len(LAB3_TOPOLOGY)
        for idx, (vm_role, spec) in enumerate(LAB3_TOPOLOGY.items()):
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
                print(f"[OpenStack] Image '{spec['image']}' not found, skipping {vm_role}")
                continue

             
            glance_image = conn.image.find_image(spec["image"])
            image_min_disk = (glance_image.min_disk if glance_image else 0) or 0

            flavor = conn.compute.find_flavor(spec["flavor"])
            if not flavor:
                flavor = conn.compute.find_flavor("edu 2x2")
            if not flavor:
                flavor = conn.compute.find_flavor("small")

             
             
            vol_size = max(20, image_min_disk)

            bdm = [{
                "boot_index": 0,
                "uuid": image.id,
                "source_type": "image",
                "destination_type": "volume",
                "volume_size": vol_size,
                "delete_on_termination": True,
            }]

             
             
            pubkey = conn.compute.get_keypair(key_name).public_key
            user_data = f"""#cloud-config
users:
  - name: student
    sudo: ALL=(ALL) NOPASSWD:ALL
    groups: [sudo, wheel]
    shell: /bin/bash
    lock_passwd: true
    ssh_authorized_keys:
      - {pubkey}

ssh_pwauth: false
disable_root: true

write_files:
  - path: /etc/sudoers.d/90-student-nopasswd
    permissions: '0440'
    content: |
      student ALL=(ALL) NOPASSWD:ALL

runcmd:
  - [ sh, -c, "sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config" ]
  - [ sh, -c, "sed -i 's/^#*PermitEmptyPasswords.*/PermitEmptyPasswords no/' /etc/ssh/sshd_config" ]
  - [ sh, -c, "sed -i 's/^#*ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config" ]
  - [ sh, -c, "sed -i 's/^#*KbdInteractiveAuthentication.*/KbdInteractiveAuthentication no/' /etc/ssh/sshd_config" ]
  - [ sh, -c, "echo 'student ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-student-nopasswd && chmod 0440 /etc/sudoers.d/90-student-nopasswd" ]
  - [ sh, -c, "systemctl restart sshd 2>/dev/null || systemctl restart ssh 2>/dev/null || service sshd restart || service ssh restart || true" ]
"""

            server = conn.compute.create_server(
                name=vm_name,
                flavor_id=flavor.id,
                networks=[{"uuid": network.id, "fixed_ip": spec["ip"]}],
                key_name=key_name,
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
                actual_ip = LAB3_TOPOLOGY[vm_role]["ip"]
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
                    floating_ip = self._assign_floating_ip(conn, vm_info["server_id"])
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
                    pubkey = conn.compute.get_keypair(key_name).public_key
                    self._bootstrap_lms_access(vm_info["floating_ip"], pubkey)
                    vm_info["ssh_bootstrapped"] = True
                except Exception as e:
                    print(f"[OpenStack] SSH bootstrap failed for {vm_role}: {e}")
                    vm_info["ssh_bootstrapped"] = False

         
         
        results["__network__"] = net_info
        return results

    def _bootstrap_lms_access(self, ip: str, public_key: str, max_wait: int = 180):
        """
        Заходит на L-MS по паролю (LAB2_TMP — не cloud-init),
        пробрасывает SSH ключ, отключает парольную аутентификацию
        и настраивает sudo без пароля для student.
        """
        import paramiko
        import socket

        user = settings.VM_DEFAULT_USER
        password = settings.VM_DEFAULT_PASSWORD

         
        client = paramiko.SSHClient()
         
         
         
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())   

        deadline = time.time() + max_wait
        last_err = None
        while time.time() < deadline:
            try:
                client.connect(
                    hostname=ip,
                    username=user,
                    password=password,
                    timeout=10,
                    banner_timeout=15,
                    auth_timeout=15,
                    look_for_keys=False,
                    allow_agent=False,
                )
                break
            except (paramiko.SSHException, socket.error, EOFError, TimeoutError) as e:
                last_err = e
                time.sleep(5)
        else:
            raise RuntimeError(f"SSH на {ip} недоступен за {max_wait}s: {last_err}")

         
        user_cmds = " && ".join([
            "mkdir -p ~/.ssh && chmod 700 ~/.ssh",
            f"echo {public_key!r} >> ~/.ssh/authorized_keys",
            "sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys",
            "chmod 600 ~/.ssh/authorized_keys",
        ])

         
         
         
        sudo_script = f"""\
set -e
# sudoers
echo '{user} ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-{user}-nopasswd
chmod 0440 /etc/sudoers.d/90-{user}-nopasswd
# sshd_config — заменяем или дописываем в конец, чтобы точно сработало
for key in PasswordAuthentication PermitEmptyPasswords ChallengeResponseAuthentication KbdInteractiveAuthentication; do
    if grep -qiE "^[[:space:]]*#?[[:space:]]*${{key}}" /etc/ssh/sshd_config; then
        sed -i "s/^[[:space:]]*#\\?[[:space:]]*${{key}}.*/${{key}} no/I" /etc/ssh/sshd_config
    else
        echo "${{key}} no" >> /etc/ssh/sshd_config
    fi
done
# conf.d — если есть
for f in /etc/ssh/sshd_config.d/*.conf 2>/dev/null; do
    [ -f "$f" ] && sed -i "s/^[[:space:]]*PasswordAuthentication.*/PasswordAuthentication no/I" "$f" || true
done
# перезапуск sshd
systemctl restart sshd 2>/dev/null || systemctl restart ssh 2>/dev/null || service sshd restart 2>/dev/null || service ssh restart 2>/dev/null || true
"""

        try:
             
             
            stdin, stdout, stderr = client.exec_command(user_cmds, timeout=30)   
            rc = stdout.channel.recv_exit_status()
            if rc != 0:
                err = stderr.read().decode(errors="ignore")[:300]
                print(f"[Bootstrap] authorized_keys rc={rc}: {err}")

             
             
            stdin, stdout, stderr = client.exec_command("sudo -S bash -s", timeout=60)   
            stdin.write(password + "\n")
            stdin.write(sudo_script)
            stdin.channel.shutdown_write()
            rc = stdout.channel.recv_exit_status()
            if rc != 0:
                err = stderr.read().decode(errors="ignore")[:500]
                raise RuntimeError(f"sudo bootstrap rc={rc}: {err}")
        finally:
            client.close()

        print(f"[Bootstrap] L-MS @ {ip}: ключ прокинут, парольный SSH выключен, sudo NOPASSWD активен")

    def _ensure_security_group(self, conn) -> object:
        sg_name = "lab-access-sg"
        sg = conn.network.find_security_group(sg_name)
        if sg:
            return sg

        sg = conn.network.create_security_group(name=sg_name, description="Lab access rules")
        rules = [
            (22, 22, "tcp"),
            (80, 80, "tcp"),
            (443, 443, "tcp"),
            (9877, 9877, "tcp"),
            (3389, 3389, "tcp"),
            (5432, 5432, "tcp"),
            (111, 111, "tcp"),
            (111, 111, "udp"),
            (2049, 2049, "tcp"),
            (2049, 2049, "udp"),
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
                protocol="icmp",
                remote_ip_prefix="0.0.0.0/0",
            )
        except Exception:
            pass
        return sg

    def _assign_floating_ip(self, conn, server_id: str) -> str:
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

        ext_net = conn.network.find_network("public")
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
        for vm_role in LAB3_TOPOLOGY:
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

        for vm_role in LAB3_TOPOLOGY:
            vm_name = f"stand{stand_id}-{vm_role}"
            try:
                server = conn.compute.find_server(vm_name)
                if server:
                    conn.compute.wait_for_delete(server, wait=120)
            except Exception:
                pass

        try:
            keypair = conn.compute.find_keypair(f"key-stand{stand_id}")
            if keypair:
                conn.compute.delete_keypair(keypair)
        except Exception:
            pass

         
        try:
            self._teardown_stand_network(conn, stand_id)
        except Exception as e:
            print(f"[OpenStack] Network teardown failed for stand {stand_id}: {e}")

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