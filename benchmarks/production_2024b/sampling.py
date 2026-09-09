"""Anytime-valid directional mixture tests; finite-horizon operating characteristics."""
import argparse
import math
from pathlib import Path
import numpy as np
from scipy.special import betaln,betainc,betaincc
from scipy.stats import binom
from prepare import read_json,write_json


def log_evidence(n,k,p0=.1):
    if not 0<p0<1 or not 0<=k<=n:raise ValueError("invalid count or null rate")
    common=betaln(k+1,n-k+1)-k*math.log(p0)-(n-k)*math.log1p(-p0)
    low=betainc(k+1,n-k+1,p0);high=betaincc(k+1,n-k+1,p0)
    return {"accept":common+math.log(low)-math.log(p0) if low else -math.inf,
            "reject":common+math.log(high)-math.log1p(-p0) if high else -math.inf}


def boundaries(cap,p0,reject_error,accept_error,method="mixture"):
    result=[]
    for n in range(1,cap+1):
        accepts=[];rejects=[]
        for k in range(n+1):
            if method=="mixture":
                evidence=log_evidence(n,k,p0)
                accept=evidence["accept"]>=math.log(1/accept_error)
                reject=evidence["reject"]>=math.log(1/reject_error)
            elif method=="naive_repeated_fixed_test":
                accept=binom.cdf(k,n,p0)<=accept_error
                reject=binom.sf(k-1,n,p0)<=reject_error
            else:raise ValueError("unknown test method")
            if accept and reject:raise ValueError("overlapping decision regions")
            if accept:accepts.append(k)
            if reject:rejects.append(k)
        result.append({"n":n,"accept_at_most":max(accepts) if accepts else None,"reject_at_least":min(rejects) if rejects else None})
    return result


def operating_characteristic(table,p):
    active=np.array([1.]);accepted=rejected=expected=0.
    for row in table:
        expected+=float(active.sum())
        next_state=np.zeros(len(active)+1)
        next_state[:-1]+=active*(1-p);next_state[1:]+=active*p
        a,r=row["accept_at_most"],row["reject_at_least"]
        if a is not None:accepted+=float(next_state[:a+1].sum());next_state[:a+1]=0
        if r is not None:rejected+=float(next_state[r:].sum());next_state[r:]=0
        active=next_state
    unresolved=float(active.sum())
    if abs(accepted+rejected+unresolved-1)>1e-10:raise ValueError("sampling path probability does not conserve mass")
    return {"true_defect_rate":p,"accept_probability":accepted,"reject_probability":rejected,
            "unresolved_probability":unresolved,"expected_tests_up_to_cap":expected}


def solve(run):
    settings=read_json(run/"artifacts/facts.json")["sampling"]
    table=boundaries(settings["cap"],settings["nominal_rate"],settings["reject_error"],settings["accept_error"])
    naive=boundaries(settings["cap"],settings["nominal_rate"],settings["reject_error"],settings["accept_error"],"naive_repeated_fixed_test")
    rates=[.01,.05,.1,.15,.2,.3]
    report={"boundaries":table,"operating_characteristics":[operating_characteristic(table,p) for p in rates],
            "naive_repeated_fixed_tests_at_boundary":operating_characteristic(naive,.1),
            "validity":"Ville inequality controls probability of ever rejecting under p<=0.1 by 0.05, and ever accepting under p>=0.1 by 0.10, under iid Bernoulli sampling",
            "cap_policy":"At 300 observations, unresolved remains unresolved; do not force acceptance or rejection",
            "minimality":"No unique sample-size optimum is identified without separation from 0.1, power/indifference requirements or sampling/decision costs. These are valid sequential boundaries, not a proof of minimum expected sample size.",
            "fixed_design_examples":{"all_good_accept_n":next(n for n in range(1,1000) if .9**n<=.1),"all_bad_reject_n":next(n for n in range(1,1000) if .1**n<=.05),
                "scope":"predeclared fixed-size examples only; cannot repeatedly apply fixed-sample confidence thresholds without correcting optional stopping"}}
    write_json(run/"artifacts/sampling.json",report)
    print(report["operating_characteristics"],report["naive_repeated_fixed_tests_at_boundary"],flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);solve(p.parse_args().run)
