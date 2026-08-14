# Ora Execution Review — Architecture & Build Spec

*Status: conceptual foundation approved; instrumentation + capability enforcement added; tier/sensitivity/read contracts tightened; read-classification timing and shell-command policy specified; Phase 5 portability release blocker added; ready as implementation handoff after the Phase 0 call-site audit.*
*A note on the name: "execution review" is the working handle, but the real axis is not execution — it is **observability**. The spec uses "execution" for continuity while treating self-evidencing-vs-not as the governing distinction. Read "execution output" as "output whose correctness depends on reality outside the returned artifact."*
*A note on generality: Ora is a general-purpose tool. Nothing in this spec assumes a particular user's stack. Where a concrete example helps (a Markdown vault, a JS test command), it is an example, not a requirement, and the generic mechanism is named alongside it.*

---

## Amendment — Cross-Platform Portability Is Release-Blocking

All Phase 5 work must run on both macOS and Windows. Treat PC compatibility as a release blocker, not a cleanup item.

Requirements:

- Do not hardcode macOS paths or user-specific paths such as `/Users/oracle`, `/tmp`, `/private`, or Obsidian-vault assumptions. Use `runtime_paths`, `pathlib`, `tempfile`, and environment-derived roots.
- Do not assume POSIX shell behavior on Windows. If Bash/POSIX semantics are required, `ORA_POSIX_SHELL` must point to a real executable and execution must refuse cleanly when unavailable. Do not silently fall back to `cmd.exe`.
- Avoid POSIX-only APIs and assumptions unless guarded and tested: `select()` on stdio pipes, Unix process groups/signals, executable bits, symlink behavior, `/dev/null`, `chmod/chown`, colon path parsing, slash-only paths.
- Evidence catalog commands must not be Mac-only. Prefer platform-neutral Python/subprocess execution. If a check truly differs by platform, declare platform-specific command variants explicitly.
- Every new path root must derive from existing runtime path plumbing, not from the repo location, current user, or OS-specific defaults.
- Add focused tests that simulate Windows path/shell behavior. macOS-only green tests are not enough.
- Every review packet must include a “Portability” section listing the cross-platform surfaces touched, tests added, and any remaining platform assumptions.

The judge should block Phase 5 if any implementation depends on macOS behavior without a guarded Windows-compatible path.

## 1. The problem, stated precisely

Ora's pipeline assumes the output is fully contained in the model's message and can be judged by reading it. A text draft is **self-evidencing**: the evaluator reads the whole thing and judges it directly, because the output *is* the result. Gear 3 and Gear 4 work on text because reading the artifact is sufficient to evaluate it.

That assumption breaks whenever the real result is a change to — or a claim drawn from — some external system, and judging correctness requires generating fresh evidence from that system. A diff tells you *what changed*, not whether it *works*. A research report reads fluently whether or not its facts are true. In both cases the reviewer must go check reality; the message alone cannot be trusted.

The clean statement:

> An output is **non-self-evidencing** when its correctness depends on reality outside the returned artifact. Such outputs cannot be judged by reading the model's message. They require a stage that converts the result into observable evidence, and the review operates on that evidence — not on the artifact, and never on the executor's own report.

This reframe does two loads of work. First, it corrects the category. The dividing line is not *text vs. code* — a generated poem is self-evidencing and goes through text review; a FRED fact-check produces prose but is non-self-evidencing and needs the execution treatment. Second, it fixes the dispatcher. The routing question is not "did this task use a mutating tool" but **"does correctness depend on reality outside the artifact?"** Mutation is one strong signal of that; it is not the whole rule. Read-only reality checks — a regulatory status update, a research pull, a fact-check against an external source — mutate nothing and are still non-self-evidencing.

One dependency to flag at the outset, because the rest of the design leans on it: "go observe reality" presumes Ora can actually *see* the reality contact an agent makes. That is an instrumentation requirement, not a given (§7). A dispatcher that can't observe reality contact can't route on it.

---

## 2. What this actually is

Ora stops being a text-critique engine and becomes a **closed-loop controller over non-self-evidencing outputs** — both state changes and externally grounded claims. A research output grounded in sources is controlled the same way a code change is: produce it, generate observable evidence for it, judge the evidence, revise. The mapping is literal: the acceptance criteria are the setpoint, the executor is the actuator, the Execution Packet is the sensor reading, and the verify stage is the comparator. That is a capability jump — from *reviewer* to *controller* — and it inherits control theory's baggage: the loop is powerful, and it can oscillate without converging. Both facts are designed for below.

It is also a concrete instantiation of the AHI thesis. The move that **demotes the executor's report to a claim and requires observable evidence** is the oracle-fallacy rejection in miniature: the architecture refuses "trust my summary" in favor of "here is the verifiable state," and it keeps the human at the escalation point rather than removing them. The execution-review architecture is not merely AHI-shaped by coincidence; it is evidence for the AHI argument.

---

## 3. Core architecture (settled)

**Single-writer execution, multi-agent judgment.** Only one agent mutates the system at a time. Multiple agents reason before and after the mutation. Parallelism lives only where the thing being merged is still *text*, because text is compositional and state changes are not.

