# Contributing

For bug reports, include the command, Python version, a minimal synthetic input,
and the observed versus expected result. Do not upload team identities, credentials
or contest data without permission to redistribute it.

Keep a pull request focused on one observable behavior. Include a counterexample
for correctness fixes and run:

```bash
python3 -m unittest discover -s tests -v
python3 examples/production/run.py --output runs/contribution-demo
```

Use an empty output directory. Keep runtime helpers inside the Skill so a copied
Skill works without the repository. Preserve numerical evidence and clearly label
synthetic demonstrations, historical replays and unfamiliar-problem evaluations.
Never weaken validation to make an example pass.
