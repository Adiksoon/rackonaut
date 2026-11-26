from unittest.mock import patch

from rackonaut_control.service import BLOCKED, PRODUCTION, READY, Calibration, ServiceAccess


def test_code_throttle_and_session_revocation(monkeypatch):
    monkeypatch.setenv("RACKONAUT_SERVICE_CODE", "temporary-test-code")
    monkeypatch.setenv("RACKONAUT_SERVICE_SESSION_SECONDS", "10")
    access = ServiceAccess()
    with patch("rackonaut_control.service.monotonic", return_value=100) as now:
        for _ in range(5):
            assert access.unlock("wrong")[0] == 401
        assert access.unlock("temporary-test-code")[0] == 429
        now.return_value = 161
        status, token, _ = access.unlock("temporary-test-code")
        assert status == 200
        assert access.authorized(token)
        assert not access.authorized("forged-token")
        now.return_value = 172
        assert not access.authorized(token)
        _, token, _ = access.unlock("temporary-test-code")
        access.revoke(token)
        assert not access.authorized(token)


def test_missing_code_disables_unlock(monkeypatch):
    monkeypatch.delenv("RACKONAUT_SERVICE_CODE", raising=False)
    assert ServiceAccess().unlock("guess")[0] == 503


def test_draft_is_empty_and_restart_never_requests_motion(tmp_path):
    path = tmp_path / "calibration-draft.json"
    calibration = Calibration(path)
    calibration.start("Example warehouse", "INS-CONTROL-TEST", 42.)
    calibration.set_state(READY, "Dock confirmed")
    draft = calibration.snapshot()["draft"]
    assert draft["locations"] == draft["waypoints"] == []
    assert draft["map_reference"] is None
    restarted = Calibration(path)
    assert restarted.state == BLOCKED
    assert restarted.owner is None
    assert restarted.draft["calibration_id"] == draft["calibration_id"]
    restarted.clear()
    assert restarted.state == PRODUCTION
    assert not path.exists()
