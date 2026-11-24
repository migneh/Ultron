"""
memory/cerebro_graph.py — Project Cerebro: Infinite Neural Memory Vector Graph Engine for Ultron AI.

Implements a local, high-performance SQLite Knowledge Graph with:
1. Entity-Relationship nodes and weighted directed edges.
2. Lightweight semantic TF-IDF / n-gram vector embeddings with L2-normalized cosine similarity.
3. Multi-hop sub-graph traversal for deep context synthesis.
"""
from __future__ import annotations

import collections
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Optional

import numpy as np

_BASE_DIR = Path(__file__).resolve().parent.parent
_DB_PATH = _BASE_DIR / "memory" / "cerebro_graph.db"


def _get_db() -> sqlite3.Connection:
    """Connect to the Cerebro Knowledge Graph SQLite database in WAL mode."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity TEXT UNIQUE,
                node_type TEXT,
                label TEXT,
                properties TEXT,
                created_at REAL,
                updated_at REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER,
                target_id INTEGER,
                relation TEXT,
                weight REAL DEFAULT 1.0,
                properties TEXT,
                created_at REAL,
                FOREIGN KEY(source_id) REFERENCES nodes(id) ON DELETE CASCADE,
                FOREIGN KEY(target_id) REFERENCES nodes(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                node_id INTEGER PRIMARY KEY,
                vector_json TEXT,
                FOREIGN KEY(node_id) REFERENCES nodes(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_entity ON nodes(entity)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(source_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_tgt ON edges(target_id)")
    return conn


def _tokenize(text: str) -> list[str]:
    """Extract clean words and character 3-grams for semantic fuzzy indexing."""
    clean = (text or "").lower()
    words = re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", clean)
    # Character 3-grams for sub-word matching
    trigrams = [clean[i:i+3] for i in range(len(clean) - 2) if " " not in clean[i:i+3]]
    return words + trigrams[:60]


def _build_vector(text: str, vocab: dict[str, int]) -> np.ndarray:
    """Build L2-normalized bag-of-tokens vector against vocabulary."""
    tokens = _tokenize(text)
    dim = len(vocab)
    if dim == 0:
        return np.zeros(1, dtype=np.float32)
    vec = np.zeros(dim, dtype=np.float32)
    for tok in tokens:
        idx = vocab.get(tok)
        if idx is not None and idx < dim:
            vec[idx] += 1.0
    norm = np.linalg.norm(vec)
    if norm > 1e-6:
        vec = vec / norm
    return vec


def _get_corpus_vocab(conn: sqlite3.Connection) -> dict[str, int]:
    """Constructs dynamic vocabulary from indexed nodes."""
    cur = conn.cursor()
    cur.execute("SELECT entity, label, properties FROM nodes")
    rows = cur.fetchall()
    counts: collections.Counter[str] = collections.Counter()
    for entity, label, props in rows:
        tokens = _tokenize(f"{entity} {label} {props}")
        counts.update(tokens)
    # Take top 800 most informative tokens
    common = [tok for tok, _ in counts.most_common(800)]
    return {tok: i for i, tok in enumerate(common)}


def upsert_node(
    entity: str,
    node_type: str = "concept",
    label: str = "",
    properties: dict | None = None
) -> int:
    """Creates or updates a node in the Cerebro Graph and refreshes its vector embedding."""
    clean_entity = (entity or "").strip().lower()
    if not clean_entity:
        raise ValueError("Entity identifier cannot be empty.")

    clean_type = (node_type or "concept").strip().lower()
    clean_label = (label or entity).strip()
    props_json = json.dumps(properties or {}, ensure_ascii=False)
    now = time.time()

    conn = _get_db()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO nodes (entity, node_type, label, properties, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity) DO UPDATE SET
                    node_type = excluded.node_type,
                    label = excluded.label,
                    properties = excluded.properties,
                    updated_at = excluded.updated_at
            """, (clean_entity, clean_type, clean_label, props_json, now, now))
            # lastrowid can refer to a different prior insert on UPSERT conflict.
            cur.execute("SELECT id FROM nodes WHERE entity = ?", (clean_entity,))
            node_id = cur.fetchone()[0]

            # Update semantic embedding
            vocab = _get_corpus_vocab(conn)
            text_rep = f"{clean_entity} {clean_label} {props_json}"
            vec = _build_vector(text_rep, vocab)
            cur.execute("""
                INSERT OR REPLACE INTO embeddings (node_id, vector_json)
                VALUES (?, ?)
            """, (node_id, json.dumps(vec.tolist())))

        return int(node_id)
    finally:
        conn.close()


