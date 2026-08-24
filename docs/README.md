# Ora — Documentation

This is the documentation for a source install of Ora, a local multi-model
orchestrator. Ora runs a small Python server on your own machine and reaches the
AI models through a browser interface at localhost. The server keeps tools — web
search, file access, knowledge search — in the loop between you and the model, so
tool calls run automatically before you see a response. Work that needs those
tools should go through the local interface, not through claude.ai, ChatGPT, or
Gemini directly, which have no tools in the loop.

## The canonical documentation (start here)

Three documents describe the installed system. Each is a body-only mirror of a
vault canonical: the vault copy is the source of truth and these mirrors are
regenerated from it, so edit the vault original, never these files.

- **[Using Ora](../help/user-guide.md)** — a task-indexed how-to: install, add API keys,
  choose models, run work, and recover from problems, with every command
  platform-labeled. Start here to operate the system.
- **[Accessible overview](../help/accessible-overview.md)** — a plain-language explanation
  of what Ora is and why it is built this way.
- **[Technical documentation](technical-documentation.md)** — the deepest source
  of truth: every subsystem's problem, design, implementation, and verification,
  with a platform-compatibility matrix and an implemented-vs-planned ledger. For
  engineers and maintainers.

## Install and operations references

The reader-facing install and recovery specifics live in the tracked help library:
`../help/install-guide.md` (happy-path install with a per-platform command matrix),
`../help/install-manual.md` (manual fallback when the installer is broken),
`../help/install-recovery.md` (recovering from a partial install), `install-testing.md`
(clean-room test protocol), and `cloud-ora-install.md` (Linux server operator
guide).

## Source of truth and parity

The three canonical documents are governed by the Documentation-Code Parity rule:
the vault file is canonical, the repo mirror carries the body only (YAML
frontmatter stripped), and the mirror is regenerated whenever the vault canonical
changes. The rule is stated in the technical documentation's Appendix C,
"Vault↔Repo Mirror Parity Rule."
