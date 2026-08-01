# Campaign Audit

_Generated 2026-07-20T03:27:14+00:00_

## Authenticated Sources

- Manifest: `/Users/oracle/ora/data/campaign/campaign-manifest.jsonl`
- Manifest SHA-256: `e0c3aaf8fa3f65f59c8a8341595891c3493b45e2d75b20c0f6615b3db1160f43`
- Corpus: `/Users/oracle/Documents/vault/Projects/Ora/Reference — Trigger Prompt Corpus.md`
- Corpus SHA-256: `a251ff4d6751e5f7c22da073ff5a040e8c22d09697f821a99217e54b1d9571fd`

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

## Accepted Trace Health

- Bare control rows excluded from trace-health accounting: 396
- Accepted Ora pipeline traces in scope: 792
- Accepted Ora traces with retained step-health: 3
- Historical Ora traces missing step-health: 789
- Traces with contingencies: 1
- Severity counts: {'clean': 2, 'info': 0, 'review': 1, 'verification_gap': 0, 'critical': 0}

### Historical Coverage Limitation

789 of 792 accepted Ora pipeline traces predate step-health persistence or lack a retained step-health file. This historical coverage gap is distinct from campaign-row completeness and is not represented as trace-health success.

Campaign-row completeness and trace-health coverage are separate. The 198/198 result certifies accepted row presence in every lane; it does not claim that historical step-health exists for every Ora trace.

### Contingency Categories

- unclassified: 1

### Top Contingency Labels

- 1 x `step6_5-gear3-quality-gate-PASS` - review / unclassified

### Highest-Severity Trace Samples

- review: `mode:passion-exploration` / `optimum-plus` - `step6_5-gear3-quality-gate-PASS`
