from unittest import TestCase

import numpy as np
from scipy.spatial.transform import Rotation

from rackonaut_localization.inertial import GRAVITY, State, propagate
from rackonaut_localization.registration import StaticMap
from rackonaut_localization.slam import MeasuredRegistration, group_voxels, planar_voxel_support


class LocalizationTests(TestCase):
    def test_group_voxels_retains_the_first_index_and_sorted_group_order(self):
        voxels = np.array([[2, -1, 1], [-1, 3, 0], [2, -1, 1], [2, -1, -1], [-1, 3, 0]])
        first, membership = group_voxels(voxels)
        np.testing.assert_array_equal(first, [1, 3, 0])
        np.testing.assert_array_equal(membership, [2, 0, 2, 1, 0])

    def test_voxel_support_preserves_oldest_plane_at_a_shelf_edge(self):
        points = np.array([[.01, .02, .01], [.07, .02, .03], [.09, .09, .07], [.09, .09, .08]])
        normals = np.array([[0., 0., 1.], [0., 0., -1.], [1., 0., 0.], [0., 0., 1.]])
        support = planar_voxel_support(points, normals, np.array([0]), np.zeros(4, dtype=int), .18)
        # The second observation shares the plane despite the sign of its normal.
        # The crossing face and the separate parallel plane cannot shift the support.
        np.testing.assert_allclose(support, [[.0154, .02, .01]])

    def test_measured_registration_uses_its_own_keyframes(self):
        x, y = np.meshgrid(np.linspace(-1.5, 1.5, 43), np.linspace(-1.5, 1.5, 43))
        planes = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
        observed = np.vstack((planes - [0, 0, .75], planes[:, [2, 0, 1]] + [1.4, 0, .3],
                              planes[:, [1, 2, 0]] + [0, -1.4, .3]))
        odometry = MeasuredRegistration()
        seed = np.array([-4.7, 10.3, .05])
        yaw = Rotation.from_euler("z", .16)
        moved = seed + [.13, .1, .25]
        second_scan = yaw.inv().apply(observed + seed - moved)
        self.assertIsNone(odometry.match(second_scan, np.zeros(3), seed, yaw))
        self.assertTrue(odometry.consider(observed, np.zeros(3), seed, Rotation.identity()))
        fit = odometry.match(second_scan, np.zeros(3), moved + [.045, -.03, .02], yaw)
        self.assertIsNotNone(fit)
        np.testing.assert_allclose(fit.xyz, moved, atol=.012)
        self.assertGreater(fit.weakest, .011)
        self.assertTrue(odometry.consider(second_scan, np.zeros(3), fit.xyz, fit.attitude))
        self.assertEqual(len(odometry.keyframes), 2)
        self.assertEqual(odometry.keyframe_count, 2)
        self.assertIsNone(MeasuredRegistration().target)

    def test_registration_resolves_translation_and_rotation_in_three_planes(self):
        static = StaticMap([[0., 0., -.05, 5., 5., .1],
                            [-1.5, 0., 1.3, .1, 4., 2.6],
                            [0., 1.5, 1.3, 4., .1, 2.6]])
        xyz = np.array([.2, .1, .8])
        orientation = Rotation.from_euler("xyz", [.015, -.04, .16])
        source = orientation.inv().apply(static.points[::4] - xyz)
        fit = static.match(source, xyz + [.07, -.065, .05],
                           Rotation.from_euler("xyz", [.025, -.03, .13]))
        self.assertIsNotNone(fit)
        np.testing.assert_allclose(fit.xyz, xyz, atol=.008)
        self.assertLess((fit.attitude * orientation.inv()).magnitude(), .007)
        self.assertGreater(fit.weakest, .011)

    def test_plane_alone_exposes_unobservable_directions(self):
        static = StaticMap([[0., 0., -.05, 4., 4., .1]])
        top = static.points[(static.points[:, 2] == 0.) & (np.abs(static.points[:, :2]).max(axis=1) < 1.5)][::3]
        fit = static.match(top - [0., 0., 1.], np.array([0., 0., 1.04]), Rotation.identity())
        self.assertIsNotNone(fit)
        self.assertLess(fit.weakest, .011)

    def test_inertial_prediction_uses_specific_force_and_measured_body_rate(self):
        start = State(0., np.zeros(3), np.zeros(3), Rotation.identity())
        stationary = [(i*.02, np.zeros(3), GRAVITY) for i in range(11)]
        result = propagate(start, .2, stationary, np.zeros(3), np.zeros(3))
        np.testing.assert_allclose(result.xyz, [0., 0., 0.], atol=1.e-10)
        turning = [(i*.02, np.array([0., 0., .3]), GRAVITY) for i in range(11)]
        result = propagate(start, .2, turning, np.zeros(3), np.zeros(3))
        self.assertAlmostEqual(result.attitude.as_euler("xyz")[2], .06, places=5)
