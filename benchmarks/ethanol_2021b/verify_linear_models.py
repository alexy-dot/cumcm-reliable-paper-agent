"""Re-fit every recorded temperature-only and ridge outer-fold model independently."""
import argparse
from pathlib import Path
import numpy as np
from prepare import read_json, write_json, sha256_file, PROJECT
from polynomial_reference import predict_reference

ATOL = 1e-7  # Percentage points; fixed before comparison, not a model-error tolerance.
FAMILIES = ("temperature_only", "ridge")


def compare_models(observations, result):
    rows = observations["rows"]
    x = np.array([[row[f] for f in observations["features"]] for row in rows])
    groups = np.array([row["group"] for row in rows])
    checks = []
    for target in ("conversion_pct", "selectivity_pct", "yield_pct"):
        output = result["targets"][target]
        y = np.array([row[target] for row in rows])
        folds = output["folds"]
        for family in FAMILIES:
            model = output["models"][family]
            raw = np.asarray(model["raw_prediction"], float)
            clipped = np.asarray(model["prediction"], float)
            if raw.shape != y.shape or clipped.shape != y.shape or not np.isfinite(raw).all() or not np.isfinite(clipped).all():
                raise ValueError("invalid stored prediction vector")
            choices = {row["fold"]: row["selected"] for row in model["selection"]}
            if len(choices) != len(folds):
                raise ValueError("model-selection records do not cover folds")
            seen = []
            for fold in folds:
                train, test = np.array(fold["train_rows"]), np.array(fold["test_rows"])
                if not np.issubdtype(train.dtype, np.integer) or not np.issubdtype(test.dtype, np.integer):
                    raise ValueError("fold indices must be integers")
                if min(train.min(),test.min()) < 0 or max(train.max(),test.max()) >= len(rows):
                    raise ValueError("fold row outside observation range")
                if len(set(train)) != len(train) or len(set(test)) != len(test) or set(groups[train]) & set(groups[test]):
                    raise ValueError("duplicate rows or overlapping train/test groups")
                if set(train) | set(test) != set(range(len(rows))):
                    raise ValueError("fold excludes observations from both sides")
                spec = choices[fold["fold"]]
                if spec["kind"] != "polynomial":
                    raise ValueError("unsupported model in a polynomial family")
                columns = spec["columns"]
                independent, diagnostic = predict_reference(x[np.ix_(train,columns)], y[train], x[np.ix_(test,columns)],
                                                           degree=spec["degree"], alpha=spec.get("alpha",0.))
                raw_error = float(np.max(np.abs(raw[test]-independent)))
                clipped_error = float(np.max(np.abs(clipped[test]-np.clip(independent,0,100))))
                checks.append({"target":target, "family":family, "fold":fold["fold"], "query_rows":test.tolist(),
                    "independent_raw_prediction":independent.tolist(), "selected_spec":spec,
                    "max_raw_error":raw_error, "max_clipped_error":clipped_error,
                    "passed":raw_error<=ATOL and clipped_error<=ATOL, "diagnostic":diagnostic})
                seen.extend(test.tolist())
            if sorted(seen) != list(range(len(rows))):
                raise ValueError("outer query coverage must equal each observation exactly once")
    return checks


def verify(run):
    folder = run/"artifacts/linear_model_verification"
    folder.mkdir(exist_ok=False)
    observations = read_json(run/"artifacts/observations.json")
    sources = {"original":"artifacts/statistical_results.json", **{str(seed):f"artifacts/split_sensitivity/seed-{seed}.json" for seed in (17,43,97)}}
    protocol = {"atol_percentage_points":ATOL, "rtol":0, "families":list(FAMILIES),
        "observations_sha256":sha256_file(run/"artifacts/observations.json"),
        "sources":{key:{"path":value,"sha256":sha256_file(run/value)} for key,value in sources.items()},
        "reference_code_sha256":sha256_file(PROJECT/"skill/cumcm-reliable-paper/scripts/polynomial_reference.py"),
        "scope":"independent re-fitting conditional on recorded selected hyperparameters and outer indices; does not independently reselect inner folds or reimplement random forests"}
    write_json(folder/"protocol.json", protocol)
    comparisons = {key:compare_models(observations,read_json(run/path)) for key,path in sources.items()}
    checks = [c for group in comparisons.values() for c in group]
    report = {"passed":all(c["passed"] for c in checks), "protocol_sha256":sha256_file(folder/"protocol.json"),
              "fold_models":len(checks), "heldout_predictions":sum(len(c["query_rows"]) for c in checks),
              "max_raw_error":max(c["max_raw_error"] for c in checks),
              "max_clipped_error":max(c["max_clipped_error"] for c in checks),
              "comparisons":comparisons, "scope":protocol["scope"]}
    write_json(folder/"report.json",report)
    print({k:v for k,v in report.items() if k!="comparisons"},flush=True)
    if not report["passed"]:
        raise ValueError("independent polynomial model predictions disagree")
    return report


def checked_report(run):
    folder=run/"artifacts/linear_model_verification"
    report=read_json(folder/"report.json");protocol=read_json(folder/"protocol.json")
    if report.get("passed") is not True or report["protocol_sha256"]!=sha256_file(folder/"protocol.json"):
        raise ValueError("independent model verification failed or protocol changed")
    if protocol["observations_sha256"]!=sha256_file(run/"artifacts/observations.json"):
        raise ValueError("independent model verification predates current observations")
    for source in protocol["sources"].values():
        if sha256_file(run/source["path"])!=source["sha256"]:
            raise ValueError("recorded model predictions changed after independent verification")
    checks=[c for group in report["comparisons"].values() for c in group]
    if len(checks)!=120 or sum(len(c["query_rows"]) for c in checks)!=2736 or not all(c["passed"] for c in checks):
        raise ValueError("independent model coverage is incomplete")
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("run",type=Path);verify(p.parse_args().run)
