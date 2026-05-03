# Deep Research Protocol

## Display Name
Deep Research Protocol

## Display Description
Produce structured, cited research reports addressing open-ended knowledge gaps. Searches the vault first, then fans out to web, browser AI, and API AI sources in parallel, with confidence-triggered iteration. Use when the question is genuinely open and you want a defensible report rather than a single-pass answer.


*A Level 2 framework for orchestrated multi-step research producing cited reports on open-ended knowledge gaps.*

*Version 1.0*

---

## PURPOSE

The Deep Research Protocol orchestrates multi-step research that addresses open-ended knowledge gaps and produces a structured, cited report. It decomposes the input query into sub-queries, consults the vault first, fans out Level 1 subagents in parallel to fill residual gaps from external sources (web, browser-driven commercial AIs, API-driven commercial AIs), iterates on under-covered sub-queries using confidence-triggered re-retrieval, and synthesizes findings into a markdown report with source-class citations. It is the research substrate for the Terrain Mapping Framework (TMF) and any other Level 2+ caller that requires authoritative coverage of a topic area.

## INPUT CONTRACT

Required:
- **research_query**: Natural-language description of the research goal or knowledge gap. Format: markdown or plain text. Source: TMF Stage 2 prompt output, direct user invocation, or project-agent delegation.
- **caller_context**: Invocation source. Format: one of `TMF`, `USER_DIRECT`, `PROJECT_AGENT`. Source: dispatcher metadata. Determines clarification and plan-review gate behavior.

Optional:
- **nexus**: Project identifier for report inheritance. Format: string matching a Master Matrix entry. Source: parent PED if spawned within a project.
  Default behavior if absent: the final report is saved as domain-general (empty nexus).
- **sources_allowed**: Filter restricting retrieval to a subset of `{vault, web, browser_ai, api_ai}`. Format: list of strings.
  Default behavior if absent: all available sources, with vault consulted first.
- **depth_cap**: Maximum iteration depth for follow-up query generation. Format: integer between 1 and 10.
  Default behavior if absent: 3.
- **subagent_cap**: Maximum parallel subagents per fan-out. Format: integer between 1 and 10.
  Default behavior if absent: 5.
- **persist**: Whether to save the final report to vault. Format: boolean.
  Default behavior if absent: true.

## OUTPUT CONTRACT

Primary outputs:
- **research_report**: Markdown document containing executive summary, per-sub-query sections, cross-query synthesis, named caveats, and bibliography with inline citations. Destination: if `persist=true`, vault root with filename `Reference — [Topic].md` inheriting `nexus` from input if provided; if `persist=false`, returned in-memory to the caller.
  Quality threshold: every sub-query from the research plan has at least one cited claim; every claim carries an epistemic label; no claim appears without a citable source; the Self-Evaluation layer reports no UNRESOLVED DEFICIENCY on any criterion.

Secondary outputs:
- **evidence_map**: Structured intermediate artifact containing per-sub-query evidence with source-class tags. Destination: session-scoped temp directory. Used for step-level retry if synthesis fails.
- **research_plan**: The decomposed sub-query plan with coverage criteria. Destination: session temp directory. Used for step-level retry and for user-facing plan review.

## EXECUTION TIER

Specification. This canonical document describes the intellectual content of the framework. Execution variants (single-pass, agent-mode, reasoning-model) are rendered from this specification per the Process Formalization Framework's Rendering Protocol (Section V of PFF v2.0). The primary deployment target for Ora is agent-mode with Level 1 subagent fan-out.

---

## MILESTONES DELIVERED

This framework delivers three sequential milestones. Each milestone is a coherent intermediate deliverable that downstream milestones consume; each is a checkpoint where adversarial review and drift detection fire.

### Milestone 1: Approved Research Plan

- **Endpoint produced:** A research plan containing 3-7 sub-queries; per-sub-query coverage_criterion; per-sub-query source_hints (VAULT_CONTENT first-ranked); stopping_criteria for the run; for caller_context=USER_DIRECT with vague initial query, explicit user approval of the plan structure (plan_review_status = APPROVED).
- **Verification criterion:** Every sub-query has a coverage_criterion; every sub-query has source_hints; stopping_criteria declared; sub-queries collectively cover normalized_query without obvious gap; plan_review_status = APPROVED for vague USER_DIRECT input, NOT_REQUIRED for TMF / PROJECT_AGENT / detailed USER_DIRECT.
- **Layers covered:** 1, 2
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** See Layer 2 Output Format (RESEARCH PLAN block with sub-queries, coverage criteria, source hints, stopping criteria, plan review status).
- **Drift check question:** Does this research plan address the user's original query without scope expansion into adjacent topics?

### Milestone 2: Evidence Integrated and Iteration Resolved

