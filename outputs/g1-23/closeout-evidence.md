# G1.23 Mac/general soft-launch closeout evidence

Date: 2026-07-26 (America/Los_Angeles)

Behavioral runtime commit: `53087d10e119565b956b6fc55738ef494ea9d346`

Phase-2 recovery correction: `331291497164589c169be49c4de8b039e345fa5e`

Scope: G1.23 Phases 1–2 and static Windows refusal-path analysis only.

## Boundary

- This packet does not perform or claim the live Windows proof in Phase 3.
- `orchestrator/tests/test_windows_appcontainer_live.py` was not run. It remains coordinated with deferred G1.3 in the preserved Windows environment.
- MSI gear-script coverage and the live-chat `~/ora` repository reach limitation remain the already-declared exclusions.
- No G1.3, G1.7, G1.12, G1.17, G1.21, G1.22A/B, G1.24, channel, hardware, or Windows mutation entered this commit.

## Phase 1 — latency and cost

The measurement subject was a realistic vault-note mutation review: exact file name, Ora-valid YAML, exact body, a diff-name receipt, schema-validator success, and full-file capture.

### Baseline

With `ORA_EXECUTION_LOOP=0`, 50 calls to the terminal review seam produced:

- median: `0.000584 ms`
- p95: `0.001167 ms`
- maximum: `7.161125 ms` (cold import/outlier)

The ordinary server path emits `pipeline_stage: complete` and the response frame before Execution Review begins. The review therefore adds no time to first response delivery, but it keeps the SSE request/server worker alive until the review finishes.

### Findings and corrections

1. The general API output ceiling was 32,000 tokens. The first configured review exceeded 615 seconds and was terminated without a receipt. Execution Review now uses a 2,400-token compact-verdict ceiling.
2. The general long-form truncation retry doubled the first bounded allowance and duplicated findings. Execution Review now makes one call per endpoint; a truncated review is recorded as truncated and never doubled.
3. New direct-vendor endpoints omitted `training_family`, so the active `budget` profile degraded to same/unknown-family review. The router now preserves explicit family metadata and otherwise derives family from the actual model identity first, then a non-generic direct provider. Generic/OpenRouter transport remains unknown.
4. An unavailable primary cross-family endpoint suppressed declared profile fallbacks. Execution Review now walks only the profile's remaining confirmed cross-family candidates and records the exact endpoint that produced the verdict.

### Corrected live result

The corrected active `budget` path resolved executor family `minimax`, rejected the unavailable `deepseek` primary, and obtained a real cross-family `PASS` from the next declared `glm`-family endpoint:

- elapsed terminal-tail time: `12.097912 s`
- authenticated usage receipt: `304` prompt + `652` completion = `956` tokens
- calls with usage: `1`
- exact dollar cost: `unavailable`, not zero. The direct endpoint has no price in the active model registry/routing row. `compute_cost_summary()` therefore reports the model as unpriced. The runtime must not invent a dollar value from a different transport's catalogue.
- reviewer assurance: cross-family (`same_family: false`), `PASS`, confidence `0.93`

For comparison, the earlier same-family MiniMax measurement produced an authenticated `2,237`-token receipt in `63.313529 s`; its routing-row price computed to `$0.00219570`. That value is provenance for the replaced path, not a claim about the corrected GLM call.

Disposition: **PASS with disclosed pricing limitation.** The user receives the response before the 12.1-second review tail, the runaway/retry defects are closed, cross-family fallback is real, and missing direct-vendor price data is represented as unavailable rather than free.

## Phase 2 — escalation branch and user comprehension

The real-git escalation regression creates `execution-review/escalation-<task_id>-<turn>` from the persisted pre-execution base with a throwaway index, leaves the user's HEAD/index/working tree untouched, and preserves the branch without merging it.

The product gap was real: the Paused API/UI projected only a raw `ExecutionReviewEscalation` event and generic reasoning. The bounded correction:

- authenticates the review kind from the persisted handback;
- exposes only a grammar-checked `execution-review/escalation-*` attempt reference;
- labels the card `Execution Review`;
- explains that Ora could not independently verify the turn;
- says the preserved review branch was not automatically merged; and
- keeps Approve, Deny, and Discuss on the existing Paused resolution path.

Untrusted branch strings, shell punctuation, non-review refs, and overlong refs are not projected.

Independent judgment then found one recovery defect in the branch mechanism: it published a base-only placeholder ref before the throwaway-index snapshot succeeded and ignored several Git return codes. A failed `write-tree` could therefore return a branch name even though no attempted changes had been captured. The recovery correction now:

- checks `read-tree`, `add -A`, `write-tree`, `commit-tree`, ref lookup, `update-ref`, and exact readback;
- completes the attempt commit before publishing any ref;
- uses compare-and-swap publication against the exact previous ref identity;
- restores that exact ref, or deletes a newly created ref, if publication cannot be authenticated;
- leaves the user's HEAD, staged index, and working tree unchanged; and
- withholds the handback and preserved-attempt claim whenever capture returns no authenticated ref.