def link_entities(
    source_entity: str,
    target_entity: str,
    relation: str = "related_to",
    weight: float = 1.0,
    properties: dict | None = None
) -> str:
    """Forms a weighted, directed semantic edge between two entity nodes."""
    # Linking must not reset existing labels, types and properties.
    def ensure(entity):
        conn = _get_db()
        try:
            row = conn.execute("SELECT id FROM nodes WHERE entity=?",
                               (entity.strip().lower(),)).fetchone()
        finally:
            conn.close()
        return row[0] if row else upsert_node(entity)
    s_id = ensure(source_entity)
    t_id = ensure(target_entity)

    rel_clean = (relation or "related_to").strip().lower()
    props_json = json.dumps(properties or {}, ensure_ascii=False)
    now = time.time()

    conn = _get_db()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO edges (source_id, target_id, relation, weight, properties, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (s_id, t_id, rel_clean, float(weight), props_json, now))
        return f"Linked: ({source_entity}) -[{rel_clean} (w={weight:.1f})]-> ({target_entity})"
    finally:
        conn.close()


def semantic_query(query: str, top_k: int = 5, depth: int = 1) -> list[dict]:
    """
    Performs cosine vector RAG search across the graph, then traverses connected subgraphs.
    """
    conn = _get_db()
    try:
        vocab = _get_corpus_vocab(conn)
        if not vocab:
            return []

        q_vec = _build_vector(query, vocab)
        cur = conn.cursor()

        # Vocabulary changes on every insert/update. Persisted vectors may have
        # different dimensions OR the same dimensions with different token order.
        # Compute against one shared vocabulary snapshot for correct comparisons.
        cur.execute("SELECT id, entity, label, properties FROM nodes")
        scores = []
        for n_id, entity, label, props in cur.fetchall():
            vector = _build_vector(f"{entity} {label} {props}", vocab)
            sim = float(np.dot(q_vec, vector))
            if sim > 0:
                scores.append((n_id, sim))

        scores.sort(key=lambda t: t[1], reverse=True)
        top_nodes = scores[:top_k]

        results = []
        for n_id, score in top_nodes:
            cur.execute("SELECT id, entity, node_type, label, properties FROM nodes WHERE id = ?", (n_id,))
            n_row = cur.fetchone()
            if not n_row:
                continue

            nid, ent, ntype, lbl, props_str = n_row
            try:
                props = json.loads(props_str)
            except Exception:
                props = {}

            connections = _connections(conn, nid, depth)

            results.append({
                "id": nid,
                "entity": ent,
                "type": ntype,
                "label": lbl,
                "properties": props,
                "relevance_score": round(score, 3),
                "connections": connections,
            })

        return results
    finally:
        conn.close()


def get_graph_metrics() -> dict:
    """Computes graph topological metrics (nodes, edges, types, density)."""
    conn = _get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM nodes")
        node_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM edges")
        edge_count = cur.fetchone()[0]
        cur.execute("SELECT node_type, COUNT(*) FROM nodes GROUP BY node_type")
        types_breakdown = {t: c for t, c in cur.fetchall()}

        density = (2.0 * edge_count / (node_count * (node_count - 1))) if node_count > 1 else 0.0
        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "density": round(density, 4),
            "node_types": types_breakdown,
            "storage_path": str(_DB_PATH),
        }
    finally:
        conn.close()


def _connections(conn: sqlite3.Connection, node_id: int, depth: int) -> list[dict]:
    """Bounded breadth-first traversal, also used for exact entity lookups."""
    seen = {node_id}
    frontier = {node_id}
    result = []
    edge_seen = set()
    for _ in range(min(max(depth, 0), 4)):
        following = set()
        for current in sorted(frontier):
            rows = conn.execute("""
                SELECT e.id, e.source_id, e.target_id, e.relation, e.weight,
                       s.entity, s.label, t.entity, t.label
                FROM edges e JOIN nodes s ON s.id=e.source_id
                             JOIN nodes t ON t.id=e.target_id
                WHERE e.source_id=? OR e.target_id=?
            """, (current, current)).fetchall()
            for eid, src, tgt, relation, weight, se, sl, te, tl in rows:
                if eid in edge_seen:
                    continue
                edge_seen.add(eid)
                outgoing = src == current
                other = tgt if outgoing else src
                item = {"direction": "out" if outgoing else "in",
                        "relation": relation, "weight": weight,
                        "label": tl if outgoing else sl}
                item["target" if outgoing else "source"] = te if outgoing else se
                result.append(item)
                if len(result) >= 100:
                    return result
                if other not in seen:
                    following.add(other)
        seen.update(following)
        frontier = following
    return result


def get_connections(entity: str, depth: int = 2) -> list[dict]:
    conn = _get_db()
    try:
        row = conn.execute("SELECT id FROM nodes WHERE entity=?",
                           (entity.strip().lower(),)).fetchone()
        return _connections(conn, row[0], depth) if row else []
    finally:
        conn.close()


def delete_node(entity: str) -> None:
    conn = _get_db()
    try:
        with conn:
            conn.execute("DELETE FROM nodes WHERE entity=?", (entity.strip().lower(),))
    finally:
        conn.close()
