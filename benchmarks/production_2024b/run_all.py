"""Four-question historical replay with explicitly requested illustrative Q4 counts."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from prepare import read_json,write_json


def contract(run):
    data=read_json(run/"problem_contract.json")
    objectives=["anytime-valid acceptance/rejection and sample-count operating characteristics","two-part stationary policy costs with free replacement","eight-part tree policy optimization","sample-count-conditional production decisions with explicit illustrative scenarios"]
    data.update(problem_interpretation="Persistent component quality, conditional assembly defects and free replacement; no invented observed counts for Q4",
                official_outputs=objectives,questions=[{"id":"Q"+str(i),"source_locator":"original PDF question "+str(i)+" and appendix definitions",
                "objective":value,"inputs":["source-frozen original problem and explicitly labeled model settings"],"outputs":[value],
                "decision_variables":["inspection, disassembly and stopping policy as applicable"],"hard_constraints":["persistent component quality","conditional assembly defect rate","one payment per fulfilled order"],
                "units":["yuan per fulfilled order","probability","sample count"],"ambiguities":["actual Q4 sample counts and confidence-loss specification absent"],
                "termination_condition":"specified finite policy class and independent numerical verification; unresolved sampling remains unresolved"} for i,value in enumerate(objectives,1)])
    write_json(run/"problem_contract.json",data)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--example-sizes",type=int,nargs="+",required=True,help="explicitly illustrative, never actual observed counts")
    p.add_argument("--latex-compiler");p.add_argument("--cache-dir",type=Path)
    args=p.parse_args();compiler=args.latex_compiler or shutil.which("tectonic") or shutil.which("xelatex")
    if not compiler:p.error("Tectonic or XeLaTeX needed")
    if args.example_sizes!=[20,200]:p.error("the reviewed four-question paper uses exactly --example-sizes 20 200; use sampled_rates.py for other real or illustrative samples")
    scripts=Path(__file__).resolve().parent;run=args.output.resolve()
    def execute(name,*extra):subprocess.run([sys.executable,str(scripts/name),*map(str,extra)],check=True)
    execute("run_q1_q2.py","--source",args.source.resolve(),"--output",run)
    contract(run);execute("run_q3.py",run)
    folders=[]
    for n in args.example_sizes:
        samples=run/f"artifacts/example-n{n}.json";folder=run/f"artifacts/uncertainty-n{n}";folders.append(folder)
        execute("sampled_rates.py",run,"--make-example",n,"--output",samples)
        execute("sampled_rates.py",run,"--samples",samples,"--output",folder)
        execute("verify_sampled_rates.py",run,folder)
    execute("report_q4.py",run,*folders);execute("figures.py",run);execute("paper.py",run)
    renderer=scripts.parents[1]/"skill/cumcm-reliable-paper/scripts/render_paper.py"
    command=[sys.executable,str(renderer),"--run",str(run),"--source",str(run/"paper/document.json"),"--latex-compiler",compiler]
    if args.cache_dir:command.extend(["--cache-dir",str(args.cache_dir.resolve())])
    subprocess.run(command,check=True)
    subprocess.run([sys.executable,str(renderer.with_name("paper_structure.py")),str(run/"paper/main.pdf"),"--contract",str(run/"problem_contract.json"),"--report",str(run/"paper/structure_review.json")],check=True)
    execute("finish.py",run)
