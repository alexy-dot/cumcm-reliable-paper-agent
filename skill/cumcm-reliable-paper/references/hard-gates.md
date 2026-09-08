# Hard gates

Apply P0 before P1. Stop the affected question on any P0 failure. Preserve failed evidence and either repair the pipeline or narrow the claim.

## P0 correctness gates

1. **Problem contract**: answer the exact output, objective, constraints, range, and units in the official wording.
2. **Source integrity**: freeze official files, hashes, sheets, columns, types, missingness, duplicates, and units.
3. **Dimensions and coordinates**: verify unit conversions, angle conventions, signs, frames, and conservation identities.
4. **Arithmetic identities**: verify totals, partitions, MSE/RMSE, precision/recall/F1, weighted means, and table-text agreement.
5. **Feasibility**: recompute every hard constraint from the final solution and report residual/slack.
6. **Identifiability**: enumerate or perturb small problems; report tied optima and avoid false precision.
7. **Formula-code-config agreement**: compare key formulas pointwise and freeze actual parameters, seeds, and bounds.
8. **Information boundary**: prevent future data and same-entity/time/space leakage.
9. **Train/validation/test isolation**: fit, select, and report on separated data; never tune on final test labels.
10. **Shape and schema**: test mask use, padding invariance, maximum sizes, labels, and output dimensions.
11. **Termination and one-command execution**: lock seeds and stopping conditions; require a clean non-interactive run.
12. **Headline provenance**: generate abstract, conclusion, and main-table numbers from one machine result chain.

## P1 evidence gates

Use `PASS`, `WARN`, or `FAIL`.

- Require a strong simple baseline and a genuinely different independent reproduction.
- Match residual and holdout checks to the model type.
- test parameter identifiability, degeneracy, boundary hits, and free scaling.
- Vary decisive assumptions, thresholds, preprocessing, and random seeds; report conclusion flips.
- Search for counterexamples and competing explanations.
- Respect observational units, repeated measurements, clustering, and dependence.
- Verify external formulas, constants, datasets, and citations against authoritative sources.

A P1 warning may remain only with explicit allowed language. Without evidence, replace “optimal”, “accurate”, “robust”, “significant”, “mechanism”, or “generalizable” with a scoped statement such as “under the current data and assumptions”.

## P2 reviewer usability

Optimize only after related P0 checks pass:

- Write the abstract question by question: task, method, result, verification/boundary.
- Put direct answers and units before procedural detail.
- Use each figure or table for one stated claim.
- Reuse verified modules across questions and state inheritance explicitly.
- Write limitations with trigger, impact, and remedy.
