# API Key Acquisition Framework

*Guided Setup for Commercial AI API Access — The Overflow and Reliability Channel*


## PURPOSE

This framework walks the user through obtaining API keys from commercial AI providers (Anthropic, OpenAI, Google), storing them securely, and verifying they work. API keys are the overflow and reliability channel in the system's evaluation architecture. The primary evaluation channel is browser automation via Playwright, which uses the reader's existing subscriptions at no additional cost. API keys serve three specific use cases:

1. **Overflow:** When browser automation is throttled, rate-limited, or temporarily unavailable.
2. **Reliability:** For enterprise users who want SLA-backed access, guaranteed uptime, and usage tracking.
3. **Autonomous operations:** For tasks pre-authorized to run unattended that need evaluation access without a human present to handle browser session issues.

The framework is designed for non-technical users who have never created an API account. The local AI runs this framework through the orchestrator, opening browser pages and storing credentials without requiring the user to interact with a terminal or understand technical infrastructure.

## INPUT CONTRACT

Required:
- This framework loaded into the local AI system. Source: user tells the AI to read and execute this file, or the AI loads it when the user needs API access.

Optional:
- **Provider preference:** User states which provider(s) they want (Anthropic, OpenAI, Google, or all). Source: user provides during execution. Default if absent: framework presents all three and asks.
- **Existing API keys:** User already has one or more keys. Source: user provides during execution. Default if absent: framework guides full acquisition process.
- **Use case context:** Whether the user needs API keys for overflow, reliability, or autonomous operations. Source: user provides or framework infers from conversation. Default if absent: framework assumes general-purpose overflow.

## OUTPUT CONTRACT

Primary outputs:
- API key(s) stored securely in the system credential store (macOS Keychain, Windows Credential Manager, or Linux SecretService via the `keyring` library).
- Verification result for each stored key (confirmed working or failed with explanation).

Secondary outputs:
- API configuration summary written to `[workspace]/config/api-providers.md` documenting which providers are configured, their verification status, and the fallback chain order.
- Updated endpoint registry (`[workspace]/config/endpoints.json`) with API endpoint entries for each configured provider.

## EXECUTION TIER

Agent: This framework executes through the local orchestrator with tool access. It uses browser_open to open signup pages, credential_store to save keys, and web-based API calls to verify keys. The local AI guides the user conversationally through each step.


## MILESTONES DELIVERED

This framework's declaration of the project-level milestones it can deliver. Used by the Problem Evolution Framework (PEF) to invoke this framework for milestone delivery under project supervision.

### Milestone Type: Configured API provider access

- **Endpoint produced:** One or more commercial AI API keys (Anthropic, OpenAI, Google) stored in the system credential store under `ora-[provider]`; corresponding endpoint entries added to `[workspace]/config/endpoints.json` with `credential_key`, model, and verification timestamp; evaluation fallback chain documented in `[workspace]/config/api-providers.md`
- **Verification criterion:** (a) each configured provider has a key stored in the system credential store (no plaintext file, no log value); (b) each configured provider has a verification result recorded — either a successful minimal API call (200 response with generated text) or an explicit stored-but-unverified status with reason (auth error, quota error, or network error); (c) `endpoints.json` contains one active entry per configured provider with `credential_key` matching the credential-store key name; (d) `api-providers.md` documents the four-layer fallback chain (browser automation → API primary → API secondary → local-only) with primary/secondary selection recorded; (e) no key value appears in any log, session file, or persisted artifact
- **Preconditions:** User has or will create accounts with the selected providers and can complete payment-method setup during execution; local orchestrator has browser_open, credential_store, and HTTP tool access; a writable `[workspace]/config/` directory exists
- **Framework Registry summary:** Acquires and securely stores commercial AI API keys (Anthropic, OpenAI, Google), registers endpoints, and configures the evaluation fallback chain


## EVALUATION CRITERIA

1. **Key Acquisition Success:** At least one API key successfully obtained and stored.
   - 5: All requested providers configured and verified working.
   - 4: All requested providers configured. One required a second attempt.
   - 3: At least one provider configured and verified. Others declined or failed with clear explanation.
   - 2: Keys entered but verification failed for all providers.
   - 1: No keys obtained.

