# API Key Setup Framework

## Display Name
API Key Setup

## Display Description
Help the user add an external API provider — open the right signup / key page, store the key securely in the system keychain, and confirm it works. Covers OpenRouter (strongly recommended but optional), eligible direct PAYG AI vendors, OpenRouter-served Meta/NVIDIA access, web search (Tavily, Brave, Exa), model intelligence (Artificial Analysis), economic data (FRED), transcription, speech, and image providers.

*Guided, conversational setup for a non-technical user.*

---

## PURPOSE

Most people should set keys directly in **Settings → External APIs** — that panel lists every provider in two columns, links straight to each key console, validates the key format as you type, and verifies where possible when **Save** is pressed. Run this framework when the user wants a hand walking through it conversationally, or asks you to set a provider up for them.

The live provider catalogue, signup and console URLs, key prefixes, and activation metadata live in one place in code — `orchestrator/provider_registry.py`. Settings reads that registry at runtime. This framework summarizes it for the conversational path but is not itself code-generated, so when details disagree the live Settings row and registry are authoritative.

The catalogue below covers Ora's built-in providers. A loaded trusted first-party
feature may add its own provider row at startup without a built-in catalogue edit;
use that live Settings row for its console and activation details. The feature can
read only the named credential in its own accepted declaration, while Settings
continues to return presence rather than the value.

Ora runs with no external keys when local models are configured, and the installer can complete with no keys. Keys are optional add-ons. **OpenRouter** is the practical gateway to commercial and hosted open-weight models (one key, hundreds of models), so recommend it early, but do not describe it as a hard install prerequisite. Free OpenRouter models are rate-limited and sometimes unavailable; paid models require credits/payment.

## HOW KEYS ARE USED

- **OpenRouter** — the gateway. One key reaches almost every model, and is the simplest way to move beyond free/local capacity.
- **Eligible direct PAYG vendors** — after the key is saved **and the Models registry is refreshed**, the vendor's own `/models` catalogue becomes authoritative for that vendor. Ora creates exact native direct endpoints and avoids OpenRouter's ~5.5% markup on those routes. Native authoritative endpoints do not promise an automatic same-model OpenRouter retry; the configured model fallback chain owns availability. Eligible today: Anthropic, OpenAI, Google Gemini, xAI, Mistral, DeepSeek, Qwen, Moonshot, MiniMax, and Xiaomi.
- **Meta and NVIDIA** — their current individual programs do not provide the same self-serve PAYG contract, so the default authoritative build keeps their models OpenRouter-served. Saving these keys does not convert the Models menu to native direct routes.
- **Flag-off fallback** — with `ORA_VENDOR_CATALOG_AUTHORITATIVE=0`, the OpenRouter inventory stays primary and the catalogue-aware `ORA_PREFER_DIRECT` path can try the exact same model directly, then reactively fall back to OpenRouter on error. `ORA_PREFER_DIRECT=0` disables that runtime rewrite; legacy OpenAI/Anthropic/Gemini direct endpoints already generated from stored keys remain direct until the endpoint universe is regenerated without those keys.
- **Auto-activating keys** — search (Tavily/Brave/Exa), Artificial Analysis, and FRED turn on from key presence with no separate toggle. Direct-vendor model keys still require the registry refresh boundary above.
- **Explicit-choice keys** — transcription (AssemblyAI/Deepgram), speech (ElevenLabs), and image (Stability/Replicate/Tensor.Art) only take effect when you also select that provider in the relevant Settings tab — local Whisper / macOS say are free defaults and are never silently overridden.

## STORAGE CONVENTION

Every key lives in the system keychain under service `ora`, using the registry's `keyring_username` (generally `<provider>-api-key`; e.g. `ora/openrouter-api-key`, `ora/deepseek-api-key`, with `ora/aa-api-key` for Artificial Analysis). The Settings panel and `set_api_key()` write there; never store a key in a plaintext file or echo it into a log.

---

## NAMED FAILURE MODES

**The One-Chance Key Trap:** most providers show a new key exactly once. Warn the user to copy it before leaving the page — twice: once before opening the page, once at the generation step. If lost, they generate a new one (the old one is invalidated).

