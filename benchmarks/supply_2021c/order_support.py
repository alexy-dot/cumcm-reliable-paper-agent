"""Quantify interpolation gaps and their contribution to frozen production plans."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from prepare import write


def audit(run, output):
    if output.exists():raise ValueError("choose a new support audit file")
    d=np.load(run/"artifacts/observations.npz");o,s=d["orders"],d["supply"]
    f=json.loads((run/"artifacts/facts.json").read_text());p=json.loads((run/"artifacts/plans.json").read_text())
    loss=np.array(f["carrier_mean_loss"]);conversion=np.array(f["conversion"])
    cases={}
    for name,plan in p.items():
        q=np.array(plan["orders"]);y=np.array(plan["shipments"])
        contribution=(y*(1-loss)[None,None,:]/conversion[None,:,None]).sum((0,2))
        rows=[]
        for i in range(len(o)):
            amounts=np.unique(q[:,i][q[:,i]>1e-8])
            if not len(amounts):continue
            history=o[i][o[i]>0]
            for amount in amounts:
                near=(o[i]>=.8*amount)&(o[i]<=1.2*amount)&(o[i]>0)
                lower=history[history<=amount];upper=history[history>=amount]
                near_count=int(near.sum())
                rows.append({"supplier":f["ids"][i],"quantity":float(amount),"nearby_count":near_count,
                             "lower_observed_order":float(lower.max()) if len(lower) else None,
                             "upper_observed_order":float(upper.min()) if len(upper) else None,
                             "local_supply_mean":float(s[i,near].mean()) if near_count else None,
                             "planned_mean_supply":float(f["supply_rate"][i]*amount),
                             "total_24week_product_contribution":float(contribution[i])})
        # Count each supplier once despite multiple order amounts across 24 weeks.
        unsupported={r["supplier"] for r in rows if r["nearby_count"]==0}
        idx=[i for i,v in enumerate(f["ids"]) if v in unsupported]
        cases[name]={"supplier_count_with_any_unsupported_amount":len(unsupported),
                     "share_of_modeled_product_from_these_suppliers":float(contribution[idx].sum()/contribution.sum()),
                     "suppliers":rows}
    result={"scope":"local order support within ±20%; not a hypothesis test or proof of unavailable capacity. Sparse small integer orders can legitimately bracket a fractional recommendation. Contribution shares count a supplier entire 24-week contribution if any amount lacks nearby observations.",
            "cases":cases,"source_plans_sha256":hashlib.sha256((run/"artifacts/plans.json").read_bytes()).hexdigest()}
    write(output,result)
    print({k:{a:b for a,b in v.items() if a!="suppliers"} for k,v in cases.items()})


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();audit(args.run,args.output)
