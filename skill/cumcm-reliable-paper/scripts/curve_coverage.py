"""Arc-length coverage of ordered polylines, with explicit discretization bounds.

Optional NumPy/SciPy helper. Coordinates must share a frame and length unit.
It measures geometric support, not feature identity or registration correctness.
"""
from math import ceil

import numpy as np
from scipy.spatial import cKDTree


def _curve(points):
    p = np.asarray(points, dtype=float)
    if p.ndim != 2 or p.shape[1] not in (2, 3) or len(p) < 2 or not np.isfinite(p).all():
        raise ValueError("finite ordered 2D or 3D points required")
    p = p[np.r_[True, np.linalg.norm(np.diff(p, axis=0), axis=1) > 0]]
    if len(p) < 2:
        raise ValueError("curve must have positive length")
    s = np.r_[0., np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    return p, s


def directed_coverage(source, target, *, tolerance, step, max_points=2_000_000):
    """Bound source arc length within tolerance of the target polyline.

    Target subdivision retains every original vertex and limits segment length
    to step. Source intervals have equal arc length <=step and are queried at
    their midpoints. Distance-to-set is 1-Lipschitz, giving conservative lower
    and upper covered-length fractions and maximum-distance bounds. Ambiguous
    intervals require finer step, not an automatic pass. No points are trimmed.
    """
    if not np.isfinite(tolerance) or tolerance < 0 or not np.isfinite(step) or step <= 0:
        raise ValueError("finite tolerance>=0 and step>0 required")
    if type(max_points) is not int or max_points < 2:
        raise ValueError("max_points must be an integer >=2")
    a, sa = _curve(source)
    b, sb = _curve(target)
    if a.shape[1] != b.shape[1]:
        raise ValueError("curve dimensions differ")
    target_lengths = np.diff(sb)
    subdivisions_float = np.ceil(target_lengths / step)
    count_float = np.ceil(sa[-1] / step)
    if not np.isfinite(subdivisions_float).all() or not np.isfinite(count_float) or subdivisions_float.sum() + 1 > max_points or count_float > max_points:
        raise ValueError("requested resolution exceeds max_points; choose a coarser step")
    subdivisions = subdivisions_float.astype(int)
    target_count = int(subdivisions.sum()) + 1
    count = int(count_float)
    # Most measured polylines are already finer than step.
    if np.all(subdivisions == 1):
        dense = b
    else:
        dense = np.concatenate([
            b[i] + np.arange(n)[:, None] / n * (b[i + 1] - b[i])
            for i, n in enumerate(subdivisions)
        ] + [b[-1:]], axis=0)
    target_radius = float(np.max(target_lengths / subdivisions) / 2)
    interval = float(sa[-1] / count)
    mid_s = (np.arange(count) + .5) * interval
    mid = np.column_stack([np.interp(mid_s, sa, a[:, j]) for j in range(a.shape[1])])
    distances = cKDTree(dense).query(mid)[0]
    point_lower = np.maximum(0., distances - target_radius)
    interval_lower = np.maximum(0., point_lower - interval / 2)
    interval_upper = distances + interval / 2
    covered = interval_upper <= tolerance
    uncovered = interval_lower > tolerance
    edges = np.diff(np.r_[False, uncovered, False].astype(int))
    spans = [[float(i * interval), float(j * interval)]
             for i, j in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))]
    keep = max(1, ceil(.2 * count))
    return {
        "source_length": float(sa[-1]),
        "target_length": float(sb[-1]),
        "tolerance": float(tolerance), "source_interval": interval,
        "target_sampling_radius_bound": target_radius,
        "source_intervals": count, "target_points": target_count,
        "covered_fraction_lower": float(covered.mean()),
        "covered_fraction_upper": float(1 - uncovered.mean()),
        "unresolved_fraction": float((~(covered | uncovered)).mean()),
        "maximum_distance_lower": float(point_lower.max()),
        "maximum_distance_upper": float(interval_upper.max()),
        "definitely_uncovered_arc_intervals": spans,
        "midpoint_sample_distance_quantiles": dict(zip(
            ("q50", "q90", "q95", "q99", "max"),
            map(float, np.quantile(distances, [.5, .9, .95, .99, 1])))),
        "best_20_percent_midpoint_rms": float(np.sqrt(np.mean(np.sort(distances)[:keep] ** 2))),
        "scope": "directed geometric support of supplied polylines; bounds include sampling error but not measurement uncertainty or wrong correspondences",
    }


def compare_curves(first, second, **kwargs):
    """Both directions; a partial scan and a full contour need different scopes."""
    return {"first_to_second": directed_coverage(first, second, **kwargs),
            "second_to_first": directed_coverage(second, first, **kwargs)}
