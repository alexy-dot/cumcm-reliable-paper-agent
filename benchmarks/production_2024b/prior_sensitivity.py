"""Compare fixed alternative priors on the same explicitly illustrative Q4 counts."""
import argparse
from copy import deepcopy
from pathlib import Path
from prepare import read_json,write_json,sha256_file
from sampled_rates import solve
from verify_sampled_rates import verify

PRIORS=[{"name":"Jeffreys","alpha":.5,"beta":.5},
        {"name":"mean_0.1_strength_20","alpha":2.,"beta":18.}]


def study(run):
    output=run/"artifacts/prior_sensitivity";output.mkdir(exist_ok=False)
    protocol={"priors":PRIORS,"sample_sizes":[20,200],
        "source_samples":{str(n):sha256_file(run/f"artifacts/example-n{n}.json") for n in (20,200)},
        "scope":"same illustrative counts under declared alternative independent priors; Beta(2,18) expresses hypothetical prior information and is not empirically established",
        "selection":"same 512 selection draws and 8192 separate validation draws; prior scenarios frozen before selection; no retuning after validation"}
    write_json(output/"protocol.json",protocol)
    rows=[]
    for n in protocol["sample_sizes"]:
        for prior in PRIORS:
            sample=deepcopy(read_json(run/f"artifacts/example-n{n}.json"))
            sample["prior"]={key:prior[key] for key in ("alpha","beta")}
            sample["label"]=f"illustrative_n{n}_{prior['name']}"
            path=output/(sample["label"]+".json");write_json(path,sample)
            folder=output/sample["label"]
            solve(run,path,folder);checked=verify(run,folder)
            result=read_json(folder/"result.json")
            baseline=read_json(run/f"artifacts/uncertainty-n{n}/result.json")
            for name,value in result["results"].items():
                verification=next((r for r in checked["checks"] if r["problem"]==name),None)
                rows.append({"n":n,"prior":prior,"problem":name,"selected_policy":value["selected_policy"],
                    "changed_from_uniform_prior":value["selected_policy"]!=baseline["results"][name]["selected_policy"],
                    "validation_mean_cost":value["selected"]["posterior_mean_cost"],
                    "deterministic_selected_cost":verification.get("quadrature_selected_cost",verification.get("analytic_cost")) if verification else None,
                    "deterministic_selection_gap":verification.get("selected_gap") if verification else None,
                    "verification_passed":checked["passed"]})
    result={"protocol_sha256":sha256_file(output/"protocol.json"),"results":rows,
        "scope":protocol["scope"],"subresults_sha256":{str(path.relative_to(output)):sha256_file(path) for path in sorted(output.glob("*/result.json"))}}
    write_json(output/"report.json",result)
    print({"changed":[(r["n"],r["prior"]["name"],r["problem"]) for r in rows if r["changed_from_uniform_prior"]]},flush=True)


def checked_report(run):
    output=run/"artifacts/prior_sensitivity";report=read_json(output/"report.json");protocol=read_json(output/"protocol.json")
    if report["protocol_sha256"]!=sha256_file(output/"protocol.json"):raise ValueError("prior sensitivity protocol changed")
    for n,digest in protocol["source_samples"].items():
        if sha256_file(run/f"artifacts/example-n{n}.json")!=digest:raise ValueError("sample counts changed after prior sensitivity")
    for path,digest in report["subresults_sha256"].items():
        if sha256_file(output/path)!=digest:raise ValueError("prior scenario output changed")
        verification=read_json((output/path).with_name("verification.json"))
        if not verification["passed"] or verification["result_sha256"]!=digest:raise ValueError("prior scenario verification failed or stale")
    if len(report["results"])!=28 or not all(r["verification_passed"] for r in report["results"]):raise ValueError("prior sensitivity is incomplete")
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);study(p.parse_args().run)
