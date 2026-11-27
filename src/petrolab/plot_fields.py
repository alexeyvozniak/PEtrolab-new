"""Geometric fields derived from valid points on a scientific projection."""

from math import atan2, cos, hypot, log1p, pi, sin, sqrt
from statistics import covariance, mean, variance

from contourpy import contour_generator
import numpy as np


KDE_GRID_SIZE = 129
KDE_BANDWIDTH_RANGE = (0.02, 0.5)


def gaussian_kde_grid(points, bandwidth_x, bandwidth_y):
    """Evaluate an equal-weight Gaussian KDE on the normalized plot rectangle."""
    samples = np.asarray(points, dtype=np.float64)
    if (samples.ndim != 2 or samples.shape[1] != 2 or not len(samples)
            or not np.all(np.isfinite(samples) & (samples >= 0) & (samples <= 1))):
        raise ValueError("KDE points must be nonempty, finite, normalized pairs")
    low, high = KDE_BANDWIDTH_RANGE
    if not (low <= bandwidth_x <= high and low <= bandwidth_y <= high):
        raise ValueError("KDE bandwidth outside the supported grid range")

    axis = np.linspace(0.0, 1.0, KDE_GRID_SIZE)
    grid = np.zeros((KDE_GRID_SIZE, KDE_GRID_SIZE))
    positions = axis[np.newaxis, :]
    for start in range(0, len(samples), 1024):
        x, y = samples[start:start + 1024].T
        horizontal = np.exp(-0.5 * ((positions - x[:, np.newaxis]) / bandwidth_x) ** 2)
        vertical = np.exp(-0.5 * ((positions - y[:, np.newaxis]) / bandwidth_y) ** 2)
        grid += vertical.T @ horizontal
    grid /= len(samples) * 2 * pi * bandwidth_x * bandwidth_y
    return axis, grid


def gaussian_kde_rings(points, bandwidth_x, bandwidth_y, level):
    """Return closed rings of the region at or above a fraction of the grid peak."""
    if not 0 < level < 1:
        raise ValueError("KDE level must be a fraction between zero and one")
    axis, grid = gaussian_kde_grid(points, bandwidth_x, bandwidth_y)
    peak = float(grid.max())
    generator = contour_generator(x=axis, y=axis, z=grid, name="serial", fill_type="OuterOffset")
    polygons, offsets = generator.filled(level * peak, float("inf"))
    return [
        polygon[int(start):int(stop)].tolist()
        for polygon, boundaries in zip(polygons, offsets)
        for start, stop in zip(boundaries[:-1], boundaries[1:])
    ]


def convex_hull(points):
    ordered = sorted(set(points))
    if len(ordered) < 3:
        return []

    def half(sequence):
        chain = []
        for point in sequence:
            while len(chain) >= 2:
                (ax, ay), (bx, by) = chain[-2:]
                if (bx - ax) * (point[1] - ay) - (by - ay) * (point[0] - ax) > 0:
                    break
                chain.pop()
            chain.append(point)
        return chain[:-1]

    vertices = half(ordered) + half(reversed(ordered))
    return vertices if len(vertices) >= 3 else []


def normal_probability_ellipse(points, probability):
    """Return the fitted bivariate normal probability contour, not a confidence region for the mean."""
    if len(points) < 3:
        return []
    xs, ys = zip(*points)
    xvar, yvar = variance(xs), variance(ys)
    cov = covariance(xs, ys)
    spread = hypot(xvar - yvar, 2 * cov)
    major_variance = (xvar + yvar + spread) / 2
    minor_variance = (xvar * yvar - cov * cov) / major_variance if major_variance else 0
    if minor_variance <= major_variance * 1e-12:
        return []
    quantile = -2 * log1p(-probability)
    major = sqrt(major_variance * quantile)
    minor = sqrt(minor_variance * quantile)
    rotation = atan2(2 * cov, xvar - yvar) / 2
    cx, cy = mean(xs), mean(ys)
    vertices = []
    for index in range(96):
        angle = 2 * pi * index / 96
        x, y = major * cos(angle), minor * sin(angle)
        vertices.append((cx + x * cos(rotation) - y * sin(rotation), cy + x * sin(rotation) + y * cos(rotation)))
    return vertices


def clip_to_plot_rectangle(vertices):
    """Clip a polygon to the normalized binary axis range using straight segments."""
    for axis, boundary, direction in ((0, 0, 1), (0, 1, -1), (1, 0, 1), (1, 1, -1)):
        if not vertices:
            break
        output = []
        previous = vertices[-1]
        for point in vertices:
            previous_inside = direction * (previous[axis] - boundary) >= 0
            inside = direction * (point[axis] - boundary) >= 0
            if inside != previous_inside:
                fraction = (boundary - previous[axis]) / (point[axis] - previous[axis])
                other = 1 - axis
                intersection = previous[other] + fraction * (point[other] - previous[other])
                output.append((boundary, intersection) if axis == 0 else (intersection, boundary))
            if inside:
                output.append(point)
            previous = point
        vertices = output
    return vertices