- **Endpoint produced:** An integrated_evidence_map with one entry per sub-query in research_plan, each carrying deduplicated claims tagged with source class ([VAULT], [WEB], [BROWSER_AI], [API_AI], [INFERRED]) and citations; iteration_decision (one of CONVERGED, CONVERGED_WITH_GAPS, BLOCKED — never ITERATE, since iteration is internal to this milestone); uncovered-dimension caveats recorded for the synthesis layer.
- **Verification criterion:** Every sub-query in research_plan appears in integrated_evidence_map; every retained claim carries a source-class tag and citation; iteration count did not exceed depth_cap; vault was consulted before external retrieval for every sub-query (unless sources_allowed explicitly excluded vault); subagent_cap was respected on every fan-out wave; iteration_decision is one of CONVERGED, CONVERGED_WITH_GAPS, or BLOCKED.
- **Layers covered:** 3, 4, 5
- **Required prior milestones:** M1
- **Gear:** 4
- **Output format:** See Layer 5 Output Format (INTEGRATED EVIDENCE MAP + ITERATION DECISION block).
- **Drift check question:** Does the integrated evidence cover every sub-query approved in the research plan, and does the iteration decision faithfully reflect coverage status without falsely declaring CONVERGED while material gaps remain?

### Milestone 3: Final Research Report

- **Endpoint produced:** Structured markdown research report with Executive Summary (150-250 words answering normalized_query), per-sub-query sections with inline source-class tags and citations, Cross-Query Synthesis, Caveats and Epistemic Notes, Bibliography grouped by source class, Corrections Log, Missing Information Declaration, and Recovery Declaration for any UNRESOLVED DEFICIENCY; if persist=true, saved to vault root as `Reference — [Topic].md` with inherited nexus and YAML frontmatter (type, nexus, tags, dates); if persist=false, returned in-memory to caller.
- **Verification criterion:** Every sub-query from research_plan has a section in the report; every substantive claim carries a source-class tag; Bibliography contains every cited URL with no orphans in either direction; all 9 Evaluation Criteria scored at or above threshold (or below-threshold deficiencies surfaced with UNRESOLVED DEFICIENCY labels); structural completeness matches Layer 6 Output Format; YAML frontmatter present and correctly populated when persisted.
- **Layers covered:** 6, 7, 8
- **Required prior milestones:** M2
- **Gear:** 4
- **Output format:** See Layer 6 Output Format (the markdown report structure) and Layer 8 Output Format (Corrections Log, Missing Information Declaration, Recovery Declaration appendices).
- **Drift check question:** Does the final report directly answer the user's original query with proper citation grounding, no fabricated URLs, and faithful representation of the integrated evidence?

---

## EVALUATION CRITERIA

This framework's output is evaluated against these 9 criteria. Each criterion is rated 1-5. Minimum passing score: 3 per criterion.

1. **Coverage Completeness**:
   - 5 (Excellent): Every sub-query in the research plan has at least three cited claims from at least two distinct source classes; cross-query synthesis identifies patterns spanning three or more sub-queries.
   - 4 (Strong): Every sub-query has at least two cited claims; synthesis covers most sub-queries.
   - 3 (Passing): Every sub-query has at least one cited claim; synthesis present but shallow.
   - 2 (Below threshold): One or more sub-queries uncited; synthesis absent or token-thin.
   - 1 (Failing): Multiple sub-queries uncited; report reads as partial or incomplete.

2. **Source Provenance Integrity**:
   - 5 (Excellent): Every claim carries an explicit source-class tag; every external citation resolves to a valid URL that appears in the retrieval log; vault citations reference resolvable vault paths.
   - 4 (Strong): 95% or more of claims carry source-class tags; five percent or fewer orphan citations.
   - 3 (Passing): 90% or more of claims carry tags; all substantive claims trace to a named source.
   - 2 (Below threshold): Fewer than 90% of claims carry tags; multiple orphan citations.
   - 1 (Failing): Claims routinely appear without source; tags inconsistent or missing.

3. **Vault-First Adherence**:
   - 5 (Excellent): Vault reconnaissance completed before external retrieval for every sub-query; vault-sourced claims weighted prominently in synthesis; the gap map is explicit about what was and was not found in vault.
   - 4 (Strong): Vault consulted first for every sub-query; vault findings visible in synthesis.
   - 3 (Passing): Vault consulted first; vault findings present in report.
   - 2 (Below threshold): Vault consultation incomplete, skipped on some sub-queries, or performed in parallel with external fan-out.
   - 1 (Failing): External fan-out fired before vault consultation, or vault findings ignored in synthesis.

4. **Contradiction Handling**:
   - 5 (Excellent): Every identified source contradiction is explicitly named in the report with citations to both positions and an epistemic note on which is more credible and why.
   - 4 (Strong): Major contradictions named with citations to both positions.
   - 3 (Passing): Contradictions surfaced with positions cited; no reconciliation attempted.
   - 2 (Below threshold): Contradictions silently resolved in favor of one position without notation.
   - 1 (Failing): Contradictions suppressed; single-source-view synthesis.

5. **Anti-Confabulation Compliance**:
   - 5 (Excellent): No claim without a citable source; every inferred claim carries `[INFERRED]` tag plus an explicit reasoning statement; every `[INFERRED]` traces to the underlying cited evidence base.
   - 4 (Strong): No unsourced claims; inferences explicitly labeled.
   - 3 (Passing): No obvious unsourced claims; inferences mostly labeled.
   - 2 (Below threshold): Some claims appear without source; inference labels inconsistent.
   - 1 (Failing): Fluent prose with ungrounded claims; confabulation-shaped output.

