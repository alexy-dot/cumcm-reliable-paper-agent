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

For ordered contour or trajectory registration, `scripts/curve_coverage.py` provides `directed_coverage(source, target, tolerance=..., step=...)` and `compare_curves`. It measures arc-length coverage and missing intervals over the full supplied curves, with discretization bounds; NumPy/SciPy are optional dependencies. A small trimmed overlap residual can coexist with substantial missing geometry. Choose the physically meaningful overlap/domain before judging either direction, keep censored intervals separate, and do not confuse a reference-trace consensus with a union of all observations. Local fitted parameters only revise a global contour after feature correspondence and a geometric update have actually been performed.

1. Start with a transparent executable baseline.
2. Upgrade only for an observed limitation, not because a method name appears advanced.
3. Freeze the decision time, available event prefix and irreversible actions before constructing a predictor or plan. A clairvoyant optimum may provide a retrospective bound, but cannot be used as an online decision input.
4. Separate model fit, parameter identifiability, predictive validity, and decision feasibility.
5. Exploit structural bounds before adding a solver: if a primary piece cannot hold two valid products, its recovery can be evaluated locally and used as a graph-edge cost. If a feasible solution attains a valid relaxation bound, state exactly which objective and initial conditions that certifies; do not extend it to secondary objectives or other initial states.
6. Propagate uncertainty when an upstream estimate enters a downstream optimization.

For sequential inspection, a fixed-sample confidence threshold does not retain its error guarantee when checked after every observation. Use a justified sequential test or an explicit error-spending rule; report unresolved outcomes at a sampling cap. For rework, preserve defective-item identity and inspection knowledge across reuse. Check for reachable failure cycles before computing expected profit, and count free customer replacements as costs rather than new sales.

In tree-structured assembly, keep acquisition cost, defect probability and repair cost conditional on a confirmed defect separate. If a bad child necessarily makes its parent bad, the child's repair contribution conditioned on parent failure uses the corresponding conditional probability; failed-parent children are generally dependent. Additive expected costs do not require conditional independence. Verify a hierarchical recurrence against an item-level simulator and its one-stage special case before using it for policy selection.

When a decision uses an estimated rate, retain sample counts and the sampling condition, not only the observed fraction. Integrate nonlinear decision costs over the stated uncertainty model; substituting the mean rate is a different calculation. Separate parameter uncertainty from outcome randomness and integration error. Missing counts require a conditional interface or clearly labeled scenarios, never invented observations; assembly defect-rate samples must match the stipulated input-quality condition.

Before reporting Monte Carlo standard errors for an unbounded cost, check the required moments under the uncertainty distribution: a finite expectation does not imply finite variance. State when the chosen integration method is inapplicable rather than claiming the mean itself is undefined. Compare plausible priors with the same sample counts and policy class when a small-sample decision depends on the prior; do not present a hypothetical informative prior as measured knowledge.

For nonlinear expected costs, inspect whether a closed set of moments can be propagated before using simulation. In an independent-rate assembly tree, retaining expected acquisition cost, good probability, inverse good probability, the cost/inverse-good joint moment and defect-weighted repair cost permits exact posterior integration for the declared recovery policy. Preserve within-subtree dependence rather than replacing every function by a function of mean parameters; justify any factorization using disjoint independent subtrees.

For numeric grouped regression, `scripts/grouped_regression.py` provides `evaluate_grouped(x, y, groups, families, ...)` with outer group-held-out predictions and training-only inner model selection. Install the optional `scripts/requirements-statistics.txt`. Specify the independent unit and numeric candidate features yourself; the helper cannot infer them. Compare a training-fold mean and a relevant simple predictor, and report group-weighted and row-weighted errors separately. A global response mean is valid in the usual descriptive R² denominator, but is not a deployable held-out mean predictor. Exchange group-constant dependent descriptors jointly using `permute_group_descriptors`; do not turn that predictive-dependence experiment into a component-level causal effect.

When a model choice depends on a small difference, `group_splits(groups, folds=5, seed=...)` can test alternate group assignments while keeping model candidates fixed. It balances group counts; the default without a seed balances row counts through GroupKFold. Report each partition's errors and reversals. Reusing the same groups across partitions gives sensitivity evidence, not independent experiments, confidence intervals or a reason to select the most flattering partition.

`polynomial_reference.py::predict_reference(train_x, train_y, query_x, degree=1|2, alpha=...)` independently fits standardized polynomial least squares/ridge using explicit monomials and NumPy SVD. Compare raw predictions before physical clipping, including constant and dependent columns; the intercept is not penalized. This reference verifies the fitted model conditional on specified hyperparameters, not their selection or a different estimator such as a random forest.

When a question asks about mixture proportions and total dose, distinguish these physical factors from raw columns: compare changing total mass at fixed ratio, and changing ratio at fixed total mass, while matching the other recorded conditions and measured temperatures. Two mass columns changing together need not represent two uncontrolled factors. Do not interpolate missing comparison temperatures silently or infer unconfounded causality from a matched observational series.
