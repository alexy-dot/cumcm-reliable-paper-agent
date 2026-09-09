"""Independent finite upper bound for the excluded-supplier contingency.

For fixed counts of A/B/C suppliers, taking the largest supply caps within each
type dominates any other portfolio. Enumerate the three type counts and apply
the rearrangement allocation, without importing the MILP or response fitter.
"""
import argparse
import hashlib
import json
from pathlib import Path

from prepare import write


def bound_for_count(facts, excluded, count):
    caps={k:sorted([float(v) for i,v in enumerate(facts["supply_cap"])
                    if facts["kinds"][i]==k and facts["ids"][i]!=excluded],reverse=True) for k in "ABC"}
    loss=sorted(facts["carrier_mean_loss"])
    best=-1.;winner=None;tested=0
    for na in range(count+1):
        for nb in range(count-na+1):
            nc=count-na-nb
            counts=(na,nb,nc)
            if any(n>len(caps[k]) for k,n in zip("ABC",counts)):continue
            amounts=[sum(caps[k][:n]) for k,n in zip("ABC",counts)]
            remaining=[6000.]*8;total=0.
            for amount,conversion in zip(amounts,(.6,.66,.72)):
                for j,ell in enumerate(loss):
                    used=min(amount,remaining[j]);amount-=used;remaining[j]-=used
                    total+=used*(1-ell)/conversion
            tested+=1
            if total>best:best=total;winner=counts
    return {"supplier_count":count,"maximum_product_output":best,"type_counts":winner,"type_count_allocations_enumerated":tested}


def verify(run, contingency, output):
    if output.exists():raise ValueError("choose new verification output")
    f=json.loads((run/"artifacts/facts.json").read_text());c=json.loads(contingency.read_text())
    bound=bound_for_count(f,c["excluded_supplier"],c["minimum_suppliers"]-1)
    q=c["weekly_orders"];y=c["weekly_shipments"];arrivals=0.;cost=0.;carrier=[0.]*8;active=0
    for i,row in enumerate(y):
        shipped=sum(row)
        assert min(row)>=-1e-8 and shipped<=f["supply_cap"][i]+1e-6
        assert abs(shipped-q[i]*f["supply_rate"][i])<1e-6
        if f["ids"][i]==c["excluded_supplier"]:assert abs(shipped)<1e-8
        active+=shipped>1e-8
        for j,amount in enumerate(row):
            carrier[j]+=amount
            arrivals+=amount*(1-f["carrier_mean_loss"][j])/f["conversion"][i]
            cost+=amount*f["price"][i]*24
    passed=bound["maximum_product_output"]<f["demand"] and arrivals>=f["demand"]-1e-6 and max(carrier)<=6000+1e-6 and active==c["minimum_suppliers"] and abs(cost-c["purchase_index_24weeks"])<1e-5
    report={"passed":passed,"independent_upper_bound":bound,"required_output":f["demand"],
            "candidate_supplier_count":active,"candidate_product_output":arrivals,"candidate_purchase_index":cost,
            "source_contingency_sha256":hashlib.sha256(contingency.read_bytes()).hexdigest(),
            "scope":"minimum count proved only under original fitted supply caps, identical within-type conversion and unrestricted transport links/splitting; no physical supply guarantee"}
    write(output,report)
    if not passed:raise ValueError("contingency bound or candidate failed")
    print(report)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);p.add_argument("contingency",type=Path);p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();verify(args.run,args.contingency,args.output)
