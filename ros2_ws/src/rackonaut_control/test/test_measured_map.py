import numpy as np
from sensor_msgs.msg import PointCloud2, PointField

from rackonaut_control.measured_map import FRAME, MeasuredMap, packed_map, spatial_sample


def message(points, seconds=1):
    cloud = PointCloud2(height=1, width=len(points), point_step=12, row_step=len(points) * 12,
                        fields=[PointField(name=name, offset=4 * index, datatype=PointField.FLOAT32, count=1)
                                for index, name in enumerate("xyz")],
                        data=np.asarray(points, dtype="<f4").tobytes())
    cloud.header.frame_id = FRAME
    cloud.header.stamp.sec = seconds
    return cloud


def test_only_finite_canonical_cloud_is_accepted():
    cloud = message([[1., 2., 3.], [4., 5., 6.]])
    assert packed_map(cloud) == bytes(cloud.data)
    cloud.header.frame_id = "unexpected_frame"
    assert packed_map(cloud) is None
    assert packed_map(message([[float("nan"), 0., 0.]])) is None


def test_spatial_detail_preserves_measured_xyz_and_budget():
    points = np.array([[x, y, 0.] for x in range(220) for y in range(110)], dtype="<f4")
    data = points.tobytes()
    assert spatial_sample(data, 80000) is data
    for limit in (2200, 16000):
        display = np.frombuffer(spatial_sample(data, limit), dtype="<f4").reshape(-1, 3)
        assert len(np.unique(display, axis=0)) == len(display) == limit
        assert set(map(tuple, display)) <= set(map(tuple, points))
        assert display[:, 0].min() == 0 and display[:, 0].max() == 219


def test_duplicate_timestamps_do_not_refresh_a_historical_map():
    stream = MeasuredMap()
    first = message([[1., 2., 3.]])
    stream.accept(first)
    sample = stream.sample
    stream.accept(first)
    assert stream.sample is sample
    assert stream.payload(sample, "high") == bytes(first.data)
    stream.new_session()
    assert stream.sample is None
    stream.accept(first)
    assert stream.sample.session != sample.session
