# Ultron engineering orientation

Use this as a navigation aid, not proof that every advertised feature works.
Read relevant tests alongside the implementation; do not ingest all reports at once.

| Concern | Starting points | Questions to answer |
|---|---|---|
| Startup/CLI | `main.py`, `ultron/__main__.py`, `ultron/app.py` | Which commands avoid GUI imports? Who owns shutdown? |
| Desktop frontend | `ultron/ui.py` | Which thread updates widgets? Does failure reach the user? |
| Tools/extensions | `ultron/core/action_loader.py`, `ultron/core/plugin_loader.py`, `ultron/actions/`, `ultron/plugins/` | What is discovered/imported? How are schemas, arguments and permissions checked? |
| Voice/wake | `ultron/core/wake_word.py`, `ultron/core/tts.py`, `ultron/core/stt.py`, app lifecycle | Who owns audio, model, queues and cancellation? |
| Provider/session | `ultron/core/gemini.py`, `ultron/core/llm_client.py`, app dispatch | What happens on reconnect, timeout and partial failure? |
| State/configuration | `ultron/paths.py`, `ultron/config.py`, `ultron/memory/`, `ultron/core/productivity_store.py` | Separate bundled resources from writable deployment state; inspect schema and migration risks. |
| Web frontend/backend | `ultron/dashboard/server.py`, `ultron/dashboard/static/`, `ultron/core/productivity_api.py` | Trace authentication, validation, API contracts and browser error states. |
| Privileged effects | `ultron/core/operation_policy.py`, `ultron/core/confirm.py`, relevant adapter | Can the effect bypass consent? What remains vulnerable to races or in-process access? |
| Packaging | `pyproject.toml`, `ultron/_version.py`, `scripts/version.py`, `docs/PROJECT_STRUCTURE.md` | Are resources included? Do installed paths work outside a checkout? |

## Task-driven discovery

1. Establish current Git status and environment without changing either.
2. Read README, this map, relevant code/tests and the applicable safety report.
3. Trace one real request: UI/provider input → dispatch → policy → effect → result → UI.
4. List reproduced facts separately from inferred risks and historical claims.
5. Define acceptance checks before coding; include failure, cancellation and cleanup.

`ULTRON_HOME` selects writable deployment state; see `ultron/paths.py`. Do not
repoint it at real user data for experiments. Use disposable synthetic locations.
The prompt/mesh/assets/dashboard are packaged resources, not writable state.

## Historical baseline, not today's test result

`reports/DEEP_DEBUG.md` records 1,196 passing tests, an existing Starlette warning,
425 remaining broad runtime/scripts lint findings, version 0.1.0, and missing native
prerequisites. Re-run relevant checks before quoting those numbers as current.
`CONTRIBUTING.md` mentions CI, but this checkout has no `.github/workflows` directory:
do not assert that PR checks are enforced without inspecting current configuration.

Keep onboarding reports short: architecture references, actual check outputs,
ranked risks, and the next bounded task. Understanding is iterative—not a claim
that a model has permanently absorbed the whole repository.