```
Gear 4 Plan        (dual → converge to one brief + evidence contract)
  → Gear 3 Execute (single writer, consuming the brief)
    → Capture      (mechanical evidence generation — not narrated)
      → Gear 4 Verify (dual, independent review of the one delta)
        → Revise    (single writer applies fixes)
          → Re-verify or escalate
```

**Why not parallel execution.** For text, consolidation is synthesis — cheap, because a consolidator can lift a paragraph from A and a paragraph from B and stitch them. Two independent code implementations of the same feature are not compositional: they diverge in file structure, naming, abstraction, and which layer a fix belongs at. "Merge the best of both" for code is not a merge — it is a consolidator re-deriving two implementations it did not write and authoring a third from scratch, after you already paid for two full independent executions. That is the "too many cooks" cost, and it is real. Fan-out belongs at the two points where merging is cheap — **planning** (merging proposed approaches) and **verification** (merging critiques of one delta) — and the expensive middle stays single-threaded.

**The narrow exception where parallel execution is fine.** When it is *cheap to run two attempts* AND *cheap to score them against each other*, running two and picking a winner is parallel search, not consolidation — you never merge, you **select**. Two agents writing a small pure function that tests then judge; two candidate SQL queries compared by output; two scraper selectors decided by browser evidence. Keep this pattern distinct in the design so no one builds a generic diff-merger for it.

---

## 4. Evidence taxonomy — routing vocabulary, not a promise of one adapter each

Every non-self-evidencing result falls into one of five **evidence classes**, grouped by *how you make the result observable*, because that is what determines the reusable machinery. Treat these as adapter **families** plus repo/project-specific recipes — not a guarantee that each class collapses to a single perfect adapter.

**Diff + validate** — structured state you can snapshot before and after: code, note-and-metadata changes (e.g. a linked Markdown vault), config, data-pipeline outputs. Evidence: the before/after diff plus structural validators (tests, YAML/schema lint, backlink integrity, row counts). Characteristic failure: the diff looks right but a validator was never run.

**Run + observe** — behavior you must execute to see: scripts, web-app changes, API integrations, browser automation. Evidence: an execution transcript plus runtime observations (logs, HTTP responses, screenshots, DOM snapshot). Characteristic failure: it compiles but doesn't *do* the thing.

**Render + inspect** — artifacts a human must perceive: slide decks, documents, images, audio, PDF layout. Evidence: the rendered output plus perceptual inspection (visual/audio check, dimensions, export validity). Characteristic failure: the file is valid but the *rendering* is wrong.

**Deploy + probe** — external world state: cloud infra, production deploys, published articles, live services. Evidence: probing the live system (status checks, live-page fetch, cache state, resource inventory) *and a rollback path*. Characteristic failure: the deploy log says success while the live site 500s.

**Collect + verify provenance** — assembled data: research runs, scraping, dataset building, reference libraries. Evidence: a source manifest plus extraction logs, dedup checks, sampling quality, provenance trail. Characteristic failure: plausible data with no traceable origin. Note that the tool-event log (§7) proving a source was *contacted* is necessary but **not sufficient** — it shows reality was consulted, not that it was used correctly. This lane additionally requires source snapshots or URLs with timestamps, the relevant excerpts, and a **claim-to-source map** linking each output claim to the excerpt that supports it. This is the provenance analog of the two-instrument rule: *contacting* the source (event log) and *using it correctly* (claim-to-source map) are different checks, and you need both. Building this map is also the point at which raw reads are finally classified as claim-grounding `source_read`s (§7).

Adapters compose. Publishing an article is *deploy + probe* layered on a *diff + validate* code change; a real task chains adapters rather than needing a bespoke pipeline.

---

## 5. Route by evaluation unit, not by whole task

A task is not one route. It is a set of **evaluation lanes**, each with its own target and standard. This is what makes mixed work tractable: one deliverable can carry a mechanically checkable layer and an irreducibly human layer at the same time, and each is judged in its own lane. Mechanical lanes and judgment lanes are kept **structurally separate**, so a matter of taste can never be dressed up as a passing check.

```yaml
# One task, multiple lanes. Note the two are different KINDS, not two entries in one list.
evidence_lanes:                   # mechanical, verifiable — each yields a real verdict
  - target: factual_claims
    lane: collect_provenance
    check: source / provenance verification + claim-to-source map
  - target: published_page
    lane: deploy_probe
    check: live HTTP + render probe
judgment_lanes:                   # interpretive — reviewer critique, NEVER a mechanical verdict
  - target: voice_quality         # e.g. "is this satirical voice landing"
    critique: human / reviewer interpretation
    verdict: null                 # by construction — no pass/fail exists here
```

The **judgment lane** never receives a mechanical pass/fail. Bolting an evidence stage onto "is this satire landing" or "is this prose good" adds ceremony without adding truth. Separating the observable layer from the judgment layer is exactly what the self-evidencing reframe is designed to enforce: the observable layer (did it render, export, validate, deploy) gets evidence; the judgment layer stays text-review. Pretending a passing render tells you the writing is good is the category error to avoid — which is why the schema (§9) keeps `judgment_lanes` in a separate block with `verdict: null` rather than a `sufficient` field it might accidentally inherit.

---

## 6. The dispatcher — two clocks, decided by cost-of-error

