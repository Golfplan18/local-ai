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
- a Git worktree name or path; and
- explicit activation of Programming.

Ora first reads the repository root, current commit and branch, dirty state, applicable instruction files, likely tests, and visible automation. Planning may use additional read-only repository inspection. No repository mutation occurs during planning.

If the request leaves a material choice unresolved, Ora may ask up to three questions in each of at most two rounds. Questions are limited to choices that change product outcome, scope, risk, cost, authority, or external effects. After two question rounds, the next planning pass must choose reasonable defaults and produce the plan.

## Plan Contract

Ora presents one concise plan that states:

- user-visible outcome;
- component scope;
- explicit non-goals;
- protected pre-existing work;
- coherent milestones;
- completion criteria and the exact authorized checks, which are the complete testing ceiling;
- authorized local or external effects; and
- one Git finish line: local commits, push, pull request, merge, or the DCP-only coordinated finish; and
- a Documentation-Code Parity impact declaration when repository instructions require it, with a unique ordered list of stable affected surface identifiers.

Programming independently reads tracked top-level `AGENTS.md` and `CLAUDE.md` instructions. Their active Documentation-Code Parity section determines whether the task uses DCP: a planner declaration cannot turn the requirement on or off.

The browser-visible `Git finish line:` value must equal the plan's structured finish authority; a hidden coordinated finish cannot sit behind visible local-only wording. The plan excludes file-by-file micromanagement, fixed step counts, mandatory attempt ceilings, schemas, digests, ledgers, receipts, and recovery bookkeeping. One explicit approval authorizes execution of that exact plan. Materially different scope, architecture, authority, or effects require a replacement plan.

## Execution Contract

Before editing, Ora verifies the planned repository root, commit, branch, and dirty state still match. Dirty paths explicitly named in Component scope are task-owned. Other pre-existing dirty paths are protected from executor writes, review diffs, and accepted commits while Programming continues. If task work and user work cannot be separated safely, the outcome is `ASK USER`.

Ora then:

1. creates a task branch from the inspected baseline;
2. gives the executor the approved plan and repository-scoped read, search, command, write, edit, and delete tools;
3. executes one coherent, testable milestone at a time;
4. prevents the executor from staging, committing, switching branches, pushing, publishing, deploying, messaging, or using credentials;
5. sends the raw slice diff and current repository to a fresh reviewer;
6. corrects a rejected slice before committing it; and
7. commits each reviewer-accepted slice as its rollback point.

When the plan declares Documentation-Code Parity impact, those milestone commits are not final documentation evidence. After the last milestone, Programming pauses and asks for a freshly generated five-repository evidence packet. The browser accepts that packet as JSON, sends its raw text through the ordinary privacy screen, and resumes the same approved branch. A packet supplied before execution cannot bypass this pause.

Repository behavior and Git state are authoritative. Programming creates no Programming-owned Run database, artifact store, event log, receipt ledger, lifecycle record, snapshot system, scheduler, Trigger, or process library. The separate Scheduled Trigger facility under Oversight is outside Programming.

## Independent Review Contract

Each review is a separate model call. It receives only:

- the approved plan;
- the current milestone, or `FINAL`;
- the runtime Git baseline;
- the raw task diff;
- whole-repository read access and authority to run only the plan's exact review checks; and
- read-only evidence tools required by the plan; and
- only for cumulative `FINAL` review of a documentation-impacting plan, the coordinator's fresh complete cross-repository documentation-review packet.

It receives no executor transcript, hidden reasoning, summary, or executor claims. It independently inspects implementation and runs only the exact checks authorized by the approved plan. A material risk that cannot be judged within that testing ceiling requires `ASK USER` for changed authority before another check runs. For claims about live or outside facts, it fetches the smallest sufficient authoritative source. For images or PDFs, it directly inspects attached bytes or rendered pages. Descriptions and citations without source inspection are not evidence.

