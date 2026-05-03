<!-- Phase 4 Wave 3 signals appended 2026-05-01 (causal-dag, process-tracing, fragility-antifragility-audit, principled-negotiation, third-side, mechanism-understanding, process-mapping, place-reading-genius-loci, information-density). -->


# Reference — Signal Vocabulary Registry

The signal vocabulary registry maps prompt vocabulary to territories, modes, and disambiguation answers (Decision 4). It is consulted by the Stage 2 sufficiency analyzer of the four-stage pre-routing pipeline. The registry's job is not to make routing decisions on its own — it provides the controlled vocabulary against which prompts are scanned, with each match contributing weight toward a candidate mode within a territory. Phase 2 enriches the registry per migrated mode; Phase 4 adds new-mode signals per wave.

T-numbering follows the locked 21-territory inventory in `Reference — Analytical Territories.md`. Sections are ordered T1 → T21.

## Entry format

Each row in a territory section provides five fields:

- **`signal`** — the prompt phrase or substring to match (case-insensitive). Substring matching is the default; longer matches win on overlap (see Query Interface).
- **`territory`** — `T<n>-<short-name>` identifying the territory the signal points into.
- **`mode`** — the `mode_id` this signal points toward within the territory.
- **`disambiguation_answer`** — when this signal is the answer to a within-territory disambiguation question, name the question stem; otherwise `—`.
- **`confidence_weight`** — `strong` (explicit method-name reference, unambiguous vocabulary) or `weak` (tonal cue, contextual implication).
- **`evidence_for_mapping`** — brief rationale (e.g., "explicit method-name reference", "trigger phrase from mode positive list", "tonal cue").

Each migrated mode contributes 5–15 entries — 2–3 mode-name aliases plus trigger phrases extracted from the mode file's `## TRIGGER CONDITIONS → Positive` list. Strong-confidence entries cap at ~10 per mode; weak-confidence entries can extend to 15.

---

## T1 — Argumentative Artifact Examination

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| coherence audit | T1-argumentative-artifact-examination | coherence-audit | within-territory: stance? → neutral | strong | mode-name reference |
| does this argument hold up | T1-argumentative-artifact-examination | coherence-audit | within-territory: stance? → neutral | strong | trigger phrase |
| is this argument sound | T1-argumentative-artifact-examination | coherence-audit | within-territory: stance? → neutral | strong | trigger phrase |
| does the argument work | T1-argumentative-artifact-examination | coherence-audit | within-territory: stance? → neutral | strong | trigger phrase |
| check the logic | T1-argumentative-artifact-examination | coherence-audit | — | strong | trigger phrase |
| fallacy check | T1-argumentative-artifact-examination | coherence-audit | — | strong | trigger phrase |
| fallacy detection | T1-argumentative-artifact-examination | coherence-audit | — | strong | trigger phrase |
| fallacies | T1-argumentative-artifact-examination | coherence-audit | — | strong | mode vocabulary |
| internal consistency | T1-argumentative-artifact-examination | coherence-audit | within-territory: stance? → neutral | strong | mode vocabulary |
| argument soundness | T1-argumentative-artifact-examination | coherence-audit | within-territory: stance? → neutral | strong | trigger phrase |
| Toulmin | T1-argumentative-artifact-examination | coherence-audit | — | strong | method-name reference |
| warrant | T1-argumentative-artifact-examination | coherence-audit | — | strong | mode vocabulary |
| premises and conclusion | T1-argumentative-artifact-examination | coherence-audit | — | strong | trigger phrase |
| inferential audit | T1-argumentative-artifact-examination | coherence-audit | — | strong | trigger phrase |
| frame audit | T1-argumentative-artifact-examination | frame-audit | within-territory: stance? → suspending | strong | mode-name reference |
| framing analysis | T1-argumentative-artifact-examination | frame-audit | within-territory: stance? → suspending | strong | trigger phrase |
| what frame | T1-argumentative-artifact-examination | frame-audit | within-territory: stance? → suspending | strong | trigger phrase |
| framing | T1-argumentative-artifact-examination | frame-audit | within-territory: stance? → suspending | strong | trigger phrase |
| what's the lens | T1-argumentative-artifact-examination | frame-audit | within-territory: stance? → suspending | strong | trigger phrase |
| what's foregrounded | T1-argumentative-artifact-examination | frame-audit | — | strong | trigger phrase |
| what's backgrounded | T1-argumentative-artifact-examination | frame-audit | — | strong | trigger phrase |
| what is selected in and selected out | T1-argumentative-artifact-examination | frame-audit | — | strong | trigger phrase |
| Lakoff | T1-argumentative-artifact-examination | frame-audit | — | strong | author/method reference |
| Lakoff frame | T1-argumentative-artifact-examination | frame-audit | — | strong | method-name reference |
| Goffman frame analysis | T1-argumentative-artifact-examination | frame-audit | — | strong | method-name reference |
| Entman framing functions | T1-argumentative-artifact-examination | frame-audit | — | strong | method-name reference |
| tacit assumptions in this frame | T1-argumentative-artifact-examination | frame-audit | within-territory: stance? → suspending | strong | trigger phrase |
| naturalization | T1-argumentative-artifact-examination | frame-audit | — | strong | mode vocabulary |
| presupposition smuggling | T1-argumentative-artifact-examination | frame-audit | — | strong | mode vocabulary |
| propaganda audit | T1-argumentative-artifact-examination | propaganda-audit | within-territory: stance? → adversarial | strong | mode-name reference |
| propaganda | T1-argumentative-artifact-examination | propaganda-audit | within-territory: stance? → adversarial | strong | mode-name shorthand |
| is this propaganda | T1-argumentative-artifact-examination | propaganda-audit | within-territory: stance? → adversarial | strong | trigger phrase |
| manipulation | T1-argumentative-artifact-examination | propaganda-audit | — | strong | mode vocabulary |
| manufacturing consent | T1-argumentative-artifact-examination | propaganda-audit | — | strong | framework reference |
| Manufacturing Consent | T1-argumentative-artifact-examination | propaganda-audit | — | strong | book reference |
| Stanley | T1-argumentative-artifact-examination | propaganda-audit | — | strong | author reference |
| Stanley test | T1-argumentative-artifact-examination | propaganda-audit | — | strong | method-name reference |
| supporting vs undermining propaganda | T1-argumentative-artifact-examination | propaganda-audit | — | strong | mode vocabulary |
| flawed ideology | T1-argumentative-artifact-examination | propaganda-audit | — | strong | mode vocabulary |
| concept-substitution | T1-argumentative-artifact-examination | propaganda-audit | — | strong | mode vocabulary |
| not-at-issue content | T1-argumentative-artifact-examination | propaganda-audit | — | strong | mode vocabulary |
| engineering of consent | T1-argumentative-artifact-examination | propaganda-audit | — | strong | method-name reference |
| manufactured doubt | T1-argumentative-artifact-examination | propaganda-audit | — | weak | tonal cue (propaganda) |
| argument audit | T1-argumentative-artifact-examination | argument-audit | within-territory: depth? → molecular | strong | mode-name reference |
| audit this argument fully | T1-argumentative-artifact-examination | argument-audit | within-territory: depth? → molecular | strong | trigger phrase |
| comprehensive argument analysis | T1-argumentative-artifact-examination | argument-audit | within-territory: depth? → molecular | strong | trigger phrase |
| Frame Audit and Coherence Audit together | T1-argumentative-artifact-examination | argument-audit | within-territory: depth? → molecular | strong | composition reference |
| frame and coherence audit | T1-argumentative-artifact-examination | argument-audit | within-territory: depth? → molecular | strong | composition reference |
| argument audit molecular | T1-argumentative-artifact-examination | argument-audit | — | strong | mode-name + composition reference |
| full argument analysis | T1-argumentative-artifact-examination | argument-audit | within-territory: depth? → molecular | strong | trigger phrase |
| analyze this argument from every angle | T1-argumentative-artifact-examination | argument-audit | within-territory: depth? → molecular | strong | trigger phrase |
| frame and inference audit | T1-argumentative-artifact-examination | argument-audit | within-territory: depth? → molecular | strong | composition reference |
| both frame and logic | T1-argumentative-artifact-examination | argument-audit | within-territory: depth? → molecular | strong | composition trigger |
| comprehensive argument examination | T1-argumentative-artifact-examination | argument-audit | within-territory: depth? → molecular | strong | trigger phrase |
| full argumentative artifact examination | T1-argumentative-artifact-examination | argument-audit | within-territory: depth? → molecular | strong | trigger phrase |
| deep argument review | T1-argumentative-artifact-examination | argument-audit | within-territory: depth? → molecular | weak | tonal cue (depth) |

---

## T2 — Interest and Power Analysis

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| cui bono | T2-interest-and-power | cui-bono | — | strong | mode-name reference |
| who benefits | T2-interest-and-power | cui-bono | — | strong | trigger phrase |
| whose interests | T2-interest-and-power | cui-bono | — | strong | trigger phrase |
| who gains from X | T2-interest-and-power | cui-bono | — | strong | trigger phrase |
| trace the interests | T2-interest-and-power | cui-bono | — | strong | trigger phrase |
| what does the institution want | T2-interest-and-power | cui-bono | — | strong | trigger phrase |
| distributional | T2-interest-and-power | cui-bono | — | strong | mode vocabulary |
| who pays | T2-interest-and-power | cui-bono | — | strong | trigger phrasing |
| FGL | T2-interest-and-power | cui-bono | — | strong | tool reference |
| fear greed laziness | T2-interest-and-power | cui-bono | — | strong | tool name reference |
| follow the money | T2-interest-and-power | cui-bono | — | weak | tonal cue (distributional) |
| structural incentive | T2-interest-and-power | cui-bono | — | weak | tonal cue (institutional) |
| wicked problem | T2-interest-and-power | wicked-problems | — | strong | framework name reference |
| WPF | T2-interest-and-power | wicked-problems | — | strong | framework abbreviation |
| irreducible value conflict | T2-interest-and-power | wicked-problems | — | strong | wicked-problem indicator |
| no good answer | T2-interest-and-power | wicked-problems | — | weak | tonal cue (wickedness) |
| every option harms someone | T2-interest-and-power | wicked-problems | — | weak | tonal cue (incompatible benefit structures) |
| stakeholders fundamentally disagree | T2-interest-and-power | wicked-problems | — | weak | tonal cue (value conflict) |
| boundary critique | T2-interest-and-power | boundary-critique | within-territory: stance? → critical | strong | mode-name reference |
| Ulrich | T2-interest-and-power | boundary-critique | within-territory: stance? → critical | strong | author reference |
| CSH | T2-interest-and-power | boundary-critique | within-territory: stance? → critical | strong | method abbreviation |
| critical systems heuristics | T2-interest-and-power | boundary-critique | within-territory: stance? → critical | strong | method-name reference |
| boundary judgments | T2-interest-and-power | boundary-critique | — | strong | mode vocabulary |
| whose voices are missing | T2-interest-and-power | boundary-critique | within-territory: stance? → critical | strong | trigger phrase |
| whose voice is missing | T2-interest-and-power | boundary-critique | within-territory: stance? → critical | strong | trigger phrase |
| who's left out | T2-interest-and-power | boundary-critique | within-territory: stance? → critical | strong | trigger phrase |
| who is excluded | T2-interest-and-power | boundary-critique | within-territory: stance? → critical | strong | trigger phrase |
| who isn't being asked | T2-interest-and-power | boundary-critique | within-territory: stance? → critical | strong | trigger phrase |
| is/ought boundary | T2-interest-and-power | boundary-critique | — | strong | mode vocabulary |
| sources of motivation | T2-interest-and-power | boundary-critique | — | strong | Ulrich category vocabulary |
| sources of legitimacy | T2-interest-and-power | boundary-critique | — | strong | Ulrich category vocabulary |
| affected but not involved | T2-interest-and-power | boundary-critique | — | strong | mode vocabulary |
| what's outside the system being analyzed | T2-interest-and-power | boundary-critique | — | weak | tonal cue (boundary) |
| decision clarity | T2-interest-and-power | decision-clarity | within-territory: output? → decision-document | strong | mode-name reference |
| decision clarity document | T2-interest-and-power | decision-clarity | within-territory: output? → decision-document | strong | mode-name + output reference |
| produce a decision document | T2-interest-and-power | decision-clarity | within-territory: output? → decision-document | strong | trigger phrase |
| decision-maker brief | T2-interest-and-power | decision-clarity | within-territory: output? → decision-document | strong | trigger phrase |
| wicked decision document | T2-interest-and-power | decision-clarity | within-territory: output? → decision-document | strong | trigger phrase |
| produce a brief for the decision-maker | T2-interest-and-power | decision-clarity | within-territory: output? → decision-document | strong | trigger phrase |
| stakeholder-and-scenario document | T2-interest-and-power | decision-clarity | within-territory: output? → decision-document | strong | composition reference |
| third-party decision support document | T2-interest-and-power | decision-clarity | within-territory: output? → decision-document | strong | trigger phrase |
| decision clarity analysis | T2-interest-and-power | decision-clarity | within-territory: output? → decision-document | strong | framework reference |
| help a decision-maker see clearly | T2-interest-and-power | decision-clarity | within-territory: output? → decision-document | weak | tonal cue (decision-document) |
| comprehensive decision brief | T2-interest-and-power | decision-clarity | within-territory: output? → decision-document | strong | trigger phrase |
| cui-bono with stakeholders and scenarios | T2-interest-and-power | decision-clarity | within-territory: depth? → molecular | strong | composition reference |

