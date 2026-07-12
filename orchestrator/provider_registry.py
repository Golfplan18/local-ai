"""Provider registry — single source of truth for external API providers.

Every external service Ora can talk to is declared exactly once here:
its display label, category, where its key lives in the keyring, which
env var consumers read, the signup / key-console URLs the settings panel
links to, the key-format hint used for inline validation, and — for the
LLM providers — the dispatch metadata used to build eligible vendors'
native endpoint universe after a registry refresh and by the OpenRouter-first
prefer-direct fallback when authoritative mode is disabled.

Consumers
---------
* ``orchestrator/user_settings.py`` — builds the keyring-username map, the
  labelled display order, and the enriched per-provider status rows the
  settings panel renders.
* ``orchestrator/boot.py`` — (a) bridges every stored key into its
  conventional env var at boot; (b) the generic ``openai_compatible``
  dispatch branch reads ``base_url`` here; (c) the flag-off *prefer-direct*
  rewrite
  maps an OpenRouter ``vendor/model`` id back to the vendor's own API via
  ``or_prefix`` when that vendor's key is present.
* ``server/server.py`` — ``/api/settings`` returns the enriched rows;
  ``/api/settings/api-key/verify`` uses ``base_url`` + auth to ping.
* ``scripts/sync_model_registry.py`` — AA path auto-derives from key
  presence.
* ``server/static/settings-panel.js`` — renders the two-column grouped
  UI purely from the server payload (no metadata duplicated in JS).
* ``scripts/build_vendor_authoritative_registry.py`` and
  ``scripts/sync_endpoints_from_catalog.py`` — select keyed, self-serve PAYG
  vendors and build their native model inventory/endpoints.

Design rules
------------
* Keys live ONLY in the system keyring (service ``ora``, username
  ``<keyring_username>``). Nothing here stores a secret.
* ``auto_activate`` providers need no separate enable toggle. Key presence is
  the enable signal, although model-menu and endpoint changes take effect on
  the next registry refresh rather than at key-save time.
* Adding a provider is a one-entry edit here; no consumer needs touching
  for the key to be storable, linkable, and bridged-to-env. Eligible
  OpenAI-compatible PAYG vendors also enter the authoritative direct-routing
  build automatically.
"""
from __future__ import annotations

# Machine category → display group header (render order).
GROUP_ORDER = [
    ("gateway",       "Gateway"),
    ("llm_us",        "US AI providers"),
    ("llm_cn",        "Chinese AI providers"),
    ("search",        "Web search"),
    ("metadata",      "Model intelligence"),
    ("econ",          "Economic data"),
    ("transcription", "Transcription"),
    ("tts",           "Text-to-speech"),
    ("image",         "Image & video"),
]

