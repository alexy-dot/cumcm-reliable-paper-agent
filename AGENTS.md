# CUMCM Reliable Paper Agent development rules

## Authority

- Treat frozen problem files and current official competition rules as higher authority than historical papers, prompts, or model memory.
- Preserve the evidence boundary: 20 stratified primary full papers plus 2 targeted supplements, 22 full papers and 1,158 pages total; do not claim all 45 papers were fully reviewed.
- Never promise a national award or present observable paper commonalities as hidden judge rules.

## Implementation

- Keep the MVP standard-library-only unless a concrete feature requires another dependency.
- Keep the CLI and workflow engine inside the Skill so an installed copy remains functional.
- Use atomic JSON writes and relative paths inside run artifacts.
- Treat malformed or unsupported source structures as explicit gate failures, not implicit success or uncaught crashes.
- Never fabricate or self-approve a human sign-off.
- Do not weaken a gate merely to make a benchmark pass.
- Do not silently mutate a sealed run; create a new version after invalidating affected downstream stages.

## Verification

- Run `python3 -m unittest discover -s tests -v` after code changes.
- Run the Skill Creator `quick_validate.py` after changing `SKILL.md` or `agents/openai.yaml`.
- Test both acceptance and rejection paths, including source mutation, method non-independence, unverified claims, and manifest tampering.
- Treat multi-agent agreement as discussion, not independent numerical evidence.