---

## T3 — Decision-Making Under Uncertainty

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| constraint mapping | T3-decision-under-uncertainty | constraint-mapping | within-territory: deterministic? → yes | strong | mode-name reference |
| compare alternatives | T3-decision-under-uncertainty | constraint-mapping | within-territory: deterministic? → yes | strong | trigger phrase |
| map the tradeoffs | T3-decision-under-uncertainty | constraint-mapping | within-territory: deterministic? → yes | strong | trigger phrase |
| pros and cons of each option | T3-decision-under-uncertainty | constraint-mapping | within-territory: deterministic? → yes | strong | trigger phrase |
| which should I choose | T3-decision-under-uncertainty | constraint-mapping | within-territory: deterministic? → yes | strong | trigger phrase |
| 2x2 matrix | T3-decision-under-uncertainty | constraint-mapping | within-territory: deterministic? → yes | strong | trigger phrase (strategic_2x2) |
| strategic 2x2 | T3-decision-under-uncertainty | constraint-mapping | within-territory: deterministic? → yes | strong | method-name reference |
| viable options | T3-decision-under-uncertainty | constraint-mapping | — | weak | tonal cue (option space) |
| best fit | T3-decision-under-uncertainty | constraint-mapping | — | weak | tonal cue (selection) |
| decision under uncertainty | T3-decision-under-uncertainty | decision-under-uncertainty | — | strong | mode-name reference |
| DUU | T3-decision-under-uncertainty | decision-under-uncertainty | — | strong | mode abbreviation |
| decision tree | T3-decision-under-uncertainty | decision-under-uncertainty | — | strong | trigger phrase |
| should we act now or wait | T3-decision-under-uncertainty | decision-under-uncertainty | — | strong | trigger phrase |
| expected value | T3-decision-under-uncertainty | decision-under-uncertainty | — | strong | trigger phrase |
| is it worth waiting for more information | T3-decision-under-uncertainty | decision-under-uncertainty | — | strong | trigger phrase |
| value of information | T3-decision-under-uncertainty | decision-under-uncertainty | — | strong | trigger phrase |
| minimax regret | T3-decision-under-uncertainty | decision-under-uncertainty | — | strong | method-name reference |
| real options | T3-decision-under-uncertainty | decision-under-uncertainty | — | strong | method-name reference |
| hedge | T3-decision-under-uncertainty | decision-under-uncertainty | — | weak | tonal cue (optionality) |
| defer | T3-decision-under-uncertainty | decision-under-uncertainty | — | weak | tonal cue (wait-and-learn) |
| multi-criteria decision | T3-decision-under-uncertainty | multi-criteria-decision | within-territory: complexity? → multi-criteria | strong | mode-name reference |
| multi-criteria | T3-decision-under-uncertainty | multi-criteria-decision | within-territory: complexity? → multi-criteria | strong | mode-name shorthand |
| weigh several criteria | T3-decision-under-uncertainty | multi-criteria-decision | within-territory: complexity? → multi-criteria | strong | trigger phrase |
| multiple criteria | T3-decision-under-uncertainty | multi-criteria-decision | within-territory: complexity? → multi-criteria | strong | trigger phrase |
| MCDA | T3-decision-under-uncertainty | multi-criteria-decision | — | strong | method abbreviation |
| MCDM | T3-decision-under-uncertainty | multi-criteria-decision | — | strong | method abbreviation |
| AHP | T3-decision-under-uncertainty | multi-criteria-decision | — | strong | method abbreviation |
| weighted-sum decision | T3-decision-under-uncertainty | multi-criteria-decision | — | strong | trigger phrase |
| weighted criteria | T3-decision-under-uncertainty | multi-criteria-decision | — | strong | trigger phrase |
| SMART analysis | T3-decision-under-uncertainty | multi-criteria-decision | — | strong | method-name reference |
| ELECTRE | T3-decision-under-uncertainty | multi-criteria-decision | — | strong | method-name reference |
| TOPSIS | T3-decision-under-uncertainty | multi-criteria-decision | — | strong | method-name reference |
| pairwise comparison | T3-decision-under-uncertainty | multi-criteria-decision | — | strong | method vocabulary |
| criteria matrix | T3-decision-under-uncertainty | multi-criteria-decision | — | strong | trigger phrase |
| prioritize across dimensions | T3-decision-under-uncertainty | multi-criteria-decision | within-territory: complexity? → multi-criteria | strong | trigger phrase |
| rank options across | T3-decision-under-uncertainty | multi-criteria-decision | — | strong | trigger phrase |
| decision architecture | T3-decision-under-uncertainty | decision-architecture | within-territory: depth? → molecular | strong | mode-name reference |
| integrated decision analysis | T3-decision-under-uncertainty | decision-architecture | within-territory: depth? → molecular | strong | trigger phrase |
| decision with multiple stakeholders and risks | T3-decision-under-uncertainty | decision-architecture | within-territory: depth? → molecular | strong | trigger phrase |
| decision design | T3-decision-under-uncertainty | decision-architecture | within-territory: depth? → molecular | strong | trigger phrase |
| comprehensive decision analysis | T3-decision-under-uncertainty | decision-architecture | within-territory: depth? → molecular | strong | trigger phrase |
| design this decision | T3-decision-under-uncertainty | decision-architecture | within-territory: depth? → molecular | strong | trigger phrase |
| DUU plus stakeholders plus pre-mortem | T3-decision-under-uncertainty | decision-architecture | within-territory: depth? → molecular | strong | composition reference |
| decision under uncertainty with constraints stakeholders pre-mortem | T3-decision-under-uncertainty | decision-architecture | within-territory: depth? → molecular | strong | composition reference |
| full decision architecture | T3-decision-under-uncertainty | decision-architecture | within-territory: depth? → molecular | strong | mode-name reference |
| comprehensive decision design | T3-decision-under-uncertainty | decision-architecture | within-territory: depth? → molecular | strong | trigger phrase |
| decision involving uncertainty constraints stakeholders and risk | T3-decision-under-uncertainty | decision-architecture | within-territory: depth? → molecular | strong | trigger phrase |
| build the full decision picture | T3-decision-under-uncertainty | decision-architecture | within-territory: depth? → molecular | weak | tonal cue (molecular) |

---

## T4 — Causal Investigation

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| root cause | T4-causal-investigation | root-cause-analysis | — | strong | mode-name reference |
| RCA | T4-causal-investigation | root-cause-analysis | — | strong | mode abbreviation |
| fishbone | T4-causal-investigation | root-cause-analysis | — | strong | trigger phrase |
| Ishikawa | T4-causal-investigation | root-cause-analysis | — | strong | trigger phrase |
| 5 whys | T4-causal-investigation | root-cause-analysis | — | strong | trigger phrase |
| why does this keep happening | T4-causal-investigation | root-cause-analysis | — | strong | trigger phrase |
| what's the real problem | T4-causal-investigation | root-cause-analysis | — | strong | trigger phrase |
| we've tried X but it didn't work | T4-causal-investigation | root-cause-analysis | — | strong | trigger phrase |
| diagnose | T4-causal-investigation | root-cause-analysis | — | weak | tonal cue (backward causal) |
| postmortem | T4-causal-investigation | root-cause-analysis | — | weak | tonal cue (failure trace) |
| what went wrong | T4-causal-investigation | root-cause-analysis | — | weak | tonal cue (backward) |
| systems dynamics | T4-causal-investigation | systems-dynamics-causal | within-territory: feedback present? → yes | strong | mode-name reference (causal-flavoured) |
| feedback loop | T4-causal-investigation | systems-dynamics-causal | within-territory: feedback present? → yes | strong | trigger phrase (loop signal) |
| why does fixing X make things worse | T4-causal-investigation | systems-dynamics-causal | within-territory: counterintuitive? → yes | strong | trigger phrase |
| counterintuitive | T4-causal-investigation | systems-dynamics-causal | within-territory: feedback present? → yes | weak | tonal cue (loops) |
| causal DAG | T4-causal-investigation | causal-dag | within-territory: depth? → thorough + formalism? → explicit | strong | mode-name reference |
| causal dag | T4-causal-investigation | causal-dag | within-territory: depth? → thorough + formalism? → explicit | strong | mode-name shorthand |
| Pearl | T4-causal-investigation | causal-dag | — | strong | author reference |
| do-calculus | T4-causal-investigation | causal-dag | — | strong | method-name reference |
| do calculus | T4-causal-investigation | causal-dag | — | strong | method-name reference |
| do-operator | T4-causal-investigation | causal-dag | — | strong | method vocabulary |
| directed acyclic graph | T4-causal-investigation | causal-dag | — | strong | method-name reference |
| backdoor criterion | T4-causal-investigation | causal-dag | — | strong | method vocabulary |
| back-door criterion | T4-causal-investigation | causal-dag | — | strong | method vocabulary |
| front-door criterion | T4-causal-investigation | causal-dag | — | strong | method vocabulary |
| d-separation | T4-causal-investigation | causal-dag | — | strong | method vocabulary |
| confounder | T4-causal-investigation | causal-dag | — | strong | method vocabulary |
| collider | T4-causal-investigation | causal-dag | — | strong | method vocabulary |
| intervention model | T4-causal-investigation | causal-dag | — | strong | trigger phrase |
| intervention vs observation | T4-causal-investigation | causal-dag | — | strong | trigger phrase |
| counterfactual | T4-causal-investigation | causal-dag | — | strong | trigger phrase |
| what would happen if we did X | T4-causal-investigation | causal-dag | — | strong | trigger phrase |
| identifiability | T4-causal-investigation | causal-dag | — | strong | method vocabulary |
| process tracing | T4-causal-investigation | process-tracing | within-territory: specificity? → historical-event | strong | mode-name reference |
| process-tracing | T4-causal-investigation | process-tracing | within-territory: specificity? → historical-event | strong | mode-name reference |
| Bennett-Checkel | T4-causal-investigation | process-tracing | — | strong | author reference |
| Bennett Checkel | T4-causal-investigation | process-tracing | — | strong | author reference |
| hoop test | T4-causal-investigation | process-tracing | — | strong | method-name reference |
| smoking-gun test | T4-causal-investigation | process-tracing | — | strong | method-name reference |
| smoking gun | T4-causal-investigation | process-tracing | — | strong | method-name reference |
| doubly-decisive test | T4-causal-investigation | process-tracing | — | strong | method-name reference |
| doubly decisive | T4-causal-investigation | process-tracing | — | strong | method-name reference |
| straw in the wind | T4-causal-investigation | process-tracing | — | strong | method-name reference |
| straw-in-the-wind | T4-causal-investigation | process-tracing | — | strong | method-name reference |
| historical event causal | T4-causal-investigation | process-tracing | — | strong | trigger phrase |
| what really happened | T4-causal-investigation | process-tracing | — | strong | trigger phrase |
| trace the causal chain | T4-causal-investigation | process-tracing | — | strong | trigger phrase |
| case study causal inference | T4-causal-investigation | process-tracing | — | strong | trigger phrase |

