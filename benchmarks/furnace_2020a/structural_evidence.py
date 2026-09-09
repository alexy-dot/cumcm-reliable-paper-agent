"""Check model-derived comparison and superposition identities on actual solutions.

These checks support explicit conditional proofs in the paper; they are not
additional physical experiments or a global certificate for Q3/Q4.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

from model import LENGTH, temperature_curve, curve_metrics, margins
from independent import independently_solve

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill/cumcm-reliable-paper/scripts"))
from engine import read_json, write_json


def affine_basis(speed, parameters, dx=.05):
    """Four unit responses; holds only for frozen zoned parameters and speed."""
    time, ambient = temperature_curve([25.] * 4, speed, parameters, dx=dx)
    basis = []
    for index in range(4):
        settings = np.full(4, 25.)
        settings[index] = 26.
        _, response = temperature_curve(settings, speed, parameters, dx=dx)
        basis.append(response - ambient)
    return time * speed / 60, ambient, np.array(basis)


def check_speed_identity(settings, parameters, v1=70., v2=90.):
    """Verify the positive-filter identity with separate continuous ODE outputs."""
    if not 0 < v1 < v2:
        raise ValueError("require 0 < v1 < v2")
    first, first_metrics = independently_solve(settings, v1, parameters)
    second, second_metrics = independently_solve(settings, v2, parameters)
    def y1(x):
        return first(float(x) * 60 / v1) - 25
    def rhs(x, state):
        index = int(np.searchsorted([200., 235.5, 271., 342.], x, side="right"))
        return [(60 / v2) / parameters[index] * (y1(x) - state[0])]
    coordinates = np.linspace(0, LENGTH, 1001)
    # Segment the integral filter at the same rate discontinuities.
    pieces = []
    state = [0.]
    cuts = [0., 200., 235.5, 271., 342., LENGTH]
    for left, right in zip(cuts[:-1], cuts[1:]):
        ode = solve_ivp(rhs, (left, right), state, rtol=1e-9, atol=1e-9,
                        max_step=.2, dense_output=True)
        if not ode.success:
            raise RuntimeError(ode.message)
        pieces.append(ode.sol)
        state = ode.y[:, -1]
    reconstructed, actual = [], []
    for x in coordinates:
        index = min(len(pieces) - 1, max(0, int(np.searchsorted(cuts, x, side="right")) - 1))
        smooth = float(pieces[index](x)[0])
        reconstructed.append((v1 / v2) * y1(x) + (1 - v1 / v2) * smooth + 25)
        actual.append(second(float(x) * 60 / v2))
    error = float(np.max(np.abs(np.array(reconstructed) - actual)))
    return {"speeds_cm_min": [v1, v2], "peak_temperatures_c": [first_metrics["peak"], second_metrics["peak"]],
            "max_identity_error_c": error, "tolerance_c": 1e-5,
            "passed": error <= 1e-5 and first_metrics["peak"] > second_metrics["peak"]}


def evaluate(run):
    solution = read_json(run / "artifacts/solution.json")
    parameters = solution["parameters"]
    q2 = solution["Q2"]
    identity = check_speed_identity(q2["settings"], parameters)
    speed_sweep = [{"speed_cm_min": float(speed), "peak_c": curve_metrics(q2["settings"], speed, parameters, dx=.05)["peak"]}
                   for speed in np.linspace(65, 100, 36)]
    q3 = solution["Q3"]
    speed = q3["speed_cm_min"]
    x, ambient, basis = affine_basis(speed, parameters)
    predicted = ambient + (np.array(q3["settings"]) - 25) @ basis
    _, direct = temperature_curve(q3["settings"], speed, parameters, dx=.05)
    superposition_error = float(np.max(np.abs(predicted - direct)))
    entry = 273.5  # Beginning of zone 8: all earlier heater controls leave the forcing.
    entry_weights = np.array([np.interp(entry, x, response) for response in basis])
    # Preserve T8 and entry temperature by trading off T1 and T6.
    direction = np.array([1., -entry_weights[0] / entry_weights[1], 0., 0.])
    alternatives = []
    for delta in [-.25, 0., .25]:
        settings = np.array(q3["settings"]) + delta * direction
        _, curve = temperature_curve(settings, speed, parameters, dx=.05)
        metrics = curve_metrics(settings, speed, parameters, dx=.05)
        limits = np.array([[165,185], [185,205], [225,245], [245,265]])
        feasible = bool(np.all(settings >= limits[:,0]) and np.all(settings <= limits[:,1]) and np.min(margins(metrics)) >= -1e-4)
        alternatives.append({"delta_t1_c": delta, "settings": settings.tolist(),
                             "entry_temperature_c": float(np.interp(entry,x,curve)),
                             "post_entry_max_difference_c": float(np.max(np.abs(curve[x>=entry] - direct[x>=entry]))),
                             "area": metrics["area_rising_above_217"], "constraint_margins": margins(metrics).tolist(),
                             "threshold_after_entry": bool(metrics["t217_up"] * speed / 60 > entry), "feasible": feasible})
    _, boundary_metrics = independently_solve(q2["settings"], q2["speed_cm_min"], parameters)
    check = {"scope": "fixed positive time constants, fixed nonnegative forcing relative to ambient and common entry temperature; no physical validation",
             "speed_comparison_identity": identity,
             "speed_sweep": speed_sweep,
             "sweep_strictly_decreasing": all(b["peak_c"] < a["peak_c"] for a,b in zip(speed_sweep,speed_sweep[1:])),
             "q2_boundary": {"speed_cm_min": q2["speed_cm_min"], "continuous_peak_c": boundary_metrics["peak"],
                             "other_constraint_margins": margins(boundary_metrics).tolist()[:6]},
             "q3_superposition": {"max_error_c": superposition_error, "tolerance_c": 1e-8,
                                   "entry_cm": entry, "entry_weights": entry_weights.tolist(),
                                   "null_direction": direction.tolist(), "alternatives": alternatives}}
    check["passed"] = bool(identity["passed"] and check["sweep_strictly_decreasing"] and superposition_error < 1e-8
                           and all(row["feasible"] and row["threshold_after_entry"] and row["post_entry_max_difference_c"] < 1e-8 for row in alternatives)
                           and abs(boundary_metrics["peak"] - 240) < .005 and min(check["q2_boundary"]["other_constraint_margins"]) > 0)
    write_json(run / "artifacts/structural_evidence.json", check)
    if not check["passed"]:
        raise RuntimeError("model structure verification failed; inspect structural_evidence.json")
    print({"passed": True, "speed_identity_error_c": identity["max_identity_error_c"],
           "superposition_error_c": superposition_error, "q3_alternatives": alternatives})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    evaluate(parser.parse_args().run)
