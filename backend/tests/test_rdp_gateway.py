import paramiko
import pytest

from app.services import rdp_gateway


class FakeChannel:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_wait_for_rdp_retries_transient_channel_timeout(monkeypatch) -> None:
    clock = FakeClock()
    channel = FakeChannel()

    class FakeTransport:
        attempts = 0

        @staticmethod
        def is_active() -> bool:
            return True

        def open_channel(self, *_args, **_kwargs):
            self.attempts += 1
            if self.attempts == 1:
                raise paramiko.SSHException("Timeout opening channel.")
            return channel

    transport = FakeTransport()
    monkeypatch.setattr(rdp_gateway.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(rdp_gateway.time, "sleep", clock.sleep)
    monkeypatch.setattr(rdp_gateway.settings, "RDP_READY_TIMEOUT_SECONDS", 10)
    monkeypatch.setattr(rdp_gateway.settings, "RDP_CHANNEL_ATTEMPT_TIMEOUT_SECONDS", 2)

    rdp_gateway._wait_for_rdp(transport, "10.10.0.5")

    assert transport.attempts == 2
    assert channel.closed is True


def test_wait_for_rdp_reports_bounded_readiness_timeout(monkeypatch) -> None:
    clock = FakeClock()

    class FakeTransport:
        @staticmethod
        def is_active() -> bool:
            return True

        @staticmethod
        def open_channel(*_args, **kwargs):
            clock.now += kwargs["timeout"]
            raise paramiko.SSHException("Timeout opening channel.")

    monkeypatch.setattr(rdp_gateway.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(rdp_gateway.time, "sleep", clock.sleep)
    monkeypatch.setattr(rdp_gateway.settings, "RDP_READY_TIMEOUT_SECONDS", 3)
    monkeypatch.setattr(rdp_gateway.settings, "RDP_CHANNEL_ATTEMPT_TIMEOUT_SECONDS", 1)

    with pytest.raises(rdp_gateway.RDPGatewayError, match="в течение 3 с"):
        rdp_gateway._wait_for_rdp(FakeTransport(), "10.10.0.5")


def test_wait_for_rdp_does_not_retry_disabled_ssh_forwarding(monkeypatch) -> None:
    class FakeTransport:
        attempts = 0

        @staticmethod
        def is_active() -> bool:
            return True

        def open_channel(self, *_args, **_kwargs):
            self.attempts += 1
            raise paramiko.ChannelException(1, "Administratively prohibited")

    transport = FakeTransport()
    monkeypatch.setattr(rdp_gateway.settings, "RDP_READY_TIMEOUT_SECONDS", 10)

    with pytest.raises(rdp_gateway.RDPGatewayError, match="AllowTcpForwarding"):
        rdp_gateway._wait_for_rdp(transport, "10.10.0.5")

    assert transport.attempts == 1
