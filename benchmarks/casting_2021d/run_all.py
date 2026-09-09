"""Replay all three 2021 D questions from the original PDF through the checked paper."""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--paper-python",default=sys.executable)
    parser.add_argument("--latex-compiler")
    parser.add_argument("--cache-dir",type=Path)
    args=parser.parse_args()
    compiler=args.latex_compiler or shutil.which("tectonic") or shutil.which("xelatex")
    if not compiler: parser.error("mathematical typesetting requires Tectonic or XeLaTeX")
    scripts=Path(__file__).resolve().parent; project=scripts.parents[1]
    output=args.output.resolve()
    def execute(name,*extra,python=sys.executable):
        subprocess.run([python,str(scripts/name),*map(str,extra)],check=True)
    execute("prepare.py","--source",args.source.resolve(),"--output",output)
    for name in ("solve.py","verify.py","sensitivity.py","plots.py","package.py","check_package.py","paper.py"):
        execute(name,output)
    renderer=project/"skill/cumcm-reliable-paper/scripts/render_paper.py"
    command=[args.paper_python,str(renderer),"--run",str(output),"--source",str(output/"paper/document.json"),"--latex-compiler",compiler]
    if args.cache_dir: command.extend(["--cache-dir",str(args.cache_dir.resolve())])
    subprocess.run(command,check=True)
    subprocess.run([args.paper_python,str(renderer.with_name("paper_structure.py")),str(output/"paper/main.pdf"),
                    "--contract",str(output/"problem_contract.json"),"--report",str(output/"paper/structure_review.json")],check=True)
    execute("finish.py",output)
