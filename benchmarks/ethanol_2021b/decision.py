"""Within-formulation temperature relationships, matched contrasts and a five-run design."""
import argparse
import math
from itertools import combinations
from fractions import Fraction
from pathlib import Path
import numpy as np
import openpyxl
from prepare import FEATURES,read_json,write_json,sha256_file


def fit_local(temperatures,values):
    t=np.asarray(temperatures,float);y=np.asarray(values,float)
    center=float(t.mean());scale=float(t.std()) or 1.;z=(t-center)/scale
    choices=[]
    for degree in (1,2):
        predicted=[]
        for i in range(len(y)):
            keep=np.arange(len(y))!=i
            p=np.polyfit(z[keep],y[keep],degree)
            predicted.append(float(np.polyval(p,z[i])))
        choices.append({"degree":degree,"selection_loocv_rmse":float(np.sqrt(np.mean((y-predicted)**2))),
                        "coefficients":np.polyfit(z,y,degree).tolist()})
    chosen=min(choices,key=lambda x:(x["selection_loocv_rmse"],x["degree"]))
    return {**chosen,"center":center,"scale":scale,"candidates":choices,
            "scope":"LOOCV chooses degree; selected LOOCV error is model-selection evidence, not a fresh independent test"}


def polynomial_maximum(coefficients,center,scale,lower,upper,upper_open=False):
    if lower>=upper or scale<=0:raise ValueError("invalid temperature domain")
    points=[(float(lower),True),(float(upper),not upper_open)]
    derivative=np.polyder(coefficients)
    for root in np.roots(derivative):
        if abs(root.imag)<1e-10:
            t=float(root.real*scale+center)
            if lower<t<upper:points.append((t,True))
    candidates=[{"temperature_c":t,"predicted_yield_pct":float(np.polyval(coefficients,(t-center)/scale)),"attained":attained} for t,attained in points]
    value=max(row["predicted_yield_pct"] for row in candidates)
    ties=[row for row in candidates if abs(row["predicted_yield_pct"]-value)<=1e-10]
    winner=min(ties,key=lambda row:(not row["attained"],row["temperature_c"]))
    return {**winner,"kind":"maximum" if winner["attained"] else "supremum_not_attained",
            "domain_lower_c":lower,"domain_upper_c":upper,"upper_open":upper_open}


def matched_contrasts(rows):
    grouped={g:[r for r in rows if r["group"]==g] for g in sorted({r["group"] for r in rows})}
    result=[]
    for first,second in combinations(grouped,2):
        a,b=grouped[first][0],grouped[second][0]
        differences=[name for name in FEATURES[1:] if a[name]!=b[name]]
        if len(differences)!=1:continue
        feature=differences[0]
        if a[feature]>b[feature]:first,second=second,first;a,b=b,a
        left={r["temperature_c"]:r for r in grouped[first]};right={r["temperature_c"]:r for r in grouped[second]}
        temperatures=sorted(set(left)&set(right))
        if not temperatures:continue
        differences_by_t=[{"temperature_c":t,**{name:right[t][name]-left[t][name] for name in ("conversion_pct","selectivity_pct","yield_pct")}} for t in temperatures]
        result.append({"from_group":first,"to_group":second,"changed_feature":feature,"from_value":a[feature],"to_value":b[feature],
                       "matched_temperatures":temperatures,"differences":differences_by_t,
                       "mean_differences":{name:float(np.mean([d[name] for d in differences_by_t])) for name in ("conversion_pct","selectivity_pct","yield_pct")},
                       "scope":"all recorded formulation fields except one and temperature matched; batch/randomization unknown, so descriptive contrast rather than causal estimate"})
    return result


def material_series(rows):
    """Vary total charge at fixed composition, or composition at fixed total charge.

    A raw-column-only contrast misses both cases because two masses change together.
    Compare only common measured temperatures, never interpolated values.
    """
    grouped={g:[r for r in rows if r["group"]==g] for g in sorted({r["group"] for r in rows})}
    buckets={}
    for group,points in grouped.items():
        first=points[0]
        controls=(first["co_loading_pct"],first["feed_ml_min"],first["mode_II"],first["quartz_mass_mg"])
        if any(any(p[k]!=first[k] for k in FEATURES[1:]) for p in points):
            raise ValueError("formulation changes within a group")
        co,hap=Fraction(str(first["co_mass_mg"])),Fraction(str(first["hap_mass_mg"]))
        total=co+hap
        if co<=0 or hap<=0:
            continue  # Ratios involving absent HAP are a different material comparison.
        for factor,fixed,value in [("total_mass_mg",co/total,total),("co_mass_fraction",total,co/total)]:
            key=(factor,controls,fixed)
            buckets.setdefault(key,[]).append((value,group))
    result=[]
    for (factor,controls,fixed),items in sorted(buckets.items(),key=lambda x:str(x[0])):
        if len({value for value,_ in items})<2:continue
        items.sort()
        temperatures=sorted(set.intersection(*[{p["temperature_c"] for p in grouped[g]} for _,g in items]))
        if not temperatures:continue
        points=[]
        for value,group in items:
            by_temperature={p["temperature_c"]:p for p in grouped[group]}
            if len(by_temperature)!=len(grouped[group]):raise ValueError("duplicate group temperature requires a replicate policy")
            source=grouped[group][0]
            points.append({"group":group,"factor_value":float(value),"factor_exact":str(value),
                "co_mass_mg":source["co_mass_mg"],"hap_mass_mg":source["hap_mass_mg"],
                "observations":[{"temperature_c":t,"source_row":by_temperature[t]["source_row"],
                    **{target:by_temperature[t][target] for target in ("conversion_pct","selectivity_pct","yield_pct")}} for t in temperatures]})
        result.append({"factor":factor,"fixed_factor":"co_mass_fraction" if factor=="total_mass_mg" else "total_mass_mg",
            "fixed_value":float(fixed),"fixed_exact":str(fixed),
            "controls":dict(zip(("co_loading_pct","feed_ml_min","mode_II","quartz_mass_mg"),controls)),
            "common_temperatures":temperatures,"points":points,
            "scope":"recorded-condition matched material series; no batch, aging or randomized causal identification"})
    return result


