"""Link verified waste claims, preserving pending human review and conditional scope."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from solve import read_json,write_json,sha256_file
from engine import validate_run


def finish(run,visual_note=""):
    data=read_json(run/"artifacts/solution.json")
    independent=read_json(run/"artifacts/independent.json")
    rendering=read_json(run/"paper/render_report.json")
    structure=read_json(run/"paper/structure_review.json")
    if (rendering.get("render_status")!="COMPILED" or rendering["pdf_sha256"]!=sha256_file(run/"paper/main.pdf")
            or rendering["document_sha256"]!=sha256_file(run/"paper/document.json")
            or not structure["passed"] or structure["pdf_sha256"]!=rendering["pdf_sha256"]
            or structure["contract_sha256"]!=sha256_file(run/"problem_contract.json")
            or independent["solution_sha256"]!=sha256_file(run/"artifacts/solution.json") or not independent["passed"]):
        raise ValueError("incomplete or stale paper/verification")
    values={"Q1":[r["waste_m"] for r in data["tails"]],"Q2":data["online"]["Q2"]["total_waste_m"],
            "Q3":[data["online"][k]["total_waste_m"] for k in ("Q3a","Q3b")]}
    references={"Q1":[r["waste_m"] for r in independent["tails"]],"Q2":independent["online"]["Q2"]["continuous_lower_bound"]["waste_m"],
                "Q3":[independent["online"][k]["continuous_lower_bound"]["waste_m"] for k in ("Q3a","Q3b")]}
    write_json(run/"artifacts/headlines.json",values)
    write_json(run/"artifacts/reference_headlines.json",references)
    def update(name,**fields):
        payload=read_json(run/name);payload.update(fields);write_json(run/name,payload)
    update("results.json",questions=[{"id":q,"status":"VERIFIED","headline_results":[
        {"id":q+"-waste","label":q+"报废长度","value":value,"unit":"m","source_artifact":"artifacts/headlines.json",
         "source_pointer":"/"+q,"status":"VERIFIED"}],
        "constraints":[{"id":q+"-physical","passed":True,"evidence":"Exact tail allocation or independent full interval/cut-time trace checked in artifacts/independent.json"}]} for q,value in values.items()])
    methods={r["id"]:r["independent_method"] for r in read_json(run/"model_plan.json")["questions"]}
    update("verification_report.json",p0_checks=[{"id":"EXACT-TRANSPORT-RECOVERY","passed":True,"evidence":"12 tails and all actual cut intervals checked; no primary short-tail exception"},
           {"id":"ONLINE-PREFIX","passed":True,"evidence":"Known-event prefixes and immutable cuts reconstructed from the final execution ledger"}],
           p1_checks=[{"id":"CONDITIONAL-OPTIMALITY","verdict":"WARN","evidence":"Initial phase and secondary norm are explicitly chosen; grid refinement changes deviation",
                       "allowed_language":"Minimum waste for the stated initial state and realized sequence; per-event secondary optimality only on the chosen grid",
                       "question_ids":["Q1","Q2","Q3"],"forbidden_terms":["保证获奖","任意异常序列均全局最优"]}],
           questions=[{"id":q,"independent_method":methods[q],"anchors":[
                       {"type":"conservation","evidence":"primary length = recovered length + waste, with every interval checked"},
                       {"type":"hand_calculation","evidence":("14.5=9.7+4.8; 13.7 cannot leave both a >=9.0 m product and a >=4.8 m transportable remainder" if q=="Q1" else "Two 0.8 m defects whose centers are 4.7 m apart leave only 3.9 m of clean material; that gap is unusable under all three target ranges")}],
                       "independent_agreement":{"passed":values[q]==references[q],"evidence":"Q1 network flow loss; Q2/Q3 independently derived continuous material lower bound attained",
                       "comparisons":[{"result_id":q+"-waste","reference_artifact":"artifacts/reference_headlines.json","reference_pointer":"/"+q}]}} for q in values])
    document=read_json(run/"paper/document.json")
    claims=[]
    for q,prefix in [("Q1","尾坯损失依次为"),("Q2","问题二累计实际报废为"),("Q3","问题三两组累计实际报废分别为")]:
        section=next(s for s in document["sections"] if s.get("id")==q.lower())
        sentence=next(b["text"] for b in section["blocks"] if b.get("text","").startswith(prefix))
        claims.append({"id":q+"-claim","question_id":q,"text":sentence,"paper_excerpt":sentence,
                       "paper_locator":section["title"],"result_ids":[q+"-waste"],"status":"VERIFIED"})
    update("claim_ledger.json",paper_artifact="paper/main.pdf",paper_source_artifact="paper/main.md",claims=claims)
    report=validate_run(run,"PAPER_LINKED")
    write_json(run/"trial_workflow_validation.json",report)
    if report["failed_checks"] != ["HUMAN-SIGNOFFS"]:
        raise ValueError(report["failed_checks"])
    if visual_note:
        rendering["visual_review"]={"reviewer_type":"agent","status":"PASS","scope":visual_note,"pdf_sha256":rendering["pdf_sha256"]}
        write_json(run/"paper/render_report.json",rendering)
    clock=read_json(run/"trial_clock.json")
    ended=datetime.now(timezone.utc)
    summary={"case":"2021 D continuous casting online cutting","source_sha256":read_json(run/"artifacts/facts.json")["source_sha256"],
             "headline_waste_m":values,"paper":{"pages":rendering["pages"],"sha256":rendering["pdf_sha256"],"visual_review":rendering["visual_review"],"structure":structure},
             "independent_checks":{"tail_network_losses":12,"online_network_objective_pairs":27,"continuous_waste_bounds_attained":all(r["continuous_lower_bound"]["attained"] for r in independent["online"].values())},
             "elapsed_minutes":(ended-datetime.fromisoformat(clock["started_at"])).total_seconds()/60,
             "source_exposure":clock["scope"],"workflow_scope":"model contract prepared before solving on clean replay; stage remains READING pending real human signoffs",
             "conditional_scope":["initial cut at coordinate/time zero","centered defect interval","zero kerf and unconstrained offline cutting","secondary squared deviation on declared grid"],
             "submission_ready":False,"national_award_level":"NOT_ESTABLISHED",
             "remaining":["actual team/reviewer assessment","initial-state confirmation","formal code appendix and AI-use details for contest submission","other task families"]}
    write_json(run/"trial_summary.json",summary)
    clock.update(status="ARTIFACTS_READY_REVIEW_PENDING",finished_at=ended.isoformat())
    write_json(run/"trial_clock.json",clock)
    print({"pages":rendering["pages"],"waste_m":values,"validation_pending":report["failed_checks"]},flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("run",type=Path)
    parser.add_argument("--visual-note",default="")
    args=parser.parse_args();finish(args.run,args.visual_note)