There is a chicken-and-egg trap in pre-classifying route: an agentic task often decides *dynamically* whether to touch the filesystem, and *having* a tool available is not *using* it (a coding agent has Bash and Edit available even when the task is "explain this function"). Pre-classification misfires on exactly the ambiguous cases that matter most. The fix is to stop forcing a pre-decision and split the two decisions onto two clocks, because they have opposite costs of being wrong.

**Routing is decided after the run.** Capture two signals on every non-trivial task, regardless of declared type:

1. **What it changed** — mutations recorded by the instrumentation layer (§7), not inferred from a working-tree hash alone.
2. **What it read as a source of truth** — reads whose content grounds the output's claims (a data fetch, a query, an API call — and, importantly, a *local* file whose contents become claimed facts, including local *code* the output describes rather than merely acts on). This is deliberately narrower than "any read": reading local context to decide *how* to act (browsing your own codebase to decide how to edit it) does **not** count. Only reads the output's correctness *depends on* do. Crucially, this classification is partly **post-hoc** — whether a read grounded a claim can depend on an output that does not exist until the run finishes — so at dispatch Ora uses a cheap over-approximation (did the output make claims about material it read?) and defers precise `source_read` labeling to the provenance lane (§4, §7). Over-routing here is safe, by the same asymmetry that makes conservative risk estimation safe.

*Either* signal takes the output out of pure text review. Mutation says it touched reality; a source read says it drew its claims from reality. If neither fired, the run degrades gracefully to plain text review — no separate classifier, no wrong-pipeline risk. The declared `output_type` is a **hint that sets initial expectations, not a gate that must be right upfront**; observed reality is the primary signal, and the two are consistency-checked (a "text" task that turns out to have changed files or grounded claims in a source, or an "execution" task that produced no delta and no source read, was misrouted).

**These signals are cheap only because instrumentation exists.** A bare working-tree hash catches local file edits but is blind to database writes, network calls, browser actions, and effects buried inside a shell command. The telemetry is cheap *where every tool call passes through an instrumented boundary* (§7) — and where it doesn't, the dispatcher is blind and can route a reality-touching task to text review. That is why §7 is a hard dependency of this section, not an add-on: the "just observe it afterward" design is only as trustworthy as the observation layer beneath it.

*Why after the fact:* getting the route wrong means reviewing the wrong object, which is unsafe. Observing reality first eliminates that.

**Risk is estimated before the run, conservatively, and overridable by the user.** Assign a tier up front. Overestimating risk is *safe* — it just spends more scrutiny than the task needed. This is a different question from routing, on a different clock, for a different reason.

**The hard boundary that ties the two clocks together:** post-hoc routing is permitted **inside reversible tiers only**. For reversible actions (git changes, file edits, note edits) you can look afterward and decide, because anything done is cheap to undo. For irreversible actions (production deploy, email send, payment, published article) the damage is done by the time you observe the delta — so these are classified and **gated before the executor runs, no exceptions**. Note this is consistent with post-hoc *read* classification: writes and irreversibility are knowable at call time and gated then; only claim-grounding read-labeling is deferred (§7). The upfront risk tier is not only a cost dial; for irreversible actions it is a safety gate that must fire first, and that gate must be *enforced*, not merely computed (§7).

---

## 7. Tool instrumentation and capability enforcement

The dispatcher (§6) and the irreversible gate both depend on two capabilities the concept alone does not provide: Ora must be able to **observe** what an agent actually does, and **constrain** what it is allowed to do. Classification without observation misses the reality contact it routes on. Classification without enforcement cannot stop an irreversible action from firing before the gate decides. This section is the substrate that makes the two clocks trustworthy.

**Tool-event log.** Every tool or action invocation is recorded independently of the executor's narration: action name, arguments (redacted), declared capability category, raw read event (what was read, from where, network-or-not — classified as a `source_read` only *post-hoc*, below), sensitivity, whether it mutated state, exit status, and any captured artifacts. This log — not the model's summary — is the source of §6's two signals. "Reality contact is observed, not narrated" is only true if this log exists.

**Capability categories (the mutability axis).** Each tool or action declares one of four categories:

```
read              observes only; no state change            (fetch, query, read file)
reversible_write  local, cheaply undoable                   (edit file, git commit, note write)
external_write    changes an external system, recoverable   (API write with an undo, staging deploy)
irreversible      cannot be cleanly undone                  (prod deploy, email/SMTP send, payment, force-push)
```

**Read taxonomy (which reads matter, and for what).** "Read" is not one thing. The determinant is **what the output does with the material, not where the material lives**:

```
local_context_read   informs HOW to act; the output makes no claim about it   (read a file to decide an edit)
source_read          grounds a CLAIM in the output                            (fetch data; query an API;
                                                                               read code in order to DESCRIBE it)
```

Reading the codebase to decide how to edit it is context; reading the *same* code to "explain this function" or "summarize the architecture" is a `source_read`, because the output now makes claims whose correctness depends on that code. Local vs. remote is irrelevant. Only a `source_read` triggers the §6 source-read signal and only a `source_read` requires provenance evidence (§4). Network egress is a *separate, orthogonal* property tracked for safety (proxy rule below).

