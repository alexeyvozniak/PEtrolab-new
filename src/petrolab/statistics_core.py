"""Versioned exploratory statistics over explicitly selected measured features."""

import numpy as np

from .analyte_dictionary import COMPONENTS, ELEMENTS, REPORTED_INDICES, REPORTED_INDEX_UNITS
from .clean_table import VALID_MEASUREMENT_UNITS
from .import_preview import ImportCommandError


_OXIDES = frozenset(COMPONENTS) - {"Total", "LOI", "H2O", "H2O+", "H2O-"}
_ELEMENTS = frozenset(ELEMENTS)


def feature_domain(feature):
    field, unit = feature["field"], feature["unit"]
    if unit == "wt.%" and field in _OXIDES:
        return "oxide_wt_percent"
    if unit in ("ppm", "ppb") and field in _ELEMENTS:
        return "trace_concentration"
    if unit == "apfu" and field in _ELEMENTS:
        return "apfu"
    if unit == "ratio" or (field in REPORTED_INDICES and unit in REPORTED_INDEX_UNITS):
        return "ratio_or_index"
    return "other"


def review_feature_domains(features):
    domains = [feature_domain(feature) for feature in features]
    units = {feature["unit"] for feature in features}
    contexts = {(feature["method"], feature["measurement_set"]) for feature in features}
    names = {feature["field"] for feature in features}
    totals = names & {"FeOt", "Fe2O3t"}
    overlapping_iron = bool(totals and (len(totals) > 1 or names & {"FeO", "Fe2O3"}))
    logratio_available = (
        len(features) >= 2 and len(names) == len(features) and len(set(domains)) == 1
        and domains[0] in {"oxide_wt_percent", "trace_concentration", "apfu"}
        and len(units) == len(contexts) == 1 and not overlapping_iron
    )
    return {"domains": domains, "logratio_available": logratio_available, "mixed_context": len(contexts) > 1,
            "mixed_units": len(units) > 1, "overlapping_iron": overlapping_iron,
            "euclidean_available": all(unit in VALID_MEASUREMENT_UNITS or unit in {"epsilon", "permil"} for unit in units)}


def transform_values(values, transform):
    data = np.asarray(values, dtype=np.float64)
    if data.ndim != 2 or data.shape[1] < 2 or not np.isfinite(data).all():
        raise ValueError("statistics_matrix")
    if transform == "euclidean":
        if np.abs(data).max() > 1e100:
            raise ImportCommandError("STATISTICS_NUMERIC_RANGE", "Числа выходят за поддерживаемый диапазон расчёта.")
        return data
    if transform not in ("clr", "ilr") or np.any(data <= 0):
        raise ValueError("statistics_transform")
    logged = np.log(data)
    if transform == "clr":
        return logged - logged.mean(axis=1, keepdims=True)
    count = np.arange(1, data.shape[1])
    return (np.cumsum(logged[:, :-1], axis=1) / count - logged[:, 1:]) * np.sqrt(count / (count + 1))


def scale_values(data, scaling):
    if scaling == "none":
        center, spread = np.zeros(data.shape[1]), np.ones(data.shape[1])
    elif scaling == "standard":
        center, spread = np.mean(data, axis=0), np.std(data, axis=0)
    elif scaling == "robust":
        low, center, high = np.quantile(data, (0.25, 0.5, 0.75), axis=0, method="linear")
        spread = high - low
    else:
        raise ValueError("statistics_scaling")
    spread = np.where(spread == 0, 1, spread)
    scaled = (data - center) / spread
    if not np.isfinite(scaled).all() or np.abs(scaled).max() > 1e100:
        raise ImportCommandError("STATISTICS_NUMERIC_RANGE", "Масштабирование выводит числа за поддерживаемый диапазон.")
    return scaled, {"center": center.tolist(), "scale": spread.tolist()}


def fit_kmeans(data, clusters, seed):
    unique = np.unique(data, axis=0)
    if len(unique) < clusters:
        raise ImportCommandError("STATISTICS_CLUSTERS_TOO_MANY", "Для такого числа кластеров недостаточно различных строк.")
    generator = np.random.default_rng(seed)
    best = None
    for _ in range(8):
        centers = unique[generator.choice(len(unique), clusters, replace=False)].copy()
        previous = None
        for iteration in range(1, 101):
            distances = np.sum((data[:, None, :] - centers[None, :, :]) ** 2, axis=2)
            labels = np.argmin(distances, axis=1)
            counts = np.bincount(labels, minlength=clusters)
            if np.any(counts == 0):
                break
            if np.array_equal(previous, labels):
                loss = float(distances[np.arange(len(data)), labels].sum())
                if best is None or loss < best[0]:
                    best = (loss, centers, labels, iteration)
                break
            previous = labels
            centers = np.stack([data[labels == index].mean(axis=0) for index in range(clusters)])
    if best is None:
        raise ImportCommandError("STATISTICS_CLUSTERING_DID_NOT_CONVERGE", "Кластеризация не сошлась. Измените число кластеров или seed.")
    loss, centers, labels, iteration = best
    order = sorted(range(clusters), key=lambda index: tuple(centers[index]))
    relabel = np.argsort(order)
    return {"labels": relabel[labels].tolist(), "centers": centers[order].tolist(),
            "inertia": loss, "iterations": iteration}


def pca_projection(data):
    mean = data.mean(axis=0)
    centered = data - mean
    left, singular, vectors = np.linalg.svd(centered, full_matrices=False)
    directions = vectors[:2]
    pivots = np.argmax(np.abs(directions), axis=1)
    signs = np.where(directions[np.arange(len(pivots)), pivots] < 0, -1, 1)
    scores = left[:, :2] * singular[:2] * signs
    loadings = directions * signs[:, None]
    if scores.shape[1] == 1:
        scores = np.column_stack((scores, np.zeros(len(data))))
        loadings = np.vstack((loadings, np.zeros(data.shape[1])))
    limits = np.vstack((scores.min(axis=0), scores.max(axis=0)))
    span = limits[1] - limits[0]
    # SVD may return tiny residuals for a mathematically zero second component.
    varies = span > 16 * np.finfo(np.float64).eps * singular[0]
    projected = np.where(varies, (scores - limits[0]) / np.where(varies, span, 1), 0.5)
    variance = singular ** 2
    total = variance.sum()
    fraction = (variance[:2] / total).tolist() if total else []
    return {"scores": scores.tolist(), "projection": projected.tolist(),
            "mean": mean.tolist(), "loadings": loadings.tolist(),
            "explained_variance_ratio": fraction + [0.0] * (2 - len(fraction))}
