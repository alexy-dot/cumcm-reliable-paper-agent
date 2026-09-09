"""Integrate and verify both baseline and alternative-prior posterior policy searches."""
import argparse
from pathlib import Path
from exact_posterior import solve
from verify_exact_posterior import verify
from prepare import read_json,write_json,sha256_file


def study(run):
    folder=run/"artifacts/exact_posterior";folder.mkdir(exist_ok=False)
    inputs=[(f"uniform-n{n}",run/f"artifacts/example-n{n}.json",run/f"artifacts/uncertainty-n{n}") for n in (20,200)]
    prior=run/"artifacts/prior_sensitivity"
    for name in ("Jeffreys","mean_0.1_strength_20"):
        for n in (20,200):
            label=f"illustrative_n{n}_{name}"
            inputs.append((label,prior/(label+".json"),prior/label))
    write_json(folder/"protocol.json",{"inputs":[{"label":label,"samples_sha256":sha256_file(samples),"mc_result_sha256":sha256_file(mc/"result.json")} for label,samples,mc in inputs],
        "scope":"exact comparison using the same illustrative sample scenarios and priors as prior reports; no new observed data"})
    rows=[]
    for label,samples,mc in inputs:
        result=solve(run,samples,folder/label);verification=verify(run,folder/label,mc)
        rows.append({"label":label,"input_samples_sha256":sha256_file(samples),"results":{name:{"policy_count":r["policy_count"],"best_policies":r["best_policies"]} for name,r in result["results"].items()},
            "mc_policy_comparisons":verification["mc_policy_comparisons"],"verification_passed":verification["passed"],
            "result_sha256":sha256_file(folder/label/"result.json"),"verification_sha256":sha256_file(folder/label/"verification.json")})
    write_json(folder/"summary.json",{"scenarios":rows,"protocol_sha256":sha256_file(folder/"protocol.json"),"scope":"exact conditional posterior mean within the declared policy class, not a guarantee under other priors or adaptive recovery policies"})


def checked_report(run):
    folder=run/"artifacts/exact_posterior";summary=read_json(folder/"summary.json")
    if len(summary["scenarios"])!=6 or summary["protocol_sha256"]!=sha256_file(folder/"protocol.json"):
        raise ValueError("exact posterior study incomplete or stale")
    for row in summary["scenarios"]:
        if not row["verification_passed"] or row["result_sha256"]!=sha256_file(folder/row["label"]/"result.json") or row["verification_sha256"]!=sha256_file(folder/row["label"]/"verification.json"):
            raise ValueError("exact posterior scenario changed")
    return summary


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);study(p.parse_args().run)