**Read classification is post-hoc; nothing else is.** Capability category, network egress, and sensitivity are all knowable *when the call is made* — you know you are about to deploy, hit the network, or read a credential file before you do it — so gating and redaction happen at call time and **no safety gate is ever deferred.** Whether a read is a `source_read`, by contrast, can depend on an output that does not exist yet: a fetched source may go unused, or a file read "for context" may end up quoted as a claim. So Ora records **raw read events at call time** and classifies which of them are `source_read`s **post-hoc**, when the claim-to-source map is built (§4). This defers only the *labeling*, not the *observation* — the raw events are still captured mechanically from the tool-event log, so the "observed, not narrated" invariant (§16) holds — and it defers only *read* classification, never writes or irreversibility.

**Sensitivity axis (orthogonal to mutability — read-only is not harmless).** A read that mutates nothing can still be high-risk: secrets, credentials, production data, private logs, regulated records. Each tool/resource carries a sensitivity level independent of its capability category, and this level *is* known at call time:

```
public     freely shareable
private    internal; not for durable public storage
sensitive  PII, regulated records, production data — gated, and ALWAYS redacted from durable storage
secret     credentials, keys, tokens — NEVER enters a packet at all
```

This axis is what the redaction rules (§10, §14) key off — it turns "redact secrets" from a hand-wave into a rule with a driver. Its *enforcement* splits by execution model the same way irreversibility does: in-harness gates reads per-call on sensitivity; orchestrated prevents-by-absence — don't mount `secret`/`sensitive` resources in the sandbox at all (no credential files, no secret env vars, no production DB creds).

**Unknown-action default is fail-closed.** An action not classified in the manifest is treated as `irreversible` and `secret`-sensitive, and gated. Safety defaults to caution; a new or unrecognized capability never runs un-gated on the assumption it is harmless.

**The irreversible gate is enforcement, not classification.** The executor must not be able to *reach* an `irreversible` (or unknown) capability until the gate fires — meaning the risk tier is cleared and, for the irreversible tier, human approval is recorded. Computing "this would be irreversible" while the agent has already sent the email is worthless. The gate has to sit in the path.

**Shell commands are composite and get a special policy.** A single `bash -c "..."` can read files, mutate state, hit the network, and invoke a deploy tool at once, so it cannot honestly be assigned one capability category. Treated as a single classified action, the shell becomes a side door that bypasses the entire manifest. Two acceptable handlings, and unknown commands fail closed:

- **Allowlist with known profiles** — specific commands whose capability/sensitivity/egress profile is known (e.g. `git commit`, `npm test`) run with that profile; anything outside the allowlist is gated or denied.
- **Sandbox and observe at the boundary** — un-decomposable shell runs under the *orchestrated* enforcement model even inside an otherwise in-harness deployment: worktree isolation, no irreversible/sensitive credentials in the environment, network only through the egress proxy, and mutations/reads/egress captured at the sandbox boundary.

This is **not a third enforcement model.** A shell tool is, in effect, an orchestrated sub-executor: the same reason Ora can't per-call-gate an external agent applies to a shell it can't per-syscall-gate. Any capability Ora cannot intercept per-call — an external agent or an opaque shell — is governed by prevention-by-absence plus boundary observation.

**Two enforcement models — state which one an adapter uses, because the guarantee differs.** This is the load-bearing honesty of the section.

- **In-harness** — the executor calls tools Ora provides. Every call passes through the recorder and the gate. Mutation/read detection and sensitivity gating are exact; the irreversible gate can block a call *before* it runs. Strong, per-call guarantees. This is the model the capability manifest assumes. (Opaque shell inside an in-harness deployment is the exception — it degrades to the orchestrated model above.)
- **Orchestrated** — Ora shells out to an external agent (e.g. a coding agent with its own tool access Ora cannot intercept call-by-call). Enforcement is coarser and *environmental*: run the agent in a sandbox with a restricted or absent network, a scratch worktree, and **no credentials for irreversible or sensitive systems**. You cannot stop the agent from *attempting* an action; you ensure it *cannot succeed*, because the capability is not reachable from inside the sandbox. Reality contact is then observed at the boundary rather than per call. **If an orchestrated task requires network access, that egress must route through a logging proxy (or be denied entirely).** Without it, boundary observation of source reads is incomplete and the dispatcher goes blind to what the agent read — reintroducing the exact hole this section exists to close.

The honest consequence: per-call irreversible gating, exact per-call telemetry, and per-call sensitivity gating require the in-harness model with non-opaque tools. Orchestrated execution (and opaque shell) gets **prevention-by-absence** plus **boundary observation via the egress proxy** — weaker than interception, but sound *if and only if* the sandbox denies irreversible/sensitive capabilities by default and network egress is logged. An adapter that runs orchestrated agents must not claim per-call enforcement. Each adapter records its `enforcement_model` in the packet (§9) so the guarantee level is never ambiguous.

**Evidence-runner safety rules.** The evidence runner (§10) is itself an executor and is governed by the same manifest — otherwise "evidence over claims" leaks through the back door via an uncontrolled runner. Each check runs under declared constraints: a timeout, a fixed working directory (checks do not roam), environment isolation (no ambient secrets unless declared), a network policy (`deny` / `local` / `allow`), secret redaction on captured output, defined exit-code handling, and an explicit `mutates` flag. A check that mutates state (some integration tests do) is declared as such and runs under the same sandbox discipline as execution. An undeclared check is not silently run.

