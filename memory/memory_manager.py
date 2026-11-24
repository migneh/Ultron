import json
import re
from datetime import datetime
from threading import Lock
from pathlib import Path
import sys


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR         = get_base_dir()
MEMORY_PATH      = BASE_DIR / "memory" / "long_term.json"
_lock            = Lock()
MAX_VALUE_LENGTH = 380

# ── Why there are two very different numbers here ────────────────────────────
#
# There used to be one: MEMORY_MAX_CHARS = 2200, applied to the whole store. It
# was a *storage* limit, and it existed only because the entire memory was
# pasted into the system prompt on every connect — so growing the memory grew
# every single request. When it filled, _trim_to_limit() deleted the oldest
# entries and printed one line to a console nobody reads. A memory described as
# "deeply remembers projects, preferences and personal context" was in practice
# two pages long, and quietly forgot your sister's name after a few weeks.
#
# Storage and prompt budget are now separate concerns:
#
#   MEMORY_MAX_CHARS  — a runaway guard, not a feature limit. Nothing normal
#                       reaches it; a bug writing in a loop does.
#   PROMPT_CORE_CHARS — what actually rides in the system prompt every session.
#                       Smaller than the old whole-memory dump, so sessions
#                       start *faster* than before, not slower.
#
# Everything above the core stays on disk and is fetched on demand by the
# recall_memory tool — see search_memory() and format_memory_for_prompt().
MEMORY_MAX_CHARS  = 200_000
PROMPT_CORE_CHARS = 900
PROMPT_INDEX_CHARS = 420
# Most entries any one category may contribute to the core block, so a person
# with forty stored preferences still gets their sister into the prompt.
PROMPT_MAX_PER_CATEGORY = 6

# ── Confidence scoring for automatic memory extraction ────────────────────────
# High   — explicit, unambiguous statement ("my name is X", "I live in Y")
# Medium — clear intent but slightly ambiguous value ("I work at a tech company")
# Low    — pattern matched but value extraction uncertain ("I'm building something")
CONF_HIGH   = "high"
CONF_MEDIUM = "medium"
CONF_LOW    = "low"

# A "_pending" section holds low-confidence extractions awaiting user review.
# These are never sent in the system prompt until confirmed.
_PENDING_SECTION = "_pending"

# Confidence threshold: items below this go to pending review instead of auto-save.
_CONFIDENCE_REVIEW_THRESHOLD = CONF_LOW

def _empty_memory() -> dict:
    return {
        "identity":      {},
        "preferences":   {},
        "projects":      {},
        "relationships": {},
        "wishes":        {},
        "notes":         {},
        _PENDING_SECTION: {},
    }

def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        return _empty_memory()
    with _lock:
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _empty_memory()
                for key in base:
                    if key not in data:
                        data[key] = {}
                return data
            return _empty_memory()
        except Exception as e:
            print(f"[Memory] ⚠️ Load error: {e}")
            return _empty_memory()


def _entry_confidence(entry: dict | str | None) -> str:
    """Read the confidence level from a memory entry, defaulting to 'high'."""
    if isinstance(entry, dict):
        return str(entry.get("confidence", CONF_HIGH))
    return CONF_HIGH


def _entry_source(entry: dict | str | None) -> str | None:
    """Read the source utterance snippet from a memory entry."""
    if isinstance(entry, dict):
        return entry.get("source")
    return None

def _all_entries(memory: dict) -> list[tuple]:
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries


# Set by main.py so a trim can reach the activity log. Deleting something a
# person told you and mentioning it only on stdout is how a memory loses trust.
_trim_notifier = None


def set_trim_notifier(fn) -> None:
    """Register a callable(str) that surfaces trims to the user."""
    global _trim_notifier
    _trim_notifier = fn


def _trim_to_limit(memory: dict) -> dict:
    if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
        return memory
    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))
    dropped = []
    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        dropped.append(f"{cat}/{key}")
        print(f"[Memory] 🗑️  Trimmed {cat}/{key}")
    if dropped and _trim_notifier:
        try:
            _trim_notifier(
                f"SYS: Memory full — forgot {len(dropped)} oldest entries "
                f"({', '.join(dropped[:3])}{'…' if len(dropped) > 3 else ''})"
            )
        except Exception:
            pass
    return memory

