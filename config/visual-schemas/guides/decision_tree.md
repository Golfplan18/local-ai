**Structure.** A `decision_tree` (DECISION family, "decision-under-uncertainty" mode) is a rooted left-to-right tree of three node `kind`s: `decision` (square, a choice YOU control), `chance` (circle, an uncertain outcome NATURE controls), `terminal` (triangle leaf, an end-state). Edges live in `node.children[]` as `{edge_label, probability?, payoff?, node}`. `spec.mode` is `"decision"` or `"probability"`; if `"decision"`, `utility_units` is REQUIRED (e.g. "USD thousands (3-yr NPV)").

**vs siblings.** Not a `flowchart` (no payoffs/probabilities, process steps not gambles). Not `influence_diagram` (that's a DAG showing conditional-independence; a tree shows the unrolled sequence of choices and chances). If your nodes have no payoffs or probabilities, you picked the wrong type.

**Hard invariants (critical, auto-block):** (1) each chance node's children `probability` values sum to 1±1e-6, each in [0,1]; (2) every `terminal` carries a numeric `payoff` when mode=decision; (3) decision-node edges carry NO `probability`; (4) decision nodes have ≥1 child.

**The named failure modes — defeat each:**
- *Un-numbered tree* (EV=0 everywhere, payoff-free leaves): the deliverable a decision tree EXISTS to produce is a folded-back value and an optimal path. Populate EVERY terminal payoff. Surface the rollback EV per root branch and the chosen path in `semantic_description.type_specific` (`optimal_path`, `root_ev_by_branch`).
- *Flattened sequential branch*: a "Wait/Pilot/Stage" branch must model the REAL second stage as chance→`decision`→leaf — a genuine second-stage decision node, not collapsed to one leaf. Build at least one such two-stage branch.
- *Incoherent rollback* (positive root over all-negative leaves): hand-compute folded-back EV — chance node = Σ p·child, decision node = max over children — and make it consistent. Put the arithmetic in level_2.
- *Root label collision / over-elaboration*: keep root `label` short ("Fraud platform strategy"); put detail on `edge_label`. Don't invent splits the scenario didn't ask for; 3 root options, ≤2 two-stage branches.

**Labeling.** `edge_label` states the option or outcome and may embed "(p=0.45)"; node `label` names the state. Terminal labels are outcome states ("Owned IP, low run cost"), not numbers.

**semantic_description.** All three levels + short_alt(<=150) describing THIS tree (the optimal path + EVs), never "bar chart" boilerplate. Level_2 = the rollback arithmetic; level_3 = how close the branches cluster and where the tail risk sits.