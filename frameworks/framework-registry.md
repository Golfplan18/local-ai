# Framework Registry

## Format

Each entry documents a framework available in this system.

| Field | Description |
|---|---|
| **Name** | Framework identifier |
| **Purpose** | What the framework accomplishes |
| **Problem Class** | The type of problem it solves |
| **Input Summary** | What inputs are required |
| **Output Summary** | What outputs are produced |
| **Proven Applications** | Known successful use cases |
| **Known Limitations** | Edge cases or failure modes |
| **File Location** | Path within frameworks/ |
| **Provenance** | Source (book-shipped, user-created, community) |
| **Confidence** | Reliability rating 1–5 |
| **Version** | Framework version |

## Registered Frameworks

### Local AI First Boot Framework
- **Purpose:** Transform a bare machine into a working local AI system with browser chat interface
- **Problem Class:** System setup and installation
- **Input Summary:** Hardware access; optional model preference and workspace path
- **Output Summary:** Browser-based AI at localhost:5000, hardware report, README
- **Proven Applications:** macOS, Linux, Windows; Tier 0–C hardware profiles
- **Known Limitations:** Requires Python 3; browser automation depends on existing accounts
- **File Location:** frameworks/book/local-ai-first-boot.md
- **Provenance:** book-shipped
- **Confidence:** 5
- **Version:** v4

### Browser Evaluation Setup Framework
- **Purpose:** Connect Playwright browser automation to commercial AI services
- **Problem Class:** Integration setup
- **Input Summary:** Existing commercial AI accounts (Claude, ChatGPT, Gemini)
- **Output Summary:** Saved browser sessions, registered endpoints in endpoints.json
- **Proven Applications:** All tiers with existing subscriptions
- **Known Limitations:** Sessions expire; re-run when login cookies expire
- **File Location:** frameworks/book/browser-eval-setup.md
- **Provenance:** book-shipped
- **Confidence:** 4
- **Version:** v1

### API Key Acquisition Framework
- **Purpose:** Acquire and securely store API keys for commercial AI services
- **Problem Class:** Credential management
- **Input Summary:** User-selected AI providers
- **Output Summary:** API keys stored in system keyring, endpoints registered
- **Proven Applications:** Anthropic, OpenAI, Google AI
- **Known Limitations:** Requires paid account for some providers
- **File Location:** frameworks/book/api-key-setup.md
- **Provenance:** book-shipped
- **Confidence:** 5
- **Version:** v1

### Framework Capture Framework (FCF)
- **Purpose:** Capture, document, and register new frameworks into the registry
- **Problem Class:** Knowledge management
- **Input Summary:** A reusable process or method worth capturing
- **Output Summary:** A registered framework entry with standardized metadata
- **Proven Applications:** Any repeatable process
- **Known Limitations:** Requires human judgment to identify what is worth capturing
- **File Location:** frameworks/book/fcf.md
- **Provenance:** book-shipped
- **Confidence:** 5
- **Version:** v1