# Each entry:
#   id              stable provider id (also the keyring username stem)
#   label           UI display name
#   category        machine category (see GROUP_ORDER)
#   keyring_username keyring account under service "ora"
#   env_var         conventional env var consumers read (bridged at boot); None = no bridge
#   signup_url      where a new user creates an account
#   console_url     exact page to create / manage the key
#   key_prefix      literal key prefix for the inline format hint (None = opaque)
#   essential       True only for a provider that blocks install if missing
#   auto_activate   True when key-presence alone engages the provider
#   dispatch        None | "native" | "openai_compatible"  (LLM direct-call style)
#   native_service  service id for the native branch in boot.py (when dispatch="native")
#   base_url        OpenAI-compatible base URL (when dispatch="openai_compatible")
#   or_prefix       OpenRouter vendor segment, for the prefer-direct rewrite
#   verifiable      True when /api/settings/api-key/verify can cheaply confirm the key
#   note            one-line UI hint
#
# Metadata verified 2026-06-14 against each provider's official docs
# (research + adversarial second-source pass).
PROVIDERS: list[dict] = [
    # ── Gateway ───────────────────────────────────────────────────────────
    {
        "id": "openrouter", "label": "OpenRouter", "category": "gateway",
        "keyring_username": "openrouter-api-key", "env_var": "OPENROUTER_API_KEY",
        "signup_url": "https://openrouter.ai/",
        "console_url": "https://openrouter.ai/settings/keys",
        "key_prefix": "sk-or-", "essential": False, "auto_activate": True,
        "dispatch": None, "native_service": None,
        "base_url": "https://openrouter.ai/api/v1", "or_prefix": None,
        "verifiable": True,
        "note": "Strongly recommended. One key → 300+ models; free models are rate-limited and sometimes unavailable. Direct-vendor keys below bypass its ~5.5% markup.",
    },

    # ── US AI providers (direct) ─────────────────────────────────────────
    {
        "id": "anthropic", "label": "Anthropic (Claude)", "category": "llm_us",
        "keyring_username": "anthropic-api-key", "env_var": "ANTHROPIC_API_KEY",
        "signup_url": "https://platform.claude.com",
        "console_url": "https://platform.claude.com/settings/keys",
        "key_prefix": "sk-ant-", "essential": False, "auto_activate": True,
        "dispatch": "native", "native_service": "claude",
        "base_url": None, "or_prefix": "anthropic", "verifiable": True,
        "note": "Native Messages API (keeps prompt caching).",
    },
    {
        "id": "openai", "label": "OpenAI", "category": "llm_us",
        "keyring_username": "openai-api-key", "env_var": "OPENAI_API_KEY",
        "signup_url": "https://platform.openai.com/signup",
        "console_url": "https://platform.openai.com/api-keys",
        "key_prefix": "sk-", "essential": False, "auto_activate": True,
        "dispatch": "native", "native_service": "openai",
        "base_url": "https://api.openai.com/v1", "or_prefix": "openai", "verifiable": True,
        "note": "Same key serves chat, vision, and OpenAI TTS.",
    },
    {
        "id": "gemini", "label": "Google Gemini", "category": "llm_us",
        "keyring_username": "gemini-api-key", "env_var": "GEMINI_API_KEY",
        "signup_url": "https://aistudio.google.com/",
        "console_url": "https://aistudio.google.com/app/apikey",
        "key_prefix": "AIza", "essential": False, "auto_activate": True,
        "dispatch": "native", "native_service": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "or_prefix": "google", "verifiable": True,
        "note": "Free tier available in Google AI Studio.",
    },
    {
        "id": "xai", "label": "xAI Grok", "category": "llm_us",
        "keyring_username": "xai-api-key", "env_var": "XAI_API_KEY",
        "signup_url": "https://console.x.ai/",
        "console_url": "https://console.x.ai/team/default/api-keys",
        "key_prefix": "xai-", "essential": False, "auto_activate": True,
        "dispatch": "openai_compatible", "native_service": None,
        "base_url": "https://api.x.ai/v1", "or_prefix": "x-ai", "verifiable": True,
        "note": "OpenAI-compatible.",
    },
    {
        "id": "meta", "label": "Meta Llama", "category": "llm_us",
        "direct_payg": False,  # Llama API is a waitlisted free preview, no self-serve PAYG
        "keyring_username": "meta-api-key", "env_var": "LLAMA_API_KEY",
        "signup_url": "https://llama.developer.meta.com/",
        "console_url": "https://llama.developer.meta.com/api-keys",
        "key_prefix": "LLM|", "essential": False, "auto_activate": True,
        "dispatch": "openai_compatible", "native_service": None,
        "base_url": "https://api.llama.com/compat/v1/", "or_prefix": "meta-llama",
        "verifiable": True,
        "note": "Llama API is a waitlisted free preview (no pay-as-you-go) — Llama models are served via OpenRouter.",
    },
    {
        "id": "nvidia", "label": "NVIDIA NIM", "category": "llm_us",
        "direct_payg": False,  # free key is trivial, but no individual pay-as-you-go path
        "keyring_username": "nvidia-api-key", "env_var": "NVIDIA_API_KEY",
        "signup_url": "https://build.nvidia.com/",
        "console_url": "https://build.nvidia.com/settings/api-keys",
        "key_prefix": "nvapi-", "essential": False, "auto_activate": True,
        "dispatch": "openai_compatible", "native_service": None,
        "base_url": "https://integrate.api.nvidia.com/v1", "or_prefix": "nvidia",
        "verifiable": True,
        "note": "Free dev key, but no individual pay-as-you-go — these models are served via OpenRouter.",
    },
    {
        "id": "mistral", "label": "Mistral AI", "category": "llm_us",
        "keyring_username": "mistral-api-key", "env_var": "MISTRAL_API_KEY",
        "signup_url": "https://console.mistral.ai/",
        "console_url": "https://console.mistral.ai/api-keys",
        "key_prefix": None, "essential": False, "auto_activate": True,
        "dispatch": "openai_compatible", "native_service": None,
        "base_url": "https://api.mistral.ai/v1", "or_prefix": "mistralai",
        "verifiable": True, "note": "OpenAI-compatible.",
    },

    # ── Chinese AI providers (direct) ────────────────────────────────────
    {
        "id": "deepseek", "label": "DeepSeek", "category": "llm_cn",
        "keyring_username": "deepseek-api-key", "env_var": "DEEPSEEK_API_KEY",
        "signup_url": "https://platform.deepseek.com/sign_up",
        "console_url": "https://platform.deepseek.com/api_keys",
        "key_prefix": "sk-", "essential": False, "auto_activate": True,
        "dispatch": "openai_compatible", "native_service": None,
        "base_url": "https://api.deepseek.com/v1", "or_prefix": "deepseek",
        "verifiable": True, "note": "OpenAI-compatible.",
    },
    {
        "id": "qwen", "label": "Alibaba Qwen", "category": "llm_cn",
        "keyring_username": "qwen-api-key", "env_var": "DASHSCOPE_API_KEY",
        "signup_url": "https://www.alibabacloud.com/en/product/modelstudio",
        "console_url": "https://modelstudio.console.alibabacloud.com/?tab=playground#/api-key",
        "key_prefix": "sk-", "essential": False, "auto_activate": True,
        "dispatch": "openai_compatible", "native_service": None,
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "or_prefix": "qwen", "verifiable": True,
        "note": "International DashScope endpoint, OpenAI-compatible.",
    },
    {
        "id": "moonshot", "label": "Moonshot Kimi", "category": "llm_cn",
        "keyring_username": "moonshot-api-key", "env_var": "MOONSHOT_API_KEY",
        "signup_url": "https://platform.kimi.ai",
        "console_url": "https://platform.kimi.ai/console/api-keys",
        "key_prefix": "sk-", "essential": False, "auto_activate": True,
        "dispatch": "openai_compatible", "native_service": None,
        "base_url": "https://api.moonshot.ai/v1", "or_prefix": "moonshotai",
        "verifiable": True, "note": "International endpoint, OpenAI-compatible.",
    },
    {
        "id": "minimax", "label": "MiniMax", "category": "llm_cn",
        "keyring_username": "minimax-api-key", "env_var": "MINIMAX_API_KEY",
        "signup_url": "https://platform.minimax.io/login",
        "console_url": "https://platform.minimax.io/user-center/basic-information/interface-key",
        "key_prefix": "eyJ", "essential": False, "auto_activate": True,
        "dispatch": "openai_compatible", "native_service": None,
        "base_url": "https://api.minimax.io/v1", "or_prefix": "minimax",
        "verifiable": True, "note": "International endpoint, OpenAI-compatible.",
    },
    {
        "id": "xiaomi", "label": "Xiaomi MiMo", "category": "llm_cn",
        "keyring_username": "xiaomi-api-key", "env_var": "XIAOMI_MIMO_API_KEY",
        "signup_url": "https://platform.xiaomimimo.com/",
        "console_url": "https://platform.xiaomimimo.com/#/console/api-keys",
        "key_prefix": "sk-", "essential": False, "auto_activate": True,
        "dispatch": "openai_compatible", "native_service": None,
        "base_url": "https://api.xiaomimimo.com/v1", "or_prefix": "xiaomi",
        "verifiable": True, "note": "OpenAI-compatible.",
    },

    # ── Web search (auto-activate via cascade) ───────────────────────────
    {
        "id": "tavily", "label": "Tavily", "category": "search",
        "keyring_username": "tavily-api-key", "env_var": "TAVILY_API_KEY",
        "signup_url": "https://app.tavily.com/",
        "console_url": "https://app.tavily.com/home",
        "key_prefix": "tvly-", "essential": False, "auto_activate": True,
        "dispatch": None, "native_service": None, "base_url": None, "or_prefix": None,
        "verifiable": True, "note": "Cascade tier 1. Free ~1,000/mo.",
    },
    {
        "id": "brave", "label": "Brave", "category": "search",
        "keyring_username": "brave-api-key", "env_var": "BRAVE_API_KEY",
        "signup_url": "https://api-dashboard.search.brave.com/register",
        "console_url": "https://api-dashboard.search.brave.com/app/keys",
        "key_prefix": None, "essential": False, "auto_activate": True,
        "dispatch": None, "native_service": None, "base_url": None, "or_prefix": None,
        "verifiable": True, "note": "Cascade tier 2. Free ~2,000/mo (subscribe Free plan).",
    },
    {
        "id": "exa", "label": "Exa", "category": "search",
        "keyring_username": "exa-api-key", "env_var": "EXA_API_KEY",
        "signup_url": "https://dashboard.exa.ai/",
        "console_url": "https://dashboard.exa.ai/api-keys",
        "key_prefix": None, "essential": False, "auto_activate": True,
        "dispatch": None, "native_service": None, "base_url": None, "or_prefix": None,
        "verifiable": True, "note": "Auto-engages as a semantic search tier when its key is present.",
    },

    # ── Model intelligence ───────────────────────────────────────────────
    {
        "id": "artificial_analysis", "label": "Artificial Analysis", "category": "metadata",
        "keyring_username": "aa-api-key", "env_var": "AA_API_KEY",
        "signup_url": "https://artificialanalysis.ai/",
        "console_url": "https://artificialanalysis.ai/api-key-management-redirect",
        "key_prefix": None, "essential": False, "auto_activate": True,
        "dispatch": None, "native_service": None, "base_url": None, "or_prefix": None,
        "verifiable": True,
        "note": "Free. Present ⇒ Ora uses the API for model intelligence instead of scraping.",
    },

    # ── Economic data ────────────────────────────────────────────────────
    {
        "id": "fred", "label": "FRED", "category": "econ",
        "keyring_username": "fred-api-key", "env_var": "FRED_API_KEY",
        "signup_url": "https://fredaccount.stlouisfed.org/login/secure/",
        "console_url": "https://fredaccount.stlouisfed.org/apikeys",
        "key_prefix": None, "essential": False, "auto_activate": True,
        "dispatch": None, "native_service": None, "base_url": None, "or_prefix": None,
        "verifiable": True, "note": "Free. Economic time-series for charts / analyses.",
    },

    # ── Transcription (explicit provider choice; not silent default) ─────
    {
        "id": "assemblyai", "label": "AssemblyAI", "category": "transcription",
        "keyring_username": "assemblyai-api-key", "env_var": "ASSEMBLYAI_API_KEY",
        "signup_url": "https://www.assemblyai.com/dashboard/signup",
        "console_url": "https://www.assemblyai.com/dashboard/api-keys",
        "key_prefix": None, "essential": False, "auto_activate": False,
        "dispatch": None, "native_service": None, "base_url": None, "or_prefix": None,
        "verifiable": False, "note": "Select under Transcription to use.",
    },
    {
        "id": "deepgram", "label": "Deepgram", "category": "transcription",
        "keyring_username": "deepgram-api-key", "env_var": "DEEPGRAM_API_KEY",
        "signup_url": "https://console.deepgram.com/signup",
        "console_url": "https://console.deepgram.com/",
        "key_prefix": None, "essential": False, "auto_activate": False,
        "dispatch": None, "native_service": None, "base_url": None, "or_prefix": None,
        "verifiable": False, "note": "Select under Transcription to use.",
    },

    # ── Text-to-speech ───────────────────────────────────────────────────
    {
        "id": "elevenlabs", "label": "ElevenLabs", "category": "tts",
        "keyring_username": "elevenlabs-api-key", "env_var": "ELEVENLABS_API_KEY",
        "signup_url": "https://elevenlabs.io/sign-up",
        "console_url": "https://elevenlabs.io/app/settings/api-keys",
        "key_prefix": "sk_", "essential": False, "auto_activate": False,
        "dispatch": None, "native_service": None, "base_url": None, "or_prefix": None,
        "verifiable": False, "note": "Select under Speech to use.",
    },

    # ── Image & video ────────────────────────────────────────────────────
    {
        "id": "stability", "label": "Stability AI", "category": "image",
        "keyring_username": "stability-api-key", "env_var": "STABILITY_API_KEY",
        "signup_url": "https://platform.stability.ai",
        "console_url": "https://platform.stability.ai/account/keys",
        "key_prefix": "sk-", "essential": False, "auto_activate": False,
        "dispatch": None, "native_service": None, "base_url": None, "or_prefix": None,
        "verifiable": False, "note": "Image fallback. Pay-per-image.",
    },
    {
        "id": "replicate", "label": "Replicate", "category": "image",
        "keyring_username": "replicate-api-key", "env_var": "REPLICATE_API_TOKEN",
        "signup_url": "https://replicate.com/signin",
        "console_url": "https://replicate.com/account/api-tokens",
        "key_prefix": "r8_", "essential": False, "auto_activate": False,
        "dispatch": None, "native_service": None, "base_url": None, "or_prefix": None,
        "verifiable": False, "note": "Long-tail image / video model host.",
    },
    {
        "id": "tensorart", "label": "Tensor.Art", "category": "image",
        "keyring_username": "tensorart-api-key", "env_var": "TENSORART_API_KEY",
        "signup_url": "https://tensor.art/",
        "console_url": "https://tams.tensor.art/apps",
        "key_prefix": None, "essential": False, "auto_activate": False,
        "dispatch": None, "native_service": None, "base_url": None, "or_prefix": None,
        "verifiable": False, "note": "Image generation.",
    },
]