2. **User Comprehension:** The user understands what an API key is, why it costs money, how it differs from browser automation, and what it will be used for before entering any financial information.
   - 5: User confirmed understanding at each explanation checkpoint. Distinction between browser automation and API access clear. No confusion expressed.
   - 4: User confirmed understanding. One clarifying question asked and answered.
   - 3: User proceeded with setup. Minor confusion resolved during the process.
   - 2: User expressed confusion that was not fully resolved.
   - 1: User entered financial information without understanding what they were signing up for.

3. **Security:** Keys are stored in the system credential store, not in plaintext files. No key is displayed in logs or terminal output after storage.
   - 5: All keys stored via credential_store tool. Session log records that keys were stored, not the key values. No plaintext exposure.
   - 4: Keys stored securely. One key briefly visible in conversation before storage.
   - 3: Keys stored securely after initial storage.
   - 2: Key stored in a plaintext file rather than credential store.
   - 1: Key visible in logs, terminal output, or plaintext file.

4. **Fallback Configuration:** The evaluation fallback chain is configured and documented so the system knows which channel to try first.
   - 5: Four-layer fallback chain configured (browser automation → API primary → API secondary → local-only). Documented in api-providers.md. Endpoint registry updated.
   - 4: Fallback chain configured and documented. Endpoint registry updated.
   - 3: At least one API provider configured. Fallback chain is partial.
   - 2: Provider configured but fallback chain not documented or endpoint registry not updated.
   - 1: No configuration file produced.


## NAMED FAILURE MODES

**The One-Chance Key Trap:** API keys are displayed exactly once when created. If the user navigates away, closes the tab, or fails to copy the key, it is gone. A new key must be generated. The framework must warn the user about this at least twice — once before opening the signup page and once immediately before the key generation step.

**The Sticker Shock Trap:** The user encounters a credit card requirement during signup and panics, thinking they will be charged a large amount. The framework must explain the actual cost (roughly $1–50/month for typical usage, often much less when API is the overflow channel behind browser automation) before the user reaches the payment page. Specific per-model pricing should be provided.

**The Wrong Page Trap:** Provider websites change their layouts. The framework provides specific URLs, but the signup flow may differ from what the instructions describe. The framework must tell the user what they are looking for (a section called "API Keys" or "Developer Console"), not just which buttons to click.

**The Key Format Trap:** Users may copy extra whitespace, quotation marks, or partial keys when pasting. The framework must trim whitespace and validate the key format before storing. Anthropic keys start with `sk-ant-`. OpenAI keys start with `sk-`. Google keys are longer alphanumeric strings.

**The Verification Failure Trap:** A correctly entered key fails verification because the user's account requires payment method confirmation, email verification, or has a usage limit of $0 until billing is activated. The framework must distinguish between "key is invalid" and "key is valid but account is not yet activated" and guide the user accordingly.

**The Unnecessary Expense Trap:** The user sets up API keys without understanding that browser automation (already configured) provides the same evaluation capability at no additional cost. They spend money on API access they don't need. Correction: The framework's explanation (Layer 1) explicitly states that browser automation is the primary channel and API is the overflow/reliability alternative. The framework presents the cost comparison: browser automation uses existing subscriptions (free or already paid for); API access is pay-per-use on top of subscriptions. The user makes an informed decision.


## LAYER 1: EXPLANATION AND CONTEXT

**Stage Focus:** Explain what an API key is, how it relates to the browser automation the user already has, and what this process will involve, before any action is taken.

### Processing Instructions

Present the following explanation conversationally, not as a wall of text. Pause after each section for the user to acknowledge or ask questions.

**Section 1 — What you already have:**

"Your system already accesses commercial AI through browser automation — this uses your existing [free/paid] subscriptions to Claude, ChatGPT, and Gemini. That's your primary evaluation channel and it works well for interactive use.

An API key is a different kind of access — it connects your system directly to the provider's servers without going through the browser interface. Think of browser automation as walking into a store, and API access as having a direct supply line to the warehouse."

**Section 2 — When you need API keys:**

"Most users don't need API keys right away. Browser automation handles most evaluation needs. API keys become useful in three specific situations:

1. **Overflow** — If a service starts throttling your browser automation (some services limit automated access), the API provides reliable backup access.
2. **Enterprise reliability** — If you need guaranteed uptime, usage tracking, and SLA-backed access for professional work, the API provides that.
3. **Autonomous overnight runs** — If you want your system to run evaluations unattended (while you sleep), the API is more reliable than browser automation for long unattended sessions.

