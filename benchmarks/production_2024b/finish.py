"""Record four-question coverage and verification while preserving conditional scope."""
import argparse
from pathlib import Path
from prepare import read_json,write_json,sha256_file
from prior_sensitivity import checked_report
from exact_study import checked_report as checked_exact_report


def finish(run,visual_note=""):
    prior=checked_report(run)
    exact=checked_exact_report(run)
    figures=read_json(run/"artifacts/figures/figure_evidence.json")
    if figures["source_result_sha256"]!=sha256_file(run/"artifacts/multistage/result.json") or figures["source_protocol_sha256"]!=sha256_file(run/"artifacts/multistage/protocol.json"):
        raise ValueError("figure evidence predates current numerical sources")
    for name,digest in figures["figure_sha256"].items():
        if sha256_file(run/"artifacts/figures"/name)!=digest:raise ValueError("figure file changed")
    rendering=read_json(run/"paper/render_report.json");structure=read_json(run/"paper/structure_review.json")
    if rendering["render_status"]!="COMPILED" or rendering["pdf_sha256"]!=sha256_file(run/"paper/main.pdf") or rendering["document_sha256"]!=sha256_file(run/"paper/document.json"):
        raise ValueError("paper render is stale")
    if not structure["passed"] or structure["pdf_sha256"]!=rendering["pdf_sha256"] or structure["contract_sha256"]!=sha256_file(run/"problem_contract.json"):
        raise ValueError("four-question structure not verified")
    first=read_json(run/"artifacts/verification.json");third=read_json(run/"artifacts/multistage/verification.json");fourth=read_json(run/"artifacts/q4_summary.json")
    if not first["passed"] or not third["passed"] or first["rework_sha256"]!=sha256_file(run/"artifacts/rework.json") or third["result_sha256"]!=sha256_file(run/"artifacts/multistage/result.json"):
        raise ValueError("production numerical verification is stale")
    for folder,digest in fourth["source_results"].items():
        p=run/"artifacts"/folder;verification=read_json(p/"verification.json")
        if sha256_file(p/"result.json")!=digest or verification["result_sha256"]!=digest or not verification["passed"]:raise ValueError("Q4 independent checks are stale")
    if visual_note:
        rendering["visual_review"]={"reviewer_type":"agent","scope":visual_note,"status":"PASS","pdf_sha256":rendering["pdf_sha256"]}
        write_json(run/"paper/render_report.json",rendering)
    result={"case":"2024 B production decisions, four-question conditional training paper","paper":{"pages":rendering["pages"],"sha256":rendering["pdf_sha256"],"visual_review":rendering["visual_review"],"structure":structure},
        "source_sha256":read_json(run/"artifacts/facts.json")["source_sha256"],
        "q1_q2":{"sampling_quadrature_checks":len(first["quadrature_checks"]),"simulated_orders":sum(r["orders"] for r in first["simulations"])},
        "q3":{"policy_count":65536,"best_policy":read_json(run/"artifacts/multistage/result.json")["best_policies"][0],"simulated_orders":sum(r["orders"] for r in third["checks"])},
        "q4":{"input_scope":fourth["scope"],"scenarios":fourth["scenarios"]},
        "prior_sensitivity":{"report_sha256":sha256_file(run/"artifacts/prior_sensitivity/report.json"),"results":prior["results"],"scope":prior["scope"]},
        "exact_posterior":{"summary_sha256":sha256_file(run/"artifacts/exact_posterior/summary.json"),"scenario_count":len(exact["scenarios"]),
                           "all_previous_selected_policies_optimal":all(c["old_mc_policy_optimal"] for s in exact["scenarios"] for c in s["mc_policy_comparisons"]),"scope":exact["scope"]},
        "figure_evidence":figures,
        "workflow_scope":"source-frozen historical analysis and numerical checks; workflow stage remains READING, no human signoffs fabricated",
        "remaining":["actual Q4 sample counts and sampling-design/priors assessment","complete code appendix and formal AI details","team/reviewer assessment and current contest submission checks"],
        "submission_ready":False,"national_award_level":"NOT_ESTABLISHED"}
    write_json(run/"four-question-summary.json",result)
    print({"paper_pages":rendering["pages"],"q4_actual_observations_available":False,"submission_ready":False},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);p.add_argument("--visual-note",default="");args=p.parse_args();finish(args.run,args.visual_note)
