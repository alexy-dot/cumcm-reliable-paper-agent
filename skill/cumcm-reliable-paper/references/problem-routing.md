# Problem routing and minimum evidence

Route only after completing the problem contract. A problem may use multiple routes; preserve the data and uncertainty passed between them.

| Task structure | Typical chain | Minimum independent evidence |
|---|---|---|
| Mechanism and dynamics | conservation/geometry -> state equations -> parameter identification -> numerical solution -> constrained decision | dimensions, conservation, boundary conditions, convergence, known or extreme case |
| Prediction to decision | data audit -> interpretable baseline -> entity/time split -> uncertainty -> constrained decision | leakage-free holdout, simple baseline, residuals/calibration, error propagation into decisions |
| Probability and risk | random variables -> event decomposition -> integration/simulation -> risk rule -> decision | normalization, exact small case, analytic/simulation agreement, confidence interval and convergence |
| Recognition and signals | acquisition audit -> denoise -> features/model -> isolated validation -> failure analysis | synthetic truth or labeled holdout, confusion/error structure, parameter sensitivity, identifiable scope |
| Network, scheduling, planning | graph/state -> capacity/time/resource constraints -> baseline -> exact/heuristic solve | per-constraint residuals, enumeration/relaxation bound; for online work, replay event prefixes and preserve initiated actions; multi-seed checks for heuristics |
| Monitoring and control | metric reconciliation -> trend/season/change -> forecast/state estimate -> policy | conservation/accounting reconciliation, rolling holdout, counterfactual or baseline, operational constraints |

## Selection rules

1. Start with a transparent executable baseline.
2. Upgrade only for an observed limitation, not because a method name appears advanced.
3. Freeze the decision time, available event prefix and irreversible actions before constructing a predictor or plan. A clairvoyant optimum may provide a retrospective bound, but cannot be used as an online decision input.
4. Separate model fit, parameter identifiability, predictive validity, and decision feasibility.
5. Exploit structural bounds before adding a solver: if a primary piece cannot hold two valid products, its recovery can be evaluated locally and used as a graph-edge cost. If a feasible solution attains a valid relaxation bound, state exactly which objective and initial conditions that certifies; do not extend it to secondary objectives or other initial states.
6. Propagate uncertainty when an upstream estimate enters a downstream optimization.

For numeric grouped regression, `scripts/grouped_regression.py` provides `evaluate_grouped(x, y, groups, families, ...)` with outer group-held-out predictions and training-only inner model selection. Install the optional `scripts/requirements-statistics.txt`. Specify the independent unit and numeric candidate features yourself; the helper cannot infer them. Compare a training-fold mean and a relevant simple predictor, and report group-weighted and row-weighted errors separately. A global response mean is valid in the usual descriptive R² denominator, but is not a deployable held-out mean predictor. Exchange group-constant dependent descriptors jointly using `permute_group_descriptors`; do not turn that predictive-dependence experiment into a component-level causal effect.

When a model choice depends on a small difference, `group_splits(groups, folds=5, seed=...)` can test alternate group assignments while keeping model candidates fixed. It balances group counts; the default without a seed balances row counts through GroupKFold. Report each partition's errors and reversals. Reusing the same groups across partitions gives sensitivity evidence, not independent experiments, confidence intervals or a reason to select the most flattering partition.

`polynomial_reference.py::predict_reference(train_x, train_y, query_x, degree=1|2, alpha=...)` independently fits standardized polynomial least squares/ridge using explicit monomials and NumPy SVD. Compare raw predictions before physical clipping, including constant and dependent columns; the intercept is not penalized. This reference verifies the fitted model conditional on specified hyperparameters, not their selection or a different estimator such as a random forest.
