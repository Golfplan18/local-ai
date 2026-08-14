# Execution Review — Phase 8 · Chunk C pre-implementation ADDENDUM (Rev 4)
## Adapter families: final schemas, filler registry, `.ora/tools` deployment + protection, reachability, judge-P3 paths

*Thread: Execution Thread. Date: 2026-07-05. Design base: `phase8-design.md` **Rev 4** (§4 + §8; the ⚖ Rev-3/Rev-4 folds are binding). Anchors verified against **`157cfe31`** (= current origin/main = the Chunk-B landing) in the pinned read-only worktree `phase8c-scout`. Gate: LIGHT design check-in — NO code. Chunk B is LANDED, so every integration point below is real code.*

*__Rev 4 (2026-07-05) — judge design check-in APPROVED WITH CONDITIONS; all three P2 conditions folded (no blockers).__ (C1 — probe manifest coverage) `deploy_probe:<kind>` action names will NOT resolve against a single `deploy_probe` manifest entry (`manifest_axes` is exact-match, `tool_events.py:209` → fail-closed to secret), AND `_redact_for_record` (`tool_events.py:466`) keys off the EVENT's own `sensitivity` field (default `secret`), not the manifest → §4 now ships **per-kind manifest entries** (`deploy_probe:{page,sitemap,feed,headers,git_heartbeat}`) AND requires each probe event to carry an explicit `sensitivity: public`, with per-kind tests proving sanitized refs survive both the redaction path and a manifest lookup. (C2 — `git fetch` is not read-only) `git_heartbeat.fetch:true` mutates local remote-tracking state, contradicting the read/public event posture → **`fetch` is REMOVED from Chunk C**; `git_heartbeat` is LOCAL-remote-tracking-ref inspection only (honest read/public); a live-fetch heartbeat with honest write/external axes is deferred to Chunk D (where the MSI recipe lives). (C3 — in-place `title_universe` false-fails new notes) the in-place builder used `git ls-tree <before_head>` (the OLD tree, missing the turn's untracked new notes → a new note linking a new note false-dangles) → §2.2 now builds the in-place universe from `git ls-files --cached --others --exclude-standard` (current tracked + untracked), with a two-newly-created-linked-notes regression. Rev 3's structure/decisions are otherwise unchanged and judge-verified.*

*__Rev 3 (2026-07-05) — adversarial pre-check fold (4-lens critic × per-finding verify; the code-fidelity lens + 2 verifiers died on a mid-run model rate-limit → their findings + both null votes were RE-VERIFIED BY HAND against `157cfe31`). 10 distinct findings folded (1 BLOCKER + 5 MAJOR + 4 MINOR); 1 correctly rejected.__ Headline: __the vault family was UNREACHABLE on a live turn as Rev 2 specified__ — no seam resolves `repo_root` to the vault; discovery always lands on `~/ora` (§1.10 + §3.0 reframe + judge item 1). Also folded: the `/.ora/` protection rule was case-bypassable on macOS + blind to git-mediated writes (§6 rewritten); the `changed_files` builder listed DELETED paths → false-FAIL → false escalation on routine vault deletes (§2.2 + §3 fixed); declared lanes never filled on the source-read-only branch (§2.3 fixed); the `inputs_dir` builder placement was misassigned to a caller that lacks `delta_commit` in scope (§2.2 pinned); sparse-checkout durably writes `extensions.worktreeConfig` into the user's vault `.git/config` (§3.5 disclosed); a wrong §1 substrate claim about the sandbox read surface (§1.9 corrected); render_inspect on SEC-2 repos was structurally refused (§5 routed). Rev 2's structure is preserved; the ⚖ marks below are the folds.*

*__Rev 2 (2026-07-05) — superseded structure retained.__ Re-based Rev 1 on the design's binding ⚖ Rev-3 folds: self-contained check scripts in the target repo's own `.ora/tools/` (materialize in the isolated worktree via the delta commit; no git and no ora import inside the sandbox), title universe an actuator-prebuilt check INPUT. Rev 1's tmp-bundle staging + placeholder machinery retired.*

---

## 0. What this pins

Final, implementable shapes for design §4, now reachability-honest: (1) lane-declaration + filler-registry schemas incl. the source-read-only branch (§2.1–2.3); (2) the check-INPUTS mechanism with builder placement pinned per call site (§2.2); (3) the vault family's deployment, deleted-path handling, catalog, reachability, and sparse residue (§3); (4) deploy_probe vocabulary + the mandatory `web_fetch` extension + `rollback` (§4); (5) render_validity + its SEC-2 routing (§5); (6) the `.ora/` protection decision — case-folded + git-route-covered (§6); (7) judge-P3 paths + Windows fixtures. Scope fences §8; judge items §10 (headlined by the reachability decision).

## 1. Substrate facts the decisions lean on (scout- + hand-verified @ 157cfe31)

