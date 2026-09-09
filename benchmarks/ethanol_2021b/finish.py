"""Publish observable reanalysis results without claiming blind or award certification."""
import argparse
from pathlib import Path
from prepare import read_json,write_json,sha256_file
from split_sensitivity import checked_report


def finish(run,visual_note=""):
    partitions=checked_report(run)
    result=read_json(run/"artifacts/statistical_results.json");verification=read_json(run/"artifacts/independent_statistics.json")
    decisions=read_json(run/"artifacts/decisions.json");render=read_json(run/"paper/render_report.json");structure=read_json(run/"paper/structure_review.json")
    if (verification["results_sha256"]!=sha256_file(run/"artifacts/statistical_results.json") or verification["decisions_sha256"]!=sha256_file(run/"artifacts/decisions.json")
        or not verification["passed"] or not structure["passed"] or render["render_status"]!="COMPILED"
        or render["pdf_sha256"]!=sha256_file(run/"paper/main.pdf") or structure["pdf_sha256"]!=render["pdf_sha256"]
        or render["document_sha256"]!=sha256_file(run/"paper/document.json") or structure["contract_sha256"]!=sha256_file(run/"problem_contract.json")):
        raise ValueError("stale or failed statistical/manuscript evidence")
    if visual_note:
        render["visual_review"]={"reviewer_type":"agent","status":"PASS","scope":visual_note,"pdf_sha256":render["pdf_sha256"]}
        write_json(run/"paper/render_report.json",render)
    summary={"case":"2021 B ethanol statistical reanalysis","source_hashes":read_json(run/"artifacts/observations.json")["source_hashes"],
        "group_rmse":{target:{name:row["metrics"]["group_rmse"] for name,row in value["models"].items()} for target,value in result["targets"].items()},
        "observed_candidates":{key:decisions[key] for key in ("observed_best","observed_below_350_best")},
        "low_temperature_boundary":next(x["below_350"] for x in decisions["local_models"] if x["group"]==decisions["polynomial_low_best"]),
        "verification":{"metric_comparisons":len(verification["comparisons"]),"source_anchors":verification["direct_workbook_anchors"],"passed":verification["passed"]},
        "split_sensitivity":{"summary":partitions["summary"],"additional_metric_checks":partitions["independent_metric_checks"],
                             "report_sha256":sha256_file(run/"artifacts/split_sensitivity/report.json")},
        "paper":{"pages":render["pages"],"sha256":render["pdf_sha256"],"visual_review":render["visual_review"],"structure_review":structure},
        "exposure_scope":"retrospective reanalysis after inspecting old 2021 B work; neither fresh blind evaluation nor prospective stage approval",
        "workflow_scope":"raw inputs and protocol frozen; state remains READING; generated evidence is not a sealed competition submission",
        "submission_ready":False,"national_award_level":"NOT_ESTABLISHED",
        "remaining":["new physical experiments and replication","actual human assessment","complete competition code appendix/support and AI disclosure","broader unseen task evaluation"]}
    write_json(run/"trial_summary.json",summary)
    print({"paper_pages":render["pages"],"independent_metric_comparisons":len(verification["comparisons"]),"submission_ready":False},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("run",type=Path);p.add_argument("--visual-note",default="")
    args=p.parse_args();finish(args.run,args.visual_note)