Fault injection covers every listed stage for both new and pre-existing refs. The Judge's exact `write-tree` reproducer now returns `None`, with calls ending at `write-tree` and no branch operation.

Disposition: **NEEDS FIX → FIXED.** Both the safe branch publication/recovery contract and the missing user explanation are now shipped and exercised through real Git and DOM surfaces.

## Static Windows refusal-path analysis

The shipping Windows launcher enables `ORA_EXECUTION_LOOP=1` but does not enable `ORA_WINDOWS_APPCONTAINER`. Native AppContainer remains an explicit opt-in spike. With no native backend or declared enforcing wrapper:

- the evidence runner returns `skipped=true` with an explicit “NOT run unenforced” reason;
- no subprocess is created;
- no orchestrated enforcement claim is recorded;
- a refused/skipped check is insufficient evidence but is not a ran-and-failed check;
- backend absence alone therefore does not create an escalation branch or human hold; and
- the loop degrades to its recorded reduced-verification/text-review state rather than treating refusal as a test failure.

AppContainer setup/launch failures take the same refusal path. Static structural/ABI/ACL/job/recovery contracts remain covered by `test_windows_appcontainer.py`.

Disposition: **STATIC PASS; LIVE EVIDENCE DEFERRED.** Phase 3 must still run `test_windows_appcontainer_live.py` and a public-turn refusal probe during deferred G1.3. No Windows-support or Gate-1 claim is made here.

## Reproducible verification

Working directory for every command: `/Users/oracle/ora-msi-central-routing`.

### Owning Python matrix

```bash
ORA_SCRATCH=/private/tmp/g1-23-scratch PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider orchestrator/tests/test_g1_23_execution_review_readiness.py orchestrator/tests/test_execution_loop.py orchestrator/tests/test_execution_packet.py orchestrator/tests/test_execution_persistence.py orchestrator/tests/test_execution_provenance.py orchestrator/tests/test_execution_review.py orchestrator/tests/test_evidence_runner.py orchestrator/tests/test_isolated_actuator.py orchestrator/tests/test_windows_appcontainer.py orchestrator/tests/test_execution_families.py orchestrator/tests/test_model_router.py orchestrator/tests/test_router_config_name.py --tb=short
```

Result: `416 passed, 14 subtests passed in 8.64s`; exit `0`. The live-Windows suite is intentionally absent.

### Focused plus adjacent Python matrix

```bash
ORA_SCRATCH=/private/tmp/g1-23-scratch PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider orchestrator/tests/test_g1_23_execution_review_readiness.py orchestrator/tests/test_execution_loop.py orchestrator/tests/test_evidence_runner.py orchestrator/tests/test_model_router.py orchestrator/tests/test_router_config_name.py orchestrator/tests/test_trace_manifest.py::TestPhysicalModelCallConfig::test_truncation_retry_records_each_effective_attempt --tb=short
```

Result: `201 passed, 12 subtests passed, 4 warnings in 5.06s`; exit `0`. Warnings are the pre-existing `datetime.utcnow()` deprecations in `pipeline_trace.py`.

### Judge recovery reproducer

```bash
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from orchestrator import execution_loop as el
calls=[]
def failing_git(repo, args, env=None):
    calls.append(tuple(args))
    if args[0] in {'branch','read-tree','add'}:
        return 0, ''
    if args[0] == 'write-tree':
        return 1, 'simulated write-tree failure'
    raise AssertionError(args)
ref = el.create_escalation_branch(
    '/tmp/does-not-matter', 'a'*40, 'recovery-probe',
    trace_dir='/tmp/turn-1', git=failing_git)
print(ref)
print(calls)
PY
```

Result: `None`, followed by `[('read-tree', ...), ('add', '-A'), ('write-tree',)]`; exit `0`. No ref operation occurs.

### Browser DOM

```bash
node server/static/tests/test-process-attention.js
```

Result: `18 / 18 tests passed`; exit `0`.

### Syntax and diff integrity

```bash
PYTHONPYCACHEPREFIX=/private/tmp/g1-23-pycache python3 -m py_compile orchestrator/boot.py orchestrator/execution_loop.py orchestrator/router.py server/server.py orchestrator/tests/test_g1_23_execution_review_readiness.py orchestrator/tests/test_execution_loop.py
node --check server/static/js/sidebar-oversight.js
node --check server/static/tests/test-process-attention.js
git diff --check
```

Result: all commands exit `0`.

## Deferred acceptance condition

This packet is the bounded Mac/general submission requested before G1.24. Full G1.23 remains open until the live Windows Phase-3 evidence is joined from G1.3. It does not authorize a release-candidate declaration.
