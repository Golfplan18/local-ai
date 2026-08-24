# Campaign Audit

_Generated 2026-08-23T03:38:55+00:00_

## Authenticated Sources

- Manifest: `/Users/oracle/ora/data/campaign/campaign-manifest.jsonl`
- Manifest SHA-256: `3d5b132e8f731c531a806417bbabe1ae33db056aaa2583a60f7738d1a66cd6d4`
- Corpus: `/Users/oracle/Documents/vault/Projects/Ora/Reference — Trigger Prompt Corpus.md`
- Corpus SHA-256: `bcfdac1eaa98e7fd627b300c2243b69b6addf7c075ed66fbf8a57f751f7482e3`

## Corpus

- Entries: 198
- Unique keys: 198
- By kind: {'mode': 60, 'visual': 22, 'lens': 116}
- Duplicate public ids: {'causal-dag': ['mode:causal-dag', 'visual:causal-dag'], 'fishbone-diagram': ['visual:fishbone-diagram', 'lens:fishbone-diagram']}

## Completeness

- Complete main four lanes: 198 / 198
- Complete selected lanes: 198 / 198

| pipeline | ok | failed latest | missing | total |
|---|---:|---:|---:|---:|
| premium | 198 | 0 | 0 | 198 |
| qwen9b | 198 | 0 | 0 | 198 |
| optimum | 198 | 0 | 0 | 198 |
| optimum-plus | 198 | 0 | 0 | 198 |
| single-pass | 198 | 0 | 0 | 198 |
| single-pass-9b | 198 | 0 | 0 | 198 |

## Capture Integrity

- Declared cells checked by the physical verifier: 1188
- Cells accepted by both manifest and capture verifier: 1188
- Verifier-reported affected cells: 0

Evidence state counts. Only `verified` and `attested` tie a capture's bytes to the cell that claims them; `unverified_legacy` is an honest record of captures written before the sidecar existed.

| evidence | cells |
|---|---|
| attested | 20 |
| unverified_legacy | 1164 |
| verified | 4 |

### Verifier-Reported Resume Selectors

These selectors are derived from the current manifest and physical capture check; they are not a hard-coded exception list.


## Accepted Trace Health

- Bare control rows excluded from trace-health accounting: 396
- Accepted Ora pipeline traces in scope: 792
- Accepted Ora traces with retained step-health: 0
- Historical Ora traces missing step-health: 792
- Traces with contingencies: 0
- Severity counts: {'clean': 0, 'info': 0, 'review': 0, 'verification_gap': 0, 'critical': 0}

### Historical Coverage Limitation

792 of 792 accepted Ora pipeline traces predate step-health persistence or lack a retained step-health file. This historical coverage gap is distinct from campaign-row completeness and is not represented as trace-health success.

Campaign-row completeness and trace-health coverage are separate. The 198/198 result certifies accepted row presence in every lane; it does not claim that historical step-health exists for every Ora trace.

### Contingency Categories


### Top Contingency Labels


### Highest-Severity Trace Samples
