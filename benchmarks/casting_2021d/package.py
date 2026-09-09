"""Snapshot portable computation/manuscript sources and build the support archive."""
import argparse
import platform
import shutil
import sys
from pathlib import Path

from artifact_io import read_json, write_json, sha256_file
from reproduce import comparable_solution, comparable_sensitivity

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "skill/cumcm-reliable-paper/scripts"))
from package_support import package_support

CODE = ("artifact_io.py", "solve.py", "verify.py", "sensitivity.py", "plots.py", "paper.py", "reproduce.py")


def build(run):
    run = Path(run).resolve()
    if read_json(run / "state.json")["stage"] == "VERIFIED":
        raise ValueError("create a new run before packaging a sealed result")
    solution = read_json(run / "artifacts/solution.json")
    independent = read_json(run / "artifacts/independent.json")
    sensitivity = read_json(run / "artifacts/sensitivity.json")
    digest = sha256_file(run / "artifacts/solution.json")
    if (not independent["passed"] or independent["solution_sha256"] != digest or
            sensitivity["solution_sha256"] != digest or
            solution["facts_sha256"] != sha256_file(run / "artifacts/facts.json")):
        raise ValueError("results or independent verification are stale")
    staging = run / "artifacts/support-input"
    staging.mkdir(exist_ok=False)
    files = []
    def add(source, name, role):
        shutil.copyfile(source, staging / name)
        files.append({"source": "artifacts/support-input/" + name, "archive_path": name, "role": role})
    for name in CODE:
        add(Path(__file__).with_name(name), name, "code")
    add(PROJECT / "skill/cumcm-reliable-paper/scripts/render_latex.py", "render_latex.py", "code")
    add(Path(__file__).with_name("requirements.txt"), "requirements.txt", "document")
    add(Path(__file__).with_name("SUPPORT.md"), "README.md", "document")
    add(PROJECT / "LICENSE", "LICENSE", "document")
    add(run / "artifacts/facts.json", "facts.json", "data")
    import numpy
    import scipy
    write_json(staging / "environment.json", {"python": platform.python_version(), "numpy": numpy.__version__,
               "scipy": scipy.__version__, "scope": "observed runtime, not a promise of bitwise equality on all platforms"})
    write_json(staging / "expected-results.json", {"solution": comparable_solution(solution),
               "sensitivity": comparable_sensitivity(sensitivity)})
    for name in ("environment.json", "expected-results.json"):
        files.append({"source": "artifacts/support-input/" + name, "archive_path": name, "role": "data"})
    selection = {"files": files}
    write_json(run / "artifacts/support-selection.json", selection)
    receipt = package_support(run, selection)
    print({"support_zip": "artifacts/submission-package/support.zip", "code_files": receipt["code_count"],
           "sha256": receipt["sha256"], "isolated_reproduction": "PENDING"}, flush=True)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    build(parser.parse_args().run)
