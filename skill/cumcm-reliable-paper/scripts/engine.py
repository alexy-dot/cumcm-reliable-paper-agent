#!/usr/bin/env python3
"""Deterministic workflow engine for the CUMCM reliable-paper skill."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from source_audit import build_source_audit


STAGES = (
    "READING",
    "MODEL_DRAFT",
    "CODE_RUN",
    "P0_PASS",
    "P1_PASS",
    "PAPER_LINKED",
    "VERIFIED",
)

RESULT_STATUSES = {"HYPOTHESIS", "PROVISIONAL", "VERIFIED", "REJECTED"}
P1_VERDICTS = {"PASS", "WARN", "FAIL"}
STRONG_TERMS = (
    "最优",
    "全局最优",
    "准确",
    "稳健",
    "鲁棒",
    "显著",
    "可靠",
    "可推广",
    "机制成立",
    "optimal",
    "accurate",
    "robust",
    "significant",
    "reliable",
    "generalizable",
)
ANCHOR_TYPES = {
    "hand_calculation",
    "closed_form",
    "enumeration",
    "conservation",
    "synthetic_truth",
    "external_truth",
}
SIGNOFF_REQUIREMENTS = (
    ("S1-INTERPRETATION", "READING", "central problem interpretation"),
    ("S2-ASSUMPTIONS-MODEL", "MODEL_DRAFT", "main assumptions and model selection"),
    ("S3-KEY-REPRODUCTION", "P1_PASS", "one key numerical reproduction"),
    ("S4-FINAL-FEASIBILITY", "P1_PASS", "final solution feasibility"),
    ("S5-ABSTRACT-HEADLINES", "PAPER_LINKED", "abstract headlines and strong wording"),
    ("S6-RULES-AI-DECLARATION", "PAPER_LINKED", "rules and AI-use declaration"),
)


class WorkflowError(RuntimeError):
    """Raised when the run cannot safely proceed."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkflowError(f"Missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkflowError(f"Expected a JSON object in {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _nonempty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return value is not None


def _unique(values: Iterable[str]) -> bool:
    values = list(values)
    return len(values) == len(set(values))


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    return cleaned or "cumcm-run"


def _copy_source(source: Path, destination: Path) -> dict[str, Any]:
    if not source.is_file():
        raise WorkflowError(f"Source is not a file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {
        "original_name": source.name,
        "frozen_path": destination.as_posix(),
        "sha256": sha256_file(destination),
        "bytes": destination.stat().st_size,
    }


def _safe_run_path(run_dir: Path, value: Any) -> Path | None:
    raw = Path(str(value))
    if raw.is_absolute():
        return None
    candidate = (run_dir / raw).resolve()
    try:
        candidate.relative_to(run_dir.resolve())
    except ValueError:
        return None
    return candidate


def _canonical_sha256(value: Any) -> str:
    serialized = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _json_pointer(document: Any, pointer: Any) -> Any:
    """Resolve a result location without accepting negative or ambiguous indices."""
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise WorkflowError("source_pointer must be a nonempty JSON Pointer")
    value = document
    for token in pointer[1:].split("/"):
        if re.search(r"~(?![01])", token):
            raise WorkflowError("invalid JSON Pointer escape")
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and token in value:
            value = value[token]
        elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", token) and int(token) < len(value):
            value = value[int(token)]
        else:
            raise WorkflowError("source_pointer does not resolve")
    return value


def _same_result_value(actual: Any, declared: Any) -> bool:
    # Booleans are not numeric results. JSON null and nonfinite values cannot be headlines.
    if type(actual) in (int, float) and type(declared) in (int, float):
        return all(not isinstance(v, float) or math.isfinite(v) for v in (actual, declared)) and actual == declared
    if isinstance(actual, str) and isinstance(declared, str):
        return bool(actual.strip()) and actual == declared
    if isinstance(actual, list) and isinstance(declared, list):
        return bool(actual) and len(actual) == len(declared) and all(_same_result_value(a, b) for a, b in zip(actual, declared))
    return False


def _valid_tolerance(tolerance: Any) -> bool:
    if not isinstance(tolerance, dict) or not isinstance(tolerance.get("reason"), str) or not tolerance["reason"].strip():
        return False
    return all(type(tolerance.get(key)) in (int, float) and math.isfinite(tolerance[key])
               and tolerance[key] >= 0 for key in ("atol", "rtol"))


def _compare_values(primary: Any, reference: Any, atol: float, rtol: float) -> tuple[bool, float]:
    if isinstance(primary, list) and isinstance(reference, list):
        if not primary or len(primary) != len(reference):
            return False, 0.0
        pairs = [_compare_values(a, b, atol, rtol) for a, b in zip(primary, reference)]
        return all(passed for passed, _ in pairs), max(error for _, error in pairs)
    if type(primary) in (int, float) and type(reference) in (int, float):
        if not math.isfinite(primary) or not math.isfinite(reference):
            return False, 0.0
        error = abs(primary - reference)
        limit = atol + rtol * abs(reference)
        return math.isfinite(error) and math.isfinite(limit) and error <= limit, error
    return _same_result_value(primary, reference), 0.0


def _verify_comparisons(run_dir: Path, result: dict, agreement: Any, tolerance: Any) -> list[str]:
    """Recompute agreement from separate outputs, with tolerances frozen in the plan."""
    if not _valid_tolerance(tolerance):
        return ["missing_frozen_tolerance"]
    comparisons = agreement.get("comparisons", []) if isinstance(agreement, dict) else []
    if not isinstance(comparisons, list) or not comparisons:
        return ["missing_comparisons"]
    headlines = result.get("headline_results", [])
    headline_map = {row.get("id"): row for row in headlines if isinstance(row, dict)} if isinstance(headlines, list) else {}
    seen = set()
    failures = []
    for comparison in comparisons:
        if not isinstance(comparison, dict) or not isinstance(comparison.get("result_id"), str):
            failures.append("malformed_comparison")
            continue
        result_id = comparison["result_id"]
        if result_id in seen or result_id not in headline_map:
            failures.append(f"{result_id}:duplicate_or_unknown_result")
            continue
        seen.add(result_id)
        headline = headline_map[result_id]
        primary_path = _safe_run_path(run_dir, headline.get("source_artifact", ""))
        reference_path = _safe_run_path(run_dir, comparison.get("reference_artifact", ""))
        if primary_path is None or reference_path is None or not primary_path.is_file() or not reference_path.is_file():
            failures.append(f"{result_id}:missing_comparison_artifact")
            continue
        if primary_path.samefile(reference_path):
            failures.append(f"{result_id}:same_artifact")
            continue
        try:
            primary = _json_pointer(read_json(primary_path), headline.get("source_pointer"))
            reference = _json_pointer(read_json(reference_path), comparison.get("reference_pointer"))
            passed, error = _compare_values(primary, reference, tolerance["atol"], tolerance["rtol"])
            if not passed:
                failures.append(f"{result_id}:disagreement:error={error}")
        except (WorkflowError, UnicodeError, OSError, OverflowError):
            failures.append(f"{result_id}:unreadable_comparison")
    if seen != set(headline_map):
        failures.append("incomplete_headline_coverage")
    return failures


def _results_without_statuses(value: Any) -> Any:
    if isinstance(value, list):
        return [_results_without_statuses(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _results_without_statuses(item)
            for key, item in value.items()
            if key != "status"
        }
    return value


def _result_artifact_receipts(run_dir: Path, results: dict[str, Any]) -> list[dict[str, Any]]:
    receipts = []
    questions = results.get("questions", [])
    for question in questions if isinstance(questions, list) else []:
        if not isinstance(question, dict):
            continue
        headlines = question.get("headline_results", [])
        for headline in headlines if isinstance(headlines, list) else []:
            if not isinstance(headline, dict):
                continue
            relative = headline.get("source_artifact", "")
            path = _safe_run_path(run_dir, relative)
            receipts.append(
                {
                    "result_id": headline.get("id"),
                    "path": relative,
                    "sha256": sha256_file(path) if path is not None and path.is_file() else None,
                }
            )
    return sorted(receipts, key=lambda item: (str(item["result_id"]), str(item["path"])))


def _stage_signoffs(data: dict[str, dict[str, Any]], stage: str) -> list[dict[str, Any]]:
    required = {
        signoff_id
        for signoff_id, required_stage, _ in SIGNOFF_REQUIREMENTS
        if required_stage == stage
    }
    items = data["signoff_ledger.json"].get("items", [])
    return sorted(
        [
            item
            for item in items
            if isinstance(item, dict) and item.get("id") in required
        ],
        key=lambda item: str(item.get("id")),
    )


def _independent_artifact_receipts(run_dir: Path, verification: dict) -> list[dict]:
    receipts = []
    questions = verification.get("questions", [])
    for question in questions if isinstance(questions, list) else []:
        agreement = question.get("independent_agreement", {}) if isinstance(question, dict) else {}
        comparisons = agreement.get("comparisons", []) if isinstance(agreement, dict) else []
        for comparison in comparisons if isinstance(comparisons, list) else []:
            if not isinstance(comparison, dict):
                continue
            relative = comparison.get("reference_artifact", "")
            path = _safe_run_path(run_dir, relative)
            receipts.append({"path": relative, "sha256": sha256_file(path) if path is not None and path.is_file() else None})
    return receipts


def _stage_scope_payload(
    run_dir: Path, stage: str, data: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    results = data["results.json"]
    verification = data["verification_report.json"]
    if stage == "READING":
        payload = {
            "source_manifest": data["source_manifest.json"],
            "source_audit": data["source_audit.json"],
            "problem_contract": data["problem_contract.json"],
        }
    elif stage == "MODEL_DRAFT":
        payload = {
            "assumptions": data["assumption_ledger.json"],
            "model_plan": data["model_plan.json"],
        }
    elif stage == "CODE_RUN":
        payload = {
            "results": _results_without_statuses(results),
            "result_artifacts": _result_artifact_receipts(run_dir, results),
        }
    elif stage == "P0_PASS":
        result_questions = results.get("questions", [])
        payload = {
            "p0_checks": verification.get("p0_checks", []),
            "constraints": [
                {"id": row.get("id"), "constraints": row.get("constraints", [])}
                for row in result_questions
                if isinstance(row, dict)
            ],
        }
    elif stage == "P1_PASS":
        payload = {
            "p1_checks": verification.get("p1_checks", []),
            "question_verification": verification.get("questions", []),
            "verified_results": results,
            "result_artifacts": _result_artifact_receipts(run_dir, results),
            "independent_artifacts": _independent_artifact_receipts(run_dir, verification),
        }
    elif stage == "PAPER_LINKED":
        claims = data["claim_ledger.json"]
        paper_receipts = []
        for key in ("paper_artifact", "paper_source_artifact"):
            relative = claims.get(key, "")
            path = _safe_run_path(run_dir, relative)
            paper_receipts.append(
                {
                    "kind": key,
                    "path": relative,
                    "sha256": sha256_file(path)
                    if path is not None and path.is_file()
                    else None,
                }
            )
        payload = {"claims": claims, "paper_receipts": paper_receipts}
    else:
        raise WorkflowError(f"No stage scope for {stage}")
    return payload


def _stage_scope_sha256(
    run_dir: Path, stage: str, data: dict[str, dict[str, Any]]
) -> str:
    return _canonical_sha256(_stage_scope_payload(run_dir, stage, data))


def _stage_fingerprint(
    run_dir: Path, stage: str, data: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    scope_sha256 = _stage_scope_sha256(run_dir, stage, data)
    signed_payload = {
        "scope_sha256": scope_sha256,
        "human_signoffs": _stage_signoffs(data, stage),
    }
    return {
        "version": 1,
        "stage": stage,
        "scope_sha256": scope_sha256,
        "sha256": _canonical_sha256(signed_payload),
    }


def initialize_run(
    output_dir: Path,
    problem: Path,
    attachments: list[Path],
    title: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise WorkflowError(f"Refusing to initialize a non-empty directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    sources_dir = output_dir / "sources"
    artifacts_dir = output_dir / "artifacts"
    paper_dir = output_dir / "paper"
    sources_dir.mkdir()
    artifacts_dir.mkdir()
    paper_dir.mkdir()

    sources: list[dict[str, Any]] = []
    frozen_problem = sources_dir / f"problem__{problem.name}"
    problem_row = _copy_source(problem, frozen_problem)
    problem_row.update({"source_id": "problem", "role": "problem"})
    problem_row["frozen_path"] = str(frozen_problem.relative_to(output_dir))
    sources.append(problem_row)

    for index, attachment in enumerate(attachments, start=1):
        frozen = sources_dir / f"attachment_{index:02d}__{attachment.name}"
        row = _copy_source(attachment, frozen)
        row.update({"source_id": f"attachment-{index:02d}", "role": "attachment"})
        row["frozen_path"] = str(frozen.relative_to(output_dir))
        sources.append(row)

    created_at = now_iso()
    stable_run_id = run_id or f"{_slug(title)}-{created_at[:10]}"
    manifest = {
        "schema_version": "1.0",
        "run_id": stable_run_id,
        "created_at": created_at,
        "sources": sources,
    }
    write_json(output_dir / "source_manifest.json", manifest)
    write_json(
        output_dir / "source_audit.json",
        build_source_audit(output_dir, manifest, generated_at=created_at),
    )

    problem_contract = {
        "schema_version": "1.0",
        "run_id": stable_run_id,
        "title": title,
        "problem_interpretation": "",
        "official_outputs": [],
        "questions": [
            {
                "id": "Q1",
                "source_locator": "",
                "objective": "",
                "inputs": [],
                "outputs": [],
                "decision_variables": [],
                "hard_constraints": [],
                "units": [],
                "ambiguities": [],
                "termination_condition": "",
            }
        ],
    }
    assumptions = {
        "schema_version": "1.0",
        "run_id": stable_run_id,
        "items": [],
    }
    model_plan = {
        "schema_version": "1.0",
        "run_id": stable_run_id,
        "questions": [],
    }
    results = {
        "schema_version": "1.0",
        "run_id": stable_run_id,
        "questions": [],
    }
    verification = {
        "schema_version": "1.0",
        "run_id": stable_run_id,
        "p0_checks": [],
        "p1_checks": [],
        "questions": [],
    }
    claims = {
        "schema_version": "1.0",
        "run_id": stable_run_id,
        "paper_artifact": "",
        "paper_source_artifact": "",
        "claims": [],
    }
    signoffs = {
        "schema_version": "1.0",
        "run_id": stable_run_id,
        "items": [
            {
                "id": signoff_id,
                "label": label,
                "required_by_stage": required_stage,
                "status": "PENDING",
                "reviewer": "",
                "reviewer_type": "human",
                "evidence": "",
                "approved_at": "",
                "scope_sha256": "",
            }
            for signoff_id, required_stage, label in SIGNOFF_REQUIREMENTS
        ],
    }
    state = {
        "schema_version": "1.0",
        "run_id": stable_run_id,
        "title": title,
        "created_at": created_at,
        "stage": "READING",
        "history": [
            {
                "event": "initialized",
                "stage": "READING",
                "at": created_at,
                "note": "Problem and attachments frozen before semantic modeling.",
            }
        ],
    }
    for name, payload in (
        ("problem_contract.json", problem_contract),
        ("assumption_ledger.json", assumptions),
        ("model_plan.json", model_plan),
        ("results.json", results),
        ("verification_report.json", verification),
        ("claim_ledger.json", claims),
        ("signoff_ledger.json", signoffs),
        ("state.json", state),
    ):
        write_json(output_dir / name, payload)
    (paper_dir / ".gitkeep").write_text("", encoding="utf-8")
    (artifacts_dir / ".gitkeep").write_text("", encoding="utf-8")
    return {
        "run_dir": str(output_dir),
        "run_id": stable_run_id,
        "stage": "READING",
        "source_count": len(sources),
    }


def _add_check(
    checks: list[dict[str, Any]], check_id: str, passed: bool, evidence: str
) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "evidence": evidence})


def _load_run(run_dir: Path) -> dict[str, dict[str, Any]]:
    names = (
        "state.json",
        "source_manifest.json",
        "problem_contract.json",
        "assumption_ledger.json",
        "model_plan.json",
        "results.json",
        "verification_report.json",
        "claim_ledger.json",
    )
    data = {name: read_json(run_dir / name) for name in names}
    audit_path = run_dir / "source_audit.json"
    data["source_audit.json"] = (
        read_json(audit_path)
        if audit_path.is_file()
        else {
            "schema_version": "1.0",
            "run_id": data["state.json"].get("run_id"),
            "sources": [],
        }
    )
    signoff_path = run_dir / "signoff_ledger.json"
    data["signoff_ledger.json"] = (
        read_json(signoff_path)
        if signoff_path.is_file()
        else {
            "schema_version": "1.0",
            "run_id": data["state.json"].get("run_id"),
            "items": [],
        }
    )
    return data


def _question_ids(contract: dict[str, Any]) -> list[str]:
    questions = contract.get("questions", [])
    if not isinstance(questions, list):
        return []
    return [str(item.get("id", "")) for item in questions if isinstance(item, dict)]


def validate_run(run_dir: Path, target_stage: str | None = None) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    data = _load_run(run_dir)
    state = data["state.json"]
    current_stage = state.get("stage")
    target = target_stage or current_stage
    if current_stage not in STAGES:
        raise WorkflowError(f"Invalid current stage: {current_stage!r}")
    if target not in STAGES:
        raise WorkflowError(f"Invalid target stage: {target!r}")

    checks: list[dict[str, Any]] = []
    run_ids = {payload.get("run_id") for payload in data.values()}
    _add_check(
        checks,
        "CORE-RUN-ID",
        len(run_ids) == 1 and None not in run_ids,
        f"run_ids={sorted(str(value) for value in run_ids)}",
    )

    snapshot_failures = []
    history = state.get("history", [])
    if not isinstance(history, list):
        snapshot_failures.append("history_not_list")
        history = []
    for index, event in enumerate(history):
        if not isinstance(event, dict):
            snapshot_failures.append(f"history-{index}:not-object")
            continue
        if event.get("event") != "advanced":
            continue
        frozen_stage = event.get("from")
        expected = event.get("stage_fingerprint", {})
        if frozen_stage not in STAGES[:-2] or not isinstance(expected, dict):
            snapshot_failures.append(f"history-{index}:fingerprint_missing")
            continue
        actual = _stage_fingerprint(run_dir, frozen_stage, data)
        if expected.get("sha256") != actual["sha256"]:
            snapshot_failures.append(f"{frozen_stage}:content_changed")
    _add_check(
        checks,
        "CORE-UPSTREAM-FREEZE",
        not snapshot_failures,
        f"failures={snapshot_failures}",
    )

    manifest = data["source_manifest.json"]
    source_rows = manifest.get("sources", [])
    source_ok = isinstance(source_rows, list) and bool(source_rows)
    source_evidence = []
    for row in source_rows if isinstance(source_rows, list) else []:
        if not isinstance(row, dict):
            source_ok = False
            source_evidence.append("malformed-row")
            continue
        path = _safe_run_path(run_dir, row.get("frozen_path", ""))
        ok = (
            path is not None
            and path.is_file()
            and path.stat().st_size == row.get("bytes")
            and sha256_file(path) == row.get("sha256")
        )
        source_ok &= ok
        source_evidence.append(f"{row.get('source_id')}:{'ok' if ok else 'mismatch'}")
    _add_check(
        checks,
        "G0-SOURCE-FREEZE",
        source_ok,
        ", ".join(source_evidence) or "no sources",
    )

    source_map = {
        row.get("source_id"): row
        for row in source_rows
        if isinstance(row, dict) and row.get("source_id")
    }
    audit = data["source_audit.json"]
    audit_rows = audit.get("sources", [])
    audit_map = {
        row.get("source_id"): row
        for row in audit_rows
        if isinstance(row, dict) and row.get("source_id")
    }
    audit_failures = []
    if not isinstance(audit_rows, list):
        audit_failures.append("sources_not_list")
    for source_id, source in source_map.items():
        row = audit_map.get(source_id, {})
        if not row:
            audit_failures.append(f"{source_id}:missing")
            continue
        if row.get("source_sha256") != source.get("sha256"):
            audit_failures.append(f"{source_id}:source_hash_drift")
        if row.get("frozen_path") != source.get("frozen_path"):
            audit_failures.append(f"{source_id}:source_path_drift")
        status = row.get("parse_status")
        if status == "MANUAL_REQUIRED":
            manual = row.get("manual_review", {})
            if (
                not isinstance(manual, dict)
                or manual.get("completed") is not True
                or not _nonempty(manual.get("evidence"))
            ):
                audit_failures.append(f"{source_id}:manual_review_incomplete")
        elif status != "PASS":
            audit_failures.append(f"{source_id}:parse_{status or 'missing'}")

        text_artifact = row.get("text_artifact")
        if text_artifact:
            text_path = _safe_run_path(run_dir, text_artifact)
            if (
                text_path is None
                or not text_path.is_file()
                or sha256_file(text_path) != row.get("text_artifact_sha256")
            ):
                audit_failures.append(f"{source_id}:text_artifact_mismatch")
        if source.get("role") == "problem" and status == "PASS":
            if not text_artifact or not _nonempty(row.get("character_count")):
                audit_failures.append(f"{source_id}:problem_text_missing")
        if row.get("detected_format") in {"xlsx", "xlsm"} and status == "PASS":
            sheets = row.get("sheets", [])
            if not isinstance(sheets, list) or not sheets:
                audit_failures.append(f"{source_id}:workbook_sheets_missing")
            else:
                for sheet in sheets:
                    if not isinstance(sheet, dict) or not isinstance(sheet.get("profile"), dict) or sheet["profile"].get("scan_complete") is not True:
                        audit_failures.append(f"{source_id}:full_scan_missing")
                    elif sheet.get("unresolved_shared_strings", 0) > 0:
                        audit_failures.append(f"{source_id}:unresolved_strings")
        if row.get("detected_format") in {"csv", "tsv"} and status == "PASS":
            if not isinstance(row.get("row_count"), int) or row.get("row_count", 0) < 1:
                audit_failures.append(f"{source_id}:table_rows_missing")
            if not isinstance(row.get("profile"), dict) or row["profile"].get("scan_complete") is not True:
                audit_failures.append(f"{source_id}:full_scan_missing")
    audit_ok = (
        audit.get("run_id") == state.get("run_id")
        and set(audit_map) == set(source_map)
        and len(audit_rows) == len(source_rows)
        and not audit_failures
    )
    _add_check(
        checks,
        "G0-SOURCE-AUDIT",
        audit_ok,
        f"audited={sorted(audit_map)}; failures={audit_failures}",
    )

    target_index = STAGES.index(target)

    signoff_items = data["signoff_ledger.json"].get("items", [])
    signoff_map = {
        item.get("id"): item
        for item in signoff_items
        if isinstance(item, dict) and item.get("id")
    }
    required_signoffs = [
        (signoff_id, required_stage)
        for signoff_id, required_stage, _ in SIGNOFF_REQUIREMENTS
        if target_index >= STAGES.index(required_stage)
    ]
    signoff_failures = []
    for signoff_id, required_stage in required_signoffs:
        item = signoff_map.get(signoff_id, {})
        if item.get("required_by_stage") != required_stage:
            signoff_failures.append(f"{signoff_id}:stage_drift")
        if item.get("status") != "APPROVED":
            signoff_failures.append(f"{signoff_id}:not_approved")
        if item.get("reviewer_type") != "human":
            signoff_failures.append(f"{signoff_id}:reviewer_not_human")
        for field in ("reviewer", "evidence", "approved_at"):
            if not _nonempty(item.get(field)):
                signoff_failures.append(f"{signoff_id}:{field}_missing")
        expected_scope = _stage_scope_sha256(run_dir, required_stage, data)
        if item.get("scope_sha256") != expected_scope:
            signoff_failures.append(f"{signoff_id}:scope_mismatch")
    _add_check(
        checks,
        "HUMAN-SIGNOFFS",
        isinstance(signoff_items, list) and not signoff_failures,
        f"required={[item[0] for item in required_signoffs]}; failures={signoff_failures}",
    )

    contract = data["problem_contract.json"]
    question_ids = _question_ids(contract)

    if target_index >= STAGES.index("READING"):
        required_top = ("title", "problem_interpretation", "official_outputs", "questions")
        top_ok = all(_nonempty(contract.get(field)) for field in required_top)
        _add_check(
            checks,
            "G1-CONTRACT-TOP",
            top_ok,
            "required=" + ",".join(required_top),
        )
        question_required = (
            "id",
            "source_locator",
            "objective",
            "inputs",
            "outputs",
            "decision_variables",
            "hard_constraints",
            "units",
            "ambiguities",
            "termination_condition",
        )
        malformed = []
        questions = contract.get("questions", [])
        for index, question in enumerate(questions if isinstance(questions, list) else []):
            if not isinstance(question, dict):
                malformed.append(f"row-{index}:not-object")
                continue
            missing = [field for field in question_required if not _nonempty(question.get(field))]
            if missing:
                malformed.append(f"{question.get('id', index)}:{','.join(missing)}")
        questions_ok = bool(question_ids) and _unique(question_ids) and not malformed
        _add_check(
            checks,
            "G1-QUESTION-CONTRACTS",
            questions_ok,
            f"question_ids={question_ids}; malformed={malformed}",
        )

    if target_index >= STAGES.index("MODEL_DRAFT"):
        assumptions = data["assumption_ledger.json"].get("items", [])
        assumption_required = ("id", "text", "evidence", "impact", "status")
        bad_assumptions = []
        for index, item in enumerate(assumptions if isinstance(assumptions, list) else []):
            if not isinstance(item, dict):
                bad_assumptions.append(f"row-{index}:not-object")
                continue
            missing = [field for field in assumption_required if not _nonempty(item.get(field))]
            if missing:
                bad_assumptions.append(f"{item.get('id', index)}:{','.join(missing)}")
        assumption_ids = [item.get("id") for item in assumptions if isinstance(item, dict)]
        assumptions_ok = bool(assumption_ids) and _unique(assumption_ids) and not bad_assumptions
        _add_check(
            checks,
            "G2-ASSUMPTION-LEDGER",
            assumptions_ok,
            f"count={len(assumption_ids)}; malformed={bad_assumptions}",
        )

        plans = data["model_plan.json"].get("questions", [])
        plan_map = {
            item.get("id"): item for item in plans if isinstance(item, dict) and item.get("id")
        }
        bad_plans = []
        plan_required = (
            "id",
            "baseline",
            "observed_bottleneck",
            "primary_method",
            "independent_method",
            "validation_plan",
        )
        for question_id in question_ids:
            plan = plan_map.get(question_id, {})
            missing = [field for field in plan_required if not _nonempty(plan.get(field))]
            if plan.get("primary_method") == plan.get("independent_method") and _nonempty(
                plan.get("primary_method")
            ):
                missing.append("independent_method_must_differ")
            if missing:
                bad_plans.append(f"{question_id}:{','.join(missing)}")
            if not _valid_tolerance(plan.get("agreement_tolerance")):
                bad_plans.append(f"{question_id}:missing_agreement_tolerance")
        plans_ok = set(plan_map) == set(question_ids) and not bad_plans
        _add_check(
            checks,
            "G2-MODEL-PLAN",
            plans_ok,
            f"planned={sorted(plan_map)}; malformed={bad_plans}",
        )

    result_questions = data["results.json"].get("questions", [])
    result_map = {
        item.get("id"): item
        for item in result_questions
        if isinstance(item, dict) and item.get("id")
    }
    result_ids: dict[str, dict[str, Any]] = {}

    if target_index >= STAGES.index("CODE_RUN"):
        bad_results = []
        for question_id in question_ids:
            result = result_map.get(question_id, {})
            status = result.get("status")
            headlines = result.get("headline_results", [])
            if status not in RESULT_STATUSES:
                bad_results.append(f"{question_id}:invalid_status")
            if not isinstance(headlines, list) or not headlines:
                bad_results.append(f"{question_id}:no_headlines")
                continue
            for row in headlines:
                if not isinstance(row, dict):
                    bad_results.append(f"{question_id}:headline_not_object")
                    continue
                missing = [
                    field
                    for field in ("id", "label", "value", "unit", "source_artifact", "status")
                    if not _nonempty(row.get(field))
                ]
                artifact = _safe_run_path(run_dir, row.get("source_artifact", ""))
                if artifact is None or not artifact.is_file():
                    missing.append("source_artifact_missing")
                else:
                    try:
                        actual_value = _json_pointer(read_json(artifact), row.get("source_pointer"))
                        if not _same_result_value(actual_value, row.get("value")):
                            missing.append("value_differs_from_source")
                    except (WorkflowError, UnicodeError, OSError):
                        missing.append("source_value_unreadable")
                if row.get("status") not in RESULT_STATUSES:
                    missing.append("invalid_status")
                row_id = row.get("id")
                if row_id in result_ids:
                    missing.append("duplicate_result_id")
                elif row_id:
                    result_ids[row_id] = row
                if missing:
                    bad_results.append(f"{row.get('id', question_id)}:{','.join(missing)}")
        results_ok = set(result_map) == set(question_ids) and not bad_results
        _add_check(
            checks,
            "G4-RESULT-LEDGER",
            results_ok,
            f"questions={sorted(result_map)}; malformed={bad_results}",
        )

    verification = data["verification_report.json"]
    if target_index >= STAGES.index("P0_PASS"):
        p0_checks = verification.get("p0_checks", [])
        p0_ok = isinstance(p0_checks, list) and bool(p0_checks) and all(
            item.get("passed") is True and _nonempty(item.get("id")) and _nonempty(item.get("evidence"))
            for item in p0_checks
            if isinstance(item, dict)
        ) and len(p0_checks) == sum(isinstance(item, dict) for item in p0_checks)
        _add_check(
            checks,
            "P0-AUDIT",
            p0_ok,
            f"checks={len(p0_checks) if isinstance(p0_checks, list) else 0}",
        )
        constraint_failures = []
        status_failures = []
        for question_id in question_ids:
            result = result_map.get(question_id, {})
            constraints = result.get("constraints", [])
            if not isinstance(constraints, list) or not constraints:
                constraint_failures.append(f"{question_id}:no_constraint_checks")
            else:
                for constraint in constraints:
                    if not isinstance(constraint, dict):
                        constraint_failures.append(f"{question_id}:malformed_constraint")
                        continue
                    if constraint.get("passed") is not True or not _nonempty(
                        constraint.get("evidence")
                    ):
                        constraint_failures.append(
                            f"{question_id}:{constraint.get('id', 'unnamed')}"
                        )
            if result.get("status") not in {"PROVISIONAL", "VERIFIED"}:
                status_failures.append(f"{question_id}:{result.get('status')}")
        _add_check(
            checks,
            "P0-CONSTRAINTS",
            not constraint_failures,
            f"failures={constraint_failures}",
        )
        _add_check(
            checks,
            "P0-RESULT-STATUS",
            not status_failures,
            f"failures={status_failures}",
        )

    p1_warns: list[dict[str, Any]] = []
    if target_index >= STAGES.index("P1_PASS"):
        p1_checks = verification.get("p1_checks", [])
        malformed_p1 = []
        p1_fails = []
        for index, item in enumerate(p1_checks if isinstance(p1_checks, list) else []):
            if not isinstance(item, dict):
                malformed_p1.append(f"row-{index}:not-object")
                continue
            verdict = item.get("verdict")
            if verdict not in P1_VERDICTS or not _nonempty(item.get("id")) or not _nonempty(
                item.get("evidence")
            ):
                malformed_p1.append(str(item.get("id", index)))
            elif verdict == "FAIL":
                p1_fails.append(item.get("id"))
            elif verdict == "WARN":
                p1_warns.append(item)
                if not _nonempty(item.get("allowed_language")):
                    malformed_p1.append(f"{item.get('id')}:missing_allowed_language")
                question_scope = item.get("question_ids", question_ids)
                forbidden_terms = item.get("forbidden_terms", STRONG_TERMS)
                if not isinstance(question_scope, list):
                    malformed_p1.append(f"{item.get('id')}:question_ids_not_list")
                if not isinstance(forbidden_terms, (list, tuple)) or not all(
                    isinstance(term, str) for term in forbidden_terms
                ):
                    malformed_p1.append(f"{item.get('id')}:forbidden_terms_not_strings")
        p1_ok = bool(p1_checks) and not malformed_p1 and not p1_fails
        _add_check(
            checks,
            "P1-AUDIT",
            p1_ok,
            f"fails={p1_fails}; malformed={malformed_p1}; warns={len(p1_warns)}",
        )

        question_verifications = verification.get("questions", [])
        verification_map = {
            item.get("id"): item
            for item in question_verifications
            if isinstance(item, dict) and item.get("id")
        }
        bad_verification = []
        for question_id in question_ids:
            item = verification_map.get(question_id, {})
            anchors = item.get("anchors", [])
            if not isinstance(anchors, list):
                anchors = []
            anchor_types = {
                anchor.get("type") for anchor in anchors if isinstance(anchor, dict)
            }
            if len(anchors) < 2:
                bad_verification.append(f"{question_id}:fewer_than_two_anchors")
            if not anchor_types.intersection(ANCHOR_TYPES):
                bad_verification.append(f"{question_id}:no_hard_anchor")
            agreement = item.get("independent_agreement", {})
            if not isinstance(agreement, dict) or agreement.get("passed") is not True:
                bad_verification.append(f"{question_id}:independent_check_failed")
            plan = next(
                (
                    row
                    for row in data["model_plan.json"].get("questions", [])
                    if isinstance(row, dict) and row.get("id") == question_id
                ),
                {},
            )
            if item.get("independent_method") != plan.get("independent_method"):
                bad_verification.append(f"{question_id}:independent_method_drift")
            result = result_map.get(question_id, {})
            bad_verification.extend(f"{question_id}:{failure}" for failure in
                                    _verify_comparisons(run_dir, result, agreement, plan.get("agreement_tolerance")))
            if result.get("status") != "VERIFIED":
                bad_verification.append(f"{question_id}:result_not_verified")
            headlines = result.get("headline_results", [])
            for headline in headlines if isinstance(headlines, list) else []:
                if not isinstance(headline, dict):
                    bad_verification.append(f"{question_id}:headline_not_object")
                    continue
                if headline.get("status") != "VERIFIED":
                    bad_verification.append(f"{headline.get('id')}:headline_not_verified")
        _add_check(
            checks,
            "P1-INDEPENDENT-VERIFICATION",
            set(verification_map) == set(question_ids) and not bad_verification,
            f"failures={bad_verification}",
        )

    if target_index >= STAGES.index("PAPER_LINKED"):
        claims_data = data["claim_ledger.json"]
        paper_path = _safe_run_path(run_dir, claims_data.get("paper_artifact", ""))
        paper_source_path = _safe_run_path(
            run_dir, claims_data.get("paper_source_artifact", "")
        )
        _add_check(
            checks,
            "G5-PAPER-ARTIFACT",
            paper_path is not None
            and paper_path.is_file()
            and paper_path.stat().st_size > 0
            and paper_source_path is not None
            and paper_source_path.is_file()
            and paper_source_path.stat().st_size > 0,
            (
                f"paper={claims_data.get('paper_artifact')}; "
                f"source={claims_data.get('paper_source_artifact')}"
            ),
        )
        claims = claims_data.get("claims", [])
        bad_claims = []
        paper_source_text = ""
        if paper_source_path is not None and paper_source_path.is_file():
            try:
                paper_source_text = paper_source_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                bad_claims.append("paper_source:not_utf8_text")
        normalized_paper = re.sub(r"\s+", "", paper_source_text)
        for index, claim in enumerate(claims if isinstance(claims, list) else []):
            if not isinstance(claim, dict):
                bad_claims.append(f"row-{index}:not-object")
                continue
            claim_id = claim.get("id", index)
            if claim.get("status") != "VERIFIED":
                bad_claims.append(f"{claim_id}:not_verified")
            if claim.get("question_id") not in question_ids:
                bad_claims.append(f"{claim_id}:unknown_question")
            if not _nonempty(claim.get("paper_locator")):
                bad_claims.append(f"{claim_id}:no_locator")
            excerpt = str(claim.get("paper_excerpt", ""))
            if not excerpt.strip():
                bad_claims.append(f"{claim_id}:no_paper_excerpt")
            elif re.sub(r"\s+", "", excerpt) not in normalized_paper:
                bad_claims.append(f"{claim_id}:excerpt_not_found")
            linked = claim.get("result_ids", [])
            if not isinstance(linked, list) or not linked:
                bad_claims.append(f"{claim_id}:no_result_links")
            else:
                for result_id in linked:
                    if result_id not in result_ids:
                        bad_claims.append(f"{claim_id}:unknown_result:{result_id}")
                    elif result_ids[result_id].get("status") != "VERIFIED":
                        bad_claims.append(f"{claim_id}:unverified_result:{result_id}")
            text = str(claim.get("text", "")) + " " + excerpt
            for warning in p1_warns:
                applies = warning.get("question_ids", question_ids)
                forbidden = warning.get("forbidden_terms", STRONG_TERMS)
                if not isinstance(applies, list):
                    applies = question_ids
                if not isinstance(forbidden, (list, tuple)):
                    forbidden = STRONG_TERMS
                if claim.get("question_id") in applies:
                    hits = [
                        term
                        for term in forbidden
                        if isinstance(term, str) and term.lower() in text.lower()
                    ]
                    if hits:
                        bad_claims.append(f"{claim_id}:warn_forbidden_terms:{hits}")
        _add_check(
            checks,
            "G5-CLAIM-LEDGER",
            isinstance(claims, list) and bool(claims) and not bad_claims,
            f"claims={len(claims) if isinstance(claims, list) else 0}; failures={bad_claims}",
        )

    if target_index >= STAGES.index("VERIFIED"):
        manifest_path = run_dir / "artifact_manifest.json"
        manifest_ok = manifest_path.is_file()
        manifest_evidence = "missing"
        if manifest_ok:
            artifact_manifest = read_json(manifest_path)
            rows = artifact_manifest.get("artifacts", [])
            rows_are_list = isinstance(rows, list)
            canonical = []
            failures = []
            for row in rows if rows_are_list else []:
                if not isinstance(row, dict):
                    failures.append("malformed-row")
                    continue
                path = _safe_run_path(run_dir, row.get("path", ""))
                ok = (
                    path is not None
                    and path.is_file()
                    and path.stat().st_size == row.get("bytes")
                    and sha256_file(path) == row.get("sha256")
                )
                if not ok:
                    failures.append(row.get("path"))
                canonical.append(f"{row.get('path')}\t{row.get('sha256')}\n")
            package_digest = hashlib.sha256("".join(canonical).encode("utf-8")).hexdigest()
            declared_digest = artifact_manifest.get("package_digest", {})
            if not isinstance(declared_digest, dict):
                declared_digest = {}
            manifest_ok = (
                rows_are_list
                and bool(rows)
                and not failures
                and artifact_manifest.get("run_id") == state.get("run_id")
                and declared_digest.get("artifact_count") == len(rows)
                and package_digest == declared_digest.get("sha256")
            )
            manifest_evidence = (
                f"artifacts={len(rows) if rows_are_list else 0}; failures={failures}; "
                f"package_sha256={package_digest}"
            )
        _add_check(checks, "FINAL-ARTIFACT-MANIFEST", manifest_ok, manifest_evidence)

    failed = [item["id"] for item in checks if not item["passed"]]
    return {
        "schema_version": "1.0",
        "run_id": state.get("run_id"),
        "current_stage": current_stage,
        "target_stage": target,
        "passed": not failed,
        "failed_checks": failed,
        "checks": checks,
    }


def advance_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    state_path = run_dir / "state.json"
    state = read_json(state_path)
    current = state.get("stage")
    if current not in STAGES:
        raise WorkflowError(f"Invalid current stage: {current!r}")
    if current == "VERIFIED":
        raise WorkflowError("Run is already VERIFIED")
    if current == "PAPER_LINKED":
        raise WorkflowError("Use the seal command to enter VERIFIED")
    report = validate_run(run_dir, current)
    if not report["passed"]:
        raise WorkflowError(
            f"Cannot advance from {current}; failed checks: {report['failed_checks']}"
        )
    next_stage = STAGES[STAGES.index(current) + 1]
    fingerprint = _stage_fingerprint(run_dir, current, _load_run(run_dir))
    state["stage"] = next_stage
    state.setdefault("history", []).append(
        {
            "event": "advanced",
            "from": current,
            "stage": next_stage,
            "at": now_iso(),
            "validated_checks": [item["id"] for item in report["checks"]],
            "stage_fingerprint": fingerprint,
        }
    )
    write_json(state_path, state)
    return {"run_id": state["run_id"], "from": current, "stage": next_stage}


def audit_run_sources(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    state = read_json(run_dir / "state.json")
    if state.get("stage") != "READING":
        raise WorkflowError("Source inspection may be regenerated only at READING")
    manifest = read_json(run_dir / "source_manifest.json")
    try:
        audit = build_source_audit(run_dir, manifest, generated_at=now_iso())
    except ValueError as exc:
        raise WorkflowError(str(exc)) from exc
    write_json(run_dir / "source_audit.json", audit)
    report = validate_run(run_dir, "READING")
    audit_passed = next(
        item["passed"]
        for item in report["checks"]
        if item["id"] == "G0-SOURCE-AUDIT"
    )
    return {
        "run_id": state.get("run_id"),
        "source_count": len(audit.get("sources", [])),
        "passed": audit_passed,
        "audit_passed": audit_passed,
        "summary": audit.get("summary", {}),
    }


def signoff_status(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    data = _load_run(run_dir)
    state = data["state.json"]
    items = data["signoff_ledger.json"].get("items", [])
    signoff_map = {
        item.get("id"): item
        for item in items
        if isinstance(item, dict) and item.get("id")
    }
    rows = []
    for signoff_id, required_stage, label in SIGNOFF_REQUIREMENTS:
        item = signoff_map.get(signoff_id, {})
        expected = _stage_scope_sha256(run_dir, required_stage, data)
        rows.append(
            {
                "id": signoff_id,
                "label": label,
                "required_by_stage": required_stage,
                "status": item.get("status", "MISSING"),
                "reviewer": item.get("reviewer", ""),
                "expected_scope_sha256": expected,
                "recorded_scope_sha256": item.get("scope_sha256", ""),
                "scope_matches": item.get("scope_sha256") == expected,
            }
        )
    return {"run_id": state.get("run_id"), "stage": state.get("stage"), "signoffs": rows}


def _iter_artifacts(run_dir: Path) -> list[Path]:
    ignored_names = {"artifact_manifest.json"}
    return sorted(
        (
            path
            for path in run_dir.rglob("*")
            if path.is_file()
            and path.name not in ignored_names
            and "__pycache__" not in path.parts
            and path.name != ".DS_Store"
        ),
        key=lambda path: path.relative_to(run_dir).as_posix(),
    )


def seal_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    state_path = run_dir / "state.json"
    state = read_json(state_path)
    if state.get("stage") != "PAPER_LINKED":
        raise WorkflowError("A run can be sealed only from PAPER_LINKED")
    report = validate_run(run_dir, "PAPER_LINKED")
    if not report["passed"]:
        raise WorkflowError(f"Cannot seal; failed checks: {report['failed_checks']}")
    write_json(run_dir / "final_validation.json", report)

    state["stage"] = "VERIFIED"
    state.setdefault("history", []).append(
        {
            "event": "sealed",
            "from": "PAPER_LINKED",
            "stage": "VERIFIED",
            "at": now_iso(),
            "note": "All accumulated gates passed before artifact hashing.",
        }
    )
    write_json(state_path, state)

    rows = []
    canonical = []
    for path in _iter_artifacts(run_dir):
        relative = path.relative_to(run_dir).as_posix()
        digest = sha256_file(path)
        rows.append({"path": relative, "sha256": digest, "bytes": path.stat().st_size})
        canonical.append(f"{relative}\t{digest}\n")
    package_digest = hashlib.sha256("".join(canonical).encode("utf-8")).hexdigest()
    artifact_manifest = {
        "schema_version": "1.0",
        "run_id": state["run_id"],
        "sealed_at": state["history"][-1]["at"],
        "scope_note": (
            "Binds the run artifacts and passed gates. It certifies traceability and "
            "the declared checks, not an award outcome or universal model correctness."
        ),
        "package_digest": {
            "algorithm": "sha256",
            "canonicalization": (
                "Sort relative paths. Hash UTF-8 lines <path>\\t<sha256>\\n. "
                "Exclude artifact_manifest.json."
            ),
            "artifact_count": len(rows),
            "sha256": package_digest,
        },
        "artifacts": rows,
    }
    write_json(run_dir / "artifact_manifest.json", artifact_manifest)
    final_check = validate_run(run_dir, "VERIFIED")
    if not final_check["passed"]:
        raise WorkflowError(
            "Artifact manifest failed its own verification: "
            + ", ".join(final_check["failed_checks"])
        )
    return {
        "run_id": state["run_id"],
        "stage": "VERIFIED",
        "artifact_count": len(rows),
        "package_sha256": package_digest,
    }


def status_run(run_dir: Path) -> dict[str, Any]:
    state = read_json(run_dir.resolve() / "state.json")
    report = validate_run(run_dir, state.get("stage"))
    return {
        "run_id": state.get("run_id"),
        "title": state.get("title"),
        "stage": state.get("stage"),
        "stage_passed": report["passed"],
        "failed_checks": report["failed_checks"],
        "next_action": (
            "sealed"
            if state.get("stage") == "VERIFIED"
            else "seal"
            if state.get("stage") == "PAPER_LINKED" and report["passed"]
            else "advance"
            if report["passed"]
            else "complete_failed_checks"
        ),
    }
