
# System File Drift Correction Framework

## Display Name
System File Drift Correction

## Display Description
Detect and reconcile drift between the canonical vault and the ~/ora/ deployment surface. Runs under explicit user-controlled direction with .bak backups for every overwrite. Use when vault and ora .md files have diverged.


*A framework for detecting and reconciling drift between content files in the canonical vault and the ~/ora deployment surface.*

*Version 1.1*

---

## How to Use This File

This framework manages the dual-copy relationship between the Ora vault (canonical source-of-truth) and the ~/ora deployment directory (operational copies the orchestrator loads at runtime). Most ora content has a paired vault file. When edits accumulate in either location without being propagated, the pair drifts. This framework detects and reconciles that drift.

Paste this entire file into a Claude session that has file system access (Claude Code or equivalent). State the operation mode below the USER INPUT marker at the bottom. The AI executes the operation and reports.

**Mode D-Detect:** Scan all registered pairs and report drift status. No file changes. Use when you want a snapshot of what's out of sync.

**Mode D-Sync:** Push current vault content to ora copies that have drifted (vault-newer or body-different cases). Backs up every overwritten ora file as `<filename>.bak`. Refuses to act on `ora-newer` pairs — those surface as conflicts requiring explicit user decision.

**Mode D-Accept-Ora:** Reverse sync — for pairs the user has explicitly approved as "ora is newer because Claude Code edited it directly", pull ora's body back into vault. Backs up every overwritten vault file. Runs only on the explicit pair list the user supplies; never sweeps automatically.

**Mode D-Bootstrap:** For ora files matching a registered pairing pattern but lacking a vault counterpart, create the vault copy by copying ora content verbatim to the destination path. Refuses to overwrite existing vault files. Use after adding new content categories or new files to ora that should become canonical.

---

## PURPOSE

Detect drift between paired content files in `/Users/oracle/Documents/vault/` (canonical) and `/Users/oracle/ora/` (deployment), and reconcile that drift on demand under explicit user-controlled direction. The vault is the single source of truth; ora carries operational copies the orchestrator loads at runtime. This framework prevents silent divergence and ensures every reconciliation action is reversible via `.bak` backups.

## INPUT CONTRACT

Required:
- **Operation mode:** one of `D-Detect | D-Sync | D-Accept-Ora | D-Bootstrap`. Source: user.
- **Vault root path:** absolute path to the vault directory. Default: `/Users/oracle/Documents/vault/`. Source: user or default.
- **Ora root path:** absolute path to the ora directory. Default: `/Users/oracle/ora/`. Source: user or default.

Optional:
- **Pair filter:** glob or substring restricting which pairs are processed (e.g., `Framework — *` or `Specification —`). Default behavior if absent: process all registered pairs.
- **Explicit pair list (D-Accept-Ora only):** newline-separated list of vault file paths whose ora counterparts should overwrite them. Required for D-Accept-Ora; the mode refuses to run without it.

## OUTPUT CONTRACT

Primary outputs vary by mode:

- **D-Detect:** A drift report. Format: one section per category, listing every pair with classification (`identical | yaml-only-diff | vault-newer | ora-newer | body-different | vault-only | ora-only | excluded`). Destination: chat output. Quality threshold: every registered pair appears exactly once with a classification; no file system writes occurred.

- **D-Sync:** A sync log. Format: list of every modified ora file with pre/post sizes and the path of the `.bak` created. Destination: chat output plus the file system mutations themselves. Quality threshold: every targeted ora file's body equals its vault counterpart's body (modulo YAML and trailing-blank-line normalization); every overwrite has a `.bak`.

- **D-Accept-Ora:** A reverse sync log. Format: same as D-Sync but reversed direction. Destination: chat output plus file system mutations. Quality threshold: every targeted vault file's body equals its ora counterpart's body; every overwrite has a `.bak`; only files in the user's explicit pair list are touched.

- **D-Bootstrap:** A creation log. Format: list of new vault files created with their source ora paths. Destination: chat output plus new vault files. Quality threshold: every ora file matching a registered pattern that lacked a vault pair now has one; no existing vault file was overwritten.

## EXECUTION TIER

specification — operates in a single context window for commercial AI execution with file system tools. Agent-mode rendering is straightforward but not required.

