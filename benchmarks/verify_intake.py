"""Integration benchmark for dense numeric workbooks; optional openpyxl oracle.

Run from the project root:
python3 benchmarks/verify_intake.py --source-dir ../2020/D --output runs/intake-2020d
This checks ingestion only, not a modeling solution or an unseen-problem test.
"""
import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill/cumcm-reliable-paper/scripts"))
from engine import initialize_run, read_json, write_json


def main():
    import openpyxl  # Benchmark dependency only; not used by the skill.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    problems = sorted(args.source_dir.glob("*.docx"))
    if len(problems) != 1:
        parser.error("expected one DOCX problem")
    attachments = sorted(args.source_dir.glob("*.xlsx"))
    start = time.perf_counter()
    initialize_run(args.output, problems[0], attachments, "Full intake integration check")
    audit = read_json(args.output / "source_audit.json")
    intake_seconds = time.perf_counter() - start
    print(f"Full scan finished in {intake_seconds:.2f}s; comparing with openpyxl", flush=True)
    comparisons = []
    for source in audit["sources"]:
        if source["role"] != "attachment":
            continue
        book = openpyxl.load_workbook(args.output / source["frozen_path"], read_only=True, data_only=True)
        try:
            for sheet in source["sheets"]:
                ws = book[sheet["name"]]
                ws.reset_dimensions()  # Do not rely on the same declared dimensions.
                rows = ws.iter_rows(values_only=True)
                header = next(rows)
                columns = [[] for _ in header]
                missing = [0 for _ in header]
                row_count = 0
                for row in rows:
                    row_count += 1
                    if len(row) > len(header):
                        raise ValueError("oracle expects dense tables with stable width")
                    for index in range(len(header)):
                        value = row[index] if index < len(row) else None
                        if value is None:
                            missing[index] += 1
                        elif isinstance(value, (float, int)) and math.isfinite(value):
                            columns[index].append(value)
                        else:
                            raise ValueError("oracle expects finite numeric cells")
                actual = sheet["profile"]
                failures = []
                if row_count != actual["data_row_count"]:
                    failures.append("row_count")
                for index, values in enumerate(columns):
                    measured = actual["columns"][index]
                    expected_mean = math.fsum(values) / len(values) if values else None
                    if measured["missing_count"] != missing[index] or measured["numeric_count"] != len(values):
                        failures.append(f"column-{index + 1}:counts")
                    if values and (min(values) != measured["minimum"] or max(values) != measured["maximum"]
                                   or not math.isclose(expected_mean, measured["mean"], rel_tol=1e-10, abs_tol=1e-10)):
                        failures.append(f"column-{index + 1}:numeric_statistics")
                comparisons.append({"source_id": source["source_id"], "sheet": sheet["name"],
                                    "data_rows": row_count, "passed": not failures, "failures": failures})
            print(f"Compared {len(source['sheets'])} sheets in {source['original_name']}", flush=True)
        finally:
            book.close()
    report = {"scope": "full intake only; dense numeric workbook oracle",
              "oracle": f"openpyxl {openpyxl.__version__} + math.fsum; reset worksheet dimensions",
              "intake_seconds": intake_seconds, "total_seconds": time.perf_counter() - start,
              "sheet_count": len(comparisons), "data_rows": sum(row["data_rows"] for row in comparisons),
              "passed": bool(comparisons) and all(row["passed"] for row in comparisons),
              "comparisons": comparisons}
    write_json(args.output / "intake_comparison.json", report)
    print({key: value for key, value in report.items() if key != "comparisons"})
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
