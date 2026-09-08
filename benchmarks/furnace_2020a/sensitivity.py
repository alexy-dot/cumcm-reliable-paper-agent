"""Parameter scenarios and interior operating suggestions, not experimental guarantees."""
import argparse
import sys
from pathlib import Path
import numpy as np
from model import curve_metrics, margins
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill/cumcm-reliable-paper/scripts"))
from engine import read_json, write_json


def analyze(run):
    solution = read_json(run / "artifacts/solution.json")
    parameters = np.array(solution["parameters"])
    scenarios = [("nominal", parameters)]
    for index in [0, 1, 2, 3, 4, 6]:
        for direction in [-1, 1]:
            altered = parameters.copy()
            altered[index] *= 1 + direction * .02
            scenarios.append((f"parameter_{index}_{direction * 2:+}%", altered))
    rows = {}
    for question in ["Q2", "Q3", "Q4"]:
        point = solution[question]
        checks = []
        for name, altered in scenarios:
            result = curve_metrics(point["settings"], point["speed_cm_min"], altered, dx=.1)
            checks.append({"scenario": name, "metrics": result, "margins": margins(result).tolist(),
                           "feasible": bool(np.min(margins(result)) >= -1e-4)})
        suggestion = None
        # Keep the same heater settings; search downward for a speed with margins
        # across the specified one-at-a-time parameter scenarios.
        for speed in np.arange(np.floor(point["speed_cm_min"] * 10) / 10, 64.99, -.1):
            evaluated = [curve_metrics(point["settings"], speed, altered, dx=.1) for _, altered in scenarios]
            minimum = np.min(np.array([margins(result) for result in evaluated]), axis=0)
            if np.min(minimum) > .05:
                suggestion = {"settings": point["settings"], "speed_cm_min": float(speed),
                              "minimum_scenario_margins": minimum.tolist(), "nominal_metrics": evaluated[0],
                              "scope": "process constraints only; area and symmetry tradeoffs must also be reviewed",
                              "q4_area_cap_satisfied": evaluated[0]["area_rising_above_217"] <= point.get("area_cap", float("inf"))}
                break
        rows[question] = {"checks": checks, "failed_scenarios": sum(not row["feasible"] for row in checks),
                          "interior_suggestion": suggestion}
    write_json(run / "artifacts/sensitivity.json", {
        "scope": "OAT +/-2% of six fitted rates/length parameters; excludes correlated simultaneous changes and new physical runs",
        "entry_parameter": "at fitted bound; not perturbed beyond the original geometry range",
        "questions": rows,
    })
    print({question: {"failed": row["failed_scenarios"], "suggested_speed": row["interior_suggestion"]["speed_cm_min"] if row["interior_suggestion"] else None} for question, row in rows.items()}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    analyze(parser.parse_args().run)