Each mode (D-Detect / D-Sync / D-Accept-Ora / D-Bootstrap) covers Layers 1-6 (six processing layers) and declares a single milestone. Per the Process Formalization Framework Section II §2.3, this single-milestone-for->5-layer-modes design is justified by the atomic-by-design nature of drift-correction: the file pair is either reconciled per the mode's contract or it is not. Per-layer milestones would fragment what users experience as a single sync operation and risk partial-state commits to the filesystem.

## MILESTONES DELIVERED

### Milestones for Mode D-Detect

#### Milestone 1: Drift Detection Report

- **Mode:** D-Detect
- **Endpoint produced:** A report classifying every registered file pair as one of: `identical | yaml-only-diff | vault-newer | ora-newer | body-different | vault-only | ora-only | excluded`.
- **Verification criterion:** Every registered pair appears exactly once with a classification; the file system is unchanged after the operation completes.
- **Layers covered:** 1, 2, 3, 4, 5, 6
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** Structured drift report with per-pair classifications.
- **Drift check question:** Does every registered pair appear exactly once with a classification, and is the file system genuinely unchanged after detection?

### Milestones for Mode D-Sync

#### Milestone 1: Drift Correction (Vault → Ora)

- **Mode:** D-Sync
- **Endpoint produced:** Every pair classified as `vault-newer` or `body-different` has its ora copy updated to match vault's body. Every overwritten ora file has a `.bak` of its prior content alongside it.
- **Verification criterion:** For every modified pair, the ora file's body equals its vault counterpart's body modulo YAML differences and trailing-blank-line normalization. Every overwrite produced a `.bak` file. No `ora-newer` pair was modified.
- **Layers covered:** 1, 2, 3, 4, 5, 6
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** Updated ora files plus `.bak` files plus sync summary report.
- **Drift check question:** Did every modified pair receive a `.bak` and does its ora body now match vault's body, with no `ora-newer` pair touched?

### Milestones for Mode D-Accept-Ora

#### Milestone 1: Reverse Sync (Ora → Vault, Opt-In)

- **Mode:** D-Accept-Ora
- **Endpoint produced:** For every vault file in the user's explicit pair list, vault's body is updated to match ora's body. Every overwritten vault file has a `.bak`.
- **Verification criterion:** Only files in the explicit pair list were modified. Every modified vault file's body equals its ora counterpart's body. Every overwrite produced a `.bak`.
- **Layers covered:** 1, 2, 3, 4, 5, 6
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** Updated vault files plus `.bak` files plus reverse-sync summary report.
- **Drift check question:** Were only the explicitly-listed pairs modified, and does every modified vault file body now match its ora counterpart with a `.bak` preserved?

### Milestones for Mode D-Bootstrap

#### Milestone 1: Bootstrap (Ora-Only → Vault)

- **Mode:** D-Bootstrap
- **Endpoint produced:** For every ora file matching a registered pairing pattern but lacking a vault counterpart, a vault file is created at the canonical destination path containing ora's verbatim content.
- **Verification criterion:** Every previously ora-only file matching a registered pattern now has a vault pair. No existing vault file was overwritten. The created vault files contain ora's content unchanged.
- **Layers covered:** 1, 2, 3, 4, 5, 6
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** New vault files at canonical paths plus bootstrap summary report.
- **Drift check question:** Did the bootstrap create vault files only for newly-recognized ora-only patterns, with no existing vault file overwritten?

## EVALUATION CRITERIA

This framework's output is evaluated against these seven criteria. Each criterion is rated 1-5. Minimum passing score: 4 per criterion.

1. **Pairing accuracy:**
   - 5 (Excellent): Every pair is correctly identified per the Pairing Rules table; no false matches; no missed pairs.
   - 4 (Strong): All standard pairs identified correctly; one edge case may need user disambiguation.
   - 3 (Passing): Standard cases handled; multiple edge cases surfaced rather than silently mishandled.
   - 2 (Below threshold): Pairs misidentified or silently dropped without surfacing.
   - 1 (Failing): Wrong files paired together; data loss risk.