1. **Chunk B is landed as designed:** `run_isolated_checks` (`execution_loop.py:361-449`) = prune → backend-gate → `tree_commit_at` → `create_isolated_worktree` → `run_contract(…, worktree=wt, mode="clean_worktree")` → finally-remove. `create_isolated_worktree` accepts `sparse=` but **no caller passes it** (`evidence_runner.py:1078-1084` defers the sparse opt-in to THIS addendum — including its disclosed side effect, §3.5).
2. **`tree_commit_at` (`evidence_runner.py:1001-1045`)** is the ONLY `delta_commit` producer, called ONLY inside `run_isolated_checks` (`execution_loop.py:407`). `base_sha` there = `before_head` (the stashed pre-exec HEAD). An in-place `run_contract` call (`execution_loop.py:582-585`) has `before_head` but NO delta commit.
3. **NO check-inputs mechanism exists:** the sandbox allows reads of the worktree + the per-check `run_tmp`; `run_tmp` is created and destroyed INSIDE `_run_check_impl` (`evidence_runner.py:742-786`); argv is executed verbatim (only `python`/`python3` → `sys.executable`, `:341-344`). `_clean_env(work_home, tmpdir)` (`:303-325`) keeps only PATH/LANG/LC_ALL + sets HOME/TMPDIR — a new env var needs an explicit injection point. §2.2 adds the mechanism.
4. **NO filler registry:** dispatch is two hardcoded signal-keyed call sites in `run_loop` (`fill_provenance_lane` at `:1175`/`:1229`; `evidence_runner.fill_evidence_lanes` via `run_capture` at `:605`), each filler self-locating its lane by name-string scan. `run_observe`/`render_inspect`/`deploy_probe` exist only in the `EvidenceLane.lane` comment (`execution_packet.py:74`).
5. **`converged()` reads `capture.sufficient` + findings — NEVER lanes** (`all_evidence_sufficient` has no production caller). A new lane's `sufficient` cannot gate convergence. But a filled diff_validate check that FAILED does gate: `contract_sufficient` False (`evidence_runner.py:1241-1257`) → `converged()` False + `ran_and_failed()` True (`execution_loop.py:150-165`) → `escalation_warranted()` (`:909-923`). **This is the false-escalation vector §2.2/§3 must not trip.**
6. **Renderer leak hazard for new lanes:** any non-provenance lane renders via the generic template — a filled-but-failing lane emits the bare `INSUFFICIENT` token into the verifier prompt (`execution_packet.py:289`); `durable_summary` suppression is provenance-branch-only (`:203-256`). New lanes need dedicated render branches + durable_summary handling.
7. **Durable lane scrub auto-covers new lanes IFF results stay JSON-primitive** (`execution_persistence.py:329-399`): every lane's `generated_by` + `result` walked (str/list/dict only — tuples/objects pass UNSCRUBBED); URLs under `ref`/`map_ref`/`delta_ref` keys or plain str leaves; short fixed-vocab tokens survive sensitive turns only if in `_LANE_STRUCTURAL_KEYS`.
8. **`web_fetch` cannot serve the declared probe vocabulary as-is:** returns `{url, markdown, title, channel, fetched_at[, error]}` — no status code (only `error: "HTTP <code>"` strings ≥400 with the tier pinned), no headers, no timeout parameter; `channel="auto"` cascades a 403 through Playwright/Jina so the origin status is lost (`web_fetch.py:86-92,156-157,273-283`). §4's extension is mandatory, not optional. Its Chunk-A library guard records each call automatically; the loop terminal runs on the turn's thread → filler fetches file to the turn trace with correct stealth/conversation context.
9. **⚖ Rev 3 (corrected substrate):** the SBPL profile is **`(allow default)` + deny-reads over four private roots ($HOME, WORKSPACE, VAULT, CONVERSATIONS, `_private_deny_roots` `:503-512`) + worktree/run_tmp re-allows** (`_macos_profile` `:545-572`) — NOT "reads of exactly the worktree + run_tmp." Reads OUTSIDE the deny roots (the interpreter, site-packages incl. PyYAML) are open — which is *why* the self-contained scripts import PyYAML at all. The inputs dir is under `SCRATCH_DIR` = `ORA_HOME/scratch` = under two deny roots, so it needs an explicit read re-allow (a re-allow punched into a denied root, not an increment to a default-deny allowlist). Design states the correct shape verbatim (`phase8-design.md:206`).
10. **⚖ Rev 3 (BLOCKER substrate):** on a LIVE turn `repo_root` ALWAYS resolves to `~/ora`, never the vault. Nothing sets `context_pkg['repo_root']`; `ORA_PROJECT_ROOT` is exported only to project-tool subprocesses (`project_registry.py:917`), never the server process; both planning seams call `apply_evidence_contract(...)` with no `repo_root` (`boot.py:9414`, `server.py:2880`); server cwd = `WORKSPACE` = `~/ora`, which has its own `.ora/evidence.yaml`, so `discover_repo_root`/`discover_catalog` (`execution_loop.py:185-214`, `evidence_runner.py:272-299`) terminate on the ora repo. §3.0 reframes the vault family's reachability around this.
11. **Protection today:** `is_protected_config_path` (`tool_events.py:285-297`) = exact-basename set + WORKSPACE-anchored prefixes, consulted only for surfaced write paths (`dispatcher.py:602-636`); the key is `_cmp_key` = `normcase(realpath())` — **`normcase` is a no-op on darwin**, and git subcommands surface NO write paths (`bash_execute._command_target_paths` `:273-387` has no git branch; `_segment_axes` `:437-454` maps git checkout/restore/mv → `reversible_write`). §6 fixes both.
12. **Vault reality:** git repo; no `.ora/` yet; `.gitignore` = 3 lines (`MSI News/` untracked → 15,178 files invisible to git; `.obsidian/` mostly TRACKED). 137,647 tracked files. Frontmatter NOT universal (~79 legacy notes lack it; 5 root notes lack `type`); `type` near-universal among frontmatter-bearing root notes (647/652). Live wikilinks ~99.3% bare-title; 43 broken legacy `[[Library/…]]` path links in Resources/. Basenames unique vault-wide except 4.
13. **Evidence Contract** = `run_evidence_contract_pass` (model pass; catalog-restricted parse) carrying `{required_standard_checks, bespoke_probes, sufficiency, repo_less}`; only the first is consumed. `apply_evidence_contract` (evidence_runner, NOT risk_gate) stashes `context_pkg["evidence_contract"]`. The catalog is a local inside `run_capture` (re-discovered per iteration) — the landed re-parse-per-seam idiom.

