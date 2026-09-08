---
name: cumcm-reliable-paper
description: Solve and review CUMCM/国赛 modeling tasks with frozen inputs, executable verification and traceable paper claims. Use for contest preparation, attachment audits, modeling-to-paper workflows and reproducibility checks.
---

# CUMCM Reliable Paper

Answer the supplied problem and current official rules. Use historical papers for writing and modeling ideas only. Choose the simplest adequate model; support stronger claims with stronger evidence.

## Run the workflow

Run the CLI relative to this Skill directory:

```bash
python3 scripts/cumcm_agent.py init --problem /path/problem.docx --attachment /path/data.xlsx --output /path/run --title "题目"
python3 scripts/cumcm_agent.py status /path/run
```

Initialize before modeling. Read the original statement, including diagrams, then inspect `source_audit.json`. CSV/XLSX audits scan every stored row; DOCX extraction covers paragraph text only. A successful scan establishes readability, not semantic understanding or model validity.

Use the current stage to select the work:

| Stage | Required work |
| --- | --- |
| READING | Resolve each requested output, input, constraint, unit and ambiguity in the problem contract. Interpret full-scan findings. |
| MODEL_DRAFT | Record assumptions, a baseline, the reason for any upgrade, and an independent verification method. |
| CODE_RUN | Execute the model and retain machine-readable results and failure cases. |
| P0_PASS | Recompute units, identities and constraints from the delivered solution. |
| P1_PASS | Establish independent agreement and investigate sensitivity and counterexamples. |
| PAPER_LINKED | Link paper claims to verified results; inspect the rendered submission. |
| VERIFIED | Preserve the sealed package; report the scope of verification. |

After completing a stage, use `validate RUN` then `advance RUN`; from `PAPER_LINKED`, use `seal RUN`. Use `inspect RUN` to regenerate intake only at `READING`. Earlier preview-only runs need a new full audit; already advanced runs need a new version.

Stage hashes detect changes to recorded content. When evidence warrants a revised interpretation or model, preserve the earlier run, state the reason and create a new version. Do not confuse consistency with refusing to correct a mistake.

## Evidence that matters

- Read [artifact-contracts.md](references/artifact-contracts.md) when editing ledgers, interpreting intake statistics or recording approvals. Keep schema details there.
- Read [problem-routing.md](references/problem-routing.md) when choosing methods and checks appropriate to the task.
- Read [hard-gates.md](references/hard-gates.md) when assessing numerical and methodological evidence.
- Read [paper-patterns.md](references/paper-patterns.md) when drafting. Use [paper-outline.md](assets/paper-outline.md) as an adaptable starting point.
- Read [competition-operations.md](references/competition-operations.md) for time management.

Prepare concrete review material before requesting a recorded human sign-off; reuse applicable explicit approval already given in the conversation. `signoffs RUN` shows the content hash to bind. Never invent a reviewer or approval. The ledger checks declarations and content binding; it does not authenticate human identity.

The engine checks recorded fields, hashes and links. Different method names do not prove numerical independence; an excerpt does not prove a claim; a sealed package does not prove algorithm correctness. Perform the actual calculation and semantic review before recording a pass. Do not describe workflow tests or intake benchmarks as a complete unfamiliar-problem trial.

Keep claims about historical research within the documented evidence scope in the project manifest. Patterns are observations, not hidden judge rules or an award guarantee.
