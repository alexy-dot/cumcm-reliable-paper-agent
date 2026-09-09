"""Compute model-conditional scenario-feasible alternatives, then run a sealed holdout.

Does not certify the entire uncertainty box or physical production reliability.
The Q4 area cap is relative to this design's worst-case Q3 candidate, not a silent
replacement of the nominal Q4 answer.
"""
import argparse
import itertools
import sys
from pathlib import Path
from functools import lru_cache

import numpy as np
from scipy.optimize import minimize
from scipy.stats import qmc

from model import curve_metrics, margins
from decision_evidence import joint_parameters
from independent import independently_solve

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill/cumcm-reliable-paper/scripts"))
from engine import read_json, write_json, sha256_file

BOUNDS=[(165,185),(185,205),(225,245),(245,265),(65,100)]
SCALES=np.array([3.,3.,60.,60.,50.,50.,10.,10.])
RESERVES=np.array([.005,.005,.1,.1,.1,.1,.02,.02])
MARGIN_NAMES=["rise_upper","cooling_upper","soak_lower","soak_upper","liquid_lower","liquid_upper","peak_lower","peak_upper"]


def design_parameters(parameters):
    vertices=np.array(list(itertools.product([0.,1.],repeat=7)))
    interior=qmc.Sobol(7,scramble=True,seed=314159).random_base2(m=5)
    return np.vstack([np.asarray(parameters),joint_parameters(parameters,vertices),joint_parameters(parameters,interior)])


def evaluate_controls(control, parameters, dx=.25):
    outcomes=[curve_metrics(control[:4],control[4],p,dx=dx) for p in parameters]
    slacks=np.array([margins(row) for row in outcomes])
    if not np.all(np.isfinite(slacks)):
        raise ValueError("nonfinite scenario margins")
    return outcomes,slacks


def solve_alternative(name, parameters, starts, *, q4_cap=None):
    @lru_cache(maxsize=32)
    def evaluate(values):
        return evaluate_controls(np.array(values),parameters)
    def unpack(x):
        return np.r_[starts[0][:4],x[0]] if name=="Q2" else x[:5]
    def constraints(x):
        outcomes,slacks=evaluate(tuple(unpack(x)))
        constraints=((np.min(slacks,axis=0)-RESERVES)/SCALES).tolist()
        if name=="Q3":
            constraints.append(x[5]-max(row["area_rising_above_217"] for row in outcomes)/1000)
        elif name=="Q4":
            constraints.append(x[5]-max(row["symmetry"] for row in outcomes))
            constraints.append((q4_cap-max(row["area_rising_above_217"] for row in outcomes))/1000)
        return np.array(constraints)
    objective=(lambda x:-x[0]/100) if name=="Q2" else (lambda x:x[5])
    attempts=[]
    best=None
    for start in starts:
        outcomes,_=evaluate(tuple(start))
        initial=[start[4]] if name=="Q2" else [*start,
            max(row["area_rising_above_217"] for row in outcomes)/1000 if name=="Q3" else max(row["symmetry"] for row in outcomes)]
        bounds=[(65,100)] if name=="Q2" else BOUNDS+[(0,10)]
        result=minimize(objective,initial,method="SLSQP",bounds=bounds,
                        constraints={"type":"ineq","fun":constraints},
                        options={"maxiter":160,"ftol":1e-9,"eps":1e-5})
        smallest=float(np.min(constraints(result.x)))
        feasible=smallest>=-1e-7
        attempts.append({"start":list(start),"success":bool(result.success),"message":str(result.message),
                         "iterations":int(result.nit),"smallest_scaled_margin":smallest,"objective":float(result.fun),
                         "controls":unpack(result.x).tolist(),"feasible":bool(feasible)})
        if feasible and (best is None or result.fun<best.fun):
            best=result
        print(name,attempts[-1],flush=True)
    if best is None:
        return {"found":False,"attempts":attempts,"status":"no feasible candidate found; not an infeasibility certificate"}
    controls=unpack(best.x)
    outcomes,slacks=evaluate_controls(controls,parameters,dx=.05)
    result={"found":True,"controls":controls.tolist(),"design_minimum_margins":np.min(slacks,axis=0).tolist(),
            "design_worst_area":max(row["area_rising_above_217"] for row in outcomes),
            "design_worst_symmetry":max(row["symmetry"] for row in outcomes),"attempts":attempts,
            "q4_area_cap":q4_cap,"search_scope":"multi-start local SLSQP epigraph; no global certificate"}
    result["fine_design_feasible"]=bool(np.min(slacks)>=-1e-4 and (q4_cap is None or result["design_worst_area"]<=q4_cap+1e-3))
    return result


