# Framework — Programming

## Display Name

Programming

## Display Description

Inspect a Git repository, propose one bounded plan, change the real repository after approval, and independently review each coherent slice through completion.

## Purpose

Programming is Ora's native repository-work path. It accepts an incomplete or nontechnical objective, inspects before questioning, proposes one plan, waits for approval, gives an Ora-configured model real repository tools, and has a fresh model call verify the resulting code, diff, checks, and task-required evidence.

Programming is explicitly entered from its toolbar action. It never intercepts ordinary Inquiry, framework selection, or conversation text. It requires neither Codex nor Claude Code; those products may offer convenience workflows but are not runtime dependencies.

## Entry Contract

Required:

- a natural-language objective;
- an absolute path to a Git worktree; and
- explicit activation of Programming.

Ora first reads the repository root, current commit and branch, dirty state, applicable instruction files, likely tests, and visible automation. Planning may use additional read-only repository inspection. No repository mutation occurs during planning.

If the request leaves a material choice unresolved, Ora may ask up to three questions in each of at most two rounds. Questions are limited to choices that change product outcome, scope, risk, cost, authority, or external effects. On the second round Ora must choose reasonable defaults and produce the plan.

## Plan Contract

Ora presents one concise plan that states:

- user-visible outcome;
- component scope;
- explicit non-goals;
- protected pre-existing work;
- coherent milestones;
- completion criteria and meaningful checks;
- authorized local or external effects; and
- one Git finish line: local commits, push, pull request, or merge.

The plan excludes file-by-file micromanagement, fixed step counts, mandatory attempt ceilings, schemas, digests, ledgers, receipts, and recovery bookkeeping. One explicit approval authorizes execution of that exact plan. Materially different scope, architecture, authority, or effects require a replacement plan.

## Execution Contract

Before editing, Ora verifies that the planned repository root, commit, and dirty state still match. If user work appeared or cannot be separated safely, the outcome is `ASK USER` before branch creation or mutation.

Ora then:

1. creates a task branch from the inspected baseline;
2. gives the executor the approved plan and repository-scoped read, search, command, write, edit, and delete tools;
3. executes one coherent, testable milestone at a time;
4. prevents the executor from staging, committing, switching branches, pushing, publishing, deploying, messaging, or using credentials;
5. sends the raw slice diff and current repository to a fresh reviewer;
6. corrects a rejected slice before committing it; and
7. commits each reviewer-accepted slice as its rollback point.

Repository behavior and Git state are authoritative. Programming creates no Run database, artifact store, event log, receipt ledger, lifecycle record, snapshot system, scheduler, trigger, or process library.

## Independent Review Contract

Each review is a separate model call. It receives only:

- the approved plan;
- the current milestone, or `FINAL`;
- the runtime Git baseline;
- the raw task diff;
- whole-repository read and local-check authority; and
- read-only evidence tools required by the plan.

It receives no executor transcript, hidden reasoning, summary, or executor claims. It independently inspects implementation and runs relevant checks. For claims about live or outside facts, it fetches the smallest sufficient authoritative source. For images or PDFs, it directly inspects attached bytes or rendered pages. Descriptions and citations without source inspection are not evidence.

If required evidence is unavailable, the criterion stays unverified. Review rejects only substantive defects: wrong user-visible behavior, unmet criteria, data or content loss, runtime failure, unauthorized scope, broken atomicity, or lost user work. It does not add preferences, speculative safeguards, tracking, style work, or unrequested generality.

The reviewer begins with exactly one outcome:

- `CONTINUE` — this slice is sound and approved work remains;
- `FIX` — substantive defects can be corrected inside the approved plan;
- `DONE` — the cumulative result satisfies the complete plan; or
- `ASK USER` — responsible continuation requires changed authority, scope, architecture, a human-only decision, safe separation of user work, or a spend decision.

`DONE` is valid only during cumulative final review. An executor claim can never produce it.

## Correction and User Return

There is no fixed correction ceiling. Continue while evidence improves. After two consecutive reviews reproduce substantially the same failure without new evidence or progress, return `ASK USER` with the consolidated blocker.

The soft spend boundary is 90 minutes. At that point Ora reports progress and asks once whether to continue. Ordinary implementation choices, reversible ambiguity, failing tests, and correctable review findings do not require the user.

## Completion, Git, and Recovery

After `DONE`, Ora performs only the approved Git finish line. Accepted-slice commits are the rollback and resume mechanism. A later session reconstructs state from the approved plan, task branch, commits, current diff, and checks.

No accepted result may remain parked outside the repository, and temporary test or rendering material must be removed by the tools that created it.

## User Surface

The browser surface shows only what the user needs to act:

- repository path and current objective;
- material questions, when necessary;
- the one proposed plan and approval control;
- milestone progress and accepted commits;
- reviewer outcomes and substantive details; and
- genuine user decisions or completion.

Closing Programming restores ordinary Inquiry. There is no automatic routing, management interview, plan projection pair, Process Library, trigger manager, Run Inspector, or background-resume UI.

## Required Proofs

Programming is not considered complete until the native Ora path demonstrates:

1. real changes and meaningful checks in a consequence-controlled Git repository;
2. fresh review that cannot see or trust executor claims;
3. independent inspection of authoritative outside information;
4. direct inspection of a non-text artifact; and
5. rejection of an unsupported executor completion claim.

## Named Failure Modes

**Implicit Entry.** Ordinary Inquiry is classified as programming. Correction: require the explicit Programming action.

**Plan Before Inspection.** Questions or steps are proposed from the request alone. Correction: inspect repository instructions, implementation, tests, Git state, and automation first.

**Executor Self-Certification.** The review repeats the executor's report. Correction: omit the transcript and inspect repository evidence independently.

**Claim-as-Evidence.** A URL, screenshot description, or test claim is accepted without direct inspection. Correction: obtain the source or artifact with the appropriate reviewer tool, or leave it unverified.

**Uncommitted Acceptance.** A sound slice advances without a rollback point. Correction: commit the reviewer-accepted slice before the next milestone.

**Bookkeeping Runtime.** Custom persistence is added to remember what Git already proves. Correction: recover from the plan, branch, commits, diff, and checks.

**Premature User Return.** Ora asks about an ordinary technical choice or correctable defect. Correction: investigate, choose a reversible option, test, or correct within scope before `ASK USER`.

## Version History

- **3.0 (2026-08-05):** Replaced the persisted governed-process design with explicit standalone Programming: inspect-first planning, one approval, a real repository executor, fresh independent review, accepted-slice commits, direct external and non-text evidence inspection, and Git-native recovery.
