"""Reproduce the 2021 C calculations; optionally rebuild official workbooks and PDF."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent


def run(args):
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    (out/"sources").mkdir();(out/"artifacts").mkdir()
    sources=sorted(args.source.glob("*.xlsx"))+[args.source/"CUMCM2021-C.pdf"]
    if len(sources)!=5 or not all(p.is_file() for p in sources):raise ValueError("official PDF and four original workbooks required")
    for p in sources:shutil.copy2(p,out/"sources"/p.name)
    (out/"problem_contract.json").write_text(json.dumps({"schema_version":"1.0","run_id":"supply-2021c-reproduction","title":"2021 C 原材料订购与运输"},ensure_ascii=False),encoding="utf-8")
    for script in ("prepare.py","solve.py","verify.py","alternatives.py"):
        subprocess.run([sys.executable,str(HERE/script),str(out)],check=True)
    if args.deliver:
        bundled=Path.home()/".cache/codex-runtimes/codex-primary-runtime/dependencies/node"
        node=args.node or bundled/"bin/node"
        modules=args.artifact_modules or bundled/"node_modules"
        if not node.is_file() or not (modules/"@oai/artifact-tool").is_dir():
            raise ValueError("workbook export requires available Codex artifact-tool runtime; provide --node and --artifact-modules")
        link=HERE/"node_modules"
        if not link.exists():link.symlink_to(modules.resolve(),target_is_directory=True)
        subprocess.run([str(node),str(HERE/"workbooks.mjs"),str(out),"fill"],check=True)
        for script in ("check_workbooks.py","figures.py","package.py","paper.py"):
            subprocess.run([sys.executable,str(HERE/script),str(out)],check=True)
        renderer=HERE/"renderer/render_paper.py"
        if not renderer.exists():renderer=HERE.parents[1]/"skill/cumcm-reliable-paper/scripts/render_paper.py"
        cmd=[sys.executable,str(renderer),"--run",str(out),"--source",str(out/"paper/document.json")]
        if args.latex_compiler:cmd.extend(["--latex-compiler",str(args.latex_compiler)])
        if args.cache_dir:cmd.extend(["--cache-dir",str(args.cache_dir)])
        subprocess.run(cmd,check=True)
    print("Reproduction finished. Original timed-trial acceptance is not changed.")


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source",type=Path,required=True);ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--deliver",action="store_true");ap.add_argument("--node",type=Path);ap.add_argument("--artifact-modules",type=Path)
    ap.add_argument("--latex-compiler",type=Path);ap.add_argument("--cache-dir",type=Path)
    run(ap.parse_args())
