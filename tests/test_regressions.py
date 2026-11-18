"""
tests/test_regressions.py — regression tests for bugs that were found and fixed.

Every test here exists because the behaviour actually broke once. They are
deliberately stdlib-only (unittest + sqlite3), so they run anywhere the app runs
without pulling in pytest, a display, or an API key:

    python -m unittest discover -s tests -t . -v

Covered:
  * Cerebro: linking an entity no longer erases its label/properties
  * Cerebro: memories stay findable after the corpus vocabulary grows
  * Cerebro: databases written by the old schema self-migrate and self-heal
  * workspace_recall: remember() -> search_memories() round-trip
  * web_autopilot: flight date fallback does not raise
  * main.py: imports the modules it actually uses (os)
"""
from __future__ import annotations

import ast
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import memory.cerebro_graph as cg


def _fresh_db(name: str) -> Path:
    return Path(tempfile.mkdtemp()) / f"{name}.db"


class CerebroLinkTests(unittest.TestCase):
    """link_entities() must add an edge, never rewrite the nodes it connects."""

    def setUp(self):
        cg._DB_PATH = _fresh_db(f"link_{time.time_ns()}")

    def tearDown(self):
        try:
            cg._DB_PATH.unlink(missing_ok=True)
        except OSError:
            pass

    def test_link_preserves_node_payload(self):
        cg.upsert_node(
            "flight:del_bom",
            node_type="travel",
            label="IndiGo 6E-204 Delhi to Mumbai",
            properties={"airline": "IndiGo", "flight": "6E-204", "seat": "12A"},
        )
        cg.link_entities("flight:del_bom", "mumbai", relation="arrives_in")

        conn = cg._get_db()
        try:
            label, props = conn.execute(
                "SELECT label, properties FROM nodes WHERE entity = 'flight:del_bom'"
            ).fetchone()
        finally:
            conn.close()

        import json
        self.assertEqual(label, "IndiGo 6E-204 Delhi to Mumbai")
        self.assertEqual(json.loads(props)["seat"], "12A")

    def test_link_still_creates_missing_targets(self):
        cg.upsert_node("flight:del_bom", label="IndiGo 6E-204")
        cg.link_entities("flight:del_bom", "project:trip_planning", relation="part_of")
        results = cg.semantic_query("trip planning", top_k=3)
        self.assertTrue(
            any(r["entity"] == "project:trip_planning" for r in results),
            f"newly linked node not searchable: {results}",
        )

    def test_edge_is_recorded_both_ways_for_traversal(self):
        cg.upsert_node("reactor", label="arc reactor")
        cg.link_entities("reactor", "palladium", relation="uses_element")
        top = cg.semantic_query("reactor", top_k=1)[0]
        self.assertTrue(
            any(c.get("target") == "palladium" and c["relation"] == "uses_element"
                for c in top["connections"]),
            top["connections"],
        )


