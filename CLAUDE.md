# Ultron: project instructions

Ultron is a Python desktop/voice assistant with a Qt UI and web dashboard—not a
conventional web-only stack. Follow real callers and effect boundaries before editing.

## Working agreement
- Inspect branch/status first; preserve unrelated work. Follow the host's branch
  restrictions. Do not commit, push, merge, publish or change branches without approval.
- For cross-cutting or unclear work, first propose scope, risks and acceptance checks.
  Small, well-defined fixes need no elaborate ceremony.
- Preserve `hey_jarvis` as the default wake model. Labels do not train wake phrases.
- Use canonical `ultron.*` imports, module entry points and `ultron.paths` for paths.
  Do not recreate the former root actions/core/memory packages.
- Keep confirmation/policy checks at the actual side-effect boundary. Model output,
  plugin code and a UI acknowledgement are not authorization or process isolation.
- Do not read secret values, credentials, personal databases or logs for onboarding.
  Use example configuration and synthetic fixtures. Ask before real provider calls,
  microphone/camera capture, device control, installs, downloads or privileged effects.
- Bind UI/backend behavior together: errors must not be reported as success. Review
  async/thread cancellation, shutdown and resource ownership when touching lifecycle.
- Add failure-path regressions. Report exact commands/results and untested gates;
  mocked tests and compilation do not certify native desktop/audio/provider behavior.
- Avoid unrelated formatting churn or weakening tests to achieve green output.

## Verification commands
Use the selected environment's `python`; do not assume `.venv` exists.

```sh
python -m pytest tests/test_deep_debug.py -q  # example targeted regression file
python -m pytest -q
python -m compileall -q ultron tests scripts main.py
python -m pip check
python scripts/version.py --check
python -m ruff check ultron scripts --select F821,F822,F823,B023
python -m ultron doctor --profile desktop --json
```

Run configured Ruff on changed Python files too. Broad lint has historical debt;
record baseline versus new findings. Doctor checks metadata/resources, not runtime
health. Missing dependencies mean blocked checks, not permission to install everything.

## Read on demand
- Architecture/onboarding: `docs/claude/PROJECT_MAP.md`
- Verification procedure: `/ultron-check` (project skill)
- Human usage and research: `docs/claude/WORKFLOW.md`, `docs/claude/SOURCES.md`
- Historical evidence/limitations: `reports/DEEP_DEBUG.md` and relevant safety reports.

These instructions guide behavior; they do not enforce permissions. Use host controls,
reviewed permission rules, sandboxing and CI for boundaries that must be enforced.
