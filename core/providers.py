"""
core/providers.py — the one list of AI providers, and the rules that go with it.

Before this module the list existed in three shapes at once: a dropdown in
`ui.py`, a `_PROVIDER_KEY_FIELDS` map in `memory/config_manager.py`, and the
branch structure of `core/llm_client.py`. Anything that had to know which
providers exist — the setup screen, the settings panel, the doctor — re-derived
that knowledge, and the copies drifted (the setup screen could offer a provider
the client could not speak to, and store its key under a name nothing read).

What lives here:
  * PROVIDERS        — name, curated models, default model, key label/placeholder,
                       whether a base URL is needed, and where to get a key
  * KEY_FIELDS       — where each provider's key is stored in config/api_keys.json
  * REALTIME         — the providers that can drive a Gemini-style live voice
                       session; everything else talks through the unified loop

Pure data and pure functions: no file I/O, no network, no Qt. Every decision
that needs to be tested can be tested here without a UI or an API key.
"""

from __future__ import annotations

PROVIDERS: dict[str, dict] = {
    "gemini": {
        "name": "Google Gemini",
        "models": [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-live-preview",
            "gemini-2.5-pro",
        ],
        "default_model": "gemini-2.5-flash",
        "key_label": "GEMINI API KEY",
        "key_placeholder": "AIzaSy...",
        "has_url": False,
        "default_url": "",
    },
    "ollama": {
        "name": "Ollama (Local / Offline)",
        "models": [
            "llama3.2",
            "llama3.3",
            "deepseek-r1",
            "qwen2.5",
            "mistral",
            "phi4",
            "gemma2",
            "codellama",
        ],
        "default_model": "llama3.2",
        "key_label": "API KEY (OPTIONAL)",
        "key_placeholder": "Leave blank for local Ollama",
        "has_url": True,
        "url_label": "OLLAMA SERVER URL",
        "default_url": "http://localhost:11434",
    },
    "gpt": {
        "name": "OpenAI (GPT)",
        "models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4.5-preview",
            "o3-mini",
            "o1",
            "gpt-4-turbo",
        ],
        "default_model": "gpt-4o",
        "key_label": "OPENAI API KEY",
        "key_placeholder": "sk-proj-...",
        "has_url": False,
        "default_url": "https://api.openai.com/v1",
    },
    "nvidia_nim": {
        "name": "NVIDIA NIM",
        "models": [
            "meta/llama-3.3-70b-instruct",
            "deepseek-ai/deepseek-r1",
            "meta/llama-3.1-405b-instruct",
            "nvidia/nemotron-4-340b-instruct",
            "mistralai/mistral-large-2-instruct",
        ],
        "default_model": "meta/llama-3.3-70b-instruct",
        "key_label": "NVIDIA NIM API KEY",
        "key_placeholder": "nvapi-...",
        "has_url": True,
        "url_label": "NIM BASE URL",
        "default_url": "https://integrate.api.nvidia.com/v1",
    },
    "opencode_zen": {
        "name": "OpenCode Zen",
        "models": [
            "opencode/zen-coder-34b",
            "qwen/qwen-2.5-coder-32b-instruct",
            "deepseek/deepseek-coder",
            "meta-llama/llama-3.3-70b-instruct",
        ],
        "default_model": "opencode/zen-coder-34b",
        "key_label": "OPENCODE ZEN API KEY",
        "key_placeholder": "sk-...",
        "has_url": True,
        "url_label": "BASE URL",
        "default_url": "https://api.opencode.zen/v1",
    },
    "claude": {
        "name": "Anthropic Claude",
        "models": [
            "claude-3-7-sonnet-20250219",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ],
        "default_model": "claude-3-7-sonnet-20250219",
        "key_label": "ANTHROPIC API KEY",
        "key_placeholder": "sk-ant-...",
        "has_url": False,
        "default_url": "https://api.anthropic.com/v1",
    },
    "deepseek": {
        "name": "DeepSeek",
        "models": [
            "deepseek-chat",
            "deepseek-reasoner",
        ],
        "default_model": "deepseek-chat",
        "key_label": "DEEPSEEK API KEY",
        "key_placeholder": "sk-...",
        "has_url": True,
        "url_label": "DEEPSEEK BASE URL",
        "default_url": "https://api.deepseek.com",
    },
    "groq": {
        "name": "Groq (Ultra-Fast)",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "deepseek-r1-distill-llama-70b",
            "mixtral-8x7b-32768",
        ],
        "default_model": "llama-3.3-70b-versatile",
        "key_label": "GROQ API KEY",
        "key_placeholder": "gsk_...",
        "has_url": False,
        "default_url": "https://api.groq.com/openai/v1",
    },
    "openrouter": {
        "name": "OpenRouter / Custom",
        "models": [
            "meta-llama/llama-3.3-70b-instruct",
            "anthropic/claude-3.5-sonnet",
            "deepseek/deepseek-r1",
            "google/gemini-2.5-flash",
            "openai/gpt-4o",
        ],
        "default_model": "meta-llama/llama-3.3-70b-instruct",
        "key_label": "API KEY",
        "key_placeholder": "sk-or-...",
        "has_url": True,
        "url_label": "BASE URL",
        "default_url": "https://openrouter.ai/api/v1",
    },
}


