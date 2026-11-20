"""Geometric fields derived from valid points on a scientific projection."""

from math import atan2, cos, hypot, log1p, pi, sin, sqrt
from statistics import covariance, mean, variance


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