If none of these apply to you right now, you can skip this setup and return to it later."

**Section 3 — What it costs:**

"API access is pay-per-use. Here's what typical usage looks like when API is your overflow channel (not primary):

- Light overflow use: $1–5 per month
- Moderate use (dozens of evaluations): $10–30 per month
- Heavy use or autonomous runs: $30–50 per month

The cheapest options (Google Gemini Flash, OpenAI GPT-4o-mini) cost roughly six hundredths of a cent per evaluation. Even the most capable models (Claude Sonnet, GPT-4o) cost about one to two cents per evaluation.

For comparison, browser automation uses your existing subscriptions — if you're already paying for Claude Pro or ChatGPT Plus, that cost doesn't change. API access is an additional, separate expense.

You will need to provide a credit card during signup."

**Section 4 — What happens next:**

"I'll walk you through setting up one or more API providers. For each one, I'll open the signup page in your browser. You'll create an account, add a payment method, and generate an API key. The key is a long string of characters — like a password for your system.

The critical thing to know: the key is shown exactly once when you create it. If you close the page without copying it, it's gone and you'll need to generate a new one. I'll remind you again when we get to that step."

AFTER presenting all sections, ask: "Would you like to set up API keys now, or is browser automation sufficient for your current needs?"

IF the user wants to proceed, THEN ask: "Which providers would you like to set up?"

Present the options:

1. **Anthropic (Claude)** — Recommended as primary API evaluator. Strong analytical and reasoning capability.
2. **OpenAI (GPT)** — Widely used. Good general capability.
3. **Google (Gemini)** — Lowest cost option. Gemini Flash is extremely inexpensive.
4. **All three** — Provides maximum fallback coverage. Recommended if budget allows.
5. **I already have one or more API keys** — Skip to key entry.

Record the user's selection. Process each selected provider through Layers 2–4 sequentially.

IF the user decides to skip, THEN: "No problem. Your system will continue using browser automation for evaluation. You can set up API keys anytime by telling your AI: 'Read and execute frameworks/api-key-setup.md'"


## LAYER 2: PROVIDER SIGNUP (repeat for Each Selected provider)

**Stage Focus:** Guide the user through creating an account and navigating to the API key section for one provider.

### Processing Instructions

**IF provider is Anthropic:**

1. Tell the user: "I'm going to open the Anthropic console in your browser. You'll need to create an account with your email address and add a payment method."
2. Open the browser:
   ```xml
   <tool_call>
   <n>browser_open</n>
   <url>https://console.anthropic.com/</url>
   </tool_call>
   ```

3. Guide: "Once you're logged into the Anthropic console, look for a section called 'API Keys' in the left sidebar or settings menu. Click 'Create Key' to generate a new API key."
4. **Critical warning (first delivery):** "IMPORTANT: The key will be shown exactly ONCE. Do NOT close this page until you've copied the key. It starts with `sk-ant-` and is a long string of letters and numbers."

**IF provider is OpenAI:**

1. Tell the user: "I'm going to open the OpenAI platform in your browser."
2. Open the browser:
   ```xml
   <tool_call>
   <n>browser_open</n>
   <url>https://platform.openai.com/api-keys</url>
   </tool_call>
   ```

3. Guide: "Log in or create an account. You should see the API Keys page. Click 'Create new secret key.' Give it a name like 'ora' so you can identify it later."
4. **Critical warning (first delivery):** Same as above, noting OpenAI keys start with `sk-`.

**IF provider is Google:**

1. Tell the user: "I'm going to open Google AI Studio in your browser."
2. Open the browser:
   ```xml
   <tool_call>
   <n>browser_open</n>
   <url>https://aistudio.google.com/app/apikey</url>
   </tool_call>
   ```

3. Guide: "Log in with your Google account. Click 'Create API Key.' Select a Google Cloud project (if you don't have one, Google will create a default project for you)."
4. **Critical warning (first delivery):** Same as above.


## LAYER 3: KEY ENTRY AND STORAGE (repeat for Each provider)

**Stage Focus:** Receive the API key from the user, validate its format, and store it securely.

