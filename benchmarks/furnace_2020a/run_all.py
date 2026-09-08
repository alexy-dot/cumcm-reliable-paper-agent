"""Replay the historical furnace benchmark from user-supplied original files."""
import argparse
import subprocess
import sys
from pathlib import Path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--paper-python", default=sys.executable, help="Python with reportlab and pypdf; defaults to this interpreter")
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    scripts = Path(__file__).resolve().parent
    project = scripts.parents[1]
    output = args.output.resolve()
    def run(name, *extra, interpreter=sys.executable):
        subprocess.run([interpreter, str(scripts / name), *map(str, extra)], check=True)
    run("prepare.py", "--source-dir", args.source_dir.resolve(), "--output", output)
    for phase in ["calibrate.py", "solve.py", "independent.py", "sensitivity.py", "plots.py", "paper.py"]:
        run(phase, output)
    command = [args.paper_python, str(project / "skill/cumcm-reliable-paper/scripts/render_paper.py"),
               "--run", str(output), "--source", str(output / "paper/document.json")]
    if args.font:
        command.extend(["--font", str(args.font)])
    subprocess.run(command, check=True)
    run("link_workflow.py", output)
    run("finalize.py", output)
