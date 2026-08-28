import json
from datetime import datetime, timedelta, timezone

from infra import degradation, status_server

# degradation.py's process-global state is reset before every test by the
# autouse _reset_degradation_state fixture in conftest.py.

NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)


# --- degradation.cycle_staleness_message -------------------------------------


def test_cycle_staleness_none_when_last_success_is_recent():
    degradation._last_cycle_success_at = NOW - timedelta(minutes=3)
    started = NOW - timedelta(hours=2)
    assert degradation.cycle_staleness_message(900, started, now=NOW) is None


def test_cycle_staleness_none_within_post_start_grace_when_no_cycle_yet():
    # fresh process, first cycle still running -- measured from started_at
    started = NOW - timedelta(minutes=10)
    assert degradation.cycle_staleness_message(900, started, now=NOW) is None


def test_cycle_staleness_message_when_no_cycle_and_past_grace():
    started = NOW - timedelta(minutes=25)
    msg = degradation.cycle_staleness_message(900, started, now=NOW)
    assert msg == "no successful cycle in 25m"


def test_cycle_staleness_message_when_last_success_is_old():
    degradation._last_cycle_success_at = NOW - timedelta(minutes=40)
    started = NOW - timedelta(hours=5)
    msg = degradation.cycle_staleness_message(900, started, now=NOW)
    assert msg == "no successful cycle in 40m"


# --- _build_status ----------------------------------------------------------


def _fresh_start():
    status_server._started_at = datetime.now(timezone.utc)


def test_build_status_ok_when_clean_and_cycle_fresh():
    _fresh_start()
    degradation.record_cycle_success()
    status = status_server._build_status()
    assert status["status"] == "ok"
    assert status["degraded"] == {}


def test_build_status_degraded_on_subsystem_failure():
    _fresh_start()
    degradation.record_cycle_success()
    degradation.record("dedup", "redis unreachable")
    status = status_server._build_status()
    assert status["status"] == "degraded"
    assert "dedup" in status["degraded"]
    assert "cycle" not in status["degraded"]


def test_build_status_degraded_and_synthetic_cycle_entry_when_loop_wedged():
    # no successful cycle, process started well past the threshold
    status_server._started_at = datetime.now(timezone.utc) - timedelta(
        seconds=status_server.STATUS_STALE_CYCLE_SECONDS + 600
    )
    status = status_server._build_status()
    assert status["status"] == "degraded"
    assert list(status["degraded"]) == ["cycle"]
    assert status["degraded"]["cycle"]["message"].startswith("no successful cycle in ")


def test_build_status_body_is_compact_json():
    _fresh_start()
    body = json.dumps(status_server._build_status(), separators=(",", ":")).encode("utf-8")
    # matches ingestion/'s JSON.stringify framing -- no space after ',' or ':'
    assert b", " not in body
    assert b'": ' not in body
    assert b'"status":"ok"' in body


# --- strict_status_code ---------------------------------------------------------


def test_strict_status_code_maps_ok_to_200_and_degraded_to_503():
    assert status_server.strict_status_code({"status": "ok"}) == 200
    assert status_server.strict_status_code({"status": "degraded"}) == 503