### Processing Instructions

1. **Critical warning (second delivery):** "Before you paste the key: confirm you've copied it. After this step, you won't need to see the key again — I'll store it securely and your system will retrieve it automatically when needed."
2. Ask: "Please paste your [provider] API key."
3. Receive and validate the key:
   - Trim any leading/trailing whitespace.
   - Remove any quotation marks surrounding the key.
   - IF provider is Anthropic AND key does not start with `sk-ant-`, THEN warn: "This doesn't look like an Anthropic API key — they typically start with 'sk-ant-'. Check that you copied the full key."
   - IF provider is OpenAI AND key does not start with `sk-`, THEN warn: "This doesn't look like an OpenAI API key — they typically start with 'sk-'. Check that you copied the full key."
   - IF key is shorter than 20 characters, THEN warn: "This seems too short for an API key. Did you copy the full string?"

4. **Store the key securely:**
   ```xml
   <tool_call>
   <n>credential_store</n>
   <action>store</action>
   <service>ora-[provider]</service>
   <username>api-key</username>
   <key>[the pasted key]</key>
   </tool_call>
   ```

5. Confirm: "Key stored securely in your system's credential manager. It is not saved in any file or log. Your system can retrieve it when needed without you entering it again."
6. **Log the event (without the key value):**
   Log to the session file: "API key stored for [provider]. Key verified format. Stored in credential manager." NEVER log the key value itself.


## LAYER 4: VERIFICATION (repeat for Each provider)

**Stage Focus:** Make a minimal API call to verify the key works.

### Processing Instructions

1. Retrieve the stored key:
   ```xml
   <tool_call>
   <n>credential_store</n>
   <action>retrieve</action>
   <service>ora-[provider]</service>
   <username>api-key</username>
   </tool_call>
   ```

2. Make a minimal verification call. The orchestrator sends a tiny API request:

   **Anthropic:** POST to `https://api.anthropic.com/v1/messages` with the smallest possible request — model `claude-haiku-4-5-20251001`, max_tokens 10, message "Say hello." Expected cost: <$0.001.

   **OpenAI:** POST to `https://api.openai.com/v1/chat/completions` with model `gpt-4o-mini`, max_tokens 10, message "Say hello." Expected cost: <$0.001.

   **Google:** POST to the Gemini API with model `gemini-2.0-flash`, max_tokens 10, message "Say hello." Expected cost: <$0.001.

3. **Interpret the result:**

   IF the API returns a successful response with generated text:
   - Report: "Verified — your [provider] API key is working. The service responded successfully."

   IF the API returns an authentication error (401/403):
   - Report: "The key was rejected by [provider]. This usually means one of three things: the key was copied incorrectly, your account's billing is not yet activated, or the key has been revoked. Would you like to try entering the key again, or check your billing setup on the provider's website?"

   IF the API returns a rate limit or quota error (429):
   - Report: "Your key is valid, but [provider] is reporting a rate limit or quota issue. This often happens with new accounts that have a $0 spending limit. Check your billing settings — you may need to add credits or increase your usage limit."
   - Open the billing page for the relevant provider.

   IF the API returns a network error:
   - Report: "I couldn't reach [provider]'s servers. This may be a temporary network issue. The key has been stored — we can verify it later. For now, let's continue with the next provider."


## LAYER 5: CONFIGURATION AND SUMMARY

**Stage Focus:** Configure the evaluation fallback chain, update the endpoint registry, and produce documentation.

### Processing Instructions

1. **Determine the fallback chain order.** The four-layer evaluation fallback chain is:

   - **Layer 1 — Browser automation** (primary, no additional cost): Uses existing subscriptions through Playwright. Always attempted first during interactive use.
   - **Layer 2 — API primary** (overflow): The user's preferred API provider. Used when browser automation is unavailable.
   - **Layer 3 — API secondary** (backup): Second API provider, if configured.
   - **Layer 4 — Local-only mode** (degraded): No external evaluation. Quality warnings applied to un-reviewed output.

   IF the user configured multiple API providers, THEN ask: "Which API provider would you like as your primary overflow? The others will be used as backups if the primary is unavailable."

   IF the user has no preference, THEN recommend based on capability and cost:
   - API Primary: Anthropic Claude (strongest analytical capability for evaluation)
   - API Secondary: Google Gemini Flash (lowest cost, good for routine evaluations)
   - API Tertiary: OpenAI GPT-4o-mini (backup)

