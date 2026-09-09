"""Bind final paper, source appendix, official templates and external reproduction."""
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import fitz
import numpy as np
from prepare import write

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"skill/cumcm-reliable-paper/scripts"))
from paper_structure import check_structure


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def finish(run,reproduced,visual_note):
    load=lambda p:json.loads(p.read_text())
    pdf=run/"paper/main.pdf";render=load(run/"paper/render_report.json")
    if render["render_status"]!="COMPILED" or render["pdf_sha256"]!=sha(pdf) or render["document_sha256"]!=sha(run/"paper/document.json"):
        raise ValueError("paper render receipt is stale")
    structure=check_structure(pdf,contract_path=run/"problem_contract.json")
    if not structure["passed"]:raise ValueError("paper structure incomplete")
    write(run/"artifacts/paper-structure.json",structure)
    verify=load(run/"artifacts/verification.json");books=load(run/"artifacts/workbook-verification.json")
    if not verify["passed"] or not books["passed"] or verify["plans_sha256"]!=sha(run/"artifacts/plans.json") or books["plans_sha256"]!=verify["plans_sha256"]:
        raise ValueError("current plan verification missing")
    for name,digest in books["workbook_sha256"].items():
        if sha(run/"artifacts/submission"/name)!=digest:raise ValueError("workbook changed")
    package=load(run/"artifacts/submission-package/package_receipt.json")
    archive=run/"artifacts/submission-package/support.zip"
    if sha(archive)!=package["sha256"]:raise ValueError("support package changed")
    printed={b["filename"]:b["utf8_sha256"] for b in render["code_blocks"]}
    with zipfile.ZipFile(archive) as z:
        for row in package["manifest"]["files"]:
            if hashlib.sha256(z.read(row["path"])).hexdigest()!=row["sha256"]:raise ValueError("archive member changed")
            if row["role"]=="code":
                source=ROOT/"skill/cumcm-reliable-paper/scripts"/Path(row["path"]).name if row["path"].startswith("renderer/") else Path(__file__).parent/row["path"]
                if printed.get(row["path"])!=row["sha256"] or sha(source)!=row["sha256"]:raise ValueError("source appendix differs from actual delivered code")
    repro_verify=load(reproduced/"artifacts/verification.json");repro_books=load(reproduced/"artifacts/workbook-verification.json")
    if not repro_verify["passed"] or not repro_books["passed"]:raise ValueError("external reproduction failed")
    plans=load(run/"artifacts/plans.json");newplans=load(reproduced/"artifacts/plans.json")
    comparisons={}
    for q in plans:
        comparisons[q]={k:float(np.max(np.abs(np.array(plans[q][k])-np.array(newplans[q][k])))) for k in ("orders","shipments","ending_inventory_product_equivalent")}
        if max(comparisons[q].values())>1e-6:raise ValueError("reproduced plans differ")
    bounds=[]
    with fitz.open(pdf) as doc,fitz.open(reproduced/"paper/main.pdf") as other:
        for i,page in enumerate(doc):
            for b in page.get_text("blocks"):
                if b[0]<40 or b[2]>page.rect.width-40 or b[1]<28 or b[3]>page.rect.height-18:bounds.append({"page":i+1,"bbox":list(b[:4])})
        body_pages=min(structure["heading_pages"]["appendix"])-1
        same_body=[doc[i].get_pixmap().samples==other[i].get_pixmap().samples for i in range(body_pages)]
        page_count=len(doc)
    if bounds or not all(same_body):raise ValueError("page overflow or reproduced main paper differs")
    diagnostic=load(run/"artifacts/current-format-diagnostic.json")
    if diagnostic["files"]["paper"]["sha256"]!=sha(pdf):raise ValueError("format diagnostic predates paper")
    report={"case":"2021 C source-only timed trial", "paper":{"sha256":sha(pdf),"pages":page_count,"body_and_front_matter_pages":body_pages,
        "appendix_pages":page_count-body_pages,"bounds_issues":bounds,"agent_visual_review":visual_note},
        "numerical_checks":len(verify["checks"]),"official_workbook_sheets":len(books["sheets"]),"full_source_files":len(printed),
        "external_reproduction":{"scope":"isolated extracted support package on the same interpreter/runtime; re-read official files, regenerated decisions, official workbooks and PDF; only a final paper page-break edit required repeating the dependent packaging/render stages",
            "max_absolute_differences":comparisons,"main_paper_pages_pixel_identical":all(same_body),"reproduced_plans_sha256":sha(reproduced/"artifacts/plans.json")},
        "results":{q:{k:r[k] for k in ("production_per_week","active_suppliers","purchase_cost_index","raw_material_volume","expected_transport_loss")} for q,r in plans.items()},
        "capacity":verify["capacity_bound"],"supplier_count_proof":verify["minimum_count_proof"],
        "current_2026_format_diagnostic":{"passed":diagnostic["passed"],"failed_checks":diagnostic["failed_checks"],
            "scope":"current submission-format comparison, not retrospective application of 2026 rules to 2021 contestants"},
        "artifact_sha256":{"support_zip":sha(archive),"plans":sha(run/"artifacts/plans.json"),"verification":sha(run/"artifacts/verification.json"),
                           "workbook_verification":sha(run/"artifacts/workbook-verification.json"),"document":sha(run/"paper/document.json")},
        "completed":"four conditional problem answers, complete original-template results, independent numerical checks, Chinese paper and same-source code appendix",
        "not_established":["continuous supplier availability and physical maximum capacity","calibrated future supply reliability","same-problem award-paper comparison or real expert assessment","2026 submission readiness and actual team approval"],
        "submission_ready":False,"national_award_level":"NOT_ESTABLISHED"}
    write(run/"artifacts/final-review.json",report)
    print({"pages":page_count,"main_pages":body_pages,"source_files":len(printed),"numerical_checks":len(verify["checks"]),"reproduction":"PASS","format_failures":diagnostic["failed_checks"]},flush=True)


if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("run",type=Path);ap.add_argument("--reproduced",type=Path,required=True);ap.add_argument("--visual-note",required=True)
    args=ap.parse_args();finish(args.run.resolve(),args.reproduced.resolve(),args.visual_note)
