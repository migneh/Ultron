"""Self-update from GitHub releases.

Queries the GitHub releases API for migneh/Ultron, compares the latest release
tag against the local version, and if newer, applies the update.

Usage:
    python scripts/update.py [--check-only] [--force] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_OWNER = "migneh"
REPO_NAME = "Ultron"
GITHUB_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
VERSION_PATTERN = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class GitHubReleaseChecker:
    """Fetches and parses the latest GitHub release."""

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/vnd.github+json", "User-Agent": "Ultron-Updater"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def fetch_latest(self) -> dict[str, Any]:
        """Return dict with tag, version, assets, html_url."""
        req = urllib.request.Request(GITHUB_API, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise RuntimeError("No releases found on GitHub") from e
            if e.code == 403:
                raise RuntimeError("GitHub API rate limited or forbidden. Set GITHUB_TOKEN for higher limits.") from e
            raise RuntimeError(f"GitHub API error: {e.code} {e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error fetching release: {e}") from e

        tag = data.get("tag_name", "")
        version = self._normalize_version(tag)
        assets = data.get("assets", [])
        html_url = data.get("html_url", "")
        return {
            "tag": tag,
            "version": version,
            "assets": assets,
            "html_url": html_url,
            "published_at": data.get("published_at", ""),
        }

    @staticmethod
    def _normalize_version(tag: str) -> str:
        """Strip leading 'v' from tag like 'v0.1.1' -> '0.1.1'."""
        return tag.lstrip("v")


class VersionComparer:
    """Semantic version comparison."""

    @staticmethod
    def parse(version: str) -> tuple[int, int, int]:
        if not VERSION_PATTERN.fullmatch(version):
            raise ValueError(f"Invalid version format: {version}")
        return tuple(map(int, version.split(".")))

    @classmethod
    def compare(cls, local: str, remote: str) -> int:
        """Return -1 if local < remote, 0 if equal, 1 if local > remote."""
        lv = cls.parse(local)
        rv = cls.parse(remote)
        if lv < rv:
            return -1
        if lv > rv:
            return 1
        return 0


class InstallModeDetector:
    """Detects how Ultron is installed."""

    @staticmethod
    def detect() -> str:
        """Return 'editable', 'package', or 'source'."""
        try:
            # Check if running from source (not installed)
            import ultron
            ultron_path = Path(ultron.__file__).resolve().parent
            if (ultron_path / "_version.py").exists() and (ROOT / "scripts" / "version.py").exists():
                # Running from source checkout
                return "source"
        except ImportError:
            pass

        # Check pip show for editable install
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", "-f", "ultron-ai"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("Location:"):
                        location = Path(line.split(":", 1)[1].strip())
                        # If location is the repo root (or contains scripts/version.py), it's editable
                        if (location / "scripts" / "version.py").exists():
                            return "editable"
                        return "package"
        except Exception:
            pass

        # Default to source if we can find the repo structure
        if (ROOT / "scripts" / "version.py").exists():
            return "source"
        return "unknown"


class Updater:
    """Applies updates based on install mode."""

    def __init__(self, checker: GitHubReleaseChecker, comparer: VersionComparer, detector: InstallModeDetector):
        self.checker = checker
        self.comparer = comparer
        self.detector = detector

    def check_update(self) -> dict[str, Any]:
        """Check for updates without applying."""
        local_version = self._get_local_version()
        release = self.checker.fetch_latest()
        remote_version = release["version"]
        cmp = self.comparer.compare(local_version, remote_version)

        return {
            "local_version": local_version,
            "remote_version": remote_version,
            "update_available": cmp < 0,
            "comparison": cmp,
            "release": release,
        }

    def apply_update(self, force: bool = False) -> dict[str, Any]:
        """Apply the update if available."""
        check = self.check_update()

        if not check["update_available"] and not force:
            return {
                "success": True,
                "message": f"Already at latest version ({check['local_version']})",
                "local_version": check["local_version"],
                "remote_version": check["remote_version"],
                "updated": False,
            }

        mode = self.detector.detect()
        remote_version = check["remote_version"]

        try:
            if mode == "editable":
                result = self._update_editable(remote_version)
            elif mode == "package":
                result = self._update_package(remote_version)
            elif mode == "source":
                result = self._update_source(remote_version)
            else:
                # Fallback: try pip install from git
                result = self._update_via_git(remote_version)

            if result["success"]:
                result["updated"] = True
                result["local_version"] = remote_version
                result["remote_version"] = remote_version
            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "local_version": check["local_version"],
                "remote_version": remote_version,
                "updated": False,
            }

    def _get_local_version(self) -> str:
        """Read local version from ultron/_version.py."""
        version_file = ROOT / "ultron" / "_version.py"
        if not version_file.exists():
            raise RuntimeError("Cannot find ultron/_version.py")
        import ast
        tree = ast.parse(version_file.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__version__":
                        return ast.literal_eval(node.value)
        raise RuntimeError("Cannot parse __version__ from ultron/_version.py")

    def _run_cmd(self, cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True, timeout=120)

    def _update_editable(self, version: str) -> dict[str, Any]:
        """Update editable install: git pull + re-run setup."""
        # Git pull
        result = self._run_cmd(["git", "pull", "--ff-only"])
        if result.returncode != 0:
            return {"success": False, "error": f"git pull failed: {result.stderr.strip()}"}
        # Re-run setup_environment.py
        result = self._run_cmd([sys.executable, "scripts/setup_environment.py"])
        if result.returncode != 0:
            return {"success": False, "error": f"setup_environment.py failed: {result.stderr.strip()}"}
        return {"success": True, "message": f"Updated to {version} via git pull + setup"}

    def _update_package(self, version: str) -> dict[str, Any]:
        """Update regular package install: pip install --upgrade from git."""
        result = self._run_cmd([
            sys.executable, "-m", "pip", "install", "--upgrade",
            "git+https://github.com/migneh/Ultron.git"
        ])
        if result.returncode != 0:
            return {"success": False, "error": f"pip install failed: {result.stderr.strip()}"}
        return {"success": True, "message": f"Updated to {version} via pip"}

    def _update_source(self, version: str) -> dict[str, Any]:
        """Update source checkout: git pull + re-run setup (same as editable)."""
        return self._update_editable(version)

    def _update_via_git(self, version: str) -> dict[str, Any]:
        """Fallback: try git pull + setup."""
        return self._update_editable(version)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Only check for updates, do not apply")
    parser.add_argument("--force", action="store_true", help="Force update even if up to date")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args(argv)

    try:
        checker = GitHubReleaseChecker()
        comparer = VersionComparer()
        detector = InstallModeDetector()
        updater = Updater(checker, comparer, detector)

        if args.check_only:
            result = updater.check_update()
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                if result["update_available"]:
                    print(f"Update available: {result['local_version']} -> {result['remote_version']}")
                    print(f"Release: {result['release']['html_url']}")
                else:
                    print(f"Up to date: {result['local_version']}")
            return 2 if result["update_available"] else 0

        result = updater.apply_update(force=args.force)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["success"]:
                if result.get("updated"):
                    print(f"Successfully updated to {result['local_version']}")
                else:
                    print(result.get("message", "Up to date"))
            else:
                print(f"Update failed: {result.get('error', 'unknown error')}")
                return 1
        return 0

    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}, indent=2))
        else:
            print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())