"""Package/path contracts without starting desktop or native services."""
import ast
import json
import os
import subprocess
import sys
from pathlib import Path

from ultron import paths
from ultron.core.action_loader import discover_actions
from ultron.memory import config_manager, memory_manager

ROOT = Path(__file__).resolve().parents[1]


def test_existing_config_and_state_paths_preserved():
    assert config_manager.CONFIG_FILE == paths.PROJECT_ROOT / "config" / "api_keys.json"
    assert memory_manager.MEMORY_PATH == paths.PROJECT_ROOT / "memory" / "long_term.json"
    assert paths.PACKAGE_ROOT == ROOT / "ultron"


def test_packaged_resources_present():
    assert (paths.PACKAGE_ROOT / "core" / "prompt.txt").is_file()
    assert (paths.PACKAGE_ROOT / "core" / "face_model.obj").is_file()
    assert (paths.ASSETS_DIR / "ultron_avatar.png").is_file()
    assert (paths.PACKAGE_ROOT / "dashboard" / "static" / "app.html").is_file()


def test_discovery_uses_single_canonical_namespace(tmp_path):
    name = "layout_contract_fake"
    (tmp_path / (name + ".py")).write_text(
        'from ultron.core import operation_policy\n'
        'def run(parameters): return "fake"\n'
        'TOOL = {"name": "layout_fake", "description": "fake", "handler": run}\n')
    try:
        registry = discover_actions(tmp_path, logger=lambda _: None)
        assert registry.names() == {"layout_fake"}
        assert "ultron.actions." + name in sys.modules
        assert "actions." + name not in sys.modules
    finally:
        sys.modules.pop("ultron.actions." + name, None)


def test_no_legacy_top_level_runtime_imports():
    legacy = {"actions", "core", "memory", "dashboard", "plugins", "ui", "config"}
    failures = []
    for source in (ROOT / "ultron").rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[0] in legacy:
                failures.append(str(source))
            if isinstance(node, ast.Import) and any(name.name.split(".")[0] in legacy for name in node.names):
                failures.append(str(source))
    assert not failures


def test_home_override_independent_of_working_directory(tmp_path):
    home = tmp_path / "deployment"
    env = {**os.environ, "ULTRON_HOME": str(home), "PYTHONPATH": str(ROOT)}
    result = subprocess.run([sys.executable, "-c", 'import json; from ultron.paths import PROJECT_ROOT; print(json.dumps(str(PROJECT_ROOT)))'],
                            cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == str(home)
    assert not home.exists()  # resolving paths never creates deployment files


def test_legacy_launcher_help_does_not_start_desktop(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "main.py"), "--help"],
                            cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "wake-config" in result.stdout


def test_shortcut_and_new_schedule_sources_use_module_launches():
    ui = (ROOT / "ultron" / "ui.py").read_text()
    assert '{script}' not in ui and 'PROJECT_ROOT / "main.py"' not in ui
    assert "-m ultron" in ui
    schedule = (ROOT / "ultron" / "actions" / "game_updater.py").read_text()
    assert "-m ultron.actions.game_updater" in schedule
