"""Q4: posterior expected-cost decisions conditional on supplied sample counts.

This uses an explicit independent Beta prior. Example counts are illustrative,
never represented as observations from the competition attachments.
"""
import argparse
from itertools import product
from pathlib import Path
import numpy as np
from prepare import read_json,write_json,sha256_file
from multistage import source_tree

DESIGN_DRAWS=512
CHECK_DRAWS=8192


def counts_parameters(samples,bases,prior):
    if len(samples)!=len(bases):raise ValueError("wrong number of stage sample records")
    a,b=prior["alpha"],prior["beta"]
    if not np.isfinite([a,b]).all() or min(a,b)<=0:raise ValueError("Beta prior parameters must be positive")
    parameters=[]
    for record,basis in zip(samples,bases):
        n,k=record["n"],record["k"]
        if type(n) is not int or type(k) is not int or n<=0 or not 0<=k<=n:raise ValueError("sample counts must satisfy 0<=k<=n with positive integer n")
        if record.get("basis")!=basis:raise ValueError("assembly defect samples require confirmed good input components")
        if b+n-k<=1:raise ValueError("posterior inverse-good-rate mean diverges; finite expected rework cost is not justified")
        parameters.append((a+k,b+n-k))
    return np.asarray(parameters,float)


def draws(parameters,count,seed):
    rng=np.random.default_rng(seed)
    return np.column_stack([rng.beta(a,b,count) for a,b in parameters])


def part_moment(p,c,t,tested):
    ensured=(c+t)/(1-p)
    return (ensured if tested else np.full_like(p,c),np.zeros_like(p) if tested else p,
            np.zeros_like(p) if tested else p*ensured,t,bool(tested))


def node_moment(children,p,a,t,d,tested,dismantle):
    success=1-p
    for _,bad,_,_,_ in children:success=success*(1-bad)
    bad=1-success;purchase=sum(c[0] for c in children)
    if dismantle:
        unknown=sum(c[3] for c in children if not c[4]);child_repair=sum(c[2] for c in children)
        weighted=child_repair+bad*(d+unknown+(a+t+p*d)/(1-p))
        ensured=purchase+a+t+weighted
    else:
        ensured=(purchase+a+t)/success;weighted=bad*ensured
    return (ensured if tested else purchase+a,np.zeros_like(p) if tested else bad,
            np.zeros_like(p) if tested else weighted,t,bool(tested))


def final_cost(children,p,node,tested,dismantle):
    success=1-p
    for child in children:success=success*(1-child[1])
    bad=1-success;purchase=sum(c[0] for c in children)
    a,t,d,L=[node[k] for k in ("assembly","test","dismantle","exchange_loss")]
    loss=(1-tested)*L
    if not dismantle:return (purchase+a+tested*t+bad*loss)/success
    unknown=sum(c[3] for c in children if not c[4])
    return purchase+a+tested*t+sum(c[2] for c in children)+bad*(loss+d+unknown+(a+tested*t+p*(d+loss))/(1-p))


def case_tree(case):
    return {"parts":[{"p":case["p"+str(i)],"purchase":case["purchase"+str(i)],"test":case["inspect"+str(i)]} for i in (1,2)],"semis":[],
            "final":{"p":case["assembly_defect"],"assembly":case["assembly"],"test":case["inspect_final"],
                     "dismantle":case["disassembly"],"exchange_loss":case["replacement_loss"],"price":case["price"]}}


def evaluate(tree,policy,rates):
    parts=[part_moment(rates[:,i],p["purchase"],p["test"],policy["part_tests"][i]) for i,p in enumerate(tree["parts"])]
    semis=[node_moment([parts[j] for j in node["children"]],rates[:,len(parts)+i],node["assembly"],node["test"],node["dismantle"],
                       policy["semi_tests"][i],policy["semi_dismantle"][i]) for i,node in enumerate(tree["semis"])]
    return final_cost(semis if semis else parts,rates[:,-1],tree["final"],policy["final_test"],policy["final_dismantle"])


def search(tree,rates):
    options=[];nparts=len(tree["parts"])
    if tree["semis"]:
        for index,node in enumerate(tree["semis"]):
            group=[]
            for part_tests in product((0,1),repeat=len(node["children"])):
                children=[part_moment(rates[:,i],tree["parts"][i]["purchase"],tree["parts"][i]["test"],flag) for i,flag in zip(node["children"],part_tests)]
                for test,d in product((0,1),repeat=2):
                    moment=node_moment(children,rates[:,nparts+index],node["assembly"],node["test"],node["dismantle"],test,d)
                    group.append((part_tests,test,d,moment))
            options.append(group)
    else:
        for i,node in enumerate(tree["parts"]):
            options.append([((flag,),None,None,part_moment(rates[:,i],node["purchase"],node["test"],flag)) for flag in (0,1)])
    finalists=[];count=0
    for combination in product(*options):
        for test,d in product((0,1),repeat=2):
            cost=final_cost([c[3] for c in combination],rates[:,-1],tree["final"],test,d)
            mean=float(cost.mean());count+=1
            if not np.isfinite(mean):raise ValueError("nonfinite posterior cost; inspect posterior tail")
            policy={"part_tests":[v for c in combination for v in c[0]],"semi_tests":[c[1] for c in combination] if tree["semis"] else [],
                    "semi_dismantle":[c[2] for c in combination] if tree["semis"] else [],"final_test":test,"final_dismantle":d}
            finalists.append({"policy":policy,"selection_mean_cost":mean})
            finalists.sort(key=lambda r:r["selection_mean_cost"])
            del finalists[5:]
    return {"policy_count":count,"finalists":finalists}


