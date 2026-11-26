"""Version/release preparation with temporary project files; never invokes Git."""
import json
import sys
import tomllib

import pytest

from scripts import version as release
from ultron import __version__
from ultron.__main__ import main
from ultron._version import __version__ as source_version


@pytest.fixture
def project(tmp_path):
    (tmp_path / "ultron").mkdir()
    (tmp_path / "ultron" / "_version.py").write_text('__version__ = "1.2.3"\n')
    (tmp_path / "pyproject.toml").write_text('[project]\ndynamic = ["version"]\n[tool.setuptools.dynamic]\nversion = {attr = "ultron._version.__version__"}\n')
    (tmp_path / "CHANGELOG.md").write_text('# Changelog\n\n## [Unreleased]\n\n- Test notes.\n\n## [1.2.3]\n\n- Baseline.\n')
    return tmp_path


def test_single_source_and_packaging_consistency():
    assert __version__ == source_version == release.check(release.ROOT)
    metadata = tomllib.loads((release.ROOT / "pyproject.toml").read_text())
    assert "version" not in metadata["project"]


def test_cli_flag_without_native_imports(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == "Ultron " + __version__
    assert "ultron.app" not in sys.modules and "ultron.ui" not in sys.modules


def test_cli_machine_readable_version(capsys):
    main(["version", "--json"])
    assert json.loads(capsys.readouterr().out) == {"application": "ultron-ai", "version": __version__}


@pytest.mark.parametrize("part,expected", [("patch", "1.2.4"), ("minor", "1.3.0"), ("major", "2.0.0")])
def test_bump_preview_does_not_write(project, part, expected, capsys):
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    release.main(["--bump", part], root=project)
    assert expected in capsys.readouterr().out
    assert all(p.read_bytes() == content for p, content in before.items())


def test_explicit_write_only_versions_and_changelog(project):
    (project / "keep").write_text("untouched")
    release.main(["--bump", "minor", "--write"], root=project)
    assert release.check(project) == "1.3.0"
    changelog = (project / "CHANGELOG.md").read_text()
    assert changelog.index("## [Unreleased]") < changelog.index("## [1.3.0]") < changelog.index("## [1.2.3]")
    assert "Test notes" in changelog and (project / "keep").read_text() == "untouched"
    assert not list(project.rglob(".version-*"))


@pytest.mark.parametrize("bad", ["01.2.3", "1.2", "v1.2.3", "1.2.3rc1", "1.2.3-dev", "1.2.3+build", "-1.2.3"])
def test_invalid_or_unsupported_release_version_rejected(bad):
    with pytest.raises(ValueError):
        release.next_version(bad, "patch")


def test_mismatched_packaging_refused(project):
    (project / "pyproject.toml").write_text('[project]\nversion = "8.0.0"\n')
    with pytest.raises(ValueError):
        release.check(project)


def test_interrupted_multi_file_write_detected(project):
    path = project / "CHANGELOG.md"
    path.write_text(path.read_text().replace("## [Unreleased]", "## [Unreleased]\n\n## [1.2.4]"))
    with pytest.raises(ValueError):
        release.check(project)


@pytest.mark.parametrize("args", [["--write"], ["--check", "--bump", "patch"], ["--check", "--write"]])
def test_invalid_flags_no_writes(project, args):
    before = (project / "ultron" / "_version.py").read_bytes()
    with pytest.raises(SystemExit):
        release.main(args, root=project)
    assert (project / "ultron" / "_version.py").read_bytes() == before


def test_current_version_is_valid_stable_release_identifier():
    assert release.PATTERN.fullmatch(__version__)
