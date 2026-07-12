# Specification — Supplemental RAG Protocol

*Universal standing instruction injected into every analytical pipeline step (analyst, evaluator, reviser, verifier, consolidator). Authorises the model to request additional retrieval when the package is insufficient, instead of confabulating. The orchestrator runs the query against the vault, appends the result to the package, and re-submits as a fresh stateless call. Paired with `~/ora/frameworks/book/supplemental-rag-protocol.md`.*

## Why this exists

LLM pipeline outputs that look complete can be subtly wrong — the **Subtle-Calculation-Error Class** of failure documented in `Paper — Subtle-Calculation Errors in LLM Pipelines`. When a step has insufficient information, it produces a plausible-looking answer instead of halting. The fix has to live **at the source step**, not at verification, because the wrong answer is internally coherent and adversarial review cannot catch it.

This protocol gives the model an authorised non-confabulation path. When it cannot verify a factual claim from training and the package does not support it, instead of guessing, the model emits a structured request. The orchestrator fetches the missing material and re-submits the entire package as a fresh stateless call. The supplement-request log is the empirical record of where the vault is thin.

## When to use it

Use the SUPPLEMENTAL RAG REQUEST block any time you encounter:

- A factual claim, name, date, statistic, or definition you cannot verify from training **and** that the provided package does not support
- A relationship between two named entities that you cannot confirm from training
- A canonical fact about a specific person, document, framework, or event referenced in the prompt
- A specific number (revenue, population, measurement) where confabulation would be measurable error

**Do NOT use it for:**
- Reasoning, judgment, opinion, analysis — those are your job, not retrievable
- Speculation or hypothetical scenarios
- Items the package already covers (read the package before requesting)
- Asking the user — supplementation is orchestrator-mediated, not user-mediated

## Request format

Emit the block in your response in this exact format:

```
## SUPPLEMENTAL RAG REQUEST
gap_statement: <one sentence: what claim or fact you cannot verify>
query_terms: <comma-separated terms the orchestrator should search>
why_it_matters: <one sentence: how the gap affects your output if unfilled>
```

Place the block **before** the rest of your response, at the top. Continue producing the rest of your analysis after it; use placeholders like `[awaiting supplement on X]` where the missing fact would appear.

## Resubmission behaviour

When the orchestrator detects this block:
1. The `query_terms` are run against the vault knowledge collection (ChromaDB) with provenance ranking.
2. The result is appended to the system context as a `## SUPPLEMENTAL RAG RESULT` block.
3. The **entire package is re-submitted as a fresh stateless call** to the same step. You will see your own prior request, the orchestrator's fetched result, and the original task all together. Re-run your analysis with the new information.

## Caps and degradation

- Maximum **two** supplements per pipeline step.
- After two supplements, no further requests are honoured. If you still cannot verify a claim, replace the request with a `## COVERAGE GAP` block:

```
## COVERAGE GAP
unresolved: <one sentence: the claim that remains unverifiable>
attempts: <summary of what the supplements returned>
impact: <how this affects the analysis you are producing>
```

The COVERAGE GAP is an **admission**, not a failure. The user prefers a partial answer with named gaps over a confident-looking confabulation. Cite COVERAGE GAPs explicitly in your output.

## Anti-patterns

- **Confabulating** — producing plausible content for facts you cannot verify. The whole protocol exists to avoid this; if you find yourself filling a gap with a guess, stop and emit a SUPPLEMENTAL RAG REQUEST instead.
- **Omitting** — silently skipping a question because you lack information. The user asked a question; tell them what is missing.
- **Asking the user** — do not put a question to the user (that would surface as Phase A clarification, not supplemental RAG). The orchestrator is the channel for vault retrieval.
- **Bundling unrelated gaps** — one request per coherent gap. If you need three different supplements, emit three separate request blocks. (Within the per-step cap of two, you may pick the two most consequential.)
- **Requesting for opinion-type material** — only retrievable facts qualify. "Find me other people who think this" is not a supplemental RAG request; it's a separate research task.

## Trace and observability

Every SUPPLEMENTAL RAG REQUEST is logged to `~/ora/data/pipeline-traces/<conversation_id>/<turn-ts>/supplemental-rag.jsonl` with:

- The step that emitted it
- The gap statement, query terms, why-it-matters
- The supplement-result length (and content excerpt)
- Whether the resubmission resolved the gap

This log is the empirical signal of where vault coverage is thin and where models would otherwise have confabulated. Reviewing it monthly identifies content gaps for vault enrichment.

## Where this protocol is injected

The protocol is added to the system prompt of every model call at these pipeline steps:

| Step | Role | Injected |
|---|---|---|
| Phase A | Prompt cleanup | No — preprocessing only |
| Pre-routing | Mode dispatch | No — deterministic logic |
| Step 3 | Analyst (Depth + Breadth) | Yes |
| Step 4 | Evaluator | Yes |
| Step 5 | Reviser | Yes |
| Step 6 | Verifier | Yes |
| Step 7 | Consolidator | Yes |
| Step 8 | Formatter | No — placement only, no new facts |

Detection and resubmission logic lives in `orchestrator/boot.py::_call_with_supplement` (the wrapper around `_call_with_retry`).

## Failure modes named

**The Confident Confabulator.** Model produces a plausible answer without emitting a request. Detection: trace shows no supplement_request, but the answer contains specific verifiable claims the package did not supply. Mitigation: stronger training-time anti-confabulation discipline; the protocol is the structural fix but does not guarantee compliance.

**The Always-Requester.** Model emits a request on every step, even when the package is adequate. Detection: trace shows high supplement frequency on prompts that should not need supplementation. Mitigation: tighten the "when to use it" guidance; consider supplements/turn metric in oversight dashboards.

**The Unhelpful Supplement.** Orchestrator's fetched result is irrelevant to the gap. Detection: trace shows supplement provided but model still emits COVERAGE GAP. Mitigation: revisit the model's `query_terms` — too narrow or too broad — and tune the vault collection's coverage.

**The Cap-Forced Confabulation.** Model hits the 2-supplement cap and confabulates instead of emitting COVERAGE GAP. Detection: trace shows two supplements followed by an answer with specific verifiable claims the supplements did not support. Mitigation: the explicit instruction to emit COVERAGE GAP after the cap is the structural fix; if it fails repeatedly, raise the cap or strengthen the post-cap instruction.

## Relationship to other frameworks

- **Phase A Prompt Cleanup** handles ambiguity *in the user's prompt*. Supplemental RAG handles ambiguity *in the model's information*. Different surfaces, different fixes.
- **Framework — Deep Research Protocol** is a heavier-weight retrieval framework for open-ended research questions. Supplemental RAG is per-step micro-retrieval inside an already-running pipeline turn.
- **Framework — Process Coherence** (Layer B oversight) supervises the pipeline as a whole; it does not handle per-call retrieval gaps.

## Status

Active canonical (v1.0, drafted 2026-05-15). Paired with `~/ora/frameworks/book/supplemental-rag-protocol.md` and implemented by `orchestrator/boot.py::_call_with_supplement` + `_parse_supplemental_request` + `_fetch_supplement` (added 2026-05-15).