---

## T5 — Hypothesis Evaluation

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| differential diagnosis | T5-hypothesis-evaluation | differential-diagnosis | within-territory: depth? → light | strong | mode-name reference |
| differential | T5-hypothesis-evaluation | differential-diagnosis | within-territory: depth? → light | strong | mode-name shorthand |
| candidate explanations | T5-hypothesis-evaluation | differential-diagnosis | — | strong | trigger phrase |
| what are the possibilities | T5-hypothesis-evaluation | differential-diagnosis | — | strong | trigger phrase |
| rule out | T5-hypothesis-evaluation | differential-diagnosis | — | strong | trigger phrase |
| rule things out quickly | T5-hypothesis-evaluation | differential-diagnosis | within-territory: depth? → light | strong | trigger phrase |
| most likely cause | T5-hypothesis-evaluation | differential-diagnosis | — | strong | trigger phrase |
| narrow down the candidates | T5-hypothesis-evaluation | differential-diagnosis | — | strong | trigger phrase |
| what else could this be | T5-hypothesis-evaluation | differential-diagnosis | — | strong | trigger phrase |
| quick weigh-in | T5-hypothesis-evaluation | differential-diagnosis | within-territory: depth? → light | weak | tonal cue (depth-light selector) |
| zebra | T5-hypothesis-evaluation | differential-diagnosis | — | weak | medical-tradition vocabulary (rare-but-serious) |
| competing hypotheses | T5-hypothesis-evaluation | competing-hypotheses | within-territory: depth? → thorough | strong | mode-name reference |
| ACH | T5-hypothesis-evaluation | competing-hypotheses | within-territory: depth? → thorough | strong | mode abbreviation |
| ACH matrix | T5-hypothesis-evaluation | competing-hypotheses | within-territory: depth? → thorough | strong | trigger phrase |
| which explanation fits best | T5-hypothesis-evaluation | competing-hypotheses | — | strong | trigger phrase |
| what rules out X | T5-hypothesis-evaluation | competing-hypotheses | — | strong | trigger phrase |
| how would we know if we're wrong | T5-hypothesis-evaluation | competing-hypotheses | — | strong | trigger phrase |
| strongest evidence against each theory | T5-hypothesis-evaluation | competing-hypotheses | — | strong | trigger phrase |
| Heuer | T5-hypothesis-evaluation | competing-hypotheses | — | strong | author/method reference |
| disconfirmation | T5-hypothesis-evaluation | competing-hypotheses | — | strong | mode posture vocabulary |
| diagnosticity | T5-hypothesis-evaluation | competing-hypotheses | — | strong | mode vocabulary |
| deception possible | T5-hypothesis-evaluation | competing-hypotheses | — | weak | tonal cue (intelligence framing) |
| Bayesian network | T5-hypothesis-evaluation | bayesian-hypothesis-network | within-territory: depth? → molecular | strong | mode-name reference |
| Bayesian hypothesis network | T5-hypothesis-evaluation | bayesian-hypothesis-network | within-territory: depth? → molecular | strong | mode-name reference |
| probabilistic posterior over hypotheses | T5-hypothesis-evaluation | bayesian-hypothesis-network | within-territory: depth? → molecular | strong | trigger phrase |
| ACH with priors | T5-hypothesis-evaluation | bayesian-hypothesis-network | within-territory: depth? → molecular | strong | composition reference |
| ACH plus priors | T5-hypothesis-evaluation | bayesian-hypothesis-network | within-territory: depth? → molecular | strong | composition reference |
| Bayes net | T5-hypothesis-evaluation | bayesian-hypothesis-network | — | strong | method abbreviation |
| Pearl Bayesian network | T5-hypothesis-evaluation | bayesian-hypothesis-network | — | strong | author + method reference |
| posterior probability | T5-hypothesis-evaluation | bayesian-hypothesis-network | within-territory: depth? → molecular | strong | method vocabulary |
| likelihood ratios across hypotheses | T5-hypothesis-evaluation | bayesian-hypothesis-network | within-territory: depth? → molecular | strong | trigger phrase |
| sensitivity to priors | T5-hypothesis-evaluation | bayesian-hypothesis-network | within-territory: depth? → molecular | strong | method vocabulary |
| differential plus ACH plus Bayesian | T5-hypothesis-evaluation | bayesian-hypothesis-network | within-territory: depth? → molecular | strong | composition reference |
| full hypothesis network | T5-hypothesis-evaluation | bayesian-hypothesis-network | within-territory: depth? → molecular | strong | trigger phrase |
| comprehensive hypothesis evaluation | T5-hypothesis-evaluation | bayesian-hypothesis-network | within-territory: depth? → molecular | strong | trigger phrase |

---

## T6 — Future Exploration

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| consequences and sequel | T6-future-exploration | consequences-and-sequel | — | strong | mode-name reference |
| C&S | T6-future-exploration | consequences-and-sequel | — | strong | mode abbreviation |
| second-order consequences | T6-future-exploration | consequences-and-sequel | — | strong | trigger phrase |
| what would happen if | T6-future-exploration | consequences-and-sequel | — | strong | trigger phrase |
| downstream effects | T6-future-exploration | consequences-and-sequel | — | strong | trigger phrase |
| if we do X then what | T6-future-exploration | consequences-and-sequel | — | strong | trigger phrase |
| cascade forward | T6-future-exploration | consequences-and-sequel | — | strong | trigger phrase |
| what does this lead to | T6-future-exploration | consequences-and-sequel | — | strong | trigger phrase |
| ripple effects | T6-future-exploration | consequences-and-sequel | — | weak | tonal cue (forward cascade) |
| scenario planning | T6-future-exploration | scenario-planning | within-territory: futures? → yes | strong | mode-name reference |
| scenarios | T6-future-exploration | scenario-planning | — | strong | trigger phrase |
| 2x2 scenario matrix | T6-future-exploration | scenario-planning | within-territory: futures? → yes | strong | trigger phrase (scenario_planning subtype) |
| possible futures | T6-future-exploration | scenario-planning | — | strong | trigger phrase |
| what-if matrix | T6-future-exploration | scenario-planning | — | strong | trigger phrase |
| how should we prepare | T6-future-exploration | scenario-planning | — | strong | trigger phrase |
| what could happen | T6-future-exploration | scenario-planning | — | strong | trigger phrase |
| official future | T6-future-exploration | scenario-planning | — | strong | method vocabulary |
| driving forces | T6-future-exploration | scenario-planning | — | strong | method vocabulary |
| STEEP | T6-future-exploration | scenario-planning | — | strong | method abbreviation |
| strategic foresight | T6-future-exploration | scenario-planning | — | weak | tonal cue (multi-future) |
| pre-mortem this plan | T6-future-exploration | pre-mortem-action | within-territory: artifact? → action plan | strong | mode-name reference + disambiguation answer |
| pre-mortem on the plan | T6-future-exploration | pre-mortem-action | within-territory: artifact? → action plan | strong | trigger phrase + disambiguation |
| imagine this failed | T6-future-exploration | pre-mortem-action | — | strong | prospective-hindsight signal |
| Klein pre-mortem | T6-future-exploration | pre-mortem-action | — | strong | method-name + author reference |
| prospective hindsight | T6-future-exploration | pre-mortem-action | — | strong | method vocabulary |
| what would the post-mortem say | T6-future-exploration | pre-mortem-action | — | strong | trigger phrase |
| before we launch | T6-future-exploration | pre-mortem-action | within-territory: artifact? → action plan | strong | trigger phrase |
| before we commit | T6-future-exploration | pre-mortem-action | within-territory: artifact? → action plan | strong | trigger phrase |
| where would I bet this trips | T6-future-exploration | pre-mortem-action | — | weak | tonal cue (failure-anticipation) |
| sober failure walk | T6-future-exploration | pre-mortem-action | — | weak | tonal cue (anti-optimism) |
| probabilistic forecast | T6-future-exploration | probabilistic-forecasting | within-territory: depth? → thorough + output? → probability | strong | mode-name reference |
| probabilistic forecasting | T6-future-exploration | probabilistic-forecasting | within-territory: depth? → thorough + output? → probability | strong | mode-name reference |
| Tetlock | T6-future-exploration | probabilistic-forecasting | — | strong | author/method reference |
| superforecasting | T6-future-exploration | probabilistic-forecasting | — | strong | method-name reference |
| Brier score | T6-future-exploration | probabilistic-forecasting | — | strong | method vocabulary |
| calibration | T6-future-exploration | probabilistic-forecasting | — | strong | method vocabulary |
| calibrated probability | T6-future-exploration | probabilistic-forecasting | — | strong | method vocabulary |
| outside view forecast | T6-future-exploration | probabilistic-forecasting | — | strong | method vocabulary |
| reference class forecast | T6-future-exploration | probabilistic-forecasting | — | strong | method vocabulary |
| reference class | T6-future-exploration | probabilistic-forecasting | — | strong | method vocabulary |
| base rate | T6-future-exploration | probabilistic-forecasting | — | strong | method vocabulary |
| base rate for | T6-future-exploration | probabilistic-forecasting | — | strong | trigger phrase |
| probability of | T6-future-exploration | probabilistic-forecasting | within-territory: output? → probability | strong | trigger phrase |
| what are the odds | T6-future-exploration | probabilistic-forecasting | within-territory: output? → probability | strong | trigger phrase |
| what are the chances | T6-future-exploration | probabilistic-forecasting | within-territory: output? → probability | strong | trigger phrase |
| forecast | T6-future-exploration | probabilistic-forecasting | — | weak | tonal cue (forward) |
| wicked future | T6-future-exploration | wicked-future | within-territory: depth? → molecular | strong | mode-name reference |
| scenario plus pre-mortem plus forecast | T6-future-exploration | wicked-future | within-territory: depth? → molecular | strong | composition reference |
| integrated future analysis | T6-future-exploration | wicked-future | within-territory: depth? → molecular | strong | trigger phrase |
| comprehensive future analysis | T6-future-exploration | wicked-future | within-territory: depth? → molecular | strong | trigger phrase |
| scenario planning with pre-mortem and probabilistic forecast | T6-future-exploration | wicked-future | within-territory: depth? → molecular | strong | composition reference |
| full forward analysis | T6-future-exploration | wicked-future | within-territory: depth? → molecular | strong | trigger phrase |
| many possible futures with failure modes and probabilities | T6-future-exploration | wicked-future | within-territory: depth? → molecular | strong | trigger phrase |
| wicked futures | T6-future-exploration | wicked-future | within-territory: depth? → molecular | strong | mode-name variant |
| deep future analysis | T6-future-exploration | wicked-future | within-territory: depth? → molecular | strong | trigger phrase |
| molecular future exploration | T6-future-exploration | wicked-future | within-territory: depth? → molecular | strong | mode-name + composition |
| three-component future analysis | T6-future-exploration | wicked-future | within-territory: depth? → molecular | strong | composition reference |

