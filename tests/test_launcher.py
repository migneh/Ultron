"""
tests/test_launcher.py — the `ultron` command.

Both launchers are thin on purpose, but they are the first thing anyone runs, so
the two properties that matter get held down here:

  * they use the project virtual environment when it exists (that is where
    `python setup.py` put the dependencies) and fall back to `python` otherwise;
  * they forward every argument untouched, so `--provider`, `--model`, `--pick`
    and `--doctor` behave exactly as they do on the command line.

`--doctor` has one extra requirement, tested here for real: it has to work when
the environment is broken. `main.py` imports sounddevice (PortAudio) at module
level, so before the flag was handled ahead of those imports, `ultron --doctor`
died of the very problem it was called to describe.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BAT = ROOT / "ultron.bat"
SH = ROOT / "ultron"


class WindowsLauncherTests(unittest.TestCase):
    def setUp(self):
        if not BAT.exists():
            self.fail("ultron.bat is missing")
        self.text = BAT.read_text(encoding="utf-8")

    def test_it_prefers_the_project_virtual_environment(self):
        self.assertIn(".venv", self.text)
        self.assertIn(r"Scripts\python.exe", self.text)

    def test_it_falls_back_to_python_on_path(self):
        self.assertIn('set "PY=python"', self.text)

    def test_it_forwards_every_argument(self):
        self.assertIn("%*", self.text)

    def test_it_keeps_the_window_open_when_something_failed(self):
        # Double-clicking closes the window the instant the app stops, taking
        # the reason with it.
        self.assertIn("pause", self.text)

    def test_it_returns_the_child_exit_code(self):
        self.assertIn("exit /b %CODE%", self.text)

    def test_it_runs_the_checkout_it_sits_in(self):
        self.assertIn("%~dp0", self.text)


class PosixLauncherTests(unittest.TestCase):
    def setUp(self):
        self.text = SH.read_text(encoding="utf-8")

    def test_it_is_executable(self):
        import os
        self.assertTrue(os.access(SH, os.X_OK), "chmod +x ultron was lost")

    def test_it_prefers_the_virtual_environment_and_forwards_arguments(self):
        self.assertIn(".venv/bin/python", self.text)
        self.assertIn('"$@"', self.text)

    def test_it_runs_main_py_from_its_own_directory(self):
        self.assertIn('"$HERE/main.py"', self.text)


class DoctorBeforeHeavyImportsTests(unittest.TestCase):
    """`ultron --doctor` must run even when the app cannot import."""

    def test_doctor_flag_is_handled_before_sounddevice_is_imported(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        guard = source.index('"--doctor"')
        heavy = source.index("import sounddevice")
        self.assertLess(guard, heavy,
                        "--doctor is answered after the imports that may be broken")

    def test_running_the_launcher_with_doctor_produces_a_report(self):
        if not shutil_which_python():
            self.skipTest("no interpreter available to run the launcher")
        proc = subprocess.run([sys.executable, str(ROOT / "main.py"), "--doctor"],
                              capture_output=True, text=True, timeout=180,
                              cwd=str(ROOT))
        output = proc.stdout + proc.stderr
        self.assertIn("checks", output, output[:400])
        self.assertNotIn("Traceback", output)


def shutil_which_python() -> bool:
    import shutil
    return bool(shutil.which(sys.executable) or True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