## 2. §4.1 — lane declaration + filler registry (final)

### 2.1 Declaration: one protected file, two blocks (additive)

`.ora/evidence.yaml` gains one optional top-level block; extended `parse_catalog` keeps old catalogs valid and errors LOUDLY on unknown keys in the new block:

```yaml
recipes:                       # named, repo-declared, write-protected (§6)
  <name>:
    lane: deploy_probe | render_inspect | run_observe
    target: <short label>
    standing: false            # true → run on programmatic record_program_run (Chunk D)
    probes: [ <§4 spec> ]      # deploy_probe recipes
    rollback: <string>         # MANDATORY for deploy_probe (⚖ Rev 3) — absent = validation ERROR
    check: <catalog check name> # render_inspect recipes — must exist under checks:
```

The **Evidence Contract** gains `lanes:` the way `required_standard_checks` works: the prompt lists catalog recipe NAMES; `_parse_contract` keeps only names present in the catalog (**the model cannot invent a probe/recipe** — §16-2). Shape `"lanes": [{"lane","target","recipe"}]`.

**Emission:** `route_lanes` keeps its two observed lanes and gains `declared:`; `build_execution_packet` passes the contract's `lanes` entries; dedup by `(lane, target)`. Declared lanes emit DECLARED-EMPTY (`sufficient=None`).

### 2.2 The check-INPUTS mechanism + builder placement (⚖ Rev 3 — placement pinned)

Delta-scoped checks need harness-derived inputs readable in-sandbox, WITHOUT staging into the user's live tree (the vault autocommit would sweep them) and WITHOUT breaking the worktree's byte-equality to the delta commit. Mechanism:

- `run_check`/`run_contract`/`run_isolated_checks` gain `inputs_dir: str | None = None` — a directory under `SCRATCH_DIR/evidence-runner/inputs-<id>` (mkdtemp), SBPL-char pre-flighted, **read-only re-allowed** in the profile, exported to the check as env **`ORA_CHECK_INPUTS`** via an extended `_clean_env` (env, not argv — argv is exec'd shell-free and cannot expand variables). Removed finally-guaranteed.
- Catalog `checks.<name>` gains optional **`inputs: [changed_files | title_universe]`** and **`scope: repo | changed_files`** (default `repo`), both validated against fixed vocabularies.
- **⚖ Builder placement (the fix — each builder lives where its base is in scope):**
  - **Isolated batch:** `run_isolated_checks` builds the inputs dir (it holds `base_sha`=`before_head` AND `delta_commit`) BEFORE its `run_contract` call. `changed_files` = `git diff --name-only --diff-filter=d <base_sha> <delta_commit>` — **`--diff-filter=d` (lowercase = EXCLUDE deleted)** so a deleted/renamed-away path never enters the list (⚖ Rev 3 false-FAIL fix, §5 of the finding set). `title_universe` = `git ls-tree -r --name-only <delta_commit>` (object-DB read, no checkout).
  - **In-place path:** `run_capture` builds the inputs dir before the in-place `run_contract` call (it holds `before_head`). `changed_files` = `git diff --name-only --diff-filter=d <before_head>` ∪ `git ls-files --others --exclude-standard`. `title_universe` = **`git ls-files --cached --others --exclude-standard`** — the CURRENT working tree's note set (tracked + untracked), **not** `git ls-tree <before_head>` (⚖ Rev-4/C3: the base tree omits the turn's own untracked new notes, so a new note linking another new note would false-dangle). The isolated path's `title_universe` = `git ls-tree -r --name-only <delta_commit>` already covers new notes because `tree_commit_at`'s `add -A` captured them into the delta commit — the two derivations differ in mechanism but both yield the note universe *as it exists at check time, including this turn's new notes*. This closes the Rev-2 gap where `title_universe` had no in-place derivation (native-Linux `unshare` runs vault checks in place — §7).
  - Both builders run OUTSIDE the sandbox (git works there), are mechanical, and record the input names on the check's `evidence_check` event (`inputs: [...]` — observed, not narrated, §16-3).
- A check declaring inputs with no stashed base (base-unknown) REFUSES with `skip_reason: "declared inputs unavailable (base-unknown)"` — never a guessed input.
- **Belt (defense-in-depth):** scripts SKIP a listed-but-absent file with a `skipped_missing` count rather than crashing — so even if a deleted path slips the diff-filter, the check degrades to honest-skip, never a false-FAIL that trips §1.5's escalation vector.
- **Sparse opt-in:** when EVERY check in an isolated batch declares `scope: changed_files`, `run_isolated_checks` passes `sparse = changed paths ∪ [".ora"]` (so scripts + catalog materialize). Any `scope: repo` check → full checkout. See §3.5 for the sparse `.git/config` residue disclosure.

