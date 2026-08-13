import sys
import subprocess
from types import SimpleNamespace


# The policy builder is pure; a tiny module stub keeps this unit test independent
# from the optional native ``netifaces`` dependency of openstacksdk on Windows.
sys.modules.setdefault(
    "openstack",
    SimpleNamespace(connection=SimpleNamespace(Connection=object), connect=lambda **_: None),
)

from app.core.openstack_client import OpenStackClient  # noqa: E402


ADMIN_KEY = "ssh-ed25519 AAAA-admin admin@test"
STUDENT_KEY = "ssh-ed25519 AAAA-student student@test"


def test_linux_cloud_init_separates_admin_and_student() -> None:
    user_data = OpenStackClient.build_user_data("L-MS", ADMIN_KEY, STUDENT_KEY)

    assert "name: labadmin" in user_data
    assert "labadmin ALL=(ALL) NOPASSWD:ALL" in user_data
    assert "name: student" in user_data
    assert "student ALL=(ALL) NOPASSWD:ALL" not in user_data
    assert "gpasswd -d student sudo" in user_data
    assert "PermitRootLogin no" in user_data
    assert "PasswordAuthentication no" in user_data
    assert "ssh_pwauth: false" in user_data
    assert ADMIN_KEY in user_data
    assert STUDENT_KEY in user_data


def test_windows_cloudbase_init_uses_keys_and_standard_student() -> None:
    user_data = OpenStackClient.build_user_data("W-DC", ADMIN_KEY, STUDENT_KEY)

    assert user_data.startswith("#ps1")
    assert "net localgroup Administrators labadmin /add" in user_data
    assert "net localgroup Administrators student /delete" in user_data
    assert "administrators_authorized_keys" in user_data
    assert "PasswordAuthentication' = 'no'" in user_data
    assert ADMIN_KEY in user_data
    assert STUDENT_KEY in user_data


def test_legacy_bootstrap_creates_separate_users_and_disables_passwords() -> None:
    script = OpenStackClient._legacy_bootstrap_script()

    path_setup = 'export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin${PATH:+:$PATH}"'
    assert path_setup in script
    assert script.index(path_setup) < script.index('ensure_user "$admin_user"')
    assert 'ensure_user "$admin_user"' in script
    assert 'ensure_user "$student_user"' in script
    assert 'install_key "$admin_user" "$admin_key"' in script
    assert 'install_key "$student_user" "$student_key"' in script
    assert "NOPASSWD:ALL" in script
    assert 'gpasswd -d "$student_user" sudo' in script
    assert "PasswordAuthentication no" in script
    assert "PermitRootLogin no" in script
    assert "sshd -t" in script

    syntax_check = subprocess.run(
        ["bash", "-n"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    assert syntax_check.returncode == 0, syntax_check.stderr
