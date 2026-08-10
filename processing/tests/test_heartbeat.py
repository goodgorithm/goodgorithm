import requests

import heartbeat


def test_ping_no_op_when_url_not_configured(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append((a, k)))

    heartbeat.ping(None)

    assert calls == []


def test_ping_calls_the_configured_url(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: calls.append((url, kwargs)))

    heartbeat.ping("https://hc-ping.com/some-uuid")

    assert len(calls) == 1
    assert calls[0][0] == "https://hc-ping.com/some-uuid"
    assert calls[0][1]["timeout"] == heartbeat.PING_TIMEOUT_SECONDS


def test_ping_swallows_request_failures(monkeypatch):
    # A monitoring call must never be able to crash the pipeline it's
    # monitoring - a missed ping is the alert signal itself, not an
    # exception here.
    def raise_error(*args, **kwargs):
        raise requests.ConnectionError("network unreachable")

    monkeypatch.setattr(requests, "get", raise_error)

    heartbeat.ping("https://hc-ping.com/some-uuid")  # must not raise
