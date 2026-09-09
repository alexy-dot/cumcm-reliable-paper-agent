"""Verify pre-dispatch recourse on frozen supply plans and explicit disruptions."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from prepare import write

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skill/cumcm-reliable-paper/scripts"))
from transport_recourse import reallocate, inventory_step


def independent_bounds(supply, capacities, losses, conversion):
    remaining = list(map(float, capacities)); receipt = 0.; raw_loss = 0.
    # All supplied goods must ship. Cheapest carriers fill first; assigning the
    # most efficient material to the lowest loss maximizes received product.
    for i in sorted(range(len(supply)), key=lambda i: conversion[i]):
        left = float(supply[i])
        for j in sorted(range(len(capacities)), key=lambda j: losses[j]):
            amount = min(left, remaining[j]);left -= amount;remaining[j] -= amount
            receipt += amount*(1-losses[j])/conversion[i];raw_loss += amount*losses[j]
        if left > 1e-6:raise ValueError("independent bound requires enough transport capacity")
    return receipt, raw_loss


def check(run, output):
    output.mkdir(parents=True, exist_ok=False)
    facts=json.loads((run/"artifacts/facts.json").read_text())
    plans=json.loads((run/"artifacts/plans.json").read_text())
    a=np.array(facts["conversion"]);loss=np.array(facts["carrier_mean_loss"])
    rows=[]
    for name, plan in plans.items():
        baseline=np.array(plan["shipments"])[0]
        if baseline.min() < -1e-8:raise ValueError("original plan has material negative shipments")
        roundoff_correction=float(np.maximum(-baseline,0).max())
        baseline=np.maximum(baseline,0)
        production=plan["production_per_week"]
        initial=facts["initial_inventory_product_equivalent"]
        required=max(0.,3*production-initial)
        for label, factor, capacities in (
            ("supply_minus_10pct",.9,[6000.]*8),
            ("supply_plus_10pct",1.1,[6000.]*8),
            ("carrier_T3_unavailable",1.,[6000.,6000.,0.,6000.,6000.,6000.,6000.,6000.]),
            ("total_capacity_shortfall",1.,[1000.]*8),
        ):
            ref=baseline*factor;supply=ref.sum(1)
            result=reallocate(supply,capacities,loss,a,required_receipt=required,reference=ref)
            proof={}
            if result["all_supply_dispatched"]:
                y=np.array(result["shipments"])
                receipt=0.;waste=0.;cost=0.
                for i in range(len(supply)):
                    for j in range(8):
                        receipt+=y[i,j]*(1-loss[j])/a[i]
                        waste+=y[i,j]*loss[j]
                        cost+=y[i,j]*facts["price"][i]
                upper,lower=independent_bounds(supply,capacities,loss,a)
                proof={"supplier_balance_max_error":float(np.abs(y.sum(1)-supply).max()),
                       "carrier_overload":max(0.,float((y.sum(0)-capacities).max())),
                       "maximum_product_bound_error":abs(upper-result["maximum_product_receipt"]),
                       "minimum_raw_loss_bound_error":abs(lower-waste),
                       "receipt_accounting_error":abs(receipt-result["received_product"]),
                       "raw_loss_accounting_error":abs(waste-result["raw_loss"])}
                if max(proof.values())>1e-6:raise ValueError(proof)
                expected_status="TARGET_SHORTFALL" if upper<required-1e-6 else "FEASIBLE"
                if expected_status!=result["status"]:raise ValueError("incorrect feasibility status")
                result["inventory"]=inventory_step(initial,receipt,production,2*production)
                result["purchase_cost_index"]=cost
            else:
                deficit=float(supply.sum()-sum(capacities))
                if result["status"]!="TRANSPORT_CAPACITY_SHORTFALL" or result["shipments"] is not None or abs(deficit-result["minimum_extra_raw_capacity"])>1e-6:
                    raise ValueError("transport shortfall hidden")
                proof={"extra_capacity_accounting_error":abs(deficit-result["minimum_extra_raw_capacity"])}
            filename=f"{name}-{label}.json"
            artifact={"inputs":{"supply":supply.tolist(),"capacities":capacities,"losses":loss.tolist(),"conversion":a.tolist(),
                                "required_receipt":required,"reference":ref.tolist(),"original_negative_roundoff_clipped_max":roundoff_correction},"result":result,"independent_checks":proof}
            write(output/filename,artifact)
            row={"question":name,"scenario":label,"status":result["status"],
                 "original_proposal_overload":max(0.,float((ref.sum(0)-capacities).max())),
                 "rerouted_quantity":result.get("changed_raw_quantity"),
                 "receipt_shortfall":result.get("receipt_shortfall"),
                 "minimum_extra_capacity":result.get("minimum_extra_raw_capacity",0.),
                 "inventory":result.get("inventory"),"artifact":filename,
                 "sha256":hashlib.sha256((output/filename).read_bytes()).hexdigest()}
            rows.append(row);print({k:row[k] for k in ("question","scenario","status","original_proposal_overload","rerouted_quantity")},flush=True)
    report={"passed":True,"cases":rows,"source_plans_sha256":hashlib.sha256((run/"artifacts/plans.json").read_bytes()).hexdigest(),
            "source_code_sha256":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),ROOT/"skill/cumcm-reliable-paper/scripts/transport_recourse.py")},
            "scope":"first week of each frozen plan, four deterministic disruptions. Supply is known before dispatch; losses are original planning estimates. Independent exchange construction checks maximum product and minimum raw loss; minimum L1 rerouting relies on LP certificate. Not real performance or calibrated risk probabilities.",
            "timed_trial_changed":False,"submission_ready":False}
    write(output/"report.json",report)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();check(args.run,args.output)
