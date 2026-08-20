import base64
import hashlib
import hmac
import json
from types import SimpleNamespace

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.api.v1 import rdp
from app.core.models import StandStatusEnum


class FakeQuery:
    def __init__(self, stand):
        self.stand = stand

    def filter(self, *_args):
        return self

    def first(self):
        return self.stand


class FakeDb:
    def __init__(self, stand):
        self.stand = stand

    def query(self, *_args):
        return FakeQuery(self.stand)


def test_guacamole_json_is_signed_and_encrypted(monkeypatch) -> None:
    key_hex = "00112233445566778899aabbccddeeff"
    monkeypatch.setattr(rdp.settings, "GUACAMOLE_JSON_SECRET_KEY", key_hex)
    payload = {"username": "student", "expires": 123, "connections": {}}

    encrypted = base64.b64decode(rdp.encrypt_guacamole_json(payload))
    decryptor = Cipher(algorithms.AES(bytes.fromhex(key_hex)), modes.CBC(bytes(16))).decryptor()
    padded = decryptor.update(encrypted) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    signed = unpadder.update(padded) + unpadder.finalize()
    signature, plaintext = signed[:32], signed[32:]

    assert hmac.compare_digest(
        signature,
        hmac.new(bytes.fromhex(key_hex), plaintext, hashlib.sha256).digest(),
    )
    assert json.loads(plaintext) == payload


def test_guacamole_client_identifier_targets_json_wdc() -> None:
    encoded = rdp.guacamole_client_identifier()
    padding_chars = "=" * (-len(encoded) % 4)
    decoded = base64.urlsafe_b64decode(encoded + padding_chars).decode("utf-8")
    assert decoded == "W-DC\0c\0json"


def test_rdp_session_uses_owned_stand_and_internal_wdc(monkeypatch) -> None:
    stand = SimpleNamespace(
        id=7,
        user_id=42,
        status=StandStatusEnum.READY,
        ip_address="203.0.113.10",
        student_private_key="private-key",
        vm_details=json.dumps({"W-DC": {"ip": "10.10.0.5"}}),
        network_details=json.dumps({"cidr": "10.10.0.0/24"}),
    )
    opened = {}
    payloads = []

    class FakeTunnel:
        port = 45123

        def close(self):
            opened["closed"] = True

    def fake_open(lms_ip, private_key, wdc_ip):
        opened.update(lms_ip=lms_ip, private_key=private_key, wdc_ip=wdc_ip)
        return FakeTunnel()

    monkeypatch.setattr(rdp.rdp_tunnel_broker, "open", fake_open)
    monkeypatch.setattr(
        rdp,
        "encrypt_guacamole_json",
        lambda payload: payloads.append(payload) or "token+/=",
    )
    monkeypatch.setattr(rdp.time, "time", lambda: 1000.0)

    response = rdp.create_rdp_session(
        "7",
        db=FakeDb(stand),
        user={"user_id": 42, "role": "student"},
    )

    assert opened == {
        "lms_ip": "203.0.113.10",
        "private_key": "private-key",
        "wdc_ip": "10.10.0.5",
    }
    connection = payloads[0]["connections"]["W-DC"]
    assert connection["protocol"] == "rdp"
    assert connection["parameters"]["hostname"] == "backend"
    assert connection["parameters"]["port"] == "45123"
    assert response["launch_url"].startswith("/rdp/#/client/")
    assert response["launch_url"].endswith("?data=token%2B%2F%3D")
