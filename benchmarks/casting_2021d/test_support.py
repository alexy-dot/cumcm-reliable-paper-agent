"""The package runs without repository imports and cannot accept stale references."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from artifact_io import read_json, write_json, sha256_file
from solve import solve
from verify import verify
from sensitivity import assess
from package import build
from paper import support_appendix


class PortableSupportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.work = cls.root / "run"
        facts = {"source_sha256": "fixture-not-a-real-statement", "tail_lengths_m": [13.7, 14.5],
                 "event_times_min": [0, 4.7], "cases": {"Q2": {"target_m": 9.5, "lower_m": 9., "upper_m": 10.}}}
        write_json(cls.work / "state.json", {"stage": "READING"})
        write_json(cls.work / "artifacts/facts.json", facts)
        with contextlib.redirect_stdout(io.StringIO()):
            solve(cls.work)
            verify(cls.work)
            assess(cls.work)
            cls.receipt = build(cls.work)

    def extract(self, name):
        directory = self.root / name
        with zipfile.ZipFile(self.work / "artifacts/submission-package/support.zip") as archive:
            archive.extractall(directory)
        return directory

    def execute(self, root, output):
        env = os.environ.copy()
        env["PYTHONPATH"] = "/definitely-not-the-repository"
        return subprocess.run([sys.executable, "-I", str(root / "reproduce.py"), "--output", str(output)],
                              cwd=self.root, env=env, capture_output=True, text=True)

    def test_isolated_reproduction_and_no_overwrite(self):
        root = self.extract("good")
        output = self.root / "reproduced"
        result = self.execute(root, output)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = read_json(output / "reproduction_report.json")
        self.assertTrue(report["passed"])
        self.assertFalse(report["source_pdf_checked"])
        original = (output / "artifacts/solution.json").read_bytes()
        self.assertNotEqual(self.execute(root, output).returncode, 0)
        self.assertEqual((output / "artifacts/solution.json").read_bytes(), original)

    def test_missing_verifier_prevents_execution(self):
        root = self.extract("missing")
        (root / "verify.py").unlink()
        output = self.root / "missing-output"
        result = self.execute(root, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing or changed: verify.py", result.stderr)
        self.assertFalse(output.exists())

    def test_matching_manifest_cannot_hide_an_incorrect_expected_answer(self):
        root = self.extract("wrong-answer")
        path = root / "expected-results.json"
        expected = read_json(path)
        expected["solution"]["tails"][0]["waste_m"] = 0
        write_json(path, expected)
        manifest = read_json(root / "manifest.json")
        entry = next(item for item in manifest["files"] if item["path"] == path.name)
        entry.update(sha256=sha256_file(path), bytes=path.stat().st_size)
        write_json(root / "manifest.json", manifest)
        output = self.root / "wrong-output"
        result = self.execute(root, output)
        self.assertNotEqual(result.returncode, 0)
        report = read_json(output / "reproduction_report.json")
        self.assertFalse(report["checks"]["all_tail_and_online_decisions"])
        self.assertEqual(read_json(output / "artifacts/solution.json")["tails"][0]["waste_m"], 13.7)

    def test_every_appendix_program_is_byte_identical_to_zip(self):
        appendix = support_appendix(self.work)
        blocks = [block for block in appendix["blocks"] if "code" in block]
        self.assertEqual(len(blocks), 8)
        with zipfile.ZipFile(self.work / "artifacts/submission-package/support.zip") as archive:
            for block in blocks:
                self.assertEqual(block["code"].encode("utf-8"), archive.read(block["filename"]))
        self.assertEqual(appendix, support_appendix(self.work, self.extract("appendix")))


if __name__ == "__main__":
    unittest.main()