def cost_summary(cost,price):
    return {"posterior_mean_cost":float(cost.mean()),"integration_standard_error":float(cost.std(ddof=1)/np.sqrt(len(cost))),
            "posterior_mean_profit":float(price-cost.mean()),"cost_parameter_quantiles_05_50_95":np.quantile(cost,[.05,.5,.95]).tolist(),
            "scope":"distribution of conditional expected order costs across uncertain rates, not individual order outcomes"}


def illustrative_counts(run,n,output):
    facts=read_json(run/"artifacts/facts.json")
    def records(rates,bases):
        rows=[]
        for p,basis in zip(rates,bases):
            if abs(n*p-round(n*p))>1e-9:raise ValueError("example n cannot exactly represent nominal rates")
            rows.append({"n":n,"k":round(n*p),"basis":basis})
        return rows
    specification={"label":f"illustrative_n{n}","provenance":"ILLUSTRATIVE_COUNTS_NOT_OBSERVED", "prior":{"alpha":1.,"beta":1.},
        "q2":{str(c["case"]):records([c["p1"],c["p2"],c["assembly_defect"]],["random_supply"]*2+["good_inputs"]) for c in facts["cases"]},
        "q3":records([.1]*12,["random_supply"]*8+["good_inputs"]*4)}
    if output.exists():raise ValueError("sample file already exists")
    write_json(output,specification)


def solve(run,samples_path,output):
    samples=read_json(samples_path);facts=read_json(run/"artifacts/facts.json")
    if not isinstance(samples.get("provenance"),str) or not samples["provenance"].strip():raise ValueError("sample provenance must be explicit")
    if set(samples["q2"])!={str(c["case"]) for c in facts["cases"]}:raise ValueError("all six Q2 cases need sample records")
    problems=[("Q2-"+str(c["case"]),case_tree(c),samples["q2"][str(c["case"])] ) for c in facts["cases"]]
    problems.append(("Q3",source_tree(),samples["q3"]))
    parameters={name:counts_parameters(records,["random_supply"]*len(tree["parts"])+["good_inputs"]*(len(tree["semis"])+1),samples["prior"]) for name,tree,records in problems}
    output.mkdir(parents=True,exist_ok=False)
    protocol={"samples":samples,"samples_sha256":sha256_file(samples_path),"selection_draws":DESIGN_DRAWS,"validation_draws":CHECK_DRAWS,
        "selection_seed_base":104729,"validation_seed_base":130363,"prior_and_likelihood":"independent Beta prior per stage, iid Bernoulli likelihood; assembly observations require all-good inputs",
        "objective":"minimum posterior expected completion cost among declared policies, equal integration weight; five finalists frozen before held-out integration",
        "scope":"Monte Carlo posterior decision analysis conditional on supplied counts and prior; not an exact proof of expected-cost optimality or field reliability"}
    write_json(output/"protocol.json",protocol)
    selected={}
    for index,(name,tree,records) in enumerate(problems):
        rates=draws(parameters[name],DESIGN_DRAWS,104729+index)
        selected[name]=search(tree,rates)
        nominal=np.array([[p["p"] for p in tree["parts"]]+[s["p"] for s in tree["semis"]]+[tree["final"]["p"]]])
        selected[name]["nominal_policy"]=search(tree,nominal)["finalists"][0]["policy"]
        print(name,"selected",selected[name]["finalists"][0],flush=True)
    write_json(output/"candidates.json",selected)
    reports={}
    for index,(name,tree,records) in enumerate(problems):
        rates=draws(parameters[name],CHECK_DRAWS,130363+index)
        best=selected[name]["finalists"][0]["policy"];cost=evaluate(tree,best,rates)
        baseline=evaluate(tree,selected[name]["nominal_policy"],rates)
        diff=cost-baseline
        finalists=[]
        for candidate in selected[name]["finalists"]:
            values=evaluate(tree,candidate["policy"],rates)
            finalists.append({"policy":candidate["policy"],**cost_summary(values,tree["final"]["price"])})
        reports[name]={"selected_policy":best,"nominal_policy":selected[name]["nominal_policy"],
            "selected":cost_summary(cost,tree["final"]["price"]),"nominal":cost_summary(baseline,tree["final"]["price"]),
            "paired_cost_difference":float(diff.mean()),"paired_difference_standard_error":float(diff.std(ddof=1)/np.sqrt(CHECK_DRAWS)),
            "validation_finalists":finalists,"policy_changed":best!=selected[name]["nominal_policy"],
            "posterior_parameters":parameters[name].tolist()}
    result={"protocol_sha256":sha256_file(output/"protocol.json"),"candidates_sha256":sha256_file(output/"candidates.json"),
            "sample_provenance":samples["provenance"],"results":reports,"retuned_after_validation":False,
            "remaining":"Real sample counts, sampling design, prior assessment and team review are required before treating the illustrative decisions as operational recommendations"}
    write_json(output/"result.json",result)
    print({name:{"changed":r["policy_changed"],"expected_profit":r["selected"]["posterior_mean_profit"],"difference":r["paired_cost_difference"]} for name,r in reports.items()},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);p.add_argument("--samples",type=Path);p.add_argument("--output",type=Path,required=True);p.add_argument("--make-example",type=int)
    args=p.parse_args()
    if args.make_example is not None:illustrative_counts(args.run,args.make_example,args.output)
    elif args.samples is not None:solve(args.run,args.samples,args.output)
    else:p.error("provide --samples, or --make-example to create explicitly illustrative counts")