class CerebroRecallTests(unittest.TestCase):
    """Recall must not degrade as the graph grows — the vocabulary is dynamic."""

    def setUp(self):
        cg._DB_PATH = _fresh_db(f"recall_{time.time_ns()}")

    def tearDown(self):
        try:
            cg._DB_PATH.unlink(missing_ok=True)
        except OSError:
            pass

    def test_memory_survives_corpus_growth(self):
        cg.upsert_node("quantum reactor blueprint",
                       label="arc reactor design palladium core")
        first = cg.semantic_query("reactor palladium", top_k=3)
        self.assertEqual(first[0]["entity"], "quantum reactor blueprint")
        self.assertGreater(first[0]["relevance_score"], 0.3)

        # 40 unrelated inserts reshuffle token->index mapping in the vocabulary.
        for i in range(40):
            cg.upsert_node(
                f"meeting note {i} about marketing budgets and sales funnels",
                label=f"quarterly sales funnel review number {i} pipeline metrics",
            )

        after = cg.semantic_query("reactor palladium", top_k=3)
        self.assertEqual(
            after[0]["entity"], "quantum reactor blueprint",
            f"old memory lost after corpus growth: {[(r['entity'], r['relevance_score']) for r in after]}",
        )
        self.assertGreater(after[0]["relevance_score"], 0.3)

    def test_legacy_database_self_migrates(self):
        """A DB from before vocab signatures existed must still be searchable."""
        import json
        import sqlite3

        legacy = _fresh_db(f"legacy_{time.time_ns()}")
        conn = sqlite3.connect(legacy)
        conn.executescript("""
            CREATE TABLE nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, entity TEXT UNIQUE,
                node_type TEXT, label TEXT, properties TEXT,
                created_at REAL, updated_at REAL);
            CREATE TABLE edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER,
                target_id INTEGER, relation TEXT, weight REAL DEFAULT 1.0,
                properties TEXT, created_at REAL);
            CREATE TABLE embeddings (node_id INTEGER PRIMARY KEY, vector_json TEXT);
        """)
        conn.execute(
            "INSERT INTO nodes (entity, node_type, label, properties, created_at, updated_at)"
            " VALUES (?,?,?,?,0,0)",
            ("indigo 6e-204 to mumbai", "travel", "flight booking PNR XJ92K4", "{}"),
        )
        # stale 3-dimension vector, no signature — unusable against today's vocab
        conn.execute("INSERT INTO embeddings VALUES (1, ?)", (json.dumps([0.5, 0.5, 0.0]),))
        conn.commit()
        conn.close()

        cg._DB_PATH = legacy
        cg.upsert_node("grocery list", label="milk eggs bread")   # reshapes vocab
        results = cg.semantic_query("indigo flight mumbai", top_k=2)

        self.assertTrue(results, "legacy graph returned nothing after migration")
        self.assertEqual(results[0]["entity"], "indigo 6e-204 to mumbai")
        self.assertGreater(results[0]["relevance_score"], 0.3)

        conn = sqlite3.connect(legacy)
        try:
            sig = conn.execute(
                "SELECT vocab_sig FROM embeddings WHERE node_id = 1"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertTrue(sig, "repaired vector was not stamped with a vocabulary signature")
        legacy.unlink(missing_ok=True)


class WorkspaceRecallTests(unittest.TestCase):
    """search_memories() used to raise NameError: name 're' is not defined."""

    def setUp(self):
        from actions import workspace_recall as wr
        self.wr = wr
        self._orig = getattr(wr, "_DB_PATH", None)
        wr._DB_PATH = _fresh_db(f"archive_{time.time_ns()}")

    def tearDown(self):
        if self._orig is not None:
            self.wr._DB_PATH = self._orig

    def test_remember_then_search(self):
        self.wr.remember("IndiGo 6E-204 flight to Mumbai on Dec 1, PNR XJ92K4",
                         category="travel", source="test")
        out = self.wr.search_memories("flight mumbai")
        self.assertIn("6E-204", out)

    def test_keywordless_query_is_handled(self):
        self.wr.remember("something to recall", category="note", source="test")
        out = self.wr.search_memories("!!! ???")   # no searchable tokens
        self.assertIsInstance(out, str)


class FlightAutopilotFallbackTests(unittest.TestCase):
    """The fallback date path referenced datetime/timedelta that were not imported."""

    def test_fallback_date_is_tomorrow(self):
        import types
        import actions.web_autopilot as wa

        fake = types.ModuleType("actions.flight_finder")

        def boom(*_a, **_k):
            raise RuntimeError("simulated flight_finder failure")

        fake._parse_date = boom
        fake._build_google_flights_url = boom
        original = sys.modules.get("actions.flight_finder")
        had_ddg = wa._HAS_DDG_SEARCH
        sys.modules["actions.flight_finder"] = fake
        wa._HAS_DDG_SEARCH = False          # keep the test offline and deterministic
        try:
            out = wa.flight_autopilot(query="book flight from Delhi to Mumbai",
                                      date="", auto_open=False)
        finally:
            wa._HAS_DDG_SEARCH = had_ddg
            if original is not None:
                sys.modules["actions.flight_finder"] = original
            else:
                sys.modules.pop("actions.flight_finder", None)

        expected = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        self.assertIn(f"Departure Date: {expected}", out)


class ImportHygieneTests(unittest.TestCase):
    """Static guard: a module must import what it uses at module level.

    main.py's shutdown path called os._exit() from a Timer thread with no
    `import os` — the farewell printed, then the thread died and the process kept
    running. Importing main.py needs PyQt6, so this checks the source instead.
    """

    def test_main_imports_os(self):
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])
        self.assertIn("os", imported, "main.py calls os._exit() without importing os")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class WorkspaceWiringTests(unittest.TestCase):
    """Features that were wired to functions that do not exist.

    Both sites sit inside `try/except Exception`, so nothing crashed — the
    feature just quietly did nothing and reported a reassuring string instead.
    These tests assert the caller actually reaches the real entry point.
    """

    def test_lockdown_arms_the_sentry(self):
        import types
        from actions import iot_overlord as iot

        stub = types.ModuleType("actions.sentry_protocol")
        stub.activate_sentry = lambda player=None: "SENTRY-ARMED-MARKER"
        originals = {k: sys.modules.get(k) for k in
                     ("actions.sentry_protocol", "actions.network_auditor")}
        sys.modules["actions.sentry_protocol"] = stub

        real_subprocess = iot.subprocess
        real_ha = iot._call_ha_service
        iot.subprocess = types.SimpleNamespace(run=lambda *a, **k: None, DEVNULL=-3)
        iot._call_ha_service = lambda *a, **k: False
        try:
            out = iot.execute_lockdown_protocol()
        finally:
            iot.subprocess = real_subprocess
            iot._call_ha_service = real_ha
            for k, v in originals.items():
                if v is not None:
                    sys.modules[k] = v
                else:
                    sys.modules.pop(k, None)

        self.assertIn("SENTRY-ARMED-MARKER", out,
                      "lockdown no longer reaches sentry_protocol.activate_sentry()")

    def test_cyber_preset_actually_runs_the_audit(self):
        import actions.workspace_matrix as wm
        import actions.network_auditor as na

        patched = ("_launch_code_editor", "_launch_terminal", "_launch_app_safe",
                   "_open_music_stream", "_set_volume", "_set_brightness",
                   "_trigger_iot_lighting")
        originals = {name: getattr(wm, name) for name in patched}
        real_audit = na.audit_security_posture
        for name in patched:
            setattr(wm, name, lambda *a, **k: "stubbed")
        na.audit_security_posture = lambda *a, **k: "AUDIT-RAN-MARKER"
        try:
            out = wm.orchestrate_workspace("cyber security audit mode")
        finally:
            for name, fn in originals.items():
                setattr(wm, name, fn)
            na.audit_security_posture = real_audit

        self.assertIn("AUDIT-RAN-MARKER", out,
                      "cyber preset no longer reaches network_auditor.audit_security_posture()")


