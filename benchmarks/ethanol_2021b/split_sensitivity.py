"""Vary only outer group assignment under a frozen retrospective sensitivity protocol."""
import argparse
import math
from pathlib import Path
import numpy as np
from prepare import read_json,write_json,sha256_file,PROJECT
from grouped_regression import group_splits,evaluate_grouped

SEEDS=(17,43,97)


def independent_check(rows,targets):
    checks=[]
    for target,output in targets.items():
        seen=[]
        for fold in output["folds"]:
            train,test=fold["train_rows"],fold["test_rows"]
            if set(train)&set(test) or {rows[i]["group"] for i in train}&{rows[i]["group"] for i in test}:
                raise ValueError("group or row leakage")
            expected=math.fsum(rows[i][target] for i in train)/len(train)
            if any(abs(output["models"]["training_mean"]["prediction"][i]-expected)>1e-10 for i in test):
                raise ValueError("baseline uses values outside training")
            seen.extend(test)
        if sorted(seen)!=list(range(len(rows))):raise ValueError("held-out coverage is not exactly once")
        groups=sorted({r["group"] for r in rows})
        for family,result in output["models"].items():
            if len(result["prediction"])!=len(rows):raise ValueError("prediction length mismatch")
            errors=[(r[target]-p)**2 for r,p in zip(rows,result["prediction"])]
            means=[math.fsum(errors[i] for i,r in enumerate(rows) if r["group"]==g)/sum(r["group"]==g for r in rows) for g in groups]
            actual={"row_rmse":math.sqrt(math.fsum(errors)/len(rows)),"group_rmse":math.sqrt(math.fsum(means)/len(means))}
            for metric,value in actual.items():
                error=abs(value-result["metrics"][metric]);passed=math.isfinite(error) and error<=1e-10
                checks.append({"target":target,"family":family,"metric":metric,"error":error,"passed":passed})
    if not all(c["passed"] for c in checks):raise ValueError("independent prediction metric mismatch")
    return checks


def summarize(repetitions):
    targets=repetitions[0]["targets"]
    summary={}
    for target,first in targets.items():
        families=list(first["models"])
        metrics={family:[r["targets"][target]["models"][family]["metrics"]["group_rmse"] for r in repetitions] for family in families}
        # Fixed families and the adaptive model-selection policy are separate comparisons.
        fixed=[f for f in families if f!="nested_selection"]
        winners=[min(fixed,key=lambda f:metrics[f][i]) for i in range(len(repetitions))]
        summary[target]={"families":{family:{"min":min(values),"median":float(np.median(values)),"max":max(values),
                    "per_split":values,"better_than_temperature_count":sum(value<metrics["temperature_only"][i] for i,value in enumerate(values))}
                    for family,values in metrics.items()},"fixed_family_winners":winners,
                    "scope":"three correlated regroupings of the same observations; win counts and ranges are descriptive, not independent replications, confidence intervals or win probabilities"}
    return summary


def study(run):
    protocol=read_json(run/"artifacts/protocol.json");observations=read_json(run/"artifacts/observations.json")
    if protocol["observations_sha256"]!=sha256_file(run/"artifacts/observations.json"):
        raise ValueError("observations differ from frozen protocol")
    destination=run/"artifacts/split_sensitivity";destination.mkdir(exist_ok=False)
    rows=observations["rows"];groups=np.array([r["group"] for r in rows]);x=np.array([[r[f] for f in protocol["features"]] for r in rows])
    partitions={str(seed):[{"train":train.tolist(),"test":test.tolist()} for train,test in group_splits(groups,5,seed=seed)] for seed in SEEDS}
    design={"seeds":list(SEEDS),"partitions":partitions,"model_protocol_sha256":sha256_file(run/"artifacts/protocol.json"),
            "observations_sha256":sha256_file(run/"artifacts/observations.json"),
            "code_sha256":{"study":sha256_file(Path(__file__)),"grouped_regression":sha256_file(PROJECT/"skill/cumcm-reliable-paper/scripts/grouped_regression.py")},
            "assignment":"shuffle unique group IDs, then split into near-equal group counts; no response values used",
            "selection":"same candidate models, physical bounds, inner GroupKFold and forest seed as original protocol; no retuning after seeing new outer results",
            "exposure":"post-analysis sensitivity exercise, not an untouched test set or new blind trial"}
    write_json(destination/"protocol.json",design)
    repetitions=[]
    for seed in SEEDS:
        repeat={"seed":seed,"targets":{}}
        splits=[(np.array(r["train"]),np.array(r["test"])) for r in partitions[str(seed)]]
        for target in protocol["targets"]:
            y=np.array([r[target] for r in rows])
            repeat["targets"][target]=evaluate_grouped(x,y,groups,protocol["families"],splits=splits,
                                inner_folds=protocol["inner_folds"],bounds=protocol["physical_bounds"])
            print(seed,target,{name:round(v["metrics"]["group_rmse"],3) for name,v in repeat["targets"][target]["models"].items()},flush=True)
        repeat["independent_checks"]=independent_check(rows,repeat["targets"])
        write_json(destination/f"seed-{seed}.json",repeat);repetitions.append(repeat)
    result={"complete":True,"protocol_sha256":sha256_file(destination/"protocol.json"),
            "repetition_sha256":{f"seed-{seed}.json":sha256_file(destination/f"seed-{seed}.json") for seed in SEEDS},
            "summary":summarize(repetitions),"independent_metric_checks":sum(len(r["independent_checks"]) for r in repetitions)}
    write_json(destination/"report.json",result)
    return result


def checked_report(run):
    destination=run/"artifacts/split_sensitivity"
    report=read_json(destination/"report.json");protocol=read_json(destination/"protocol.json")
    if not report["complete"] or report["protocol_sha256"]!=sha256_file(destination/"protocol.json"):
        raise ValueError("missing or stale split sensitivity protocol")
    if protocol["observations_sha256"]!=sha256_file(run/"artifacts/observations.json") or protocol["model_protocol_sha256"]!=sha256_file(run/"artifacts/protocol.json"):
        raise ValueError("split study predates current model/data protocol")
    repetitions=[]
    for name,digest in report["repetition_sha256"].items():
        if sha256_file(destination/name)!=digest:raise ValueError("split output changed")
        repetitions.append(read_json(destination/name))
    if summarize(repetitions)!=report["summary"]:raise ValueError("summary does not match repetitions")
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("run",type=Path);study(p.parse_args().run)
