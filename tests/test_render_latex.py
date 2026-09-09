"""Math is preserved as TeX, and never silently routed through the plain-text renderer."""
import json
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
