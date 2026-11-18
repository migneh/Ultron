"""
core/ui_currency.py — the currency symbol tools print money with.

Small on purpose, but it exists for one reason: `bounty_hunter` used to print
every price with a hard-coded "$". The price it *detected* could be in rupees —
the pattern already matched "Rs 80,000" — so "Rs 80,000" came back as
"$80,000.00": the right digits, the wrong money, presented as fact.

Two rules, both here so they are testable without the app:

  * a symbol detected in the source text always wins over the configured one;
  * an unknown or empty configuration falls back to "$".
"""

from __future__ import annotations

DEFAULT_SYMBOL = "$"

# Symbols the price parser understands, mapped to how they are printed.
_KNOWN: dict[str, str] = {
    "$": "$", "usd": "$",
    "€": "€", "eur": "€",
    "£": "£", "gbp": "£",
    "₹": "₹", "inr": "₹",
    "rs": "Rs ", "rs.": "Rs ",
    "د.ت": "DT ", "dt": "DT ",
    "dh": "DH ", "aed": "AED ",
    "¥": "¥", "jpy": "¥",
}


def normalise_symbol(raw: str | None) -> str:
    """A usable symbol for whatever was configured — never an empty string."""
    text = str(raw or "").strip()
    if not text:
        return DEFAULT_SYMBOL
    return _KNOWN.get(text.lower(), text if len(text) <= 6 else DEFAULT_SYMBOL)


def money(amount: float, symbol: str | None = None) -> str:
    """Format an amount with its symbol, thousands separated."""
    return f"{normalise_symbol(symbol)}{amount:,.2f}"


def detect_symbol(text: str) -> str:
    """The first currency marker in `text`, or "" when there is none."""
    import re
    for match in re.finditer(r"rs\.?|[$€£₹¥]|د\.ت|\b(?:usd|eur|gbp|inr|dt|dh|aed|jpy)\b",
                             str(text or ""), re.IGNORECASE):
        return normalise_symbol(match.group(0))
    return ""
