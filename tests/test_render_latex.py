"""Math is preserved as TeX, and never silently routed through the plain-text renderer."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill/cumcm-reliable-paper/scripts"))
from render_latex import render_latex, inline
from render_paper import render


class LatexSourceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "document.json"
        self.source.write_text(json.dumps({"title": "公式验证", "sections": [{"title": "模型", "blocks": [
            {"text": r"温度$T_n$与file_name，变化不超过5%。"},
            {"equation": r"\frac{\mathrm dT}{\mathrm dt}=\frac{U-T}{\tau_g}"}]}]}, ensure_ascii=False), encoding="utf-8")

    def test_inline_and_display_math_survive_source_generation(self):
        render_latex(self.root, self.source, compile_pdf=False)
        tex = (self.root / "paper/main.tex").read_text()
        self.assertIn(r"$T_n$", tex)
        self.assertIn(r"\begin{equation}", tex)
        self.assertIn(r"\frac{U-T}{\tau_g}", tex)
        self.assertIn(r"file\_name", tex)
        self.assertIn(r"5\%", tex)

    def test_math_document_uses_mathematical_backend(self):
        with patch("render_latex.render_latex") as backend:
            render(self.root, self.source, latex_compiler="tectonic")
            backend.assert_called_once()

    def test_unbalanced_math_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unbalanced"):
            inline("temperature $T_n")

    def test_temperature_and_inverse_time_units_are_typeset_without_missing_unicode_glyphs(self):
        tex = inline("240℃，3℃/s，416℃·s，79cm·min⁻¹")
        self.assertNotIn("℃", tex)
        self.assertNotIn("⁻", tex)
        self.assertIn(r"\mathrm{min}^{-1}", tex)
        self.assertIn(r"{}^{\circ}\mathrm{C}", tex)

    def test_source_only_generation_invalidates_an_old_pdf_receipt(self):
        (self.root / "paper").mkdir()
        (self.root / "paper/main.pdf").write_bytes(b"previous PDF")
        (self.root / "paper/render_report.json").write_text('{"render_status":"COMPILED"}')
        render_latex(self.root, self.source, compile_pdf=False)
        report = json.loads((self.root / "paper/render_report.json").read_text())
        self.assertEqual(report["render_status"], "PENDING")
        self.assertNotIn("pdf_sha256", report)
        self.assertEqual((self.root / "paper/main.pdf").read_bytes(), b"previous PDF")

    def test_code_is_literal_external_text_not_executable_tex(self):
        code = 'print("中文")\n# \\end{Verbatim}\n# ```\n'
        self.source.write_text(json.dumps({"title":"源码", "sections":[{"title":"附录","blocks":[{"code":code,"filename":"solver.py"}]}]},ensure_ascii=False),encoding="utf-8")
        render_latex(self.root,self.source,compile_pdf=False)
        self.assertEqual((self.root/"paper/source-001.txt").read_text(),code)
        tex = (self.root/"paper/main.tex").read_text()
        self.assertIn("\\VerbatimInput",tex)
        self.assertNotIn(code,tex)
        self.assertIn("````",(self.root/"paper/main.md").read_text())


@unittest.skipUnless(os.environ.get("CUMCM_TEST_TECTONIC"), "optional actual TeX pagination test requires CUMCM_TEST_TECTONIC")
class LongTablePaginationTest(unittest.TestCase):
    def test_all_rows_remain_on_visible_pages_and_headers_repeat(self):
        import fitz
        with tempfile.TemporaryDirectory() as folder:
            run=Path(folder);source=run/"document.json"
            names=[f"ENTRY{i:03d}" for i in range(85)]
            source.write_text(json.dumps({"title":"长表分页验证","sections":[{"title":"文件清单","blocks":[
                {"text":r"使用模型$x=1$。"},
                {"table":[["条目","内容","值"]]+[[name,"需要跨页保留的文件条目及说明",str(i)] for i,name in enumerate(names)],
                 "long_table":True,"caption":"全部条目清单"}]}]},ensure_ascii=False),encoding="utf-8")
            render_latex(run,source,compiler=os.environ["CUMCM_TEST_TECTONIC"],cache_dir=os.environ.get("CUMCM_TEST_TEX_CACHE"))
            with fitz.open(run/"paper/main.pdf") as pdf:
                self.assertGreater(len(pdf),1)
                text="".join(p.get_text() for p in pdf)
                for name in names:self.assertIn(name,text)
                for page in pdf:
                    for block in page.get_text("blocks"):
                        self.assertGreaterEqual(block[1],28)
                        self.assertLessEqual(block[3],page.rect.height-18)
                self.assertGreaterEqual(text.count("条目"),len(pdf))
            self.assertIn("全部条目清单",(run/"paper/main.md").read_text())
