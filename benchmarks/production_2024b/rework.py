"""Exact rational Markov rewards for persistent two-component quality and free replacement."""
import argparse
from fractions import Fraction as F
from itertools import product
from pathlib import Path
from prepare import read_json,write_json

# 0: bad/unknown; 1: good/unknown; 2: inspected good. Decisions never observe latent 0 vs 1.
STATES=list(product(range(3),repeat=2))


def fresh_part(p,c,t,inspect):
    if inspect:return {2:F(1)},(c+t)/(1-p)
    return {0:p,1:1-p},c


def combine(a,b):
    return {(i,j):pi*pj for i,pi in a.items() for j,pj in b.items() if pi*pj}


def gaussian(matrix,rhs):
    a=[list(row)+[value] for row,value in zip(matrix,rhs)];n=len(a)
    for column in range(n):
        pivot=next((i for i in range(column,n) if a[i][column]),None)
        if pivot is None:raise ValueError("nonabsorbing policy: infinite expected completion cost")
        a[column],a[pivot]=a[pivot],a[column]
        divisor=a[column][column];a[column]=[x/divisor for x in a[column]]
        for i in range(n):
            if i==column:continue
            multiple=a[i][column]
            if multiple:a[i]=[x-multiple*y for x,y in zip(a[i],a[column])]
    return [row[-1] for row in a]


def evaluate(case,bits):
    rates=[F(str(case["p1"])),F(str(case["p2"]))];p=F(str(case["assembly_defect"]))
    if any(x<0 or x>=1 for x in [*rates,p]):raise ValueError("defect rates must lie in [0,1)")
    costs=[F(case["purchase1"]),F(case["purchase2"])];tests=[F(case["inspect1"]),F(case["inspect2"])]
    fresh=[fresh_part(rates[i],costs[i],tests[i],bits[i]) for i in range(2)]
    initial=combine(fresh[0][0],fresh[1][0]);purchase=sum(row[1] for row in fresh)
    transitions={};rewards={};failure_rates={}
    for state in STATES:
        failure=F(1) if 0 in state else p
        recovery_cost=F(0)
        if bits[5]:
            new=[]
            for i,value in enumerate(state):
                if bits[2+i] and value!=2:
                    recovery_cost+=tests[i]
                    if value==0:recovery_cost+=(costs[i]+tests[i])/(1-rates[i])
                    new.append(2)
                else:new.append(value)
            target={tuple(new):F(1)}
            recovery_cost+=F(case["disassembly"])
        else:target=initial;recovery_cost=purchase
        transitions[state]={s:failure*v for s,v in target.items() if failure*v}
        failure_rates[state]=failure
        rewards[state]=F(case["assembly"])+bits[4]*F(case["inspect_final"])+failure*((1-bits[4])*F(case["replacement_loss"])+recovery_cost)
    # Exclude impossible latent states, but keep every state reachable from the actual fresh supply.
    reachable=set(initial);front=list(initial)
    while front:
        for state in transitions[front.pop()]:
            if state not in reachable:reachable.add(state);front.append(state)
    order=sorted(reachable)
    matrix=[[F(int(i==j))-transitions[s].get(t,F(0)) for j,t in enumerate(order)] for i,s in enumerate(order)]
    try:
        values=gaussian(matrix,[rewards[s] for s in order])
        attempts=gaussian(matrix,[F(1) for s in order])
        returns=gaussian(matrix,[failure_rates[s]*(1-bits[4]) for s in order])
    except ValueError:
        return {"bits":list(bits),"proper":False,"reason":"reachable closed failure class; persistent defective parts are never removed"}
    cost=purchase+sum(initial.get(s,F(0))*value for s,value in zip(order,values))
    expected_attempts=sum(initial.get(s,F(0))*value for s,value in zip(order,attempts))
    expected_returns=sum(initial.get(s,F(0))*value for s,value in zip(order,returns))
    # Exact residual, not a floating tolerance chosen after solving.
    residual=[sum(matrix[i][j]*values[j] for j in range(len(order)))-rewards[s] for i,s in enumerate(order)]
    if any(residual):raise ValueError("rational Bellman residual is nonzero")
    return {"bits":list(bits),"proper":True,"expected_cost":float(cost),"profit":float(F(case["price"])-cost),
            "cost_exact":str(cost),"expected_assemblies":float(expected_attempts),"expected_customer_returns":float(expected_returns),
            "reachable_states":[list(s) for s in order],"exact_bellman_residual_zero":True}


def solve(run):
    facts=read_json(run/"artifacts/facts.json");reports=[]
    for case in facts["cases"]:
        policies=[evaluate(case,bits) for bits in product((0,1),repeat=6)]
        proper=[r for r in policies if r["proper"]]
        best_cost=min(F(r["cost_exact"]) for r in proper)
        best=[r for r in proper if F(r["cost_exact"])==best_cost]
        reports.append({"case":case["case"],"policies":policies,"optimal_policies":best,"proper_policy_count":len(proper),
                        "scope":"exact best among 64 declared stationary policies, per fulfilled customer order; not unrestricted policy optimality"})
        print(case["case"],[(r["bits"],round(r["profit"],6)) for r in best],"proper",len(proper),flush=True)
    write_json(run/"artifacts/rework.json",{"cases":reports,"scope":facts["scope"]})


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);solve(p.parse_args().run)
