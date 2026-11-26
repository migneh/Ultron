"""Approved fixed local Git inspection; autonomous mutations fail closed."""
from __future__ import annotations

from pathlib import Path

from ultron.core import git_inspection

DISABLED = (
    "Git mutation/remote operation disabled in git_sentinel: no exact staged-file, "
    "hook/helper, branch or remote-content approval adapter is configured. "
    "No staging, commit, checkout, branch creation, stash, fetch, push or pull attempted. "
    "Use local inspection or perform reviewed Git operations manually."
)


def _run_git(args, cwd):
    """Former arbitrary argv helper is not a raw execution route."""
    return -1, "", "Legacy raw Git runner disabled; use approved fixed inspection."


def _resolve_repo(path_str):
    if not isinstance(path_str, (str, Path)) or not str(path_str).strip():
        raise ValueError("Explicit repository root required; no silent fallback")
    return Path(path_str).expanduser()


def git_status(repo_dir):
    return git_inspection.request(repo_dir, "status")


def git_diff_summary(repo_dir):
    return git_inspection.request(repo_dir, "diff")


def git_log_history(repo_dir, count=5):
    return git_inspection.request(repo_dir, "log", count)


def git_branch(repo_dir, branch_name=None, create=False):
    if branch_name or create is not False:
        return DISABLED
    return git_inspection.request(repo_dir, "branch")


def git_commit(repo_dir, message=None, push=False):
    return DISABLED


def git_push_pull(repo_dir, action="push"):
    return DISABLED


def _generate_commit_message(repo_dir):
    return "Commit generation/execution disabled; review actual staged changes manually."


def git_sentinel(parameters, player=None, **kwargs):
    if not isinstance(parameters, dict) or not isinstance(parameters.get("action", "status"), str):
        return "Invalid Git request; nothing started."
    action = parameters.get("action", "status").strip().lower()
    if action in {"commit", "auto_commit", "save", "push", "pull", "sync", "stash", "fetch", "checkout", "create_branch"}:
        return DISABLED
    try:
        repo = _resolve_repo(parameters.get("repo_path"))
        if action in {"status", "check", "inspect"}:
            return git_status(repo)
        if action in {"diff", "changes", "summary"}:
            return git_diff_summary(repo)
        if action in {"log", "history", "timeline"}:
            return git_log_history(repo, parameters.get("count", 5))
        if action == "branch":
            return git_branch(repo, parameters.get("branch"), parameters.get("create", False))
        return "Unknown Git action. Use status/diff/log/branch listing; mutations/remotes disabled."
    except Exception:
        return "Git inspection requires an explicit valid repository root; no fallback or operation attempted."


TOOL = {
    "name": "git_sentinel",
    "description": "Host-approved fixed local status/diff-stat/log/branch-list inspection for explicit repo root. No stage, commit, branch switch/create, stash, remote fetch/push/pull. Repository/config/Git remain trusted, not sandboxed. Local output disclosed to existing model/UI/log surfaces; no verified remote freshness.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "status | diff | log | branch (list only)"},
        "repo_path": {"type": "STRING", "description": "Explicit repository root with ordinary .git directory; no worktree/submodule links or silent defaults"},
        "count": {"type": "INTEGER", "description": "Log entries: explicit integer 1–20, default 5"},
        "branch": {"type": "STRING", "description": "Setting a branch is disabled"}
    }, "required": ["action", "repo_path"]},
    "handler": git_sentinel,
}
