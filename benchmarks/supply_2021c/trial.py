"""Clock and immutable final snapshot for the 2021 C source-only trial."""
import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def start(folder, source):
    folder.mkdir(parents=True, exist_ok=False)
    now = time.time()
    protocol = {"started_at": dt.datetime.now(dt.timezone.utc).isoformat(), "start_epoch": now,
                "limit_seconds": 10800, "deadline_epoch": now + 10800,
                "exposure_scope": "No prior solution/review located in workspace; title/taxonomy metadata previously available. Model pretraining exposure cannot be excluded.",
                "allowed": "Official problem, all four official workbooks, generic libraries and existing generic skill tools only until final snapshot.",
                "forbidden": "Same-problem papers, worked answers, public solution code, online answer searches.",
                "acceptance": "All official requested outputs, including result templates, independently verified calculations, Chinese mathematical paper with visual inspection, and reproducible code. Missing outputs fail full-trial acceptance regardless of test score.",
                "status": "RUNNING", "events": []}
    save(folder / "trial.json", protocol)
    cmd = [sys.executable, str(ROOT / "skill/cumcm-reliable-paper/scripts/cumcm_agent.py"), "init",
           "--problem", str(source / "CUMCM2021-C.pdf"), "--output", str(folder / "run"), "--title", "2021 C 原材料订购与运输限时演练"]
    for path in sorted(source.glob("*.xlsx")):
        cmd.extend(["--attachment", str(path)])
    subprocess.run(cmd, check=True)
    print({"started_at": protocol["started_at"], "limit_seconds": 10800}, flush=True)


def record(folder, stage, note, final):
    path = folder / "trial.json"
    p = json.loads(path.read_text(encoding="utf-8"))
    if p["status"] != "RUNNING":
        raise ValueError("trial already closed; repairs must use a new run")
    now = time.time()
    event = {"stage": stage, "epoch": now, "elapsed_seconds": now - p["start_epoch"], "note": note}
    if final:
        # Snapshot code and outputs before a later review or repair can overwrite them.
        with zipfile.ZipFile(folder / "final-snapshot.zip", "x", zipfile.ZIP_DEFLATED) as z:
            for base, prefix in ((folder / "run", "run"), (Path(__file__).parent, "code")):
                for item in sorted(base.rglob("*")):
                    if item.is_file() and "__pycache__" not in item.parts and "node_modules" not in item.parts:
                        z.write(item, str(Path(prefix) / item.relative_to(base)))
        event["snapshot_sha256"] = hashlib.sha256((folder / "final-snapshot.zip").read_bytes()).hexdigest()
        event["epoch"] = time.time()
        event["elapsed_seconds"] = event["epoch"] - p["start_epoch"]
        p["status"] = "FINISHED_WITHIN_TIME" if event["elapsed_seconds"] <= p["limit_seconds"] else "FINISHED_OVERTIME"
        p["acceptance"] = "PENDING_CONTENT_REVIEW; timing alone is not acceptance"
    p["events"].append(event)
    save(path, p)
    print(event, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("start", "mark", "finish")); ap.add_argument("folder", type=Path)
    ap.add_argument("--source", type=Path); ap.add_argument("--stage", default="checkpoint"); ap.add_argument("--note", default="")
    args = ap.parse_args()
    if args.action == "start":
        if args.source is None: ap.error("start requires --source")
        start(args.folder.resolve(), args.source.resolve())
    else:
        record(args.folder.resolve(), args.stage, args.note, args.action == "finish")
