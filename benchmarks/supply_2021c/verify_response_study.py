"""Recompute rolling scores and baseline predictions independently of model helpers."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from prepare import write


def verify(run, folder):
    protocol=json.loads((folder/"protocol.json").read_text());report=json.loads((folder/"report.json").read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if sha(folder/"protocol.json")!=report["protocol_sha256"] or sha(folder/"predictions.npz")!=report["predictions_sha256"]:
        raise ValueError("response study binding changed")
    if sha(run/"artifacts/observations.npz")!=protocol["source_observation_sha256"]:
        raise ValueError("source observations changed")
    # NPZ indexing decompresses a member on each access; load each array once
    # before independent scalar loops instead of repeatedly reopening it.
    with np.load(run/"artifacts/observations.npz") as archive:
        source={name:archive[name] for name in archive.files}
    with np.load(folder/"predictions.npz") as archive:
        d={name:archive[name] for name in archive.files}
    np.testing.assert_array_equal(d["actual"],source["supply"][:,72:240])
    np.testing.assert_array_equal(d["orders"],source["orders"][:,72:240])
    checks=[]
    for k,origin in enumerate(protocol["outer_origins"]):
        o=source["orders"][:,:origin];s=source["supply"][:,:origin]
        pooled=sum(map(float,s.ravel()))/sum(map(float,o.ravel()))
        ratios=np.array([sum(map(float,b))/sum(map(float,a)) if sum(a)>0 else pooled for a,b in zip(o,s)])
        predicted=ratios[:,None]*source["orders"][:,origin:origin+24]
        error=float(np.max(np.abs(predicted-d["ratio_all"][:,24*k:24*(k+1)])))
        chosen=min(protocol["methods"],key=lambda name:report["folds"][k]["inner_scores"][name])
        assert chosen==report["folds"][k]["selected_before_outer_supply"]
        selected_error=float(np.max(np.abs(d["nested_selected"][:,24*k:24*(k+1)]-d[chosen][:,24*k:24*(k+1)])))
        checks.append({"origin":origin,"baseline_max_error":error,"selected_array_max_error":selected_error,"passed":error<1e-7 and selected_error==0})
    for method,metrics in report["pooled_metrics"].items():
        weekly=[];weekly_raw=[];cells=[]
        for t in range(168):
            errors=[float(d[method][i,t]-d["actual"][i,t]) for i in range(402)]
            weekly.append(sum(e/float(a) for e,a in zip(errors,d["conversion"])))
            weekly_raw.append(sum(errors))
            cells.extend(e for i,e in enumerate(errors) if d["orders"][i,t]>0)
        expected={"weekly_total_mae_product":sum(map(abs,weekly))/len(weekly),
                  "weekly_total_rmse_product":math.sqrt(sum(e*e for e in weekly)/len(weekly)),
                  "weekly_total_mae_raw":sum(map(abs,weekly_raw))/len(weekly_raw),
                  "weekly_bias_product":sum(weekly)/len(weekly),
                  "active_cell_mae_raw":sum(map(abs,cells))/len(cells),
                  "active_cell_rmse_raw":math.sqrt(sum(e*e for e in cells)/len(cells))}
        error=max(abs(expected[name]-metrics[name]) for name in expected)
        checks.append({"method":method,"max_metric_error":error,"passed":error<1e-7})
    output={"passed":all(c["passed"] for c in checks),"checks":checks,"report_sha256":sha(folder/"report.json"),
            "scope":"independent scalar score recomputation, row/week alignment, direct ratio baseline and selected-array agreement; does not independently validate every nonlinear fitter or certify causal effects"}
    write(folder/"verification.json",output)
    if not output["passed"]:raise ValueError("independent score verification failed")
    print({"checks":len(checks),"passed":True})


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);p.add_argument("folder",type=Path)
    args=p.parse_args();verify(args.run,args.folder)
