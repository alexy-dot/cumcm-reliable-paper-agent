"""Independent item-level simulation and numerical quadrature of sampling evidence."""
import argparse
import math
import random
from pathlib import Path
from scipy.integrate import quad
from prepare import read_json,write_json,sha256_file
from sampling import log_evidence


def simulate(case,bits,orders,seed):
    rng=random.Random(seed);costs=[];returns=[];assemblies=[]
    rates=[case["p1"],case["p2"]];price=[case["purchase1"],case["purchase2"]];inspect=[case["inspect1"],case["inspect2"]]
    for _ in range(orders):
        cost=0.;returned=0;attempts=0
        def purchase(i,test):
            nonlocal cost
            while True:
                cost+=price[i];good=rng.random()>=rates[i]
                if test:
                    cost+=inspect[i]
                    if not good:continue
                return [good,bool(test)]
        parts=[purchase(i,bits[i]) for i in range(2)]
        while True:
            attempts+=1
            if attempts>10000:raise ValueError("nonterminating simulated order; no arbitrary depth truncation allowed")
            cost+=case["assembly"]+bits[4]*case["inspect_final"]
            success=all(p[0] for p in parts) and rng.random()>=case["assembly_defect"]
            if success:break
            if not bits[4]:cost+=case["replacement_loss"];returned+=1
            if not bits[5]:parts=[purchase(i,bits[i]) for i in range(2)];continue
            cost+=case["disassembly"]
            for i,p in enumerate(parts):
                if bits[2+i] and not p[1]:
                    cost+=inspect[i]
                    if p[0]:parts[i]=[True,True]
                    else:parts[i]=purchase(i,True)
        costs.append(cost);returns.append(returned);assemblies.append(attempts)
    mean=math.fsum(costs)/orders
    variance=math.fsum((x-mean)**2 for x in costs)/(orders-1)
    return {"orders":orders,"mean_cost":mean,"cost_standard_error":math.sqrt(variance/orders),
            "mean_customer_returns":math.fsum(returns)/orders,"mean_assemblies":math.fsum(assemblies)/orders}


def quadrature_evidence(n,k,p0,accept):
    lower,upper=(0.,p0) if accept else (p0,1.)
    peak=min(upper,max(lower,k/n))
    def log_kernel(q):
        if (q==0 and k) or (q==1 and n!=k):return -math.inf
        return (k*math.log(q/p0) if k else 0)+((n-k)*math.log((1-q)/(1-p0)) if n!=k else 0)
    shift=log_kernel(peak)
    integral,_=quad(lambda q:math.exp(log_kernel(q)-shift),lower,upper,epsabs=1e-12,epsrel=1e-12)
    return math.log(integral/(upper-lower))+shift


def verify(run):
    facts=read_json(run/"artifacts/facts.json");protocol=read_json(run/"artifacts/protocol.json")
    result=read_json(run/"artifacts/rework.json");sampling=read_json(run/"artifacts/sampling.json")
    if protocol["facts_sha256"]!=sha256_file(run/"artifacts/facts.json"):raise ValueError("input changed")
    simulations=[]
    for case,record in zip(facts["cases"],result["cases"]):
        best=record["optimal_policies"][0]
        sample=simulate(case,best["bits"],protocol["verification"]["simulation_orders_per_case"],protocol["verification"]["simulation_seed"]+case["case"])
        error=abs(sample["mean_cost"]-best["expected_cost"]);threshold=6*sample["cost_standard_error"]+.02
        simulations.append({"case":case["case"],"exact_expected_cost":best["expected_cost"],**sample,"error":error,"threshold":threshold,"passed":error<=threshold})
        print(case["case"],"simulation error",round(error,4),"threshold",round(threshold,4),flush=True)
    quadratures=[]
    for n,k in [(2,2),(22,0),(50,3),(100,10),(300,40)]:
        for direction in ("accept","reject"):
            value=quadrature_evidence(n,k,.1,direction=="accept");error=abs(value-log_evidence(n,k)[direction])
            quadratures.append({"n":n,"k":k,"direction":direction,"log_error":float(error),"passed":bool(error<1e-8)})
    boundary=next(r for r in sampling["operating_characteristics"] if r["true_defect_rate"]==.1)
    sampling_bounds=boundary["reject_probability"]<=.05+1e-12 and boundary["accept_probability"]<=.1+1e-12
    report={"passed":all(r["passed"] for r in simulations+quadratures) and sampling_bounds,
            "simulations":simulations,"quadrature_checks":quadratures,"boundary_probabilities_within_bounds":sampling_bounds,
            "rework_sha256":sha256_file(run/"artifacts/rework.json"),"sampling_sha256":sha256_file(run/"artifacts/sampling.json"),
            "scope":"item-level simulation of selected policies, independent likelihood integration, and boundary operating probabilities; analytic test validity and policy limits require stated assumptions"}
    write_json(run/"artifacts/verification.json",report)
    if not report["passed"]:raise ValueError("independent production checks failed")


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);verify(p.parse_args().run)
