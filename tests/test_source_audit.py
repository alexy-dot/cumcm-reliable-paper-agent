"""Behavioral checks with anomalies beyond the old six-row preview."""
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill/cumcm-reliable-paper/scripts"))
from source_audit import audit_source
from engine import initialize_run, audit_run_sources, read_json, write_json, WorkflowError, validate_run


def workbook(path, body, dimension="A1:B999"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", '<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="测量" r:id="s1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="s1" Target="worksheets/s1.xml"/></Relationships>')
        archive.writestr("xl/worksheets/s1.xml", f'<worksheet><dimension ref="{dimension}"/><sheetData>{body}</sheetData></worksheet>')


class FullIntakeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_csv_tail_missing_duplicate_nonfinite_and_ragged(self):
        path = self.root / "measurements.csv"
        path.write_text("x,z\n1,2\n2,4\n3,6\n4,8\n5,10\n1,2\n6\ninf,NaN\n7,bad\n", encoding="utf-8")
        audit = audit_source(path)
        profile = audit["profile"]
        self.assertEqual(profile["stored_row_count"], 10)
        self.assertEqual(profile["data_row_count"], 9)
        self.assertEqual(profile["duplicate_rows"], 1)
        self.assertEqual(profile["findings"]["missing_cells"], 1)
        self.assertEqual(profile["findings"]["nonfinite_cells"], 2)
        self.assertEqual(audit["ragged_rows"], 1)
        z = profile["columns"][1]
        self.assertEqual(z["numeric_count"], 6)
        self.assertAlmostEqual(z["mean"], 32 / 6)
        self.assertEqual(z["maximum"], 10)
        json.dumps(audit, allow_nan=False)

    def test_xlsx_tail_sparse_columns_formula_error_and_wrong_dimension(self):
        path = self.root / "measurements.xlsx"
        rows = '<row r="1"><c r="A1" t="inlineStr"><is><t>x</t></is></c><c r="B1" t="inlineStr"><is><t>z</t></is></c></row>'
        for i in range(2, 8):
            rows += f'<row r="{i}"><c r="A{i}"><v>{i}</v></c><c r="B{i}"><v>{i * 2}</v></c></row>'
        rows += '<row r="8"><c r="B8"><v>16</v></c></row>'
        rows += '<row r="9"><c r="A9"><f>1+1</f></c><c r="B9" t="e"><v>#DIV/0!</v></c></row>'
        rows += '<row r="12"><c r="A12"><v>2</v></c><c r="B12"><v>4</v></c></row>'
        workbook(path, rows)
        audit = audit_source(path)
        sheet = audit["sheets"][0]
        self.assertEqual(audit["actual_total_rows"], 10)
        self.assertEqual(audit["actual_data_rows"], 9)
        self.assertEqual(sheet["observed_last_row"], 12)
        self.assertFalse(sheet["dimension_matches_observed_end"])
        self.assertEqual(sheet["formula_cache_missing"], 1)
        self.assertEqual(sheet["error_cells"], 1)
        self.assertEqual(sheet["profile"]["columns"][0]["missing_count"], 2)
        self.assertEqual(sheet["profile"]["duplicate_rows"], 1)
        self.assertEqual(sheet["profile"]["columns"][1]["maximum"], 16)

    def test_broken_xml_after_six_rows_cannot_pass(self):
        problem = self.root / "problem.txt"
        problem.write_text("Inspect measurements.")
        path = self.root / "broken.xlsx"
        rows = ''.join(f'<row r="{i}"><c r="A{i}"><v>{i}</v></c></row>' for i in range(1, 9))
        workbook(path, rows + '<broken>')
        run = self.root / "run"
        initialize_run(run, problem, [path], "Broken tail")
        self.assertEqual(read_json(run / "source_audit.json")["sources"][1]["parse_status"], "FAIL")
        self.assertIn("G0-SOURCE-AUDIT", validate_run(run)["failed_checks"])

    def test_preview_only_audit_is_rejected(self):
        problem = self.root / "problem.txt"
        problem.write_text("Inspect measurements.")
        path = self.root / "data.csv"
        path.write_text("x,y\n1,2\n")
        run = self.root / "run"
        initialize_run(run, problem, [path], "Preview")
        audit = read_json(run / "source_audit.json")
        del audit["sources"][1]["profile"]
        write_json(run / "source_audit.json", audit)
        self.assertIn("G0-SOURCE-AUDIT", validate_run(run)["failed_checks"])

    def test_gb18030_after_long_ascii_prefix(self):
        path = self.root / "mixed.csv"
        path.write_bytes(("x,label\n" + "1,ok\n" * 3000 + "2,测量\n").encode("gb18030"))
        audit = audit_source(path)
        self.assertEqual(audit["encoding"], "gb18030")
        self.assertEqual(audit["profile"]["data_row_count"], 3001)
        self.assertEqual(audit["profile"]["columns"][1]["text_count"], 3001)

    def test_changed_source_inspect_preserves_previous_audit(self):
        problem = self.root / "problem.txt"
        problem.write_text("Original problem")
        run = self.root / "run"
        initialize_run(run, problem, [], "Changed")
        previous = (run / "source_audit.json").read_bytes()
        source = read_json(run / "source_manifest.json")["sources"][0]
        (run / source["frozen_path"]).write_text("Different problem")
        with self.assertRaises(WorkflowError):
            audit_run_sources(run)
        self.assertEqual((run / "source_audit.json").read_bytes(), previous)

    def test_source_id_traversal_cannot_write_outside_audit_directory(self):
        problem = self.root / "problem.txt"
        problem.write_text("Original problem")
        run = self.root / "run"
        initialize_run(run, problem, [], "Traversal")
        manifest = read_json(run / "source_manifest.json")
        manifest["sources"][0]["source_id"] = "../../escape"
        write_json(run / "source_manifest.json", manifest)
        with self.assertRaises(WorkflowError):
            audit_run_sources(run)
        self.assertFalse((run / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main()