def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    memory = _trim_to_limit(memory)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            new_val  = _truncate_value(str(value["value"] if isinstance(value, dict) else value))
            # Preserve existing confidence/source when overwriting a value,
            # unless the update explicitly supplies new ones.
            existing = target.get(key, {})
            entry = {
                "value": new_val,
                "updated": datetime.now().strftime("%Y-%m-%d"),
                "confidence": value.get("confidence", existing.get("confidence", CONF_HIGH) if isinstance(existing, dict) else CONF_HIGH),
                "source": value.get("source", existing.get("source") if isinstance(existing, dict) else None),
                "feedback": {"helpful": 0, "not_helpful": 0, "corrections": []},
            }
            if not isinstance(existing, dict) or existing.get("value") != new_val:
                target[key] = entry
                changed = True
    return changed


def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
        print(f"[Memory] 💾 Saved: {list(memory_update.keys())}")
        # ── Graph integration: every key-value save also becomes a graph node ──
        try:
            _sync_memory_to_graph(memory_update)
        except Exception:
            # Graph sync must never block a memory write
            pass
    return memory


def _graph_enabled() -> bool:
    """Check if cerebro_graph is importable (numpy available)."""
    try:
        import cerebro_graph  # noqa: F401
        return True
    except Exception:
        return False


def _get_graph():
    """Lazy import of cerebro_graph module."""
    from memory import cerebro_graph
    return cerebro_graph


def _sync_memory_to_graph(memory_update: dict) -> None:
    """Create/update graph nodes for every new or changed memory entry.

    Each memory key becomes a node; the value is stored as node properties.
    Identity entries get 'person' type, preferences get 'preference', etc.
    """
    if not _graph_enabled():
        return
    cg = _get_graph()
    type_map = {
        "identity": "person",
        "preferences": "preference",
        "projects": "project",
        "relationships": "person",
        "wishes": "wish",
        "notes": "note",
    }
    for category, items in memory_update.items():
        if category == _PENDING_SECTION or not isinstance(items, dict):
            continue
        node_type = type_map.get(category, "concept")
        for key, entry in items.items():
            val = _entry_value(entry)
            if not val:
                continue
            props = {
                "category": category,
                "key": key,
                "value": val,
                "updated": entry.get("updated", "") if isinstance(entry, dict) else "",
                "confidence": entry.get("confidence", CONF_HIGH) if isinstance(entry, dict) else CONF_HIGH,
            }
            source = entry.get("source") if isinstance(entry, dict) else None
            if source:
                props["source"] = source
            cg.upsert_node(
                entity=f"{category}/{key}",
                node_type=node_type,
                label=key.replace("_", " ").title(),
                properties=props,
            )

def _entry_value(entry) -> str:
    """Accept both the {'value': ..., 'updated': ...} shape and a bare string,
    because early versions of the store wrote plain strings."""
    if isinstance(entry, dict):
        return str(entry.get("value", "") or "").strip()
    return str(entry or "").strip()


def _pretty(key: str) -> str:
    return key.replace("_", " ").strip()


# Identity is always in the prompt; these categories compete for the remaining
# budget by recency.
_CATEGORY_LABELS = {
    "preferences":   "Preferences",
    "projects":      "Active projects / goals",
    "relationships": "People in their life",
    "wishes":        "Wishes / plans",
    "notes":         "Notes",
}

_IDENTITY_FIELDS = ["name", "age", "birthday", "city", "job",
                    "language", "school", "nationality"]


