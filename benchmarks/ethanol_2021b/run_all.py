"""Reproduce the retrospective 2021 B reanalysis, with nested grouped predictions."""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--source-dir",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--paper-python",default=sys.executable);p.add_argument("--latex-compiler");p.add_argument("--cache-dir",type=Path)
    p.add_argument("--legacy-predictions",type=Path,help="optional prior OOF CSV for a read-only baseline audit")
    args=p.parse_args();compiler=args.latex_compiler or shutil.which("tectonic") or shutil.which("xelatex")
    if compiler is None:p.error("Tectonic or XeLaTeX is required")
    root=Path(__file__).resolve().parent;project=root.parents[1];run=args.output.resolve()
    def execute(name,*extra):subprocess.run([sys.executable,str(root/name),*map(str,extra)],check=True)
    execute("prepare.py","--source-dir",args.source_dir.resolve(),"--output",run)
    for name in ("analyze.py","decision.py","verify.py","plots.py","paper.py"):execute(name,run)
    if args.legacy_predictions:execute("legacy_audit.py",run,"--legacy-predictions",args.legacy_predictions.resolve())
    renderer=project/"skill/cumcm-reliable-paper/scripts/render_paper.py"
    command=[args.paper_python,str(renderer),"--run",str(run),"--source",str(run/"paper/document.json"),"--latex-compiler",compiler]
    if args.cache_dir:command.extend(["--cache-dir",str(args.cache_dir.resolve())])
    subprocess.run(command,check=True)
    subprocess.run([args.paper_python,str(renderer.with_name("paper_structure.py")),str(run/"paper/main.pdf"),"--contract",str(run/"problem_contract.json"),"--report",str(run/"paper/structure_review.json")],check=True)
    execute("finish.py",run)
