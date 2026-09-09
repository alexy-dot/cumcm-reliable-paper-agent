"""Fixed-budget optimizer ablation on the already calibrated historical furnace task.

The protocol is written before any search. This is retrospective method assessment,
not a blind trial; the Q4 area cap comes from the existing nominal solution.
"""
import argparse
import platform
import sys
from pathlib import Path
from time import perf_counter

import numpy as np
import scipy
from scipy.optimize import differential_evolution, minimize

from model import curve_metrics, margins
from independent import independently_solve
from solve import BOUNDS, SCALES

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill/cumcm-reliable-paper/scripts"))
from engine import read_json, write_json, sha256_file

SEEDS = [11, 29, 47, 71, 101, 131]
BUDGET = 2400
METHODS = ["multistart_slsqp", "de", "de_slsqp"]


class BudgetExhausted(Exception):
    pass


class Evaluator:
    """Count distinct physical-model evaluations, sharing objective/constraint calls."""

    def __init__(self, parameters, cap, budget, metric_function=curve_metrics):
        self.parameters, self.cap, self.limit = parameters, cap, budget
        self.metric_function = metric_function
        self.cache = {}
        self.best = None
        self.best_penalty = None
        self.history = []

    def evaluate(self, x):
        x = np.asarray(x, dtype=float)
        if not np.all(np.isfinite(x)):
            raise ValueError("nonfinite search coordinate")
        if np.any(x < np.array(BOUNDS)[:, 0] - 1e-8) or np.any(x > np.array(BOUNDS)[:, 1] + 1e-8):
            raise ValueError("search coordinate outside decision bounds")
        key = tuple(x.tolist())
        if key in self.cache:
            return self.cache[key]
        if len(self.cache) >= self.limit:
            raise BudgetExhausted
        m = self.metric_function(x[:4], x[4], self.parameters, dx=.25)
        constraints = margins(m) / SCALES - 1e-5
        if self.cap is not None:
            constraints = np.r_[constraints, (self.cap - m["area_rising_above_217"]) / 1000 - 1e-5]
        objective = m["area_rising_above_217"] / 1000 if self.cap is None else m["symmetry"]
        if not np.isfinite(objective) or not np.all(np.isfinite(constraints)):
            raise ValueError("nonfinite objective or constraints")
        penalty = objective + 10000 * float(np.sum(np.minimum(constraints, 0) ** 2))
        row = {"x": x.tolist(), "objective": float(objective), "penalized": penalty,
               "metrics": m, "constraints": constraints.tolist()}
        self.cache[key] = row
        if self.best_penalty is None or penalty < self.best_penalty["penalized"]:
            self.best_penalty = row
        if min(constraints) >= -1e-7 and (self.best is None or objective < self.best["objective"]):
            self.best = row
            self.history.append({"evaluations": len(self.cache), "objective": float(objective)})
        return row

    def objective(self, x):
        return self.evaluate(x)["objective"]

    def constraints(self, x):
        return np.asarray(self.evaluate(x)["constraints"])

    def penalized(self, x):
        return self.evaluate(x)["penalized"]


def initial_population(seed):
    bounds = np.asarray(BOUNDS)
    population = np.random.default_rng(seed).uniform(bounds[:, 0], bounds[:, 1], (40, 5))
    population[0] = [182, 203, 237, 254, 75]
    population[1] = np.mean(bounds, axis=1)
    return population


def check_candidate(x, m, cap):
    """Physical-unit margins reconstructed without calling the main margin function."""
    physical = [3-m["max_rise"], 3-m["max_cooling"], m["soak_150_190"]-60,
                120-m["soak_150_190"], m["time_above_217"]-40, 90-m["time_above_217"],
                m["peak"]-240, 250-m["peak"]]
    # Numerical tolerances from the pre-existing independent comparison, not uncertainty reserves.
    tolerance = [.005, .005, .01, .01, .01, .01, .005, .005]
    if cap is not None:
        physical.append(cap-m["area_rising_above_217"])
        tolerance.append(.1)
    bounds_ok = all(lo-1e-8 <= value <= hi+1e-8 for value, (lo, hi) in zip(x, BOUNDS))
    finite = bool(np.all(np.isfinite(physical)))
    return {"margins": physical, "tolerances": tolerance,
            "strict_feasible": bool(finite and bounds_ok and min(physical) >= 0),
            "feasible_with_numerical_tolerance": bool(finite and bounds_ok and all(v >= -t for v, t in zip(physical, tolerance)))}