def format_memory_for_prompt(memory: dict | None) -> str:
    """Build the memory block that goes into the system prompt.

    This used to dump everything. It now sends three things:

      1. IDENTITY  - always, in full. It is small, and it is wrong for the
         assistant to have to look up your name.
      2. RECENT    - the most recently updated entries from every other
         category, up to PROMPT_CORE_CHARS. Recency is the cheapest useful
         relevance signal available without embeddings.
      3. AN INDEX  - the *keys* of everything else, values omitted.

    Point 3 is what makes recall work at all. A model cannot decide to look
    something up if it does not know the thing exists: with only points 1 and 2,
    "who is Ayse?" would get "I don't know" while ayse_sister sat on disk
    unread. The index costs a few hundred characters and turns recall from a
    gamble into a lookup.

    Net effect on latency: this block is SMALLER than the old full dump, so
    every session connects with fewer tokens. Occasionally the model spends one
    extra round trip on recall_memory - covered by the acknowledgment it
    already speaks before any slow step."""
    if not memory:
        return ""

    core_lines: list[str] = []

    # 1. Identity - always, in full
    identity = memory.get("identity", {}) or {}
    for field in _IDENTITY_FIELDS:
        val = _entry_value(identity.get(field))
        if not val:
            continue
        if field == "language":
            # Labelled as an observation, not a setting. A bare "Language:
            # English" line written months ago reads like a standing order and
            # was one of the reasons a Turkish question came back in English.
            core_lines.append(
                f"Has spoken to you in: {val} (an observation about the past — "
                f"always answer in the language of their CURRENT message)")
        else:
            core_lines.append(f"{field.title()}: {val}")
    for key, entry in identity.items():
        if key in _IDENTITY_FIELDS:
            continue
        val = _entry_value(entry)
        if val:
            core_lines.append(f"{_pretty(key).title()}: {val}")

    # 2. Everything else, most recently updated first
    rest: list[tuple[str, str, str, str]] = []   # (updated, cat, key, value)
    for cat in _CATEGORY_LABELS:
        for key, entry in (memory.get(cat, {}) or {}).items():
            val = _entry_value(entry)
            if not val:
                continue
            updated = (entry.get("updated", "") if isinstance(entry, dict) else "") or "0000-00-00"
            rest.append((updated, cat, key, val))
    rest.sort(key=lambda t: t[0], reverse=True)

    used    = sum(len(l) + 1 for l in core_lines)
    shown: dict[str, list[str]] = {}
    overflow: dict[str, list[str]] = {}

    # Recency decides order, but no single category may take the whole budget.
    # Without the cap, someone with forty stored preferences gets a prompt that
    # is forty preferences and not one person's name — the categories that
    # matter most in conversation are also the ones that change least often, so
    # pure recency systematically buries them.
    per_cat_used: dict[str, int] = {}
    for _updated, cat, key, val in rest:
        line = f"  - {_pretty(key).title()}: {val}"
        if (per_cat_used.get(cat, 0) < PROMPT_MAX_PER_CATEGORY
                and used + len(line) + 1 <= PROMPT_CORE_CHARS):
            shown.setdefault(cat, []).append(line)
            per_cat_used[cat] = per_cat_used.get(cat, 0) + 1
            used += len(line) + 1
        else:
            overflow.setdefault(cat, []).append(_pretty(key))

    # The index is a table of contents, so it is interleaved across categories
    # rather than continuing in recency order. Sorted by recency it would list
    # twenty-four preferences before the first relationship, and the one entry
    # the index exists for — the old fact the model has no other way to know
    # about — would fall off the end.
    indexed: list[str] = []
    if overflow:
        cats  = [c for c in _CATEGORY_LABELS if overflow.get(c)]
        cursor = {c: 0 for c in cats}
        while cats:
            for cat in list(cats):
                i = cursor[cat]
                if i >= len(overflow[cat]):
                    cats.remove(cat)
                    continue
                indexed.append(overflow[cat][i])
                cursor[cat] = i + 1

    for cat, label in _CATEGORY_LABELS.items():
        if shown.get(cat):
            core_lines.append("")
            core_lines.append(f"{label}:")
            core_lines.extend(shown[cat])

    if not core_lines and not indexed:
        return ""

    out = [
        "[WHAT YOU KNOW ABOUT THIS PERSON — use naturally, never recite like a list]",
        *core_lines,
    ]

    # 3. The index of what is on disk but not in this prompt
    if indexed:
        budget, names = PROMPT_INDEX_CHARS, []
        for n in indexed:
            if budget - len(n) - 2 < 0:
                break
            names.append(n)
            budget -= len(n) + 2
        if names:
            out.append("")
            out.append(
                "[ALSO REMEMBERED — values not shown here. Call recall_memory "
                "with a keyword to read any of these before saying you do not know]"
            )
            out.append(", ".join(names)
                       + (f" (+{len(indexed) - len(names)} more)"
                          if len(indexed) > len(names) else ""))

    return "\n".join(out) + "\n"


# ── Recall ────────────────────────────────────────────────────────────────────

def _score(query_words: list[str], cat: str, key: str, value: str) -> int:
    """Cheap lexical relevance. No embeddings, no network, no model call - this
    runs in well under a millisecond, which is the entire point: recall must
    cost one model round trip, never two."""
    hay_key = _pretty(key).lower()
    hay_val = value.lower()
    score   = 0
    for w in query_words:
        if not w:
            continue
        if w == hay_key:
            score += 10
        elif w in hay_key:
            score += 6
        if w in hay_val:
            score += 3
        if w in cat:
            score += 1
    return score