### 2.3 The filler registry (⚖ Rev 3 — both engaged branches covered)

Module-level registry in `execution_loop`:

```python
LANE_FILLERS = {
  "diff_validate":      <adapter → run_capture/fill_evidence_lanes — existing path, unchanged>,
  "collect_provenance": <adapter → fill_provenance_lane — existing path, unchanged>,
  "deploy_probe":       fill_deploy_probe_lane,      # new, §4
  "render_inspect":     fill_render_inspect_lane,    # new, §5
  "run_observe":        None,                        # DECLARED-ONLY in Phase 8 — no filler shipped
}
```

New-filler protocol: `fill(packet, lane, *, fill_ctx) -> summary | None`, `fill_ctx = {context_pkg, recipe, catalog, repo_root, capture, trace_dir, stealth}` where **`capture` MAY be None** (the source-read-only branch has no capture — see below). The declared fillers (deploy_probe, render_inspect) do NOT consume `capture`; the two existing lanes are filled by their own paths, not the registry, so their entries are thin adapters with ZERO behavior delta (parity by construction).

**⚖ Both engaged branches (the fix):** a helper `fill_declared_lanes(packet, fill_ctx)` iterates packet lanes with `sufficient is None` + a registered non-None filler + a matching declared recipe, and is called in BOTH places: (a) the mutation branch AFTER `run_capture` (`capture` set), and (b) the source-read-only branch BEFORE its early return at `execution_loop.py:1202` (`capture=None`). Rev 2's "one post-capture step" was unreachable on the source-read-only branch (it returns before any capture exists) — this corrects the invariant so a declared lane with a filler + recipe fills on either engaged branch; only genuinely no-filler/no-recipe lanes stay owed.

**Convergence + render fences:** `converged()`/`should_engage` UNTOUCHED — new-lane sufficiency is record+render, never a convergence input (OQ-4). Both new lanes get DEDICATED render branches that (a) never emit the bare `INSUFFICIENT` token (informational headers, e.g. `DEPLOY PROBE (informational — not a convergence input in this phase)`), (b) implement `durable_summary=True` as verdict-counts-only (no URLs, no stdout, no rollback free-text), (c) keep `lane.result` strictly JSON-primitive with URLs under `ref` keys `sanitize_url`-cleaned at build time → the §2.6 durable scrub covers them. `_LANE_STRUCTURAL_KEYS` gains `"verdict"` (fixed vocab PASS/FAIL/INDETERMINATE).

## 3. §4.2 — vault family (final)

### 3.0 ⚖ Rev 3 — reachability (the BLOCKER; headline judge decision)

Rev 2 asserted "vault checks ride the diff_validate lane through the Chunk-B worktree" as if `repo_root` could be the vault — but on a LIVE turn it never is (§1.10). Worse, live-turn reach is architecturally hard: `snapshot_pre_execution` captures the pre-exec base at PLANNING against the cwd-default repo (`~/ora`), *before* the turn reveals which repo it touched, so even retargeting at the terminal leaves no valid vault base (→ base-unknown → owed). **Decision (recommend, judge's call — item 1):** the vault family lands reachable via **explicit `repo_root`** — the test suite (real integration), programmatic/recipe runs, and Chunk D's `record_program_run` (which takes an explicit repo + event-log reference). **Live-chat-turn vault reach is a NAMED, LOUD follow-up** requiring a distinct pre-execution multi-repo targeting + base-capture seam — NOT smuggled onto the families chunk. This is consistent with design §3.4 ("Phase 8 does NOT silently reroute live chat-turn tool writes") and the honest-deferral discipline. The vault family is thus a real, tested, landed capability exercised exactly as MSI's will be (Chunk D) — with no false claim of live reach. A minimal explicit hook (`context_pkg['repo_root']` honored by the existing `discover_repo_root` first branch) is the substrate a future live seam will build on; Chunk C wires the family end-to-end THROUGH that hook and tests it against a real scratch vault-shaped repo.

### 3.1 Deployment (binding ⚖ Rev-3 shape)

Two self-contained single-file scripts in the TARGET repo's **`.ora/tools/`** — `vault_frontmatter_lint.py`, `vault_wikilink_check.py`. Python stdlib + PyYAML only (sandboxed interpreter = `sys.executable` = ora's own → PyYAML present via the allow-default site-packages read, §1.9; PyYAML-import failure → machine-readable error + exit 3, an honest failure). Import-scan test asserts zero `orchestrator.*`/third-party-beyond-yaml. **Canonical copies in ora's own `.ora/tools/`** (write-protected by §6; exercised AS SUBPROCESSES against fixtures) + a family README documenting the copy-into-repo pattern. No git and no ora imports inside the sandbox (OQ-8 stays closed).

### 3.2 Script contracts

Argv static; inputs via `ORA_CHECK_INPUTS`; stdout machine-readable JSON; exit 0 iff ok, 1 on findings, 2 usage, 3 tooling-unavailable; **absent listed file → `skipped_missing++`, never a crash** (§2.2 belt):

