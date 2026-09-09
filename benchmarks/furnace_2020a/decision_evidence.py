"""Decision sensitivity: epsilon constraints, alternative models and joint scenarios.

Scenario violation fractions are design diagnostics, NOT probabilities or fitted
confidence levels. The epsilon sweep contains best-found candidates, not a
certified global Pareto frontier.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from scipy.stats import qmc
from model import curve_metrics, margins
from solve import optimize
from independent import independently_solve

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill/cumcm-reliable-paper/scripts"))
from engine import read_json, write_json, sha256_file


def is_candidate_feasible(candidate, cap, tolerance=1e-4):
    """Apply process, control and epsilon constraints to one evaluated candidate."""
    control = np.r_[candidate["settings"], candidate["speed_cm_min"]]
    bounds = np.array([[165,185],[185,205],[225,245],[245,265],[65,100]])
    metric = candidate["metrics"]
    return bool(np.all(np.isfinite(control)) and np.all(control >= bounds[:,0]-1e-8)
                and np.all(control <= bounds[:,1]+1e-8)
                and all(np.isfinite(value) for value in margins(metric))
                and np.min(margins(metric)) >= -tolerance
                and np.isfinite(metric["symmetry"]) and metric["symmetry"] >= 0
                and 0 < metric["area_rising_above_217"] <= cap+tolerance)


def select_incumbent(candidates, cap):
    valid = [row for row in candidates if is_candidate_feasible(row,cap)]
    if not valid:
        raise ValueError("no candidate satisfies the process and area constraints")
    return min(valid, key=lambda row: row["metrics"]["symmetry"])


def joint_parameters(parameters, points):
    """Bounded deterministic design: +/-2% rates/lengths, entry width down to -2%."""
    base = np.asarray(parameters, dtype=float)
    unit = np.asarray(points, dtype=float)
    if base.shape != (7,) or unit.ndim != 2 or unit.shape[1] != 7 or np.any(unit < 0) or np.any(unit > 1):
        raise ValueError("expected seven parameters and points in [0,1]^7")
    factors = .98+.04*unit
    factors[:,5] = .98+.02*unit[:,5]  # The fitted width is already at its upper bound.
    return base[None,:]*factors


def evaluate(run):
    solution = read_json(run / "artifacts/solution.json")
    calibration = read_json(run / "artifacts/calibration.json")
    sensitivity = read_json(run / "artifacts/sensitivity.json")
    parameters = solution["parameters"]
    area0 = solution["Q3"]["metrics"]["area_rising_above_217"]
    report = {"schema_version":"1.0", "source_sha256": {
        name:sha256_file(run/"artifacts"/name) for name in ("solution.json","calibration.json","sensitivity.json")},
        "interpretation": "Model-conditional numerical diagnostics; no new physical data, global optimality certificate or calibrated failure probabilities.",
        "status":"RUNNING"}
    output = run / "artifacts/decision_evidence.json"
    candidates = [solution["Q3"]]
    rows = []
    for fraction in [0.,.001,.0025,.005,.01,.02,.05,.10]:
        cap = area0*(1+fraction)
        new = None
        # At exactly zero slack, the stored Q3 point supplies a feasible incumbent;
        # the epsilon optimizer uses an interior reserve and cannot enter that face.
        if fraction > 0:
            new = optimize(parameters,area_cap=cap,seeds=(2020,917))
            candidates.append(new)
        selected = select_incumbent(candidates,cap)
        _, continuous = independently_solve(selected["settings"],selected["speed_cm_min"],parameters)
        checked = {**selected,"metrics":continuous}
        agreement = (abs(continuous["area_rising_above_217"]-selected["metrics"]["area_rising_above_217"]) < .1
                     and abs(continuous["symmetry"]-selected["metrics"]["symmetry"]) < 1e-4)
        row = {"allowed_area_increase_pct":100*fraction, "cap":cap,
               "actual_area_increase_pct":100*(selected["metrics"]["area_rising_above_217"]/area0-1),
               "settings":selected["settings"],"speed_cm_min":selected["speed_cm_min"],
               "metrics":selected["metrics"],"independent_metrics":continuous,
               "continuous_feasible":is_candidate_feasible(checked,cap), "numerical_agreement":bool(agreement),
               "selected_previous_incumbent":new is not None and selected is not new,
               "search_attempts":new["attempts"] if new else [],
               "zero_slack_note":"Q3 incumbent only; not optimized for symmetry at exactly zero area slack" if fraction==0 else None}
        rows.append(row)
        report["tradeoff"] = rows
        write_json(output,report)
        print(f"cap +{100*fraction:g}%: area={row['metrics']['area_rising_above_217']:.5f}, J={row['metrics']['symmetry']:.6f}, continuous_feasible={row['continuous_feasible']}",flush=True)
    # Compare fixed decisions across ALL fitted alternatives that have a fully
    # implemented metric evaluator. Do not average their outputs into a new model.
    variants = []
    for name in ["mixing","radiative","two_node","smooth_two_node","zoned"]:
        fitted = calibration["models"][name]
        point = solution["Q2"]
        metric = curve_metrics(point["settings"],point["speed_cm_min"],fitted["parameters"],dx=.05)
        grid = []
        for speed in np.linspace(65,100,351):
            m = curve_metrics(point["settings"],speed,fitted["parameters"],dx=.1)
            if np.all(np.isfinite(margins(m))) and np.min(margins(m)) >= -1e-4:
                grid.append(float(speed))
        variants.append({"model":name,"fit_rmse_c":fitted["rmse"],"selection_block_rmse_c":fitted["held_block_rmse"],
                         "fixed_q2_peak_c":metric["peak"],"fixed_q2_margins":margins(metric).tolist(),
                         "fixed_q2_feasible":bool(np.min(margins(metric))>=-1e-4),
                         "largest_feasible_grid_speed_cm_min":max(grid) if grid else None,
                         "speed_grid_step":.1})
    report["alternative_models"] = variants
    points = qmc.Sobol(d=7,scramble=True,seed=20260909).random_base2(m=8)
    scenario_parameters = joint_parameters(parameters,points)
    cases = []
    for name in ("Q2","Q3","Q4"):
        for kind in ("nominal_optimum","oat_interior_suggestion"):
            point = solution[name] if kind == "nominal_optimum" else sensitivity["questions"][name]["interior_suggestion"]
            if point is None:
                continue
            outcomes = [curve_metrics(point["settings"],point["speed_cm_min"],p,dx=.1) for p in scenario_parameters]
            slacks = np.array([margins(m) for m in outcomes])
            if not np.all(np.isfinite(slacks)):
                raise ValueError("nonfinite joint scenario results")
            cases.append({"question":name,"kind":kind,"speed_cm_min":point["speed_cm_min"],
                          "scenario_count":len(outcomes),"process_violations":int(np.sum(np.any(slacks < -1e-4,axis=1))),
                          "minimum_margins":np.min(slacks,axis=0).tolist(),
                          "peak_range_c":[min(m["peak"] for m in outcomes),max(m["peak"] for m in outcomes)],
                          "area_range":[min(m["area_rising_above_217"] for m in outcomes),max(m["area_rising_above_217"] for m in outcomes)],
                          "q4_area_cap_violations":sum(m["area_rising_above_217"]>solution["Q4"]["area_cap"]+1e-4 for m in outcomes) if name=="Q4" else None})
    report["joint_scenarios"]={"design":"scrambled Sobol, 256 points, seed 20260909",
                               "scope":"all seven parameters vary together; six +/-2%, entry width -2% to nominal; selected box, not inferred uncertainty distribution",
                               "parameters":scenario_parameters.tolist(), "cases":cases}
    report["passed"] = all(row["continuous_feasible"] and row["numerical_agreement"] for row in rows)
    report["status"] = "COMPLETE"
    report["monotone_best_found_envelope"] = all(b["metrics"]["symmetry"] <= a["metrics"]["symmetry"]+1e-10 for a,b in zip(rows,rows[1:]))
    write_json(output,report)
    print({"passed":report["passed"],"variants":variants,"joint_cases":cases},flush=True)
    if not report["passed"]:
        raise RuntimeError("tradeoff candidate failed independent validation")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run",type=Path)
    evaluate(parser.parse_args().run)
