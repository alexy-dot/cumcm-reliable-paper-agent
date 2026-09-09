"""Actually execute the extracted package outside the repository with isolated Python."""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from artifact_io import read_json, write_json, sha256_file


def check(run):
    run = Path(run).resolve()
    package = run / "artifacts/submission-package"
    archive = package / "support.zip"
    receipt = read_json(package / "package_receipt.json")
    if receipt["sha256"] != sha256_file(archive):
        raise ValueError("support ZIP differs from package receipt")
    with tempfile.TemporaryDirectory(prefix="casting-support-") as temporary:
        root = Path(temporary)
        extracted = root / "extracted"
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                target = (extracted / name).resolve()
                target.relative_to(extracted.resolve())
                if "\\" in name:
                    raise ValueError("nonportable ZIP member")
            bundle.extractall(extracted)
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        command = [sys.executable, "-I", str(extracted / "reproduce.py"), "--output", str(root / "reproduced")]
        completed = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
        (run / "artifacts/support_reproduction.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
        if completed.returncode:
            raise ValueError("isolated support reproduction failed; inspect artifacts/support_reproduction.log")
        result = read_json(root / "reproduced/reproduction_report.json")
        if not result.get("passed"):
            raise ValueError("isolated reproduction did not pass")
        # Preserve actual recomputed outputs as evidence, not just the process exit status.
        destination = run / "artifacts/isolated_reproduction"
        if destination.exists():
            raise ValueError("isolated reproduction already recorded; use a new run")
        shutil.copytree(root / "reproduced/artifacts", destination)
        result.update(archive_sha256=receipt["sha256"],
                      original_solution_sha256=sha256_file(run / "artifacts/solution.json"),
                      execution_scope="ZIP extracted in a fresh system temporary directory outside repository; Python -I, no PYTHONPATH/PYTHONHOME, no expected-results read until solving/verification complete",
                      preserved_recomputed_artifacts="artifacts/isolated_reproduction")
        write_json(run / "artifacts/support_reproduction.json", result)
    print({"support_reproduced": True, "archive_sha256": receipt["sha256"]}, flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    check(parser.parse_args().run)