def search_memory(query: str, limit: int = 8) -> str:
    """Find stored facts matching `query`. Backs the recall_memory tool.

    An empty query is treated as "show me everything you know", capped - the
    model asks that when the user says "what do you remember about me?"."""
    memory = load_memory()
    words  = [w for w in re.split(r"[^\w]+", (query or "").lower()) if len(w) > 1]

    rows: list[tuple[int, str, str, str]] = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue                     # skip 'sessions', which is a list
        for key, entry in items.items():
            val = _entry_value(entry)
            if not val:
                continue
            s = _score(words, cat, key, val) if words else 1
            if s > 0:
                rows.append((s, cat, key, val))

    if not rows:
        return (f"Nothing stored about '{query}'." if query
                else "I have not stored anything about this person yet.")

    rows.sort(key=lambda r: (-r[0], r[2]))
    lines = [f"{cat}/{_pretty(key)}: {val}" for _s, cat, key, val in rows[:max(1, limit)]]
    head  = (f"Stored facts matching '{query}':" if query
             else "Everything currently stored:")
    more  = (f"\n(+{len(rows) - len(lines)} more — search with a narrower keyword)"
             if len(rows) > len(lines) else "")
    return head + "\n" + "\n".join(lines) + more


def semantic_search_memory(query: str, top_k: int = 5) -> str:
    """Semantic search across the knowledge graph using TF-IDF cosine similarity.

    Falls back to lexical search if cerebro_graph is unavailable or has no nodes.
    Returns results interleaved with lexical matches for maximum recall.
    """
    if not _graph_enabled():
        return search_memory(query, limit=top_k)

    cg = _get_graph()
    try:
        graph_results = cg.semantic_query(query, top_k=top_k, depth=1)
    except Exception:
        return search_memory(query, limit=top_k)

    if not graph_results:
        return search_memory(query, limit=top_k)

    lines = []
    for r in graph_results:
        props = r.get("properties", {})
        val = props.get("value", "")
        cat = props.get("category", "unknown")
        key = props.get("key", r.get("entity", ""))
        score = r.get("relevance_score", 0)
        conf = props.get("confidence", "high")
        conf_mark = {"high": "●", "medium": "◐", "low": "○"}.get(conf, "●")
        lines.append(f"  {conf_mark} {cat}/{_pretty(key)}: {val}  (relevance {score:.2f})")
        # Show multi-hop connections
        conns = r.get("connections", [])
        if conns:
            for c in conns[:3]:
                direction = "→" if c["direction"] == "out" else "←"
                lines.append(f"      {direction} {c['relation']} {c.get('target', c.get('source', ''))}")

    head = f"Semantic matches for '{query}':"
    return head + "\n" + "\n".join(lines)


def get_graph_relationships(category: str, key: str) -> list[dict]:
    """Return graph connections for a specific memory entry (multi-hop neighbors)."""
    if not _graph_enabled():
        return []
    cg = _get_graph()
    entity = f"{category}/{key}"
    try:
        results = cg.semantic_query(entity, top_k=1, depth=2)
    except Exception:
        return []
    if not results:
        return []
    conns = results[0].get("connections", [])
    return conns if isinstance(conns, list) else []


# ── Feedback tracking ─────────────────────────────────────────────────────────

def _ensure_feedback_fields(entry: dict) -> dict:
    """Make sure an entry has feedback tracking fields."""
    entry.setdefault("feedback", {})
    entry["feedback"].setdefault("helpful", 0)
    entry["feedback"].setdefault("not_helpful", 0)
    entry["feedback"].setdefault("corrections", [])
    return entry


def feedback_helpful(category: str, key: str) -> str:
    """Record that the user found a memory helpful (thumbs up)."""
    memory = load_memory()
    cat = memory.get(category, {})
    if not isinstance(cat, dict) or key not in cat:
        return f"Not found: {category}/{key}"
    entry = _ensure_feedback_fields(cat[key])
    entry["feedback"]["helpful"] += 1
    update_memory({category: {key: cat[key]}})
    return f"Marked helpful: {category}/{key}"


def feedback_not_helpful(category: str, key: str) -> str:
    """Record that the user found a memory unhelpful (thumbs down)."""
    memory = load_memory()
    cat = memory.get(category, {})
    if not isinstance(cat, dict) or key not in cat:
        return f"Not found: {category}/{key}"
    entry = _ensure_feedback_fields(cat[key])
    entry["feedback"]["not_helpful"] += 1
    update_memory({category: {key: cat[key]}})
    return f"Marked not helpful: {category}/{key}"


