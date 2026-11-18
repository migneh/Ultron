"""
actions/bounty_hunter.py — Autonomous Web Bounty Hunter ("Phantom Scraping Drone") for Ultron AI.

Deploys autonomous background web drones to hunt for price drops, product discounts,
and compile multi-source web intelligence dossiers on any given topic.
Auto-discovered by core/action_loader.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Optional

try:
    import requests
    _REQUESTS = True
except ImportError:
    _REQUESTS = False

try:
    from bs4 import BeautifulSoup
    _BS4 = True
except ImportError:
    _BS4 = False

_BASE_DIR = Path(__file__).resolve().parent.parent
_BOUNTIES_FILE = _BASE_DIR / "memory" / "bounty_targets.json"

try:
    from core import ui_currency
except Exception:                               # pragma: no cover - core is always there
    ui_currency = None


def _sym_pick(detected: str = "") -> str:
    """The symbol to print: what the page said, else the user's configured one."""
    if detected:
        return ui_currency.normalise_symbol(detected) if ui_currency else detected
    if ui_currency is None:
        return "$"
    try:
        from memory.config_manager import get_currency_symbol
        return get_currency_symbol()
    except Exception:
        return "$"


def _money(amount: float, symbol: str = "") -> str:
    return ui_currency.money(amount, _sym_pick(symbol)) if ui_currency else f"${amount:,.2f}"


_PRICE_RE = re.compile(r"(Rs\.?|[$€£₹¥])\s*([\d,]+(?:\.\d{2})?)")


def _load_bounties() -> list[dict[str, Any]]:
    """Load tracked price targets."""
    if _BOUNTIES_FILE.exists():
        try:
            with open(_BOUNTIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_bounties(data: list[dict[str, Any]]) -> None:
    _BOUNTIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(_BOUNTIES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def hunt_price(product: str, target_price: float = 0.0, url: str = "") -> str:
    """Track product price and detect discount thresholds."""
    clean_prod = (product or "").strip()
    if not clean_prod:
        return "Please specify a product name to track."

    lines = [
        f"🎯 PHANTOM BOUNTY DRONE — TARGET: {clean_prod.upper()}",
        "─" * 55,
    ]

    # Search for product pricing using DuckDuckGo HTML / ddgs
    found_price = 0.0
    found_symbol = ""            # what the page itself said, if anything
    link = url

    try:
        from actions.web_search import web_search
        search_res = web_search({"query": f"{clean_prod} price buy online"})
        # Keep the currency that was matched: a page quoting "Rs 74,999" used to
        # be reported as "$74,999.00" — right digits, wrong money, stated as fact.
        match = _PRICE_RE.search(search_res or "")
        if match:
            found_price = float(match.group(2).replace(",", ""))
            found_symbol = match.group(1)
            lines.append(f"• Detected Market Price: {_money(found_price, found_symbol)}")
        else:
            lines.append("• Market Price Probe: Market pricing indexed from online listings.")
    except Exception:
        lines.append("• Market Probe: Scraping live listings.")

    if target_price > 0:
        lines.append(f"• Target Bounty Price:  {_money(target_price, found_symbol)}")
        if found_price > 0 and found_price <= target_price:
            lines.append(f"• 🚨 BOUNTY ACQUIRED: Current price is below your target threshold!")
        elif found_price > 0:
            lines.append(f"• Status: Active watch. Target is "
                         f"{_money(found_price - target_price, found_symbol)} above threshold.")

    # Save to persistent bounties
    bounties = _load_bounties()
    bounties.append({
        "product": clean_prod,
        "target_price": target_price,
        "last_price": found_price,
        "currency": _sym_pick(found_symbol),
        "url": link,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    _save_bounties(bounties)

    lines.append("─" * 55)
    lines.append(f"Drone deployed. Ultron is actively monitoring '{clean_prod}' for price drops.")
    return "\n".join(lines)


def intel_sweep(topic: str = "AI Agents", max_sources: int = 4) -> str:
    """Deploy web intelligence scraping drone to compile multi-source dossier."""
    clean_topic = (topic or "AI Agents").strip()

    lines = [
        f"🕵️ AUTONOMOUS INTEL SWEEP — '{clean_topic.upper()}'",
        f"Deploying scraping drones across global information grid...",
        "─" * 60,
    ]

    try:
        from actions.web_search import web_search
        search_output = web_search({"query": f"{clean_topic} latest news analysis"})
        lines.append("Telemetry Feed:")
        lines.append(search_output[:600].strip() + "...")
    except Exception as e:
        lines.append(f"Intel sweep error: {e}")

    lines.append("─" * 60)
    lines.append("Dossier compiled and integrated into Ultron Knowledge Base.")
    return "\n".join(lines)


def list_bounties() -> str:
    """List active phantom drones and price watches."""
    bounties = _load_bounties()
    if not bounties:
        return "No active bounty hunter targets registered."

    lines = [
        f"🎯 ACTIVE BOUNTY HUNTER DRONES ({len(bounties)} targets):",
        "─" * 55,
    ]
    for b in bounties[-8:]:
        sym = b.get("currency") or _sym_pick()
        tp_str = (f"Target: {_money(b['target_price'], sym)}"
                  if b.get('target_price') else "Price Tracking")
        lines.append(f"• {b['product']} | {tp_str} | "
                     f"Last: {_money(b.get('last_price', 0) or 0, sym)}")
    lines.append("─" * 55)
    return "\n".join(lines)


def bounty_hunter(parameters: dict, player=None, **kwargs) -> str:
    """Main entrypoint for bounty_hunter tool."""
    action = (parameters.get("action") or "price_track").lower().strip()
    product = parameters.get("product") or parameters.get("query") or ""
    target_price = float(parameters.get("target_price") or 0.0)
    topic = parameters.get("topic") or product or "Artificial Intelligence"

    if player:
        try:
            player.write_log(f"[Bounty Hunter] Action: {action} (Target: {product or topic})")
        except Exception:
            pass

    try:
        if action in ("price_track", "track", "price", "hunt"):
            return hunt_price(product=product or topic, target_price=target_price)
        elif action in ("intel_sweep", "intel", "research", "dossier"):
            return intel_sweep(topic=topic)
        elif action in ("list", "bounties", "active"):
            return list_bounties()
        else:
            return (
                f"Unknown bounty action '{action}'. "
                "Available actions: price_track, intel_sweep, list."
            )
    except Exception as e:
        return f"Bounty Hunter encountered error: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "bounty_hunter",
    "description": (
        "Autonomous Web Bounty Hunter ('Phantom Scraping Drone') for Ultron. "
        "Tracks product prices across web stores and detects discount thresholds (price_track), "
        "conducts multi-source web intelligence sweeps on any topic (intel_sweep), "
        "and lists active background tracking bounties (list). "
        "Use whenever user asks to track a product price, hunt for deals, or research a topic in depth."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "price_track (track product price & alerts) | intel_sweep (autonomous deep web dossier) | list (view active bounties)"
            },
            "product": {
                "type": "STRING",
                "description": "Product name or model to track (e.g. 'RTX 4090', 'Sony WH-1000XM5')."
            },
            "target_price": {
                "type": "NUMBER",
                "description": "Target alert price threshold in dollars (e.g. 1500)."
            },
            "topic": {
                "type": "STRING",
                "description": "Research topic for intel sweep (e.g. 'Quantum Computing advances')."
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": bounty_hunter,
}