If required evidence is unavailable, the criterion stays unverified. Review rejects only substantive defects: wrong user-visible behavior, unmet criteria, data or content loss, runtime failure, unauthorized scope, broken atomicity, or lost user work. It does not add preferences, speculative safeguards, tracking, style work, or unrequested generality.

For a documentation-impacting task, milestone review judges the slice without pretending final cross-repository evidence already exists. After all milestone commits, the final packet must contain all five cumulative repository diffs, a `repository_states` mapping whose five records each contain exactly `root`, `base`, `branch`, and `head`, the global-instruction and Programming-skill changes, the exact affected-surface list, canonical-section changes, every no-impact trailer with its rationale, registered propagation results, the complete verbose five-root gate result, and the authorized focused-test output. Every affected surface must have exactly one disposition: a nonempty canonical-section change or one exact `Documentation-No-Impact: <surface-id>` declaration, never both. The one passing gate contains exactly one `affected surfaces:` line. Its stable unique set is authoritative: the plan, packet, disposition coverage, and reviewer verdict set must all equal it, while ordering is retained only for stable presentation. Programming parses the gate's five explicit roots, bases, and heads; before and after final review it requires five distinct exact Git roots on explicit `codex/` or `ora/` task branches, verifies every submitted state against the gate and live worktree, and compares each nonempty submitted cumulative diff byte-for-byte with that clean branch's raw live base-to-head diff, including every trailing space and newline. The exact `[no changes]` sentinel is valid only for a genuinely empty diff. The current Programming branch and baseline must be the gated ones. Missing, malformed, stale, or drifting evidence cannot reach an accepting final outcome.

The deterministic gate establishes only mechanical correspondence. The fresh reviewer owns semantic truth: it compares changed behavior with each owning canonical section, or evaluates the declared no-impact rationale. An accepting `CONTINUE` or `DONE` response includes exactly one line per affected surface: `Documentation-Verdict: <surface-id>: ACCEPT` for a canonical change, or `Documentation-No-Impact-Verdict: <surface-id>: ACCEPT` for no impact. A false disposition uses `REJECT` with `FIX`; missing, repeated, wrong-type, or rejected verdicts invalidate acceptance.

The reviewer begins with exactly one outcome:

- `CONTINUE` — this slice is sound and approved work remains;
- `FIX` — substantive defects can be corrected inside the approved plan;
- `DONE` — the cumulative result satisfies the complete plan; or
- `ASK USER` — responsible continuation requires changed authority, scope, architecture, an unapproved external effect, human-only access, or safe separation of inseparable user work.

`DONE` is valid only during cumulative final review. An executor claim can never produce it.

## Correction and User Return

There is no fixed correction ceiling. Continue while evidence improves. Three consecutive reviews that reproduce the same substantive failure against an unchanged task diff return `ASK USER` with the consolidated blocker.

The soft spend boundary is 90 minutes. At that point Ora reports progress and asks once whether to continue. Ordinary implementation choices, reversible ambiguity, failing tests, and correctable review findings do not require the user.

## Completion, Git, and Recovery

After ordinary non-DCP `DONE`, Ora performs only the approved Git finish line. Accepted-slice commits are the rollback and resume mechanism. A later session reconstructs state from the approved plan, task branch, commits, current diff, and checks.

Documentation-impacting `DONE` has a different boundary because one Programming run owns only one repository while DCP landing is a five-repository decision. Its approved finish line is either `local_commits`, which stops with the five reviewed branches local, or `coordinated_dcp`, which authorizes the five-repository coordinator to land only those exact reviewed heads. Programming rejects the ordinary single-repository push, pull-request, and merge values for DCP work and never invokes that finish path. If DCP final review returns `FIX`, or returns `CONTINUE` without completion, Programming returns the full consolidated defect in a dedicated coordinated-correction state. It does not invoke the current-repository executor and does not create a correction or no-op commit. The five-repository coordinator corrects the participating branches; final review resumes by recovering the task and submitting a fresh current gate and packet.

