"""Fit the frozen calibration run, retaining baseline and withheld-block residuals."""
import argparse
import sys
from pathlib import Path
import numpy as np
import openpyxl
from scipy.optimize import least_squares

from model import BASE_SETTINGS, temperature_curve, curve_metrics
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill/cumcm-reliable-paper/scripts"))
from engine import write_json


def fit(run):
    workbook = openpyxl.load_workbook(run / "sources/attachment_01__附件.xlsx", read_only=True, data_only=True)
    observed = np.asarray(list(workbook.active.values)[1:], dtype=float)
    workbook.close()
    time, temp = observed.T
    models = {}
    for mode, initial, bounds in [
        ("baseline", [50.], ([1.], [300.])),
        ("mixing", [50., 5., 75.], ([1., .5, 1.], [300., 80., 200.])),
        ("radiative", [50., 5., 40., .5], ([20., .5, 1., 0.], [150., 80., 200., 1.])),
        ("two_node", [.1, .01, .03, .03, 10.], ([.001, .001, .0001, .001, .5], [2., 2., 2., 2., 1000.])),
        ("smooth_two_node", [.5, .02, .003, .02, 25., 10.],
         ([.005, .001, .0001, .001, 0., 2.5], [2., 2., 2., 2., 30.5, 17.75])),
        ("zoned", [50., 50., 40., 45., 55., 25., 55.],
         ([10., 10., 10., 10., 10., 0., 1.], [150., 150., 150., 150., 200., 30.5, 200.]))]:
        def residual(parameters, mask):
            t, y = temperature_curve(BASE_SETTINGS, 70, parameters, mode=mode, dx=.1)
            return np.interp(time[mask], t, y) - temp[mask]
        # Withhold contiguous blocks throughout the trajectory, including cooling.
        holdout = (np.floor(time / 20).astype(int) % 4) == 2
        training = ~holdout
        res = least_squares(lambda p: residual(p, training), initial, bounds=bounds,
                            xtol=1e-11, ftol=1e-11, gtol=1e-11)
        held_errors = residual(res.x, holdout)
        full = least_squares(lambda p: residual(p, np.ones(len(time), dtype=bool)), res.x,
                             bounds=bounds, xtol=1e-11, ftol=1e-11, gtol=1e-11)
        errors = residual(full.x, np.ones(len(time), dtype=bool))
        covariance = np.linalg.pinv(full.jac.T @ full.jac) * np.sum(errors ** 2) / (len(time) - len(full.x))
        models[mode] = {"parameters": full.x.tolist(), "rmse": float(np.sqrt(np.mean(errors ** 2))),
                        "max_abs_error": float(np.max(np.abs(errors))), "held_block_rmse": float(np.sqrt(np.mean(held_errors ** 2))),
                        "train_parameters": res.x.tolist(), "train_count": int(training.sum()), "held_count": int(holdout.sum()),
                        "parameter_standard_errors_iid_diagnostic_only": np.sqrt(np.diag(covariance)).tolist(),
                        "jacobian_condition": float(np.linalg.cond(full.jac)), "success": bool(full.success)}
    write_json(run / "artifacts/calibration.json", {"n": len(time), "record_start_seconds": float(time[0]),
              "record_end_seconds": float(time[-1]), "models": models,
              "warning": "one physical run only; blocked interpolation is not independent experimental validation; IID standard errors are diagnostic"})
    print(models, flush=True)
    print("calibrated metrics", curve_metrics(BASE_SETTINGS, 70, models["zoned"]["parameters"]), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("run", type=Path)
    fit(p.parse_args().run)
