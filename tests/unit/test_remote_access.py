"""
Unit tests for check_remote_access (the app's "Remote access" light).
"""

import pytest

from src.utils import network


@pytest.fixture(autouse=True)
def clear_cache():
    network._remote_cache.clear()
    yield
    network._remote_cache.clear()


def test_no_funnel_url_is_none():
    assert network.check_remote_access("") is None
    assert network.check_remote_access(None) is None


def test_ok_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(network, "_public_ip", lambda h: calls.append(h) or "208.111.35.209")
    monkeypatch.setattr(network, "_health_via", lambda ip, h: True)
    assert network.check_remote_access("https://tkframe.whale-ayu.ts.net") is True
    assert network.check_remote_access("https://tkframe.whale-ayu.ts.net/") is True
    assert calls == ["tkframe.whale-ayu.ts.net"]


def test_failure_is_false_and_rechecked_sooner(monkeypatch):
    def boom(ip, h):
        raise OSError("SSL_ERROR_SYSCALL")
    monkeypatch.setattr(network, "_public_ip", lambda h: "208.111.35.209")
    monkeypatch.setattr(network, "_health_via", boom)
    clock = [1000.0]
    monkeypatch.setattr(network.time, "monotonic", lambda: clock[0])
    assert network.check_remote_access("https://tkframe.whale-ayu.ts.net") is False

    monkeypatch.setattr(network, "_health_via", lambda ip, h: True)
    clock[0] += network.REMOTE_FAIL_TTL - 1
    assert network.check_remote_access("https://tkframe.whale-ayu.ts.net") is False  # still cached
    clock[0] += 2
    assert network.check_remote_access("https://tkframe.whale-ayu.ts.net") is True


def test_unresolvable_host_is_false(monkeypatch):
    monkeypatch.setattr(network, "_public_ip", lambda h: "")
    assert network.check_remote_access("https://nosuch.whale-ayu.ts.net") is False
