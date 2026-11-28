# Contributing to Ultron AI

Thanks for considering a contribution. Ultron is a voice-first autonomous
desktop assistant (Gemini Live + PyQt6 HUD + ~50 workstation tools) targeting
Python 3.11–3.13 on Windows, macOS, and Linux.

## Ground rules

1. **Security first.** `ultron/actions/system_command.py` and `ultron/actions/self_evolution.py`
   are the most sensitive files in the repository — they execute code on the
   host. Any change to them requires explicit review and must keep the
   confirmation gate (`ultron/core/confirm.py`) and the audit logs intact. Never
   weaken the destructive-command blocklist or the hot-load consent flow.
2. **No secrets in the tree.** `config/api_keys.json`, `*.db`, `*.env`,
   `token*.json`, and `logs/` are gitignored. Do not commit API keys, tokens,
   or credentials. Use `config/api_keys.json.example` as the template.
3. **Tests run on every PR.** Add tests under `tests/` for new behavior. Run
   `python3 -m pytest` before pushing.
4. **Lint and type-check.** `ruff` (E/F/B/I rules) and `mypy` are configured
   in `pyproject.toml`. Run them on the files you touch (CI enforces
   `ruff check ultron/core/config.py tests/` and `mypy ultron/core/config.py tests/`). The
   rest of the codebase carries pre-existing lint debt that is being paid down
   incrementally — do not introduce *new* violations in files you modify.
5. **Every Python file must compile.** CI runs `python3 -m py_compile` on the
   whole tree. Do not commit files that fail to parse.

## Development setup

```bash
# Clone
git clone https://github.com/AbuZar-Ansarii/Ultron.git
cd Ultron

# Python 3.11–3.13 required
python --version

# Install runtime deps (OS-specific wheels are filtered by pip markers)
python -m pip install -r requirements.txt

# Install dev deps (lint, types, tests)
python -m pip install -r requirements-dev.txt

# Optional: Playwright browsers for browser automation
python -m playwright install chromium firefox

# Configure a Gemini API key (or set GEMINI_API_KEY in the environment)
cp config/api_keys.json.example config/api_keys.json
# edit config/api_keys.json and paste your key

# Launch
python -m ultron
```

## Submitting a change

1. Fork the repo and create a branch from `main`.
2. Make one coherent change per pull request.
3. Add or update tests in `tests/` for anything you change.
4. Run `python3 -m pytest`, `ruff check .`, and `mypy .`.
5. Open a pull request describing the what and why. Mention whether it touches
   security-sensitive code (`ultron/actions/system_command.py`,
   `ultron/actions/self_evolution.py`, `ultron/dashboard/server.py`, `ultron/core/confirm.py`).

## License & provenance

The README states the project is MIT-licensed. A `LICENSE` file now ships to
make that explicit. Because early development drew on a public
reverse-engineering brief (root `Prompt.txt` referencing Mark-LVI), confirm the
license is appropriate before any commercial distribution — see
`CRITIQUE.md` §M3/L1 for the provenance note.

## Code of conduct

Be respectful, assume good faith, and remember this is a tool that runs with
the user's full privileges on their own machine — caution is a feature, not a
bug.