2. **Direction correctness:**
   - 5 (Excellent): No write to vault except in D-Accept-Ora or D-Bootstrap; no write to ora except in D-Sync. Direction is explicit and traceable for every operation.
   - 4 (Strong): All writes go in the correct direction; each is logged.
   - 3 (Passing): Writes in correct direction; logging may be incomplete.
   - 2 (Below threshold): A write in an unexpected direction occurred without user approval.
   - 1 (Failing): Vault overwritten with stale ora content silently.

3. **Backup compliance:**
   - 5 (Excellent): Every file overwrite is preceded by a `.bak` of the prior content; the `.bak` path is included in the output log.
   - 4 (Strong): Every overwrite has a `.bak`; logs may be slightly incomplete.
   - 3 (Passing): Backups created; logging skipped a small number.
   - 2 (Below threshold): At least one overwrite occurred without a `.bak`.
   - 1 (Failing): Multiple overwrites without backups; data loss risk realized.

4. **Conflict surfacing:**
   - 5 (Excellent): Every `ora-newer` pair, every `vault-only` framework lacking an ora pair, and every ambiguous case is surfaced as a conflict requiring explicit user decision rather than silently resolved.
   - 4 (Strong): All conflicts surfaced; recommended resolution presented for each.
   - 3 (Passing): Conflicts surfaced; recommendations may be missing.
   - 2 (Below threshold): A conflict was silently resolved by the framework's heuristic.
   - 1 (Failing): Multiple silent conflict resolutions; user has no visibility into what changed and why.

5. **Pattern coverage:**
   - 5 (Excellent): Every category in the Pairing Rules table is handled; excluded paths are explicitly enumerated; no file is silently ignored.
   - 4 (Strong): All standard categories handled; one category may surface as "needs user input."
   - 3 (Passing): Standard categories handled; some files surface as "uncategorized" rather than silently ignored.
   - 2 (Below threshold): Files silently ignored due to missing pattern.
   - 1 (Failing): Major content category not handled.

6. **Idempotency:**
   - 5 (Excellent): Running the framework twice with identical input produces identical output; the second run reports zero changes.
   - 4 (Strong): Second run produces zero functional changes; minor logging differences acceptable.
   - 3 (Passing): Second run produces a small number of redundant operations on edge cases.
   - 2 (Below threshold): Second run produces unnecessary writes.
   - 1 (Failing): Second run produces different file system state than first run.

7. **Output clarity:**
   - 5 (Excellent): The report is scannable, categorized, names every affected file with relative paths, and surfaces conflicts at the top.
   - 4 (Strong): All required information present; categorization clear.
   - 3 (Passing): Required information present; layout could be improved.
   - 2 (Below threshold): User must search the output to find what changed.
   - 1 (Failing): Output is incomplete or misleading.

## PERSONA

You are the System File Drift Auditor — a meticulous custodian of source-of-truth integrity between the canonical Ora vault and its operational deployment surface in `~/ora`.

You possess:
- The patience to compare hundreds of file pairs without skipping;
- The discipline to refuse silent overwrites when authority direction is ambiguous;
- The reflex to back up before every write and surface conflicts before resolving them.

Throughout this framework, you operate as a single auditor across all stages. You do not improvise pairing rules; you apply only the rules in the Pairing Rules table. You do not infer the user's intent on conflicts; you surface them.

## LAYER 1: INPUT VALIDATION AND MODE DISPATCH

**Stage Focus:** Validate inputs and route to the correct operation flow.

**Input:** User-supplied operation mode and any optional parameters.

**Output:** Validated operation parameters; routing decision to subsequent layers.

### Processing Instructions

1. Confirm the operation mode is one of `D-Detect`, `D-Sync`, `D-Accept-Ora`, `D-Bootstrap`. IF the mode is missing or invalid, THEN list the valid modes and request a corrected input.
2. Confirm vault root and ora root paths exist and are readable. IF either is missing, THEN list the missing path and request a corrected input.
3. IF the operation mode is `D-Accept-Ora`, THEN confirm the user supplied an explicit pair list. The list must be non-empty and every entry must reference an existing vault file. IF the list is missing or any entry is invalid, THEN refuse to proceed and request a corrected input.
4. IF a pair filter is supplied, THEN normalize it to a glob pattern.
5. State the validated parameters back to the user in a one-line summary before proceeding.

## LAYER 2: PAIR DISCOVERY

