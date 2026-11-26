from collections import deque
from pathlib import Path
import runpy
from threading import Lock

import pytest
from sensor_msgs.msg import Imu

from rackonaut_localization.node import IMU_FRAME, MAX_IMU_AGE

X3Localization = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/localize_x3"))["X3Localization"]


@pytest.fixture
def estimator():
    node = X3Localization.__new__(X3Localization)
    node.samples = deque(maxlen=100)
    node.inbox = deque(maxlen=32)
    node.inbox_lock = Lock()
    node.imu_at = float("-inf")
    node.match_at = 100.
    node.accepted = 1
    node.calibrated = True
    node.quality = "TRACKING"
    node.reason = "Synchronized"
    return node


def imu(second, frame=IMU_FRAME):
    msg = Imu()
    msg.header.frame_id = frame
    msg.header.stamp.sec = second
    return msg


def test_buffer_validates_stamps_without_making_samples_newer(estimator):
    estimator.inbox.extend([
        (99.80, imu(20)),
        (99.85, imu(19)),
        (99.90, imu(21)),
        (99.95, imu(22, frame="another_sensor")),
    ])
    estimator.drain_imu()

    assert [row[0] for row in estimator.samples] == [20., 21.]
    assert estimator.imu_at == 99.90
    assert not estimator.inbox


def test_old_buffered_sample_does_not_hide_dropout(estimator, monkeypatch):
    estimator.inbox.append((100. - MAX_IMU_AGE - .01, imu(20)))
    monkeypatch.setitem(X3Localization.status.__globals__, "monotonic", lambda: 100.)
    assert estimator.status(100.) == ("LOST", "IMU data stopped advancing")
