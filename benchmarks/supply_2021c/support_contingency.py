"""Replan Q2 if the largest supplier contribution in an order-data gap is unavailable.

This is a conditional contingency, not evidence that the supplier cannot deliver.
It preserves the original supply model and never revises the timed-trial files.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from prepare import write
from solve import count_suppliers, transfer_fixed_supply


def contingency(run, support_path, output):
    if output.exists():raise ValueError("choose a new output file")
    facts=json.loads((run/"artifacts/facts.json").read_text())
    baseline=json.loads((run/"artifacts/plans.json").read_text())["Q2"]
    audit=json.loads(support_path.read_text())
    gaps=[r for r in audit["cases"]["Q2"]["suppliers"] if r["nearby_count"]==0]
    if not gaps:raise ValueError("no unsupported Q2 order identified")
    chosen=max(gaps,key=lambda r:r["total_24week_product_contribution"])
    excluded=facts["ids"].index(chosen["supplier"])
    allowed=[i for i in range(len(facts["ids"])) if i!=excluded]
    y,certificate=count_suppliers(facts,facts["demand"],allowed=allowed)
    y,transport=transfer_fixed_supply(facts,y,facts["demand"])
    r=np.array(facts["supply_rate"]);a=np.array(facts["conversion"]);loss=np.array(facts["carrier_mean_loss"])
    q=np.divide(y.sum(1),r,out=np.zeros(len(r)),where=r>0)
    arrivals=float((y*(1-loss)[None,:]/a[:,None]).sum())
    cost=float((y*np.array(facts["price"])[:,None]).sum())*24
    checks={"excluded_supplier_zero":bool(np.abs(y[excluded]).max()<1e-8),
            "capacity":bool((y.sum(1)<=np.array(facts["supply_cap"])+1e-7).all()),
            "carrier_capacity":bool((y.sum(0)<=6000+1e-7).all()),
            "all_supply_transported":bool(np.max(np.abs(q*r-y.sum(1)))<1e-7),
            "production_and_stock":arrivals>=facts["demand"]-1e-6,
            "nonnegative":bool(y.min()>-1e-8 and q.min()>-1e-8)}
    with np.load(run/"artifacts/observations.npz") as data:historical=data["orders"]
    order_support=[]
    for i,amount in enumerate(q):
        if amount>1e-8:
            near=(historical[i]>=.8*amount)&(historical[i]<=1.2*amount)&(historical[i]>0)
            order_support.append({"supplier":facts["ids"][i],"weekly_order":float(amount),"nearby_historical_orders":int(near.sum())})
    result={"excluded_supplier":chosen["supplier"],"reason":chosen,"checks":checks,"passed":all(checks.values()),
            "minimum_suppliers":certificate["minimum_supplier_count"],"baseline_suppliers":baseline["active_suppliers"],
            "purchase_index_24weeks":cost,"baseline_purchase_index":baseline["purchase_cost_index"],
            "purchase_index_change":cost-baseline["purchase_cost_index"],"weekly_product_arrivals":arrivals,
            "supplier_ids":facts["ids"],"weekly_orders":q.tolist(),"weekly_shipments":y.tolist(),
            "plan_period":"repeat this stationary plan for 24 weeks with original two-week initial stock",
            "order_support":order_support,"selection_certificate":certificate,"transport_certificate":transport,
            "source_plan_sha256":hashlib.sha256((run/"artifacts/plans.json").read_bytes()).hexdigest(),
            "scope":"sensitivity to unavailability of the named supplier; no guarantee of other suppliers continuous availability or future performance; a lack of nearby orders does not prove inability"}
    write(output,result)
    if not result["passed"]:raise ValueError("contingency plan failed basic feasibility")
    print({k:result[k] for k in ("excluded_supplier","minimum_suppliers","purchase_index_change","weekly_product_arrivals")})


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);p.add_argument("--support-audit",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();contingency(args.run,args.support_audit,args.output)