**Stage Focus:** Enumerate every paired vault/ora file using the Pairing Rules table.

**Input:** Validated paths and filter from Layer 1.

**Output:** A list of pair records, each with `vault_path`, `ora_path` (or `null` if vault-only), `category`, and `bootstrap_eligible` (true if ora exists but vault does not).

### Pairing Rules

Every pair belongs to one category. Apply categories in this order:

| Vault location | Ora location | Direction default | Notes |
|---|---|---|---|
| `Framework — *.md` (vault root) | `frameworks/book/<lowercased-hyphenated>.md` | vault → ora | Strip vault YAML when writing to ora; ora has no YAML. Filename: drop "Framework — " prefix, lowercase, replace spaces with hyphens. |
| `Specification — *.md` (vault root) | `frameworks/book/<lowercased-hyphenated>.md` | vault → ora | Strip vault YAML when writing to ora. Filename: drop "Specification — " prefix, lowercase. |
| `Reference — Framework — *.md` (vault root) | none | vault-only | These are kept-but-not-deployed reference frameworks. Never push to ora. |
| `Reference — Forking Ora.md` (vault root) | `FORKING.md` (ora root) | vault → ora | Preserve verbatim; no YAML stripping (ora file has no YAML). |
| `Reference — Agent Registry.md` (vault root) | `agents/agent-registry.md` | vault → ora | Both files have YAML; preserve ora's YAML format if it differs from vault's. |
| `Reference — Mode Classification Directory.md` (vault root) | `frameworks/mode-classification-directory.md` | vault → ora | No YAML on ora side. |
| `Framework — Framework Registry.md` (vault root) | `frameworks/framework-registry.md` | vault → ora | Strip vault YAML when writing to ora. |
| `Framework — System File Drift Correction.md` (vault root) | `frameworks/book/system-file-drift-correction.md` | vault → ora | This framework itself. Strip vault YAML when writing to ora. |
| `Reference — Analytical Territories.md` (vault root) | `architecture/territories.md` | vault → ora | Strip vault YAML. Decision K: ora side holds 9 kebab-case architecture files the orchestrator reads at runtime. |
| `Reference — Mode Specification Template.md` (vault root) | `architecture/mode-template.md` | vault → ora | Strip vault YAML. |
| `Reference — Disambiguation Style Guide.md` (vault root) | `architecture/disambiguation-style-guide.md` | vault → ora | Strip vault YAML. |
| `Reference — Lens Library Specification.md` (vault root) | `architecture/lens-library-specification.md` | vault → ora | Strip vault YAML. |
| `Reference — Pre-Routing Pipeline Architecture.md` (vault root) | `architecture/pre-routing-pipeline.md` | vault → ora | Strip vault YAML. |
| `Reference — Signal Vocabulary Registry.md` (vault root) | `architecture/signal-vocabulary-registry.md` | vault → ora | Strip vault YAML. |
| `Reference — Mode Runtime Configuration.md` (vault root) | `architecture/runtime-configuration.md` | vault → ora | Strip vault YAML. |
| `Reference — Within-Territory Disambiguation Trees.md` (vault root) | `architecture/within-territory-trees.md` | vault → ora | Strip vault YAML. |
| `Reference — Cross-Territory Adjacency.md` (vault root) | `architecture/cross-territory-adjacency.md` | vault → ora | Strip vault YAML. |
| `Framework — <Territory Display Name>.md` (vault root, Phase 10 deliverables — 21 files) | `frameworks/territories/<territory-id>.md` | vault → ora | Strip vault YAML. Filename: derive territory-id from territory display name (e.g., "Argumentative Artifact Examination" → `t1-argumentative-artifact-examination.md`). Built in Phase 10. |
| `vault/Modes/*.md` | `ora/modes/*.md` | vault → ora | Both sides have YAML; preserve. Filename matches one-to-one. |
| `vault/Lenses/*.md` | `ora/knowledge/mental-models/*.md` | vault → ora | Both sides have YAML; preserve. Filename matches one-to-one. |
| `vault/Modules/Tools/*.md` | `ora/modules/tools/*.md` | vault → ora | No YAML on either side. |
| `vault/Modules/Tools/Tier2/*.md` | `ora/modules/tools/tier2/*.md` | vault → ora | No YAML on either side. |
| All other vault files (`Reference — *`, `Working — *`, `Installer — *`, `Engrams/`, `Old AI Working Files/`, `Library/`, etc.) | none | vault-only | Never push to ora. |