- `vault_frontmatter_lint.py --frontmatter optional|required --require <k1,k2,…>` — reads `$ORA_CHECK_INPUTS/changed-files.txt`, filters `.md`, STRICT `yaml.safe_load` of each leading `---` block. **Malformed ≠ absent:** malformed always FAILs; absent FAILs only under `--frontmatter required`; `--require` checked only on frontmatter-bearing files. Output `{checked, malformed:[{file,error}], missing_frontmatter:[…], missing_required:[{file,keys}], skipped_missing, ok}`.
- `vault_wikilink_check.py [--allow-file <repo-relative path>]` — reads changed `.md` BODIES (frontmatter stripped), extracts `[[target]]` handling alias (`|`), heading (`#`), embed (`![[…]]`); resolves against `$ORA_CHECK_INPUTS/title-universe.txt` (for `.md` universe entries the resolvable name = basename-minus-`.md`, Obsidian bare-title semantics; non-`.md` entries by full basename for SVG embeds; path-form targets by full relative path). Dangling → FAIL. Output `{checked, links, dangling:[{file,target}], allowed_skips, skipped_missing, ok}`.

### 3.3 Vault catalog

NEW tracked file `<vault>/.ora/evidence.yaml` (runtime derivation: `runtime_paths.VAULT`). Chunk C lands files in TWO repos (ora + vault):

```yaml
checks:
  vault-frontmatter:
    argv: [python, .ora/tools/vault_frontmatter_lint.py, --frontmatter, optional, --require, type]
    mutates: false
    timeout: 120               # provisional — delta-scoped, expected <5s
    network: deny
    inputs: [changed_files]
    scope: changed_files
  vault-wikilinks:
    argv: [python, .ora/tools/vault_wikilink_check.py, --allow-file, .ora/tools/wikilink-allowlist.txt]
    mutates: false
    timeout: 120               # provisional
    network: deny
    inputs: [changed_files, title_universe]
    scope: changed_files
runner:
  working_dir: <repo-root>
  env: isolated
  network: deny
  redact: by-sensitivity
  on_unknown: gated
```

### 3.4 Recipe choices + recorded limitations

**Provisional (catalog-retunable, per the tuning-constants discipline):** `--frontmatter optional` (79 legacy frontmatter-less notes must not fail); `--require type` (near-universal; 5 known type-less MSI notes fail only IF touched — desired surfacing); `wikilink-allowlist.txt` pre-seeded with the 43 known-broken legacy `[[Library/…]]` targets. **Limitations:** (i) `MSI News/` gitignored → absent from title universe AND delta commit → links into it would false-dangle (no inbound bare-title links found; allowlist is the escape hatch); (ii) delta-scoping surfaces PRE-EXISTING dangles in a touched file on the touching turn (defensible — touching a file makes its links current business); (iii) `relationship_graph` claim-resolution enrichment stays OUT of the sandboxed check (ora-import-dependent; possible later filler-side enrichment per ⚖ Rev 3 — engram cross-refs are YAML `relationships`, not body wikilinks).

Vault checks ride the EXISTING `diff_validate` lane through the Chunk-B worktree (SEC-2 routing, sparse per §2.2) — a catalog + tools recipe, NOT a new lane.

### 3.5 ⚖ Rev 3 — sparse residue disclosure

`git sparse-checkout` invoked from a linked worktree durably writes `[extensions] worktreeConfig = true` into the MAIN repo's shared `.git/config` — a permanent, **idempotent** (one-time; later runs no-op) metadata write in the user's vault repo that survives `worktree remove --force` + `prune` (`remove_isolated_worktree` does no config cleanup). This is the exact residue the in-code deferral (`evidence_runner.py:1078-1084`) asked THIS addendum to weigh. **Decision:** accept it (the alternative — full checkout of 137k vault files — is the scale problem sparse exists to avoid), DISCLOSE it as a repo-metadata touch in the packet alongside the design's `.git/worktrees` disclosure (`phase8-design.md:172`), and do NOT attempt cleanup (removing the flag would race concurrent worktrees; it is harmless + idempotent). Recorded as a §10 judge item + a family-README note. Chunk B's ref-less commit already keeps the object side GC-clean; this is config-side, one line, one time.

## 4. §4.3 — deploy_probe (final)

Not a subprocess check (needs network; runner enforces deny-only). A generic in-harness filler executing recipe-declared specs. Vocabulary:

```yaml
probes:
  - { kind: page,          url: <abs-url>, must_contain: <str>, timeout_s: 15 }
  - { kind: sitemap,       url: <abs-url>, must_contain: <str>, timeout_s: 20 }
  - { kind: feed,          url: <abs-url>, must_contain: <str>, timeout_s: 15 }
  - { kind: headers,       url: <abs-url>, header: <name>, max_age_s: <int>, timeout_s: 15 }
  - { kind: git_heartbeat, ref: <remote-tracking ref>, match: <commit-msg substr>, max_age_s: <int> }
```
**⚖ Rev-4/C2 — no `fetch` in Chunk C:** `git_heartbeat` inspects the LOCAL remote-tracking ref ONLY (whatever the ambient system — vault autocommit's `pull --rebase`, MSI's deploy cron — last fetched). A `git fetch` mutates local remote-tracking state and is NOT a read/public probe, so it is excluded from Chunk C; a recipe needing a live fetch is a Chunk-D concern recorded with honest write/external axes. Staleness of the local ref beyond `max_age_s` → INDETERMINATE (never a silent PASS), so a stale local ref is disclosed, not trusted.

