"""Replay the historical furnace benchmark from user-supplied original files."""
import argparse
import subprocess
import sys
import shutil
from pathlib import Path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--paper-python", default=sys.executable, help="Python with reportlab and pypdf; defaults to this interpreter")
    parser.add_argument("--font", type=Path)
    parser.add_argument("--latex-compiler", help="Tectonic or XeLaTeX executable for mathematical typesetting")
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    compiler = args.latex_compiler or shutil.which("tectonic") or shutil.which("xelatex")
    if not compiler:
        parser.error("this mathematical paper requires Tectonic or XeLaTeX; install it or pass --latex-compiler")
    scripts = Path(__file__).resolve().parent
    project = scripts.parents[1]
    output = args.output.resolve()
    def run(name, *extra, interpreter=sys.executable):
        subprocess.run([interpreter, str(scripts / name), *map(str, extra)], check=True)
    run("prepare.py", "--source-dir", args.source_dir.resolve(), "--output", output)
    for phase in ["calibrate.py", "solve.py", "independent.py", "optimizer_comparison.py", "sensitivity.py", "structural_evidence.py", "decision_evidence.py", "scenario_design.py", "plots.py", "paper.py"]:
        run(phase, output)
    command = [args.paper_python, str(project / "skill/cumcm-reliable-paper/scripts/render_paper.py"),
               "--run", str(output), "--source", str(output / "paper/document.json")]
    if args.font:
        command.extend(["--font", str(args.font)])
    command.extend(["--latex-compiler", compiler])
    if args.cache_dir:
        command.extend(["--cache-dir", str(args.cache_dir.resolve())])
    subprocess.run(command, check=True)
    run("link_workflow.py", output)
    subprocess.run([args.paper_python, str(project / "skill/cumcm-reliable-paper/scripts/paper_structure.py"),
                    str(output / "paper/main.pdf"), "--contract", str(output / "problem_contract.json"),
                    "--report", str(output / "paper/structure_review.json")], check=True)
    run("finalize.py", output)
