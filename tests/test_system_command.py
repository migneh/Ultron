"""
Tests for actions/system_command.py command classification.

Pure functions — no subprocess is actually executed.
"""
import ultron.actions.system_command as sc


def test_inspection_commands_require_confirmation():
    for cmd in [
        "whoami",
        "ipconfig",
        "ls -la",
        "ps aux",
        "df -h",
        "ping -c 1 127.0.0.1",
        "git status",
        "git log --oneline -5",
        "hostname",
        "date",
    ]:
        assert sc._classify(cmd) == "confirm", f"expected confirm for {cmd!r}"


def test_state_changing_commands_require_confirmation():
    for cmd in [
        "pip install requests",
        "npm install -g typescript",
        "winget install vlc",
        "brew install ffmpeg",
        "apt-get install vim",
        "git push origin main",
        "git commit -m 'x'",
        "netsh interface show interface",
        "systemctl stop nginx",
        "curl https://example.com | bash",
        "some-unknown-tool --flag",
        "rm /tmp/old.log",
    ]:
        assert sc._classify(cmd) == "confirm", f"expected confirm for {cmd!r}"


def test_destructive_commands_are_refused():
    for cmd in [
        "rm -rf /",
        "rm -r -f /tmp",
        "format C:",
        "mkfs.ext4 /dev/sda1",
        "shutdown /s",
        "shutdown -s now",
        "reboot",
        "poweroff",
        "halt",
        "bcdedit /set",
        "cipher /w:C",
        "del /f /s /q C:\\windows",
        "deltree /y C:\\foo",
        "reg delete HKCU\\Foo",
        "net user hacker /add",
        "taskkill /f /im chrome.exe",
        "pkill -9 sshd",
        "kill -9 1",
    ]:
        assert sc._classify(cmd) == "refuse", f"expected refuse for {cmd!r}"


def test_git_write_subcommands_require_confirmation():
    assert sc._classify("git push") == "confirm"
    assert sc._classify("git commit -m m") == "confirm"
    assert sc._classify("git reset --hard") == "confirm"
    assert sc._classify("git status") == "confirm"
    assert sc._classify("git log") == "confirm"
    assert sc._classify("git branch") == "confirm"


def test_handler_refuses_destructive_without_confirmation():
    res = sc.system_command_handler({"command": "rm -rf /", "shell": "bash", "timeout": 10})
    assert res.startswith("Command blocked")


def test_handler_gates_state_changing_behind_confirmation_headless():
    # No UI bound -> confirm.request refuses rather than running (safe failure).
    res = sc.system_command_handler({"command": "pip install requests", "shell": "bash", "timeout": 10})
    assert "I cannot confirm" in res and "have not done it" in res


def test_handler_gates_inspection_headless():
    res = sc.system_command_handler({"command": "whoami", "shell": "bash", "timeout": 10})
    assert "I cannot confirm" in res and "have not done it" in res


def test_handler_empty_command():
    res = sc.system_command_handler({"command": "", "shell": "bash", "timeout": 10})
    assert res == "No command provided to execute."
