"""Portable support-package entry point. Run with Python -I in a new output directory."""
import argparse
import copy
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

# -I deliberately excludes cwd/PYTHONPATH; allow only this extracted package's code.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_io import read_json, write_json, sha256_file


def comparable_solution(solution):
    value = copy.deepcopy(solution)
    for record in value["online"].values():
        for event in record["events"]:
            event.pop("planning_seconds", None)
    return value


def comparable_sensitivity(sensitivity):
    value = copy.deepcopy(sensitivity)
    value.pop("solution_sha256", None)
    return value


def check_manifest(root):
    manifest = read_json(root / "manifest.json")
    seen = set()
    for item in manifest["files"]:
        name = item["path"]
        if (not isinstance(name, str) or "\\" in name or ":" in name or
                PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or name in seen):
            raise ValueError("nonportable or duplicate manifest path")
        seen.add(name)
        path = root / name
        path.resolve().relative_to(root.resolve())
        if not path.is_file() or path.is_symlink() or sha256_file(path) != item["sha256"]:
            raise ValueError("package file missing or changed: " + name)
    required = {"artifact_io.py", "solve.py", "verify.py", "sensitivity.py", "reproduce.py",
                "facts.json", "expected-results.json", "requirements.txt"}
    if not required <= seen:
        raise ValueError("support manifest omits required files")
    return manifest


def reproduce(root, output, source=None):
    if not __debug__:
        raise ValueError("Verification requires assertions; run without -O")
    root, output = Path(root).resolve(), Path(output).resolve()
    check_manifest(root)
    facts = read_json(root / "facts.json")
    if source is not None and sha256_file(source) != facts["source_sha256"]:
        raise ValueError("supplied original PDF does not match the reviewed source")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "artifacts/facts.json", facts)
    from solve import solve
    from verify import verify
    from sensitivity import assess
    solve(output)
    verification = verify(output)
    assess(output)
    # Expected records are opened only after all computations have completed.
    expected = read_json(root / "expected-results.json")
    actual = read_json(output / "artifacts/solution.json")
    sensitivity = read_json(output / "artifacts/sensitivity.json")
    checks = {
        "all_tail_and_online_decisions": comparable_solution(actual) == expected["solution"],
        "baseline_grid_and_phase_sensitivity": comparable_sensitivity(sensitivity) == expected["sensitivity"],
        "independent_network_and_interval_verification": verification["passed"] is True,
    }
    report = {"passed": all(checks.values()), "checks": checks,
              "source_pdf_checked": source is not None,
              "input_scope": "reviewed statement parameters in facts.json; optional original PDF checked by hash, not reinterpreted automatically",
              "comparison_scope": "all deterministic solution fields including cuts, recovered intervals and objectives; only planning_seconds excluded; sensitivity source hash excluded because timings change solution hash",
              "manifest_sha256": sha256_file(root / "manifest.json"),
              "solution_sha256": sha256_file(output / "artifacts/solution.json"),
              "submission_ready": False}
    write_json(output / "reproduction_report.json", report)
    if not report["passed"]:
        raise ValueError("reproduced results differ from the packaged reference")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, help="optional original PDF; hash checked against the reviewed source")
    parser.add_argument("--paper", action="store_true", help="also regenerate figures, full source appendix and PDF")
    parser.add_argument("--paper-python", default=sys.executable)
    parser.add_argument("--latex-compiler")
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    output = args.output.resolve()
    report = reproduce(root, output, args.source)
    if args.paper:
        report["paper"] = {"render_status": "PENDING", "visual_review": "PENDING"}
        write_json(output / "reproduction_report.json", report)
        from plots import draw
        from paper import compose
        draw(output)
        compose(output, support_root=root)
        command = [args.paper_python, "-I", str(root / "render_latex.py"), "--run", str(output),
                   "--source", str(output / "paper/document.json")]
        if args.latex_compiler:
            command.extend(["--compiler", args.latex_compiler])
        if args.cache_dir:
            command.extend(["--cache-dir", str(args.cache_dir.resolve())])
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        subprocess.run(command, check=True, env=environment)
        report["paper"] = {"render_status": "COMPILED", "pdf_sha256": sha256_file(output / "paper/main.pdf"), "visual_review": "PENDING"}
        write_json(output / "reproduction_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