**The Sticker-Shock Trap:** the credit-card prompt panics people. Set expectations first: paid model APIs are pay-per-use and vary by use; the cheapest models can be very inexpensive, but users should expect usage-based billing instead of a fixed subscription. Search providers often offer free tiers or credits, then usage-based plans. Artificial Analysis has a free model-benchmark API with commercial data separately. FRED remains free but is not part of the public install recommendation.

**The Wrong-Page Trap:** layouts change. Tell the user *what* to look for ("a section called API Keys / Developer console"), not just buttons. Use the key page from the table below.

**The Key-Format Trap:** users paste whitespace, quotes, or a partial key. Trim it, and sanity-check the prefix in the table. Prefixes are a hint, not a hard gate — store what the user insists on.

---

## PROVIDER CATALOGUE

Each row: provider — key page · expected key prefix · activation.
`direct after refresh` = eligible for the default vendor-authoritative menu after a Models refresh. `OpenRouter-served` = the key does not replace the model menu under the current individual-access contract. `auto` = on when the key is present. `choice` = also pick it in the matching Settings tab.

### Gateway
- **OpenRouter** — https://openrouter.ai/settings/keys · `sk-or-` · auto · **strongly recommended for broad hosted model access**

### US AI providers
- **Anthropic (Claude)** — https://platform.claude.com/settings/keys · `sk-ant-` · direct after refresh
- **OpenAI** — https://platform.openai.com/api-keys · `sk-` · direct after refresh (same key serves chat, vision, OpenAI TTS)
- **Google Gemini** — https://aistudio.google.com/app/apikey · `AIza` · direct after refresh (free tier in AI Studio)
- **xAI (Grok)** — https://console.x.ai/team/default/api-keys · `xai-` · direct after refresh
- **Meta (Llama API)** — https://llama.developer.meta.com/api-keys · `LLM|` · OpenRouter-served (waitlisted free preview; no individual PAYG)
- **NVIDIA NIM** — https://build.nvidia.com/settings/api-keys · `nvapi-` · OpenRouter-served (free dev key; no individual PAYG)
- **Mistral AI** — https://console.mistral.ai/api-keys · (opaque) · direct after refresh

### Chinese AI providers
- **DeepSeek** — https://platform.deepseek.com/api_keys · `sk-` · direct after refresh
- **Alibaba Qwen (DashScope)** — https://modelstudio.console.alibabacloud.com/?tab=playground#/api-key · `sk-` · direct after refresh (international endpoint)
- **Moonshot AI (Kimi)** — https://platform.kimi.ai/console/api-keys · `sk-` · direct after refresh (international endpoint)
- **MiniMax** — https://platform.minimax.io/user-center/basic-information/interface-key · `eyJ` · direct after refresh (international endpoint)
- **Xiaomi (MiMo)** — https://platform.xiaomimimo.com/#/console/api-keys · `sk-` · direct after refresh

### Web search (free tiers; auto-activate)
- **Tavily** — https://app.tavily.com/home · `tvly-` · auto (keyword cascade tier 1)
- **Brave Search** — https://api-dashboard.search.brave.com/app/keys · (opaque) · auto (cascade tier 2; subscribe the Free plan)
- **Exa** — https://dashboard.exa.ai/api-keys · (UUID) · auto (semantic search tier)

### Model intelligence & data (free; auto-activate)
- **Artificial Analysis** — https://artificialanalysis.ai/api-key-management-redirect · (bearer) · auto (live model intelligence; optional installer recommendation, improves model selector)
- **FRED (St. Louis Fed)** — https://fredaccount.stlouisfed.org/apikeys · (32-char hex) · auto (economic time-series; specialized, not part of the public install recommendation)

### Transcription · speech · image (choice — also select in Settings)
- **AssemblyAI** — https://www.assemblyai.com/dashboard/api-keys · transcription
- **Deepgram** — https://console.deepgram.com/ · transcription
- **ElevenLabs** — https://elevenlabs.io/app/settings/api-keys · `sk_` · speech
- **Stability AI** — https://platform.stability.ai/account/keys · `sk-` · image (pay-per-image)
- **Replicate** — https://replicate.com/account/api-tokens · `r8_` · image / video
- **Tensor.Art** — https://tams.tensor.art/apps · image