---

## 8. Risk tiers

```
light        single execution + basic evidence
standard     plan brief + execution + single/dual verify
high-risk    dual plan + human gate + dual verify + rollback check
irreversible human approval BEFORE execution — enforced at the gate (§7)
```

The tier sets orchestration weight *and* verify rigor. Making the full apparatus elective and graduated is not a nicety — mandatory rigor on every file edit makes Ora too slow to use, which is its own failure mode. A cheap up-front gate ("does this even need the loop?") sends most tasks through lightweight handling and reserves the machinery for consequential, hard-to-reverse changes. The `irreversible` tier is not just the heaviest configuration; it is the one the capability gate physically blocks until approval is recorded.

**Who sets the acceptance criteria scales with tier — but the executor never sets its own, above `light`.** This is the resolution of the apparent tension with §16, and it is a scaling rule, not an exception:

- **`light`** — no planning stage. The instruction *is* the criterion, because the work is trivial enough that "wrong problem" is not a live risk — and that near-zero risk is precisely what put the task in this tier. Evidence is the repo catalog checks only (which are declared independently of the executor — §10). The executor authors nothing beyond running the declared checks; it doesn't need bespoke criteria and isn't permitted to invent them.
- **`standard`** — a single planning pass (one model family is fine) produces the Evidence Contract *before* execution and *separate from* the act of implementing. Criteria are set by a distinct prior step, not by the executor mid-implementation.
- **`high-risk` / `irreversible`** — dual planning (two families) sets the contract adversarially.

The invariant across every tier above `light`: **setting the criteria is a separate act, prior to execution.** Duality (two families) is the high-tier *strengthening* of that invariant, not the invariant itself. The load-bearing rule (§16) is separation-and-priority; adversarial duality is how much of it you buy as risk rises.

---

## 9. The Execution Packet

**Storage ground state.** The ground state is a folder of Markdown files (conventionally `vault/`) — readable and greppable with no special tooling. Obsidian, git-tracking, or a database index are optional layers on top, not requirements; a plain folder of Markdown is the floor. **Physical layout:** frontmatter carries only small, flat, indexable metadata. The packet body carries the sections. Large artifacts — diffs, logs, transcripts, planner outputs — are referenced or fenced in the body, never inlined into frontmatter. The frontmatter keys below are generic; a deployment may map them to its own taxonomy, but must not push large nested blobs into the header, or the packet becomes brittle to read, diff, and retrieve.

**Blocks are tier-optional.** Do not fabricate empty structures to satisfy the schema. Per §8: the `planning` block is **absent** at `light`, single-pass at `standard`, dual at `high-risk`/`irreversible`; `verification` is a single reviewer at lower tiers and dual (different family) at higher. A `light`-tier packet legitimately has no `planning` section and one reviewer — that is correct, not incomplete.

```yaml
# --- frontmatter (metadata index only — small and flat) ---
task_id:
created:
modified:
status:                 # in_progress | converged | escalated
output_type:            # hint only: text | execution (observed reality overrides)
risk_tier:              # light | standard | high-risk | irreversible
reversible:             # true | false — gates whether post-hoc routing is allowed
tags:

# --- body (packet sections) ---
task:
  instruction:
  constraints:
  non_goals:

planning:                         # OPTIONAL — absent at light; single-pass at standard; dual at high-risk+ (§8)
  planner_a:                      # reference to output, not inlined
  planner_b:                      # present only when dual (high-risk / irreversible)
  converged_brief:
    approach:
    acceptance_criteria:          # the WRONG-PROBLEM catch. set by a step PRIOR TO and SEPARATE FROM execution.
    known_risks:
    review_questions:
  evidence_contract:              # task-specific — NOT the repo catalog
    required_standard_checks:     # subset of the repo catalog that matters here
    bespoke_probes:               # what proves THIS feature actually works
    sufficiency:                  # what result counts as enough

execution:                        # single writer
  executor:
  enforcement_model:              # in_harness | orchestrated  (§7 — sets the guarantee level)
  mode:                           # clean_worktree | review_dirty_diff | continue_user_changes
  state_before:                   # snapshot form depends on state type:
  state_after:                    #   git → commit/tree hash; data → rows+schema+hash; files → contents
  delta:                          # changed_files, diff_ref
  tool_events:                    # reference to the recorded tool-event log (§7) — SOURCE of the two signals
                                  #   each event carries: category, RAW read (what/where/network), sensitivity, mutated, exit
  source_reads:                   # the subset CLASSIFIED POST-HOC as grounding claims (from the claim-to-source map)
  producer_claim:                 # demoted to claim, never treated as evidence
    summary:
    known_limitations:

evidence_lanes:                   # mechanical, verifiable — each yields a verdict
  - target:
    lane:                         # diff_validate | run_observe | render_inspect | deploy_probe | collect_provenance
    generated_by:                 # the command(s) actually run
    result:
    sufficient:                   # judged against evidence_contract.sufficiency
    # collect_provenance additionally requires: source snapshots/URLs + timestamps
    # + excerpts + a claim_to_source map (the event log alone is NOT sufficient — §4)

judgment_lanes:                   # interpretive — reviewer critique, NEVER mechanical
  - target:                       # e.g. voice, persuasion, taste, fit
    critique:
    verdict: null                 # by construction — kept separate so it can't look like evidence

verification:                     # single reviewer at lower tiers; dual (different family) at higher (§8, §12)
  reviewer_a:
  reviewer_b:                     # present only when dual
  findings:
    - description:
      severity:
      class:                      # plan_level | execution_level — routes the loop
  invented_tests:
    - name:
      kind:                       # acceptance | regression | diagnostic | exploratory
  reconciled_required_revisions:
  confidence:

loop:
  iteration:
  stop_condition:                 # criteria_met | max_iterations_escalated
  escalation:
    reason:
    abandoned_attempt_branch:     # inspectable, unmerged, linked — never discarded

persistence:
  tier:                           # git_only | ledger_line | durable_note
  redacted:                       # driven by the sensitivity axis (§7): secret never present, sensitive scrubbed
```