# ── derived lookups ──────────────────────────────────────────────────────

_BY_ID = {p["id"]: p for p in PROVIDERS}


def by_id(provider_id: str) -> dict | None:
    return _BY_ID.get(provider_id)


def provider_ids() -> list[str]:
    return [p["id"] for p in PROVIDERS]


def keyring_username_map() -> dict[str, str]:
    """{provider_id: keyring username under service 'ora'}."""
    return {p["id"]: p["keyring_username"] for p in PROVIDERS}


def labels_map() -> dict[str, str]:
    """{provider_id: display label} in registry (display) order."""
    return {p["id"]: p["label"] for p in PROVIDERS}


def env_bridge_pairs() -> list[tuple[str, str]]:
    """[(env_var, keyring_username)] for every provider declaring an env var.

    Used at boot to mirror keyring secrets into the env vars that SDKs and
    the existing dispatch branches read (keyring stays canonical; env is a
    convenience copy, never overwriting a value already set in the env).
    """
    return [(p["env_var"], p["keyring_username"]) for p in PROVIDERS if p.get("env_var")]


def direct_llm_providers() -> list[dict]:
    """Entries that can be called directly as an LLM (native or compat)."""
    return [p for p in PROVIDERS if p.get("dispatch")]


def catalog_authoritative_providers() -> list[dict]:
    """LLM providers whose own catalogue should be authoritative when keyed.

    Excludes vendors with no real self-serve pay-as-you-go path (Meta's
    waitlisted free preview, NVIDIA NIM's free-key-but-no-individual-PAYG) —
    those stay served via OpenRouter. ``direct_payg`` defaults True.
    """
    return [p for p in PROVIDERS
            if p.get("dispatch") and p.get("direct_payg", True)]