**Mandatory `web_fetch` extension (in Chunk C's diff; additive; guard untouched):** the vocabulary is unimplementable on today's return surface (§1.8). `web_fetch` gains optional `raw: bool = False` (httpx tier only — no trafilatura extraction, no min-chars cascade, so XML sitemap/feed bodies survive) and `timeout_s: float | None = None`; the return dict gains `status_code: int | None` + `headers: dict | None` (whitelist: `last-modified, age, cache-control, cf-cache-status, etag, content-type, content-length`), populated on the httpx tier, `None` elsewhere. The Chunk-A library guard records these calls unchanged. Existing callers see two new additive keys (`raw` does NOT bypass any safety — it only skips extraction, which is a readability transform, not a guard).

**Filler semantics:** probes run ONCE, synchronously, at fill time (bounded per-probe timeouts; async poll-with-deadline is Chunk-D orchestration on top). HTTP kinds pin `channel="httpx", raw=True`. Tri-state: `PASS` (200 + condition met) / `FAIL` (condition demonstrably false: 200 without marker, 404/410, header older than `max_age_s`) / `INDETERMINATE` (403/429/edge-challenge, timeout, network error, missing header, heartbeat local-ref staleness — never PASS; reason recorded). `git_heartbeat` reads the LOCAL remote-tracking ref only (`_git log -1 --grep <match> --format=%ct <ref>` age vs `max_age_s`) — no fetch (⚖ Rev-4/C2). Lane `sufficient = all PASS`.

**⚖ Rev-4/C1 — probe event manifest + redaction coverage:** one `deploy_probe:<kind>` tool event per probe, modeled on `_record_check_event`'s axes (`category: read, sensitivity: public, egress: external/none, enforcement_model: in_harness`). Two mechanically-distinct requirements, both load-bearing: (i) **per-kind `ACTION_MANIFEST` entries** — `deploy_probe:page`, `deploy_probe:sitemap`, `deploy_probe:feed`, `deploy_probe:headers`, `deploy_probe:git_heartbeat` (five explicit entries; a SINGLE `deploy_probe` entry would NOT match under `manifest_axes`'s exact-match lookup [`tool_events.py:209`] → fail-closed to secret/irreversible → the gate blocks the probe). Exact-match per kind is chosen over a `manifest_axes` prefix resolver because the kind vocabulary is a fixed closed set of five and exact-match is the existing, unsurprising semantics. (ii) **each probe event carries an explicit `sensitivity: "public"` field** — `_redact_for_record` (`tool_events.py:466`) keys off the EVENT's own `sensitivity`, defaulting to `secret` when absent (which strips `reads[]`/args), NOT off the manifest; the manifest fix alone does not save the payload. URLs pass `sanitize_url` before events AND lane results. Tests assert, per kind, that a sanitized probe ref survives BOTH the redaction path (explicit-public event) AND a `manifest_axes("deploy_probe:<kind>")` lookup (non-fail-closed axes).

**Rollback (⚖ Rev 3, mandatory):** every deploy_probe recipe carries `rollback: <recovery ref | "none: <recovery contract>">`; absence = catalog validation ERROR; the renderer prints it with results (suppressed on `durable_summary`). Lane result (scrub-conformant): `{probes:[{kind, ref, verdict, reason, http_status?, age_s?}], rollback: <str>, verdict_counts: {...}}`.

## 5. §4.4 — render_validity (final) + ⚖ Rev 3 SEC-2 routing

Self-contained `.ora/tools/render_validity.py` (stdlib only — `zipfile` docx/pptx/xlsx, `xml.etree` SVG, `%PDF-` PDF header, exists+nonzero), canonical copy in ora's `.ora/tools/`, declared as a normal catalog check with `inputs: [changed_files]`, `scope: changed_files`, `network: deny`, `mutates: false`; filters the changed list to its extensions, **skips missing files** (§2.2 belt — a deleted artifact never false-FAILs), exits 0 when none match (vacuously ok). Output `{checked, invalid:[{file,reason}], skipped_ext, skipped_missing, ok}`.

A `render_inspect` RECIPE (`{lane: render_inspect, check: render-validity}`) routes the result onto a `render_inspect` lane via the §2.3 filler. **⚖ Rev 3 SEC-2 routing (the fix):** the filler runs the named check via `run_check` in-place on a NORMAL repo, but when `requires_isolated_worktree(repo_root)` is true (SEC-2), it routes through the SAME isolated-worktree machinery the vault family uses (`run_isolated_checks` for the named check) — Rev 2's in-place-only spec would have been structurally REFUSED on SEC-2 repos (the Chunk-B worktree is already removed by fill time; in-place is SEC-2-refused). No Phase-8 SEC-2 repo declares a render_inspect recipe, but the schema permits it, so the routing must be defined not left to crash. Perceptual quality stays a judgment lane with `verdict: null` — no tool, out of Phase 8 (§5 category-error guard). Family README rides ora's `.ora/tools/README.md`.