Persistence rules are in §14.

---

## 10. Evidence Contract vs. the repo catalog — say it plainly

These are two different things and conflating them is the most likely way the integrity of the loop quietly leaks.

**The repo catalog (`.ora/evidence.yaml`) declares what checks exist and how they must be run.** A repo/project-level declaration of the *standard, available* checks for that codebase — the exact build, test, lint, and typecheck commands, each with its runner constraints. It exists so evidence generation runs *declared* commands mechanically, regardless of what the executor claims it did. Without it, "which tests to run" becomes a runtime decision by the executor, and self-reporting sneaks back in one level up: a lazy or failing executor simply skips the tests and reports green.

```yaml
# .ora/evidence.yaml — what checks EXIST for this repo, plus how they must run (§7)
checks:
  build:     { cmd: "npm run build",             mutates: false, timeout: 300 }
  test:      { cmd: "npm test",                  mutates: false, timeout: 600 }
  lint:      { cmd: "npm run lint",              mutates: false, timeout: 120 }
  typecheck: { cmd: "tsc --noEmit",              mutates: false, timeout: 120 }
  preview:   { cmd: "npm run preview -- --port 4321", mutates: false, timeout: 60, network: local }
runner:
  working_dir: <repo-root>        # fixed; checks do not roam
  env:         isolated           # no ambient secrets unless explicitly declared
  network:     deny               # deny | local | allow
  redact:      by-sensitivity     # §7 axis is the driver: secret never emitted, sensitive scrubbed
  on_unknown:  gated              # a check not declared here is not auto-run
```

**The Evidence Contract is task-specific and produced at planning time.** The catalog can only list standard checks; it cannot know which matter for *this* task or what bespoke probe proves *this* feature. The planning stage (single or dual by tier — §8) produces the contract: which standard checks are relevant, what custom probe demonstrates the feature works, and what result counts as sufficient.

**The evidence runner is itself an executor** (§7). Its checks run under the declared runner constraints above; a check that mutates state runs under the same sandbox discipline as execution, and an undeclared check is not silently run. Otherwise the runner becomes another uncontrolled executor and the "evidence over claims" guarantee leaks through the back door.

**The load-bearing sentence, to be stated so no future reader misreads it:** a green evidence run means *nothing broke that you knew to check* — it does **not** mean the executor solved the right problem. Only the planning-stage acceptance criteria and the adversarial verify stage catch a wrong-problem solution. The catalog catches mechanical regression; it is blind to "built the wrong thing correctly."

---

## 11. Dirty-state protocol

Development runs with live, partially-dirty working trees constantly. Requiring a pristine repo for every useful review would kill the feature on contact with how the work actually happens. The adapter supports three modes explicitly:

- **`clean_worktree`** — execution isolated in a fresh git worktree/branch, so the "before" ref is exact and the diff is precisely the change under review.
- **`review_dirty_diff`** — evaluate an existing uncommitted diff already in flight, without demanding a clean tree.
- **`continue_user_changes`** — build on changes the user owns and does not want reverted.

---

## 12. Governance — what keeps the loop from churning or self-certifying

**Model diversity over horsepower.** The verify stage uses a *different model family* than whoever executed. The lift from the adversarial harness comes from **uncorrelated blind spots**, not raw capability — a verifier that shares the executor's failure modes rubber-stamps them. Put a strong model on planning (one cheap pass sets the whole trajectory); make verify a different family from execution.

**When only one model family is available** (cost, offline, availability), diversity degrades gracefully rather than silently vanishing: run the verifier with an explicitly adversarial prompt in a distinct role (weaker than a true second family — blind spots stay partly correlated, and the packet should say so), lower the recorded `confidence` accordingly, and for `high-risk`/`irreversible` work **escalate to a human reviewer** rather than pretending single-family review is sufficient. The failure mode to avoid is same-family review presented as if it carried cross-family assurance.

