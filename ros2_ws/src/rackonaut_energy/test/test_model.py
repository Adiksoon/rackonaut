from math import pi
from unittest import TestCase

from rackonaut_energy.model import Model, contact, dock_path, estimate, first_requirement, sortie_path


class EnergyTests(TestCase):
    def setUp(self):
        self.dock = (0., 0., .05, 0.)
        self.slot = (8.26, -5.55, 2.89, pi / 2)
        self.model = Model()

    def test_motion_and_climb_draw_more_than_hover(self):
        self.assertLess(self.model.draw(0., 0., 0., False), self.model.draw(0., 0., 0., True))
        self.assertGreater(self.model.draw(.5, 0., .3, True), self.model.draw(.5, 0., -.3, True))
        self.assertGreater(self.model.draw(.5, 0., -.3, True), self.model.draw(0., 0., 0., True))

    def test_dock_requires_stationary_pose_position_yaw_and_height(self):
        self.assertTrue(contact(self.dock, self.dock, 0., 0.))
        for pose in ((.14, 0., .05, 0.), (0., 0., .3, 0.), (0., 0., .05, .3)):
            self.assertFalse(contact(pose, self.dock, 0., 0.))
        self.assertFalse(contact(self.dock, self.dock, .07, 0.))
        self.assertFalse(contact(self.dock, self.dock, 0., .11))

    def test_long_return_stays_in_the_aisle_until_the_transfer_corridor(self):
        back = dock_path(self.slot, self.dock, .79, 2.1)
        self.assertEqual([point[:2] for point in back], [(2.1, -5.55), (2.1, 0.), (0., 0.), (0., 0.)])
        forth = sortie_path(self.dock, .79, 2.1, self.slot)
        full, _ = estimate(self.model, self.dock, [*forth, *back], 4.)
        self.assertAlmostEqual(first_requirement(self.model, self.dock, .79, 2.1, self.slot, 4.),
                               full + self.model.reserve)
