### PHASE 1, LAYER 5: API KEY FRAMEWORK INSTALLATION

**Stage Focus:** Install the API Key Setup Framework, then prompt the reader for the four free-tier enrichment keys that meaningfully improve Ora's default behavior. Commercial / paid API keys stay deferred until the reader chooses to wire them.

### Processing Instructions

1. Verify the API Key Setup Framework exists at `[workspace]/frameworks/book/api-key-setup.md` (installed from the Git repository).
2. IF the repository was not available and a placeholder was created, THEN generate the API Key Setup Framework directly at `[workspace]/frameworks/api-key-setup.md`. The framework content is specified in the companion document "API Key Setup Framework."
3. **Commercial / paid API keys** (Anthropic, OpenAI, Google, OpenRouter, Stability AI, Replicate) are NOT collected at install time. The framework is installed but not executed for these providers. The reader activates the framework when they want to wire commercial models into the routing buckets — via the V3 settings panel "+ Add new provider" button or by telling the AI "Read and execute frameworks/api-key-setup.md".
4. **Free-tier enrichment keys** ARE collected at install time. The four providers below all offer free tiers and meaningfully improve default behavior (search cascade reliability and live model-metadata) without billing exposure. Run the API Key Setup Framework's Layers 2–4 for each provider the reader opts into.

   For each provider in [Tavily, Brave, Exa, Artificial Analysis]:
   - Present the provider's one-line framing from the Layer 1 menu (options 9, 10, 11, 12 respectively).
   - Ask: "Would you like to set up [provider] now? (free, recommended)"
   - IF the reader says yes, THEN invoke the API Key Setup Framework Layers 2–4 for that provider (browser_open → key entry → store under `service="ora", username="<provider>-api-key"` → verification ping).
   - IF the reader says no, THEN continue to the next provider. Do not re-prompt at install time; the reader can configure later via the framework.

   IF the reader declines all four, present a one-line summary: "No problem. Ora will use DDG search (the keyless cascade tail) and scrape-based model metadata as defaults. You can add any of these keys later by telling the AI 'Read and execute frameworks/api-key-setup.md'."

   **Why these four are install-time prompts:** Each one is free-tier, materially improves default behavior, and has no billing exposure to surprise a first-boot reader. Tavily and Brave activate Tiers 1 and 2 of the web-search cascade (DDG is the keyless tail). Exa registers as a cascade provider but is opt-in to the cascade order — collecting the key at install lets the reader enable it later by editing one config field. Artificial Analysis supersedes a public-page scrape that breaks when the site changes layout, so the live API path is meaningfully more reliable for the automated model selector.

### Model Registration Rule

When a user provides an API key for any provider, **all available models** from that provider are registered in `routing-config.json` automatically. The canonical model list is defined in `config/api-model-registry.json`. Users can disable or remove models they don't want from the Model Configuration panel.

**Rationale:** It is easier to delete what you don't need than to discover and add what you didn't know existed. Default to everything.

For each model added:
1. Create an endpoint entry in `routing-config.json` with the provider's credential key, appropriate tier, and standard capabilities.
2. Add the endpoint ID to the corresponding bucket (`premium`, `mid`, `fast`) in the `buckets` section.
3. Set `enabled: true` and `status: "active"` — the user can disable from the UI.

---