**The reviewer sees a rendered view, not raw prose.** Existing evaluator prompts expect text; a structured packet is converted to review text by a canonical **packet-to-review renderer** that fixes presentation order — mechanical evidence first, producer claim last and explicitly labeled as an *unverified claim*. This renderer is not mere formatting; it is where "evidence over claims" is physically enforced, because it controls what the reviewer weights. If evidence and claim were handed over as equals, a fluent claim could out-argue a failing test.

**Findings are tagged plan-level or execution-level**, by the reviewer, as part of producing the review. Execution-level findings route back to the executor; plan-level findings route back to the planners. Without this fork, plan-level defects get fed to the executor alone and you converge on a steadily better implementation of a wrong plan. No separate classification pass is needed — the tag is part of the finding.

**Reviewer-invented tests are tagged** `acceptance`, `regression`, `diagnostic`, or `exploratory`. Genuine missing acceptance tests obligate the executor; diagnostic probes and reviewer preferences do not. Without this, the executor is trapped chasing every invented objection.

**Grading-your-own-homework is the load-bearing integrity risk.** If the same agent writes both the implementation and the tests that "prove" it, the tests can encode the bug and pass tautologically. This is closed by two structural facts, not by good intentions: acceptance criteria are set at the planning stage before execution (the executor implements against criteria it did not invent), and the **verify** stage may author additional adversarial acceptance tests. The executor is never the sole author of its own passing condition.

---

## 13. Stop rule, escalation, and the fate of the abandoned attempt

The loop has **no guaranteed fixed point** — two verifiers can persistently disagree, and the plan/execution revision fork can ping-pong. This is a known property of feedback systems, not a bug to be fully solved, which is exactly why the human-escalation point is load-bearing rather than a fallback.

**Stop when** all acceptance criteria pass and no high-severity finding remains, **or** at a fixed iteration count, escalate to the human with the packet and the reason it did not converge. Build the loop to converge *or hand you the packet and stop* — never to churn.

**Escalation specifies the fate of the attempt.** The abandoned work lands on an **inspectable, unmerged branch that the packet links to** — never silently discarded, never left as a dangling untracked worktree to be hunted down mid-escalation. This matches how the work already runs: git for everything, no side-channel `.bak` files.

---

## 14. Tiered persistence — retrieval hygiene

Writing every Execution Packet to durable memory sounds like free institutional memory, but it recreates a known problem: not everything worth generating is worth keeping, and storing all of it pollutes retrieval so the signal you actually want is buried under routine noise. A routine session that closes clean in one revision pass does not need a permanent record any more than routine chatter needs to survive memory pruning.

- **`git_only`** — routine clean passes leave their durable record in git history, which already *is* the durable record for code.
- **`ledger_line`** — a single line in a consolidated execution ledger (one file, which avoids many-small-files retrieval noise).
- **`durable_note`** — promote only when the packet is genuinely informative: it **escalated**, **failed to converge**, or contains a **plan-level finding** worth remembering.

**Redaction before any durable write** is driven by the sensitivity axis (§7), not an ad-hoc list: nothing classed `secret` is ever present, and anything classed `sensitive` (PII, regulated records, production data, private logs) is scrubbed before the write. Without this rule the memory becomes the next thing that needs cleaning. *(A deployment that already runs a memory-pruning discipline should route packet retention through it rather than duplicating the policy.)*

---

## 15. Build plan (phased)

**Phase 0 — Audit call sites. Do not skip.** Enumerate every place that assembles a Gear 3 or Gear 4 prompt. Any custom path that builds its own prompts will *not* inherit shared-assembly changes for free (in the current codebase these include the article generator, the backfill job, the standalone Gear 3 orchestrator, and the Gear 4 runner). Locate where "output" is typed in the current loop. The polymorphic-output change must reach all of these, or the custom paths quietly keep reviewing prose reports the old way — a beautiful core abstraction that the real workload bypasses.

**Phase 1 — Tool instrumentation and capability layer (foundational).** Build the substrate everything else leans on: the tool-event recorder; the capability manifest with its four mutability categories, the read taxonomy (`local_context_read` vs `source_read`, determined by whether the output makes claims about the material), and the sensitivity axis (`public`/`private`/`sensitive`/`secret`); the **shell-command policy** (allowlist-with-profile or sandbox-and-observe, unknown fails closed) so the shell is not a side door; **raw read events recorded at call time with `source_read` classification deferred** to the provenance lane; mutation and call-time sensitivity gating; the fail-closed unknown-action default; the enforced irreversible gate; and the two enforcement models (in-harness interception vs. orchestrated sandboxing with an egress-logging proxy) with `enforcement_model` recorded per run. Include the evidence-runner safety rules here, since the runner is an executor too. Nothing downstream is trustworthy until this exists.

**Phase 2 — Risk gate + two clocks.** Build the upfront risk classifier (conservative, user-overridable) and wire the two-clock split: risk decided before, route decided after. The gate relies on Phase 1 to *enforce* the irreversibility boundary, not merely compute it. Wire the per-tier criteria-source rule (§8) here so `standard`+ runs get a planning pass and `light` runs correctly get none.

**Phase 3 — Universal capture.** The two signals — what changed, and what was read *as a source* — read from the Phase 1 tool-event log. The source-read signal uses the coarse over-approximation at dispatch (did the output make claims about material it read?), with precise `source_read` labeling deferred to the provenance lane (§7). Honestly cheap now, because the instrumentation exists to make it so.

