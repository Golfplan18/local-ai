# API Key Acquisition Framework

This framework sets up API keys for commercial AI services as the overflow/reliability channel.

## When to Use

- Browser automation is throttled or sessions have expired
- Enterprise users who want guaranteed SLAs
- Autonomous tasks that need API access pre-authorized
- Primary channel if browser automation is unavailable

## Supported Services

- **Anthropic (Claude)** — console.anthropic.com
- **OpenAI (ChatGPT/GPT-4)** — platform.openai.com
- **Google (Gemini)** — aistudio.google.com

## Instructions

Tell your AI: "I want to add an API key for [service]."

The AI will:
1. Open the API key page in your browser
2. Guide you through creating a key
3. Store it securely in your macOS Keychain
4. Register the endpoint in endpoints.json

## Manual Setup

To store a key manually, tell your AI:
"Store my [Anthropic/OpenAI/Google] API key: [your-key-here]"

The key will be stored via keyring (macOS Keychain) — never written to a plain text file.
