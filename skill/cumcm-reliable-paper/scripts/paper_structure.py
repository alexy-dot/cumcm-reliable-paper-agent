"""Inspect PDF sections against the user's CUMCM structure and question contract."""
import argparse
import hashlib
import json
import re
from pathlib import Path

SECTIONS = {
    "restatement": ("问题重述",),
    "analysis": ("问题分析",),
    "assumptions": ("模型假设", "基本假设"),
    "notation": ("符号说明", "符号与说明"),
    "solution": ("模型的建立与求解", "模型建立与求解"),
    "validation": ("模型检验与灵敏度分析", "模型检验与敏感性分析", "模型检验"),
    "evaluation": ("模型评价与改进", "模型评价"),
    "conclusion": ("结论",),
    "ai": ("AI工具使用声明",),
    "references": ("参考文献",),
    "appendix": ("附录",),
}
NUMBER = r"(?:[一二三四五六七八九十百]+[、.．]|\d+(?:\.\d+)*[、.．]?)?"


def chinese_number(number):
    if not 1 <= number <= 99:
        raise ValueError("automatic labels support 1-99 questions")
    digits="一二三四五六七八九"
    if number<10:
        return digits[number-1]
    tens,units=divmod(number,10)
    return (digits[tens-1] if tens>1 else "")+"十"+(digits[units-1] if units else "")


def expected_questions(contract, question_count):
    if contract is not None:
        if not isinstance(contract,dict) or not isinstance(contract.get("questions"),list) or not contract["questions"]:
            raise ValueError("contract must contain a nonempty questions list")
        rows=contract["questions"]
        if any(not isinstance(row,dict) or not isinstance(row.get("id"),str) or not row["id"].strip() for row in rows):
            raise ValueError("every question requires a nonempty string id")
        ids=[row["id"] for row in rows]
        if len(set(ids))!=len(ids):
            raise ValueError("duplicate question ids")
        if question_count is not None and question_count!=len(ids):
            raise ValueError("explicit count disagrees with contract")
        return ids
    if type(question_count) is not int or not 1<=question_count<=99:
        raise ValueError("provide a problem contract or question count; no four-question default")
    return [f"Q{i}" for i in range(1,question_count+1)]


def analyze_pages(pages, *, contract=None, question_count=None):
    ids=expected_questions(contract,question_count)
    if len(ids)>99:
        raise ValueError("too many top-level questions for the default profile")
    # Preserve line boundaries: paragraph mentions are not standalone section headings.
    lines=[(page_index+1,re.sub(r"\s+","",line)) for page_index,page in enumerate(pages)
           for line in page.splitlines() if line.strip()]
    hits={key:[] for key in SECTIONS}
    for index,(page,line) in enumerate(lines):
        for key,names in SECTIONS.items():
            suffix = r"(?:[：:].*)?" if key=="appendix" else ""
            if any(re.fullmatch(NUMBER+re.escape(name)+suffix,line) for name in names):
                hits[key].append(index)
    unique=all(len(indices)==1 for indices in hits.values())
    ordered=unique and [hits[key][0] for key in SECTIONS]==sorted(hits[key][0] for key in SECTIONS)
    first_page=re.sub(r"\s+","",pages[0]) if pages else ""
    checks={
        "extractable_text":bool(pages) and all(page.strip() for page in pages),
        "abstract_and_keywords_on_page_one":"摘要" in first_page and any(word in first_page for word in ("关键词","关键字")),
        "body_starts_on_page_two":len(hits["restatement"])==1 and lines[hits["restatement"][0]][0]==2,
        "required_heading_order":ordered,
    }
    question_evidence={}
    for scope,end in (("analysis","assumptions"),("solution","validation")):
        found=[]
        if ordered:
            for index in range(hits[scope][0]+1,hits[end][0]):
                page,line=lines[index]
                match=re.match(r"^(?:\d+(?:\.\d+)+[、.．]?)?问题([一二三四五六七八九十百]+|\d+)(?=[:：的]|$)",line)
                if match:
                    ordinal=next((i for i in range(1,len(ids)+1) if match[1] in (str(i),chinese_number(i))),None)
                    found.append({"ordinal":ordinal,"label":match[1],"page":page,"heading":line})
        ordinals=[row["ordinal"] for row in found]
        checks[f"all_questions_{scope}"]=list(dict.fromkeys(ordinals))==list(range(1,len(ids)+1))
        question_evidence[scope]={"expected_question_ids":ids,"found":found,
                                  "missing_ids":[qid for i,qid in enumerate(ids,1) if i not in ordinals],
                                  "unknown_labels":[row["label"] for row in found if row["ordinal"] is None]}
    notation=""
    if ordered:
        notation="".join(line for _,line in lines[hits["notation"][0]+1:hits["solution"][0]])
    checks["notation_table_columns"]=all(token in notation for token in ("符号","含义","单位"))
    return {"profile":"user-requested CUMCM organization; recognized labels are conventions, not universal official rules",
            "passed":all(checks.values()),"checks":checks,"pages":len(pages),"question_count":len(ids),
            "question_evidence":question_evidence,
            "heading_pages":{key:[lines[index][0] for index in indices] for key,indices in hits.items()},
            "scope":"actual section coverage only; no certification of substantive answers, math, visual quality or awards",
            "question_mapping":"contract questions in listed order map to 问题一/问题1 etc.; nested outputs need semantic review"}


def check_structure(path, *, contract_path=None, question_count=None):
    from pypdf import PdfReader
    path=Path(path)
    if contract_path is None and question_count is None:
        candidate=path.parent.parent/"problem_contract.json"
        if candidate.is_file():
            contract_path=candidate
    contract=None
    if contract_path is not None:
        raw=Path(contract_path).read_bytes()
        contract=json.loads(raw.decode("utf-8"))
    pdf=PdfReader(path)
    if pdf.is_encrypted:
        raise ValueError("encrypted PDF requires decryption")
    pages=[page.extract_text(extraction_mode="layout") or "" for page in pdf.pages]
    result=analyze_pages(pages,contract=contract,question_count=question_count)
    result["pdf_sha256"]=hashlib.sha256(path.read_bytes()).hexdigest()
    result["extractor"]="pypdf layout text"
    if contract_path is not None:
        result["contract_sha256"]=hashlib.sha256(raw).hexdigest()
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf",type=Path)
    parser.add_argument("--contract",type=Path)
    parser.add_argument("--question-count",type=int)
    parser.add_argument("--report",type=Path)
    args=parser.parse_args()
    try:
        result=check_structure(args.pdf,contract_path=args.contract,question_count=args.question_count)
    except (ValueError,OSError) as exc:
        parser.exit(2,f"Cannot check structure: {exc}\n")
    if args.report:
        args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result["passed"] else 1)
