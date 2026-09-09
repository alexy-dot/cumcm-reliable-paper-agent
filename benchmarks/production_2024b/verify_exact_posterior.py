"""Compare exact posterior recursion with independent quadrature and prior MC outputs."""
import argparse
from fractions import Fraction as F
from pathlib import Path
import numpy as np
from prepare import read_json,write_json,sha256_file
from sampled_rates import case_tree
from multistage import source_tree
from exact_posterior import evaluate
from verify_sampled_rates import posterior_costs,all_tested_expectation


def verify(run,exact_folder,mc_folder):
    exact=read_json(exact_folder/"result.json");protocol=read_json(exact_folder/"protocol.json")
    mc=read_json(mc_folder/"result.json");mc_protocol=read_json(mc_folder/"protocol.json")
    if exact["protocol_sha256"]!=sha256_file(exact_folder/"protocol.json") or mc["protocol_sha256"]!=sha256_file(mc_folder/"protocol.json"):
        raise ValueError("posterior protocol changed")
    if protocol["samples"]!=mc_protocol["samples"]:raise ValueError("cannot compare different counts or priors")
    checks=[];selection=[]
    for case in read_json(run/"artifacts/facts.json")["cases"]:
        name="Q2-"+str(case["case"]);r=exact["results"][name];params=np.array([[float(F(a)),float(F(b))] for a,b in r["posterior_shapes"]])
        quadrature=posterior_costs(case_tree(case),params,32)
        for row in r["q2_all_policies"]:
            reference=next(v["posterior_mean_cost"] for v in quadrature if v["policy"]==row["policy"])
            error=abs(reference-row["expected_cost"])
            checks.append({"problem":name,"policy":row["policy"],"absolute_error":error,"passed":error<=1e-8})
        old_cost=evaluate(case_tree(case),mc["results"][name]["selected_policy"],[(F(a),F(b)) for a,b in r["posterior_shapes"]])
        best=F(r["best_policies"][0]["cost_exact"])
        selection.append({"problem":name,"old_mc_policy_exact_gap":str(old_cost-best),"old_mc_policy_optimal":old_cost==best})
    r=exact["results"]["Q3"];params=[(F(a),F(b)) for a,b in r["posterior_shapes"]];policy=r["best_policies"][0]["policy"]
    if not all(policy["part_tests"]+policy["semi_tests"]+policy["semi_dismantle"]+[policy["final_dismantle"]]):
        raise ValueError("this scenario needs a different independent Q3 verification anchor")
    reference=all_tested_expectation(source_tree(),np.array(params,float),policy["final_test"])
    error=abs(reference-r["best_policies"][0]["expected_cost"])
    checks.append({"problem":"Q3","method":"separate all-upstream-tested analytic Beta expectation","absolute_error":error,"passed":error<=1e-8})
    old_cost=evaluate(source_tree(),mc["results"]["Q3"]["selected_policy"],params);best=F(r["best_policies"][0]["cost_exact"])
    selection.append({"problem":"Q3","old_mc_policy_exact_gap":str(old_cost-best),"old_mc_policy_optimal":old_cost==best})
    report={"passed":all(c["passed"] for c in checks),"checks":checks,"mc_policy_comparisons":selection,
            "exact_result_sha256":sha256_file(exact_folder/"result.json"),"old_mc_result_sha256":sha256_file(mc_folder/"result.json"),
            "scope":"all Q2 policy costs checked by deterministic integration, selected Q3 cost by a separate analytic formula; general recursion additionally checked on mixed two-layer policies"}
    write_json(exact_folder/"verification.json",report)
    if not report["passed"]:raise ValueError("exact posterior integration failed independent comparison")
    print({"comparisons":len(checks),"passed":True,"old_mc_optimal":all(r["old_mc_policy_optimal"] for r in selection)},flush=True)
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);p.add_argument("exact_folder",type=Path);p.add_argument("mc_folder",type=Path)
    args=p.parse_args();verify(args.run,args.exact_folder,args.mc_folder)
