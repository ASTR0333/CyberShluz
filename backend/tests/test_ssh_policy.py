import sys
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
