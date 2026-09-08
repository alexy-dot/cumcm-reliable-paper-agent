# Problem routing and minimum evidence

Route only after completing the problem contract. A problem may use multiple routes; preserve the data and uncertainty passed between them.

| Task structure | Typical chain | Minimum independent evidence |
|---|---|---|
| Mechanism and dynamics | conservation/geometry -> state equations -> parameter identification -> numerical solution -> constrained decision | dimensions, conservation, boundary conditions, convergence, known or extreme case |
| Prediction to decision | data audit -> interpretable baseline -> entity/time split -> uncertainty -> constrained decision | leakage-free holdout, simple baseline, residuals/calibration, error propagation into decisions |
| Probability and risk | random variables -> event decomposition -> integration/simulation -> risk rule -> decision | normalization, exact small case, analytic/simulation agreement, confidence interval and convergence |
| Recognition and signals | acquisition audit -> denoise -> features/model -> isolated validation -> failure analysis | synthetic truth or labeled holdout, confusion/error structure, parameter sensitivity, identifiable scope |
| Network, scheduling, planning | graph/state -> capacity/time/resource constraints -> baseline -> exact/heuristic solve | per-constraint residuals, small-instance enumeration/bound, multi-seed stability, infeasibility handling |
| Monitoring and control | metric reconciliation -> trend/season/change -> forecast/state estimate -> policy | conservation/accounting reconciliation, rolling holdout, counterfactual or baseline, operational constraints |

## Selection rules

1. Start with a transparent executable baseline.
2. Upgrade only for an observed limitation, not because a method name appears advanced.
3. Freeze the prediction time and available-information boundary before feature engineering.
4. Separate model fit, parameter identifiability, predictive validity, and decision feasibility.
5. Prefer a smaller validated solution over a complex unverified solution under contest time pressure.
6. Propagate uncertainty when an upstream estimate enters a downstream optimization.