class GitStatusParsingTests(unittest.TestCase):
    """Branch names were parsed with one regex that mishandled three real cases."""

    @classmethod
    def setUpClass(cls):
        import shutil
        if not shutil.which("git"):
            raise unittest.SkipTest("git not installed")

    def _repo(self, branch=None, commit=False, detach=False):
        import subprocess
        d = Path(tempfile.mkdtemp()) / "repo"
        d.mkdir()
        def sh(*a):
            return subprocess.run(["git", *a], cwd=d, capture_output=True, text=True)
        sh("init", "-q")
        sh("config", "user.email", "t@t.t")
        sh("config", "user.name", "T")
        if commit:
            (d / "a.txt").write_text("x")
            sh("add", "-A"); sh("commit", "-qm", "init")
        if branch:
            sh("checkout", "-qb", branch)
        if detach:
            sh("checkout", "-q", "--detach")
        return d

    @staticmethod
    def _branch_line(repo):
        """Pull the branch name out of the rendered status block.

        The sync suffix ("(Up to date)", "(2 ahead)") is stripped from the END
        only — a naive split on "(" would also eat "HEAD (detached)".
        """
        import re
        from actions.git_sentinel import git_status
        for line in git_status(repo).splitlines():
            if "Branch" in line:
                value = line.split("Branch:")[1]
                value = re.sub(r"\s*\((?:Up to date|[^()]*ahead[^()]*|[^()]*behind[^()]*)\)\s*$",
                               "", value)
                return value.strip()
        return None

    def test_repo_with_no_commits_reports_its_branch(self):
        got = self._branch_line(self._repo())
        self.assertIn(got, ("master", "main"),
                      f"fresh repo reported branch {got!r} instead of its real branch")

    def test_branch_name_with_a_dot_is_not_truncated(self):
        got = self._branch_line(self._repo(branch="feature/v1.2", commit=True))
        self.assertEqual(got, "feature/v1.2")

    def test_detached_head_is_reported_as_detached(self):
        got = self._branch_line(self._repo(commit=True, detach=True))
        self.assertEqual(got, "HEAD (detached)")


class QuickTimerTests(unittest.TestCase):
    """A tool handler must answer, not raise — and must not invent a duration."""

    def setUp(self):
        import actions.quick_timer as qt
        self.qt = qt
        self._real = qt.start_countdown_timer
        qt.start_countdown_timer = lambda secs, message="", speak_cb=None, player_cb=None: f"SET:{secs}"

    def tearDown(self):
        self.qt.start_countdown_timer = self._real

    def test_non_numeric_duration_answers_instead_of_raising(self):
        out = self.qt.quick_timer_handler({"seconds": "abc"})
        self.assertIsInstance(out, str)
        self.assertIn("must be a number", out)

    def test_numeric_strings_are_accepted(self):
        self.assertEqual(self.qt.quick_timer_handler({"minutes": "2"}), "SET:120")
        self.assertEqual(self.qt.quick_timer_handler({"seconds": "90"}), "SET:90")

    def test_floats_are_accepted(self):
        self.assertEqual(self.qt.quick_timer_handler({"seconds": 1.5}), "SET:1")

    def test_missing_duration_asks_instead_of_defaulting(self):
        out = self.qt.quick_timer_handler({})
        self.assertIn("How long", out)
        self.assertNotIn("SET:", out)

    def test_negative_duration_is_rejected(self):
        out = self.qt.quick_timer_handler({"minutes": -1})
        self.assertIn("already passed", out)

    def test_booleans_are_rejected(self):
        out = self.qt.quick_timer_handler({"seconds": True})
        self.assertIn("must be a number", out)


class PlatformImportTests(unittest.TestCase):
    """Tools must load on every supported OS, even where a library has no backend."""

    def test_chronos_predictive_imports_on_every_platform(self):
        # pygetwindow raises NotImplementedError on Linux — not ImportError — so
        # the old guard let it escape and the entire Chronos tool failed to load.
        # gw is only consulted on Windows, so degrading is the correct behaviour.
        import actions.chronos_predictive as chronos  # noqa: F401
        self.assertIn("_GW_AVAILABLE", vars(chronos))
