import unittest
from math import cos, erf, exp, log, pi, sin, sqrt, tau

import numpy as np

from petrolab.plot_fields import gaussian_kde_grid, gaussian_kde_rings


class GaussianKDETests(unittest.TestCase):
    def test_grid_matches_anisotropic_gaussian_and_window_mass(self):
        hx, hy = 0.125, 0.25
        axis, density = gaussian_kde_grid([(0.5, 0.5)], hx, hy)
        self.assertEqual(list(axis[[0, 64, 128]]), [0, 0.5, 1])
        center = 1 / (2 * pi * hx * hy)
        self.assertAlmostEqual(density[64, 64], center)
        self.assertAlmostEqual(density[64, 80], center * exp(-0.5))
        self.assertAlmostEqual(density[96, 64], center * exp(-0.5))
        # Independent integral of the normalized Gaussian over the unit square.
        expected = erf(0.5 / (sqrt(2) * hx)) * erf(0.5 / (sqrt(2) * hy))
        weights = np.ones(len(axis))
        weights[[0, -1]] = 0.5
        mass = weights @ density @ weights / 128 ** 2
        self.assertAlmostEqual(mass, expected, delta=0.00004)

    def test_half_peak_single_kernel_matches_analytic_radius(self):
        bandwidth, level = 0.1, 0.5
        ring, = gaussian_kde_rings([(0.5, 0.5)], bandwidth, bandwidth, level)
        expected_radius = bandwidth * sqrt(-2 * log(level))
        self.assertEqual(ring[0], ring[-1])
        self.assertGreater(len(ring), 10)
        for x, y in ring:
            self.assertAlmostEqual(abs(complex(x - 0.5, y - 0.5)), expected_radius, delta=0.0003)

    def test_separated_modes_keep_two_closed_regions(self):
        rings = gaussian_kde_rings([(0.25, 0.5), (0.75, 0.5)], 0.05, 0.05, 0.5)
        rings.sort(key=lambda ring: min(x for x, _ in ring))
        self.assertEqual(len(rings), 2)
        self.assertTrue(all(ring[0] == ring[-1] for ring in rings))
        self.assertTrue(all(x < 0.5 for x, _ in rings[0]))
        self.assertTrue(all(x > 0.5 for x, _ in rings[1]))

    def test_annular_density_retains_its_hole(self):
        angles = [tau * index / 24 for index in range(24)]
        samples = [(0.5 + 0.24 * cos(angle), 0.5 + 0.24 * sin(angle)) for angle in angles]
        outer, hole = gaussian_kde_rings(samples, 0.04, 0.04, 0.5)
        self.assertEqual(outer[0], outer[-1])
        self.assertEqual(hole[0], hole[-1])
        self.assertGreater(max(x for x, _ in outer), 0.75)
        self.assertLess(max(x for x, _ in hole), 0.72)

    def test_invalid_parameters_and_coordinates_are_rejected(self):
        with self.assertRaises(ValueError):
            gaussian_kde_grid([(0.5, 0.5)], 0.001, 0.1)
        with self.assertRaises(ValueError):
            gaussian_kde_grid([(float("nan"), 0.5)], 0.1, 0.1)
        with self.assertRaises(ValueError):
            gaussian_kde_rings([(0.5, 0.5)], 0.1, 0.1, 1.0)
