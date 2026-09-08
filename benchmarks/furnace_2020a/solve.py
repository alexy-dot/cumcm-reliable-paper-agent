"""Answer all four questions conditionally on the selected calibrated model."""
import argparse
import csv
import sys
from pathlib import Path
import numpy as np
from scipy.optimize import differential_evolution, minimize, brentq
from model import LENGTH, temperature_curve, curve_metrics, margins

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill/cumcm-reliable-paper/scripts"))
from engine import read_json, write_json

BOUNDS = [(165, 185), (185, 205), (225, 245), (245, 265), (65, 100)]
SCALES = np.array([3, 3, 60, 60, 50, 50, 10, 10])


def optimize(parameters, area_cap=None, seeds=(2020, 917)):
    def metrics(x):
        return curve_metrics(x[:4], x[4], parameters, dx=.25)
    def objective(x):
        m = metrics(x)
        return m["area_rising_above_217"] / 1000 if area_cap is None else m["symmetry"]
    def constraints(x):
        m = metrics(x)
        # Tiny numerical interior reserve; final report retains unrounded margins.
        values = margins(m) / SCALES - 1e-5
        return values if area_cap is None else np.r_[values, (area_cap - m["area_rising_above_217"]) / 1000 - 1e-5]
    def penalized(x):
        return objective(x) + 10000 * np.sum(np.minimum(constraints(x), 0) ** 2)
    attempts = []
    candidates = []
    for seed in seeds:
        de = differential_evolution(penalized, BOUNDS, seed=seed, maxiter=110, popsize=8,
                                    tol=1e-7, polish=False, updating="immediate")
        for initial in (de.x, np.array([182, 203, 237, 254, 75.])):
            local = minimize(objective, initial, method="SLSQP", bounds=BOUNDS,
                             constraints={"type": "ineq", "fun": constraints},
                             options={"maxiter": 400, "ftol": 1e-11})
            violation = float(np.min(constraints(local.x)))
            attempts.append({"seed": seed, "success": bool(local.success), "minimum_scaled_margin": violation,
                             "objective": float(objective(local.x)), "settings_speed": local.x.tolist()})
            if violation >= -1e-7:
                candidates.append(local)
        print(f"optimization seed={seed} area_cap={area_cap} feasible_candidates={len(candidates)}", flush=True)
    if not candidates:
        raise RuntimeError("No feasible optimization candidate; do not report a nominal solution")
    best = min(candidates, key=lambda result: objective(result.x))
    final = curve_metrics(best.x[:4], best.x[4], parameters, dx=.05)
    return {"settings": best.x[:4].tolist(), "speed_cm_min": float(best.x[4]), "metrics": final,
            "constraint_margins": margins(final).tolist(), "attempts": attempts,
            "optimality": "best feasible point found by multi-start DE and SLSQP; no global certificate"}


def solve(run):
    calibration = read_json(run / "artifacts/calibration.json")
    parameters = calibration["models"]["zoned"]["parameters"]
    q1_settings = [173., 198., 230., 257.]
    t, temp = temperature_curve(q1_settings, 78, parameters, dx=.025)
    locations = {"zone3_mid": 111.25, "zone6_mid": 217.75, "zone7_mid": 253.25, "zone8_end": 304.}
    q1 = {"settings": q1_settings, "speed_cm_min": 78,
          "locations": {name: {"x_cm": x, "time_seconds": x / (78 / 60),
                                 "temperature_c": float(np.interp(x / (78 / 60), t, temp))} for name, x in locations.items()}}
    sample_times = np.arange(0, t[-1] + 1e-9, .5)
    with (run / "artifacts/result.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["时间(s)", "温度(摄氏度)"])
        writer.writerows(zip(sample_times, np.interp(sample_times, t, temp)))
    q1["sample_count"] = len(sample_times)
    q1["sampling_note"] = "0.5s grid from furnace entry; last fractional exit time omitted from CSV grid, retained in full curve"
    fixed = [182, 203, 237, 254]
    speed_grid = np.linspace(65, 100, 351)
    minimum = lambda v: float(np.min(margins(curve_metrics(fixed, v, parameters, dx=.05)) / SCALES))
    feasibility = np.array([minimum(v) for v in speed_grid])
    feasible = np.where(feasibility >= 0)[0]
    if not len(feasible):
        raise RuntimeError("Q2 no feasible speed found")
    last = int(feasible[-1])
    speed = 100. if last == len(speed_grid) - 1 else brentq(minimum, speed_grid[last], speed_grid[last + 1], xtol=1e-9)
    q2metrics = curve_metrics(fixed, speed, parameters, dx=.025)
    q2 = {"settings": fixed, "speed_cm_min": speed, "metrics": q2metrics,
          "constraint_margins": margins(q2metrics).tolist(), "scan_step_cm_min": .1,
          "search_note": "last feasible grid interval plus root refinement; narrow unsampled feasibility islands not certified absent"}
    preliminary = {"selected_model": "zoned", "parameters": parameters, "Q1": q1, "Q2": q2}
    write_json(run / "artifacts/solution.json", preliminary)
    print("Q1/Q2 completed", q1["locations"], q2["speed_cm_min"], flush=True)
    q3 = optimize(parameters)
    preliminary["Q3"] = q3
    write_json(run / "artifacts/solution.json", preliminary)
    cap = 1.05 * q3["metrics"]["area_rising_above_217"]
    q4 = optimize(parameters, area_cap=cap)
    q4["area_cap"] = cap
    q4["tradeoff_policy"] = "minimize normalized squared asymmetry with rising area <= 1.05 times Q3; a declared engineering preference"
    preliminary["Q4"] = q4
    write_json(run / "artifacts/solution.json", preliminary)
    print({key: {"speed": preliminary[key]["speed_cm_min"], "metrics": preliminary[key].get("metrics")} for key in ("Q2", "Q3", "Q4")}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    solve(parser.parse_args().run)
