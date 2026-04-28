# API Provider Configuration

Generated: 2026-04-16

## Role in the System

API keys are the overflow/reliability channel. Browser automation
is the primary evaluation channel during interactive use.
API access activates when browser automation is unavailable, for
enterprise reliability needs, or for pre-authorized autonomous operations.

## Setup Rule

When a user provides an API key for a provider, ALL available models
from that provider are registered in routing-config.json by default.
Users can disable or remove models they don't want. It is easier to
delete than to discover and add.

## Configured Providers

### Anthropic (Claude)
- Status: Verified
- Credential store key: ora/anthropic-api-key
- Models registered:
  - Claude Opus 4.6 (premium tier) — strongest analytical capability
  - Claude Sonnet 4.6 (mid tier) — current-gen balanced
  - Claude Sonnet 4.5 (mid tier) — previous-gen balanced
  - Claude Haiku 4.5 (fast tier) — speed-optimized, low cost
  - Claude 3 Opus (mid tier) — previous-gen flagship
  - Claude 3.5 Sonnet (fast tier) — previous-gen balanced, very capable
  - Claude 3.5 Haiku (fast tier) — previous-gen speed, very low cost

### OpenAI (GPT)
- Status: Verified
- Credential store key: ora/openai-api-key
- Models registered:
  - GPT-4o (mid tier) — capable general-purpose
  - GPT-4 Turbo (mid tier) — previous-gen flagship
  - GPT-4o Mini (fast tier) — speed-optimized, very low cost
  - GPT-3.5 Turbo (fast tier) — legacy, extremely low cost

### Google (Gemini)
- Status: Verified
- Credential store key: ora/gemini-api-key
- Models registered:
  - Gemini 2.5 Pro (premium tier) — flagship, highest capability
  - Gemini 2.5 Flash (fast tier) — extremely low cost, good capability
  - Gemini 1.5 Pro (mid tier) — previous-gen flagship
  - Gemini 1.5 Flash (fast tier) — previous-gen speed

## Evaluation Fallback Chain

1. Local models (primary — zero cost, hardware-bound)
2. Browser automation (uses existing subscriptions)
3. API premium-tier: Claude Opus 4.6, Gemini 2.5 Pro (strongest)
4. API mid-tier: Claude Sonnet 4.6, GPT-4o, Gemini 1.5 Pro (overflow)
5. API fast-tier: Claude Haiku 4.5, GPT-4o Mini, Gemini 2.5 Flash (backup)
6. Local-only mode (no external evaluation — quality warnings applied)

## Operational Context Rules

- Interactive work: all channels available (local, browser, API)
- Autonomous overnight: local only by default. API available if
  explicitly pre-authorized in the task specification.
- Agent operations: local + fast API tier by default.
- Browser automation: prohibited during unattended work (sessions
  may expire and require human interaction to re-authenticate).

## Updating Keys

To update or replace a key, tell your AI:
"Read and execute Framework — API Key Acquisition.md"
and select the provider you want to update.

## Adding Browser Automation Connections

To add or reconnect browser automation:
"Read and execute Framework — Browser Evaluation Setup.md"
