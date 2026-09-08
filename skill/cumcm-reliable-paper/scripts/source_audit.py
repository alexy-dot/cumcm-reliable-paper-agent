#!/usr/bin/env python3
"""Standard-library structural inspection for frozen contest sources."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import posixpath
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


TEXT_ENCODINGS = ("utf-8-sig", "gb18030")
MAX_TEXT_BYTES = 20 * 1024 * 1024
MAX_SHARED_STRINGS = 50_000
SAMPLE_ROWS = 6


class TableProfile:
    """Profile stored rows; first stored row is a header candidate, not inferred truth."""

    def __init__(self) -> None:
        self.rows = 0
        self.header: dict[int, str] = {}
        self.columns: dict[int, dict[str, Any]] = {}
        self.seen: set[bytes] = set()
        self.duplicates = 0

    def add(self, cells: dict[int, str]) -> None:
        self.rows += 1
        if self.rows == 1:
            self.header = cells.copy()
            for column in cells:
                self._column(column)
            return
        # Exact decoded text comparison; does not equate 1 with 1.0 or infer entity IDs.
        canonical = json.dumps(sorted((k, v) for k, v in cells.items() if v != ""),
                               ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).digest()
        self.duplicates += digest in self.seen
        self.seen.add(digest)
        for column, value in cells.items():
            stats = self._column(column)
            if not value.strip():
                continue
            stats["nonempty"] += 1
            try:
                number = float(value)
            except ValueError:
                stats["text_count"] += 1
                continue
            if not math.isfinite(number):
                stats["nonfinite_count"] += 1
                continue
            stats["numeric_count"] += 1
            stats["minimum"] = number if stats["minimum"] is None else min(stats["minimum"], number)
            stats["maximum"] = number if stats["maximum"] is None else max(stats["maximum"], number)
            # Convex update avoids overflow when finite observations have opposite signs.
            count = stats["numeric_count"]
            stats["mean"] = number if count == 1 else stats["mean"] * ((count - 1) / count) + number / count

    def _column(self, index: int) -> dict[str, Any]:
        return self.columns.setdefault(index, {
            "nonempty": 0, "numeric_count": 0, "text_count": 0,
            "nonfinite_count": 0, "minimum": None, "maximum": None, "mean": None,
        })

    def report(self) -> dict[str, Any]:
        data_rows = max(0, self.rows - 1)
        columns = [{"index": index, "header_candidate": self.header.get(index, ""),
                    **stats, "missing_count": data_rows - stats["nonempty"]}
                   for index, stats in sorted(self.columns.items())]
        return {
            "scan_complete": True, "stored_row_count": self.rows,
            "data_row_count": data_rows,
            "header_policy": "first stored row excluded as header candidate; confirm against problem",
            "row_policy": "stored rows only; absent worksheet row numbers are not fabricated observations",
            "duplicate_rows": self.duplicates,
            "duplicate_policy": "SHA-256 of exact decoded cell text, excluding empty cells; data rows only",
            "columns": columns,
            "findings": {
                "missing_cells": sum(row["missing_count"] for row in columns),
                "nonfinite_cells": sum(row["nonfinite_count"] for row in columns),
                "mixed_numeric_text_columns": sum(bool(row["numeric_count"] and row["text_count"]) for row in columns),
            },
            "numeric_policy": "float-parsable text; dates, units, identifiers and precision require interpretation",
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _decode_text(path: Path) -> tuple[str, str]:
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise ValueError(f"text file exceeds {MAX_TEXT_BYTES} bytes")
    raw = path.read_bytes()
    for encoding in TEXT_ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("text is neither UTF-8 nor GB18030")


def _audit_text(path: Path) -> dict[str, Any]:
    text, encoding = _decode_text(path)
    lines = text.splitlines()
    return {
        "encoding": encoding,
        "line_count": len(lines),
        "character_count": len(text),
        "preview": "\n".join(lines[:12])[:1200],
        "extracted_text": text,
    }


def _audit_csv(path: Path) -> dict[str, Any]:
    encoding = None
    for candidate in TEXT_ENCODINGS:
        try:
            with path.open("r", encoding=candidate, newline="") as stream:
                sample = stream.read(8192)
                # An ASCII prefix cannot determine the encoding of a later Chinese row.
                for _ in iter(lambda: stream.read(65536), ""):
                    pass
            encoding = candidate
            break
        except UnicodeDecodeError:
            continue
    if encoding is None:
        raise ValueError("CSV is neither UTF-8 nor GB18030")

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel

    rows = 0
    maximum_columns = 0
    ragged_rows = 0
    blank_cells = 0
    expected_columns = None
    samples: list[list[str]] = []
    profile = TableProfile()
    with path.open("r", encoding=encoding, newline="") as stream:
        reader = csv.reader(stream, dialect, strict=True)
        for row in reader:
            profile.add(dict(enumerate(row, start=1)))
            rows += 1
            maximum_columns = max(maximum_columns, len(row))
            if expected_columns is None:
                expected_columns = len(row)
            elif len(row) != expected_columns:
                ragged_rows += 1
            blank_cells += sum(not cell.strip() for cell in row)
            if len(samples) < SAMPLE_ROWS:
                samples.append(row[:50])
    if not rows or not maximum_columns:
        raise ValueError("CSV has no tabular rows")
    return {
        "encoding": encoding,
        "delimiter": dialect.delimiter,
        "row_count": rows,
        "maximum_columns": maximum_columns,
        "header": samples[0] if samples else [],
        "ragged_rows": ragged_rows,
        "blank_cells": blank_cells,
        "sample_rows": samples,
        "profile": profile.report(),
    }


def _audit_docx(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        member = "word/document.xml"
        if member not in archive.namelist():
            raise ValueError("DOCX has no word/document.xml")
        root = ET.parse(archive.open(member)).getroot()
    paragraphs = []
    for element in root.iter():
        if _local_name(element.tag) != "p":
            continue
        text = "".join(
            node.text or "" for node in element.iter() if _local_name(node.tag) == "t"
        ).strip()
        if text:
            paragraphs.append(text)
    extracted = "\n".join(paragraphs)
    if not extracted:
        raise ValueError("DOCX yielded no paragraph text")
    return {
        "paragraph_count": len(paragraphs),
        "character_count": len(extracted),
        "preview": "\n".join(paragraphs[:12])[:1200],
        "extracted_text": extracted + "\n",
        "coverage": "paragraph text only; diagrams, equation layout and embedded objects require original-document review",
    }


def _shared_strings(archive: zipfile.ZipFile) -> tuple[list[str], bool]:
    member = "xl/sharedStrings.xml"
    if member not in archive.namelist():
        return [], False
    values: list[str] = []
    truncated = False
    with archive.open(member) as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if _local_name(element.tag) != "si":
                continue
            values.append(
                "".join(
                    node.text or ""
                    for node in element.iter()
                    if _local_name(node.tag) == "t"
                )
            )
            element.clear()
            if len(values) > MAX_SHARED_STRINGS:
                values.pop()
                truncated = True
                break
    return values, truncated


def _column_number(cell_reference: str) -> int:
    match = re.match(r"([A-Za-z]+)", cell_reference)
    if not match:
        return 0
    value = 0
    for character in match.group(1).upper():
        value = value * 26 + ord(character) - ord("A") + 1
    return value


def _dimension_size(reference: str) -> tuple[int | None, int | None]:
    if not reference:
        return None, None
    final = reference.split(":")[-1]
    column = _column_number(final)
    match = re.search(r"(\d+)$", final)
    return (int(match.group(1)) if match else None, column or None)


def _cell_value(cell: ET.Element, shared: list[str]) -> tuple[str, bool]:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return (
            "".join(
                node.text or ""
                for node in cell.iter()
                if _local_name(node.tag) == "t"
            ),
            False,
        )
    value = next(
        (node.text or "" for node in cell if _local_name(node.tag) == "v"), ""
    )
    if cell_type == "s" and value:
        try:
            index = int(value)
        except ValueError:
            return value, True
        if 0 <= index < len(shared):
            return shared[index], False
        return f"<shared-string:{index}>", True
    if cell_type == "b":
        return ("TRUE" if value == "1" else "FALSE"), False
    return value, False


def _audit_worksheet(
    archive: zipfile.ZipFile, member: str, shared: list[str]
) -> dict[str, Any]:
    dimension = ""
    sampled_rows: list[dict[str, Any]] = []
    sampled_max_column = 0
    formula_cells = 0
    unresolved_shared_strings = 0
    profile = TableProfile()
    last_row = 0
    missing_formula_cache = 0
    error_cells = 0
    merged_ranges = []
    with archive.open(member) as stream:
        stack = []
        for event, element in ET.iterparse(stream, events=("start", "end")):
            if event == "start":
                stack.append(element)
                continue
            local = _local_name(element.tag)
            if local == "dimension":
                dimension = element.attrib.get("ref", "")
            elif local == "mergeCell":
                merged_ranges.append(element.attrib.get("ref", ""))
            elif local == "row":
                row_number = int(element.attrib.get("r", last_row + 1))
                if row_number <= last_row:
                    raise ValueError("worksheet row coordinates are duplicated or unordered")
                last_row = row_number
                cells: dict[str, str] = {}
                indexed = {}
                for cell in element:
                    if _local_name(cell.tag) != "c":
                        continue
                    reference = cell.attrib.get("r", "")
                    column = _column_number(reference) if reference else len(indexed) + 1
                    if column < 1 or column in indexed:
                        raise ValueError("invalid or duplicate worksheet column coordinate")
                    coordinate = re.fullmatch(r"([A-Za-z]+)([0-9]+)", reference) if reference else None
                    if reference and (coordinate is None or int(coordinate.group(2)) != row_number):
                        raise ValueError("cell coordinate does not match worksheet row")
                    sampled_max_column = max(
                        sampled_max_column, column
                    )
                    value, unresolved = _cell_value(cell, shared)
                    indexed[column] = value
                    unresolved_shared_strings += int(unresolved)
                    if any(_local_name(node.tag) == "f" for node in cell):
                        formula_cells += 1
                        missing_formula_cache += not any(_local_name(node.tag) == "v" and node.text is not None for node in cell)
                    error_cells += cell.attrib.get("t") == "e"
                    cells[reference or f"cell-{len(cells) + 1}"] = value
                profile.add(indexed)
                if len(sampled_rows) < SAMPLE_ROWS:
                    sampled_rows.append({"row": row_number, "cells": cells})
                # Release completed rows from their parent, not just their children.
                stack[-2].remove(element)
                element.clear()
            stack.pop()
    estimated_rows, estimated_columns = _dimension_size(dimension)
    return {
        "xml_member": member,
        "dimension": dimension or None,
        "estimated_rows": estimated_rows,
        "estimated_columns": estimated_columns or sampled_max_column or None,
        "header_cells": sampled_rows[0]["cells"] if sampled_rows else {},
        "sampled_rows": sampled_rows,
        "formula_cells": formula_cells,
        "formula_cache_missing": missing_formula_cache,
        "error_cells": error_cells,
        "unresolved_shared_strings": unresolved_shared_strings,
        "merged_ranges": merged_ranges,
        "observed_last_row": last_row,
        "dimension_matches_observed_end": (estimated_rows, estimated_columns) == (last_row, sampled_max_column),
        "profile": profile.report(),
    }


def _audit_xlsx(path: Path) -> dict[str, Any]:
    relationship_attribute = (
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    )
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "xl/workbook.xml" not in names:
            raise ValueError("XLSX has no xl/workbook.xml")
        workbook = ET.parse(archive.open("xl/workbook.xml")).getroot()
        relationships: dict[str, str] = {}
        rel_member = "xl/_rels/workbook.xml.rels"
        if rel_member in names:
            rel_root = ET.parse(archive.open(rel_member)).getroot()
            for relation in rel_root:
                relation_id = relation.attrib.get("Id")
                target = relation.attrib.get("Target")
                if relation_id and target:
                    normalized = posixpath.normpath(
                        target.lstrip("/")
                        if target.startswith("/xl/")
                        else posixpath.join("xl", target)
                    )
                    relationships[relation_id] = normalized
        shared, shared_truncated = _shared_strings(archive)
        sheets = []
        for sheet in workbook.iter():
            if _local_name(sheet.tag) != "sheet":
                continue
            relation_id = sheet.attrib.get(relationship_attribute, "")
            member = relationships.get(relation_id, "")
            if not member or member not in names:
                sheets.append(
                    {
                        "name": sheet.attrib.get("name", ""),
                        "parse_status": "FAIL",
                        "reason": f"worksheet target missing for {relation_id}",
                    }
                )
                continue
            details = _audit_worksheet(archive, member, shared)
            details.update(
                {
                    "name": sheet.attrib.get("name", ""),
                    "parse_status": "PASS",
                }
            )
            sheets.append(details)
    if not sheets or any(sheet.get("parse_status") != "PASS" for sheet in sheets):
        raise ValueError("one or more XLSX worksheets could not be inspected")
    header_signatures = []
    for sheet in sheets:
        signature = list(sheet.get("header_cells", {}).values())
        if signature not in header_signatures:
            header_signatures.append(signature)
    return {
        "sheet_count": len(sheets),
        "scan_complete": True,
        "actual_total_rows": sum(sheet["profile"]["stored_row_count"] for sheet in sheets),
        "actual_data_rows": sum(sheet["profile"]["data_row_count"] for sheet in sheets),
        "estimated_total_rows": sum(
            sheet.get("estimated_rows") or 0 for sheet in sheets
        ),
        "header_signatures": header_signatures,
        "consistent_headers": len(header_signatures) <= 1,
        "shared_strings_loaded": len(shared),
        "shared_strings_truncated": shared_truncated,
        "sheets": sheets,
    }


def audit_source(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".tex"}:
        return {"detected_format": suffix[1:], "parse_status": "PASS", **_audit_text(path)}
    if suffix in {".csv", ".tsv"}:
        return {"detected_format": suffix[1:], "parse_status": "PASS", **_audit_csv(path)}
    if suffix == ".docx":
        return {"detected_format": "docx", "parse_status": "PASS", **_audit_docx(path)}
    if suffix in {".xlsx", ".xlsm"}:
        return {"detected_format": suffix[1:], "parse_status": "PASS", **_audit_xlsx(path)}
    return {
        "detected_format": suffix[1:] or "unknown",
        "parse_status": "MANUAL_REQUIRED",
        "reason": "format is not structurally parsed by the standard-library intake layer",
        "manual_review": {"completed": False, "evidence": ""},
    }


def build_source_audit(
    run_dir: Path, manifest: dict[str, Any], generated_at: str
) -> dict[str, Any]:
    rows = []
    sources = manifest.get("sources", [])
    if not isinstance(sources, list) or not sources:
        raise ValueError("source manifest must contain a nonempty list")
    run_dir = run_dir.resolve()
    # Validate all targets before any read or extraction write.
    seen = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("malformed source row")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", source_id) or source_id in seen:
            raise ValueError("invalid or duplicate source ID")
        seen.add(source_id)
        relative = source.get("frozen_path")
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("invalid frozen source path")
        path = (run_dir / relative).resolve()
        path.relative_to(run_dir)
        target = (run_dir / "artifacts/source_audit" / f"{source_id}.txt").resolve()
        target.relative_to(run_dir)
        if not path.is_file() or _sha256_file(path) != source.get("sha256"):
            raise ValueError("frozen source content changed")
    for source in sources:
        frozen_path = source.get("frozen_path", "")
        path = run_dir / str(frozen_path)
        base = {
            "source_id": source.get("source_id"),
            "role": source.get("role"),
            "original_name": source.get("original_name"),
            "frozen_path": frozen_path,
            "source_sha256": source.get("sha256"),
        }
        try:
            details = audit_source(path)
            extracted = details.pop("extracted_text", None)
            if extracted is not None:
                artifact = Path("artifacts/source_audit") / f"{source.get('source_id')}.txt"
                artifact_path = run_dir / artifact
                _atomic_text(artifact_path, extracted)
                details["text_artifact"] = artifact.as_posix()
                details["text_artifact_sha256"] = _sha256_file(artifact_path)
        except (OSError, ValueError, csv.Error, ET.ParseError, zipfile.BadZipFile) as exc:
            details = {
                "detected_format": path.suffix.lower().lstrip(".") or "unknown",
                "parse_status": "FAIL",
                "reason": str(exc),
            }
        rows.append({**base, **details})
    return {
        "schema_version": "1.0",
        "run_id": manifest.get("run_id"),
        "generated_at": generated_at,
        "sources": rows,
        "summary": {
            "expected_sources": len(manifest.get("sources", [])),
            "audited_sources": len(rows),
            "passed": sum(row.get("parse_status") == "PASS" for row in rows),
            "manual_required": sum(
                row.get("parse_status") == "MANUAL_REQUIRED" for row in rows
            ),
            "failed": sum(row.get("parse_status") == "FAIL" for row in rows),
        },
    }
