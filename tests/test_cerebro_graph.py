"""Graph regressions, using isolated SQLite databases."""
import pytest
pytest.importorskip("numpy")
from memory import cerebro_graph as cg
from memory import memory_manager as mm


@pytest.fixture(autouse=True)
def isolated_graph(tmp_path, monkeypatch):
    monkeypatch.setattr(cg, "_DB_PATH", tmp_path / "graph.db")
    monkeypatch.setattr(mm, "MEMORY_PATH", tmp_path / "memory.json")


def test_search_remains_correct_after_vocabulary_growth():
    cg.upsert_node("astronomy", properties={"value": "galaxies telescope"})
    cg.upsert_node("gardening", properties={"value": "orchid compost soil"})
    assert cg.semantic_query("galaxies telescope")[0]["entity"] == "astronomy"
    assert cg.semantic_query("orchid compost")[0]["entity"] == "gardening"
    assert cg.semantic_query("zzzzqqqq") == []


def test_link_preserves_properties_and_traverses_two_hops():
    first = cg.upsert_node("a", node_type="person", label="Alice", properties={"value": "friend"})
    cg.link_entities("a", "b", "knows")
    cg.link_entities("b", "c", "knows")
    conn = cg._get_db()
    try:
        row = conn.execute("SELECT node_type, label, properties FROM nodes WHERE id=?", (first,)).fetchone()
        assert row[0:2] == ("person", "Alice")
        assert "friend" in row[2]
    finally:
        conn.close()
    assert len(cg.get_connections("a", depth=1)) == 1
    assert len(cg.get_connections("a", depth=2)) == 2
    assert cg.get_connections("unknown") == []


def test_memory_sync_and_forgetting():
    mm.remember("hobby", "astronomy")
    assert "astronomy" in mm.semantic_search_memory("astronomy")
    mm.forget("hobby")
    assert "Nothing stored" in mm.semantic_search_memory("astronomy")
    assert not cg.semantic_query("astronomy")


def test_stale_graph_does_not_override_replaced_store():
    mm.remember("hobby", "astronomy")
    mm.import_memories('{"notes": {"hobby": {"value": "gardening"}}}', merge=False)
    assert mm.semantic_search_memory("astronomy").startswith("Nothing stored")
