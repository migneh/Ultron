---
name: ultron-check
description: Verify an Ultron change with targeted regressions, static checks and an honest native/provider acceptance report.
disable-model-invocation: true
---

# Verify an Ultron change

This is a verification procedure, not authorization to edit, install dependencies,
start services, operate devices, commit or contact providers.

1. Read Git status/diff and identify intended changes; preserve unrelated work.
2. Identify the affected UI/API/dispatch/policy/storage/lifecycle paths. Read relevant
   tests. For bug fixes, demonstrate the regression fails against the old behavior
   when practical, without resetting or discarding the working tree.
3. Select the existing interpreter. If unavailable or missing dependencies, report
   the precise blocker and ask before installation. Do not silently skip checks.
4. Run targeted tests, then the full suite when feasible:
   - `python -m pytest <relevant-test-paths> -q`
   - `python -m pytest -q`
5. Run configured Ruff on changed Python files; separate pre-existing violations:
   - `python -m ruff check <changed-python-paths>`
   - `python -m ruff check ultron scripts --select F821,F822,F823,B023`
   - `python -m compileall -q ultron tests scripts main.py`
   - `python -m pip check`
   - `python scripts/version.py --check`
   - `git diff --check`
6. For prerequisite questions use `python -m ultron doctor --profile desktop --json`.
   Exit 1 may correctly mean missing prerequisites; metadata presence is not runtime
   verification. Use workspace/test profiles only when relevant.
7. For packaging changes, build in disposable output locations and inspect wheel
   metadata/resources; keep artifacts out of version control. Request approval if
   build isolation requires network installs.
8. For desktop/dashboard changes, specify an actual visual/manual check. Only run it
   in an approved environment with synthetic state; avoid live credentials/audio.
   Report missing native/browser tooling as an unverified gate, not a pass.
9. Review the diff against acceptance criteria. A separate reviewer/subagent may
   inspect correctness/security, but its opinion is not execution evidence.
10. Return: changed behavior; root cause; exact checks and results; skipped checks
    and reasons; remaining risks. Do not commit or publish unless explicitly asked.
