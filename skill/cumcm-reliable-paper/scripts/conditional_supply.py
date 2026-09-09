"""Training-only conditional supply responses and order-range diagnostics.

These models predict supply at specified orders. They do not identify available
capacity, counterfactual order effects, or joint future delivery reliability.
NumPy is an optional dependency. Rows are suppliers; columns are ordered weeks.
"""
import numpy as np


METHODS = ("identity", "ratio_all", "ratio_48", "saturation_all",
           "saturation_48", "bins_all", "bins_48")


def _matrix(value, name):
    a = np.asarray(value, dtype=float)
    if a.ndim != 2 or a.shape[0] == 0 or a.shape[1] == 0 or not np.isfinite(a).all() or (a < 0).any():
        raise ValueError(f"{name} must be a nonempty finite nonnegative supplier-by-week matrix")
    return a


def fit_response(orders, supply, method="ratio_all"):
    o, s = _matrix(orders, "orders"), _matrix(supply, "supply")
    if o.shape != s.shape or ((o == 0) & (s > 0)).any():
        raise ValueError("matching history and zero supply when no order are required")
    if method not in METHODS:
        raise ValueError("unknown response method")
    pooled_rate = float(s.sum() / o.sum()) if o.sum() > 0 else 0.
    rows = []
    for original_o, original_s in zip(o, s):
        full_positive = original_o > 0
        recent = method.endswith("_48")
        x, y = (original_o[-48:], original_s[-48:]) if recent else (original_o, original_s)
        fallback = bool(recent and (x > 0).sum() < 4)
        if fallback:
            x, y = original_o, original_s
        positive = x > 0
        x, y = x[positive], y[positive]
        support = {"historical_active_weeks": int(full_positive.sum()),
                   "fitted_active_weeks": len(x), "recent_fallback_to_all": fallback,
                   "order_min": float(x.min()) if len(x) else None,
                   "order_max": float(x.max()) if len(x) else None,
                   "sorted_fitted_orders": np.sort(x).tolist()}
        parameters = {"rate": float(y.sum() / x.sum()) if len(x) else pooled_rate}
        if method.startswith("saturation") and len(x):
            cap = float(np.quantile(x, .9))
            clipped = np.minimum(x, cap)
            parameters = {"cap": cap, "rate": float(y @ clipped / (clipped @ clipped))}
        if method.startswith("bins") and len(x):
            cuts = np.unique(np.quantile(x, [1/3, 2/3]))
            bins = np.searchsorted(cuts, x, side="right")
            means = [float(y[bins == j].mean()) if (bins == j).any() else float(y.mean())
                     for j in range(len(cuts) + 1)]
            parameters = {"cuts": cuts.tolist(), "means": means}
        rows.append({"support": support, "parameters": parameters})
    return {"method": method, "history_weeks": o.shape[1], "rows": rows,
            "scope": "conditional response at requested order quantities; not capacity or causal policy identification"}


def predict_response(model, orders, *, local_tolerance=.2):
    """Predict and flag extrapolation, cold starts and local order gaps.

    Local support counts observations within ±local_tolerance of the order.
    Missing nearby points is a diagnostic, not a rejection of interpolation.
    """
    q = _matrix(orders, "prediction orders")
    if not np.isfinite(local_tolerance) or not 0 <= local_tolerance < 1:
        raise ValueError("local_tolerance must be finite and in [0,1)")
    if len(model["rows"]) != len(q):
        raise ValueError("prediction suppliers must match fitted suppliers in order")
    result = np.zeros_like(q)
    outside = np.zeros(q.shape, dtype=bool)
    cold = np.zeros(q.shape, dtype=bool)
    nearby = np.zeros(q.shape, dtype=int)
    for i, (row, x) in enumerate(zip(model["rows"], q)):
        active = x > 0
        p, support = row["parameters"], row["support"]
        if support["order_min"] is None:
            cold[i] = active
        else:
            outside[i] = active & ((x < support["order_min"]) | (x > support["order_max"]))
            levels = support["sorted_fitted_orders"]
            nearby[i, active] = (np.searchsorted(levels, (1+local_tolerance)*x[active], side="right")
                                 - np.searchsorted(levels, (1-local_tolerance)*x[active], side="left"))
        if model["method"] == "identity":
            result[i] = x
        elif "cuts" in p:
            index = np.searchsorted(p["cuts"], x, side="right")
            result[i, active] = np.asarray(p["means"])[index[active]]
        elif "cap" in p:
            result[i] = p["rate"] * np.minimum(x, p["cap"])
        else:
            result[i] = p["rate"] * x
    return result, {"outside_fitted_order_range": outside, "cold_start": cold,
                    "nearby_order_count": nearby, "no_nearby_orders": (q > 0) & (nearby == 0)}
