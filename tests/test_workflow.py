from __future__ import annotations

import hashlib
import sys
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT / "skill/cumcm-reliable-paper/scripts"
sys.path.insert(0, str(SCRIPTS))

from engine import (  # noqa: E402
    WorkflowError,
    advance_run,
    audit_run_sources,
    initialize_run,
    read_json,
    seal_run,
    signoff_status,
    status_run,
    validate_run,
    write_json,
)


class ReliablePaperWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.problem = self.root / "problem.txt"
        self.attachment = self.root / "attachment.csv"
        self.problem.write_text("Question 1: estimate y from x.", encoding="utf-8")
        self.attachment.write_text("x,y\n1,2\n2,4\n", encoding="utf-8")
        self.run_dir = self.root / "run"
        initialize_run(
            output_dir=self.run_dir,
            problem=self.problem,
            attachments=[self.attachment],
            title="Smoke problem",
            run_id="smoke-run",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_docx(self, path: Path, text: str) -> None:
        document = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>
</w:document>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", document)

    def make_xlsx(self, path: Path) -> None:
        workbook = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets>
</workbook>
"""
        relationships = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Target="worksheets/sheet1.xml"
   Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>
</Relationships>
"""
        shared = """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>x</t></si><si><t>y</t></si>
</sst>
"""
        worksheet = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:B3"/><sheetData>
    <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
    <row r="2"><c r="A2"><v>1</v></c><c r="B2"><v>2</v></c></row>
    <row r="3"><c r="A3"><v>2</v></c><c r="B3"><v>4</v></c></row>
  </sheetData>
</worksheet>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("xl/workbook.xml", workbook)
            archive.writestr("xl/_rels/workbook.xml.rels", relationships)
            archive.writestr("xl/sharedStrings.xml", shared)
            archive.writestr("xl/worksheets/sheet1.xml", worksheet)

    def approve_signoffs(self, *signoff_ids: str) -> None:
        expected_scopes = {
            row["id"]: row["expected_scope_sha256"]
            for row in signoff_status(self.run_dir)["signoffs"]
        }
        ledger = read_json(self.run_dir / "signoff_ledger.json")
        for item in ledger["items"]:
            if item["id"] not in signoff_ids:
                continue
            item.update(
                {
                    "status": "APPROVED",
                    "reviewer": "Team member A",
                    "reviewer_type": "human",
                    "evidence": f"Reviewed source evidence for {item['id']}.",
                    "approved_at": "2026-09-08T00:00:00Z",
                    "scope_sha256": expected_scopes[item["id"]],
                }
            )
        write_json(self.run_dir / "signoff_ledger.json", ledger)

    def fill_reading(self) -> None:
        contract = read_json(self.run_dir / "problem_contract.json")
        contract.update(
            {
                "problem_interpretation": "Estimate the slope and report its unit.",
                "official_outputs": ["slope estimate"],
                "questions": [
                    {
                        "id": "Q1",
                        "source_locator": "problem.txt line 1",
                        "objective": "Estimate y/x.",
                        "inputs": ["x", "y"],
                        "outputs": ["slope"],
                        "decision_variables": ["slope parameter"],
                        "hard_constraints": ["use only frozen rows"],
                        "units": ["y-unit per x-unit"],
                        "ambiguities": ["none after direct reading"],
                        "termination_condition": "finite two-row calculation",
                    }
                ],
            }
        )
        write_json(self.run_dir / "problem_contract.json", contract)
        self.approve_signoffs("S1-INTERPRETATION")

    def fill_model(self, independent_method: str = "hand calculation") -> None:
        assumptions = read_json(self.run_dir / "assumption_ledger.json")
        assumptions["items"] = [
            {
                "id": "A1",
                "text": "The two rows use the same units.",
                "evidence": "attachment header and problem wording",
                "impact": "permits one common slope",
                "status": "ACTIVE",
            }
        ]
        write_json(self.run_dir / "assumption_ledger.json", assumptions)
        plan = read_json(self.run_dir / "model_plan.json")
        plan["questions"] = [
            {
                "id": "Q1",
                "baseline": "ratio y/x per row",
                "observed_bottleneck": "must confirm both rows agree",
                "primary_method": "least squares through the origin",
                "independent_method": independent_method,
                "validation_plan": "hand ratio, residual zero, source hash check",
                "agreement_tolerance": {"atol": 1e-12, "rtol": 0, "reason": "exact toy ratios; float rounding only"},
            }
        ]
        write_json(self.run_dir / "model_plan.json", plan)
        self.approve_signoffs("S2-ASSUMPTIONS-MODEL")

    def fill_results(self) -> None:
        artifact = self.run_dir / "artifacts/q1_result.json"
        write_json(artifact, {"slope": 2.0, "residual": 0.0})
        results = read_json(self.run_dir / "results.json")
        results["questions"] = [
            {
                "id": "Q1",
                "status": "PROVISIONAL",
                "headline_results": [
                    {
                        "id": "Q1-SLOPE",
                        "label": "slope",
                        "value": 2.0,
                        "unit": "y-unit/x-unit",
                        "source_artifact": "artifacts/q1_result.json",
                        "source_pointer": "/slope",
                        "status": "PROVISIONAL",
                    }
                ],
                "constraints": [
                    {
                        "id": "Q1-FROZEN-DATA",
                        "passed": True,
                        "evidence": "computed from the frozen attachment",
                    }
                ],
            }
        ]
        write_json(self.run_dir / "results.json", results)

    def fill_p0(self) -> None:
        verification = read_json(self.run_dir / "verification_report.json")
        verification["p0_checks"] = [
            {
                "id": "P0-UNITS",
                "passed": True,
                "evidence": "slope carries y-unit/x-unit",
            },
            {
                "id": "P0-ARITHMETIC",
                "passed": True,
                "evidence": "both row ratios equal 2",
            },
        ]
        write_json(self.run_dir / "verification_report.json", verification)

    def fill_p1(self, warning: bool = False) -> None:
        write_json(self.run_dir / "artifacts/independent.json", {"slope": 2.0})
        verification = read_json(self.run_dir / "verification_report.json")
        verification["p1_checks"] = [
            {
                "id": "P1-INDEPENDENT",
                "verdict": "WARN" if warning else "PASS",
                "evidence": "least squares equals direct hand ratios",
                **(
                    {
                        "allowed_language": "Under the two frozen rows, the slope is 2.",
                        "question_ids": ["Q1"],
                        "forbidden_terms": ["可推广", "robust"],
                    }
                    if warning
                    else {}
                ),
            }
        ]
        verification["questions"] = [
            {
                "id": "Q1",
                "independent_method": "hand calculation",
                "anchors": [
                    {
                        "type": "hand_calculation",
                        "evidence": "2/1=2 and 4/2=2",
                    },
                    {"type": "residual_check", "evidence": "residual is zero"},
                ],
                "independent_agreement": {
                    "passed": True,
                    "tolerance": 1e-12,
                    "evidence": "both methods return 2",
                    "comparisons": [{"result_id": "Q1-SLOPE", "reference_artifact": "artifacts/independent.json", "reference_pointer": "/slope"}],
                },
            }
        ]
        write_json(self.run_dir / "verification_report.json", verification)
        results = read_json(self.run_dir / "results.json")
        results["questions"][0]["status"] = "VERIFIED"
        results["questions"][0]["headline_results"][0]["status"] = "VERIFIED"
        write_json(self.run_dir / "results.json", results)
        self.approve_signoffs("S3-KEY-REPRODUCTION", "S4-FINAL-FEASIBILITY")

    def fill_paper(self, text: str = "Under the frozen rows, the slope is 2.") -> None:
        paper = self.run_dir / "paper/final.md"
        paper.write_text(f"# Result\n\n{text}\n", encoding="utf-8")
        claims = read_json(self.run_dir / "claim_ledger.json")
        claims["paper_artifact"] = "paper/final.md"
        claims["paper_source_artifact"] = "paper/final.md"
        claims["claims"] = [
            {
                "id": "C1",
                "question_id": "Q1",
                "text": text,
                "result_ids": ["Q1-SLOPE"],
                "paper_locator": "Result paragraph 1",
                "paper_excerpt": text,
                "status": "VERIFIED",
            }
        ]
        write_json(self.run_dir / "claim_ledger.json", claims)
        self.approve_signoffs("S5-ABSTRACT-HEADLINES", "S6-RULES-AI-DECLARATION")

    def advance_to_code_run(self) -> None:
        self.fill_reading()
        advance_run(self.run_dir)
        self.fill_model()
        advance_run(self.run_dir)

    def advance_to_paper_linked(self, warning: bool = False) -> None:
        self.advance_to_code_run()
        self.fill_results()
        advance_run(self.run_dir)
        self.fill_p0()
        advance_run(self.run_dir)
        self.fill_p1(warning=warning)
        advance_run(self.run_dir)

    def test_initial_run_freezes_sources_and_refuses_empty_contract(self) -> None:
        report = validate_run(self.run_dir, "READING")
        self.assertFalse(report["passed"])
        self.assertIn("G1-CONTRACT-TOP", report["failed_checks"])
        self.assertNotIn("G0-SOURCE-AUDIT", report["failed_checks"])
        sources = read_json(self.run_dir / "source_manifest.json")["sources"]
        self.assertEqual(len(sources), 2)
        self.assertTrue(all("original_path" not in row for row in sources))

        audit = read_json(self.run_dir / "source_audit.json")
        self.assertEqual(audit["summary"]["passed"], 2)
        problem_audit = next(row for row in audit["sources"] if row["role"] == "problem")
        self.assertEqual(problem_audit["parse_status"], "PASS")
        self.assertTrue(problem_audit["text_artifact"].startswith("artifacts/"))

    def test_docx_and_xlsx_sources_are_structurally_audited(self) -> None:
        problem = self.root / "problem.docx"
        attachment = self.root / "attachment.xlsx"
        self.make_docx(problem, "Question 1: estimate the slope.")
        self.make_xlsx(attachment)
        run_dir = self.root / "office-run"
        initialize_run(run_dir, problem, [attachment], "Office smoke", "office-run")

        audit = read_json(run_dir / "source_audit.json")
        problem_row = next(row for row in audit["sources"] if row["role"] == "problem")
        workbook_row = next(
            row for row in audit["sources"] if row["role"] == "attachment"
        )
        self.assertIn("estimate the slope", problem_row["preview"])
        self.assertEqual(workbook_row["sheet_count"], 1)
        self.assertTrue(workbook_row["consistent_headers"])
        self.assertEqual(workbook_row["header_signatures"], [["x", "y"]])
        self.assertEqual(workbook_row["sheets"][0]["dimension"], "A1:B3")
        self.assertEqual(workbook_row["sheets"][0]["sampled_rows"][0]["cells"]["A1"], "x")
        report = validate_run(run_dir, "READING")
        self.assertNotIn("G0-SOURCE-AUDIT", report["failed_checks"])

    def test_manual_source_review_and_audit_tampering_are_gated(self) -> None:
        problem = self.root / "problem.pdf"
        problem.write_bytes(b"not a parsed PDF")
        run_dir = self.root / "manual-run"
        initialize_run(run_dir, problem, [], "Manual smoke", "manual-run")
        report = validate_run(run_dir, "READING")
        self.assertIn("G0-SOURCE-AUDIT", report["failed_checks"])

        cli = SCRIPTS / "cumcm_agent.py"
        inspected = subprocess.run(
            [sys.executable, str(cli), "inspect", str(run_dir)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(inspected.returncode, 1)
        self.assertIn('"audit_passed": false', inspected.stdout)

        audit_path = run_dir / "source_audit.json"
        audit = read_json(audit_path)
        audit["sources"][0]["manual_review"] = {
            "completed": True,
            "evidence": "Page-by-page review recorded by a human.",
        }
        write_json(audit_path, audit)
        report = validate_run(run_dir, "READING")
        self.assertNotIn("G0-SOURCE-AUDIT", report["failed_checks"])

        source_audit = read_json(self.run_dir / "source_audit.json")
        problem_row = next(
            row for row in source_audit["sources"] if row["role"] == "problem"
        )
        extracted = self.run_dir / problem_row["text_artifact"]
        extracted.write_text("tampered", encoding="utf-8")
        report = validate_run(self.run_dir, "READING")
        self.assertIn("G0-SOURCE-AUDIT", report["failed_checks"])

    def test_source_audit_cannot_be_regenerated_after_reading(self) -> None:
        self.fill_reading()
        advance_run(self.run_dir)
        with self.assertRaises(WorkflowError):
            audit_run_sources(self.run_dir)

    def test_agent_cannot_replace_required_human_signoff(self) -> None:
        self.fill_reading()
        ledger = read_json(self.run_dir / "signoff_ledger.json")
        item = next(row for row in ledger["items"] if row["id"] == "S1-INTERPRETATION")
        item["reviewer"] = "Codex"
        item["reviewer_type"] = "agent"
        write_json(self.run_dir / "signoff_ledger.json", ledger)
        report = validate_run(self.run_dir, "READING")
        self.assertIn("HUMAN-SIGNOFFS", report["failed_checks"])

    def test_signoff_is_invalidated_when_its_scope_changes_before_advance(self) -> None:
        self.fill_reading()
        contract = read_json(self.run_dir / "problem_contract.json")
        contract["problem_interpretation"] = "Changed after human approval."
        write_json(self.run_dir / "problem_contract.json", contract)
        report = validate_run(self.run_dir, "READING")
        self.assertIn("HUMAN-SIGNOFFS", report["failed_checks"])

    def test_upstream_contract_change_is_detected_after_advancing(self) -> None:
        self.advance_to_code_run()
        contract = read_json(self.run_dir / "problem_contract.json")
        contract["questions"][0]["objective"] = "Silently changed objective."
        write_json(self.run_dir / "problem_contract.json", contract)
        report = validate_run(self.run_dir, "CODE_RUN")
        self.assertIn("CORE-UPSTREAM-FREEZE", report["failed_checks"])
        with self.assertRaises(WorkflowError):
            advance_run(self.run_dir)

    def test_result_value_and_artifact_changes_are_detected_after_advancing(self) -> None:
        self.advance_to_code_run()
        self.fill_results()
        advance_run(self.run_dir)

        results = read_json(self.run_dir / "results.json")
        results["questions"][0]["headline_results"][0]["value"] = 3.0
        write_json(self.run_dir / "results.json", results)
        report = validate_run(self.run_dir, "P0_PASS")
        self.assertIn("CORE-UPSTREAM-FREEZE", report["failed_checks"])

        results["questions"][0]["headline_results"][0]["value"] = 2.0
        write_json(self.run_dir / "results.json", results)
        artifact = self.run_dir / "artifacts/q1_result.json"
        write_json(artifact, {"slope": 3.0, "residual": 0.0})
        report = validate_run(self.run_dir, "P0_PASS")
        self.assertIn("CORE-UPSTREAM-FREEZE", report["failed_checks"])

    def test_cli_init_status_and_validate_exit_codes(self) -> None:
        cli_run = self.root / "cli-run"
        cli = SCRIPTS / "cumcm_agent.py"
        initialized = subprocess.run(
            [
                sys.executable,
                str(cli),
                "init",
                "--problem",
                str(self.problem),
                "--attachment",
                str(self.attachment),
                "--output",
                str(cli_run),
                "--title",
                "CLI smoke",
                "--run-id",
                "cli-smoke",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        status = subprocess.run(
            [sys.executable, str(cli), "status", str(cli_run)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
        self.assertIn('"stage": "READING"', status.stdout)
        validation = subprocess.run(
            [sys.executable, str(cli), "validate", str(cli_run)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(validation.returncode, 1)
        self.assertIn('"passed": false', validation.stdout)

    def test_source_mutation_is_detected(self) -> None:
        frozen = next((self.run_dir / "sources").glob("problem__*"))
        frozen.write_text("mutated", encoding="utf-8")
        report = validate_run(self.run_dir, "READING")
        self.assertIn("G0-SOURCE-FREEZE", report["failed_checks"])

    def test_result_artifact_cannot_escape_run_directory(self) -> None:
        self.advance_to_code_run()
        self.fill_results()
        results = read_json(self.run_dir / "results.json")
        results["questions"][0]["headline_results"][0]["source_artifact"] = "../problem.txt"
        write_json(self.run_dir / "results.json", results)
        report = validate_run(self.run_dir, "CODE_RUN")
        self.assertIn("G4-RESULT-LEDGER", report["failed_checks"])

    def test_headline_must_equal_machine_artifact_before_stage_freeze(self) -> None:
        self.advance_to_code_run()
        self.fill_results()
        results = read_json(self.run_dir / "results.json")
        results["questions"][0]["headline_results"][0]["value"] = 3.0
        write_json(self.run_dir / "results.json", results)
        self.assertIn("G4-RESULT-LEDGER", validate_run(self.run_dir)["failed_checks"])

    def test_result_pointer_vectors_and_invalid_numeric_values(self) -> None:
        self.advance_to_code_run()
        self.fill_results()
        artifact = self.run_dir / "artifacts/q1_result.json"
        results = read_json(self.run_dir / "results.json")
        headline = results["questions"][0]["headline_results"][0]
        headline["source_pointer"] = "/a~1b/0"
        for actual, declared, passed in [([1.0, 2.0], [1, 2], True),
                                         ([1.0, 2.0], [1, 3], False),
                                         (True, 1, False), (float("inf"), float("inf"), False)]:
            with self.subTest(actual=actual, declared=declared):
                write_json(artifact, {"a/b": [actual]})
                headline["value"] = declared
                write_json(self.run_dir / "results.json", results)
                self.assertEqual("G4-RESULT-LEDGER" not in validate_run(self.run_dir)["failed_checks"], passed)
        write_json(artifact, {"a/b": [2]})
        headline["value"] = 2
        for pointer in [None, "/a~1b/-1", "/a~1b/01", "/a~2b/0", "/absent"]:
            with self.subTest(pointer=pointer):
                headline["source_pointer"] = pointer
                write_json(self.run_dir / "results.json", results)
                self.assertIn("G4-RESULT-LEDGER", validate_run(self.run_dir)["failed_checks"])

    def test_same_method_cannot_count_as_independent(self) -> None:
        self.fill_reading()
        advance_run(self.run_dir)
        self.fill_model(independent_method="least squares through the origin")
        report = validate_run(self.run_dir, "MODEL_DRAFT")
        self.assertIn("G2-MODEL-PLAN", report["failed_checks"])
        with self.assertRaises(WorkflowError):
            advance_run(self.run_dir)

    def test_malformed_nested_json_fails_closed(self) -> None:
        self.fill_reading()
        advance_run(self.run_dir)
        assumptions = read_json(self.run_dir / "assumption_ledger.json")
        assumptions["items"] = [42]
        write_json(self.run_dir / "assumption_ledger.json", assumptions)
        report = validate_run(self.run_dir, "MODEL_DRAFT")
        self.assertIn("G2-ASSUMPTION-LEDGER", report["failed_checks"])

        self.fill_model()
        advance_run(self.run_dir)
        self.fill_results()
        advance_run(self.run_dir)
        self.fill_p0()
        advance_run(self.run_dir)
        self.fill_p1()
        verification = read_json(self.run_dir / "verification_report.json")
        verification["questions"][0]["independent_agreement"] = []
        write_json(self.run_dir / "verification_report.json", verification)
        report = validate_run(self.run_dir, "P1_PASS")
        self.assertIn("P1-INDEPENDENT-VERIFICATION", report["failed_checks"])

    def test_warning_forbids_strong_paper_language(self) -> None:
        self.advance_to_paper_linked(warning=True)
        self.fill_paper("The result is robust and 可推广.")
        report = validate_run(self.run_dir, "PAPER_LINKED")
        self.assertIn("G5-CLAIM-LEDGER", report["failed_checks"])

    def test_declared_pass_does_not_hide_independent_disagreement(self) -> None:
        self.advance_to_code_run()
        self.fill_results()
        advance_run(self.run_dir)
        self.fill_p0()
        advance_run(self.run_dir)
        self.fill_p1()
        write_json(self.run_dir / "artifacts/independent.json", {"slope": 2.1})
        report = validate_run(self.run_dir)
        self.assertIn("P1-INDEPENDENT-VERIFICATION", report["failed_checks"])

    def test_primary_output_cannot_serve_as_its_own_comparison(self) -> None:
        self.advance_to_code_run()
        self.fill_results()
        advance_run(self.run_dir)
        self.fill_p0()
        advance_run(self.run_dir)
        self.fill_p1()
        report_path = self.run_dir / "verification_report.json"
        verification = read_json(report_path)
        agreement = verification["questions"][0]["independent_agreement"]
        agreement["comparisons"][0]["reference_artifact"] = "artifacts/q1_result.json"
        write_json(report_path, verification)
        self.assertIn("P1-INDEPENDENT-VERIFICATION", validate_run(self.run_dir)["failed_checks"])
        agreement["comparisons"] = []
        write_json(report_path, verification)
        self.assertIn("P1-INDEPENDENT-VERIFICATION", validate_run(self.run_dir)["failed_checks"])

    def test_independent_output_is_frozen_even_within_tolerance(self) -> None:
        self.advance_to_paper_linked()
        write_json(self.run_dir / "artifacts/independent.json", {"slope": 2.0 + 5e-13})
        self.assertIn("CORE-UPSTREAM-FREEZE", validate_run(self.run_dir)["failed_checks"])

    def test_complete_run_seals_and_detects_later_tampering(self) -> None:
        self.advance_to_paper_linked()
        self.fill_paper()
        paper_report = validate_run(self.run_dir, "PAPER_LINKED")
        self.assertTrue(paper_report["passed"], paper_report)
        sealed = seal_run(self.run_dir)
        self.assertEqual(sealed["stage"], "VERIFIED")
        self.assertGreater(sealed["artifact_count"], 8)
        self.assertTrue(validate_run(self.run_dir, "VERIFIED")["passed"])
        self.assertEqual(status_run(self.run_dir)["next_action"], "sealed")

        paper = self.run_dir / "paper/final.md"
        paper.write_text(paper.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
        report = validate_run(self.run_dir, "VERIFIED")
        self.assertIn("FINAL-ARTIFACT-MANIFEST", report["failed_checks"])

    def test_non_list_artifact_manifest_is_rejected(self) -> None:
        self.advance_to_paper_linked()
        self.fill_paper()
        seal_run(self.run_dir)
        manifest_path = self.run_dir / "artifact_manifest.json"
        manifest = read_json(manifest_path)
        manifest["artifacts"] = {"crafted": "not-a-list"}
        manifest["package_digest"]["artifact_count"] = 1
        manifest["package_digest"]["sha256"] = hashlib.sha256(b"").hexdigest()
        write_json(manifest_path, manifest)
        report = validate_run(self.run_dir, "VERIFIED")
        self.assertIn("FINAL-ARTIFACT-MANIFEST", report["failed_checks"])


if __name__ == "__main__":
    unittest.main()
