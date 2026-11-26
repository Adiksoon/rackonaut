from types import SimpleNamespace

from rackonaut_mission.recovery import FAILED, Recovery


def test_old_proposal_cannot_authorize_return_and_current_id_can_abort(tmp_path):
    recovery = Recovery(SimpleNamespace(stage="ABORTED"), tmp_path)
    recovery.stop = {"wall": 0.}
    recovery.phase = "WAITING_FOR_OPERATOR_APPROVAL"
    recovery.record = {"recovery_id": "REC-123456789ABC"}
    recovery.proposal = "current"
    transitions = []
    recovery.finish = lambda now, phase, detail: transitions.append((now, phase, detail))
    recovery.action("authorize", recovery.record["recovery_id"], "previous", 1.)
    assert recovery.phase == "WAITING_FOR_OPERATOR_APPROVAL"
    recovery.action("abort", "other", None, 1.)
    assert not transitions
    recovery.action("abort", recovery.record["recovery_id"], None, 1.)
    assert transitions == [(1., FAILED, "Recovery stopped by the operator")]
