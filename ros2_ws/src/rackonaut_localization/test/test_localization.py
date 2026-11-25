from unittest import TestCase

import numpy as np
from scipy.spatial.transform import Rotation

from rackonaut_localization.inertial import GRAVITY, State, propagate
from rackonaut_localization.registration import StaticMap


class LocalizationTests(TestCase):
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