def decision(run):
    rows=read_json(run/"artifacts/observations.json")["rows"]
    models=[]
    for group in sorted({r["group"] for r in rows}):
        points=[r for r in rows if r["group"]==group]
        temperatures=[r["temperature_c"] for r in points]
        responses={target:fit_local(temperatures,[r[target] for r in points]) for target in ("conversion_pct","selectivity_pct","yield_pct")}
        model=responses["yield_pct"]
        args=(model["coefficients"],model["center"],model["scale"],min(temperatures))
        unrestricted=polynomial_maximum(*args,max(temperatures))
        low=polynomial_maximum(*args,min(350,max(temperatures)),max(temperatures)>=350)
        grid=np.arange(math.ceil(min(temperatures)),min(350,max(temperatures)+1))
        predicted=np.polyval(model["coefficients"],(grid-model["center"])/model["scale"])
        index=int(np.argmax(predicted))
        models.append({"group":group,"response_models":responses,"unrestricted":unrestricted,"below_350":low,
                       "one_degree_control_grid":{"temperature_c":float(grid[index]),"predicted_yield_pct":float(predicted[index]),
                                                  "scope":"illustrative 1 C control resolution, not stated by the problem; requires experimental confirmation"}})
    observed=max(rows,key=lambda r:r["yield_pct"]);low_observed=max((r for r in rows if r["temperature_c"]<350),key=lambda r:r["yield_pct"])
    workbook=openpyxl.load_workbook(run/"sources/attachment_02__附件2.xlsx",data_only=True)
    stability=[]
    for number,values in enumerate(workbook["稳定性测试"].iter_rows(min_row=4,values_only=True),4):
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):raise ValueError("invalid stability measurement")
        if not all(0<=v<=100 for v in values[1:]) or abs(math.fsum(values[2:])-100)>.011:raise ValueError("stability percentages invalid")
        stability.append({"source_row":number,"time_min":values[0],"conversion_pct":values[1],"selectivity_pct":values[3],"yield_pct":values[1]*values[3]/100})
    workbook.close()
    quantities={name:[r[name] for r in stability] for name in ("conversion_pct","selectivity_pct","yield_pct")}
    summary={name:{"first":v[0],"last":v[-1],"relative_change_pct":100*(v[-1]/v[0]-1),"mean":float(np.mean(v)),"cv_pct":float(100*np.std(v,ddof=1)/np.mean(v))} for name,v in quantities.items()}
    design=[]
    for slot,group,temperature,reason in [(1,"A3",400,"重复最高观测点，检查其可重复性"),(2,"A3",400,"再重复一次，与原观测及第一次新增重复形成三个测量值"),
                                          (3,"A3",425,"补测400至450之间，区分上升、平台和下降趋势"),(4,"A2",349,"在声明的1℃控制示例下检验严格低于350℃的高端候选"),
                                          (5,"A2",325,"重复低温域当前最高观测点，与349℃新点作参照")]:
        source=next(r for r in rows if r["group"]==group)
        design.append({"slot":slot,"group":group,"temperature_c":temperature,"formula":source["formula"],"reason":reason})
    result={"observations_sha256":sha256_file(run/"artifacts/observations.json"),"local_models":models,"matched_contrasts":matched_contrasts(rows),
            "material_series":material_series(rows),
            "stability":{"measurements":stability,"summary":summary,"scope":"seven time points in one experiment; not seven independent experimental replicates"},
            "observed_best":observed,"observed_below_350_best":low_observed,
            "polynomial_best":max(models,key=lambda m:m["unrestricted"]["predicted_yield_pct"])["group"],
            "polynomial_low_best":max(models,key=lambda m:m["below_350"]["predicted_yield_pct"])["group"],
            "experiment_design":{"total_new_runs":5,"base_plan":design,
                "branch":"If the first two repeated A3/400 runs fail the laboratory predeclared repeatability criterion, use the remaining three slots as repeats/control checks instead of adding runs beyond five. This dataset does not identify that laboratory tolerance.",
                "sequence":"Randomize the last three run order after the initial repeatability check, record batch and reaction time; do not compare unmatched aging times.",
                "scope":"proposal targeted at current decision uncertainty, not a D-optimal or proven globally optimal design; no invented repeatability threshold"}}
    write_json(run/"artifacts/decisions.json",result)
    print({"observed_best":[observed["group"],observed["temperature_c"],observed["yield_pct"]],"matched_pairs":len(result["matched_contrasts"]),"low_polynomial":result["polynomial_low_best"]},flush=True)
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("run",type=Path);decision(p.parse_args().run)