**Phase 4 — Evaluation-lane router + polymorphic output + packet renderer.** Route by lane, not whole task, keeping `evidence_lanes` and `judgment_lanes` structurally separate. Add `ExecutionPacket` alongside `TextArtifact` as an output the *existing* review logic accepts — via the packet-to-review renderer (§12), which presents evidence first and the producer claim last, labeled unverified. Same downstream machinery, richer output — the generalize-the-primitive commitment made concrete, not a second pipeline.

**Phase 5 — Code adapter + catalog + Evidence Contract + dirty-state.** Build the one adapter used daily and make it genuinely trustworthy before generalizing. Ship `.ora/evidence.yaml` (catalog, with runner constraints) and the runner that executes it mechanically under those constraints; have the planning stage emit the task-specific Evidence Contract; implement the three dirty-state modes. State the catalog-vs-contract boundary sentence (§10) in the code comments and the spec.

**Phase 6 — Wire the loop + governance + stop rule.** Dual plan → converged brief + contract → single executor → mechanical capture → dual verify (different model family with the single-family fallback, findings tagged plan/execution, invented tests tagged) → revision router → termination and escalation with the linked unmerged branch. This is Gear4-Plan → Gear3-Execute → Verify → Revise assembled from parts already present.

**Phase 7 — Tiered persistence.** Implement `git_only` / `ledger_line` / `durable_note` with the promotion rule and sensitivity-driven redaction. Do not default to durable.

**Phase 8 — Generalize adapters.** Only after the code adapter is trustworthy: extend to notes/vault, publish pipeline, data pipelines (the `collect_provenance` lane with its claim-to-source map is the one to get right for research work) — each as an adapter *family* plus project-specific recipes, not a promise of one class = one perfect adapter.

---

## 16. The points to guard like they are load-bearing — because they are

Everything else rests on these staying honest. If any degrades, the system produces **confident wrongness**, which is worse than the honest uncertainty Ora has today: right now Ora is candidly unsure about executed work; the risk of this architecture is false trust at scale.

1. **Acceptance criteria are set by a step separate from and prior to execution** — never by the executor implementing against them. At `standard` tier a single prior planning pass suffices; at `high-risk`/`irreversible` that planning is adversarial and dual-family; at `light` tier there are no bespoke criteria to set, only the independently-declared catalog (§8). This is what catches "solved the wrong problem."
2. **The evidence recipe is declared independently of the executor** — the repo catalog plus the Evidence Contract — not chosen by the executor at runtime. This is what keeps "evidence not prose" from leaking back into self-reporting.
3. **Reality contact is observed, not narrated** — the two dispatch signals come from the tool-event log (§7), never from the executor's summary. (The raw events are captured at call time; only the claim-grounding *label* on a read is deferred, so observation stays mechanical.) If instrumentation is incomplete — an un-instrumented channel, an opaque shell treated as a single capability — the dispatcher is blind and can route a reality-touching task to text review. This is a safety prerequisite, not a nicety.

Of these, only point 1 scales with tier. Points 2 and 3 are invariant at every tier, because they are cheap and foundational — you always run declared checks and always observe rather than narrate, regardless of risk.

---

## 17. Failure modes the design must hold against

- **Not every task deserves the loop.** Forcing the full apparatus on routine edits makes Ora unusable. The loop is elective and graduated (§8).
- **Evidence can be theater.** Green tests against tautological criteria produce false trust. Guarded by §16's points.
- **Some quality is irreducibly judgment-bound.** The taxonomy tells you which — the judgment lane gets no mechanical verdict (§5).
- **The dispatcher can be blind.** If reality contact happens through an un-instrumented channel, routing silently fails. Guarded by §7 and §16, point 3.
- **The shell is a side door.** An opaque shell command can bypass a precise capability manifest. Guarded by the shell policy — allowlist or sandbox-and-observe, unknown fails closed (§7).
- **Enforcement can be overclaimed.** Orchestrated execution (and opaque shell) cannot offer per-call gating; claiming it would be the "sounds airtight, isn't" trap. Guarded by the `enforcement_model` record (§7).
- **Read-only is not harmless.** A task can expose secrets or regulated data without mutating anything, and a durable packet can leak it. Guarded by the sensitivity axis and its redaction rules (§7, §14).
- **Consulted ≠ used correctly.** A provenance task can contact real sources and still misreport them. Guarded by the claim-to-source map, not just the event log (§4).
- **No guaranteed fixed point.** The loop converges or hands you the packet and stops — it never churns (§13).

---

## 18. Broader reach (beyond any single stack)

Anywhere a workflow *trusts a report* is "execution" in this sense — a result living in external state, or a claim grounded in an external source — and each could in principle get an adapter: whether a newsletter actually sent and to whom; whether a timestamp commit landed; the regulatory state of a filed complaint; whether a scheduled job ran; whether a research claim actually follows from its cited source. The same discipline — demote the report to a claim, generate observable evidence, review the evidence, keep the human at the escalation point — applies unchanged. That generality is the point: this is not a code-review feature. It is Ora becoming a controller over non-self-evidencing outputs, with the human retained as the authority the loop escalates to rather than the oracle it replaces.