### Excluded ora paths

These ora paths are not eligible for any pairing and are silently excluded from discovery. They are operational artifacts, code, runtime state, or generated content:

- `~/ora/data/`, `~/ora/sessions/`, `~/ora/logs/`, `~/ora/output/`, `~/ora/chromadb/`, `~/ora/orchestrator/chroma_db/`
- `~/ora/orchestrator/` (Python code), `~/ora/server/` (server code), `~/ora/extension/`, `~/ora/installer/`, `~/ora/scripts/`, `~/ora/tests/`, `~/ora/orchestrator/tests/`
- `~/ora/config/` (machine-specific configuration), `~/ora/models/` (large binaries)
- `~/ora/Ora.app/`, `~/ora/Ora Models.app/`, `~/ora/logo/`
- `~/ora/mindspec/default-mindspec.md` (generated runtime artifact)
- `~/ora/boot/boot.md` (operational boot file, intentionally not vault-canonical)
- `~/ora/mind.md` (deprecated, not pipeline-loaded)
- `~/ora/CLAUDE.md`, `~/ora/.gitignore`, `~/ora/start.sh`, `~/ora/stop.sh`, `~/ora/publish.sh`, `~/ora/swap-icon.sh`, `~/ora/start.bat`, `~/ora/stop.bat`, `~/ora/make_icons.py`, `~/ora/make_logo.py`
- `~/ora/server-classic-backup-*` (archived server backups)
- `~/ora/.git/`, `~/ora/.claude/`, `~/ora/.DS_Store`
- All `*.bak` files (this framework's own backups)
- `~/ora/frameworks/README.md`, `~/ora/docs/` (operational documentation)

### Processing Instructions

1. For every Pairing Rule row, enumerate the matching vault files and the matching ora files. Build the pair list.
2. For each pair, determine status of the ora side (exists | missing).
3. For each ora file under the rule's ora-side pattern, determine status of the vault side (exists | missing).
4. IF the operation mode is `D-Bootstrap`, THEN restrict the pair list to those where the vault side is missing and the ora side exists (`bootstrap_eligible = true`).
5. IF a pair filter was supplied, THEN restrict the pair list to entries matching the filter.
6. State the count of pairs discovered, broken down by category, before proceeding.

## LAYER 3: BODY DRIFT DETECTION

**Stage Focus:** For each pair, compare bodies and classify drift status.

**Input:** Pair list from Layer 2.

**Output:** Each pair annotated with one of: `identical | yaml-only-diff | vault-newer | ora-newer | body-different | vault-only | ora-only`.

### Body normalization rule

When comparing two files for body equality:

1. Strip the YAML frontmatter from each side (the block delimited by `---` at the start, if present). Compare only what comes after.
2. Strip leading and trailing blank lines from each body.
3. Treat sequences of blank lines longer than two as equivalent.
4. Treat standalone markdown horizontal rules — lines containing only `---` (with no other characters) — as equivalent to blank lines on both sides. Section dividers carry no semantic content for the runtime loading the file, so cosmetic differences in horizontal-rule placement must not be classified as body drift. (Added in v1.1; this prevents the false-positive class observed during the 2026-04-27 smoke test where vault carried more `---` separators than ora for the same logical content.)
5. The bodies are equal if and only if the normalized strings are identical.

### Classification rule

For each pair:

- IF vault file is missing and ora file exists, THEN classify as `ora-only` (a candidate for D-Bootstrap).
- IF vault file exists and ora file is missing, THEN classify as `vault-only` (expected for `Reference — Framework —` rows; otherwise a registry mismatch to surface).
- IF both exist and bodies are equal per the normalization rule, THEN classify as `identical` (or `yaml-only-diff` if the YAML blocks differ).
- IF both exist and bodies differ, THEN classify as `body-different`. Additionally, compare filesystem mtimes:
  - IF vault mtime is more recent, also tag as `vault-newer`.
  - IF ora mtime is more recent, also tag as `ora-newer`.

### Processing Instructions

1. Read each paired file (vault and ora). For pairs of large files, you may use a streaming hash comparison after YAML stripping rather than loading both into memory simultaneously.
2. Apply the body normalization rule.
3. Apply the classification rule.
4. Annotate each pair record with its classification.
5. Before proceeding, restate any unexpected classifications (e.g., a `vault-only` for a category that should be paired) as a single bulleted list. These will be surfaced in the output.

## LAYER 4: OPERATION EXECUTION

**Stage Focus:** Execute the operation per the mode dispatched in Layer 1.

**Input:** Annotated pair list from Layer 3.

**Output:** Either a report (D-Detect) or a sequence of file mutations with their log entries (other modes).

### D-Detect

1. Produce a report grouped by category. For each category, list every pair with: vault filename, ora filename, classification.
2. At the top of the report, surface a "Conflicts and surprises" section listing: every `ora-newer` pair, every `vault-only` pair not in the `Reference — Framework —` category, every `ora-only` pair not in an excluded path, and every classification anomaly noted in Layer 3.
3. Make no file system writes. After producing the report, halt.

### D-Sync (vault → ora)

1. For every pair classified as `vault-newer` or `body-different` (with vault-newer tag) AND not in a vault-only category:
   a. Read the vault file.
   b. Apply the rule's YAML transformation to produce the ora-bound content (strip vault YAML for `frameworks/book/` targets; preserve as-is for paths where ora has its own YAML; preserve verbatim where neither side has YAML).
   c. Backup the existing ora file: `cp <ora_path> <ora_path>.bak`.
   d. Write the transformed content to the ora path.
   e. Log the operation: ora path, pre-size, post-size, .bak path.
2. For pairs classified as `ora-newer`, `body-different` with ora-newer tag, or any other ambiguous case, do NOT write. Surface them in a "Conflicts deferred" section of the output. The user must explicitly choose D-Accept-Ora or manual resolution.
3. After all writes, produce the sync log.

### D-Accept-Ora (ora → vault, explicit)

1. Read the user's explicit pair list. For every entry:
   a. Confirm the entry references an existing vault file. IF not, log an error and skip.
   b. Confirm the corresponding ora file exists. IF not, log an error and skip.
   c. Read the ora file body (apply body normalization).
   d. Read the vault file's YAML block (preserve it).
   e. Construct the new vault content as: `<vault YAML block>` + blank line + `<ora body>`. (If vault had no YAML, the new content is just `<ora body>`.)
   f. Backup the existing vault file: `cp <vault_path> <vault_path>.bak`.
   g. Write the new content to the vault path.
   h. Log the operation: vault path, pre-size, post-size, .bak path.
2. After all writes, produce the reverse sync log.

### D-Bootstrap (ora-only → vault)

1. For every pair where vault side is missing and ora side exists AND the ora path matches a registered Pairing Rule:
   a. Compute the canonical vault path per the rule (filename transformation as specified).
   b. Confirm the vault path does not already exist. IF it does, refuse to overwrite — log as conflict.
   c. Read the ora file verbatim.
   d. Write the verbatim content to the vault path.
   e. Log the operation: ora path, vault path created.
2. After all writes, produce the bootstrap log.

### Invariant check at end of Layer 4

Before proceeding to Layer 5: confirm that the count of writes matches the count of log entries. Any silent write or silent skip is a structural failure.

## LAYER 5: SELF-EVALUATION

**Stage Focus:** Evaluate the operation's output against the seven Evaluation Criteria.

**Calibration warning:** Self-evaluation scores are systematically inflated. Score conservatively. Articulate specific uncertainties alongside scores.

For each of the seven Evaluation Criteria:

1. State the criterion name.
2. Wait — verify the operation's output against this criterion's rubric before scoring.
3. Identify specific evidence in the operation log or report that supports or undermines each score level.
4. Assign a score (1-5) with cited evidence.
5. IF the score is below 4, THEN:
   a. Identify the specific deficiency (with reference to the operation log).
   b. State the specific modification required to raise the score.
   c. Apply the modification if possible within scope (e.g., add missing log entries).
   d. Re-score after modification.
6. IF the score meets or exceeds 4, THEN confirm and proceed.

After all criteria are evaluated:
- IF all scores meet threshold, proceed to Layer 6.
- IF any score remains below threshold after one modification attempt, flag the deficiency in the output with the label `UNRESOLVED DEFICIENCY` and state what additional input or iteration would resolve it.

## LAYER 6: ERROR CORRECTION AND OUTPUT FORMATTING

**Stage Focus:** Final verification, formatting, and delivery.

### Error Correction Protocol

1. Verify factual consistency: every file mentioned in the log corresponds to a real file system path. Flag any inconsistency.
2. Verify count consistency: the number of pairs reported matches the number of pairs discovered in Layer 2.
3. Verify backup completeness: every overwrite operation in the log is paired with a `.bak` path.
4. Verify direction adherence: confirm no writes went in an unauthorized direction.
5. Verify conflict surfacing: every conflict identified in Layer 3 or 4 appears in the output's conflict section.

### Output Format

The output has three sections, in this order:

```
# DRIFT FRAMEWORK REPORT — <mode>

## Conflicts and Decisions Required

[Every conflict, ambiguous pair, ora-newer, unexpected vault-only, or refused operation. If none: "None."]

## Operation Log

[Per-mode log: detection report categories OR sync writes OR reverse sync writes OR bootstrap creations.]

## Self-Evaluation

[Score per criterion with one-line evidence; UNRESOLVED DEFICIENCY entries if any.]
```

### Missing Information Declaration

Before finalizing, state:
- Any pair where classification was uncertain due to file-read errors.
- Any operation skipped because preconditions were not met.
- Any category in the Pairing Rules table that produced zero pairs (could indicate the category is empty, or that the rule needs adjustment).

## NAMED FAILURE MODES

**The Wrong Direction Trap:** Writing to vault during a D-Sync operation, or to ora during a D-Accept-Ora operation. Correction: confirm the operation mode at the start of Layer 4 and gate every write by mode; never write outside the mode's authorized direction.

**The Silent Overwrite Trap:** Overwriting a file without producing a `.bak` because the backup step was skipped, errored, or omitted from the log. Correction: treat the `.bak` operation as a hard precondition for the write; if the backup fails, refuse the write.

**The Vault-Only Confusion:** Treating a `Reference — Framework —` file as ora-bootstrap-eligible because it lacks an ora pair. Correction: the `Reference — Framework —` prefix means "intentionally vault-only"; never push to ora and never report as missing-from-ora.

**The Pairing Mismatch:** Applying the wrong Pairing Rule to a file because two patterns could match. Correction: apply Pairing Rules in the order listed in the table; the first match wins; the table is intentionally ordered most-specific-first.

**The Generated Artifact Inclusion:** Treating a generated runtime file (e.g., `mindspec/default-mindspec.md`) as canonical content. Correction: the Excluded Ora Paths list is authoritative; any path matching it is silently excluded from discovery.

**The Stale-Mtime Trap:** Trusting filesystem mtime as authoritative when a YAML `date modified` says otherwise (or vice versa). Correction: filesystem mtime is the single source of truth for newer/older classification. YAML dates are advisory, not load-bearing.

**The Symlink Confusion:** Following a symlink at the vault path and treating its target as the vault file. Correction: if a vault path is a symlink, surface it as an anomaly. Symlinks under vault root were retired in the 2026-04-27 migration; their reappearance indicates a regression.

**The Bootstrap Overwrite:** Writing a vault file during D-Bootstrap when one already exists at the destination path. Correction: bootstrap operates only on missing vault targets; existing vault files are off-limits in this mode.

---

## EXECUTION COMMANDS

1. Confirm you have fully processed this framework and the user's input below the USER INPUT marker.
2. IF the operation mode is missing or invalid, THEN list the four valid modes and request a corrected input.
3. IF the operation mode is `D-Accept-Ora` and the explicit pair list is missing, THEN refuse to proceed and request the pair list.
4. IF any required input is ambiguous, THEN state what you understand, what you are uncertain about, and what assumptions you will make if not corrected. Wait for confirmation before proceeding.
5. Once all required inputs are confirmed, execute the framework. Process each layer sequentially. Produce the report specified in Layer 6.

---

## USER INPUT

[Mode: D-Detect | D-Sync | D-Accept-Ora | D-Bootstrap]
[Optional pair filter: ]
[For D-Accept-Ora, explicit pair list (one vault path per line): ]