---

## STEPS

1. **Offer the panel first.** "The quickest way is Settings → External APIs — it links straight to each provider's key page, and Save verifies where possible. Want to do it there, or shall I walk you through it here?"
2. **Pick the provider.** If they're just starting, recommend the install starter package: **OpenRouter + Tavily + Artificial Analysis**. If they already use an eligible PAYG vendor and want native routing, set that vendor's key and plan a Models refresh after storage.
3. **Open the key page** for the chosen provider (table above). Deliver the One-Chance-Key warning. For paid model vendors, set cost expectations before the card prompt.
4. **Receive and clean the key** — trim whitespace and surrounding quotes; sanity-check the prefix; warn (don't block) if it looks off.
5. **Verify** — the panel's Save button performs the cheapest available verification before storage. In a guided flow, make the same cheapest authenticated call. A confirmed 401/403 rejection stops here; providers with no free probe and transient network failures are explicitly inconclusive. Image/TTS providers have no free verification call, so first use confirms them.
6. **Store** — after a success or disclosed inconclusive result, write the key to the system keychain under service `ora` and the provider registry's username. Confirm presence without echoing the value.
7. **Confirm activation.** Search/data auto-activating keys are live from key presence. For an eligible model vendor, open Models and press ↻ to rebuild the native inventory, endpoints, aliases, and presets; confirm the expected rows show **DIRECT**. Transcription/speech/image keys need the matching Settings selection or capability slot.

---

## RECOVERY

- **Key page closed before copying:** generate a new key; the old one is dead.
- **Confirmed authentication rejection:** do not store the key; recopy it, check account/billing state, and retry. A 429 means the key is valid but rate-limited or over quota. An inconclusive network result may be stored with the uncertainty disclosed; local models cover the gap.
- **User stops partway:** store whatever was completed; they can rerun this anytime or finish in Settings → External APIs.

---

*End of API Key Setup Framework v2.2 — simplified, registry-driven, inline-UI-first.*

**VERSION HISTORY**

v2.2 (2026/07/12): Corrected provider and routing claims for the default-on vendor-authoritative architecture. Direct PAYG keys take effect at the Models refresh boundary; native authoritative endpoints do not promise automatic same-model OpenRouter fallback; Meta/NVIDIA remain OpenRouter-served under their current individual-access contracts; panel Save is verify-before-store with explicit inconclusive handling.

v2.1 (2026/06/16): Reconciled with the source installer. OpenRouter is strongly recommended but optional, the install starter package is OpenRouter + Tavily + Artificial Analysis, FRED is explicitly specialized/non-public-install, and cost language now distinguishes free tiers/credits from usage-based plans instead of implying all search/model-intelligence keys are simply free.

v2.0 (2026/06/14): Rewritten to match the all-encompassing External APIs settings panel. Provider catalogue, signup and console URLs, prefixes, and activation behaviour are now sourced from `orchestrator/provider_registry.py` (single source of truth) and surfaced inline in the panel (signup links, console links, format validation, Verify button) — so this framework is the conversational fallback, not the primary path. Added the full provider set (OpenRouter gateway; direct US + Chinese AI vendors with markup-bypass routing; auto-activating search / model-intelligence / economic-data keys; explicit-choice transcription / speech / image). Collapsed the prior 7-layer PFF scaffolding to a short STEPS + RECOVERY flow appropriate to a UI-assisted task. Kept the four key-safety traps.

v1.5 (2026/05/29): Added Tavily / Brave / Exa / Artificial Analysis free-tier keys; normalised keychain naming to `service="ora", username="<provider>-api-key"`.

v1.4 (2026/05/10): Keychain naming normalised (Stability / Replicate moved to the canonical pattern).

v1.3 (2026/04/29): Added image-generation providers (Stability, Replicate) and split the cost regimes.

v1.3 (2026/05/16): Subscription / browser-automation path removed; API keys positioned as the commercial-AI channel.

v1.2 (2026/04/23): Added self-evaluation + error-correction layers (since removed in v2.0).

v1.1 (2026/03/24): Overflow/reliability framing (since superseded).

v1.0 (2026/03/23): Initial version.
