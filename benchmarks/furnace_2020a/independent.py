"""Continuous ODE, root and quadrature checks; does not import the primary model."""
import argparse
import math
import sys
from pathlib import Path
import numpy as np
from scipy.integrate import solve_ivp, quad
from scipy.optimize import brentq, minimize_scalar

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill/cumcm-reliable-paper/scripts"))
from engine import read_json, write_json


def independently_solve(settings, speed, parameters):
    velocity = speed / 60
    length = 25 * 2 + 11 * 30.5 + 10 * 5
    starts = [25 + i * (30.5 + 5) for i in range(11)]
    transitions = [starts[index] - 2.5 for index in [5, 6, 7, 9]]
    cooling_start = starts[8] + 30.5

    def drive(t):
        position = t * velocity
        if position < 25 + parameters[5]:
            z = max(0., position / (25 + parameters[5]))
            return 25 + (settings[0] - 25) * z * z * (3 - 2 * z)
        if position > cooling_start:
            return 25 + (settings[3] - 25) * math.exp(-(position - cooling_start) / parameters[6])
        for group, index in enumerate([5, 6, 7]):
            left = starts[index] - 5
            if position < left:
                return settings[group]
            if position < starts[index]:
                return settings[group] + (settings[group + 1] - settings[group]) * (position - left) / 5
        return settings[3]

    def rate(t):
        position = t * velocity
        index = sum(position >= border for border in transitions)
        return 1 / parameters[index]

    def rhs(t, y):
        return [(drive(t) - y[0]) * rate(t)]

    # Restart at all forcing/rate breakpoints so the adaptive solver cannot skip a narrow gap.
    cuts = sorted(set([0, length / velocity, (25 + parameters[5]) / velocity, cooling_start / velocity]
                      + [x / velocity for x in transitions]
                      + [x / velocity for index in [5, 6, 7] for x in (starts[index] - 5, starts[index])]))
    pieces = []
    state = [25.]
    for begin, end in zip(cuts[:-1], cuts[1:]):
        result = solve_ivp(rhs, (begin, end), state, rtol=1e-10, atol=1e-10,
                           max_step=.25, dense_output=True)
        if not result.success:
            raise RuntimeError(result.message)
        pieces.append(result.sol)
        state = result.y[:, -1]

    def temperature(t):
        index = min(len(pieces) - 1, max(0, int(np.searchsorted(cuts, t, side="right")) - 1))
        return float(pieces[index](t)[0])

    grid = np.linspace(0, length / velocity, 2501)
    y = np.array([temperature(t) for t in grid])
    ip = int(np.argmax(y))
    peak = minimize_scalar(lambda t: -temperature(t), bounds=(grid[max(ip - 2, 0)], grid[min(ip + 2, len(grid) - 1)]),
                           method="bounded", options={"xatol": 1e-10})
    peak_time, peak_value = float(peak.x), float(-peak.fun)

    def cross(level, up):
        indices = np.where((y[:-1] <= level) & (y[1:] > level) if up else (y[:-1] > level) & (y[1:] <= level))[0]
        if not len(indices):
            raise RuntimeError(f"missing crossing at {level}")
        index = indices[0] if up else indices[-1]
        return float(brentq(lambda t: temperature(t) - level, grid[index], grid[index + 1], xtol=1e-10))

    up, down = cross(217, True), cross(217, False)
    area = quad(lambda t: temperature(t) - 217, up, peak_time, epsabs=1e-7,
                points=[point for point in cuts if up < point < peak_time])[0]
    extra = [point + offset for point in cuts[1:-1] for offset in (-1e-7, 1e-7)]
    sample = sorted(set(grid.tolist() + extra))
    slopes = [(drive(t) - temperature(t)) * rate(t) for t in sample]
    duration = max(peak_time - up, down - peak_time)
    def positive(t):
        return max(temperature(t) - 217, 0.) if 0 <= t <= length / velocity else 0.
    symmetry = quad(lambda u: (positive(peak_time - u) - positive(peak_time + u)) ** 2, 0, duration,
                    epsabs=1e-5, points=[min(peak_time - up, down - peak_time)])[0] / (duration * (peak_value - 217) ** 2)
    metrics = {"peak": peak_value, "peak_time": peak_time, "max_rise": max(slopes), "max_cooling": -min(slopes),
               "soak_150_190": cross(190, True) - cross(150, True), "time_above_217": down - up,
               "area_rising_above_217": float(area), "symmetry": float(symmetry)}
    return temperature, metrics


def verify(run):
    primary = read_json(run / "artifacts/solution.json")
    parameters = primary["parameters"]
    comparisons = []
    independent = {}
    for question in ["Q1", "Q2", "Q3", "Q4"]:
        result = primary[question]
        temperature, metrics = independently_solve(result["settings"], result["speed_cm_min"], parameters)
        independent[question] = {"metrics": metrics}
        if question == "Q1":
            independent[question]["temperatures"] = []
            for name, point in result["locations"].items():
                value = temperature(point["time_seconds"])
                independent[question]["temperatures"].append(value)
                error = abs(value - point["temperature_c"])
                comparisons.append({"question": question, "metric": name, "error": error, "tolerance": .005, "passed": error < .005})
        else:
            tolerances = {"peak": .005, "peak_time": .05, "max_rise": .005, "max_cooling": .005,
                          "soak_150_190": .01, "time_above_217": .01, "area_rising_above_217": .1, "symmetry": .0001}
            for key, tolerance in tolerances.items():
                error = abs(result["metrics"][key] - metrics[key])
                comparisons.append({"question": question, "metric": key, "error": error, "tolerance": tolerance, "passed": error <= tolerance})
        print(f"independently integrated {question}", flush=True)
    fixed = primary["Q2"]["settings"]
    speed = brentq(lambda value: independently_solve(fixed, value, parameters)[1]["peak"] - 240,
                   65, 100, xtol=1e-7)
    independent["Q2"]["speed_cm_min"] = float(speed)
    comparisons.append({"question": "Q2", "metric": "max_speed_root", "error": abs(speed - primary["Q2"]["speed_cm_min"]),
                        "tolerance": .002, "passed": abs(speed - primary["Q2"]["speed_cm_min"]) < .002})
    write_json(run / "artifacts/independent_solution.json", independent)
    report = {"method": "separate scalar forcing + segmented solve_ivp + root solving + adaptive quadrature",
              "passed": all(row["passed"] for row in comparisons), "comparisons": comparisons,
              "scope": "numerical implementation equivalence for the selected model; not independent physical experiments or global optimality"}
    write_json(run / "artifacts/independent_comparison.json", report)
    print({"passed": report["passed"], "failed": [row for row in comparisons if not row["passed"]]}, flush=True)
    return report["passed"]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("run", type=Path)
    raise SystemExit(0 if verify(p.parse_args().run) else 1)
