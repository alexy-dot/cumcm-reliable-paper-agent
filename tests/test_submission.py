"""Actual PDF/ZIP fixtures for official-format mechanical checks. No network needed."""
import importlib.util
import sys
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill/cumcm-reliable-paper/scripts"))
from submission_check import check_submission


@unittest.skipUnless(importlib.util.find_spec("fitz"), "optional submission dependencies not installed")
class SubmissionCheckTest(unittest.TestCase):
    def setUp(self):
        import fitz
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.font = fitz.Font("cjk")

    def pdf(self, pages, *, left=80):
        import fitz
        doc = fitz.open()
        for number, paragraphs in enumerate(pages, 1):
            page = doc.new_page(width=210 * 72 / 25.4, height=297 * 72 / 25.4)
            page.insert_font(fontname="fixture", fontbuffer=self.font.buffer)
            y = 90
            for paragraph in paragraphs:
                for line in textwrap.wrap(paragraph, 34, replace_whitespace=False) or [""]:
                    page.insert_text((left, y), line, fontname="fixture", fontsize=10)
                    y += 17
                y += 7
            page.insert_text((295, 813), str(number), fontsize=9)
        content = doc.tobytes(deflate=True)
        doc.close()
        return content

    def fixture(self, *, left=80, declaration_first=True, appendix_code="print(1)", detail_name="AI工具使用详情.pdf", code="print(1)\n"):
        ai = ["AI工具使用声明", "本参赛队在竞赛过程中使用了AI工具，主要用于代码核验，详细使用情况见支撑材料。"]
        references = ["参考文献", "合成测试资料"]
        body = ["1 正文", "计算结果为1。"] + (ai + references if declaration_first else references + ai)
        body += ["附录", "model.py", detail_name, appendix_code]
        (self.root / "paper.pdf").write_bytes(self.pdf([["摘要", "合成测试论文，用于验证格式检查器。", "关键词：测试；数值"], body], left=left))
        details = self.pdf([["工具名称与版本：合成Fixture 1.0", "具体目的与环节：代码核验", "主要提示方式与使用过程：合成测试输入", "采纳、修改和核验情况：这是测试数据，不表示真实人员的审核记录。"]])
        with zipfile.ZipFile(self.root / "support.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("model.py", code)
            archive.writestr(detail_name, details)

    def check(self, **kwargs):
        return check_submission(self.root, "paper.pdf", "support.zip", year=2026, ai_used=True,
                                identity_terms=["Synthetic University"], **kwargs)

    def statuses(self, report):
        return {row["id"]: row["status"] for row in report["checks"]}

    def test_valid_mechanical_package_still_requires_substantive_review(self):
        self.fixture()
        result = self.check()
        self.assertTrue(result["passed"], result)
        self.assertFalse(result["submission_ready"])
        self.assertTrue(result["manual_review_remaining"])
        self.assertEqual(len(result["files"]["paper"]["md5"]), 32)

    def test_bad_margins_and_wrong_declaration_order_are_detected(self):
        self.fixture(left=30, declaration_first=False)
        statuses = self.statuses(self.check())
        self.assertEqual(statuses["CONTENT-MARGINS"], "FAIL")
        self.assertEqual(statuses["AI-DECLARATION-ORDER"], "FAIL")

    def test_source_code_mismatch_and_required_ai_filename(self):
        self.fixture(appendix_code="print(2)", detail_name="AI使用记录.pdf")
        statuses = self.statuses(self.check())
        self.assertEqual(statuses["APPENDIX-SOURCE-CODE"], "REVIEW_REQUIRED")
        self.assertEqual(statuses["AI-DETAIL-FILE"], "FAIL")

    def test_identity_is_detected_inside_support_and_redacted_in_report(self):
        self.fixture(code="print(1)\n# Synthetic University\n")
        result = self.check()
        self.assertEqual(self.statuses(result)["IDENTITY"], "FAIL")
        self.assertNotIn("Synthetic University", str(result))

    def test_unsupported_year_cannot_reuse_known_profile(self):
        self.fixture()
        with self.assertRaisesRegex(ValueError, "no verified"):
            check_submission(self.root, "paper.pdf", "support.zip", year=2027, ai_used=True)

    def test_rar_is_unavailable_not_misrepresented_as_forbidden(self):
        self.fixture()
        (self.root / "support.rar").write_bytes(b"RAR fixture")
        result = check_submission(self.root, "paper.pdf", "support.rar", year=2026, ai_used=True)
        self.assertEqual(self.statuses(result)["SUPPORT-INSPECTION"], "UNAVAILABLE")

    def test_omission_is_allowed_only_with_matching_no_ai_and_no_code_declarations(self):
        pages = [["摘要", "测试论文。", "关键词：测试"], ["1 正文", "本论文没有支撑材料。", "AI工具使用声明",
                 "本参赛队在竞赛过程中未使用任何AI工具。", "参考文献", "合成测试资料", "附录", "本论文没有用到程序。"]]
        (self.root / "paper.pdf").write_bytes(self.pdf(pages))
        result = check_submission(self.root, "paper.pdf", None, year=2026, ai_used=False, no_code=True, identity_terms=["Synthetic University"])
        self.assertTrue(result["passed"], result)
