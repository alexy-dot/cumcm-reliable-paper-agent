#!/usr/bin/env python3
"""Command-line entrypoint for the CUMCM reliable-paper workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine import (
    STAGES,
    WorkflowError,
    advance_run,
    audit_run_sources,
    initialize_run,
    seal_run,
    signoff_status,
    status_run,
    validate_run,
    write_json,
    read_json,
    _safe_run_path,
)


def print_json(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialize, gate, advance, and seal a traceable CUMCM paper run."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    initialize = commands.add_parser("init", help="freeze sources and create run ledgers")
    initialize.add_argument("--problem", type=Path, required=True)
    initialize.add_argument("--attachment", type=Path, action="append", default=[])
    initialize.add_argument("--output", type=Path, required=True)
    initialize.add_argument("--title", required=True)
    initialize.add_argument("--run-id")

    status = commands.add_parser("status", help="show the current stage and failed gates")
    status.add_argument("run_dir", type=Path)

    inspect = commands.add_parser(
        "inspect", help="regenerate structural audits from frozen sources"
    )
    inspect.add_argument("run_dir", type=Path)

    signoffs = commands.add_parser(
        "signoffs", help="show current human sign-off scopes and match status"
    )
    signoffs.add_argument("run_dir", type=Path)

    validate = commands.add_parser("validate", help="validate accumulated gates")
    validate.add_argument("run_dir", type=Path)
    validate.add_argument("--target", choices=STAGES)
    validate.add_argument("--report", type=Path)

    advance = commands.add_parser("advance", help="advance one stage after validation")
    advance.add_argument("run_dir", type=Path)

    seal = commands.add_parser("seal", help="seal a PAPER_LINKED run as VERIFIED")
    seal.add_argument("run_dir", type=Path)
    submission = commands.add_parser("submission-check", help="check PDF/ZIP files against a source-bound official year profile")
    submission.add_argument("run_dir", type=Path)
    submission.add_argument("--paper", default="paper/main.pdf")
    submission.add_argument("--support")
    submission.add_argument("--year", type=int, required=True)
    submission.add_argument("--ai-used", choices=("yes", "no"), required=True)
    submission.add_argument("--no-code", action="store_true")
    submission.add_argument("--identity-term", action="append", default=[])
    submission.add_argument("--report")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "init":
            result = initialize_run(
                output_dir=args.output,
                problem=args.problem,
                attachments=args.attachment,
                title=args.title,
                run_id=args.run_id,
            )
        elif args.command == "status":
            result = status_run(args.run_dir)
        elif args.command == "inspect":
            result = audit_run_sources(args.run_dir)
        elif args.command == "signoffs":
            result = signoff_status(args.run_dir)
        elif args.command == "validate":
            result = validate_run(args.run_dir, args.target)
            if args.report:
                write_json(args.report, result)
        elif args.command == "advance":
            result = advance_run(args.run_dir)
        elif args.command == "submission-check":
            from submission_check import check_submission
            try:
                report_path = _safe_run_path(args.run_dir, args.report) if args.report else None
                if args.report and report_path is None:
                    raise ValueError("report must remain inside the run directory")
                if report_path and (args.run_dir / "state.json").is_file() and read_json(args.run_dir / "state.json").get("stage") == "VERIFIED":
                    raise ValueError("sealed runs are read-only; omit --report to inspect without writing")
                if report_path and report_path.exists() and "profile_sha256" not in read_json(report_path):
                    raise ValueError("refusing to overwrite an existing artifact with a submission report")
                result = check_submission(args.run_dir, args.paper, args.support, year=args.year,
                                          ai_used=args.ai_used == "yes", identity_terms=args.identity_term, no_code=args.no_code)
                if report_path:
                    write_json(report_path, result)
            except ValueError as exc:
                raise WorkflowError(str(exc)) from exc
        else:
            result = seal_run(args.run_dir)
        print_json(result)
        return 0 if result.get("passed", True) else 1
    except WorkflowError as exc:
        print_json({"passed": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
