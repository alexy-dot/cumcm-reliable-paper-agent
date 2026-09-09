"""Execute the frozen nested grouped protocol and retain every held-out prediction."""
import argparse
import csv
import sys
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"skill/cumcm-reliable-paper/scripts"))
from engine import read_json,write_json,sha256_file
from grouped_regression import evaluate_grouped,group_splits,predict_fit,permute_group_descriptors,regression_metrics


def analyze(run):
    protocol=read_json(run/"artifacts/protocol.json")
    observations=read_json(run/"artifacts/observations.json")
    if protocol["observations_sha256"]!=sha256_file(run/"artifacts/observations.json"):
        raise ValueError("observations changed after protocol")
    rows=observations["rows"];features=protocol["features"]
    x=np.array([[row[f] for f in features] for row in rows]);groups=np.array([row["group"] for row in rows])
    splits=group_splits(groups,protocol["outer_folds"])
    report={"protocol_sha256":sha256_file(run/"artifacts/protocol.json"),"targets":{},"group_relations":[]}
    for group in np.unique(groups):
        indices=np.flatnonzero(groups==group)
        report["group_relations"].append({"group":group,"n":len(indices),
            "temperature_min":float(x[indices,0].min()),"temperature_max":float(x[indices,0].max()),
            **{name+"_spearman":float(spearmanr(x[indices,0],[rows[i][name] for i in indices]).statistic)
               for name in ("conversion_pct","selectivity_pct")}})
    for target in protocol["targets"]:
        y=np.array([row[target] for row in rows])
        result=evaluate_grouped(x,y,groups,protocol["families"],splits=splits,
                                inner_folds=protocol["inner_folds"],bounds=protocol["physical_bounds"])
        forest=result["models"]["random_forest"]
        fitted=[]
        for fold,(train,test) in enumerate(splits):
            spec=forest["selection"][fold]["selected"]
            _,model=predict_fit(x,y,train,test,spec)
            fitted.append((spec,model))
        changes=[]
        for seed in range(20):
            prediction=np.empty(len(y))
            for fold,(train,test) in enumerate(splits):
                spec,model=fitted[fold]
                # Fit once on training rows; exchange entire held-out formulation descriptors.
                changed,mapping=permute_group_descriptors(x[test],groups[test],list(range(1,x.shape[1])),seed)
                prediction[test]=np.clip(model.predict(changed[:,spec["columns"]]),0,100)
            before=forest["metrics"]["group_rmse"]**2
            changes.append(regression_metrics(y,prediction,groups)["group_rmse"]**2-before)
        result["composition_block_permutation"]={"seeds":list(range(20)),"group_mse_increases":list(map(float,changes)),
                "mean_group_mse_increase":float(np.mean(changes)),"scope":"predictive dependence on the complete observed formulation, conditional on temperature; group labels jointly exchanged within each outer held-out fold; not a causal component-effect ranking"}
        result["group_errors"]=[{"group":g,**{name:float(np.sqrt(np.mean((np.array(model["prediction"])[groups==g]-y[groups==g])**2)))
                            for name,model in result["models"].items()}} for g in np.unique(groups)]
        report["targets"][target]=result
        write_json(run/"artifacts/statistical_results.json",report)
        print(target,{name:round(model["metrics"]["group_rmse"],3) for name,model in result["models"].items()},flush=True)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("run",type=Path)
    analyze(parser.parse_args().run)
