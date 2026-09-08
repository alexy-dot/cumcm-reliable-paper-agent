"""Optional PDF integration: content preservation and embedded glyph coverage."""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill/cumcm-reliable-paper/scripts"))
from render_paper import render

PAPER_DEPS = all(importlib.util.find_spec(name) for name in ("reportlab", "pypdf"))


@unittest.skipUnless(PAPER_DEPS, "optional PDF dependencies not installed")
class PaperRenderTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        choices = [Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
                   Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
        self.font = next((path for path in choices if path.is_file()), None)
        if self.font is None:
            self.skipTest("test TrueType font unavailable")
        self.document = {"title": "Numerical report", "sections": [{"title": "Results", "blocks": [
            {"text": "A < B; verified profit = 121."}, {"table": [["Metric", "Value"], ["Profit", "121"]]}]}]}
        self.source = self.root / "document.json"

    def test_pdf_preserves_text_and_embeds_font(self):
        from pypdf import PdfReader
        self.source.write_text(json.dumps(self.document), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            render(self.root, self.source, self.font)
        pdf = PdfReader(self.root / "paper/main.pdf")
        self.assertIn("A < B; verified profit = 121.", pdf.pages[0].extract_text())
        fonts = pdf.pages[0]["/Resources"]["/Font"].values()
        embedded = [font.get_object().get("/FontDescriptor") for font in fonts]
        self.assertTrue(any(descriptor and "/FontFile2" in descriptor.get_object() for descriptor in embedded))
        self.assertFalse(pdf.is_encrypted)

    def test_unsupported_character_is_rejected_before_writing_pdf(self):
        self.document["title"] = "Unsupported " + chr(0x10FFFF)
        self.source.write_text(json.dumps(self.document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "lacks glyphs"):
            render(self.root, self.source, self.font)
        self.assertFalse((self.root / "paper/main.pdf").exists())
