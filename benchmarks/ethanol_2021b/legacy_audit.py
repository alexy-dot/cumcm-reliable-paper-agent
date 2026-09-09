"""Audit prior recorded predictions without executing or changing the old solution."""
import argparse
import csv
import math
from pathlib import Path
import numpy as np
from prepare import read_json,write_json,sha256_file


def audit(run,legacy):
    rows=read_json(run/"artifacts/observations.json")["rows"]
    with legacy.open(encoding="utf-8-sig",newline="") as stream:old=list(csv.DictReader(stream))
    mapping={"conversion":("conversion_pct","乙醇转化率(%)"),"selectivity":("selectivity_pct","C4烯烃选择性(%)"),"yield":("yield_pct","c4_yield_pct")}
    baseline=[]
    for name,(target,column) in mapping.items():
        selected=[r for r in old if r["target_name"]==name]
        if len(selected)!=len(rows):raise ValueError("legacy OOF coverage mismatch")
        for old_row,row in zip(selected,rows):
            if old_row["催化剂组合编号"]!=row["group"] or float(old_row["温度"])!=row["temperature_c"] or abs(float(old_row[column])-row[target])>1e-9:
                raise ValueError("legacy outcomes cannot be aligned to the raw attachments")
        y=[r[target] for r in rows];global_mean=math.fsum(y)/len(y);corrected=[]
        for r in selected:
            train=[float(o[column]) for o in selected if o["fold"]!=r["fold"]]
            corrected.append(math.fsum(train)/len(train))
        rmse=lambda a,b:math.sqrt(math.fsum((x-z)**2 for x,z in zip(a,b))/len(a))
        prediction=[float(r["prediction"]) for r in selected]
        model_rmse=rmse(y,prediction);wrong=rmse(y,[global_mean]*len(y));right=rmse(y,corrected)
        baseline.append({"target":target,"recorded_model_rmse":model_rmse,"global_mean_rmse":wrong,"training_fold_mean_rmse":right,
                         "old_improvement_pct":100*(1-model_rmse/wrong),"corrected_improvement_pct":100*(1-model_rmse/right)})
    x=np.array([[r["co_mass_mg"],r["hap_mass_mg"],r["co_mass_mg"]+r["hap_mass_mg"],r["co_mass_mg"]/(r["co_mass_mg"]+r["hap_mass_mg"])] for r in rows])
    rng=np.random.default_rng(20210904);violations=[]
    for column in range(4):
        changed=x.copy();changed[:,column]=rng.permutation(changed[:,column])
        invalid=(np.abs(changed[:,0]+changed[:,1]-changed[:,2])>1e-9)|(np.abs(changed[:,0]/(changed[:,0]+changed[:,1])-changed[:,3])>1e-9)
        violations.append({"column":["co_mass","hap_mass","total_mass","co_fraction"][column],"inconsistent_rows":int(invalid.sum()),"rows":len(rows)})
    report={"legacy_predictions_sha256":sha256_file(legacy),"baseline_comparisons":baseline,"single_column_permutation_counterexample":violations,
            "scope":"recorded old OOF predictions aligned to source observations; no claim to revalidate the old estimator implementation. Counterexample illustrates structural inconsistency, not the exact old permutation draws.",
            "correction":"Using all labels gives the mean baseline unavailable information; here it understates, rather than inflates, the model improvement percentage. Independent permutation of derived composition fields is not a valid physical component intervention."}
    write_json(run/"artifacts/legacy_audit.json",report)
    print(baseline,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("run",type=Path);p.add_argument("--legacy-predictions",type=Path,required=True)
    args=p.parse_args();audit(args.run,args.legacy_predictions)