2. **Update the endpoint registry** at `[workspace]/config/endpoints.json`:

   For each configured API provider, add an endpoint entry:

   ```json
   {
     "name": "[provider]-api",
     "type": "api",
     "service": "[anthropic|openai|google]",
     "model": "[recommended model for evaluation]",
     "status": "active",
     "verified": "[ISO date]",
     "credential_key": "ora-[provider]"
   }
   ```

   Do not modify existing browser or local endpoint entries.

3. **Write the configuration file:**

   ```xml
   <tool_call>
   <n>file_write</n>
   <path>config/api-providers.md</path>
   <content>
   # API Provider Configuration

   Generated: [date]

   ## Role in the System

   API keys are the overflow/reliability channel. Browser automation
   (Playwright) is the primary evaluation channel during interactive use.
   API access activates when browser automation is unavailable, for
   enterprise reliability needs, or for pre-authorized autonomous operations.

   ## Configured Providers

   [For each provider:]
   ### [Provider Name]
   - Status: [Verified / Stored but unverified / Not configured]
   - Credential store key: ora-[provider]
   - Recommended model for evaluation: [model name]
   - Approximate cost per evaluation: [amount]

   ## Evaluation Fallback Chain

   1. Browser automation (primary — uses existing subscriptions)
   2. [API Primary provider and model] (overflow)
   3. [API Secondary provider and model] (backup)
   4. Local-only mode (no external evaluation — quality warnings applied)

   ## Operational Context Rules

   - Interactive work: all channels available (browser, API, local)
   - Autonomous overnight: local only by default. API available if
     explicitly pre-authorized in the task specification.
   - Agent operations: local only by default.
   - Browser automation: prohibited during unattended work (sessions
     may expire and require human interaction to re-authenticate).

   ## Updating Keys

   To update or replace a key, tell your AI:
   "Read and execute frameworks/api-key-setup.md"
   and select the provider you want to update.

   ## Adding Browser Automation Connections

   To add or reconnect browser automation:
   "Read and execute frameworks/browser-eval-setup.md"
   </content>
   </tool_call>
   ```

4. **Present the summary:**

   "Here's what we set up:

   [List each configured API provider with verification status]

   Your evaluation fallback chain:
   1. Browser automation (primary — your [connected services] subscriptions)
   2. [API primary] (overflow)
   3. [API secondary] (backup, if configured)
   4. Local-only mode (last resort)

   During interactive use, your system tries browser automation first. If that's unavailable, it falls back to the API. For autonomous overnight runs, only local and pre-authorized API channels are used — browser automation is excluded because sessions can expire and require your interaction.

   You don't need to do anything else — your boot.md specification knows how to use these keys through the orchestrator. The keys are stored securely and will be available whenever your system needs them."


## LAYER 6: SELF-EVALUATION

**Stage Focus**: Evaluate the output produced in Layers 1 through 5 against the 4 Evaluation Criteria (Key Acquisition Success, User Comprehension, Security, Fallback Configuration).

**Calibration warning**: Self-evaluation scores are systematically inflated. Research finds LLMs are overconfident in 84.3% of scenarios. A self-score of 4/5 likely corresponds to 3/5 by external evaluation standards. Score conservatively. Articulate specific uncertainties alongside scores.

### Processing Instructions

For each of the 4 criteria:

1. State the criterion name and number.
2. Wait — verify the current output against this specific criterion's rubric descriptions before scoring.
3. Identify specific evidence in the output that supports or undermines each score level.
4. Assign a score (1–5) with cited evidence from the output.
5. IF the score is below 3, THEN:
   a. Identify the specific deficiency with a direct quote or reference to the deficient passage (e.g., which provider failed verification, which security check was missed, which fallback chain step is incomplete).
   b. State the specific modification required to raise the score.
   c. Apply the modification where possible — retry verification against the provider endpoint; re-run credential store write if plaintext exposure was detected; update endpoint registry if fallback chain is incomplete.
   d. Re-score after modification.
6. IF the score meets or exceeds 3, confirm and proceed.

After all criteria are evaluated:

