"""Append Q3 to an existing source-frozen production study without overwriting it."""
import argparse
from pathlib import Path
import subprocess
import sys

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);args=p.parse_args();scripts=Path(__file__).resolve().parent
    for name in ("multistage.py","verify_multistage.py","report_multistage.py"):
        subprocess.run([sys.executable,str(scripts/name),str(args.run.resolve())],check=True)