6. **Structural Fidelity**:
   - 5 (Excellent): Report follows the specified structure with all sections present and well-developed; bibliography complete and formatted per convention.
   - 4 (Strong): All sections present; minor structural deviations.
   - 3 (Passing): All sections present.
   - 2 (Below threshold): One or more required sections missing.
   - 1 (Failing): Report structure fails to match specification.

7. **Scope Discipline**:
   - 5 (Excellent): Every section of the report maps to a sub-query in the plan; no topical drift; sprawl-inducing tangents pruned during synthesis.
   - 4 (Strong): 95% or more of report content maps to plan sub-queries.
   - 3 (Passing): Report addresses the original query without significant drift.
   - 2 (Below threshold): Noticeable topical drift; unrelated retrievals stitched into sections.
   - 1 (Failing): Report sprawls into adjacent topics; the Topical Sprawl Trap triggered.

8. **Epistemic Calibration**:
   - 5 (Excellent): Confidence levels stated for all non-trivial claims; speculation explicitly labeled; uncertainty acknowledged where evidence is thin; no false-certainty phrasing.
   - 4 (Strong): Confidence expressed for major claims; uncertainty flagged where evident.
   - 3 (Passing): Speculation labeled; uncertainty present.
   - 2 (Below threshold): Confidence tone uniform; some overconfident claims; uncertainty under-flagged.
   - 1 (Failing): Uniformly confident tone regardless of evidence strength.

9. **Actionability for Caller**:
   - 5 (Excellent): Report answers the original query in a form directly usable by the caller; executive summary answers the question; section structure matches what the caller needs (e.g., TMF-shaped output when called from TMF).
   - 4 (Strong): Caller's needs addressed; executive summary answers question.
   - 3 (Passing): Report is usable with minimal additional processing.
   - 2 (Below threshold): Caller must do significant additional synthesis to use report.
   - 1 (Failing): Report fails to answer the query in a caller-usable form.

---

## LAYER 1: QUERY INTAKE AND CLARIFICATION GATE

**Stage Focus**: Receive the research query, assess its clarity, and route to clarification or skip based on caller context.

**Input**: `research_query`, `caller_context`.

**Output**: `normalized_query` (a clarified or validated form of the input), `clarification_status` (one of `SKIPPED`, `COMPLETED`, `BLOCKED_ON_USER`).

### Processing Instructions

1. Read `research_query` and `caller_context`.
2. Classify query detail level. IF the query specifies (a) the domain, (b) the knowledge gap in concrete terms, and (c) at least one anchor concept, THEN classify as `DETAILED`. ELSE classify as `VAGUE`.
3. Apply the routing logic:
   - IF `caller_context = TMF`, THEN set `normalized_query = research_query` and `clarification_status = SKIPPED`. TMF is expected to emit detailed prompts.
   - IF `caller_context = PROJECT_AGENT`, THEN apply the same detail-level logic: skip if `DETAILED`, run clarification if `VAGUE`.
   - IF `caller_context = USER_DIRECT` AND query classifies as `DETAILED`, THEN set `clarification_status = SKIPPED`.
   - IF `caller_context = USER_DIRECT` AND query classifies as `VAGUE`, THEN enter clarification: present no more than three focused questions to the user addressing the specific dimensions that would convert the query to `DETAILED`. Wait for user response. Consolidate the original query plus user responses into a rewritten `normalized_query`. Set `clarification_status = COMPLETED`.
4. IF clarification is required but the user declines or provides non-substantive responses, THEN set `clarification_status = BLOCKED_ON_USER` and halt execution. Return to caller with the block reason.
5. Apply the Premature Accommodation Trap correction: even if the user signals impatience ("just do it, pick something"), do not silently skip clarification. Acknowledge the time constraint, then proceed with an explicit assumption declaration rather than a silent skip: "Proceeding with these assumptions: [list]. Halt and correct if wrong." Treat silence as approval.

### Invariant Check

Before proceeding to Layer 2: confirm that `normalized_query` is populated, that `caller_context` is unchanged from input, and that the primary objective stated in the Purpose has not shifted.

### Output Format for This Layer

```
NORMALIZED QUERY: [text]
CLARIFICATION STATUS: [SKIPPED | COMPLETED | BLOCKED_ON_USER]
ORIGINAL QUERY (if modified): [text]
ASSUMPTIONS ADDED (if any): [list]
```

---

## LAYER 2: RESEARCH PLAN CONSTRUCTION

**Stage Focus**: Decompose the normalized query into sub-queries, declare coverage criteria, identify source hints per sub-query.

**Input**: `normalized_query`, `caller_context`, `clarification_status`.

**Output**: `research_plan` containing `sub_queries[]`, `coverage_criteria` per sub-query, `stopping_criteria` for the run, `source_hints_per_subquery`.

### Processing Instructions

