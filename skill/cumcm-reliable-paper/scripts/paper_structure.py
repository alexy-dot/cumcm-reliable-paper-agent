"""Inspect the actual PDF against this project's user-requested CUMCM structure."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def check_structure(path):
    import fitz
    with fitz.open(path) as pdf:
        pages = [re.sub(r"\s+", "", page.get_text(sort=True)) for page in pdf]
    headings = ["一、问题重述", "二、问题分析", "三、模型假设", "四、符号说明", "五、模型的建立与求解",
                "六、模型检验与灵敏度分析", "七、模型评价与改进", "八、结论", "AI工具使用声明", "参考文献", "附录"]
    text = "\n".join(pages)
    positions = [text.find(heading) for heading in headings]
    checks = {
        "abstract_and_keywords_on_page_one": bool(pages) and "摘要" in pages[0] and "关键词" in pages[0],
        "body_starts_on_page_two": len(pages) > 1 and "一、问题重述" not in pages[0] and pages[1].startswith("一、问题重述"),
        "required_heading_order": all(position >= 0 for position in positions) and positions == sorted(positions),
        "four_question_analysis_subsections": all(f"2.{i}问题{word}的分析" in text for i,word in enumerate("一二三四",1)),
        "four_question_solution_subsections": all(f"5.{i}问题{word}" in text for i,word in enumerate("一二三四",1)),
        "notation_table_columns": "符号含义单位" in text,
    }
    return {"profile": "user-requested CUMCM paper structure; not an official universal chapter-order rule",
            "passed": all(checks.values()), "checks": checks, "pages": len(pages),
            "heading_pages": {heading: next((i+1 for i,page in enumerate(pages) if heading in page), None) for heading in headings},
            "pdf_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "scope": "actual page-one contents and required structure; substantive writing and scientific quality still require review"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = check_structure(args.pdf)
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
