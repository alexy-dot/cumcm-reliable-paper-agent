"""Frozen-candidate rolling-origin comparison after the original timed trial.

All historical data have been exposed to the analyst. This is a retrospective
forward-fit evaluation, never a new untouched test or a new blind-trial score.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from prepare import write

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skill/cumcm-reliable-paper/scripts"))
from conditional_supply import METHODS, fit_response, predict_response


def metrics(actual, predicted, orders, conversion):
    error = predicted - actual
    active = orders > 0
    total_error = (error / conversion[:, None]).sum(0)
    return {"active_cell_mae_raw": float(np.abs(error)[active].mean()),
            "active_cell_rmse_raw": float(np.sqrt(np.mean(error[active]**2))),
            "weekly_total_mae_product": float(np.abs(total_error).mean()),
            "weekly_total_rmse_product": float(np.sqrt(np.mean(total_error**2))),
            "weekly_bias_product": float(total_error.mean()),
            "weekly_total_mae_raw": float(np.abs(error.sum(0)).mean())}


def study(run, out):
    out.mkdir(parents=True, exist_ok=False)
    observation = run / "artifacts/observations.npz"
    facts_path = run / "artifacts/facts.json"
    facts = json.loads(facts_path.read_text())
    origins = [72, 96, 120, 144, 168, 192, 216]
    protocol = {"source_observation_sha256": hashlib.sha256(observation.read_bytes()).hexdigest(),
                "source_facts_sha256": hashlib.sha256(facts_path.read_bytes()).hexdigest(),
                "methods": list(METHODS), "outer_origins": origins, "horizon": 24,
                "inner_origins": "two preceding 24-week blocks, each fitted on its earlier history only",
                "selection_metric": "inner pooled weekly squared error of total product-equivalent supply",
                "recent_window": 48, "minimum_recent_active_weeks": 4,
                "saturation_order_quantile": .9, "order_bins": 3,
                "cold_start": "training-pooled volume ratio fallback, explicitly flagged",
                "local_order_support": "count fitted observations within ±20% of predicted order; diagnostic, not a validity certificate",
                "outer_update": "refit once at each origin, freeze model across the next 24 weeks",
                "information_scope": "historical future order quantities supplied as conditional prediction inputs; future supply excluded from fitting and family selection",
                "analyst_exposure": "all historical blocks previously inspected; retrospective study, not new unseen validation or randomized policy evidence"}
    # This protocol is persisted before producing any new candidate scores.
    write(out / "protocol.json", protocol)
    d = np.load(observation)
    o, s = d["orders"], d["supply"]
    a = np.array(facts["conversion"])
    folds = []; all_predictions = {m: [] for m in METHODS}; selected_predictions = []
    for origin in origins:
        inner = {}
        for method in METHODS:
            errors = []
            for cut in (origin - 48, origin - 24):
                fitted = fit_response(o[:, :cut], s[:, :cut], method)
                pred, _ = predict_response(fitted, o[:, cut:cut+24])
                errors.extend(((pred-s[:, cut:cut+24])/a[:, None]).sum(0).tolist())
            inner[method] = float(np.mean(np.array(errors)**2))
        selected = min(METHODS, key=lambda m: inner[m])
        row = {"training_weeks": origin, "validation_weeks": [origin+1, origin+24],
               "inner_scores": inner, "selected_before_outer_supply": selected, "methods": {}}
        for method in METHODS:
            fitted = fit_response(o[:, :origin], s[:, :origin], method)
            pred, flags = predict_response(fitted, o[:, origin:origin+24])
            all_predictions[method].append(pred)
            row["methods"][method] = metrics(s[:, origin:origin+24], pred, o[:, origin:origin+24], a)
            row["methods"][method]["outside_fitted_order_range"] = int(flags["outside_fitted_order_range"].sum())
            row["methods"][method]["cold_start"] = int(flags["cold_start"].sum())
            row["methods"][method]["no_nearby_orders"] = int(flags["no_nearby_orders"].sum())
            if method == selected:
                selected_predictions.append(pred)
        folds.append(row)
        print({"origin": origin, "selected": selected,
               "selected_weekly_mae": row["methods"][selected]["weekly_total_mae_product"],
               "baseline_weekly_mae": row["methods"]["ratio_all"]["weekly_total_mae_product"]}, flush=True)
    actual, orders = s[:, 72:240], o[:, 72:240]
    predictions = {m: np.concatenate(values, axis=1) for m, values in all_predictions.items()}
    predictions["nested_selected"] = np.concatenate(selected_predictions, axis=1)
    summary = {m: metrics(actual, p, orders, a) for m, p in predictions.items()}
    np.savez_compressed(out/"predictions.npz", actual=actual, orders=orders, conversion=a, **predictions)
    # Frozen trial plans are only checked for empirical order support, not reoptimized.
    old = json.loads((run/"artifacts/plans.json").read_text())
    support = {}
    for name, plan in old.items():
        q = np.asarray(plan["orders"])[0]
        info = []
        for i, value in enumerate(q):
            if value <= 1e-8: continue
            active = o[i] > 0
            near = active & (o[i] >= .8*value) & (o[i] <= 1.2*value)
            info.append({"supplier": facts["ids"][i], "planned_order": float(value),
                         "nearby_historical_orders": int(near.sum()),
                         "active_weeks": int(active.sum()),
                         "longest_active_run": max((len(group) for group in _runs(active)), default=0)})
        support[name] = {"active_suppliers": len(info), "without_nearby_orders": sum(r["nearby_historical_orders"] == 0 for r in info),
                         "suppliers": info, "scope": "nearby means within ±20% of proposed quantity; absence indicates limited local support, not proof of inability; activity depends on prior ordering"}
    report = {"protocol_sha256": hashlib.sha256((out/"protocol.json").read_bytes()).hexdigest(),
              "folds": folds, "pooled_metrics": summary, "old_plan_order_support": support,
              "predictions_sha256": hashlib.sha256((out/"predictions.npz").read_bytes()).hexdigest(),
              "source_code_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                     for path in [Path(__file__), ROOT/"skill/cumcm-reliable-paper/scripts/conditional_supply.py"]},
              "scope": protocol["analyst_exposure"], "old_timed_results_changed": False,
              "capacity_identified": False, "submission_ready": False}
    write(out/"report.json", report)
    print(summary, flush=True)


def _runs(mask):
    edges = np.diff(np.r_[False, mask, False].astype(int))
    return [range(a, b) for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))]


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("run", type=Path); p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(); study(args.run, args.output)
