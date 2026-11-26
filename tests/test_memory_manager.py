"""Memory integrity regressions. All persistence is redirected to temporary files."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from ultron.memory import memory_manager as mm


@pytest.fixture(autouse=True)
def isolated_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(mm, "MEMORY_PATH", tmp_path / 'ultron.memory.json')
    monkeypatch.setattr(mm, "_graph_enabled", lambda: False)


def test_bare_string_updates_do_not_crash():
    mm.update_memory({"notes": {"topic": "robotics"}})
    assert mm.load_memory()["notes"]["topic"]["value"] == "robotics"


def test_feedback_and_corrections_persist():
    mm.remember("topic", "old")
    mm.feedback_helpful("notes", "topic")
    mm.feedback_not_helpful("notes", "topic")
    mm.feedback_correct("notes", "topic", "corrected")
    mm.edit_memory("topic", "latest")
    entry = mm.load_memory()["notes"]["topic"]
    assert entry["value"] == "latest"
    assert entry["feedback"]["helpful"] == 1
    assert entry["feedback"]["not_helpful"] == 1
    assert entry["feedback"]["corrections"][0]["old"] == "old"


def test_metadata_only_edit_persists():
    mm.remember("topic", "same")
    mm.edit_memory("topic", "same", confidence="medium", source="user correction")
    entry = mm.load_memory()["notes"]["topic"]
    assert entry["confidence"] == "medium"
    assert entry["source"] == "user correction"


def test_pending_confirmation_moves_entry_once():
    mm.update_memory({"_pending": {"notes/topic": {"value": "robotics"}}})
    assert mm.search_memory("robotics").startswith("Nothing stored")
    assert not mm.all_entries_for_ui()
    mm.confirm_pending("notes/topic")
    data = mm.load_memory()
    assert data["notes"]["topic"]["value"] == "robotics"
    assert not data["_pending"]


def test_legacy_feedback():
    mm.save_memory({"notes": {"legacy": "hello"}})
    mm.feedback_helpful("notes", "legacy")
    assert mm.load_memory()["notes"]["legacy"]["feedback"]["helpful"] == 1


def test_concurrent_updates_do_not_lose_entries():
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda n: mm.remember(str(n), str(n)), range(40)))
    assert len(mm.load_memory()["notes"]) == 40
    assert isinstance(json.loads(mm.MEMORY_PATH.read_text()), dict)


def test_concurrent_feedback_counts():
    mm.remember("topic", "robotics")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: mm.feedback_helpful("notes", "topic"), range(30)))
    assert mm.load_memory()["notes"]["topic"]["feedback"]["helpful"] == 30


@pytest.mark.parametrize("data", [
    {"notes": []}, {"notes": {"bad": None}},
    {"notes": {"bad": {"value": []}}},
    {"notes": {"bad": {"value": "x", "confidence": []}}},
    {"notes": {"bad": {"value": "x", "feedback": None}}},
    {"notes": {"bad": {"value": "x", "feedback": {"helpful": "lots"}}}},
])
def test_invalid_import_is_rejected_without_replacing_store(data):
    mm.remember("keep", "safe")
    assert mm.import_memories(json.dumps(data), merge=False).startswith("Import failed")
    assert mm.load_memory()["notes"]["keep"]["value"] == "safe"