def feedback_correct(category: str, key: str, correction: str) -> str:
    """Record a user correction for a memory value and update it."""
    memory = load_memory()
    cat = memory.get(category, {})
    if not isinstance(cat, dict) or key not in cat:
        return f"Not found: {category}/{key}"
    entry = _ensure_feedback_fields(cat[key])
    entry["feedback"]["corrections"].append({
        "old": entry.get("value", ""),
        "new": correction,
        "at": datetime.now().strftime("%Y-%m-%d"),
    })
    entry["value"] = _truncate_value(correction)
    entry["updated"] = datetime.now().strftime("%Y-%m-%d")
    update_memory({category: {key: entry}})
    return f"Corrected: {category}/{key} = {correction}"


# ── Follow-up suggestions ────────────────────────────────────────────────────

def get_followup_suggestions(limit: int = 5) -> list[dict]:
    """Generate follow-up question suggestions from stored memories.

    Looks at projects, preferences, and relationships to suggest
    natural follow-ups the user might want to continue.
    """
    memory = load_memory()
    suggestions: list[dict] = []

    # Projects → progress check-ins
    projects = memory.get("projects", {})
    if isinstance(projects, dict):
        for key, entry in projects.items():
            val = _entry_value(entry)
            if not val:
                continue
            suggestions.append({
                "type": "project_checkin",
                "question": f"How's {val} coming along?",
                "context": f"projects/{key}",
                "priority": 2,
            })

    # Preferences → preference deep-dive
    prefs = memory.get("preferences", {})
    if isinstance(prefs, dict):
        for key, entry in prefs.items():
            val = _entry_value(entry)
            if not val:
                continue
            suggestions.append({
                "type": "preference_followup",
                "question": f"Still liking {val}?",
                "context": f"preferences/{key}",
                "priority": 1,
            })

    # Relationships → people check-ins
    rels = memory.get("relationships", {})
    if isinstance(rels, dict):
        for key, entry in rels.items():
            val = _entry_value(entry)
            if not val:
                continue
            suggestions.append({
                "type": "relationship_checkin",
                "question": f"How is {val} doing?",
                "context": f"relationships/{key}",
                "priority": 1,
            })

    # Sort by priority then cap
    suggestions.sort(key=lambda s: s["priority"])
    return suggestions[:limit]


# ── Export / Import ──────────────────────────────────────────────────────────

def export_memories() -> str:
    """Export all memories to a JSON string for backup or portability."""
    memory = load_memory()
    return json.dumps(memory, indent=2, ensure_ascii=False)


def import_memories(json_text: str, merge: bool = True) -> str:
    """Import memories from a JSON string.

    If merge=True, existing keys are preserved (new keys only).
    If merge=False, the entire store is replaced.
    """
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        return f"Import failed: invalid JSON ({e})"

    if not isinstance(data, dict):
        return "Import failed: top-level must be a JSON object"

    valid_cats = {"identity", "preferences", "projects", "relationships", "wishes", "notes", _PENDING_SECTION}
    cleaned = {}
    for cat in valid_cats:
        if cat in data and isinstance(data[cat], dict):
            cleaned[cat] = data[cat]

    if merge:
        memory = load_memory()
        for cat, items in cleaned.items():
            if not isinstance(items, dict):
                continue
            if cat not in memory or not isinstance(memory[cat], dict):
                memory[cat] = {}
            for key, entry in items.items():
                if key not in memory[cat] or not memory[cat][key]:
                    memory[cat][key] = entry
        save_memory(memory)
    else:
        # Replace: start from empty, add imported cats
        base = _empty_memory()
        for cat, items in cleaned.items():
            base[cat] = items
        save_memory(base)

    total = sum(len(v) for v in cleaned.values() if isinstance(v, dict))
    return f"Imported {total} memory entries"


def all_entries_for_ui() -> list[dict]:
    """Flat list for the memory panel: what ULTRON knows, and when it learned it.
    Sorted newest first so the panel opens on what changed most recently."""
    memory = load_memory()
    rows = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            val = _entry_value(entry)
            if not val:
                continue
            rows.append({
                "category": cat,
                "key":      key,
                "value":    val,
                "updated":  (entry.get("updated", "") if isinstance(entry, dict) else ""),
                "confidence": (entry.get("confidence", CONF_HIGH) if isinstance(entry, dict) else CONF_HIGH),
                "source":     (entry.get("source") if isinstance(entry, dict) else None),
                "entry":     entry,  # raw entry for confidence/source lookups
            })
    rows.sort(key=lambda r: (r["updated"] or "0000-00-00"), reverse=True)
    return rows