---

## T7 — Risk and Failure Analysis

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| pre-mortem this design | T7-risk-and-failure | pre-mortem-fragility | within-territory: artifact? → system or design | strong | mode-name reference + disambiguation answer |
| pre-mortem this system | T7-risk-and-failure | pre-mortem-fragility | within-territory: artifact? → system or design | strong | mode-name reference + disambiguation answer |
| pre-mortem this architecture | T7-risk-and-failure | pre-mortem-fragility | within-territory: artifact? → system or design | strong | trigger phrase |
| structural fragilities | T7-risk-and-failure | pre-mortem-fragility | — | strong | mode vocabulary |
| where will this break | T7-risk-and-failure | pre-mortem-fragility | — | strong | trigger phrase |
| where could this design break | T7-risk-and-failure | pre-mortem-fragility | — | strong | trigger phrase |
| single points of failure | T7-risk-and-failure | pre-mortem-fragility | — | strong | trigger phrase |
| load-bearing | T7-risk-and-failure | pre-mortem-fragility | — | strong | mode vocabulary |
| failure modes does this exhibit | T7-risk-and-failure | pre-mortem-fragility | — | strong | trigger phrase |
| stress-testing this architecture | T7-risk-and-failure | pre-mortem-fragility | — | strong | trigger phrase |
| where would I look for the weak point | T7-risk-and-failure | pre-mortem-fragility | — | weak | tonal cue (fragility-hunting) |
| structural breakage | T7-risk-and-failure | pre-mortem-fragility | — | weak | mode vocabulary |
| fragility audit | T7-risk-and-failure | fragility-antifragility-audit | within-territory: stance? → Talebian | strong | mode-name reference |
| antifragility audit | T7-risk-and-failure | fragility-antifragility-audit | within-territory: stance? → Talebian | strong | mode-name reference |
| fragility antifragility | T7-risk-and-failure | fragility-antifragility-audit | within-territory: stance? → Talebian | strong | mode-name reference |
| Taleb | T7-risk-and-failure | fragility-antifragility-audit | within-territory: stance? → Talebian | strong | author reference |
| antifragile | T7-risk-and-failure | fragility-antifragility-audit | within-territory: stance? → Talebian | strong | mode vocabulary |
| antifragility | T7-risk-and-failure | fragility-antifragility-audit | within-territory: stance? → Talebian | strong | mode vocabulary |
| fragility | T7-risk-and-failure | fragility-antifragility-audit | within-territory: stance? → Talebian | strong | mode vocabulary |
| convex response | T7-risk-and-failure | fragility-antifragility-audit | — | strong | method vocabulary |
| concave exposure | T7-risk-and-failure | fragility-antifragility-audit | — | strong | method vocabulary |
| via negativa | T7-risk-and-failure | fragility-antifragility-audit | — | strong | method-name reference |
| barbell strategy | T7-risk-and-failure | fragility-antifragility-audit | — | strong | method-name reference |
| Black Swan | T7-risk-and-failure | fragility-antifragility-audit | — | strong | author/method reference |
| tail risk | T7-risk-and-failure | fragility-antifragility-audit | — | strong | method vocabulary |
| asymmetric payoff | T7-risk-and-failure | fragility-antifragility-audit | — | strong | method vocabulary |
| Lindy effect | T7-risk-and-failure | fragility-antifragility-audit | — | strong | method-name reference |
| skin in the game | T7-risk-and-failure | fragility-antifragility-audit | — | weak | tonal cue (Talebian) |

---

## T8 — Stakeholder Conflict

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| stakeholder map | T8-stakeholder-conflict | stakeholder-mapping | — | strong | mode-name reference |
| stakeholder mapping | T8-stakeholder-conflict | stakeholder-mapping | — | strong | mode-name reference |
| stakeholder analysis | T8-stakeholder-conflict | stakeholder-mapping | — | strong | mode-name variant |
| Bryson power-interest grid | T8-stakeholder-conflict | stakeholder-mapping | — | strong | method-name reference |
| Mitchell Agle Wood | T8-stakeholder-conflict | stakeholder-mapping | — | strong | method-name reference |
| Mitchell-Agle-Wood salience | T8-stakeholder-conflict | stakeholder-mapping | — | strong | method-name reference |
| salience | T8-stakeholder-conflict | stakeholder-mapping | — | strong | mode vocabulary |
| who needs to be at the table | T8-stakeholder-conflict | stakeholder-mapping | — | strong | trigger phrase |
| RACI | T8-stakeholder-conflict | stakeholder-mapping | — | strong | method abbreviation |
| who has standing | T8-stakeholder-conflict | stakeholder-mapping | — | strong | trigger phrase |
| who's involved here | T8-stakeholder-conflict | stakeholder-mapping | — | strong | trigger phrase |
| multiple parties with different stakes | T8-stakeholder-conflict | stakeholder-mapping | — | strong | trigger phrase |
| we keep getting blindsided | T8-stakeholder-conflict | stakeholder-mapping | — | weak | tonal cue (missed-stakeholder pattern) |
| absent or marginalized | T8-stakeholder-conflict | stakeholder-mapping | — | weak | mode vocabulary |
| power-interest | T8-stakeholder-conflict | stakeholder-mapping | — | strong | method abbreviation |

---

## T9 — Paradigm and Assumption Examination

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| paradigm suspension | T9-paradigm-and-assumption | paradigm-suspension | — | strong | mode-name reference |
| suspend the paradigm | T9-paradigm-and-assumption | paradigm-suspension | — | strong | trigger phrase |
| question the frame | T9-paradigm-and-assumption | paradigm-suspension | — | strong | trigger phrase |
| what if the consensus is wrong | T9-paradigm-and-assumption | paradigm-suspension | — | strong | trigger phrase |
| what if X is wrong | T9-paradigm-and-assumption | paradigm-suspension | — | strong | trigger phrase |
| heterodox | T9-paradigm-and-assumption | paradigm-suspension | — | strong | mode vocabulary |
| Kuhnian | T9-paradigm-and-assumption | paradigm-suspension | — | strong | framework reference |
| Lakatosian | T9-paradigm-and-assumption | paradigm-suspension | — | strong | framework reference |
| foundational assumption | T9-paradigm-and-assumption | paradigm-suspension | — | strong | mode vocabulary |
| Einstein guard rail | T9-paradigm-and-assumption | paradigm-suspension | — | weak | mode-internal vocabulary |
| consensus is data | T9-paradigm-and-assumption | paradigm-suspension | — | weak | tonal cue (consensus-as-evidence) |
| frame comparison | T9-paradigm-and-assumption | frame-comparison | within-territory: stance? → comparing | strong | mode-name reference |
| compare frames | T9-paradigm-and-assumption | frame-comparison | within-territory: stance? → comparing | strong | trigger phrase |
| compare the framings | T9-paradigm-and-assumption | frame-comparison | within-territory: stance? → comparing | strong | trigger phrase |
| different framings | T9-paradigm-and-assumption | frame-comparison | within-territory: stance? → comparing | strong | trigger phrase |
| Lakoff strict-father vs nurturant-parent | T9-paradigm-and-assumption | frame-comparison | within-territory: stance? → comparing | strong | method-name reference |
| strict father vs nurturant parent | T9-paradigm-and-assumption | frame-comparison | within-territory: stance? → comparing | strong | trigger phrase |
| two ways of seeing | T9-paradigm-and-assumption | frame-comparison | within-territory: stance? → comparing | strong | trigger phrase |
| alternative frames | T9-paradigm-and-assumption | frame-comparison | within-territory: stance? → comparing | strong | trigger phrase |
| competing frames | T9-paradigm-and-assumption | frame-comparison | within-territory: stance? → comparing | strong | trigger phrase |
| how each side sees | T9-paradigm-and-assumption | frame-comparison | — | strong | trigger phrase |
| two camps | T9-paradigm-and-assumption | frame-comparison | — | strong | trigger phrase |
| talking past each other | T9-paradigm-and-assumption | frame-comparison | — | weak | tonal cue (frame-clash) |
| conceptual metaphor | T9-paradigm-and-assumption | frame-comparison | — | strong | method vocabulary |
| worldview cartography | T9-paradigm-and-assumption | worldview-cartography | within-territory: depth? → molecular | strong | mode-name reference |
| multi-paradigm map | T9-paradigm-and-assumption | worldview-cartography | within-territory: depth? → molecular | strong | trigger phrase |
| compare worldviews and synthesize | T9-paradigm-and-assumption | worldview-cartography | within-territory: depth? → molecular | strong | trigger phrase |
| paradigm suspension plus frame comparison plus dialectical | T9-paradigm-and-assumption | worldview-cartography | within-territory: depth? → molecular | strong | composition reference |
| cartography of worldviews | T9-paradigm-and-assumption | worldview-cartography | within-territory: depth? → molecular | strong | trigger phrase |
| comprehensive worldview analysis | T9-paradigm-and-assumption | worldview-cartography | within-territory: depth? → molecular | strong | trigger phrase |
| map multiple paradigms | T9-paradigm-and-assumption | worldview-cartography | within-territory: depth? → molecular | strong | trigger phrase |
| three or more worldviews compared | T9-paradigm-and-assumption | worldview-cartography | within-territory: depth? → molecular | strong | trigger phrase |
| paradigm comparison with synthesis | T9-paradigm-and-assumption | worldview-cartography | within-territory: depth? → molecular | strong | composition reference |
| dialectical comparison of paradigms | T9-paradigm-and-assumption | worldview-cartography | within-territory: depth? → molecular | strong | composition reference |
| how do these worldviews relate | T9-paradigm-and-assumption | worldview-cartography | within-territory: depth? → molecular | strong | trigger phrase |
| antinomies between paradigms | T9-paradigm-and-assumption | worldview-cartography | within-territory: depth? → molecular | strong | mode vocabulary |
| productive tension among worldviews | T9-paradigm-and-assumption | worldview-cartography | within-territory: depth? → molecular | strong | mode vocabulary |