No accepted result may remain parked outside the repository, and temporary test or rendering material must be removed by the tools that created it.

## User Surface

The browser surface shows only what the user needs to act:

- repository name or path and current objective;
- material questions, when necessary;
- the one proposed plan and approval control;
- milestone progress and accepted commits;
- reviewer outcomes and substantive details; and
- for a documentation-impacting final review, a privacy-screened JSON evidence entry, a dedicated coordinated-correction handoff when needed, and the exact coordinated-landing handoff; and
- genuine user decisions or completion.

Closing Programming restores ordinary Inquiry. There is no automatic routing, management interview, plan projection pair, Process Library, process-bound Trigger manager, Run Inspector, or background-resume UI. User-authored Scheduled Triggers remain a separate Oversight surface and do not wrap Programming work.

## Required Proofs

Programming is not considered complete until the native Ora path demonstrates:

1. real changes and the plan's exact authorized checks in a consequence-controlled Git repository;
2. fresh review that cannot see or trust executor claims;
3. independent inspection of authoritative outside information;
4. direct inspection of a non-text artifact; and
5. rejection of an unsupported executor completion claim; and
6. a documentation-impacting execution that pauses for post-execution evidence, rejects stale evidence, hands final defects to the five-repository coordinator without a local correction commit, resumes from fresh evidence after external correction, and withholds the ordinary single-repository finish line.

## Named Failure Modes

**Implicit Entry.** Ordinary Inquiry is classified as programming. Correction: require the explicit Programming action.

**Plan Before Inspection.** Questions or steps are proposed from the request alone. Correction: inspect repository instructions, implementation, tests, Git state, and automation first.

**Executor Self-Certification.** The review repeats the executor's report. Correction: omit the transcript and inspect repository evidence independently.

**Claim-as-Evidence.** A URL, screenshot description, or test claim is accepted without direct inspection. Correction: obtain the source or artifact with the appropriate reviewer tool, or leave it unverified.

**Uncommitted Acceptance.** A sound slice advances without a rollback point. Correction: commit the reviewer-accepted slice before the next milestone.

**Stale Documentation Acceptance.** A packet created before execution or external correction is reused to claim current semantic acceptance. Correction: regenerate the five-root gate and packet, bind every live clean branch to the printed head, and run a new cumulative final review.

**Single-Repository DCP Landing.** A documentation-impacting `DONE` calls Programming's ordinary push, pull-request, or merge path for only the current repository. Correction: return all five reviewed local branches; stop there for `local_commits`, or let the coordinator land only the exact reviewed heads when `coordinated_dcp` was approved.

**Bookkeeping Runtime.** Custom persistence is added to remember what Git already proves. Correction: recover from the plan, branch, commits, diff, and checks.

**Premature User Return.** Ora asks about an ordinary technical choice or correctable defect. Correction: investigate, choose a reversible option, test, or correct within scope before `ASK USER`.

## Version History

- **3.3 (2026-08-29):** Made repository instructions authoritative for DCP activation, made the gate's one affected-surface line authoritative, preserved cumulative diffs byte-for-byte, and replaced single-repository final correction with a direct coordinator handoff.
- **3.2 (2026-08-29):** Made DCP evidence final-only and post-execution, added the privacy-screened JSON resume path and live five-root head binding, required evidence refresh after corrections, and replaced ordinary single-repository finish with a five-branch coordinator handoff.
- **3.1 (2026-08-29):** Added the Documentation-Code Parity impact declaration, complete cross-repository evidence packet, and explicit per-surface semantic verdict contract; narrowed removed-Trigger language to Programming's former process-bound surface.
- **3.0 (2026-08-05):** Replaced the persisted governed-process design with explicit standalone Programming: inspect-first planning, one approval, a real repository executor, fresh independent review, accepted-slice commits, direct external and non-text evidence inspection, and Git-native recovery.
