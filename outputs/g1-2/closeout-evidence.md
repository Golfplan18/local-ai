# G1.2 Audit Closeout Evidence

## Execution environment

- Working directory: `/Users/oracle/ora-msi-central-routing`
- Platform: `Darwin 25.5.0 arm64`
- Python: `Python 3.14.3`
- `ORA_HOME`: unset
- `ORA_CAMPAIGN_DIR`: unset
- Accepted runtime baseline before this bounded correction: `007bb9c9`

## Exact command

```bash
cd /Users/oracle/ora-msi-central-routing
python3 scripts/campaign_run.py audit --output-dir outputs/g1-2
```

Exit status: `0`

## Exact result

```text
[audit] entries=198 complete_main4=198 complete_selected=198
[audit] premium: ok=198 failed=0 missing=0 total=198
[audit] qwen9b: ok=198 failed=0 missing=0 total=198
[audit] optimum: ok=198 failed=0 missing=0 total=198
[audit] optimum-plus: ok=198 failed=0 missing=0 total=198
[audit] single-pass: ok=198 failed=0 missing=0 total=198
[audit] single-pass-9b: ok=198 failed=0 missing=0 total=198
[audit] ora_traces=792 health_present=3 with_contingencies=1 historical_missing_health=789 bare_controls_excluded=396
[audit] severity_counts={'clean': 2, 'info': 0, 'review': 1, 'verification_gap': 0, 'critical': 0}
[audit] manifest=/Users/oracle/ora/data/campaign/campaign-manifest.jsonl sha256=e0c3aaf8fa3f65f59c8a8341595891c3493b45e2d75b20c0f6615b3db1160f43
[audit] corpus=/Users/oracle/Documents/vault/Projects/Ora/Reference — Trigger Prompt Corpus.md sha256=a251ff4d6751e5f7c22da073ff5a040e8c22d09697f821a99217e54b1d9571fd
[audit] wrote /Users/oracle/ora-msi-central-routing/outputs/g1-2/campaign-audit.json
[audit] wrote /Users/oracle/ora-msi-central-routing/outputs/g1-2/campaign-audit.md
```

## Artifact identities

- `campaign-audit.json`: SHA-256 `ed4d1f5ae6cd3a25b8a540fefa8f9d5a1d7587c874caea0bedf12d1e353020ad`
- `campaign-audit.md`: SHA-256 `bb44bff83a8805a8cbae2721f7979deb03cba1e19aec3fa05a1ca6b893b96e10`
- Authoritative manifest: SHA-256 `e0c3aaf8fa3f65f59c8a8341595891c3493b45e2d75b20c0f6615b3db1160f43`
- Canonical corpus: SHA-256 `a251ff4d6751e5f7c22da073ff5a040e8c22d09697f821a99217e54b1d9571fd`

## Interpretation boundary

The 198/198 result is campaign-row completeness across all six lanes. Trace-health accounting covers the four Ora pipeline lanes only: 396 bare-control rows are excluded because they have no Ora pipeline trace. Of 792 accepted Ora traces, 3 retain `step-health.json` and 789 historical traces do not. The missing historical health records are an explicit evidence-coverage limitation; they are not backfilled, inferred as healthy, or included in the 198/198 completeness claim.
