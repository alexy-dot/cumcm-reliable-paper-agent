"""Readiness checks must distinguish imports, compiler presence and actual compilation."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/"skill/cumcm-reliable-paper/scripts"
sys.path.insert(0,str(SCRIPTS))
from environment_check import check_environment,probe_import,probe_compiler


class EnvironmentCheckTest(unittest.TestCase):
    def test_core_cli_needs_no_run_directory_or_optional_packages(self):
        with tempfile.TemporaryDirectory() as folder:
            result=subprocess.run([sys.executable,str(SCRIPTS/"cumcm_agent.py"),"doctor"],cwd=folder,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads(result.stdout)
            self.assertTrue(data["passed"])
            self.assertEqual(data["imports"],[])
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_import_probe_executes_import_and_handles_missing_module(self):
        self.assertTrue(probe_import("json")["passed"])
        result=probe_import("cumcm_intentionally_missing_package")
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"],"missing")
        self.assertEqual(result["missing_module"],"cumcm_intentionally_missing_package")

    def test_missing_required_package_cannot_pass_selected_profile(self):
        def probe(name):return {"module":name,"package":name,"passed":name!="scipy","status":"missing" if name=="scipy" else "available"}
        with patch("environment_check.probe_import",side_effect=probe):
            result=check_environment(["statistics"])
        self.assertFalse(result["passed"])
        self.assertEqual(result["missing_packages"],["scipy"])

    def test_timeout_is_unresolved_not_a_missing_package(self):
        with patch("environment_check.subprocess.run",side_effect=subprocess.TimeoutExpired("import",20)):
            result=probe_import("sklearn")
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"],"timeout")
        with patch("environment_check.probe_import",return_value=result):
            report=check_environment(["statistics"])
        self.assertFalse(report["passed"])
        self.assertEqual(report["missing_packages"],[])
        self.assertTrue(all(row["status"]=="timeout" for row in report["failed_imports"]))

    def test_missing_transitive_dependency_does_not_label_parent_package_missing(self):
        response=subprocess.CompletedProcess([],1,stdout='{"passed":false,"status":"dependency_missing","missing_module":"numpy","error":"No module named numpy"}',stderr="")
        with patch("environment_check.subprocess.run",return_value=response):
            result=probe_import("sklearn")
        self.assertEqual(result["status"],"dependency_missing")
        self.assertEqual(result["missing_module"],"numpy")

    def test_compiler_presence_does_not_claim_compile_success(self):
        with patch("environment_check.probe_import",side_effect=lambda n:{"module":n,"passed":True}), \
             patch("environment_check.find_compiler",return_value="tectonic"), \
             patch("environment_check.probe_compiler",return_value={"passed":True,"path":"tectonic"}):
            result=check_environment(["paper"])
            self.assertTrue(result["passed"])
            self.assertFalse(result["paper_smoke"]["attempted"])
            self.assertIsNone(result["paper_smoke"]["passed"])
            with patch("environment_check.compile_smoke",return_value={"attempted":True,"passed":False}):
                self.assertFalse(check_environment(["paper"],smoke=True)["passed"])

    def test_unrelated_executable_is_not_accepted_as_latex(self):
        self.assertFalse(probe_compiler(sys.executable)["passed"])

    def test_smoke_requires_paper_profile_and_returns_machine_readable_error(self):
        result=subprocess.run([sys.executable,str(SCRIPTS/"cumcm_agent.py"),"doctor","--smoke"],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertFalse(json.loads(result.stdout)["passed"])
        self.assertIn("requires",json.loads(result.stdout)["error"])


if __name__=="__main__":unittest.main()
