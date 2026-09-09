"""Freeze the reviewed 2021 D statement and the explicit interpretation before solving."""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "skill/cumcm-reliable-paper/scripts"))
from engine import initialize_run, read_json, write_json, sha256_file

SOURCE_SHA256 = "e5d1447a36b0cb69d3b677aba037f617724303f13dbb2709793f63c54dc2a6ee"


def prepare(source, output):
    if sha256_file(source) != SOURCE_SHA256:
        raise ValueError("This benchmark encodes the reviewed two-page 2021 D statement; review a different source before using it")
    initialize_run(output, source, [], "2021 D 连铸切割在线优化历史题实测", "casting-2021d")
    facts = {"source_sha256": SOURCE_SHA256, "source_pages": 2,
             "tail_lengths_m": [109.0,93.4,80.9,72.0,62.7,52.5,44.9,42.7,31.6,22.7,14.5,13.7],
             "event_times_min": [0.0,45.6,98.6,131.5,190.8,233.3,266.0,270.7,327.9],
             "cases": {"Q2": {"target_m":9.5,"lower_m":9.0,"upper_m":10.0},
                       "Q3a": {"target_m":8.5,"lower_m":8.0,"upper_m":9.0},
                       "Q3b": {"target_m":11.1,"lower_m":10.6,"upper_m":11.6}},
             "primary_range_m": [4.8,12.6], "downstream_range_m": [8.0,11.6],
             "cut_minutes":3, "return_minutes":1, "speed_m_min":1,
             "mold_center_distance_m":60.0, "defect_length_m":.8,
             "assumptions": [
                 "Material coordinate equals saw-arrival time at speed 1 m/min; at t=0 the initial boundary cut at x=0 is already initiated and irrevocable.",
                 "The 0.8 m defective segment is centered at the stated mold center: event t reveals material interval [t+59.6,t+60.4].",
                 "Zero kerf; the statement supplies no kerf width. Offline cutting has no stated capacity/time bound.",
                 "The 4.8-12.6 m transport rule applies to every primary piece, including the terminal tail. No unstated exception for short tails.",
                 "Among equal waste, minimize the sum of squared deviations of recovered acceptable products from the user target; the statement does not uniquely specify this norm.",
                 "At an event, cuts with start time strictly before the notification are frozen; same-time notification is processed before a new cut.",
                 "At each notification optimize for currently known defects and healthy continuation thereafter; no future notifications enter the planner.",
                 "Online controls are on a declared 0.1 m/0.1 min grid; grid optimality is distinct from unrestricted continuous optimality."
             ]}
    write_json(output / "artifacts/facts.json", facts)
    audit = read_json(output / "source_audit.json")
    for row in audit["sources"]:
        row["manual_review"] = {"completed":True, "evidence":"Agent read both PDF pages and rendered figures 1-2; parameters and interpretation recorded in artifacts/facts.json. This does not grant human sign-off."}
    write_json(output / "source_audit.json", audit)
    contract = read_json(output / "problem_contract.json")
    contract.update(problem_interpretation="Separate primary transport pieces from defect-free offline recovery; preserve online information and executed cuts.",
                    official_outputs=["12 tail plans and waste", "9 event plans/adjustments at target 9.5 m", "9 event plans/adjustments for each of targets 8.5 and 11.1 m"],
                    questions=[{"id":q, "source_locator":"PDF page 2, question "+q[-1]+" and appendix; page 1 figures 1-2",
                                "objective":objective, "inputs":["artifacts/facts.json"], "outputs":[objective],
                                "decision_variables":["primary cut positions and offline recovered intervals"],
                                "hard_constraints":["primary length 4.8-12.6 m", "recovered product in user range and free of defects", "cut-start spacing >=4 min", "no revision of already initiated cuts"],
                                "units":["m", "min", "m^2 squared deviation"],
                                "ambiguities":facts["assumptions"], "termination_condition":"finite exact enumeration or finite acyclic state graph; independent loss/feasibility verification"}
                               for q,objective in [("Q1","minimize tail waste then squared length deviation"),("Q2","causal rolling cutting plans at 9.5 m target"),("Q3","causal rolling plans for both alternative targets")]])
    write_json(output / "problem_contract.json", contract)
    assumptions=read_json(output/"assumption_ledger.json")
    assumptions["items"]=[{"id":"A"+str(i+1),"text":value,"evidence":"Reviewed original statement; interpretation beyond explicit wording is identified in facts.json",
                           "impact":"Defines the conditional feasible set, timing or secondary preference", "status":"ACTIVE"}
                          for i,value in enumerate(facts["assumptions"])]
    write_json(output/"assumption_ledger.json",assumptions)
    methods={"Q1":("continuous count enumeration and convex allocation","cell-occupancy minimum-cost network LP"),
             "Q2":("causal lexicographic acyclic dynamic programming","network LP and continuous clean-interval waste bound"),
             "Q3":("causal dynamic programming for both target intervals","network LP and continuous clean-interval waste bound")}
    model=read_json(output/"model_plan.json")
    model["questions"]=[{"id":q,"baseline":"fixed target cuts followed by offline recovery",
                         "observed_bottleneck":"defect placement and immutable cuts interact with primary transport and target constraints",
                         "primary_method":pair[0],"independent_method":pair[1],
                         "validation_plan":"every interval and event prefix; network LP for grid objectives; continuous lower bound for total waste; grid and phase sensitivity",
                         "agreement_tolerance":{"atol":0,"rtol":0,"reason":"waste measured in exact rational/integer length units then converted once to meters"}}
                        for q,pair in methods.items()]
    write_json(output/"model_plan.json",model)
    write_json(output / "trial_clock.json", {"started_at":datetime.now(timezone.utc).isoformat(),
               "status":"RUNNING", "scope":"historical cross-family evaluation; statement read before the clock; not a blind or prospectively human-approved trial"})
    print({"frozen_source":SOURCE_SHA256, "run":str(output)}, flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    prepare(args.source,args.output)
