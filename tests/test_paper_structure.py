"""Coverage depends on the supplied task, not the furnace example's four questions."""
import sys
import unittest
import tempfile
import json
import importlib.util
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"skill/cumcm-reliable-paper/scripts"))
from paper_structure import analyze_pages,chinese_number,check_structure


def manuscript(count):
    return ["示例题目\n摘要\n这是摘要。\n关键词：示例", "1 问题重述\n给定条件与任务。\n2 问题分析\n"+
            "\n".join(f"2.{i} 问题{chinese_number(i)}的分析\n该问需要回答指定任务。" for i in range(1,count+1))+
            "\n3 模型假设\n假设及理由。\n4 符号说明\n符号\n含义\n单位\n5 模型建立与求解\n"+
            "\n".join(f"5.{i} 问题{i}：模型和求解\n结果及证据。" for i in range(1,count+1))+
            "\n6 模型检验与敏感性分析\n7 模型评价\n8 结论\nAI 工具使用声明\n参考文献\n附录"]


class StructureCoverageTest(unittest.TestCase):
    def test_two_three_and_five_question_tasks_are_supported(self):
        for count in (2,3,5,12):
            with self.subTest(count=count):
                contract={"questions":[{"id":f"Q{i}"} for i in range(1,count+1)]}
                report=analyze_pages(manuscript(count),contract=contract)
                self.assertTrue(report["passed"],report)
                self.assertEqual(report["question_count"],count)

    def test_four_question_template_cannot_pass_five_question_contract(self):
        report=analyze_pages(manuscript(4),question_count=5)
        self.assertFalse(report["passed"])
        self.assertEqual(report["question_evidence"]["solution"]["missing_ids"],["Q5"])

    def test_mentions_in_wrong_chapters_do_not_fill_missing_answer(self):
        pages=manuscript(3)
        pages[1]=pages[1].replace("5.3 问题3：模型和求解", "尚未完成第三問")
        pages[0]+="\n5.3 问题3：模型和求解"
        pages[1]+="\n5.3 问题3：模型和求解"
        self.assertFalse(analyze_pages(pages,question_count=3)["checks"]["all_questions_solution"])

    def test_paragraph_mentions_are_not_main_headings(self):
        pages=manuscript(2)
        pages[1]=pages[1].replace("3 模型假设", "下一节讨论3 模型假设以及其他内容。")
        self.assertFalse(analyze_pages(pages,question_count=2)["checks"]["required_heading_order"])

    def test_duplicate_main_heading_is_reported(self):
        pages=manuscript(2);pages[1]+="\n模型假设"
        report=analyze_pages(pages,question_count=2)
        self.assertFalse(report["checks"]["required_heading_order"])
        self.assertEqual(len(report["heading_pages"]["assumptions"]),2)

    def test_count_is_required_and_must_match_contract(self):
        with self.assertRaises(ValueError): analyze_pages(manuscript(4))
        with self.assertRaises(ValueError): analyze_pages(manuscript(4),contract={"questions":[{"id":"A"}]},question_count=4)
        with self.assertRaises(ValueError): analyze_pages(manuscript(2),contract={"questions":[{"id":"A"},{"id":"A"}]})

    def test_notation_columns_must_be_inside_notation_section(self):
        pages=manuscript(2)
        pages[1]=pages[1].replace("符号\n含义\n单位", "未列符号")
        pages[0]+="\n符号含义单位"
        self.assertFalse(analyze_pages(pages,question_count=2)["checks"]["notation_table_columns"])

    def test_body_must_not_share_abstract_page(self):
        pages=manuscript(2)
        self.assertFalse(analyze_pages([pages[0]+"\n"+pages[1]],question_count=2)["checks"]["body_starts_on_page_two"])


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in ("reportlab","pypdf")), "optional PDF dependencies unavailable")
class StructurePdfTest(unittest.TestCase):
    def test_real_pdf_uses_contract_count_and_binds_source_hash(self):
        from reportlab.pdfgen import canvas
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            run=Path(folder)
            (run/"paper").mkdir()
            contract={"questions":[{"id":f"Q{i}"} for i in range(1,4)]}
            (run/"problem_contract.json").write_text(json.dumps(contract))
            path=run/"paper/main.pdf"
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            document=canvas.Canvas(str(path))
            for text in manuscript(3):
                writer=document.beginText(70,780)
                writer.setFont("STSong-Light",10)
                writer.setLeading(14)
                for line in text.splitlines(): writer.textLine(line)
                document.drawText(writer)
                document.showPage()
            document.save()
            result=check_structure(path)
            self.assertTrue(result["passed"],result)
            self.assertEqual(result["question_count"],3)
            self.assertEqual(result["pdf_sha256"],hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(result["contract_sha256"],hashlib.sha256((run/"problem_contract.json").read_bytes()).hexdigest())
            contract["questions"].append({"id":"Q4"})
            (run/"problem_contract.json").write_text(json.dumps(contract))
            self.assertFalse(check_structure(path)["passed"])