def holdout_summary(control, parameters, *, area_cap=None):
    outcomes,slacks=evaluate_controls(control,parameters,dx=.05)
    return {"count":len(parameters),"process_violations":int(np.any(slacks < -1e-4,axis=1).sum()),
            "minimum_margins":np.min(slacks,axis=0).tolist(),
            "worst_area":max(row["area_rising_above_217"] for row in outcomes),
            "worst_symmetry":max(row["symmetry"] for row in outcomes),
            "area_cap_violations":sum(row["area_rising_above_217"]>area_cap+1e-3 for row in outcomes) if area_cap is not None else None,
            "worst_peak_index":int(np.argmin(slacks[:,6])),"worst_soak_index":int(np.argmin(slacks[:,2]))}


def run_design(run):
    solution=read_json(run/"artifacts/solution.json")
    parameters=solution["parameters"]
    training=design_parameters(parameters)
    def controls(question):
        point=solution[question]
        return np.r_[point["settings"],point["speed_cm_min"]]
    q2=solve_alternative("Q2",training,[np.r_[controls("Q2")[:4],77.],np.r_[controls("Q2")[:4],75.]])
    q3=solve_alternative("Q3",training,[np.r_[controls("Q3")[:4],96.],np.array([182.,200.,235.,265.,96.])])
    q4_cap=1.05*q3["design_worst_area"] if q3["found"] and q3["fine_design_feasible"] else None
    q4=solve_alternative("Q4",training,[np.r_[controls("Q4")[:4],88.],np.array(q3["controls"])],q4_cap=q4_cap) if q4_cap else {"found":False,"status":"no valid Q3 reference"}
    candidates={"schema_version":"1.0","status":"CANDIDATES_FROZEN_BEFORE_HOLDOUT",
                "source_sha256":sha256_file(run/"artifacts/solution.json"),"training_parameters":training.tolist(),
                "design_definition":"nominal + 128 vertices + 32 Sobol interior points (seed 314159)",
                "box":"six parameters +/-2%; entry width -2% to nominal; a specified engineering set, not an estimated confidence set",
                "reserve_units":"first two C/s; next four seconds; last two C",
                "reserves":RESERVES.tolist(),"margin_names":MARGIN_NAMES,
                "Q2":q2,"Q3":q3,"Q4":q4,
                "Q4_policy":"new scenario design: minimize worst scenario J with worst area <= 1.05 times scenario Q3 design worst area"}
    candidate_path=run/"artifacts/scenario_candidates.json"
    write_json(candidate_path,candidates)
    candidate_hash=sha256_file(candidate_path)
    # Held-out points are generated ONLY after candidate serialization. No tuning below.
    holdout=joint_parameters(parameters,qmc.Sobol(7,scramble=True,seed=271828).random_base2(m=9))
    checks={}
    for question in ("Q2","Q3","Q4"):
        point=candidates[question]
        if not point["found"]:
            checks[question]={"tested":False}
            continue
        control=np.array(point["controls"])
        results=holdout_summary(control,holdout,area_cap=point.get("q4_area_cap"))
        verification=[]
        indices=sorted({results["worst_peak_index"],results["worst_soak_index"]})
        for index in indices:
            nominal=curve_metrics(control[:4],control[4],holdout[index],dx=.05)
            _,independent=independently_solve(control[:4],control[4],holdout[index])
            passed=abs(nominal["peak"]-independent["peak"])<.005 and abs(nominal["area_rising_above_217"]-independent["area_rising_above_217"])<.1 and abs(nominal["soak_150_190"]-independent["soak_150_190"])<.01
            independent_feasible=bool(np.min(margins(independent))>=-1e-4 and (point.get("q4_area_cap") is None or independent["area_rising_above_217"]<=point["q4_area_cap"]+1e-3))
            verification.append({"index":index,"passed":bool(passed and independent_feasible),"numerical_agreement":bool(passed),
                                 "independent_feasible":independent_feasible,"independent_metrics":independent})
        checks[question]={"tested":True,**results,"independent_checks":verification,
                          "nominal_metrics":curve_metrics(control[:4],control[4],parameters,dx=.05)}
        print("holdout",question,{key:value for key,value in results.items() if key not in ("minimum_margins",)},flush=True)
    if sha256_file(candidate_path)!=candidate_hash:
        raise ValueError("candidates changed after holdout generation")
    report={"candidate_sha256":candidate_hash,"candidates":candidates,"holdout_parameters":holdout.tolist(),
            "holdout_definition":"512 separate scrambled Sobol points, seed 271828; no subsequent retuning",
            "checks":checks,"claim_scope":"finite-design and held-out scenario feasibility only; neither whole-box nor physical reliability is certified",
            "submission_ready":False}
    report["passed"]=all(candidates[q].get("fine_design_feasible",False) and checks[q].get("tested",False)
                         and checks[q]["process_violations"]==0 and checks[q]["area_cap_violations"] in (None,0)
                         and all(v["passed"] for v in checks[q]["independent_checks"]) for q in ("Q2","Q3","Q4"))
    write_json(run/"artifacts/scenario_design.json",report)
    print({"passed":report["passed"],"scope":report["claim_scope"]},flush=True)
    return report["passed"]


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run",type=Path)
    raise SystemExit(0 if run_design(parser.parse_args().run) else 1)