---

## T10 — Conceptual Clarification

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| deep clarification | T10-conceptual-clarification | deep-clarification | — | strong | mode-name reference |
| deeper | T10-conceptual-clarification | deep-clarification | — | strong | trigger phrase |
| mechanism | T10-conceptual-clarification | deep-clarification | — | strong | trigger phrase |
| how does it actually work | T10-conceptual-clarification | deep-clarification | — | strong | trigger phrase |
| explain the physics | T10-conceptual-clarification | deep-clarification | — | strong | trigger phrase |
| explain the math | T10-conceptual-clarification | deep-clarification | — | strong | trigger phrase |
| explain the internals | T10-conceptual-clarification | deep-clarification | — | strong | trigger phrase |
| why does X work that way | T10-conceptual-clarification | deep-clarification | — | strong | trigger phrase |
| what's really going on underneath | T10-conceptual-clarification | deep-clarification | — | strong | trigger phrase |
| underlying principle | T10-conceptual-clarification | deep-clarification | — | weak | tonal cue (depth) |
| conceptual engineering | T10-conceptual-clarification | conceptual-engineering | within-territory: stance? → ameliorative | strong | mode-name reference |
| Cappelen | T10-conceptual-clarification | conceptual-engineering | within-territory: stance? → ameliorative | strong | author reference |
| Cappelen-Plunkett | T10-conceptual-clarification | conceptual-engineering | within-territory: stance? → ameliorative | strong | author reference |
| ameliorative | T10-conceptual-clarification | conceptual-engineering | within-territory: stance? → ameliorative | strong | mode vocabulary |
| ameliorative analysis | T10-conceptual-clarification | conceptual-engineering | within-territory: stance? → ameliorative | strong | method-name reference |
| Haslanger | T10-conceptual-clarification | conceptual-engineering | within-territory: stance? → ameliorative | strong | author reference |
| redefine the concept | T10-conceptual-clarification | conceptual-engineering | within-territory: stance? → ameliorative | strong | trigger phrase |
| engineer the concept | T10-conceptual-clarification | conceptual-engineering | within-territory: stance? → ameliorative | strong | trigger phrase |
| redefine | T10-conceptual-clarification | conceptual-engineering | — | strong | trigger phrase |
| should the concept be | T10-conceptual-clarification | conceptual-engineering | within-territory: stance? → ameliorative | strong | trigger phrase |
| what should X mean | T10-conceptual-clarification | conceptual-engineering | within-territory: stance? → ameliorative | strong | trigger phrase |
| the function the concept should serve | T10-conceptual-clarification | conceptual-engineering | — | strong | trigger phrase |
| normative purpose | T10-conceptual-clarification | conceptual-engineering | — | weak | tonal cue (ameliorative) |

---

## T11 — Structural Relationship Mapping

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| relationship mapping | T11-structural-relationship-mapping | relationship-mapping | within-territory: visual-input? → no | strong | mode-name reference |
| relationship map | T11-structural-relationship-mapping | relationship-mapping | within-territory: visual-input? → no | strong | trigger phrase |
| causal DAG | T11-structural-relationship-mapping | relationship-mapping | within-territory: visual-input? → no | strong | trigger phrase |
| dependency graph | T11-structural-relationship-mapping | relationship-mapping | within-territory: visual-input? → no | strong | trigger phrase |
| what affects what | T11-structural-relationship-mapping | relationship-mapping | within-territory: visual-input? → no | strong | trigger phrase |
| draw the connections | T11-structural-relationship-mapping | relationship-mapping | within-territory: visual-input? → no | strong | trigger phrase |
| how do these connect | T11-structural-relationship-mapping | relationship-mapping | within-territory: visual-input? → no | strong | trigger phrase |
| spatial reasoning | T11-structural-relationship-mapping | spatial-reasoning | within-territory: visual-input? → yes | strong | mode-name reference |
| what do you see | T11-structural-relationship-mapping | spatial-reasoning | within-territory: visual-input? → yes | strong | trigger phrase (with diagram input) |
| what's missing | T11-structural-relationship-mapping | spatial-reasoning | within-territory: visual-input? → yes | strong | trigger phrase (with diagram input) |
| what am I missing in this diagram | T11-structural-relationship-mapping | spatial-reasoning | within-territory: visual-input? → yes | strong | trigger phrase |
| help me see what I'm not seeing | T11-structural-relationship-mapping | spatial-reasoning | within-territory: visual-input? → yes | strong | trigger phrase |
| can you annotate this | T11-structural-relationship-mapping | spatial-reasoning | within-territory: visual-input? → yes | strong | trigger phrase |
| annotate this causal structure | T11-structural-relationship-mapping | spatial-reasoning | within-territory: visual-input? → yes | strong | trigger phrase |
| mark up this diagram | T11-structural-relationship-mapping | spatial-reasoning | within-territory: visual-input? → yes | strong | trigger phrase |
| what node am I missing | T11-structural-relationship-mapping | spatial-reasoning | within-territory: visual-input? → yes | strong | trigger phrase |
| is there a feedback loop I haven't drawn | T11-structural-relationship-mapping | spatial-reasoning | within-territory: visual-input? → yes | strong | trigger phrase |
| what relationships are implied but not shown | T11-structural-relationship-mapping | spatial-reasoning | within-territory: visual-input? → yes | strong | trigger phrase |
| Tversky | T11-structural-relationship-mapping | spatial-reasoning | within-territory: visual-input? → yes | weak | framework reference |

---

## T12 — Cross-Domain and Knowledge Synthesis

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| synthesis | T12-cross-domain-synthesis | synthesis | within-territory: stance? → integrative | strong | mode-name reference |
| synthesise | T12-cross-domain-synthesis | synthesis | within-territory: stance? → integrative | strong | trigger phrase |
| synthesize | T12-cross-domain-synthesis | synthesis | within-territory: stance? → integrative | strong | trigger phrase (US spelling) |
| connect these frameworks | T12-cross-domain-synthesis | synthesis | within-territory: stance? → integrative | strong | trigger phrase |
| structural parallel | T12-cross-domain-synthesis | synthesis | within-territory: stance? → integrative | strong | trigger phrase |
| map the intersection | T12-cross-domain-synthesis | synthesis | within-territory: stance? → integrative | strong | trigger phrase |
| how does X relate to Y | T12-cross-domain-synthesis | synthesis | within-territory: stance? → integrative | strong | trigger phrase |
| isomorphism | T12-cross-domain-synthesis | synthesis | within-territory: stance? → integrative | weak | mode vocabulary |
| productive tension | T12-cross-domain-synthesis | synthesis | within-territory: stance? → integrative | weak | mode vocabulary |
| cross-domain | T12-cross-domain-synthesis | synthesis | within-territory: stance? → integrative | weak | tonal cue (synthesis) |
| dialectical analysis | T12-cross-domain-synthesis | dialectical-analysis | within-territory: stance? → thesis-antithesis | strong | mode-name reference |
| thesis antithesis | T12-cross-domain-synthesis | dialectical-analysis | within-territory: stance? → thesis-antithesis | strong | trigger phrase |
| sublate | T12-cross-domain-synthesis | dialectical-analysis | within-territory: stance? → thesis-antithesis | strong | trigger phrase |
| Aufheben | T12-cross-domain-synthesis | dialectical-analysis | within-territory: stance? → thesis-antithesis | strong | mode vocabulary |
| drive through the contradiction | T12-cross-domain-synthesis | dialectical-analysis | within-territory: stance? → thesis-antithesis | strong | trigger phrase |
| Hegelian | T12-cross-domain-synthesis | dialectical-analysis | within-territory: stance? → thesis-antithesis | strong | framework reference |
| Adornian | T12-cross-domain-synthesis | dialectical-analysis | within-territory: stance? → thesis-antithesis | strong | framework reference |
| irreducible contradiction | T12-cross-domain-synthesis | dialectical-analysis | within-territory: stance? → thesis-antithesis | strong | mode vocabulary |
| genuine opposition | T12-cross-domain-synthesis | dialectical-analysis | within-territory: stance? → thesis-antithesis | weak | tonal cue (dialectic) |

---

## T13 — Negotiation and Conflict Resolution

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| interest mapping | T13-negotiation-and-conflict-resolution | interest-mapping | within-territory: depth? → light | strong | mode-name reference |
| Fisher Ury | T13-negotiation-and-conflict-resolution | interest-mapping | — | strong | author reference |
| Fisher-Ury | T13-negotiation-and-conflict-resolution | interest-mapping | — | strong | author reference |
| interests not positions | T13-negotiation-and-conflict-resolution | interest-mapping | — | strong | trigger phrase |
| interests vs positions | T13-negotiation-and-conflict-resolution | interest-mapping | — | strong | trigger phrase |
| underlying interests | T13-negotiation-and-conflict-resolution | interest-mapping | — | strong | mode vocabulary |
| negotiation interests | T13-negotiation-and-conflict-resolution | interest-mapping | — | strong | trigger phrase |
| BATNA mapping | T13-negotiation-and-conflict-resolution | interest-mapping | — | strong | method vocabulary |
| BATNA | T13-negotiation-and-conflict-resolution | interest-mapping | — | strong | method abbreviation |
| principled negotiation light | T13-negotiation-and-conflict-resolution | interest-mapping | within-territory: depth? → light | strong | trigger phrase |
| what does each side really want | T13-negotiation-and-conflict-resolution | interest-mapping | — | strong | trigger phrase |
| going into a negotiation | T13-negotiation-and-conflict-resolution | interest-mapping | — | weak | tonal cue (active-negotiation) |
| they're saying X but mean Y | T13-negotiation-and-conflict-resolution | interest-mapping | — | weak | tonal cue (position-vs-interest) |
| principled negotiation | T13-negotiation-and-conflict-resolution | principled-negotiation | within-territory: depth? → thorough | strong | mode-name reference |
| Fisher Ury full | T13-negotiation-and-conflict-resolution | principled-negotiation | within-territory: depth? → thorough | strong | trigger phrase (full method) |
| Getting to Yes | T13-negotiation-and-conflict-resolution | principled-negotiation | — | strong | book reference |
| BATNA | T13-negotiation-and-conflict-resolution | principled-negotiation | within-territory: depth? → thorough | strong | method abbreviation |
| best alternative to negotiated agreement | T13-negotiation-and-conflict-resolution | principled-negotiation | — | strong | method-name reference |
| options for mutual gain | T13-negotiation-and-conflict-resolution | principled-negotiation | — | strong | method vocabulary |
| objective criteria | T13-negotiation-and-conflict-resolution | principled-negotiation | — | strong | method vocabulary |
| separate the people from the problem | T13-negotiation-and-conflict-resolution | principled-negotiation | — | strong | method vocabulary |
| ZOPA | T13-negotiation-and-conflict-resolution | principled-negotiation | — | strong | method abbreviation |
| reservation price | T13-negotiation-and-conflict-resolution | principled-negotiation | — | strong | method vocabulary |
| full negotiation analysis | T13-negotiation-and-conflict-resolution | principled-negotiation | within-territory: depth? → thorough | strong | trigger phrase |
| negotiation prep | T13-negotiation-and-conflict-resolution | principled-negotiation | — | strong | trigger phrase |
| third side | T13-negotiation-and-conflict-resolution | third-side | within-territory: stance? → mediator | strong | mode-name reference |
| third-side | T13-negotiation-and-conflict-resolution | third-side | within-territory: stance? → mediator | strong | mode-name reference |
| Ury third side | T13-negotiation-and-conflict-resolution | third-side | within-territory: stance? → mediator | strong | author + method reference |
| mediator | T13-negotiation-and-conflict-resolution | third-side | within-territory: stance? → mediator | strong | role reference |
| mediator perspective | T13-negotiation-and-conflict-resolution | third-side | within-territory: stance? → mediator | strong | trigger phrase |
| third-side mediation | T13-negotiation-and-conflict-resolution | third-side | within-territory: stance? → mediator | strong | mode vocabulary |
| ten roles of conflict resolution | T13-negotiation-and-conflict-resolution | third-side | — | strong | method-name reference |
| ten roles | T13-negotiation-and-conflict-resolution | third-side | — | strong | method vocabulary |
| facilitating a conflict | T13-negotiation-and-conflict-resolution | third-side | — | strong | trigger phrase |
| containing a conflict | T13-negotiation-and-conflict-resolution | third-side | — | strong | trigger phrase |
| ombuds | T13-negotiation-and-conflict-resolution | third-side | — | strong | role reference |
| the community's role | T13-negotiation-and-conflict-resolution | third-side | — | weak | tonal cue (third-side framing) |

