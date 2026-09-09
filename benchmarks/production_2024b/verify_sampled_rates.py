"""Deterministic Beta quadrature and an analytic all-tested hierarchy expectation."""
import argparse
from itertools import product
from pathlib import Path
import numpy as np
from scipy.special import roots_jacobi
from prepare import read_json,write_json,sha256_file
from sampled_rates import counts_parameters,case_tree,evaluate


def quadrature(parameters,order):
    if len(parameters)!=3:raise ValueError("tensor quadrature is limited to the three Q2 rates")
    points=[];weights=[]
    for a,b in parameters:
        x,w=roots_jacobi(order,b-1,a-1)
        points.append((x+1)/2);weights.append(w/w.sum())
    rates=np.stack(np.meshgrid(*points,indexing="ij"),axis=-1).reshape(-1,3)
    w1,w2,w3=np.meshgrid(*weights,indexing="ij")
    return rates,(w1*w2*w3).ravel()


def posterior_costs(tree,parameters,order):
    rates,weights=quadrature(parameters,order);results=[]
    for t1,t2,tf,d in product((0,1),repeat=4):
        policy={"part_tests":[t1,t2],"semi_tests":[],"semi_dismantle":[],"final_test":tf,"final_dismantle":d}
        results.append({"policy":policy,"posterior_mean_cost":float(weights@evaluate(tree,policy,rates))})
    return results


def all_tested_expectation(tree,parameters,final_test):
    parameters=np.asarray(parameters,float)
    if parameters.ndim!=2 or parameters.shape[1]!=2 or not np.isfinite(parameters).all() or np.any(parameters<=0) or np.any(parameters[:,1]<=1):
        raise ValueError("finite analytic inverse-good-rate expectation requires positive shapes and beta>1")
    if len(parameters)!=len(tree["parts"])+len(tree["semis"])+1:raise ValueError("wrong posterior count")
    inv=(parameters.sum(axis=1)-1)/(parameters[:,1]-1)
    odds=parameters[:,0]/(parameters[:,1]-1)
    value=sum((part["purchase"]+part["test"])*inv[i] for i,part in enumerate(tree["parts"]))
    for i,node in enumerate(tree["semis"],len(tree["parts"])):
        value+=(node["assembly"]+node["test"])*inv[i]+node["dismantle"]*odds[i]
    node=tree["final"]
    value+=(node["assembly"]+final_test*node["test"])*inv[-1]+(node["dismantle"]+(1-final_test)*node["exchange_loss"])*odds[-1]
    return float(value)


def verify(run,folder):
    facts=read_json(run/"artifacts/facts.json");protocol=read_json(folder/"protocol.json");result=read_json(folder/"result.json")
    if result["protocol_sha256"]!=sha256_file(folder/"protocol.json") or result["candidates_sha256"]!=sha256_file(folder/"candidates.json"):raise ValueError("Q4 protocol/candidates changed")
    checks=[];q2=[]
    for c in facts["cases"]:
        name="Q2-"+str(c["case"]);row=result["results"][name];tree=case_tree(c);parameters=np.array(row["posterior_parameters"])
        coarse=posterior_costs(tree,parameters,16);fine=posterior_costs(tree,parameters,32)
        difference=max(abs(a["posterior_mean_cost"]-b["posterior_mean_cost"]) for a,b in zip(coarse,fine))
        if difference>1e-8:raise ValueError("Q2 posterior quadrature did not converge at predeclared tolerance")
        selected=next(r["posterior_mean_cost"] for r in fine if r["policy"]==row["selected_policy"])
        minimum=min(r["posterior_mean_cost"] for r in fine)
        error=abs(selected-row["selected"]["posterior_mean_cost"]);limit=6*row["selected"]["integration_standard_error"]+.02
        checks.append({"problem":name,"method":"16/32 point per axis Gauss-Jacobi Beta quadrature", "convergence_max_error":difference,
                       "quadrature_selected_cost":selected,"quadrature_minimum_cost":minimum,"selected_gap":selected-minimum,
                       "monte_carlo_error":error,"allowed_error":limit,"passed":error<=limit})
        q2.append({"case":c["case"],"all_policy_costs":fine})
    from multistage import source_tree
    row=result["results"]["Q3"];policy=row["selected_policy"]
    if not all(policy["part_tests"]+policy["semi_tests"]+policy["semi_dismantle"]+[policy["final_dismantle"]]):
        q3={"status":"not_applicable","scope":"closed form verifies all upstream inspections and all dismantles only"}
    else:
        value=all_tested_expectation(source_tree(),np.array(row["posterior_parameters"]),policy["final_test"])
        error=abs(value-row["selected"]["posterior_mean_cost"]);limit=6*row["selected"]["integration_standard_error"]+.02
        q3={"status":"checked","analytic_cost":value,"monte_carlo_error":error,"allowed_error":limit,"passed":error<=limit}
        checks.append({"problem":"Q3","method":"analytic Beta inverse-good-rate moments",**q3})
    report={"passed":all(c["passed"] for c in checks),"checks":checks,"q2_quadrature":q2,"q3_analytic":q3,
            "result_sha256":sha256_file(folder/"result.json"),"scope":"deterministic integration confirms selected Q2 expected costs and ranks, plus analytic expectation for the applicable selected Q3 policy; underlying conditional cost formula verified against rational models in tests"}
    write_json(folder/"verification.json",report)
    if not report["passed"]:raise ValueError("independent Q4 integration comparison failed")
    print({"passed":report["passed"],"q2_selected_gaps":[r["selected_gap"] for r in checks if "selected_gap" in r],"q3":q3},flush=True)
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);p.add_argument("folder",type=Path);args=p.parse_args();verify(args.run,args.folder)
