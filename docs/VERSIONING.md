# Application versions and release preparation

## Single source

The application version lives only in `ultron/_version.py` as a stable
`MAJOR.MINOR.PATCH` string. `ultron.__version__` re-exports it and setuptools derives
wheel/sdist metadata through the dynamic `pyproject.toml` attribute. Do not copy
version literals into other runtime modules or edit generated wheel metadata.
Current baseline remains **0.1.0**; adding this system did not publish or bump it.

```bash
python -m ultron --version
python -m ultron version
python -m ultron version --json
python main.py --version
# Installed console entry point:
ultron --version
```

These commands do not import desktop/audio services, start providers or invoke
Git. JSON contains `application` and `version`, not a claim about which uncommitted
patches, Git commit, deployment or native capabilities are present. A dirty checkout
can share the release version while containing unreleased changes. An installed
wheel's version reflects the source at build time; rebuild/reinstall after editing.

## Policy

- **PATCH**: compatible bug/security fixes within the documented capability contract.
- **MINOR**: backward-compatible features; patch resets to zero.
- **MAJOR**: intentionally incompatible public behavior, import/config/CLI contract
  changes; minor/patch reset to zero. During 0.x development, document compatibility
  restrictions prominently and review the appropriate release number explicitly.
- This initial helper supports stable numeric triples only. Prerelease/build labels
  are deliberately rejected; expand the policy/tool/tests before using them.
- Version numbers are not safety certifications or a universal compatibility promise.
  Keep remaining acceptance gates and disabled features in release notes.

This is **application release versioning**, not automatic file backups, an undo
journal, config/database schema migration, plugin ABI negotiation, self-update or
rollback. Those need their own lifecycle/security designs. No auto-update, remote
version check, telemetry or installer action is introduced.

## Preview-first workflow

```bash
python scripts/version.py --check
python scripts/version.py --bump patch        # preview only
python scripts/version.py --bump minor        # preview only
python scripts/version.py --bump major        # preview only
# Only after manually reviewing notes and acceptance gates:
python scripts/version.py --bump patch --write
```

The check verifies one stable literal, dynamic package metadata and one Unreleased
section with the current version as the newest versioned changelog section.
The explicit write updates only `ultron/_version.py` and `CHANGELOG.md`, moving
current Unreleased notes under the next version and opening a fresh Unreleased
section. No Git commands, commits, tags, push, GitHub release or package publication
occur. The assistant ran **preview/check only on this checkout**, not `--write`.
Tests exercise writes in temporary fake projects. The existing version is unchanged.

Both edits use separate temporary-file/atomic replacements, not a two-file
transaction. A crash may leave them inconsistent; `--check` detects a newer
changelog heading paired with an older source version. Reconcile manually; no
blind automatic retry/rollback. This is trusted developer tooling with a fixed
checkout root, not an agent-facing arbitrary file writer. Avoid concurrent editors
or running it against untrusted symlinked project metadata. Tempfile permissions
may replace file metadata; no permission-preserving or OS sandbox guarantee.

## Before an actual release

1. Review `CHANGELOG.md`, disabled behavior and `reports/PRIVILEGED_SINK_TODO.md`.
2. Choose the version deliberately; the helper cannot determine compatibility.
3. Run full tests, version check, targeted lint and packaging/resource checks.
4. Validate required native GUI/microphone/models/provider/device behavior on
   supported hosts. Fake tests and wheels do not establish native certification.
5. Build with `python -m pip wheel --no-deps --no-build-isolation .` in an environment
   with setuptools/wheel available; inspect the resulting metadata and contents.
6. Commit/tag/push/publish only through a separate authorized release process.

No CI release workflow or remote publishing credentials were added. Build artifacts
remain ignored; no wheels/datasets are added to Git. `CHANGELOG.md` distinguishes
Unreleased work from the existing version baseline rather than asserting that the
accumulated branch changes are already released.
