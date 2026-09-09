"""Operational tradeoffs: bounded response stress and a smaller Q3 portfolio."""
import argparse
import json
from copy import deepcopy
from pathlib import Path

import numpy as np
from prepare import write
from solve import count_suppliers, material_plan, record_plan


def alternatives(run):
    f=json.loads((run/"artifacts/facts.json").read_text());p=json.loads((run/"artifacts/plans.json").read_text())
    cap=np.zeros(402);idx=f["top50_indices"];cap[idx]=np.array(f["supply_cap"])[idx]
    y,proof=material_plan(f,f["demand"],"A_then_C",cap_override=cap)
    limited=record_plan(f,np.repeat(y[None,:,:],24,axis=0),f["demand"])
    limited["scope"]="Q3 lexicographic objective restricted to the Q1 top50, not the globally best 50-supplier portfolio"
    limited["certificates"]=proof
    worst=deepcopy(f);worst["carrier_mean_loss"]=f["carrier_p95_loss"]
    y,proof=count_suppliers(worst,f["demand"]/.9)
    resilient=record_plan(f,np.repeat(y[None,:,:],24,axis=0),f["demand"])
    lower_arrivals=.9*(y*(1-np.array(f["carrier_p95_loss"]))[None,:]/np.array(f["conversion"])[:,None]).sum()
    resilient["worst_case_weekly_arrivals"]=float(lower_arrivals)
    resilient["certificates"]=proof
    resilient["scope"]="conditional protection if every supplier delivers at least 90% of modeled mean and each carrier loss is at most its historical marginal 95th percentile; these joint bounds have no calibrated confidence level"
    if lower_arrivals<f["demand"]-1e-6:raise ValueError("bounded-response plan fails its own stress")
    saving=p["Q2"]["raw_material_volume"]-p["Q3"]["raw_material_volume"]
    increase=p["Q3"]["purchase_cost_index"]-p["Q2"]["purchase_cost_index"]
    write(run/"artifacts/alternatives.json",{
        "Q3_top50":limited,"Q2_bounded_response":resilient,
        "Q3_cost_tradeoff":{"purchase_index_increase":increase,"raw_transport_volume_saving":saving,
                            "transport_unit_fee_break_even_relative_to_C_purchase_price":increase/saving,
                            "extra_supplier_count":p["Q3"]["active_suppliers"]-p["Q2"]["active_suppliers"],
                            "scope":"ignores unknown storage and supplier administration costs; all monetary terms indexed to C raw purchase price"}})
    print({"Q3_top50_supplier_count":limited["active_suppliers"],"Q3_top50_raw_by_type":limited["raw_by_type"],
           "bounded_response_supplier_count":resilient["active_suppliers"],"bounded_response_min_arrival":lower_arrivals,
           "transport_fee_break_even":increase/saving},flush=True)


if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("run",type=Path);alternatives(ap.parse_args().run)
