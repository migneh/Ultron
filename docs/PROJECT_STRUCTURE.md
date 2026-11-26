# Runtime package structure and migration

## Layout contract

The Python runtime now lives in the single `ultron` namespace:

| Area | Responsibility |
|---|---|
| `ultron/__main__.py` | Lightweight CLI; help/wake config don't import desktop/audio |
| `ultron/app.py` | Former root main.py: application lifecycle and dispatcher |
| `ultron/ui.py` | Former root ui.py: Qt HUD/settings |
| `ultron/actions/` | Builtin action modules and tool declarations |
| `ultron/core/` | Policies, adapters, audio, jobs, services and packaged prompt/mesh |
| `ultron/memory/` | Configuration/memory Python modules, not user database storage |
| `ultron/dashboard/` | Phone server and packaged static resources |
| `ultron/plugins/` | Trusted extension modules/template; execution trust unchanged |
| `ultron/assets/` | Avatar images and original icon |
| `ultron/paths.py` | Shared package/assets/deployment path definitions |
| `config/`, `memory/`, `logs/` | Existing checkout configuration/state/log locations |
| `scripts/` | Bootstrap and reproducible static audit utilities |
| `tests/` | Contract/unit/fake-adapter regressions |
| `docs/` | Project guidance/notes; root README/CONTRIBUTING/LICENSE retained |
| `reports/` | Historical engineering records and remaining acceptance gates |

No repository root, Git directory, branch, credentials or user files were deleted.
The root `main.py` is a compatibility launcher, not a duplicate application module.
Code imports now use `ultron.core`, `ultron.actions`, `ultron.memory`,
`ultron.dashboard`, `ultron.plugins`, `ultron.ui` and `ultron.config`.
Dynamic action/plugin loaders use the same canonical namespace to avoid duplicate
policy/confirmation/registry singleton modules. No top-level compatibility module
aliases are supplied: update external scripts/plugins importing the former names.
Do not execute files inside the package directly; use module entry points.

## Setup / launch

```bash
python -m pip install -r requirements.txt
python -m pip install --no-deps -e .
python -m ultron
# or, from a checkout:
python main.py
```

Alternatively `python scripts/setup_environment.py` runs the existing opt-in
dependency/browser bootstrap plus editable package install. The old root setup.py
was a bootstrap script, not packaging metadata; its new location avoids collision
with setuptools builds. Use pyproject-based packaging, not `python setup.py`.
Runtime optional/native dependencies remain environment-dependent; wheel installation
alone does not install every desktop/audio/provider dependency. Requirements sets
remain at the repository root. `ultron --help` and `ultron wake-config` are available
after installation without starting services.

Packaged resources include the prompt, mesh, dashboard static files and avatar/icon
assets; mutable credentials/state/logs are deliberately excluded from wheels. Source
checkout config and memory paths stay in their original root directories. A normal
installed wheel defaults to `~/.ultron` for deployment state, rather than writing
into site-packages. `ULTRON_HOME=/path/to/deployment` overrides the deployment root
for normal Python runs; set it before launch. Legacy per-module frozen executable
branches remain and need native frozen-build validation. This is not a universal
storage-path rewrite: some older subsystems intentionally use `~/.ultron` or other
native paths, and source/resource packaging does not sandbox them. No directory
creation happens merely by importing `ultron.paths`.

The original mutable `memory/workspace_presets.json` remains in the checkout, not
in the code package. Installed deployments should provision desired presets in
`ULTRON_HOME/memory/`; loaders retain their existing defaults when absent. Operator
credentials belong in `ULTRON_HOME/config/api_keys.json`, never in package assets.

## Integrations / compatibility

- Existing source imports: add the `ultron.` prefix; root ui.py is now ultron/ui.py.
- Builtin action/plugin source directories moved under ultron; update trusted
  extension installations and tooling paths. Existing plugins are still trusted
  code, not isolated by this namespace change.
- Newly generated shortcut/autostart commands use `python -m ultron`, not a
  checkout-relative app file. Their Python environment must have this package
  installed. Recreate existing shortcuts/autostart entries after migrating.
- New game-update schedules launch `-m ultron.actions.game_updater`; old scheduled
  jobs pointing at the removed actions path must be recreated manually. No real
  scheduler/shortcut/autostart changes were made or native-tested.
- Reminder runner stays a stdlib standalone file at its new packaged location;
  old registered jobs may still point at the former path. Reconcile/recreate
  native jobs manually; no automatic replay or silent migration is claimed.
- Historical reports retain original path names as evidence of the work at that
  time. Interpret old `core/`, `actions/`, `dashboard/`, `plugins/`, `ui.py`, and
  application `main.py` references through this map. The static inventory has been
  regenerated against the current tree and remains leads, not coverage proof.
- Root engineering/project notes moved into docs. Reports and acceptance tracking
  remain in reports; no audit history has been represented as newly verified.

## Validation / remaining work

47 new tests cover wake configuration and package/path/import contracts. Existing
970 tests migrated to canonical imports and relocated source inspection paths.
Full suite: 1017 passed, one existing Starlette warning. New wake/path/config/CLI,
all tests and audit script pass targeted Ruff. Repository-wide lint is NOT clean;
legacy modules retain hundreds of pre-existing style/unused-import issues. Import
sorting was updated across relocated source. One exposed optional-import ordering
problem in dashboard was corrected so available FastAPI symbols aren't lost just
because uvicorn is absent.

Wheel built successfully, installed into a temporary isolated target, and CLI/help,
config write and packaged-resource/secret-exclusion checks passed from `/tmp`, not
the checkout. No credentials were used, and temporary configuration was separate
from repository settings. Compilation and diff checks pass. GUI startup, microphone,
native ONNX inference, frozen builds, native shortcuts/autostart/schedulers and live
providers remain unverified. Full test success is not whole-assistant certification.
Existing privileged-path TODOs are unchanged in priority; organization does not
complete remaining file-write/delete/download or global permission migrations.
No commit/push or branch switch performed.
