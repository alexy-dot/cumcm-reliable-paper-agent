"""Item-tree simulation independent of the expected-moment solver."""
import argparse
import math
import random
from pathlib import Path
from prepare import read_json,write_json,sha256_file


def simulate_tree(tree,policy,orders,seed):
    rng=random.Random(seed)
    nodes={"p"+str(i):{"kind":"part",**node} for i,node in enumerate(tree["parts"])}
    for i,node in enumerate(tree["semis"]):nodes["s"+str(i)]={"kind":"semi",**node,"children":["p"+str(j) for j in node["children"]]}
    nodes["f"]={"kind":"final",**tree["final"],"children":["s"+str(i) for i in range(len(tree["semis"]))]}
    tests={**{"p"+str(i):v for i,v in enumerate(policy["part_tests"])},**{"s"+str(i):v for i,v in enumerate(policy["semi_tests"])},"f":policy["final_test"]}
    dismantle={**{"s"+str(i):v for i,v in enumerate(policy["semi_dismantle"])},"f":policy["final_dismantle"]}
    totals=[];category_sums={};returns=0
    for _ in range(orders):
        costs={};operations=0
        def charge(key,value):
            nonlocal operations
            operations+=1
            if operations>100000:raise ValueError("order did not complete; never report a capped path as a fulfilled order")
            costs[key]=costs.get(key,0.)+value
        def build(key,force_test=False):
            node=nodes[key];test=tests[key] or force_test
            if node["kind"]=="part":
                while True:
                    charge("purchase",node["purchase"]);good=rng.random()>=node["p"]
                    if test:
                        charge("part_inspection",node["test"])
                        if not good:continue
                    return {"key":key,"good":good,"known":bool(test),"children":[]}
            children=[build(child) for child in node["children"]]
            charge("semi_assembly",node["assembly"])
            good=all(c["good"] for c in children) and rng.random()>=node["p"]
            item={"key":key,"good":good,"known":False,"children":children}
            if test:
                charge("semi_inspection",node["test"])
                if not good:return repair(item)
                item["known"]=True
            return item
        def recover_children(item):
            recovered=[]
            for child in item["children"]:
                if not child["known"]:
                    node=nodes[child["key"]]
                    charge("part_inspection" if node["kind"]=="part" else "semi_inspection",node["test"])
                    if not child["good"]:child=repair(child)
                    child["known"]=True
                recovered.append(child)
            return recovered
        def repair(item):
            node=nodes[item["key"]]
            if node["kind"]=="part" or not dismantle[item["key"]]:return build(item["key"],True)
            charge("semi_dismantle",node["dismantle"])
            children=recover_children(item)
            while True:
                charge("semi_assembly",node["assembly"]);charge("semi_inspection",node["test"])
                good=all(c["good"] for c in children) and rng.random()>=node["p"]
                if good:return {"key":item["key"],"good":True,"known":True,"children":children}
                charge("semi_dismantle",node["dismantle"])
        node=nodes["f"];children=[build(key) for key in node["children"]]
        while True:
            charge("final_assembly",node["assembly"])
            if tests["f"]:charge("final_inspection",node["test"])
            good=all(c["good"] for c in children) and rng.random()>=node["p"]
            if good:break
            if not tests["f"]:charge("customer_exchange_loss",node["exchange_loss"]);returns+=1
            if not dismantle["f"]:children=[build(key) for key in node["children"]];continue
            charge("final_dismantle",node["dismantle"])
            children=recover_children({"children":children})
        total=math.fsum(costs.values());totals.append(total)
        for key,value in costs.items():category_sums[key]=category_sums.get(key,0.)+value
    mean=math.fsum(totals)/orders;variance=math.fsum((value-mean)**2 for value in totals)/(orders-1)
    return {"orders":orders,"seed":seed,"mean_cost":mean,"standard_error":math.sqrt(variance/orders),
            "mean_customer_returns":returns/orders,"cost_components":{k:v/orders for k,v in sorted(category_sums.items())}}


def verify(run):
    folder=run/"artifacts/multistage";protocol=read_json(folder/"protocol.json");result=read_json(folder/"result.json")
    if result["protocol_sha256"]!=sha256_file(folder/"protocol.json"):raise ValueError("model protocol changed")
    selected=[("best",result["best_policies"][0]),*result["baselines"].items()]
    checks=[]
    for name,policy in selected:
        seeds=protocol["simulation"]["seeds"] if name=="best" else protocol["simulation"]["seeds"][:1]
        for seed in seeds:
            estimate=simulate_tree(protocol["tree"],policy,protocol["simulation"]["orders"],seed)
            error=abs(estimate["mean_cost"]-policy["expected_cost"]);limit=6*estimate["standard_error"]+.02
            checks.append({"policy":name,"expected_cost":policy["expected_cost"],**estimate,"absolute_error":error,"allowed_error":limit,"passed":error<=limit})
            print(name,seed,"exact",policy["expected_cost"],"simulation",estimate["mean_cost"],"passed",error<=limit,flush=True)
    report={"passed":all(c["passed"] for c in checks),"checks":checks,"result_sha256":sha256_file(folder/"result.json"),
            "scope":"independent object-level simulation retaining full internal item trees and observed quality; finite-sample numerical agreement, not field validation"}
    write_json(folder/"verification.json",report)
    if not report["passed"]:raise ValueError("multistage simulation disagrees with exact recursion")
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);verify(p.parse_args().run)
