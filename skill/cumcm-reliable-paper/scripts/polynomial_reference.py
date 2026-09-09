"""Independent NumPy reference for standardized degree-1/2 least squares and ridge.

No sklearn feature expansion, scaler, estimator or grouped-regression helper is used.
The intercept is unpenalized. Inputs are training data and query covariates only.
"""
import numpy as np


def expand(x, degree):
    x = np.asarray(x, dtype=float)
    if x.ndim != 2 or x.shape[1] == 0 or not np.isfinite(x).all():
        raise ValueError("expected a finite nonempty-column feature matrix")
    if degree not in (1, 2):
        raise ValueError("reference supports degree 1 or 2")
    columns = [x[:, i] for i in range(x.shape[1])]
    if degree == 2:
        columns.extend(x[:, i] * x[:, j] for i in range(x.shape[1]) for j in range(i, x.shape[1]))
    result = np.column_stack(columns)
    if not np.isfinite(result).all():
        raise ValueError("polynomial expansion overflowed")
    return result


def predict_reference(train_x, train_y, query_x, *, degree=1, alpha=0.):
    train, query = expand(train_x, degree), expand(query_x, degree)
    y = np.asarray(train_y, dtype=float)
    if len(train) < 2 or y.shape != (len(train),) or not np.isfinite(y).all():
        raise ValueError("expected at least two training rows with finite aligned targets")
    if train.shape[1] != query.shape[1] or not np.isfinite(alpha) or alpha < 0:
        raise ValueError("incompatible query columns or invalid ridge penalty")
    center = train.mean(axis=0)
    variance = ((train-center)**2).mean(axis=0)
    # Match the declared StandardScaler treatment of numerically constant columns.
    # Threshold follows floating-point error bounds; query data never sets scaling.
    eps = np.finfo(float).eps
    constant = variance <= len(train)*eps*variance + (len(train)*center*eps)**2
    scale = np.sqrt(variance)
    scale[constant] = 1.
    design = (train-center)/scale
    query_design = (query-center)/scale
    residual_center = design.mean(axis=0)
    design -= residual_center
    query_design -= residual_center
    mean_y = y.mean()
    u, singular, vt = np.linalg.svd(design, full_matrices=False)
    if alpha:
        weights = singular/(singular**2+alpha)
    else:
        cutoff = max(design.shape)*eps*(singular[0] if len(singular) else 0.)
        weights = np.divide(1., singular, out=np.zeros_like(singular), where=singular>cutoff)
    coefficient = vt.T @ (weights * (u.T @ (y-mean_y)))
    prediction = query_design @ coefficient + mean_y
    gradient = design.T @ (design @ coefficient-(y-mean_y)) + alpha*coefficient
    return prediction, {"expanded_columns":train.shape[1], "constant_columns":int(constant.sum()),
                        "stationarity_max_abs":float(np.max(np.abs(gradient))),
                        "method":"explicit monomials, training-only population scaling, unpenalized intercept, NumPy SVD"}