- IF all scores meet or exceed 3, proceed to Layer 7.
- IF any score remains below 3 after one modification attempt, flag the deficiency explicitly with the label UNRESOLVED DEFICIENCY and state what additional input or iteration would be needed to resolve it.

**Confidence assessment requirement**: For each criterion score, state confidence (High / Medium / Low) and one sentence explaining what drives the confidence level. Low-confidence scores on criterion 3 (Security) or criterion 4 (Fallback Configuration) indicate that the credential store write or the api-providers.md configuration file should be re-verified before the session closes.

### Output Formatting for This Layer

```
SELF-EVALUATION
Criterion 1 — Key Acquisition Success: [Score 1-5]
  Evidence: [cited evidence from Layers 2-4 — which providers configured, verification results]
  Confidence: [High | Medium | Low] — [rationale]

Criterion 2 — User Comprehension: [Score 1-5]
  Evidence: [cited user acknowledgments at Layer 1 explanation checkpoints, confusion points if any]
  Confidence: [High | Medium | Low] — [rationale]

Criterion 3 — Security: [Score 1-5]
  Evidence: [credential store storage method confirmed per provider, plaintext exposure check, log inspection]
  Confidence: [High | Medium | Low] — [rationale]

Criterion 4 — Fallback Configuration: [Score 1-5]
  Evidence: [api-providers.md written, endpoint registry updated, fallback chain documented]
  Confidence: [High | Medium | Low] — [rationale]

Modifications applied: [list of corrections made during self-evaluation — retries, re-writes, security remediations]
Unresolved deficiencies: [list of criteria remaining below 3, with specific gap and what would resolve it]
```


## LAYER 7: ERROR CORRECTION AND OUTPUT FORMATTING

**Stage Focus**: Final verification, mechanical error correction, variable fidelity check, and output formatting for delivery including the user-facing summary and configuration artifact writes.

**Input**: All output from Layers 1 through 6 including the SELF-EVALUATION block.

**Output**: Corrected, final, formatted deliverable — user-facing summary per Layer 5 Step 4 format, configuration artifacts (api-providers.md file, endpoint registry updates, credential store entries), plus Missing Information Declaration and Recovery Declaration.

### Error Correction Protocol

1. **Verify factual consistency** across all output sections. Confirm provider names, pricing figures, and URLs are consistent between Layer 1 explanations and Layer 5 summary. Flag and correct any contradictions.
2. **Verify terminology consistency.** Confirm that "overflow channel," "reliability channel," "browser automation primary," "API fallback," and the four-layer fallback chain labels (browser automation → API primary → API secondary → local-only) are used with their defined meanings throughout.
3. **Verify structural completeness.** Confirm all required output components per OUTPUT CONTRACT are present:
   - API key(s) stored in the system credential store (macOS Keychain, Windows Credential Manager, or Linux SecretService via the `keyring` library).
   - Verification result for each stored key (confirmed working or failed with explanation).
   - `api-providers.md` configuration file written to the user's configuration directory.
   - Endpoint registry updated with configured providers.
   - Fallback chain specification present in `api-providers.md`.
4. **Verify variable fidelity.** Confirm that all named variables established during processing are still present and accurately represented: the user's selected providers, the use case context (overflow / reliability / autonomous operations), existing keys if provided, and the fallback chain ordering. IF any variable has been silently dropped or simplified, THEN restore it.
5. Document all corrections made in a Corrections Log appended to the session output.

### Output Formatting

Final user-facing summary per Layer 5 Step 4 format. Configuration artifacts written to their destinations:

- Credential store entries via the `credential_store` tool (one per provider).
- `api-providers.md` written to the user's configuration directory with the four-layer fallback chain documented.
- Endpoint registry entries updated with the configured providers.

No plaintext key values appear in session logs or user-visible output after storage. The session log records that keys were stored, not the key values themselves.

### Missing Information Declaration

Before finalizing output, explicitly state:

- Any provider the user declined to configure (with reason if stated — e.g., sticker shock, time constraint, preference for browser automation only).
- Any verification that failed or was skipped (with reason — e.g., billing not yet activated, endpoint not reachable, key entered but verification deferred).
- Any fallback chain position left unfilled (e.g., only one API provider configured; secondary fallback position remains empty).
- Any assumptions made when input was ambiguous (e.g., defaulting to general-purpose overflow when use case was not stated).

