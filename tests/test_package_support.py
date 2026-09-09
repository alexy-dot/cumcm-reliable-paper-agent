import json
import sys
import tempfile
import unittest
import zipfile
import subprocess
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"skill/cumcm-reliable-paper/scripts"))
from package_support import package_support


class SupportPackageTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/"model.py").write_text('print("温度", 2)\n',encoding="utf-8")
        self.selection={"files":[{"source":"model.py","archive_path":"code/model.py","role":"code"}]}

    def test_zip_and_appendix_contain_identical_complete_code(self):
        receipt=package_support(self.root,self.selection)
        package=self.root/"artifacts/submission-package"
        appendix=json.loads((package/"appendix.json").read_text())
        code=next(block for block in appendix["blocks"] if "code" in block)
        with zipfile.ZipFile(package/"support.zip") as z:
            self.assertEqual(z.read("code/model.py").decode(),code["code"])
            self.assertEqual(json.loads(z.read("manifest.json")),receipt["manifest"])
        self.assertFalse(receipt["submission_ready"])

    def test_deterministic_archive_and_no_overwrite(self):
        first=package_support(self.root,self.selection,"packages/one")
        second=package_support(self.root,self.selection,"packages/two")
        self.assertEqual(first["sha256"],second["sha256"])
        with self.assertRaisesRegex(ValueError,"already exists"):
            package_support(self.root,self.selection,"packages/one")

    def test_paths_duplicates_and_symlinks_rejected_before_output(self):
        for change in [{"archive_path":"../outside.py"},{"source":"../outside.py"},{"archive_path":"manifest.json"}]:
            with self.subTest(change=change):
                bad={"files":[{**self.selection["files"][0],**change}]}
                with self.assertRaises(ValueError): package_support(self.root,bad)
        with self.assertRaises(ValueError): package_support(self.root,{"files":self.selection["files"]*2})
        (self.root/"link.py").symlink_to(self.root/"model.py")
        with self.assertRaises(ValueError): package_support(self.root,{"files":[{**self.selection["files"][0],"source":"link.py"}]})
        self.assertFalse((self.root/"artifacts/submission-package").exists())

    def test_missing_source_and_sealed_run_are_rejected(self):
        (self.root/"model.py").unlink()
        with self.assertRaises(ValueError): package_support(self.root,self.selection)
        (self.root/"state.json").write_text('{"stage":"VERIFIED"}')
        with self.assertRaisesRegex(ValueError,"sealed"):
            package_support(self.root,self.selection)

    def test_production_support_reproduces_without_repository(self):
        project=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,str(project/"examples/production/run.py"),"--output",str(self.root/"run")],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        extract=self.root/"isolated"
        with zipfile.ZipFile(self.root/"run/artifacts/submission-package/support.zip") as archive:
            archive.extractall(extract)
        result=subprocess.run([sys.executable,"solver.py","--output","reproduced.json"],cwd=extract,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        reproduced=json.loads((extract/"reproduced.json").read_text())
        self.assertEqual(reproduced["profit"],121)
        self.assertEqual(reproduced["independent_profit"],121)
        self.assertEqual(reproduced["quantities"],[3,8,3])
