"""Exact posterior expectations for the declared independent-rate assembly policies.

This integrates the conditional cost recursion algebraically with rational Beta
moments; it does not replace random rates with their means or call the MC scorer.
"""
import argparse
from fractions import Fraction as F
from itertools import product
from math import prod
from pathlib import Path
from prepare import read_json,write_json,sha256_file
from multistage import source_tree


def shapes(records,bases,prior):
    a,b=F(str(prior["alpha"])),F(str(prior["beta"]))
    if min(a,b)<=0 or len(records)!=len(bases):raise ValueError("positive prior shapes and complete stage records required")
    result=[]
    for record,basis in zip(records,bases):
        n,k=record["n"],record["k"]
        if type(n) is not int or type(k) is not int or n<=0 or not 0<=k<=n or record.get("basis")!=basis:
            raise ValueError("invalid counts or incompatible sampling condition")
        posterior=(a+k,b+n-k)
        if posterior[1]<=1:raise ValueError("inverse-good-rate expectation diverges: beta must exceed one")
        result.append(posterior)
    return result


def rate_moments(shape):
    a,b=map(F,shape)
    if a<=0 or b<=1:raise ValueError("positive alpha and beta>1 required")
    return b/(a+b),(a+b-1)/(b-1)


def leaf_moments(shape,c,t,tested):
    g,inv=rate_moments(shape);c,t=F(c),F(t)
    if tested:
        cost=(c+t)*inv
        return {"C":cost,"g":F(1),"inv_g":F(1),"C_over_g":cost,"w":F(0),"known":True,"test":t}
    return {"C":c,"g":g,"inv_g":inv,"C_over_g":c*inv,"w":(c+t)*(inv-1),"known":False,"test":t}


def child_products(children):
    eg=prod(c["g"] for c in children);inverse=prod(c["inv_g"] for c in children)
    cost_cross=sum(c["C_over_g"]*prod(other["inv_g"] for j,other in enumerate(children) if j!=i) for i,c in enumerate(children))
    return eg,inverse,cost_cross


def assembly_moments(children,shape,a,t,d,tested,dismantle):
    r,inv_r=rate_moments(shape);a,t,d=map(F,(a,t,d))
    eg,inv,cross=child_products(children);purchase=sum(c["C"] for c in children)
    if dismantle:
        unknown=sum(c["test"] for c in children if not c["known"])
        w=sum(c["w"] for c in children)+unknown*(1-r*eg)+(a+t+d)*(inv_r-eg)
    else:
        w=inv_r*(cross+(a+t)*inv)-(purchase+a+t)
    if tested:
        cost=purchase+a+t+w
        return {"C":cost,"g":F(1),"inv_g":F(1),"C_over_g":cost,"w":F(0),"known":True,"test":t}
    return {"C":purchase+a,"g":r*eg,"inv_g":inv_r*inv,"C_over_g":inv_r*(cross+a*inv),
            "w":w,"known":False,"test":t}


def finish_cost(children,shape,node,tested,dismantle):
    r,inv_r=rate_moments(shape);eg,inv,cross=child_products(children)
    a,t,d,L=[F(node[key]) for key in ("assembly","test","dismantle","exchange_loss")]
    loss=(1-tested)*L;purchase=sum(c["C"] for c in children)
    if not dismantle:return inv_r*(cross+(a+tested*t+loss)*inv)-loss
    unknown=sum(c["test"] for c in children if not c["known"])
    return purchase+a+tested*t+sum(c["w"] for c in children)+unknown*(1-r*eg)+(a+tested*t+d+loss)*(inv_r-eg)


def evaluate(tree,policy,parameters):
    parts=[leaf_moments(parameters[i],p["purchase"],p["test"],policy["part_tests"][i]) for i,p in enumerate(tree["parts"])]
    semis=[assembly_moments([parts[j] for j in n["children"]],parameters[len(parts)+i],n["assembly"],n["test"],n["dismantle"],policy["semi_tests"][i],policy["semi_dismantle"][i]) for i,n in enumerate(tree["semis"])]
    return finish_cost(semis if semis else parts,parameters[-1],tree["final"],policy["final_test"],policy["final_dismantle"])


