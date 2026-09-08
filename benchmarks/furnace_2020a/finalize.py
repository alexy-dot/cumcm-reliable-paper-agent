"""Record observable trial completion, without granting submission or award certification."""
import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill/cumcm-reliable-paper/scripts"))
from engine import read_json, write_json, sha256_file, validate_run


def finalize(run, visual_review_note=""):
    validation = validate_run(run, "PAPER_LINKED")
    if validation["failed_checks"] != ["HUMAN-SIGNOFFS"]:
        raise ValueError(validation["failed_checks"])
    independent = read_json(run / "artifacts/independent_comparison.json")
    if not independent["passed"]:
        raise ValueError("numerical comparison failed")
    with (run / "artifacts/result.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))[1:]
    times = [float(row[0]) for row in rows]
    if len(rows) != 671 or times[0] != 0 or times[-1] != 335 or any(abs(b - a - .5) > 1e-10 for a,b in zip(times, times[1:])):
        raise ValueError("Q1 output grid mismatch")
    clock = read_json(run / "trial_clock.json")
    ended = datetime.now(timezone.utc)
    elapsed = (ended - datetime.fromisoformat(clock["started_at"])).total_seconds()
    solution = read_json(run / "artifacts/solution.json")
    rendering = read_json(run / "paper/render_report.json")
    if visual_review_note:
        rendering["visual_review"] = {"status": "PASS", "reviewer_type": "agent",
                                    "scope": visual_review_note, "pdf_sha256": sha256_file(run / "paper/main.pdf")}
        write_json(run / "paper/render_report.json", rendering)
    summary = {
        "case": "2020 A furnace profile", "started_at": clock["started_at"], "artifact_ready_at": ended.isoformat(),
        "elapsed_minutes": elapsed / 60, "budget_minutes": clock["budget_minutes"],
        "within_artifact_time_budget": elapsed <= clock["budget_minutes"] * 60,
        "exposure_scope": clock["purpose"],
        "workflow_scope": "source freeze before analysis; ledgers assembled after solving; not a prospectively approved stage-by-stage run",
        "output_coverage": {"Q1": {"temperature_points": 4, "csv_samples": len(rows)}, "Q2": "speed boundary and all process metrics",
                            "Q3": "best found feasible settings, area, non-unique alternatives", "Q4": "explicit epsilon tradeoff and symmetry metric"},
        "calibration": read_json(run / "artifacts/calibration.json")["models"]["zoned"],
        "independent_numerical_checks": {"count": len(independent["comparisons"]), "passed": independent["passed"]},
        "paper": {"pages": rendering["pages"], "sha256": sha256_file(run / "paper/main.pdf"), "visual_review": rendering["visual_review"]},
        "headlines": {"Q2_speed_cm_min": solution["Q2"]["speed_cm_min"], "Q3_area": solution["Q3"]["metrics"]["area_rising_above_217"],
                      "Q4_symmetry": solution["Q4"]["metrics"]["symmetry"]},
        "submission_ready": False, "national_award_level": "NOT_ESTABLISHED",
        "remaining": ["real human review", "current contest rule and formatting approval", "new-condition physical validation", "broader task-family evaluation"],
    }
    write_json(run / "trial_summary.json", summary)
    clock["status"] = "ARTIFACTS_READY_REVIEW_PENDING"
    clock["events"].append({"phase": "artifacts_ready", "at": ended.isoformat()})
    write_json(run / "trial_clock.json", clock)
    print({"elapsed_minutes": summary["elapsed_minutes"], "paper_pages": rendering["pages"],
           "independent_checks": len(independent["comparisons"]), "submission_ready": False})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--visual-review-note", default="")
    args = parser.parse_args()
    finalize(args.run, args.visual_review_note)
