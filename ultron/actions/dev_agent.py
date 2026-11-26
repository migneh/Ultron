"""Review-only project planning, not an automatic build/install/run agent."""
from __future__ import annotations

from ultron.core import productivity_store as store
from ultron.core import source_drafts

DISABLED = "Automatic project building/execution/dependency installation is disabled. Use dev_agent for a review-only project plan or code_helper for source drafts. No isolated runtime is configured."


def _build_project(*args, **kwargs) -> str:
    return DISABLED


def _run_project(*args, **kwargs) -> str:
    return DISABLED


def _install_dependencies(*args, **kwargs) -> str:
    return DISABLED


def _try_auto_install(*args, **kwargs) -> bool:
    return False


def _open_vscode(*args, **kwargs) -> bool:
    return False


def _write_file(*args, **kwargs):
    raise PermissionError("Direct generated-project writes disabled")


def _fix_files(*args, **kwargs):
    raise PermissionError("Automatic project fix/write loops disabled")


def dev_agent(parameters: dict, response=None, player=None, session_memory=None, speak=None) -> str:
    """Generate one bounded plan in memory, then request exact-content draft consent."""
    if not isinstance(parameters, dict):
        return "Invalid project planning parameters."
    if parameters.get("action", "plan") not in {"plan", "draft"}:
        return DISABLED
    try:
        description = store.text(parameters.get("description"), "description", 8000)
        language = store.text(parameters.get("language", "python"), "language", 60)
        name = store.text(parameters.get("project_name", "proposed_project"), "project_name", 120)
        from ultron.actions.code_helper import _generate
        result = _generate(
            f"Create a review-only project plan for {name}, language {language}.\n"
            "Describe proposed files, dependencies, run commands, risks and a manual validation plan. "
            "All code/commands/dependencies are inert suggestions: do not claim any files were "
            "written, packages installed, commands executed or tests passed. No implementation "
            f"or automatic effects will follow this plan.\nUser request:\n{description}"
        )
        return source_drafts.request(result, "Save review-only project plan")
    except Exception:
        return "Project plan could not be completed. Check input/model availability. No project files, installs or execution performed."


TOOL = {
    "name": "dev_agent",
    "description": "Review-only project planner. Generates a bounded plan and requests approval to save inert .txt outside project/auto-discovery directories. Does NOT build projects, install packages, open editors, run code or perform automatic fixes. Use code_helper for reviewed source proposals.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "plan | draft; execution/build unsupported"},
        "description": {"type": "STRING", "description": "Project to propose, at most 8000 characters"},
        "language": {"type": "STRING", "description": "Proposed programming language"},
        "project_name": {"type": "STRING", "description": "Descriptive label, never a filesystem path"}
    }, "required": ["description"]},
    "handler": dev_agent,
}