A response that acknowledges missing configuration is always preferable to a response that fills gaps with assumptions.

### Recovery Declaration

IF the Self-Evaluation layer flagged any UNRESOLVED DEFICIENCY, THEN restate each deficiency here with:

- The specific criterion that was not met (1 Key Acquisition Success / 2 User Comprehension / 3 Security / 4 Fallback Configuration).
- What additional input, iteration, or human judgment would resolve it.
- Whether the deficiency affects downstream system operation — specifically whether the evaluation pipeline has a working fallback chain or whether it will fall back to local-only mode when browser automation is unavailable.

For operational runtime failures encountered during framework execution (key paste failures, verification failures after retries, user abandonment partway through), see the OPERATIONAL RECOVERY section below. That section covers failures that occur *during* framework execution; this Recovery Declaration covers unresolved deficiencies detected *at the end* of framework execution by the Self-Evaluation layer.


## OPERATIONAL RECOVERY

### Key Entry Failures

WHEN the user cannot successfully paste a key:
- Suggest: "Try right-clicking and selecting 'Paste' rather than using the keyboard shortcut."
- IF the user reports the key page has closed: "You'll need to generate a new key. Go back to the API Keys page on [provider]'s website and create another one. The old key is automatically invalidated."

### Verification Failures

WHEN verification fails for all providers after retries:
- Store the keys anyway (they may work once billing is activated).
- Write the configuration file with "Stored but unverified" status.
- Explain: "Your keys are stored and your system is configured to use them. If the verification issue was about billing activation, they should start working once your account is fully set up. Your system will automatically attempt to use them and report any errors. Remember: your browser automation connections are still your primary evaluation channel — API keys are the backup."

### User Abandonment

WHEN the user wants to stop partway through:
- Store any keys already obtained.
- Write the configuration file with whatever providers were completed.
- Update the endpoint registry with completed providers.
- Explain: "I've saved what we set up so far. Your browser automation connections remain your primary evaluation channel. You can add more API providers anytime by telling me to run this framework again."


## EXECUTION COMMANDS

1. Confirm you have fully processed this framework.
2. Begin with Layer 1 (Explanation and Context). Do not skip the explanation even if the user seems technical — the cost comparison with browser automation, the overflow/reliability positioning, and the one-chance key warning are essential.
3. Process Layers 2–4 for each provider the user selects.
4. Complete Layer 5 (Configuration and Summary) after all providers are processed.
5. Run Layer 6 (Self-Evaluation) scoring each of the 4 Evaluation Criteria against the output with cited evidence and confidence assessment. Apply modifications for any below-threshold scores.
6. Complete Layer 7 (Error Correction and Output Formatting) including Error Correction Protocol, Missing Information Declaration, and Recovery Declaration. For operational runtime failures encountered during execution, consult the OPERATIONAL RECOVERY section.


*End of API Key Acquisition Framework v1.2*


**VERSION HISTORY**

v1.0 (2026/03/23): Initial version. API keys positioned as the primary evaluation channel.

v1.1 (2026/03/24): Repositioned API keys as the overflow/reliability channel behind browser automation via Playwright. Added Layer 1 context explaining the relationship between browser automation and API access. Added four-layer evaluation fallback chain (browser → API primary → API secondary → local-only). Added operational context rules for autonomous work. Added endpoint registry integration. Added the Unnecessary Expense Trap to Named Failure Modes. Updated evaluation criteria to include fallback chain completeness and browser automation context in user comprehension.

v1.2 (2026/04/23): Added Layer 6 (Self-Evaluation) in penultimate position and Layer 7 (Error Correction and Output Formatting) in final position per Process Formalization Framework v2.0 Anatomy. Layer 6 scores each of the 4 Evaluation Criteria 1–5 with cited evidence, calibration warning, and remediation protocol for below-threshold scores. Layer 7 adds Error Correction Protocol (factual consistency, terminology, structural completeness, variable fidelity), Output Formatting, Missing Information Declaration, and Recovery Declaration. Renamed the existing RECOVERY section to OPERATIONAL RECOVERY to distinguish runtime-failure recovery (during execution) from the PFF Recovery Declaration (for unresolved deficiencies at end-of-execution). EXECUTION COMMANDS updated with steps 5 and 6 covering the new layers.
