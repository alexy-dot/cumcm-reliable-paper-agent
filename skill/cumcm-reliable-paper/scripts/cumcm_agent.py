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
        else:
            result = seal_run(args.run_dir)
        print_json(result)
        return 0 if result.get("passed", True) else 1
    except WorkflowError as exc:
        print_json({"passed": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
