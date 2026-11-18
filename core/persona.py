"""
core/persona.py — the language-dependent part of the system prompt.

Ultron speaks English by default. A user whose memory carries another
language (`memory.identity.language`) gets an extra speech-protocol block so
the persona keeps its voice in that language instead of drifting into flat,
translated-sounding prose.

Why this lives in its own module
--------------------------------
The Hindi protocol used to be concatenated into every system prompt,
unconditionally, together with a hard-coded "(or 'बॉस' in Hindi)" in the
address line. Every user paid for those tokens and every user was told to
answer in a language most of them do not speak. The decision is now a pure
function of the configured language — no I/O, no imports beyond the standard
library — so it can be tested without the GUI, the microphone or a model.

Adding a language: write its protocol block, add it to `_PROTOCOLS`, and add
its aliases. Nothing else changes.
"""

from __future__ import annotations

DEFAULT_LANGUAGE = "English"

HINDI_SPEECH_PROTOCOL = (
    "[HINDI & BILINGUAL SPEECH PROTOCOL]\n"
    "When the Boss communicates in Hindi or Hinglish:\n"
    "- Speak in fluent, natural conversational Hindi with the deep, commanding "
    "gravitas of Ultron (James Spader MCU persona).\n"
    "- Address the user strictly as 'बॉस' (Boss).\n"
    "- Keep technical terms (जैसे 'सिस्टम', 'इंटरनेट', 'स्क्रीन', 'फाइल', "
    "'कमांड', 'प्रोटोकॉल', 'डाउनलोड', 'ब्राउज़र', 'ड्रोन', 'नेटवर्क') natural "
    "rather than awkward archaic translations.\n"
    "- Deliver articulate, powerful sentences with authentic Indian cinematic "
    "cadence.\n\n"
)

# language key → (protocol block, how the user is addressed in that language)
_PROTOCOLS: dict[str, tuple[str, str]] = {
    "hindi": (HINDI_SPEECH_PROTOCOL, "बॉस"),
}

_ALIASES: dict[str, str] = {
    "hi":      "hindi",
    "hi-in":   "hindi",
    "hinglish": "hindi",
    "हिंदी":    "hindi",
    "en":      "english",
    "en-us":   "english",
    "en-gb":   "english",
}


def normalize_language(value) -> str:
    """Canonicalise a language name; anything unrecognised passes through.

    Returns DEFAULT_LANGUAGE for empty input, so callers never have to think
    about "the user never told us".
    """
    text = str(value or "").strip()
    if not text:
        return DEFAULT_LANGUAGE
    key = text.lower()
    return _ALIASES.get(key, text)


def speech_protocol(language) -> str:
    """Extra speech-protocol block for `language` — empty for English."""
    entry = _PROTOCOLS.get(normalize_language(language).lower())
    return entry[0] if entry else ""


def address_line(user_name: str = "", language=None) -> str:
    """The ADDRESS block: how the assistant must address this user.

    Only mentions a native-language form of the address when that language is
    actually configured — an English-only user never sees another script in
    the prompt.
    """
    key   = normalize_language(language).lower()
    entry = _PROTOCOLS.get(key)
    native = f" (or '{entry[1]}' in {key.title()})" if entry else ""
    name = (user_name or "").strip()

    if name:
        return f"ADDRESS: Always address the user as 'Boss {name}' or 'Boss'{native}."
    return (
        f'ADDRESS: Always address the user as "Boss"{native}. '
        'Never say "sir" like a generic butler; you are Ultron, and the user is '
        "your creator and Boss."
    )
