"""Recompute reported prediction errors and split boundaries with standard-library arithmetic."""
import argparse
import math
import re
from decimal import Decimal
from pathlib import Path
from prepare import read_json,write_json,sha256_file
import openpyxl


def verify_material_series(workbook, series):
    sheet=workbook["性能数据表"]
    group=formula=None;source={};descriptors={}
    for number,values in enumerate(sheet.iter_rows(min_row=2,values_only=True),2):
        if values[0] is not None:group=values[0]
        if values[1] is not None:formula=re.sub(r"\s+","",values[1])
        co=re.search(r"([0-9.]+)mg([0-9.]+)wt%Co/SiO2",formula)
        hap=re.search(r"([0-9.]+)mgHAP",formula)
        feed=re.search(r"乙醇浓度([0-9.]+)ml/min",formula)
        quartz=re.search(r"([0-9.]+)mg石英砂",formula)
        descriptors[group]={"co":Decimal(co[1]),"hap":Decimal(hap[1]) if hap else Decimal(0),
            "controls":{"co_loading_pct":float(co[2]),"feed_ml_min":float(feed[1]),
                        "mode_II":int(group.startswith("B")),"quartz_mass_mg":float(quartz[1]) if quartz else 0.}}
        source.setdefault(group,{})[values[2]]={"source_row":number,"conversion_pct":float(values[3]),"selectivity_pct":float(values[5]),
            "yield_pct":float(Decimal(str(values[3]))*Decimal(str(values[5]))/Decimal(100))}
    checks=[]
    if len(series)!=4:raise ValueError("reviewed source has four eligible material series")
    for item in series:
        factor=item["factor"];members=[p["group"] for p in item["points"]]
        if len(set(members))!=len(members):raise ValueError("duplicate formulation in material series")
        eligible=[]
        for group,d in descriptors.items():
            if d["hap"]<=0 or d["controls"]!=item["controls"]:continue
            total=d["co"]+d["hap"]
            fixed=d["co"]/total if factor=="total_mass_mg" else total
            if abs(float(fixed)-item["fixed_value"])<1e-12:eligible.append(group)
        if set(eligible)!=set(members):raise ValueError("material series omits or adds a comparable formulation")
        common=sorted(set.intersection(*(set(source[g]) for g in members)))
        if common!=item["common_temperatures"]:raise ValueError("non-common or omitted measured temperature")
        for point in item["points"]:
            descriptor=descriptors[point["group"]];total=descriptor["co"]+descriptor["hap"]
            value=total if factor=="total_mass_mg" else descriptor["co"]/total
            if abs(float(value)-point["factor_value"])>1e-12:raise ValueError("incorrect material factor")
            if point["co_mass_mg"]!=float(descriptor["co"]) or point["hap_mass_mg"]!=float(descriptor["hap"]):raise ValueError("wrong primary masses")
            if [r["temperature_c"] for r in point["observations"]]!=common:raise ValueError("incomplete formulation observations")
            for row in point["observations"]:
                raw=source[point["group"]][row["temperature_c"]]
                if row["source_row"]!=raw["source_row"]:raise ValueError("wrong original row locator")
                for target in ("conversion_pct","selectivity_pct","yield_pct"):
                    error=abs(row[target]-raw[target])
                    checks.append({"factor":factor,"group":point["group"],"temperature_c":row["temperature_c"],
                                   "source_row":raw["source_row"],"target":target,"error":error,"passed":error<=1e-10})
    if not all(c["passed"] for c in checks):raise ValueError("material response differs from original worksheet")
    return {"series":len(series),"source_value_checks":len(checks),"passed":True,"comparisons":checks,
            "scope":"independent regex/Decimal extraction from original workbook, eligible member/common-temperature coverage and response checks; not causal identification"}


def verify(run):
    data=read_json(run/"artifacts/observations.json")
    output=read_json(run/"artifacts/statistical_results.json")
    rows=data["rows"];expected_groups={row["group"] for row in rows}
    comparisons=[]
    for target,result in output["targets"].items():
        for family,model in result["models"].items():
            errors=[(r[target]-v)**2 for r,v in zip(rows,model["prediction"])]
            if len(model["prediction"])!=len(rows) or not all(math.isfinite(v) and 0<=v<=100 for v in model["prediction"]):
                raise ValueError("invalid prediction coverage or bounds")
            mse_by_group=[math.fsum(errors[i] for i,r in enumerate(rows) if r["group"]==g)/sum(r["group"]==g for r in rows) for g in expected_groups]
            actual={"row_rmse":math.sqrt(math.fsum(errors)/len(rows)),"group_rmse":math.sqrt(math.fsum(mse_by_group)/len(expected_groups))}
            for metric,value in actual.items():
                expected=model["metrics"][metric]
                comparisons.append({"target":target,"family":family,"metric":metric,"value":value,"error":abs(value-expected),"passed":abs(value-expected)<=1e-10})
        covered=[]
        for fold in result["folds"]:
            train=fold["train_rows"];test=fold["test_rows"]
            if {rows[i]["group"] for i in train}&{rows[i]["group"] for i in test}:raise ValueError("held-out group leakage")
            covered.extend(test)
            baseline=math.fsum(rows[i][target] for i in train)/len(train)
            if any(abs(result["models"]["training_mean"]["prediction"][i]-baseline)>1e-10 for i in test):raise ValueError("mean baseline uses non-training targets")
        if sorted(covered)!=list(range(len(rows))):raise ValueError("duplicate or missing held-out prediction")
    decision=read_json(run/"artifacts/decisions.json")
    workbook=openpyxl.load_workbook(run/"sources/attachment_01__附件1.xlsx",data_only=True)
    group=None;raw=[]
    for values in workbook["性能数据表"].iter_rows(min_row=2,values_only=True):
        if values[0] is not None:group=values[0]
        value=Decimal(str(values[3]))*Decimal(str(values[5]))/Decimal(100)
        raw.append((group,values[2],float(value)))
    materials=verify_material_series(workbook,decision["material_series"])
    workbook.close()
    anchors=[]
    for key,subset in [("observed_best",raw),("observed_below_350_best",[r for r in raw if r[1]<350])]:
        winner=max(subset,key=lambda row:row[2]);recorded=decision[key]
        if winner[:2]!=(recorded["group"],recorded["temperature_c"]) or abs(winner[2]-recorded["yield_pct"])>1e-10:
            raise ValueError("observed optimum does not match direct Decimal workbook calculation")
        anchors.append({"claim":key,"group":winner[0],"temperature_c":winner[1],"yield_pct":winner[2]})
    report={"passed":all(c["passed"] for c in comparisons),"comparisons":comparisons,"direct_workbook_anchors":anchors,
            "material_series_verification":materials,
            "decisions_sha256":sha256_file(run/"artifacts/decisions.json"),
            "results_sha256":sha256_file(run/"artifacts/statistical_results.json"),"scope":"independent scalar metric recomputation and source-row group separation; selection isolation additionally tested by held-out label perturbation"}
    if not report["passed"]:raise ValueError("independent metrics mismatch")
    write_json(run/"artifacts/independent_statistics.json",report)
    print({"metric_comparisons":len(comparisons),"passed":True},flush=True)
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("run",type=Path);verify(p.parse_args().run)
