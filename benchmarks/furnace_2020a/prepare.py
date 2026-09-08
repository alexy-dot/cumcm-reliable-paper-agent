"""Freeze inputs and start a 180-minute historical-practice clock."""
import argparse
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "skill/cumcm-reliable-paper/scripts"))
from engine import initialize_run, write_json


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    start = datetime.now(timezone.utc).isoformat()
    initialize_run(args.output, args.source_dir / "2020A-炉温曲线.docx",
                   [args.source_dir / "附件.xlsx"], "2020 A 炉温曲线历史题实测", "furnace-2020a")
    write_json(args.output / "trial_clock.json", {
        "started_at": start, "budget_minutes": 180,
        "purpose": "historical-problem practice; repeated runs are replays, not fresh blind trials",
        "status": "RUNNING", "events": [{"phase": "inputs_frozen", "at": datetime.now(timezone.utc).isoformat()}],
    })
    media = args.output / "artifacts/statement_media"
    media.mkdir()
    frozen = next((args.output / "sources").glob("problem__*.docx"))
    with zipfile.ZipFile(frozen) as archive:
        for name in archive.namelist():
            if name.startswith("word/media/") and Path(name).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif"}:
                (media / Path(name).name).write_bytes(archive.read(name))
    print({"started_at": start, "run": str(args.output)})
