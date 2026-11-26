"""Fake Git process only; temp metadata, no actual Git/remote/repository effects."""
from types import SimpleNamespace

import pytest

from ultron.actions import git_sentinel as git
from ultron.core import confirm
from ultron.core import git_inspection as inspection
from ultron.core import operation_policy as policy


@pytest.fixture
def rig(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    config = tmp_path / ".git" / "config"
    config.write_text("[core]\nrepositoryformatversion = 0\n")
    state = SimpleNamespace(repo=tmp_path, seen=[], calls=[], code=0, stdout=b"fake local output\n", stderr=b"", hang=False, killed=0, on_start=None)
    monkeypatch.setattr(inspection, "_binary", lambda: {"path": "/fake/git", "identity": [1, 2, "digest"]})
    class Process:
        def __init__(self, command, **kw):
            state.calls.append((command, kw))
            kw["stdout"].write(state.stdout)
            kw["stdout"].flush()
            kw["stderr"].write(state.stderr)
            kw["stderr"].flush()
            self.returncode = state.code
            if state.on_start:
                state.on_start()
        def poll(self):
            return None if state.hang and not state.killed else self.returncode
        def kill(self):
            state.killed += 1
        def wait(self, timeout):
            assert timeout == 1
            return self.returncode
    monkeypatch.setattr(inspection.subprocess, "Popen", Process)
    for attr in ("_pending", "_show_cb", "_hide_cb", "_log_cb", "_show_with_id_cb", "_hide_with_id_cb"):
        monkeypatch.setattr(confirm, attr, None)
    return state


def preview(rig, monkeypatch, action="status", count=5):
    monkeypatch.setattr(confirm, "request", lambda **kw: rig.seen.append(kw) or "pending")
    return inspection.request(rig.repo, action, count)


@pytest.mark.parametrize("action", ["status", "diff", "branch", "log"])
def test_headless_fixed_reads_no_process(rig, action):
    assert "have not done it" in inspection.request(rig.repo, action)
    assert not rig.calls


def test_approved_bound_command_and_replay(rig, monkeypatch):
    assert preview(rig, monkeypatch) == "pending" and not rig.calls
    assert "status" in rig.seen[0]["detail"] and str(rig.repo) in rig.seen[0]["detail"]
    assert "local inspection returned" in rig.seen[0]["run"]()
    command, options = rig.calls[0]
    assert command[-5:] == ["status", "--porcelain=v1", "-b", "--untracked-files=normal", "--ignore-submodules=all"]
    assert "--no-optional-locks" in command and "core.fsmonitor=false" in command
    assert options["env"]["GIT_NO_LAZY_FETCH"] == "1" and options["env"]["GIT_ALLOW_PROTOCOL"] == ""
    assert "REJECTED" in rig.seen[0]["run"]() and len(rig.calls) == 1


def test_deny_no_effect(rig, monkeypatch):
    preview(rig, monkeypatch)
    rig.seen[0]["on_cancel"]("denied")
    assert "REJECTED" in rig.seen[0]["run"]() and not rig.calls


def test_expired_no_process(rig, monkeypatch):
    preview(rig, monkeypatch)
    monkeypatch.setattr(policy.time, "monotonic", lambda: float("inf"))
    assert "EXPIRED" in rig.seen[0]["run"]() and not rig.calls


def test_changed_config_before_callback_refused(rig, monkeypatch):
    preview(rig, monkeypatch)
    (rig.repo / ".git" / "config").write_text("changed")
    assert "refused" in rig.seen[0]["run"]() and not rig.calls


def test_changed_config_after_query_discards_output(rig, monkeypatch):
    rig.on_start = lambda: (rig.repo / ".git" / "config").write_text("changed")
    preview(rig, monkeypatch)
    result = rig.seen[0]["run"]()
    assert "output discarded" in result and "fake local output" not in result


def test_diff_has_no_external_diff_textconv_and_two_fixed_vectors(rig, monkeypatch):
    preview(rig, monkeypatch, "diff")
    assert "local inspection returned" in rig.seen[0]["run"]()
    assert len(rig.calls) == 2
    assert all("--no-ext-diff" in cmd and "--no-textconv" in cmd for cmd, _ in rig.calls)


def test_deadline_kills_owned_process_no_retry(rig, monkeypatch):
    rig.hang = True
    preview(rig, monkeypatch)
    monkeypatch.setattr(inspection, "TIMEOUT", -1)
    assert "deadline/output cap" in rig.seen[0]["run"]()
    assert len(rig.calls) == 1 and rig.killed == 1


def test_output_cap_discards_no_raw_output(rig, monkeypatch):
    rig.stdout = b"x" * (inspection.MAX_OUTPUT + 1)
    preview(rig, monkeypatch)
    assert "output cap" in rig.seen[0]["run"]()


def test_native_error_stderr_not_exposed(rig, monkeypatch):
    rig.code = 1
    rig.stderr = b"private credentials"
    preview(rig, monkeypatch)
    result = rig.seen[0]["run"]()
    assert "returned an error" in result and "private" not in result


def test_raw_sinks_no_grant_or_argv_escape(rig):
    plan = policy.prepare("git.local_inspection", ("repo",), {})
    with pytest.raises(PermissionError):
        inspection._run_git(plan, rig.repo, [["push"]])
    assert git._run_git(["push"], rig.repo)[0] == -1
    assert not rig.calls


@pytest.mark.parametrize("action", ["commit", "auto_commit", "save", "push", "pull", "sync", "stash", "fetch", "checkout", "create_branch"])
def test_mutation_dispatch_refused_before_even_resolving_repo(rig, action):
    assert "disabled" in git.git_sentinel({"action": action, "repo_path": str(rig.repo)})
    assert not rig.calls


def test_direct_mutation_helpers_fail_closed(rig):
    assert "disabled" in git.git_commit(rig.repo, "message", push=True)
    assert "disabled" in git.git_push_pull(rig.repo, "--help")
    assert "disabled" in git.git_branch(rig.repo, "other", create=True)
    assert not rig.calls


@pytest.mark.parametrize("count", [0, 21, True, "5", -1])
def test_invalid_count_no_approval(rig, monkeypatch, count):
    assert "unavailable" in preview(rig, monkeypatch, "log", count)
    assert not rig.seen and not rig.calls


def test_explicit_repo_no_silent_fallback(rig):
    assert "explicit" in git.git_sentinel({"action": "status"})
    assert not rig.calls


def test_worktree_git_file_rejected(rig, monkeypatch):
    config = rig.repo / ".git" / "config"
    config.unlink()
    (rig.repo / ".git").rmdir()
    (rig.repo / ".git").write_text("gitdir: elsewhere")
    assert "unavailable" in preview(rig, monkeypatch)
    assert not rig.calls


def test_even_approved_constructed_plan_cannot_smuggle_mutation_vector(rig, monkeypatch):
    plan = policy.prepare("git.local_inspection", ("repo",), {"commands": [["push"]]})
    monkeypatch.setattr(confirm, "request", lambda **kw: kw["run"]())
    result = policy.request(plan, title="test", detail="fake", execute=lambda approved: inspection._run_git(approved, rig.repo, [["push"]]))
    assert "not an allowed fixed inspection" in result and not rig.calls
