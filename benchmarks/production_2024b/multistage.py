"""Exact moment recursion for a tree with persistent reusable items and perfect inspection.

Each supplied item has cost, bad probability, inspection cost and conditional repair
cost after it has been found bad. On dismantling, inspect every unknown immediate
child and repair the bad ones; already known-good children are not inspected again.
"""
import argparse
from fractions import Fraction as F
from itertools import product
from pathlib import Path
from prepare import read_json,write_json,sha256_file,SOURCE_HASH


def leaf(rate,purchase,inspection,tested):
    p=F(str(rate));c=F(purchase);t=F(inspection)
    if not 0<=p<1:raise ValueError("leaf defect rate must lie in [0,1)")
    good_cost=(c+t)/(1-p)
    return {"cost":good_cost if tested else c,"bad":F(0) if tested else p,
            "test":t,"repair_bad":good_cost,"known":bool(tested)}


def assembly(children,rate,cost,inspection,dismantle_cost,tested,dismantle):
    p=F(str(rate));a=F(cost);t=F(inspection);d=F(dismantle_cost)
    if not children or not 0<=p<1:raise ValueError("invalid assembly specification")
    success=1-p
    for child in children:success*=1-child["bad"]
    bad=1-success;purchase=sum(c["cost"] for c in children)
    if dismantle:
        inspect_unknown=sum(c["test"] for c in children if not c["known"])
        # child bad => parent bad; conditioned marginal repair contributions add.
        bad_repair=sum(c["bad"]*c["repair_bad"] for c in children)
        repair=d+inspect_unknown+(bad_repair/bad if bad else 0)+(a+t+p*d)/(1-p)
        ensured=purchase+a+t+bad*repair
    else:
        ensured=(purchase+a+t)/success
        repair=ensured
    return {"cost":ensured if tested else purchase+a,"bad":F(0) if tested else bad,
            "test":t,"repair_bad":repair,"known":bool(tested)}


def order_cost(children,rate,cost,inspection,dismantle_cost,exchange_loss,tested,dismantle):
    p=F(str(rate));a=F(cost);t=F(inspection);d=F(dismantle_cost);loss=F(exchange_loss)
    if not children or not 0<=p<1:raise ValueError("invalid final assembly")
    success=1-p
    for c in children:success*=1-c["bad"]
    bad=1-success;purchase=sum(c["cost"] for c in children);shipping_loss=(1-tested)*loss
    if not dismantle:return (purchase+a+tested*t+bad*shipping_loss)/success
    inspect_unknown=sum(c["test"] for c in children if not c["known"])
    weighted_repair=sum(c["bad"]*c["repair_bad"] for c in children)
    known_children_completion=(a+tested*t+p*(d+shipping_loss))/(1-p)
    return purchase+a+tested*t+weighted_repair+bad*(shipping_loss+d+inspect_unknown+known_children_completion)


def source_tree():
    prices=(2,8,12,2,8,12,8,12);tests=(1,1,2,1,1,2,1,2)
    return {"parts":[{"id":str(i+1),"p":.1,"purchase":c,"test":t} for i,(c,t) in enumerate(zip(prices,tests))],
            "semis":[{"id":str(i+1),"children":children,"p":.1,"assembly":8,"test":4,"dismantle":6} for i,children in enumerate(((0,1,2),(3,4,5),(6,7)))],
            "final":{"p":.1,"assembly":8,"test":6,"dismantle":10,"exchange_loss":40,"price":200}}


def supply_choices(tree,index):
    node=tree["semis"][index];choices=[]
    for part_tests in product((0,1),repeat=len(node["children"])):
        children=[leaf(part["p"],part["purchase"],part["test"],test) for part,test in
                  zip([tree["parts"][i] for i in node["children"]],part_tests)]
        for test,dismantle in product((0,1),repeat=2):
            choices.append({"part_tests":list(part_tests),"test":test,"dismantle":dismantle,
                            "moment":assembly(children,node["p"],node["assembly"],node["test"],node["dismantle"],test,dismantle)})
    return choices


def plan_record(combination,test,dismantle,value,price):
    return {"part_tests":[v for choice in combination for v in choice["part_tests"]],
            "semi_tests":[c["test"] for c in combination],"semi_dismantle":[c["dismantle"] for c in combination],
            "final_test":test,"final_dismantle":dismantle,"cost_exact":str(value),"expected_cost":float(value),
            "profit":float(F(price)-value),"recovery_rule":"inspect each unknown immediate child after dismantling; repair bad children to known-good; preserve known-good items"}


def optimize(tree):
    choices=[supply_choices(tree,i) for i in range(len(tree["semis"]))]
    final=tree["final"];best=None;winners=[];count=0;baselines={}
    for combination in product(*choices):
        children=[c["moment"] for c in combination]
        for test,dismantle in product((0,1),repeat=2):
            value=order_cost(children,final["p"],final["assembly"],final["test"],final["dismantle"],final["exchange_loss"],test,dismantle)
            count+=1
            if best is None or value<best:best=value;winners=[]
            if value==best:winners.append(plan_record(combination,test,dismantle,value,final["price"]))
            all_tests=[v for c in combination for v in c["part_tests"]]+[c["test"] for c in combination]+[test]
            all_d=[c["dismantle"] for c in combination]+[dismantle]
            if not any(all_tests+all_d):baselines["no_inspection_no_recovery"]=plan_record(combination,test,dismantle,value,final["price"])
            if all(all_tests+all_d):baselines["inspect_and_recover_everywhere"]=plan_record(combination,test,dismantle,value,final["price"])
    return {"policy_count":count,"best_policies":winners,"baselines":baselines,
            "scope":"exact optimum among declared fresh-inspection/dismantle policies with all unknown recovered children inspected; not a theorem over all history-dependent production policies"}


def solve(run):
    if sha256_file(run/"sources/problem__B题.pdf")!=SOURCE_HASH:raise ValueError("original source changed")
    folder=run/"artifacts/multistage";folder.mkdir(exist_ok=False)
    tree=source_tree()
    write_json(folder/"protocol.json",{"source_sha256":SOURCE_HASH,"tree":tree,
        "policy":"8 fresh part inspections, 3 fresh semi inspections, 3 semi dismantles, final inspection and dismantle; recovered unknown children always inspected",
        "assumptions":["independent purchase quality and per-attempt conditional assembly failures","zero inspection error","dismantling preserves item quality and prior known-good status","no shared parts across branches, no time/capacity/holding costs","one sale per fulfilled order; replacements free plus specified loss"],
        "simulation":{"orders":50000,"seeds":[20240911,20240912],"threshold":"6 sample standard errors + 0.02 yuan"}})
    result=optimize(tree);result["protocol_sha256"]=sha256_file(folder/"protocol.json")
    write_json(folder/"result.json",result)
    print({"policies":result["policy_count"],"best":result["best_policies"]},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);solve(p.parse_args().run)
