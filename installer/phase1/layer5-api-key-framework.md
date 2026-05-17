### PHASE 1, LAYER 5: API KEY FRAMEWORK INSTALLATION

**Stage Focus:** Install the API Key Acquisition Framework so it is ready when the reader sets up commercial AI access.

### Processing Instructions

1. Verify the API Key Acquisition Framework exists at `[workspace]/frameworks/book/api-key-setup.md` (installed from the Git repository).
2. IF the repository was not available and a placeholder was created, THEN generate the API Key Acquisition Framework directly at `[workspace]/frameworks/api-key-setup.md`. The framework content is specified in the companion document "API Key Acquisition Framework."
3. No API keys are collected at this time. The framework is installed but not executed. API keys are the commercial-AI access channel — direct vendor APIs (Anthropic, OpenAI, Google) and OpenRouter. The reader activates the framework when they want to wire commercial models into the routing buckets.

### Model Registration Rule

When a user provides an API key for any provider, **all available models** from that provider are registered in `routing-config.json` automatically. The canonical model list is defined in `config/api-model-registry.json`. Users can disable or remove models they don't want from the Model Configuration panel.

**Rationale:** It is easier to delete what you don't need than to discover and add what you didn't know existed. Default to everything.

For each model added:
1. Create an endpoint entry in `routing-config.json` with the provider's credential key, appropriate tier, and standard capabilities.
2. Add the endpoint ID to the corresponding bucket (`premium`, `mid`, `fast`) in the `buckets` section.
3. Set `enabled: true` and `status: "active"` — the user can disable from the UI.

---