def optimize(tree,parameters):
    if len(parameters)!=len(tree["parts"])+len(tree["semis"])+1:raise ValueError("posterior stage count mismatch")
    options=[]
    if tree["semis"]:
        for i,node in enumerate(tree["semis"]):
            choices=[]
            for flags in product((0,1),repeat=len(node["children"])):
                children=[leaf_moments(parameters[j],tree["parts"][j]["purchase"],tree["parts"][j]["test"],flag) for j,flag in zip(node["children"],flags)]
                for test,d in product((0,1),repeat=2):
                    choices.append((flags,test,d,assembly_moments(children,parameters[len(tree["parts"])+i],node["assembly"],node["test"],node["dismantle"],test,d)))
            options.append(choices)
    else:
        for i,node in enumerate(tree["parts"]):
            options.append([((flag,),None,None,leaf_moments(parameters[i],node["purchase"],node["test"],flag)) for flag in (0,1)])
    best=None;winners=[];count=0;all_q2=[]
    for combination in product(*options):
        for tested,d in product((0,1),repeat=2):
            cost=finish_cost([c[3] for c in combination],parameters[-1],tree["final"],tested,d);count+=1
            policy={"part_tests":[v for c in combination for v in c[0]],"semi_tests":[c[1] for c in combination] if tree["semis"] else [],
                    "semi_dismantle":[c[2] for c in combination] if tree["semis"] else [],"final_test":tested,"final_dismantle":d}
            record={"policy":policy,"cost_exact":str(cost),"expected_cost":float(cost),"expected_profit":float(F(tree["final"]["price"])-cost)}
            if not tree["semis"]:all_q2.append(record)
            if best is None or cost<best:best=cost;winners=[]
            if cost==best:winners.append(record)
    return {"policy_count":count,"best_policies":winners,"q2_all_policies":all_q2,
            "scope":"exact posterior-mean optimum within the same declared stationary recovery class, under independent Beta stage parameters; not unrestricted adaptive policy optimality"}


def solve(run,samples_path,output):
    from sampled_rates import case_tree
    sample=read_json(samples_path);facts=read_json(run/"artifacts/facts.json")
    if not isinstance(sample.get("provenance"),str) or not sample["provenance"].strip():raise ValueError("sample provenance required")
    if set(sample["q2"])!={str(c["case"]) for c in facts["cases"]}:raise ValueError("all six Q2 sample cases required")
    problems=[("Q2-"+str(c["case"]),case_tree(c),sample["q2"][str(c["case"])]) for c in facts["cases"]]+[("Q3",source_tree(),sample["q3"])]
    params={name:shapes(records,["random_supply"]*len(tree["parts"])+["good_inputs"]*(len(tree["semis"])+1),sample["prior"]) for name,tree,records in problems}
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/"protocol.json",{"samples":sample,"samples_sha256":sha256_file(samples_path),"facts_sha256":sha256_file(run/"artifacts/facts.json"),
         "method":"rational recursion of E(C), E(g), E(1/g), E(C/g), E(bR)","finite_moment_condition":"all posterior beta>1; no finite variance assumption or Monte Carlo standard error is used"})
    result={}
    for name,tree,_ in problems:
        result[name]=optimize(tree,params[name]);result[name]["posterior_shapes"]=[[str(a),str(b)] for a,b in params[name]]
        print(name,"exact cost",result[name]["best_policies"][0]["cost_exact"],flush=True)
    payload={"protocol_sha256":sha256_file(output/"protocol.json"),"results":result,"sample_provenance":sample["provenance"],"submission_ready":False}
    write_json(output/"result.json",payload)
    return payload


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);p.add_argument("--samples",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();solve(args.run,args.samples,args.output)