1. Decompose `normalized_query` into between 3 and 7 sub-queries. Each sub-query must be independently answerable and must not overlap materially with any other. IF the query naturally decomposes into more than 7 sub-queries, THEN group related sub-queries into dimensions and treat the dimensions as the primary decomposition (still 3-7 units).
2. For each sub-query, declare a `coverage_criterion` — a concrete statement of what constitutes "adequately answered." Example: "At least two independent sources describe the mechanism, plus one named limitation."
3. For each sub-query, declare `source_hints`: a prioritized list of source classes likely to contain relevant evidence. Use the Ora claim taxonomy. `VAULT_CONTENT` is always first-ranked; then `CURRENT_WEB`, `BROWSER_AI_CONSULTATION`, `API_AI_CONSULTATION`, `SPECIALIZED_DOMAIN` as applicable to the sub-query.
4. Declare the `stopping_criteria` for the run: all sub-queries satisfy their `coverage_criterion`, OR the iteration depth reaches `depth_cap`, OR the loop failsafe triggers (per Capability Dispatch Architecture).
5. IF `caller_context = USER_DIRECT` AND `clarification_status = COMPLETED` (the user's input was vague enough to require clarification), THEN surface the full `research_plan` to the user for review and approval before proceeding to Layer 3. Wait for explicit approval or edit. IF the user edits the plan, THEN incorporate edits and re-present.
6. IF `caller_context = USER_DIRECT` AND `clarification_status = SKIPPED` (the input was detailed), THEN proceed without plan review — the user's detailed prompt is treated as the approved plan.
7. IF `caller_context = TMF` OR `caller_context = PROJECT_AGENT`, THEN proceed without plan review.

### Invariant Check

Confirm that every sub-query maps to at least one source class in `source_hints`, that every sub-query has a `coverage_criterion`, and that the sub-queries together cover the scope of `normalized_query` with no obvious gap.

### Output Format for This Layer

```
RESEARCH PLAN
Sub-Queries:
  1. [sub-query 1]
     Coverage criterion: [text]
     Source hints: [ordered list, VAULT_CONTENT first]
  [continue for all sub-queries]

Stopping Criteria:
  - All sub-queries satisfy their coverage criterion, OR
  - Iteration depth reaches depth_cap ([N])
  - Loop failsafe triggers

Plan Review Status: [APPROVED | NOT_REQUIRED]
```

---

## LAYER 3: VAULT RECONNAISSANCE

**Stage Focus**: Consult the vault first for every sub-query; mark what is answered and what remains as gap for external retrieval.

**Input**: `research_plan`, `sources_allowed`.

**Output**: `vault_evidence_per_subquery`, `gap_map` (sub-queries with residual gaps and the specific dimensions still needing coverage).

### Processing Instructions

1. For each sub-query in `research_plan.sub_queries`:
   a. IF `sources_allowed` explicitly excludes vault, THEN skip this sub-query's vault reconnaissance and mark it as full-gap for external fan-out. Record the skip reason.
   b. ELSE emit a `knowledge_search` call with the sub-query text. Default: top 10 chunks per sub-query.
   c. Read returned chunks. For each chunk: extract the relevant proposition(s), record the source file path, note provenance weight (engram > working > resource > raw, per vault convention).
   d. Assess vault evidence against the sub-query's `coverage_criterion`. Classify the sub-query as `ANSWERED`, `PARTIALLY_ANSWERED`, or `GAP`.
2. Build `gap_map`: for each sub-query not fully `ANSWERED`, record the specific dimensions still needing coverage.
3. Apply the Vault Blindness Trap correction: do not skip this layer for any sub-query unless `sources_allowed` explicitly excludes vault. Vault-sourced claims carry the highest provenance weight and are cheap to retrieve; skipping vault inflates token cost and loses high-provenance evidence.

### Invariant Check

Confirm that every sub-query from Layer 2 has either a completed vault search result or a documented skip reason, that every extracted proposition has a source file path, and that `gap_map` accurately reflects unanswered dimensions per the coverage criteria.

### Output Format for This Layer

```
VAULT EVIDENCE PER SUB-QUERY
Sub-Query 1: [text]
  Status: [ANSWERED | PARTIALLY_ANSWERED | GAP]
  Propositions extracted:
    - [proposition] | Source: [vault path] | Provenance: [engram/working/resource/raw]
    [continue]
  Residual gap (if any): [text]
[continue for all sub-queries]

GAP MAP
Sub-queries requiring external retrieval:
  - [sub-query] | Gap: [dimension list]
  [continue]
```

---

## LAYER 4: EXTERNAL RETRIEVAL FAN-OUT

---

ORIENTATION ANCHOR — MIDPOINT REMINDER
Primary deliverable: a structured research report with cited claims addressing `normalized_query`.
Key decisions made so far: query decomposed into sub-queries with concrete coverage criteria; vault consulted first; `gap_map` identifies the sub-queries and dimensions requiring external retrieval.
Scope boundaries that must not shift: every claim in the final report must carry a source-class tag; vault is the first-ranked provenance tier; `depth_cap` and `subagent_cap` constrain fan-out; the report must remain within the scope of the sub-queries defined in the research plan.
Next layer must produce: per-sub-query external evidence gathered by Level 1 subagents, condensed and tagged with source class and citation.
Continue to Layer 4.

---

**Stage Focus**: Spawn Level 1 subagents in parallel to fill the gaps identified in `gap_map`.

**Input**: `research_plan`, `vault_evidence_per_subquery`, `gap_map`, `sources_allowed`, `subagent_cap`.

**Output**: `subagent_reports[]` — one per spawned subagent, each containing the sub-query addressed, findings with source-class tags and citations, condensed insights, and any discovered contradictions.

### Processing Instructions

1. For each sub-query present in `gap_map`:
   a. Construct a subagent prompt containing: the specific sub-query text; the vault evidence already found for that sub-query (as context); the specific gap dimensions to address; the permitted source classes (filtered by `sources_allowed`); instruction to apply the Search-o1 Reason-in-Documents pattern (extract and condense rather than paste full pages); instruction to tag every claim with its source class; an explicit constraint forbidding fabricated citations ("every URL you cite must be one your tool call actually retrieved").
   b. Dispatch the subagent at Level 1 with appropriate tool access (`web_fetch`, `browser_evaluate`, `api_evaluate` per `sources_allowed`).
2. Spawn subagents in parallel up to `subagent_cap` concurrent. Queue additional sub-queries if `gap_map` has more entries than `subagent_cap` allows concurrent.
3. On subagent return:
   a. Validate the returned report: every claim has a source-class tag, every external citation has a URL, the report condenses rather than pastes raw content.
   b. IF a subagent report fails validation, THEN spawn a continuation subagent with the validation failure flagged in the prompt. Do not silently accept malformed reports.
   c. Collect validated reports into `subagent_reports[]`.
4. Apply the Over-Spawning Trap correction: do not spawn additional subagents beyond what `gap_map` entries require. One subagent per sub-query gap, unless the sub-query's gap is broad enough to split — in which case the split is declared explicitly before spawning.
5. Apply the SEO Farm Trap correction: in every subagent prompt, explicitly instruct the subagent to prefer academic, official, first-party, and established-media sources over content farms, listicle sites, and SEO-optimized aggregators. Instruct the subagent to note source quality in its report.

### Invariant Check

Confirm that every sub-query in `gap_map` has a corresponding subagent report or an explicit skip reason, that every claim in every report carries a source-class tag, that no subagent was spawned beyond `subagent_cap` concurrent, and that `research_plan` is unchanged.

### Output Format for This Layer

```
SUBAGENT REPORTS

Sub-Query 1: [text]
  Subagent ID: [id]
  Sources consulted: [list with URLs or paths]
  Findings:
    - [condensed finding] | [SOURCE_CLASS] | [citation]
    [continue]
  Contradictions surfaced (if any): [text with both cited positions]
[continue for all sub-queries with reports]
```

---

## LAYER 5: EVIDENCE INTEGRATION AND ITERATION DECISION

**Stage Focus**: Aggregate vault and subagent evidence; assess coverage against the research plan; decide whether to iterate.

**Input**: `vault_evidence_per_subquery`, `subagent_reports[]`, `research_plan`, `depth_cap`, current iteration depth.

**Output**: `integrated_evidence_map`, `iteration_decision` (one of `CONVERGED`, `CONVERGED_WITH_GAPS`, `ITERATE`, `BLOCKED`).

### Processing Instructions

1. For each sub-query: merge vault evidence and subagent findings into a single `integrated_evidence` entry. Deduplicate overlapping claims. Preserve source-class tags on every retained claim.
2. For each sub-query, evaluate coverage:
   a. Wait — verify the integrated evidence against the sub-query's `coverage_criterion` before deciding.
   b. Classify coverage as `COMPLETE` (criterion satisfied), `PARTIAL` (criterion partially satisfied; specific gap known), or `UNCOVERED` (criterion fails; significant gap remains).
3. Decide iteration:
   - IF all sub-queries are `COMPLETE`, THEN set `iteration_decision = CONVERGED`.
   - IF at least one sub-query is `PARTIAL` or `UNCOVERED` AND current iteration depth is less than `depth_cap`, THEN set `iteration_decision = ITERATE`. Generate follow-up sub-queries addressing the specific remaining gaps. Return to Layer 4 with the follow-up sub-queries as new `gap_map` entries.
   - IF at least one sub-query is `PARTIAL` or `UNCOVERED` AND current iteration depth equals `depth_cap`, THEN set `iteration_decision = CONVERGED_WITH_GAPS`. Record the uncovered dimensions; they will appear in the report's Caveats section.
   - IF no progress was made on any `PARTIAL` or `UNCOVERED` sub-query in the most recent iteration (evidence volume did not increase and no new unique sources were consulted), THEN set `iteration_decision = BLOCKED`. Record the block reason for escalation.
4. Apply the Endless Search Trap correction: the iteration loop is hard-capped by `depth_cap`. Do not spawn follow-up queries beyond the cap even if coverage feels thin. Record the uncovered dimensions in the Caveats section instead.
5. Apply the Premature Convergence Trap correction: do not declare `CONVERGED` when one or more sub-queries are `UNCOVERED` within iteration budget. Iterate at least once on every `UNCOVERED` sub-query before declaring `CONVERGED_WITH_GAPS`.

### Invariant Check

Confirm that `integrated_evidence_map` has an entry for every sub-query in `research_plan`, that every retained claim carries a source-class tag, that iteration count does not exceed `depth_cap`, and that `normalized_query` remains the governing objective.

### Output Format for This Layer

```
INTEGRATED EVIDENCE MAP
Sub-Query 1: [text]
  Coverage: [COMPLETE | PARTIAL | UNCOVERED]
  Claims:
    - [claim] | [SOURCE_CLASS] | [citation]
    [continue]
  Residual gap (if any): [text]
[continue for all sub-queries]

ITERATION DECISION: [CONVERGED | CONVERGED_WITH_GAPS | ITERATE | BLOCKED]
Iteration depth: [N] / [depth_cap]
Reason: [text]
```

---

## LAYER 6: SYNTHESIS WITH CITATION GROUNDING

**Stage Focus**: Produce the structured research report from integrated evidence, grounding every claim in a source-class tag and citation.

**Input**: `integrated_evidence_map`, `research_plan`, `normalized_query`, `iteration_decision`, uncovered-dimension caveats from Layer 5.

**Output**: `draft_report` (complete markdown document).

### Processing Instructions

1. Draft the report structure:
   - **Executive Summary** (150-250 words): answers `normalized_query` directly, surfaces the most important findings, names the biggest caveats.
   - **Sub-Query Sections** (one per sub-query in `research_plan`): each section opens with the sub-query as a subheading, develops findings with inline citations, names contradictions where present, ends with a per-section takeaway of 1-2 sentences.
   - **Cross-Query Synthesis**: patterns that span multiple sub-queries; themes; notable convergences or divergences; the analytical through-line.
   - **Named Caveats and Epistemic Notes**: uncovered sub-queries from Layer 5; sparse-evidence zones; `[INFERRED]` claims with their reasoning basis; known source-corpus biases.
   - **Bibliography**: every URL cited in the body, grouped by source class; vault paths listed separately; duplicate URLs collapsed to a single entry.
2. Every substantive claim carries an inline source-class tag: one of `[VAULT]`, `[WEB]`, `[BROWSER_AI]`, `[API_AI]`, or `[INFERRED]`. External citations include the URL inline or as a numbered footnote. Vault citations include the vault file path.
3. Apply the Citation Hallucination Trap correction: every external URL in the report must appear in `integrated_evidence_map` or in a `subagent_reports` entry. Do not invent URLs. Do not paraphrase a URL structure you did not receive from retrieval.
4. Apply the Topical Sprawl Trap correction: every paragraph in the Sub-Query Sections must address its own sub-query. Content that belongs to a different sub-query moves to that sub-query's section. Content that belongs to none is deleted.
5. Apply the Context Dilution Trap correction: the synthesis model works from `integrated_evidence_map` (condensed), not from the full subagent reports. Evidence entered the map already condensed; do not re-expand into full-text pastes during synthesis.
6. Apply the Source-Bias Transfer Trap correction: in the Caveats section, explicitly name any source-corpus bias that could have transferred into the report (example: "all web sources for sub-query 3 were Tier-1 US publications; non-US perspectives are under-represented").

### Invariant Check

Confirm that every sub-query from `research_plan` has a section in the report, that every claim carries a source-class tag, that the Bibliography contains every cited URL with no orphans in either direction, that the report contains no content outside the scope of the plan, and that word count is reasonable for the research depth (no padding).

### Output Format for This Layer

```markdown
# [Report Title — reflecting normalized_query]

*Generated by Ora Deep Research Protocol | [date] | Iteration depth: [N]*

## Executive Summary
[150-250 words — direct answer plus biggest caveats]

## [Sub-Query 1 — as subheading]
[findings with inline [SOURCE_CLASS] tags and citations]

**Takeaway:** [1-2 sentences]

[continue for all sub-queries]

## Cross-Query Synthesis
[patterns, themes, convergences, divergences]

## Caveats and Epistemic Notes
- Uncovered dimensions: [list]
- Sparse-evidence zones: [list]
- Inferred claims: [list with reasoning basis]
- Source-corpus biases: [list]

## Bibliography
### Web Sources
- [URL] — [brief descriptor]
### Browser AI Sources
- [session label] — [consultation summary]
### API AI Sources
- [model + API] — [consultation summary]
### Vault Sources
- [vault path] — [file type + provenance]
```

---

## LAYER 7: SELF-EVALUATION

**Stage Focus**: Evaluate the draft report against the 9 Evaluation Criteria defined above.

**Calibration warning**: Self-evaluation scores are systematically inflated. Research finds LLMs are overconfident in 84.3% of scenarios. A self-score of 4/5 likely corresponds to 3/5 by external evaluation standards. Score conservatively. Articulate specific uncertainties alongside scores.

### Processing Instructions

For each of the 9 Evaluation Criteria:

1. State the criterion name and number.
2. Wait — verify the current report against this specific criterion's rubric descriptions before scoring.
3. Identify specific evidence in the report that supports or undermines each score level. Quote the relevant passage or reference it by section.
4. Assign a score (1-5) with cited evidence from the report.
5. IF the score is below 3 (below threshold), THEN:
   a. Identify the specific deficiency with a direct quote or reference to the deficient passage.
   b. State the specific modification required to raise the score.
   c. Apply the modification to the draft report.
   d. Re-score after modification.
6. IF the score is 3 or above, THEN confirm and proceed to the next criterion.

After all 9 criteria are evaluated:
- IF all scores meet threshold, THEN proceed to Layer 8.
- IF any score remains below threshold after one modification attempt, THEN flag the deficiency with the label UNRESOLVED DEFICIENCY and state what additional input or iteration would be needed to resolve it.

### Confidence Assessment

For the report as a whole, state:
- Which claims carry HIGH confidence (multiple independent sources converge).
- Which claims carry MEDIUM confidence (one primary source plus corroborating context).
- Which claims carry LOW confidence (single source, thin evidence, or `[INFERRED]`).

### Output Format for This Layer

```
SELF-EVALUATION

Criterion 1: Coverage Completeness
  Wait — verifying against rubric.
  Evidence: [quote or reference]
  Score: [1-5]
  [If below 3: Deficiency, Modification, Re-score]

[continue for all 9 criteria]

CONFIDENCE ASSESSMENT
  HIGH confidence claims: [list with brief descriptor]
  MEDIUM confidence claims: [list]
  LOW confidence claims: [list]

UNRESOLVED DEFICIENCIES (if any):
  - [criterion] | [required additional input or iteration]
```

---

## LAYER 8: ERROR CORRECTION AND OUTPUT FORMATTING

**Stage Focus**: Final verification, mechanical error correction, variable fidelity, nexus inheritance, and persistence.

### Error Correction Protocol

1. Verify factual consistency across all sections. Flag and correct contradictions within the report (distinct from source contradictions, which are preserved and named per Criterion 4).
2. Verify terminology consistency. Confirm that defined terms are used with their defined meanings throughout.
3. Verify structural completeness against the Layer 6 Output Format: Executive Summary, Sub-Query Sections, Cross-Query Synthesis, Caveats, Bibliography.
4. Verify variable fidelity: confirm that `research_query`, every sub-query from `research_plan`, every source class used, and `iteration_decision` are accurately represented. IF any named variable was silently dropped, conflated, or simplified during synthesis, THEN restore it.
5. Verify citation integrity: every URL in the Bibliography appears in the report body; every body citation resolves to a Bibliography entry; no orphan citations in either direction.
6. Document all corrections in a Corrections Log appended at the end of the report.

### Missing Information Declaration

Before finalizing output, explicitly state:
- Any required or optional input that was absent or defaulted.
- Any sub-query where evidence was thin enough that findings are speculative.
- Any evaluation criterion where the score reflects an information gap rather than a quality deficiency.

### Recovery Declaration

IF the Self-Evaluation layer flagged any UNRESOLVED DEFICIENCY, THEN restate each deficiency here with: the specific criterion not met, what additional input or iteration would resolve it, and whether the deficiency affects downstream consumers (especially relevant for TMF as caller).

### Nexus Inheritance and Persistence

1. IF `nexus` was provided in the Input Contract, THEN set the saved report's YAML `nexus:` field to that value.
2. IF `nexus` was absent, THEN leave the nexus field empty (domain-general).
3. Construct the filename: `Reference — [Topic].md` where Topic is a short title derived from `normalized_query` (title case, 3-8 words).
4. IF `persist = true`, THEN write the final report to `~/Documents/vault/[filename]`. Include YAML frontmatter with: `type: resource`, `nexus: [inherited or empty]`, `tags:`, `date created: [today]`, `date modified: [today]`.
5. IF `persist = false`, THEN return the report content in-memory to the caller without writing to disk.

### Output Format for This Layer

```markdown
[Full research report from Layer 6, with corrections applied]

---

## Corrections Log
- [correction 1]
- [correction 2]

## Missing Information Declaration
- [item]

## Recovery Declaration (if applicable)
- [unresolved deficiency]: [criterion] | [additional input needed] | [downstream impact]
```

---

## NAMED FAILURE MODES

**The Confabulation Trap:** Producing fluent, plausible-sounding claims without a citable source backing them — the default failure mode of LLMs in research-report-shaped generation. Correction: every substantive claim must carry a source-class tag pointing to a specific evidence entry in `integrated_evidence_map`. Layer 6 instruction 2 prohibits claims without retrieval backing; Evaluation Criterion 5 tests for it.

**The Citation Hallucination Trap:** Attaching invented URLs, paraphrased source paths, or misattributions to real sources. Occurs when the synthesis model generates citation-shaped tokens from training priors rather than from the evidence map. Correction: every external URL in the report must appear verbatim in `integrated_evidence_map` or a subagent report. Layer 6 instruction 3 forbids URL invention; Layer 8 citation integrity check verifies that every URL in the body appears in the Bibliography and was received from retrieval.

**The Topical Sprawl Trap:** Stitching loosely related retrievals into sections that drift beyond the sub-queries declared in the plan — the failure pattern documented in STORM where the model weaves unrelated facts into plausible-sounding paragraphs. Correction: every paragraph in Sub-Query Sections must address its own sub-query. Content belonging to a different sub-query moves; content belonging to no sub-query is deleted. Evaluation Criterion 7 tests for it.

**The SEO Farm Trap:** Ranking content farms, listicle sites, and SEO-optimized aggregators above authoritative academic, first-party, or established-media sources — documented by Anthropic as a default failure mode of retrieval agents. Correction: subagent prompts (Layer 4 instruction 5) explicitly instruct source-quality preference; subagents note source quality in their reports; synthesis downweights evident low-quality sources.

**The Vault Blindness Trap:** Skipping vault reconnaissance and over-fetching external sources — losing the high-provenance vault evidence advantage and inflating token cost unnecessarily. Correction: Layer 3 fires for every sub-query unless `sources_allowed` explicitly excludes vault. Evaluation Criterion 3 tests vault-first adherence.

**The Endless Search Trap:** The iteration loop spawns follow-up queries indefinitely, scouring for evidence on dimensions that are not well-covered by available sources — documented by Anthropic as "scouring the web endlessly for nonexistent sources." Correction: Layer 5 hard-caps iteration at `depth_cap`; uncovered dimensions move to the Caveats section rather than spawning unbounded follow-up.

**The Premature Convergence Trap:** The iteration loop declares convergence while one or more sub-queries remain `UNCOVERED` within iteration budget — reporting false completeness. Correction: Layer 5 decision logic requires at least one iteration attempt on every `UNCOVERED` sub-query before declaring `CONVERGED_WITH_GAPS`; `CONVERGED` is reserved for the all-`COMPLETE` case.

**The Over-Spawning Trap:** Fan-out exceeds query complexity — consuming tokens disproportionate to the research need. Documented by Anthropic ("50 subagents for simple queries"). Correction: Layer 4 instruction 4 caps subagent spawns at one per `gap_map` entry; `subagent_cap` hard-bounds concurrent parallelism.

**The Context Dilution Trap:** Evidence accumulates in context faster than it is condensed; synthesis quality degrades as irrelevant retrieval volume crowds out signal — documented in MemSearch-o1 as "memory dilution." Correction: subagent prompts instruct the Search-o1 Reason-in-Documents condensation pattern; synthesis works from `integrated_evidence_map` (condensed), not raw subagent reports.

**The Source-Bias Transfer Trap:** Biases in the retrieved source corpus (for example, all Tier-1 US publishers; all pro-position sources) propagate into the synthesized report without the model noting the bias — documented in STORM as an open problem. Correction: Layer 6 instruction 6 requires naming source-corpus biases in the Caveats section when retrieval clearly skewed toward a category.

**The Premature Accommodation Trap:** During Layer 1 clarification, the framework abandons question sequences when the user signals impatience, producing research on a poorly-specified query. Correction: Layer 1 instruction 5 handles impatience with explicit assumption declaration rather than silent skip.

---

## EXECUTION COMMANDS

1. Confirm you have fully processed this framework specification and all associated input materials.
2. IF any required inputs (per Input Contract) are missing, THEN list them now and request them before proceeding. Required inputs: `research_query`, `caller_context`.
3. IF any required inputs are present but ambiguous, THEN state what you understand, what you are uncertain about, and what assumptions you will make if not corrected. Wait for confirmation before proceeding.
4. IF optional inputs are absent, THEN note the defaults that will apply: `sources_allowed = all available`, `depth_cap = 3`, `subagent_cap = 5`, `persist = true`, `nexus = empty`.
5. Once required inputs are confirmed, execute Layers 1 through 8 sequentially. Produce all outputs specified in the Output Contract.
6. On completion, emit a run-level log entry (iteration depth reached, sources consulted, subagents spawned, `iteration_decision`, any UNRESOLVED DEFICIENCY labels) to the session log for step-level retry support.

---

## FRAMEWORK REGISTRY ENTRY

```
Name: Deep Research Protocol
Purpose: Produce structured, cited research reports addressing open-ended knowledge gaps via orchestrated multi-step search — vault-first, then parallel Level 1 subagent fan-out to web, browser AI, and API AI sources — with confidence-triggered iteration
Problem Class: Open-ended research and knowledge gap resolution
Input Summary: A research query (from TMF, user, or project agent); caller context; optional nexus, source filter, depth cap, subagent cap, persist flag
Output Summary: Structured markdown research report with executive summary, per-sub-query sections, cross-query synthesis, named caveats, bibliography; saved to vault root with inherited nexus if specified
Proven Applications: None yet — initial version
Known Limitations: Token cost scales 4-15× a single-shot query (per Anthropic's published figures); vault-first retrieval quality depends on vault content; confabulation risk present where external sources are sparse
File Location: frameworks/book/deep-research-protocol.md (executable); ~/Documents/vault/Framework — Deep Research Protocol.md (canonical)
Provenance: human-created
Confidence: low
Version: 1.0
Delivers: Cited research reports addressing specified knowledge gaps via vault-first retrieval and parallel external fan-out
```

---

**END OF DEEP RESEARCH PROTOCOL v1.0**
