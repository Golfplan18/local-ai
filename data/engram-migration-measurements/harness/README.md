# Measurement harness

The scripts that produced the numbers in the parent README. Preserved because
those numbers are not reproducible without them — the detector definitions and
thresholds live in the code, not the results.

| script | what it produced |
|---|---|
| `verify_phase_c.py` | the Phase C non-damage proof: strict edge counting plus a `git diff --name-only` check that nothing off-list moved. Hard-codes the strict rule (an edge is a line beginning `- type: ` at column 0) and documents the 87-phantom-edge trap that a looser parser produced once |
| `score_mechanical.py` | the mechanical-detector table: D2/D3/D4 from `prescan.py` plus D5, the generic novel-vocabulary check. D5 at threshold ≥20 is the 9/10 recall figure |
| `score_judge.py` | the judge comparison — recall, false-positive rate, and the net-fixed-per-10 column that shows a blind second pass is exactly break-even |
| `m3_judge.py` | MiniMax-M3 judging its own output against the blind benchmark |
| `analyze_pilot.py` | the standing-condition sentinel count, matched on a dash-normalized prefix because models vary between em dash, en dash and hyphen |

Two cautions carried from the parent README. The 80-case benchmark's labels are
an Opus pass, not human ground truth, so scoring against it measures agreement
with Opus rather than correctness. And `score_judge.py`'s net-fixed column
assumes a redo repairs a real defect ~87.5% of the time and breaks a sound note
~12.5% — the measured per-run rates. Change those and the ordering changes.

`verify_phase_c.py` reads `~/engram-work`, which was deleted when the repair
landed. It is kept for its counting rule and its record of the trap, not to be
re-run as-is.
