"""Reproduce the explicitly partial Q1/Q2 historical study from the supplied original."""
import argparse
from pathlib import Path
import subprocess
import sys

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();scripts=Path(__file__).resolve().parent
    subprocess.run([sys.executable,str(scripts/"prepare.py"),"--source",str(args.source.resolve()),"--output",str(args.output.resolve())],check=True)
    for name in ("sampling.py","rework.py","verify.py","report.py"):
        subprocess.run([sys.executable,str(scripts/name),str(args.output.resolve())],check=True)
