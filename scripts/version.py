"""Developer release preparation. Preview by default; never runs Git or publishes.

python scripts/version.py --check
python scripts/version.py --bump patch              # preview only
python scripts/version.py --bump minor --write      # edit version/changelog only
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")


def current(root):
    tree = ast.parse((root / "ultron" / "_version.py").read_text(encoding="utf-8"))
    values = [ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets)]
    if len(values) != 1 or not isinstance(values[0], str) or not PATTERN.fullmatch(values[0]):
        raise ValueError("Expected one stable MAJOR.MINOR.PATCH literal in ultron/_version.py")
    return values[0]


def check(root):
    value = current(root)
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    if ("version" in metadata["project"] or "version" not in metadata["project"].get("dynamic", [])
            or metadata["tool"]["setuptools"]["dynamic"]["version"].get("attr") != "ultron._version.__version__"):
        raise ValueError("Packaging must derive version only from ultron._version.__version__")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## \[([^\]]+)\]", changelog, re.MULTILINE)
    releases = [h for h in headings if h != "Unreleased"]
    if changelog.count("## [Unreleased]") != 1 or not releases or releases[0] != value:
        raise ValueError("Changelog needs one Unreleased section and the current version entry")
    return value


def next_version(value, part):
    if not PATTERN.fullmatch(value):
        raise ValueError("Only stable MAJOR.MINOR.PATCH releases supported")
    major, minor, patch = map(int, value.split("."))
    return {"major": f"{major + 1}.0.0", "minor": f"{major}.{minor + 1}.0",
            "patch": f"{major}.{minor}.{patch + 1}"}[part]


def _replace(path, text):
    fd, raw = tempfile.mkstemp(prefix=".version-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(raw, path)
    finally:
        Path(raw).unlink(missing_ok=True)


def main(argv=None, *, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate version source and changelog")
    parser.add_argument("--bump", choices=("major", "minor", "patch"))
    parser.add_argument("--write", action="store_true", help="explicitly edit version/changelog; no Git operations")
    args = parser.parse_args(argv)
    if (args.check and (args.bump or args.write)) or (args.write and not args.bump):
        parser.error("Use --check alone, or --bump PART [--write]")
    try:
        old = check(root)
        if not args.bump:
            print(f"Version configuration OK: {old}")
            return
        new = next_version(old, args.bump)
        changelog_path = root / "CHANGELOG.md"
        changelog = changelog_path.read_text(encoding="utf-8")
        if "## [" + new + "]" in changelog:
            raise ValueError("Target version already in changelog")
        # Keep future Unreleased section, move current notes under new version.
        updated = changelog.replace("## [Unreleased]", f"## [Unreleased]\n\n### Pending\n\n- No changes recorded yet.\n\n## [{new}]", 1)
        print(f"{'WRITE' if args.write else 'PREVIEW'}: {old} -> {new}; ultron/_version.py and CHANGELOG.md only. No commit/tag/push/release.")
        if args.write:
            # Two separate atomic file replacements, not a multi-file transaction.
            # A crash can require manual reconciliation; --check detects mismatch.
            _replace(changelog_path, updated)
            _replace(root / "ultron" / "_version.py", '"""Application release version (single source)."""\n\n__version__ = "' + new + '"\n')
    except (OSError, ValueError, KeyError, SyntaxError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