## 6. ⚖ Rev 3 — `.ora/` protection (case-folded + git-route-covered)

A check script is as load-bearing as the catalog that names it; the Chunk-B delta commit materializes the turn's OWN `.ora/tools/` edits for that turn's isolated review, so an executor weakening its own check is the grading-your-own-homework loop (spec §12, the "load-bearing integrity risk"). **Decision: extend `is_protected_config_path` with a repo-agnostic path-segment rule — a key containing `/.ora/` or ending `/.ora` is protected in ANY repo — AND fix two verified holes:**

1. **Case-fold the comparison (MAJOR fold).** `_cmp_key` = `normcase(realpath())`, but `normcase` is a no-op on darwin and APFS is case-insensitive, so `<repo>/.ORA/tools/check.py` opens the same file yet evades a case-sensitive `/.ora/` match (and evades the EXISTING `evidence.yaml`/prefix protection too — a latent pre-existing defect). Fix: `is_protected_config_path` lowercases its comparison key for protected-path matching (mirroring the sibling `_matchable` at `tool_events.py:61-69`, which already lowercases). This hardens the new segment rule AND the existing basename/prefix matching on macOS/Windows — strictly safer (previously-evading case variants now gate).
2. **Cover git-mediated writes (MAJOR fold).** Protection is consulted only for surfaced write paths, and `git checkout/restore/mv/apply` surface none (§1.11), so an executor can `git mv weak.py .ora/tools/check.py` (or `checkout`/`restore` from a ref) ungated and the delta commit materializes the tampered script. Fix: `bash_execute._segment_axes` escalates any git write-subcommand (`checkout`/`restore`/`mv`/`apply`/`rm`/`add` with a pathspec) whose argv contains a `/.ora` (case-folded) path segment to `irreversible` + `protected_config`. (Enumerate `_command_target_paths`/`_segment_axes` call sites at impl per the shared-code discipline.)

**Honest residual (stated, not sealed):** the write-gate raises the bar but is not a complete seal — a sufficiently creative self-edit is fundamentally bounded by the §12 verify stage + planning-set acceptance criteria (spec §10 "green ≠ honest test" — the runner alone never certifies a check the executor authored), which is Phase-6 territory, not the runner's. §6 closes the mechanical routes; the architectural closure is the loop's, and this residual is disclosed. Over-gating fails safe (gate → queued approval). Tests: vault/MSI/`C:\…\.ora\tools\…`/`.ORA`-case-variant/git-mv-into-`.ora` shaped.

## 7. Judge P3 — path derivations + portability

| Surface | Derivation (implemented) |
|---|---|
| Vault catalog + tools | `runtime_paths.VAULT` (env `ORA_VAULT`; a module CONSTANT — **no `vault_root()` accessor**) → `<VAULT>/.ora/…`. Legacy `ORA_VAULT_PATH`/hardcoded-root modules stay a recorded §1.12 limitation. |
| Check argv | Target-repo-RELATIVE (`.ora/tools/<script>.py`); `cwd` = worktree/repo — no roots in argv. |
| Inputs dirs + worktrees | `runtime_paths.SCRATCH_DIR` (env `ORA_SCRATCH`) — `evidence-runner/inputs-<id>`, `exec-review-worktrees/<id>`. |
| Canonical templates | `runtime_paths.ORA_HOME`/`WORKSPACE` → `<ora>/.ora/tools/…` (protected). |
| Containment | `runtime_paths.within_base`/`norm_key` — never `evidence_runner._is_within` (case-sensitive; scout-flagged), never raw `startswith`. |