---

## T14 — Orientation in Unfamiliar Territory

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| quick orientation | T14-orientation-in-unfamiliar-territory | quick-orientation | within-territory: depth? → light | strong | mode-name reference |
| quick overview | T14-orientation-in-unfamiliar-territory | quick-orientation | within-territory: depth? → light | strong | trigger phrase |
| quick lay of the land | T14-orientation-in-unfamiliar-territory | quick-orientation | within-territory: depth? → light | strong | trigger phrase |
| give me the gist | T14-orientation-in-unfamiliar-territory | quick-orientation | within-territory: depth? → light | strong | trigger phrase |
| high-level intro to | T14-orientation-in-unfamiliar-territory | quick-orientation | within-territory: depth? → light | strong | trigger phrase |
| dropping into this domain cold | T14-orientation-in-unfamiliar-territory | quick-orientation | within-territory: depth? → light | strong | trigger phrase |
| what do I need to know | T14-orientation-in-unfamiliar-territory | quick-orientation | within-territory: depth? → light | strong | trigger phrase |
| where do I start with this | T14-orientation-in-unfamiliar-territory | quick-orientation | within-territory: depth? → light | strong | trigger phrase |
| I have ten minutes | T14-orientation-in-unfamiliar-territory | quick-orientation | within-territory: depth? → light | weak | tonal cue (time pressure → light variant) |
| main bits to be aware of | T14-orientation-in-unfamiliar-territory | quick-orientation | — | weak | tonal cue (orientation request) |
| what's this about | T14-orientation-in-unfamiliar-territory | quick-orientation | within-territory: depth? → light | weak | tonal cue (light-orientation) |
| terrain mapping | T14-orientation-in-unfamiliar-territory | terrain-mapping | within-territory: depth? → thorough | strong | mode-name reference |
| map this domain | T14-orientation-in-unfamiliar-territory | terrain-mapping | within-territory: depth? → thorough | strong | trigger phrase (positive list) |
| concept map of | T14-orientation-in-unfamiliar-territory | terrain-mapping | within-territory: depth? → thorough | strong | trigger phrase |
| lay of the land | T14-orientation-in-unfamiliar-territory | terrain-mapping | within-territory: depth? → thorough | strong | trigger phrase |
| walk me through | T14-orientation-in-unfamiliar-territory | terrain-mapping | within-territory: depth? → thorough | strong | trigger phrase |
| big picture | T14-orientation-in-unfamiliar-territory | terrain-mapping | within-territory: depth? → thorough | strong | trigger phrase |
| where do I start | T14-orientation-in-unfamiliar-territory | terrain-mapping | within-territory: depth? → thorough | strong | trigger phrase |
| what do I need to know about | T14-orientation-in-unfamiliar-territory | terrain-mapping | within-territory: depth? → thorough | strong | trigger phrase |
| orient me | T14-orientation-in-unfamiliar-territory | terrain-mapping | — | weak | tonal cue (orientation) |
| unfamiliar with | T14-orientation-in-unfamiliar-territory | terrain-mapping | — | weak | tonal cue (admission of unfamiliarity) |
| landscape of | T14-orientation-in-unfamiliar-territory | terrain-mapping | — | weak | tonal cue (cartographic frame) |
| introduction to | T14-orientation-in-unfamiliar-territory | terrain-mapping | — | weak | tonal cue (orientation) |
| domain induction | T14-orientation-in-unfamiliar-territory | domain-induction | within-territory: depth? → molecular | strong | mode-name reference |
| orient and learn | T14-orientation-in-unfamiliar-territory | domain-induction | within-territory: depth? → molecular | strong | trigger phrase |
| structured introduction to a domain | T14-orientation-in-unfamiliar-territory | domain-induction | within-territory: depth? → molecular | strong | trigger phrase |
| structured introduction to | T14-orientation-in-unfamiliar-territory | domain-induction | within-territory: depth? → molecular | strong | trigger phrase |
| comprehensive domain introduction | T14-orientation-in-unfamiliar-territory | domain-induction | within-territory: depth? → molecular | strong | trigger phrase |
| structured learning pathway | T14-orientation-in-unfamiliar-territory | domain-induction | within-territory: depth? → molecular | strong | trigger phrase |
| induct me into this domain | T14-orientation-in-unfamiliar-territory | domain-induction | within-territory: depth? → molecular | strong | trigger phrase |
| orient me and chart the terrain and give me a learning path | T14-orientation-in-unfamiliar-territory | domain-induction | within-territory: depth? → molecular | strong | composition reference |
| quick-orient plus terrain-map plus structured-induction | T14-orientation-in-unfamiliar-territory | domain-induction | within-territory: depth? → molecular | strong | composition reference |
| comprehensive orientation in new domain | T14-orientation-in-unfamiliar-territory | domain-induction | within-territory: depth? → molecular | strong | trigger phrase |
| help me become functionally literate in | T14-orientation-in-unfamiliar-territory | domain-induction | within-territory: depth? → molecular | strong | trigger phrase |
| ordered learning pathway with prerequisites | T14-orientation-in-unfamiliar-territory | domain-induction | within-territory: depth? → molecular | strong | mode vocabulary |
| deep induction into | T14-orientation-in-unfamiliar-territory | domain-induction | within-territory: depth? → molecular | weak | tonal cue (depth-molecular) |

---