# ── Where each provider's key is stored in api_keys.json ─────────────────────
# The setup screen and the settings panel both write through these names, and
# get_provider_key() reads through them, so writer and reader cannot drift again.
KEY_FIELDS: dict[str, str] = {
    "gemini":       "gemini_api_key",
    "gpt":          "openai_api_key",
    "claude":       "anthropic_api_key",
    "nvidia_nim":   "nvidia_api_key",
    "opencode_zen": "opencode_api_key",
    "deepseek":     "deepseek_api_key",
    "groq":         "groq_api_key",
    "openrouter":   "openrouter_api_key",
}

# Providers that can hold a realtime voice session. Gemini Live is the only one
# implemented; the rest speak through the local speech loop (STT → provider →
# edge-tts), which is why this is a set of one rather than a per-provider flag.
REALTIME: frozenset[str] = frozenset({"gemini"})

# Where to send someone who asks "how do I get a key".
DOCS: dict[str, str] = {
    "gemini":       "https://aistudio.google.com/app/apikey",
    "gpt":          "https://platform.openai.com/api-keys",
    "claude":       "https://console.anthropic.com/settings/keys",
    "deepseek":     "https://platform.deepseek.com/api_keys",
    "groq":         "https://console.groq.com/keys",
    "openrouter":   "https://openrouter.ai/keys",
    "nvidia_nim":   "https://build.nvidia.com/",
    "opencode_zen": "https://opencode.ai/",
    "ollama":       "https://ollama.com/download",
}

# Names people and models actually type, mapped to the canonical id.
ALIASES: dict[str, str] = {
    "google":       "gemini",
    "google gemini": "gemini",
    "openai":       "gpt",
    "chatgpt":      "gpt",
    "anthropic":    "claude",
    "nvidia":       "nvidia_nim",
    "nim":          "nvidia_nim",
    "opencode":     "opencode_zen",
    "zen":          "opencode_zen",
    "local":        "ollama",
    "llama":        "ollama",
}

DEFAULT_PROVIDER = "gemini"


def normalise(name: str | None) -> str:
    """Canonical provider id for whatever the user (or a model) wrote."""
    key = str(name or "").strip().lower()
    if not key:
        return DEFAULT_PROVIDER
    if key in PROVIDERS:
        return key
    return ALIASES.get(key, key)


def get(name: str | None) -> dict:
    """The catalogue entry for a provider. Unknown names get an empty entry."""
    return PROVIDERS.get(normalise(name), {})


def exists(name: str | None) -> bool:
    return normalise(name) in PROVIDERS


def names() -> list[str]:
    return list(PROVIDERS)


def label(name: str | None) -> str:
    return get(name).get("name") or normalise(name)


def models(name: str | None) -> list[str]:
    """Curated models. A custom name is always allowed — this is a menu, not a cage."""
    return list(get(name).get("models") or [])


def default_model(name: str | None) -> str:
    entry = get(name)
    return entry.get("default_model") or (entry.get("models") or [""])[0]


def key_field(name: str | None) -> str:
    return KEY_FIELDS.get(normalise(name), f"{normalise(name)}_api_key")


def needs_key(name: str | None) -> bool:
    """Ollama runs locally and needs no key; every other provider does."""
    return normalise(name) != "ollama"


def needs_url(name: str | None) -> bool:
    return bool(get(name).get("has_url"))


def default_url(name: str | None) -> str:
    return get(name).get("default_url") or ""


def is_realtime(name: str | None) -> bool:
    """Can this provider hold a live voice session, or must it use the local loop?"""
    return normalise(name) in REALTIME


def docs_url(name: str | None) -> str:
    return DOCS.get(normalise(name), "")


def resolve_model(name: str | None, model: str | None) -> str:
    """The model to actually send: the user's choice, or the provider default.

    Guards against the two ways an empty model reached the API: a blank string
    from a config file and the literal "default" that once stood in for one.
    """
    chosen = str(model or "").strip()
    if not chosen or chosen.lower() in ("default", "none", "null"):
        return default_model(name)
    return chosen


def session_choice(configured_provider: str | None,
                   configured_model: str | None,
                   provider_override: str | None = None,
                   model_override: str | None = None) -> tuple[str, str]:
    """What to actually run this session, given optional command-line overrides.

    `ultron --provider ollama` must not inherit Gemini's model name: a provider
    the user only named for this run comes with its own default unless they also
    said `--model`. Neither override rewrites the config file — a one-off launch
    should not silently become the saved setting.
    """
    base_provider = normalise(configured_provider)
    if provider_override:
        chosen_provider = normalise(provider_override)
        chosen_model = (model_override if (model_override or "").strip()
                        else default_model(chosen_provider))
    else:
        chosen_provider = base_provider
        chosen_model = model_override or configured_model

    return chosen_provider, resolve_model(chosen_provider, chosen_model)


def apply_choice(provider: str | None, model: str | None,
                 previous_provider: str | None = None) -> dict:
    """What must happen after the user picks a provider/model.

    Returned to the caller rather than acted on here, so the rule can be tested
    without a UI: a Gemini Live session carries the model inside an open audio
    stream and has to reconnect, while every other provider is asked for a model
    per utterance — the next sentence already uses the new one.
    """
    chosen = normalise(provider)
    if not exists(chosen):
        return {"ok": False, "reconnect": False, "provider": chosen, "model": "",
                "message": f"Unknown provider '{provider}' — nothing was saved."}

    resolved = resolve_model(chosen, model)
    reconnect = is_realtime(chosen) or is_realtime(previous_provider)
    message = (f"Switching to {label(chosen)} ({resolved}) — reconnecting the voice session."
               if reconnect else
               f"Using {label(chosen)} ({resolved}) from your next sentence.")
    return {"ok": True, "reconnect": reconnect, "provider": chosen,
            "model": resolved, "message": message}