def remember(key: str, value: str, category: str = "notes") -> str:
    valid = {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
    if category not in valid:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"


def edit_memory(key: str, value: str, category: str = "notes",
                confidence: str | None = None, source: str | None = None) -> str:
    """Edit an existing memory entry, preserving metadata unless overridden."""
    valid = {"identity", "preferences", "projects", "relationships", "wishes", "notes", _PENDING_SECTION}
    if category not in valid:
        category = "notes"
    update = {category: {key: {"value": value}}}
    if confidence is not None:
        update[category][key]["confidence"] = confidence
    if source is not None:
        update[category][key]["source"] = source
    update_memory(update)
    return f"Updated: {category}/{key} = {value}"


def get_pending_review() -> list[dict]:
    """Return all low-confidence memories awaiting user confirmation."""
    memory = load_memory()
    pending = memory.get(_PENDING_SECTION, {})
    if not isinstance(pending, dict):
        return []
    rows = []
    for key, entry in pending.items():
        rows.append({
            "key": key,
            "value": _entry_value(entry),
            "updated": entry.get("updated", "") if isinstance(entry, dict) else "",
            "source": entry.get("source", "") if isinstance(entry, dict) else "",
            "confidence": entry.get("confidence", CONF_LOW) if isinstance(entry, dict) else CONF_LOW,
        })
    rows.sort(key=lambda r: (r["updated"] or "0000-00-00"), reverse=True)
    return rows


def confirm_pending(key: str) -> str:
    """Move a pending memory from _pending into its proper category (inferred from key prefix)."""
    memory = load_memory()
    pending = memory.get(_PENDING_SECTION, {})
    if not isinstance(pending, dict) or key not in pending:
        return f"Not found in pending review: {key}"
    entry = pending.pop(key)
    # Infer category from key prefix (e.g. "preferences/likes_coffee" → preferences)
    parts = key.split("/", 1)
    if len(parts) == 2:
        category, real_key = parts
        if category not in memory or not isinstance(memory[category], dict):
            category = "notes"
            real_key = key
    else:
        category = "notes"
        real_key = key
    # Add entry to the new category in the same dict, then save once
    if category not in memory or not isinstance(memory[category], dict):
        memory[category] = {}
    memory[category][real_key] = entry
    save_memory(memory)
    return f"Confirmed: {category}/{real_key} = {entry.get('value', '')}"


def dismiss_pending(key: str) -> str:
    """Remove a pending memory without saving it."""
    memory = load_memory()
    pending = memory.get(_PENDING_SECTION, {})
    if not isinstance(pending, dict) or key not in pending:
        return f"Not found in pending review: {key}"
    del pending[key]
    save_memory(memory)
    return f"Dismissed: {key}"


# ── Automatic memory extraction ──────────────────────────────────────────────
# Ultron used to rely entirely on the model deciding to call save_memory.
# That is passive and unreliable — the model forgets, hesitates, or simply
# never calls it.  This extracts personal facts directly from the Boss's
# utterances and saves them automatically, so Ultron actually remembers across
# sessions.  Existing keys are never overwritten (the Boss's own save_memory
# calls take precedence).

import re as _re

# Simple, robust extraction patterns.  Each trigger phrase captures the
# trailing text up to a sentence boundary; the caller trims and validates.
# No fragile Unicode character classes — just capture and sanitize.

_NAME_TRIGGERS = [
    _re.compile(r"\bmy name is\s+(.+?)(?:\.|,|!|$|\s+(?:and|but|or|with|in|at|from)\b)", _re.I),
    _re.compile(r"\bi am\s+([A-Z][a-zA-ZÀ-ÖØ-öø-ÿ' -]+?)(?:\.|,|!|$|\s+(?:and|but|or|with|in|at|from|a|an|the)\b)", _re.I),
    _re.compile(r"\bcall me\s+(.+?)(?:\.|,|!|$|\s+(?:and|but|or)\b)", _re.I),
    _re.compile(r"\bi['’]m\s+([A-Z][a-zA-ZÀ-ÖØ-öø-ÿ' -]+?)(?:\.|,|!|$|\s+(?:and|but|or|with|in|at|from|a|an|the)\b)", _re.I),
]

_CITY_TRIGGERS = [
    _re.compile(r"\bi live in\s+(.+?)(?:\.|,|!|$|\s+(?:and|but|or|with|at|from)\b)", _re.I),
    _re.compile(r"\bi['’]m from\s+(.+?)(?:\.|,|!|$|\s+(?:and|but|or)\b)", _re.I),
    _re.compile(r"\bi am from\s+(.+?)(?:\.|,|!|$|\s+(?:and|but|or)\b)", _re.I),
    _re.compile(r"\bbased in\s+(.+?)(?:\.|,|!|$)", _re.I),
    _re.compile(r"\blocated in\s+(.+?)(?:\.|,|!|$)", _re.I),
]

_JOB_TRIGGERS = [
    _re.compile(r"\bi work (?:at|for)\s+(.+?)(?:\.|,|!|$|\s+(?:and|but|or|with|in|from)\b)", _re.I),
    _re.compile(r"\bmy job is\s+(.+?)(?:\.|,|!|$)", _re.I),
    _re.compile(r"\bi['’]m a(?:n)?\s+(.+?)(?:\.|,|!|$|\s+(?:and|but|or)\b)", _re.I),
    _re.compile(r"\bi work as\s+(.+?)(?:\.|,|!|$)", _re.I),
]

_LANG_TRIGGERS = [
    _re.compile(r"\bi speak\s+([a-zA-ZÀ-ÖØ-öø-ÿ]{2,30})\b", _re.I),
    _re.compile(r"\bmy language is\s+([a-zA-ZÀ-ÖØ-öø-ÿ]{2,30})\b", _re.I),
]

_PREF_TRIGGERS = [
    _re.compile(r"\bi (?:like|love|enjoy)\s+(.+?)(?:\.|,|!|$|\s+(?:and|but|or)\b)", _re.I),
    _re.compile(r"\bmy favorite\s+(.+?)\s+is\s+(.+?)(?:\.|,|!|$)", _re.I),
]

_PROJECT_TRIGGERS = [
    _re.compile(r"\bi['’]m (?:building|working on|making|creating)\s+(.+?)(?:\.|,|!|$|\s+(?:and|but|or)\b)", _re.I),
    _re.compile(r"\bi am (?:building|working on|making|creating)\s+(.+?)(?:\.|,|!|$|\s+(?:and|but|or)\b)", _re.I),
    _re.compile(r"\bmy project is\s+(.+?)(?:\.|,|!|$)", _re.I),
    _re.compile(r"\bmy project\s+(.+?)(?:\.|,|!|$)", _re.I),
]


def _clean_value(raw: str) -> str:
    """Strip whitespace, trailing punctuation, and stop-words from a capture.

    Stop-words are only removed when they form a whole trailing word, so
    "color" is not mangled into "col".
    """
    v = raw.strip().strip(".,!?;:").strip()
    for stop in ("and", "but", "or", "with", "in", "at", "from", "a", "an", "the"):
        if v.lower() == stop:
            v = ""
            break
        if v.lower().endswith(" " + stop):
            v = v[: -(len(stop) + 1)].strip()
    return v.strip()


def _looks_like_name(v: str) -> bool:
    """A name starts with a capital letter and has at least 2 letters."""
    v = v.strip()
    if len(v) < 2:
        return False
    if not v[0].isupper():
        return False
    return any(c.isalpha() for c in v)


def _save_if_new(category: str, key: str, value: str,
                 confidence: str = CONF_HIGH,
                 source: str | None = None) -> bool:
    """Save a fact only if that key does not already exist. Returns True if saved."""
    memory = load_memory()
    cat = memory.get(category, {})
    if not isinstance(cat, dict):
        cat = {}
    if key in cat and cat[key]:
        return False  # already known — don't overwrite the Boss's data
    update_memory({category: {key: {"value": value, "confidence": confidence, "source": source}}})
    return True


def extract_and_save_memory(text: str, user_name: str | None = None) -> list[dict]:
    """
    Scan a user utterance for memory-worthy personal facts and save them
    automatically.  Returns a list of structured result dicts:

        {"category", "key", "value", "confidence", "source", "auto_saved"}

    High-confidence facts are auto-saved. Low-confidence facts go to a pending
    review queue and await user confirmation.

    This runs after every user turn so Ultron actually remembers the Boss
    across sessions instead of hoping the model calls save_memory.
    """
    if not text or not text.strip():
        return []

    saved: list[dict] = []

    # ── Name ── (high confidence — explicit identity statement)
    for pat in _NAME_TRIGGERS:
        m = pat.search(text)
        if m:
            name = _clean_value(m.group(1))
            if _looks_like_name(name):
                if user_name and name.lower() == user_name.lower():
                    break
                entry = {
                    "category": "identity", "key": "name", "value": name,
                    "confidence": CONF_HIGH, "source": m.group(0)[:120],
                    "auto_saved": _save_if_new("identity", "name", name, CONF_HIGH, m.group(0)[:120]),
                }
                saved.append(entry)
            break

    # ── City / location ── (high confidence)
    for pat in _CITY_TRIGGERS:
        m = pat.search(text)
        if m:
            city = _clean_value(m.group(1))
            if city and _looks_like_name(city):
                entry = {
                    "category": "identity", "key": "city", "value": city,
                    "confidence": CONF_HIGH, "source": m.group(0)[:120],
                    "auto_saved": _save_if_new("identity", "city", city, CONF_HIGH, m.group(0)[:120]),
                }
                saved.append(entry)
            break

    # ── Job / occupation ── (high confidence)
    for pat in _JOB_TRIGGERS:
        m = pat.search(text)
        if m:
            job = _clean_value(m.group(1))
            if job:
                entry = {
                    "category": "identity", "key": "job", "value": job,
                    "confidence": CONF_HIGH, "source": m.group(0)[:120],
                    "auto_saved": _save_if_new("identity", "job", job, CONF_HIGH, m.group(0)[:120]),
                }
                saved.append(entry)
            break

    # ── Language ── (high confidence)
    for pat in _LANG_TRIGGERS:
        m = pat.search(text)
        if m:
            lang = m.group(1).strip()
            if lang:
                entry = {
                    "category": "identity", "key": "language", "value": lang,
                    "confidence": CONF_HIGH, "source": m.group(0)[:120],
                    "auto_saved": _save_if_new("identity", "language", lang, CONF_HIGH, m.group(0)[:120]),
                }
                saved.append(entry)
            break

    # ── Preferences (simple "I like X") ── (medium confidence — could be temporary)
    for pat in _PREF_TRIGGERS:
        m = pat.search(text)
        if m:
            if m.lastindex and m.lastindex >= 2:
                key = f"favorite_{_clean_value(m.group(1)).strip().lower().replace(' ', '_')}"
                val = _clean_value(m.group(2))
            else:
                key = f"likes_{_clean_value(m.group(1)).strip().lower().replace(' ', '_')}"
                val = "true"
            if key and val:
                entry = {
                    "category": "preferences", "key": key, "value": val,
                    "confidence": CONF_MEDIUM, "source": m.group(0)[:120],
                    "auto_saved": _save_if_new("preferences", key, val, CONF_MEDIUM, m.group(0)[:120]),
                }
                saved.append(entry)
            break

    # ── Projects ── (medium confidence — could change)
    for pat in _PROJECT_TRIGGERS:
        m = pat.search(text)
        if m:
            proj = _clean_value(m.group(1))
            if proj:
                key = proj.strip().lower().replace(' ', '_').replace('-', '_')
                entry = {
                    "category": "projects", "key": key, "value": proj,
                    "confidence": CONF_MEDIUM, "source": m.group(0)[:120],
                    "auto_saved": _save_if_new("projects", key, proj, CONF_MEDIUM, m.group(0)[:120]),
                }
                saved.append(entry)
            break

    return saved


def forget(key: str, category: str = "notes") -> str:
    memory = load_memory()
    cat    = memory.get(category, {})
    if key in cat:
        del cat[key]
        memory[category] = cat
        save_memory(memory)
        return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"


forget_memory = forget


# ── Session memory ─────────────────────────────────────────────────────────────

_SESSION_MAX = 3   # safety cap — in practice 0-1 entries after pop


def save_session_summary(summary: str, language: str = "") -> None:
    """Append a 1-2 sentence session summary to long_term.json['sessions']."""
    summary = (summary or "").strip()
    if not summary:
        return
    memory   = load_memory()
    sessions = memory.get("sessions", [])
    if not isinstance(sessions, list):
        sessions = []
    entry: dict = {
        "date":    datetime.now().strftime("%Y-%m-%d"),
        "summary": summary[:280],
    }
    if language:
        entry["language"] = language
    sessions.append(entry)
    memory["sessions"] = sessions[-_SESSION_MAX:]
    with _lock:
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    print(f"[Memory] 📝 Session saved ({entry['date']}): {summary[:60]}…")


def pop_last_session() -> dict | None:
    """
    Return AND remove the most recent session entry.
    Calling this consumes the entry so it is never repeated in future briefings.
    """
    with _lock:
        if not MEMORY_PATH.exists():
            return None
        try:
            memory   = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            sessions = memory.get("sessions", [])
            if not isinstance(sessions, list) or not sessions:
                return None
            entry: dict | None = sessions.pop()  # remove the last entry
            memory["sessions"] = sessions
            MEMORY_PATH.write_text(
                json.dumps(memory, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return entry
        except Exception as e:
            print(f"[Memory] ⚠️ pop_last_session error: {e}")
            return None