## T15 — Artifact Evaluation by Stance

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| steelman | T15-artifact-evaluation-by-stance | steelman-construction | within-territory: stance? → constructive-strong | strong | mode-name reference |
| best case for | T15-artifact-evaluation-by-stance | steelman-construction | within-territory: stance? → constructive-strong | strong | trigger phrase |
| strongest version of | T15-artifact-evaluation-by-stance | steelman-construction | within-territory: stance? → constructive-strong | strong | trigger phrase |
| play devil's advocate | T15-artifact-evaluation-by-stance | steelman-construction | within-territory: stance? → constructive-strong | strong | trigger phrase |
| strongest version of the other side | T15-artifact-evaluation-by-stance | steelman-construction | within-territory: stance? → constructive-strong | strong | trigger phrase |
| mirror test | T15-artifact-evaluation-by-stance | steelman-construction | within-territory: stance? → constructive-strong | strong | mode-internal vocabulary |
| charitable reading | T15-artifact-evaluation-by-stance | steelman-construction | within-territory: stance? → constructive-strong | weak | tonal cue (charity) |
| build up | T15-artifact-evaluation-by-stance | steelman-construction | within-territory: stance? → constructive-strong | weak | tonal cue (construction) |
| benefits analysis | T15-artifact-evaluation-by-stance | benefits-analysis | within-territory: stance? → constructive-balanced | strong | mode-name reference |
| PMI | T15-artifact-evaluation-by-stance | benefits-analysis | within-territory: stance? → constructive-balanced | strong | method abbreviation |
| plus minus interesting | T15-artifact-evaluation-by-stance | benefits-analysis | within-territory: stance? → constructive-balanced | strong | trigger phrase |
| pros and cons of | T15-artifact-evaluation-by-stance | benefits-analysis | within-territory: stance? → constructive-balanced | strong | trigger phrase |
| what are the benefits and risks | T15-artifact-evaluation-by-stance | benefits-analysis | within-territory: stance? → constructive-balanced | strong | trigger phrase |
| evaluate this proposal | T15-artifact-evaluation-by-stance | benefits-analysis | within-territory: stance? → constructive-balanced | strong | trigger phrase |
| cost-benefit analysis | T15-artifact-evaluation-by-stance | benefits-analysis | within-territory: stance? → constructive-balanced | strong | method reference |
| full picture on X | T15-artifact-evaluation-by-stance | benefits-analysis | within-territory: stance? → constructive-balanced | strong | trigger phrase |
| envelope of | T15-artifact-evaluation-by-stance | benefits-analysis | within-territory: stance? → constructive-balanced | weak | tonal cue (envelope framing) |
| balanced critique | T15-artifact-evaluation-by-stance | balanced-critique | within-territory: stance? → neutral | strong | mode-name reference |
| balanced assessment | T15-artifact-evaluation-by-stance | balanced-critique | within-territory: stance? → neutral | strong | trigger phrase |
| balanced evaluation | T15-artifact-evaluation-by-stance | balanced-critique | within-territory: stance? → neutral | strong | trigger phrase |
| fair evaluation | T15-artifact-evaluation-by-stance | balanced-critique | within-territory: stance? → neutral | strong | trigger phrase |
| balanced read | T15-artifact-evaluation-by-stance | balanced-critique | within-territory: stance? → neutral | strong | trigger phrase |
| neutral read | T15-artifact-evaluation-by-stance | balanced-critique | within-territory: stance? → neutral | strong | trigger phrase |
| neutral assessment | T15-artifact-evaluation-by-stance | balanced-critique | within-territory: stance? → neutral | strong | trigger phrase |
| strengths and weaknesses | T15-artifact-evaluation-by-stance | balanced-critique | within-territory: stance? → neutral | strong | trigger phrase |
| what holds up and what doesn't | T15-artifact-evaluation-by-stance | balanced-critique | within-territory: stance? → neutral | strong | trigger phrase |
| not a steelman or a teardown | T15-artifact-evaluation-by-stance | balanced-critique | within-territory: stance? → neutral | strong | trigger phrase (negative selector ruling out advocacy and teardown) |
| both sides | T15-artifact-evaluation-by-stance | balanced-critique | within-territory: stance? → neutral | weak | tonal cue (symmetric evaluation) |
| weigh this fairly | T15-artifact-evaluation-by-stance | balanced-critique | within-territory: stance? → neutral | weak | tonal cue (neutrality) |
| red team | T15-artifact-evaluation-by-stance | red-team-assessment | within-territory: stance? → adversarial-actor-modeling, operation? → assessment (default) | strong | mode-name reference (parent term; resolves to assessment when ambiguous) |
| red-team assessment | T15-artifact-evaluation-by-stance | red-team-assessment | within-territory: stance? → adversarial-actor-modeling-assessment | strong | mode-name reference |
| stress-test this | T15-artifact-evaluation-by-stance | red-team-assessment | within-territory: stance? → adversarial-actor-modeling-assessment | strong | trigger phrase (assessment-signal) |
| attack this | T15-artifact-evaluation-by-stance | red-team-assessment | within-territory: stance? → adversarial-actor-modeling-assessment | strong | trigger phrase (assessment-signal) |
| pick this apart | T15-artifact-evaluation-by-stance | red-team-assessment | within-territory: stance? → adversarial-actor-modeling-assessment | strong | trigger phrase (assessment-signal) |
| try to break this | T15-artifact-evaluation-by-stance | red-team-assessment | within-territory: stance? → adversarial-actor-modeling-assessment | strong | trigger phrase (assessment-signal) |
| poke holes | T15-artifact-evaluation-by-stance | red-team-assessment | within-territory: stance? → adversarial-actor-modeling-assessment | strong | trigger phrase (assessment-signal) |
| find the holes | T15-artifact-evaluation-by-stance | red-team-assessment | within-territory: stance? → adversarial-actor-modeling-assessment | strong | trigger phrase (assessment-signal) |
| pre-mortem | T15-artifact-evaluation-by-stance | red-team-assessment | within-territory: stance? → adversarial-actor-modeling-assessment | weak | trigger phrase (also fires T6/T7 pre-mortem parses; weak in T15) |
| what am I missing | T15-artifact-evaluation-by-stance | red-team-assessment | within-territory: stance? → adversarial-actor-modeling-assessment | strong | trigger phrase (assessment-signal) |
| where is this weak | T15-artifact-evaluation-by-stance | red-team-assessment | within-territory: stance? → adversarial-actor-modeling-assessment | strong | trigger phrase (assessment-signal) |
| how could this fail | T15-artifact-evaluation-by-stance | red-team-assessment | within-territory: stance? → adversarial-actor-modeling-assessment | strong | trigger phrase (assessment-signal) |
| before I ship | T15-artifact-evaluation-by-stance | red-team-assessment | within-territory: stance? → adversarial-actor-modeling-assessment | strong | trigger phrase (assessment-signal) |
| before I ship this | T15-artifact-evaluation-by-stance | red-team-assessment | within-territory: stance? → adversarial-actor-modeling-assessment | strong | trigger phrase (assessment-signal) |
| before I commit | T15-artifact-evaluation-by-stance | red-team-assessment | within-territory: stance? → adversarial-actor-modeling-assessment | strong | trigger phrase (assessment-signal) |
| red-team advocate | T15-artifact-evaluation-by-stance | red-team-advocate | within-territory: stance? → adversarial-actor-modeling-advocate | strong | mode-name reference |
| argue against this | T15-artifact-evaluation-by-stance | red-team-advocate | within-territory: stance? → adversarial-actor-modeling-advocate | strong | trigger phrase (advocate-signal) |
| make the case against | T15-artifact-evaluation-by-stance | red-team-advocate | within-territory: stance? → adversarial-actor-modeling-advocate | strong | trigger phrase (advocate-signal) |
| give me ammunition | T15-artifact-evaluation-by-stance | red-team-advocate | within-territory: stance? → adversarial-actor-modeling-advocate | strong | trigger phrase (advocate-signal) |
| I need to dissuade | T15-artifact-evaluation-by-stance | red-team-advocate | within-territory: stance? → adversarial-actor-modeling-advocate | strong | trigger phrase (advocate-signal) |
| talk them out of it | T15-artifact-evaluation-by-stance | red-team-advocate | within-territory: stance? → adversarial-actor-modeling-advocate | strong | trigger phrase (advocate-signal) |
| prep me for debate | T15-artifact-evaluation-by-stance | red-team-advocate | within-territory: stance? → adversarial-actor-modeling-advocate | strong | trigger phrase (advocate-signal) |
| prep me for hostile review | T15-artifact-evaluation-by-stance | red-team-advocate | within-territory: stance? → adversarial-actor-modeling-advocate | strong | trigger phrase (advocate-signal) |
| every angle including weak ones | T15-artifact-evaluation-by-stance | red-team-advocate | within-territory: stance? → adversarial-actor-modeling-advocate | strong | trigger phrase (advocate-signal; comprehensive critique) |
| comprehensive critique | T15-artifact-evaluation-by-stance | red-team-advocate | within-territory: stance? → adversarial-actor-modeling-advocate | strong | trigger phrase (advocate-signal) |
| no triage | T15-artifact-evaluation-by-stance | red-team-advocate | within-territory: stance? → adversarial-actor-modeling-advocate | weak | trigger phrase (advocate-signal; tonal cue) |

---

## T16 — Mechanism Understanding

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| mechanism understanding | T16-mechanism-understanding | mechanism-understanding | — | strong | mode-name reference |
| mechanism | T16-mechanism-understanding | mechanism-understanding | — | strong | mode-name shorthand |
| how does this work | T16-mechanism-understanding | mechanism-understanding | — | strong | trigger phrase |
| how do the parts produce | T16-mechanism-understanding | mechanism-understanding | — | strong | trigger phrase |
| mechanistic explanation | T16-mechanism-understanding | mechanism-understanding | — | strong | trigger phrase |
| under the hood | T16-mechanism-understanding | mechanism-understanding | — | strong | trigger phrase |
| explain the gears | T16-mechanism-understanding | mechanism-understanding | — | strong | trigger phrase |
| structural explanation | T16-mechanism-understanding | mechanism-understanding | — | strong | trigger phrase |
| internal workings | T16-mechanism-understanding | mechanism-understanding | — | strong | trigger phrase |
| principle-level | T16-mechanism-understanding | mechanism-understanding | — | strong | mode vocabulary |
| components and interactions | T16-mechanism-understanding | mechanism-understanding | — | strong | mode vocabulary |
| what makes this happen | T16-mechanism-understanding | mechanism-understanding | — | weak | tonal cue (mechanism framing) |

---

## T17 — Process and System Analysis

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| systems dynamics | T17-process-and-system | systems-dynamics-structural | within-territory: feedback? → yes | strong | mode-name reference |
| CLD | T17-process-and-system | systems-dynamics-structural | within-territory: feedback? → yes | strong | abbreviation (causal loop diagram) |
| stock and flow | T17-process-and-system | systems-dynamics-structural | within-territory: feedback? → yes | strong | trigger phrase |
| Meadows leverage points | T17-process-and-system | systems-dynamics-structural | within-territory: feedback? → yes | strong | framework reference |
| reinforcing loop | T17-process-and-system | systems-dynamics-structural | within-territory: feedback? → yes | strong | mode vocabulary |
| balancing loop | T17-process-and-system | systems-dynamics-structural | within-territory: feedback? → yes | strong | mode vocabulary |
| Senge archetype | T17-process-and-system | systems-dynamics-structural | within-territory: feedback? → yes | strong | framework reference |
| draw the feedback structure | T17-process-and-system | systems-dynamics-structural | within-territory: feedback? → yes | strong | trigger phrase |
| process map | T17-process-and-system | process-mapping | within-territory: specificity? → process-flow | strong | mode-name reference |
| process mapping | T17-process-and-system | process-mapping | within-territory: specificity? → process-flow | strong | mode-name reference |
| workflow map | T17-process-and-system | process-mapping | within-territory: specificity? → process-flow | strong | trigger phrase |
| workflow analysis | T17-process-and-system | process-mapping | within-territory: specificity? → process-flow | strong | trigger phrase |
| value stream map | T17-process-and-system | process-mapping | within-territory: specificity? → process-flow | strong | method-name reference |
| swimlane diagram | T17-process-and-system | process-mapping | within-territory: specificity? → process-flow | strong | method-name reference |
| swim lane | T17-process-and-system | process-mapping | within-territory: specificity? → process-flow | strong | method-name reference |
| bottleneck identification | T17-process-and-system | process-mapping | — | strong | trigger phrase |
| bottleneck | T17-process-and-system | process-mapping | — | strong | mode vocabulary |
| as-is process | T17-process-and-system | process-mapping | within-territory: specificity? → process-flow | strong | method vocabulary |
| current state | T17-process-and-system | process-mapping | — | strong | trigger phrase |
| flow chart | T17-process-and-system | process-mapping | — | strong | trigger phrase |
| dependency map | T17-process-and-system | process-mapping | — | strong | trigger phrase |
| step by step how does this work | T17-process-and-system | process-mapping | — | strong | trigger phrase |

---

## T18 — Strategic Interaction

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| strategic interaction | T18-strategic-interaction | strategic-interaction | — | strong | mode-name reference |
| game theory | T18-strategic-interaction | strategic-interaction | — | strong | trigger phrase |
| payoff matrix | T18-strategic-interaction | strategic-interaction | — | strong | trigger phrase |
| Nash equilibrium | T18-strategic-interaction | strategic-interaction | — | strong | method reference |
| backward induction | T18-strategic-interaction | strategic-interaction | — | strong | method reference |
| deterrence | T18-strategic-interaction | strategic-interaction | — | strong | trigger phrase |
| bargaining | T18-strategic-interaction | strategic-interaction | — | strong | trigger phrase |
| what's their best move | T18-strategic-interaction | strategic-interaction | — | strong | trigger phrase |
| what will they do if we do X | T18-strategic-interaction | strategic-interaction | — | strong | trigger phrase |
| credibility of threat | T18-strategic-interaction | strategic-interaction | — | strong | trigger phrase |
| signalling | T18-strategic-interaction | strategic-interaction | — | weak | tonal cue (game-theoretic) |
| coalition | T18-strategic-interaction | strategic-interaction | — | weak | tonal cue (multi-actor) |

---