def or_prefix_map() -> dict[str, dict]:
    """{openrouter_vendor_prefix: provider entry} for the prefer-direct rewrite."""
    return {p["or_prefix"]: p for p in PROVIDERS if p.get("or_prefix")}


def validate_key_format(provider_id: str, value: str) -> tuple[bool, str]:
    """Lenient format check. Returns (looks_ok, human message).

    Non-blocking by design — mirrors Framework — API Key Setup: warn on a
    surprising shape, never refuse a key the user insists on.
    """
    v = (value or "").strip()
    p = _BY_ID.get(provider_id)
    if not p:
        return False, f"unknown provider {provider_id!r}"
    if len(v) < 12:
        return False, "That looks too short for an API key — did you copy the whole string?"
    prefix = p.get("key_prefix")
    if prefix and not v.startswith(prefix):
        return False, f"{p['label']} keys usually start with “{prefix}”. Double-check you copied the right one."
    return True, "ok"


def ui_rows() -> list[dict]:
    """Per-provider rows for the settings payload (no secrets, no presence).

    The server adds the live ``present`` boolean; the panel renders groups
    from ``category`` using GROUP_ORDER.
    """
    rows = []
    for p in PROVIDERS:
        rows.append({
            "provider": p["id"],
            "label": p["label"],
            "category": p["category"],
            "signup_url": p["signup_url"],
            "console_url": p["console_url"],
            "key_prefix": p.get("key_prefix"),
            "essential": p.get("essential", False),
            "auto_activate": p.get("auto_activate", False),
            "verifiable": p.get("verifiable", False),
            "direct": bool(p.get("dispatch")),
            "catalog_authoritative": bool(
                p.get("dispatch") and p.get("direct_payg", True)
            ),
            "note": p.get("note", ""),
        })
    return rows


__all__ = [
    "PROVIDERS", "GROUP_ORDER", "by_id", "provider_ids",
    "keyring_username_map", "labels_map", "env_bridge_pairs",
    "direct_llm_providers", "or_prefix_map", "validate_key_format", "ui_rows",
]