**Windows-shaped fixtures:** inputs-dir containment + SBPL-char refusal on backslashed paths (refuse honestly, not crash); `changed-files.txt` consumption with git-native `/` on a `C:\` repo; title-universe basename resolution with `\`-normalized fixtures; the case-folded `/.ora/` protection rule on `c:\users\x\repo\.ora\tools\check.py` AND `.ORA` variants; catalog `python` → `sys.executable` on nt. **Platform posture (unchanged, restated):** SEC-2 all-isolated routing is macOS-only; off-mac, vault `network:deny` checks REFUSE where no enforcing backend exists, or run network-denied (native-Linux `unshare`) WITHOUT filesystem containment; the in-place `title_universe` builder (§2.2) is what makes off-mac in-place vault runs defined. deploy_probe is in-harness, platform-neutral.

## 8. Scope fences (Chunk C does NOT)

- Build the pre-execution multi-repo targeting seam for live chat turns (§3.0 — named follow-up; vault family reaches via explicit `repo_root` only).
- Touch `should_engage`/`converged()`/escalation semantics — new lanes are record+render, informational, OQ-4-consistent.
- Ship a `run_observe` filler (declared-only; stated in the registry + README).
- Change the two existing lanes' fill paths beyond registry adapters (zero behavior delta; parity by construction).
- Re-fetch web content beyond declared probe specs (probes ARE reads, each recorded; recipe-bounded, no polling in C).
- Wire MSI anything (Chunk D consumes `standing:` recipes + the MSI catalog).
- Fix the non-uniform vault-root envs, `knowledge_index.index_file` arity bug, or declaration-only runner fields (recorded, not smuggled).

## 9. Test + parity plan

New: `test_vault_check_tools.py` (subprocess runs vs fixture repos: malformed-vs-absent truth table incl. both `--frontmatter` modes + `--require`; **deleted/renamed/absent-file fixtures → skipped_missing, never FAIL**; **⚖ C3: two newly-created linked notes resolve — the new-note→new-note link is NOT dangling** [in-place `git ls-files --cached --others` universe]; wikilink alias/heading/embed/path forms, allowlist, basename-collision + non-md-embed resolution; import-scan self-containment; exit-code contract; Windows-shaped fixtures); `test_deploy_probe.py` (per-kind PASS/FAIL/INDETERMINATE incl. 403/timeout/missing-header/git-heartbeat local-ref staleness; all-PASS sufficiency; **⚖ C1: per kind, a sanitized probe ref survives BOTH the redaction path [explicit `sensitivity:public` event] AND `manifest_axes("deploy_probe:<kind>")` [non-fail-closed]**; **⚖ C2: no `fetch` path exists — git_heartbeat runs zero `git fetch`**; rollback validation error; renderer durable_summary counts-only + no-INSUFFICIENT-token; scrub conformance); `test_render_validity.py` (per-format + vacuous-ok + missing-skip + recipe→lane fill incl. SEC-2 routing). Extended: `test_evidence_runner.py` (inputs_dir lifecycle: creation/read-only-allow/env export/cleanup/SBPL refusal; `--diff-filter=d` deleted-exclusion; **in-place `title_universe` = current tracked+untracked**; `inputs:`/`scope:` validation; sparse-union batch + `.ora` materialization; base-unknown input refusal; mac-gated real-sandbox integration); `test_execution_loop.py` (registry dispatch on BOTH engaged branches incl. source-read-only capture=None + None-filler owed path; declared-lane emission from contract; adapter equivalence for the two existing lanes; **explicit-repo_root vault reach against a scratch vault-shaped repo**); `test_execution_packet.py` (route_lanes `declared=` + dedup); `test_tool_events.py` (case-folded `/.ora/` segment rule incl. `.ORA` + Windows keys; git-mv-into-`.ora` escalation); `test_execution_persistence.py` (deploy_probe/render_inspect scrub walk + `verdict` structural key). Parity: fresh pre-edit baseline in the impl worktree, full suite, diff sorted FAIL/ERROR lists, ZERO NEW vs the ~27 environmental baseline (≈3,982 tests @ 157cfe31; re-measured fresh).

## 10. Open items for the judge (each with a recommendation)

1. **HEADLINE — vault family reachability (§3.0).** The vault (and any non-ora project family) is UNREACHABLE on a live turn (`repo_root` always resolves to `~/ora`; the pre-exec base is captured at planning against the cwd-default repo before the touched repo is known). **Recommend:** land the vault family reachable via explicit `repo_root` (tests + programmatic/recipe runs + Chunk D's `record_program_run`); scope live-chat-turn vault reach as a NAMED follow-up (a distinct pre-execution multi-repo targeting + base-capture seam), not a families-chunk rider. Judge confirms this reading — the alternative is inventing a base-capture-for-an-unknown-repo mechanism inside Chunk C.
2. **`inputs_dir` runner extension + builder placement (§2.2)** — read-only-allowed, env-announced inputs dir; isolated builder in `run_isolated_checks`, in-place builder in `run_capture`; `--diff-filter=d` to exclude deletions; HEAD-based in-place `title_universe`. **Recommend as stated** — smallest honest generalization; keeps the worktree byte-pure; serves in-place delta-scoped checks.
3. **`recipes:` inside `.ora/evidence.yaml`** (single protected file). **Recommend inside.**
4. **`web_fetch` probe extension (§4)** — `raw`/`timeout_s` + `status_code`/`headers` (additive; guard untouched). **Recommend** — the design's declared probe vocabulary is otherwise unimplementable and a bespoke HTTP client is forbidden by §2.3's rule.
5. **`.ora/` protection: case-fold + git-route coverage (§6)** — case-fold the protected-path key (fixes the macOS `.ORA` bypass + hardens existing protection) and escalate git write-subcommands touching `/.ora`; honest residual (verify-stage closure) disclosed. **Recommend as stated.**
6. **Sparse `.git/config` residue (§3.5)** — accept the idempotent one-time `extensions.worktreeConfig` write into the user's vault repo, disclose it in the packet, no cleanup. **Recommend** — sparse is the scale answer; the residue is harmless + idempotent; disclosure meets the design's own standard.
7. **Vault catalog recipe choices (§3.4)** — `--frontmatter optional`, `--require type`, pre-seeded allowlist; all provisional + catalog-retunable. **Recommend as stated.**

---

*Gate: light design check-in — **APPROVED WITH CONDITIONS (2026-07-05); all three P2 conditions folded as Rev 4** (per-kind probe manifest + explicit-public event [C1]; `git_heartbeat` no-fetch [C2]; in-place `title_universe` = current tracked+untracked [C3]). No blockers. NEXT: implement in a fresh worktree off CURRENT origin/main (re-fetch first), adversarial pre-check, parity zero-new vs the ~27 baseline, code-review gate, land per the git workflow (ora repo), then land the vault `.ora/` files (pull → commit → push, own files only). Chunk D's addendum (fresh MSI scout + exact seam list + loop-reach + irreversible-gate posture) follows separately after C lands.*