## T19 — Spatial Composition

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| ma reading | T19-spatial-composition | ma-reading | within-territory: specificity? → aesthetic-experiential | strong | mode-name reference |
| Ma | T19-spatial-composition | ma-reading | within-territory: specificity? → aesthetic-experiential | strong | tradition vocabulary |
| void as content | T19-spatial-composition | ma-reading | within-territory: specificity? → aesthetic-experiential | strong | mode vocabulary |
| interval as primary | T19-spatial-composition | ma-reading | within-territory: specificity? → aesthetic-experiential | strong | mode vocabulary |
| interval as content | T19-spatial-composition | ma-reading | within-territory: specificity? → aesthetic-experiential | strong | mode vocabulary |
| Japanese aesthetics | T19-spatial-composition | ma-reading | within-territory: specificity? → aesthetic-experiential | strong | tradition reference |
| Japanese aesthetic reading | T19-spatial-composition | ma-reading | within-territory: specificity? → aesthetic-experiential | strong | trigger phrase |
| Yūgen | T19-spatial-composition | ma-reading | — | strong | tradition vocabulary |
| Wabi-sabi | T19-spatial-composition | ma-reading | — | strong | tradition vocabulary |
| Mu | T19-spatial-composition | ma-reading | — | strong | tradition vocabulary |
| the empty space here | T19-spatial-composition | ma-reading | — | weak | tonal cue (void-as-content) |
| what is the silence doing | T19-spatial-composition | ma-reading | — | weak | tonal cue (void-as-content) |
| Ozu pillow shot | T19-spatial-composition | ma-reading | — | strong | tradition reference |
| Tarkovsky long take | T19-spatial-composition | ma-reading | — | strong | tradition reference |
| compositional dynamics | T19-spatial-composition | compositional-dynamics | within-territory: specificity? → universal-perceptual | strong | mode-name reference |
| Gestalt grouping | T19-spatial-composition | compositional-dynamics | within-territory: specificity? → universal-perceptual | strong | method-name reference |
| gestalt | T19-spatial-composition | compositional-dynamics | — | strong | method vocabulary |
| perceptual grouping | T19-spatial-composition | compositional-dynamics | — | strong | method vocabulary |
| figure-ground | T19-spatial-composition | compositional-dynamics | — | strong | method vocabulary |
| Arnheim | T19-spatial-composition | compositional-dynamics | — | strong | author reference |
| Arnheim forces | T19-spatial-composition | compositional-dynamics | — | strong | method-name reference |
| compositional forces | T19-spatial-composition | compositional-dynamics | — | strong | method vocabulary |
| structural skeleton | T19-spatial-composition | compositional-dynamics | — | strong | mode vocabulary |
| visual weight | T19-spatial-composition | compositional-dynamics | — | strong | mode vocabulary |
| compositional reading | T19-spatial-composition | compositional-dynamics | — | strong | trigger phrase |
| Itten | T19-spatial-composition | compositional-dynamics | — | strong | author reference |
| Albers | T19-spatial-composition | compositional-dynamics | — | strong | author reference |
| where the eye goes | T19-spatial-composition | compositional-dynamics | — | weak | tonal cue (perceptual parse) |
| eye path | T19-spatial-composition | compositional-dynamics | — | strong | mode vocabulary |
| place reading | T19-spatial-composition | place-reading-genius-loci | within-territory: specificity? → descriptive-evaluative-deep | strong | mode-name reference |
| genius loci | T19-spatial-composition | place-reading-genius-loci | within-territory: specificity? → descriptive-evaluative-deep | strong | mode-name reference |
| spirit of place | T19-spatial-composition | place-reading-genius-loci | — | strong | tradition vocabulary |
| Alexander pattern language | T19-spatial-composition | place-reading-genius-loci | — | strong | author + method reference |
| pattern language | T19-spatial-composition | place-reading-genius-loci | — | strong | method-name reference |
| Christopher Alexander | T19-spatial-composition | place-reading-genius-loci | — | strong | author reference |
| prospect-refuge | T19-spatial-composition | place-reading-genius-loci | — | strong | method-name reference |
| prospect refuge | T19-spatial-composition | place-reading-genius-loci | — | strong | method-name reference |
| Norberg-Schulz | T19-spatial-composition | place-reading-genius-loci | — | strong | author reference |
| Lynch image of the city | T19-spatial-composition | place-reading-genius-loci | — | strong | author + book reference |
| image of the city | T19-spatial-composition | place-reading-genius-loci | — | strong | book reference |
| paths edges districts nodes landmarks | T19-spatial-composition | place-reading-genius-loci | — | strong | method vocabulary |
| topoanalysis | T19-spatial-composition | place-reading-genius-loci | — | strong | method-name reference |
| Bachelard | T19-spatial-composition | place-reading-genius-loci | — | strong | author reference |
| poetics of space | T19-spatial-composition | place-reading-genius-loci | — | strong | book reference |
| Appleton | T19-spatial-composition | place-reading-genius-loci | — | strong | author reference |
| Kaplan attention restoration | T19-spatial-composition | place-reading-genius-loci | — | strong | author + method reference |
| biophilic design | T19-spatial-composition | place-reading-genius-loci | — | strong | method-name reference |
| how will people use this space | T19-spatial-composition | place-reading-genius-loci | — | weak | tonal cue (affordance reading) |
| information density | T19-spatial-composition | information-density | within-territory: specificity? → applied-evaluative | strong | mode-name reference |
| visual hierarchy | T19-spatial-composition | information-density | within-territory: specificity? → applied-evaluative | strong | trigger phrase |
| Tufte | T19-spatial-composition | information-density | within-territory: specificity? → applied-evaluative | strong | author reference |
| data-ink ratio | T19-spatial-composition | information-density | — | strong | method-name reference |
| data-ink | T19-spatial-composition | information-density | — | strong | method vocabulary |
| chartjunk | T19-spatial-composition | information-density | — | strong | method vocabulary |
| small multiples | T19-spatial-composition | information-density | — | strong | method-name reference |
| sparkline | T19-spatial-composition | information-density | — | strong | method-name reference |
| Bertin | T19-spatial-composition | information-density | — | strong | author reference |
| Bertin visual variables | T19-spatial-composition | information-density | — | strong | author + method reference |
| visual variables | T19-spatial-composition | information-density | — | strong | method vocabulary |
| selective associative ordered quantitative | T19-spatial-composition | information-density | — | strong | method vocabulary |
| Cleveland-McGill perceptual tasks | T19-spatial-composition | information-density | — | strong | author + method reference |
| Cleveland McGill | T19-spatial-composition | information-density | — | strong | author reference |
| elementary perceptual tasks | T19-spatial-composition | information-density | — | strong | method vocabulary |
| graphical perception | T19-spatial-composition | information-density | — | strong | method vocabulary |
| typographic hierarchy | T19-spatial-composition | information-density | — | strong | method-name reference |
| Bringhurst | T19-spatial-composition | information-density | — | strong | author reference |
| Lupton | T19-spatial-composition | information-density | — | strong | author reference |
| critique this chart | T19-spatial-composition | information-density | — | strong | trigger phrase |
| this dashboard isn't working | T19-spatial-composition | information-density | — | weak | tonal cue (info-graphic critique) |

---

## T20 — Open Exploration (Generative)

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| passion exploration | T20-open-exploration | passion-exploration | — | strong | mode-name reference |
| I'm interested in | T20-open-exploration | passion-exploration | — | strong | trigger phrase |
| help me think about | T20-open-exploration | passion-exploration | — | strong | trigger phrase |
| I've been wondering | T20-open-exploration | passion-exploration | — | strong | trigger phrase |
| what if | T20-open-exploration | passion-exploration | — | weak | trigger phrase (also fires T9 paradigm) |
| just exploring | T20-open-exploration | passion-exploration | — | weak | tonal cue (open-endedness) |
| no specific deliverable | T20-open-exploration | passion-exploration | — | weak | tonal cue (no project) |
| mull over | T20-open-exploration | passion-exploration | — | weak | tonal cue (wandering) |

---

## T21 — Execution / Project Mode (Non-Analytical)

| signal | territory | mode | disambiguation_answer | confidence_weight | evidence_for_mapping |
|---|---|---|---|---|---|
| project mode | T21-execution-project | project-mode | within-territory: rendering? → no | strong | mode-name reference |
| build me | T21-execution-project | project-mode | within-territory: rendering? → no | strong | trigger phrase |
| write me | T21-execution-project | project-mode | within-territory: rendering? → no | strong | trigger phrase |
| create | T21-execution-project | project-mode | within-territory: rendering? → no | strong | trigger phrase |
| draft | T21-execution-project | project-mode | within-territory: rendering? → no | strong | trigger phrase |
| design | T21-execution-project | project-mode | within-territory: rendering? → no | strong | trigger phrase |
| produce | T21-execution-project | project-mode | within-territory: rendering? → no | strong | trigger phrase |
| structured output | T21-execution-project | structured-output | within-territory: rendering? → yes | strong | mode-name reference |
| format as a memo | T21-execution-project | structured-output | within-territory: rendering? → yes | strong | trigger phrase |
| write this as a report | T21-execution-project | structured-output | within-territory: rendering? → yes | strong | trigger phrase |
| comparison table | T21-execution-project | structured-output | within-territory: rendering? → yes | strong | trigger phrase |
| outline form | T21-execution-project | structured-output | within-territory: rendering? → yes | strong | trigger phrase |
| one-pager | T21-execution-project | structured-output | within-territory: rendering? → yes | strong | trigger phrase |
| render this | T21-execution-project | structured-output | within-territory: rendering? → yes | weak | tonal cue (formatting only) |

---

## Query Interface

The Stage 2 sufficiency analyzer queries the registry with the cleaned prompt as input and returns a list of (signal, territory, mode, confidence_weight, disambiguation_answer) tuples for every match.

**Substring matching (case-insensitive).** A signal matches when its full text appears as a substring of the prompt, with no respect for word boundaries beyond what the substring naturally enforces. Case is folded on both sides. Example: a prompt containing "What do these RAG tradeoffs look like as a 2x2 matrix?" matches signals `RAG` (if registered), `2x2 matrix`, and any partial fragments registered as signals.

**Longer-match-wins overlap resolution.** When multiple signals overlap on the same prompt span, the longer signal wins and the shorter signal is suppressed for that span. Example: if both `red team` and `red team this` are registered, a prompt containing "red team this draft" credits only the `red team this` match. Distinct non-overlapping matches both count.

**Multiple-signal accumulation (signals AND together per Pre-Routing Pipeline Architecture §2.2).** Multiple signal hits within the same territory accumulate evidence for that territory's modes. The accumulator weights `strong` matches above `weak` matches. Disambiguation-answer matches additionally pre-resolve within-territory questions: if a strong-confidence disambiguation_answer hit is present, the analyzer treats the disambiguation question as already answered and proceeds to the named mode without asking the user.

**Cross-territory matches.** When signals from multiple territories fire, the analyzer surfaces all candidates to Stage 3 (territory selection) — the registry does not pick between territories on its own. Only intra-territory weight comparisons happen at Stage 2.

## Update Protocol

Registry edits require user review. The author is non-programmer; vocabulary tonal calibration is high-stakes for routing accuracy and an arbitrary signal addition can re-route a substantial fraction of traffic. Phase 2 contributes new entries incrementally per migrated mode (one mode's signals per editing session, with the user reviewing the proposed list before commit). Phase 4 adds new-mode signals per wave when a new mode lands in the registry. Out-of-band edits — e.g., a user request to add a colloquialism — go through the same review.

*End of Reference — Signal Vocabulary Registry.*