def trial(parameters, cap, seed, method, budget=BUDGET):
    evaluator = Evaluator(parameters, cap, budget)
    population = initial_population(seed)
    started = perf_counter()
    terminations = []
    if method in {"de", "de_slsqp"}:
        evaluator.limit = budget if method == "de" else budget // 2
        try:
            result = differential_evolution(evaluator.penalized, BOUNDS, seed=seed, init=population,
                                            maxiter=100000, tol=0, atol=0, polish=False, updating="immediate")
            terminations.append({"phase": "de", "message": str(result.message)})
        except BudgetExhausted:
            terminations.append({"phase": "de", "message": "evaluation budget exhausted"})
        evaluator.limit = budget
    if method in {"multistart_slsqp", "de_slsqp"}:
        starts = population.tolist()
        if method == "de_slsqp" and evaluator.best_penalty is not None:
            starts.insert(0, evaluator.best_penalty["x"])
        for start in starts:
            try:
                result = minimize(evaluator.objective, start, method="SLSQP", bounds=BOUNDS,
                                  constraints={"type": "ineq", "fun": evaluator.constraints},
                                  options={"maxiter": 400, "ftol": 1e-11})
                terminations.append({"phase": "slsqp", "success": bool(result.success),
                                     "message": str(result.message)})
            except BudgetExhausted:
                terminations.append({"phase": "slsqp", "message": "evaluation budget exhausted"})
                break
    elapsed = perf_counter() - started
    best = evaluator.best
    output = {"method": method, "seed": seed, "evaluations": len(evaluator.cache),
              "search_seconds": elapsed, "terminations": terminations,
              "incumbent_history": evaluator.history, "selected": best,
              "independent": None}
    if best is not None:
        # Select exactly once using search evidence; no retuning or reselection after this check.
        begin = perf_counter()
        x = best["x"]
        _, independent = independently_solve(x[:4], x[4], parameters)
        output["independent"] = {"metrics": independent, **check_candidate(x, independent, cap),
                                 "seconds": perf_counter()-begin}
    return output


def summarize(rows, question):
    metric = "area_rising_above_217" if question == "Q3" else "symmetry"
    summary = []
    for method in METHODS:
        group = [r for r in rows if r["question"] == question and r["method"] == method]
        eligible = [r["independent"]["metrics"][metric] for r in group
                    if r["independent"] and r["independent"]["feasible_with_numerical_tolerance"]]
        strict = sum(bool(r["independent"] and r["independent"]["strict_feasible"]) for r in group)
        summary.append({"method": method, "runs": len(group), "feasible_runs": len(eligible),
                        "strict_feasible_runs": strict,
                        "objective_best": min(eligible) if eligible else None,
                        "objective_median": float(np.median(eligible)) if eligible else None,
                        "objective_worst": max(eligible) if eligible else None,
                        "median_evaluations": float(np.median([r["evaluations"] for r in group])),
                        "median_search_seconds": float(np.median([r["search_seconds"] for r in group]))})
    return summary


def compare(run, output):
    output.mkdir(parents=True, exist_ok=False)
    solution_path = run / "artifacts/solution.json"
    solution = read_json(solution_path)
    protocol = {"seeds": SEEDS, "budget_per_run": BUDGET, "methods": METHODS,
                "bounds": BOUNDS, "search_dx_cm": .25, "hybrid_de_budget": BUDGET//2,
                "population": "40 uniform points per seed; point 0 fixed nominal baseline, point 1 bounds midpoint; shared by methods",
                "cost_unit": "distinct temperature-model evaluations, exact-coordinate cache per run; independent verification excluded and timed separately",
                "selection": "best search-feasible point among all evaluated coordinates, including finite-difference probes; independent check only after selection, no reselection",
                "termination": "shared maximum budget; SLSQP ftol 1e-11/maxiter 400 per start; DE tol/atol zero, no polish",
                "feasibility": "report both strict physical margins and numerical-tolerance acceptance; tolerances .005 degC or degC/s, .01 s, .1 degC*s; not process reserves",
                "q4_area_cap": solution["Q4"]["area_cap"], "solution_sha256": sha256_file(solution_path),
                "script_sha256": {name: sha256_file(Path(__file__).with_name(name)) for name in
                                  ("optimizer_comparison.py", "model.py", "solve.py", "independent.py")},
                "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
                "scope": "retrospective ablation on one fitted model, six seeds, one budget and one 50/50 hybrid allocation; not statistical superiority or global optimality"}
    write_json(output / "protocol.json", protocol)
    rows = []
    for question, cap in [("Q3", None), ("Q4", solution["Q4"]["area_cap"])]:
        for index, seed in enumerate(SEEDS):
            # Rotate order to reduce systematic warm-up or background-load bias in wall time.
            order = METHODS[index % 3:] + METHODS[:index % 3]
            for method in order:
                row = trial(solution["parameters"], cap, seed, method)
                row["question"] = question
                rows.append(row)
                write_json(output / "trials.json", rows)
                print(question, method, seed, row["evaluations"],
                      row["independent"]["feasible_with_numerical_tolerance"] if row["independent"] else False, flush=True)
    report = {"protocol": protocol, "protocol_sha256": sha256_file(output / "protocol.json"),
              "trials_sha256": sha256_file(output / "trials.json"),
              "summary": {question: summarize(rows, question) for question in ("Q3", "Q4")},
              "completed": len(rows) == 2*len(SEEDS)*len(METHODS) and all(r["evaluations"] <= BUDGET for r in rows)}
    write_json(output / "report.json", report)
    print(report["summary"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, help="new directory; default RUN/artifacts/optimizer_comparison")
    args = parser.parse_args()
    compare(args.run, args.output or args.run / "artifacts/optimizer_comparison")
