
# Framework — Paradigm and Assumption Examination

*Self-contained framework for stepping outside the assumed frame of a problem to examine the assumptions, paradigms, and worldviews that shape how the problem is being constructed. Compiled 2026-05-01 from territory entry, member mode specs, lens dependencies, and open debates.*

---

## Territory Header

- **Territory ID:** T9
- **Name:** Paradigm and Assumption Examination
- **Super-cluster:** A (Argument and Reasoning)
- **Characterization:** Operations that step outside the assumed frame of a problem to examine the assumptions, paradigms, and worldviews that shape how the problem is being constructed.
- **Boundary conditions:** Input is a problem, debate, or impasse where reframing is in play. Excludes within-frame causal investigation (T4) and within-frame hypothesis evaluation (T5).
- **Primary axis:** Stance (suspending vs. comparing vs. critiquing).
- **Secondary axes:** Depth (light atomic Paradigm Suspension → Frame Comparison → Worldview Cartography molecular).

## When to use this framework

Use when the question is whether the *frame* itself — the worldview, paradigm, set of foundational assumptions — should be examined or replaced, not merely whether claims within the frame are true. Plain-language triggers:

- "What if X is wrong?"
- "Evidence contradicts the accepted explanation."
- "I want to question the standard view."
- "Why does this consensus exist?"
- "Two camps are talking past each other."
- "I want to see what each side is assuming about the same situation."
- "The disagreement isn't about facts, it's about how we frame the issue."
- "Multiple worldviews are in play and I want to map the whole landscape."
- "Why does every solution to this problem keep failing?" (signal of frame-issue)

Do not route here when the question is about a single argument's frame within a single artifact (T1 — Frame Audit); when within-frame causal investigation is the work (T4); when within-frame hypothesis comparison is the work (T5); when integration across paradigms is the work rather than examination of differences (T12).

## Within-territory disambiguation

```
Q1 (stance): "Are you trying to suspend the current frame to see what it's hiding,
              compare two or more frames against each other,
              or build out the full landscape of how different worldviews see this?"
  ├─ "suspend the current frame" → paradigm-suspension (Tier-2)
  ├─ "compare frames" → frame-comparison (Tier-2)
  ├─ "full worldview landscape" → worldview-cartography molecular
                                   (Tier-3 — confirm runtime)
  └─ ambiguous → paradigm-suspension with escalation hook to frame-comparison

Q2 (depth, optional): "Want a single-frame surfacing on this one artifact (atomic),
                        or a sustained walk through how multiple frames build
                        and constrain each other (molecular)?"
  ├─ "single-frame on one artifact" → use the mode selected in Q1
  └─ "sustained molecular walk" → worldview-cartography
```

**Default route.** `paradigm-suspension` at Tier-2 when ambiguous (the lightest atomic; the comparing and cartography variants are sideways/upward escalations).

**Escalation hooks.**
- After `paradigm-suspension`: if multiple frames surface that need explicit comparison, hook upward to `frame-comparison`.
- After `frame-comparison`: if the comparison expands into a full landscape of worldviews, hook upward to `worldview-cartography` molecular.
- After any T9 mode: if the question collapses back into within-frame argumentation, hook sideways to T1 (`frame-audit` for a single-artifact frame surface).
- After any T9 mode: if the question becomes "integrate across these paradigms" rather than "examine the differences", hook sideways to T12 (`synthesis` or `dialectical-analysis`).

## Mode entries

### Mode — paradigm-suspension

- **Educational name:** paradigm suspension and assumption surfacing
- **Plain-language description:** A stance-suspending pass that surfaces the foundational assumptions a single consensus or position depends on, audits evidence for the consensus by separating observational from interpretive components, assesses which assumptions are load-bearing, generates alternative interpretations grounded in evidence (not strawmen), and evaluates without endorsing or attacking. The Einstein guard rail is enforced — push back against authority, never against observation; mode does not invite contrarian rejection of empirical data.

- **Critical questions:**
  1. Have foundational assumptions been stated as testable propositions, or are they smuggled in as conclusions?
  2. Is observational evidence cleanly separated from interpretive evidence, with the same standard applied to consensus and alternatives?
  3. Is the Einstein guard rail honoured — push back against authority, never against observation?
  4. Are alternatives genuinely distinct from the consensus and grounded in observational evidence, not strawmen?

- **Per-pipeline-stage guidance:**
  - **Depth.** Foundational assumptions surfaced as testable propositions; evidence audit separates observational from interpretive; load-bearing assessment per assumption; alternatives grounded in evidence.
  - **Breadth.** Scan historical paradigm-revision analogues; consider what the consensus was originally constructed against (its dialectical opposition); generate ≥2 alternative interpretations.
  - **Evaluation.** Four critical questions plus failure modes (assumption-as-conclusion, asymmetric-evidence-standard, einstein-guard-rail-violation, false-equivalence, contrarianism-trap).
  - **Consolidation.** Five required sections in prose: foundational assumptions; evidence audit (observational vs. interpretive); load-bearing assessment; alternative interpretations; evaluation.
  - **Verification.** Foundational assumptions stated as testable propositions; observational/interpretive separation maintained; Einstein guard rail honored; alternatives grounded in evidence.

- **Source tradition:** Kuhn *The Structure of Scientific Revolutions* (1962/1996); Lakatos *The Methodology of Scientific Research Programmes* (1978) for hard core / protective belt; Feyerabend *Against Method* (1975) for paradigm pluralism; Einstein on observation as the load-bearing constraint on theory revision.

- **Lens dependencies:**
  - `kuhn-paradigm-shift`: Normal science → anomaly accumulation → crisis → revolution → new normal science. Paradigms incommensurable; revolution is not just better theory but reconfiguration of what counts as a problem and a solution.
  - `lakatos-research-programmes`: Hard core (load-bearing assumptions immune to revision) + protective belt (auxiliary hypotheses revised to absorb anomalies). Programmes are progressive (predict novel facts) or degenerating (only absorb anomalies post-hoc).
  - Optional: `feyerabend-against-method`; `popper-falsification`. Foundational: `kahneman-tversky-bias-catalog`.

### Mode — frame-comparison

- **Educational name:** frame comparison (Lakoff strict-father vs. nurturant-parent and other frames)
- **Plain-language description:** A descriptive comparison of ≥2 named frames or worldviews that each apply to the same situation. Each frame is articulated on its own terms (steelman-mode within the frame) with symmetric depth across frames. Core conceptual metaphors are surfaced (Lakoff-style). What each frame makes visible is paired with what each frame obscures. Cross-frame translation difficulties and residual irreducibilities are honored — the analysis does not collapse one frame into the other's vocabulary when translation distorts.

- **Critical questions:**
  1. Has each frame been articulated on its own terms (steelman-mode within the frame), or has the analyst's preferred frame received fuller articulation than the others?
  2. Have the core conceptual metaphors of each frame been surfaced (Lakoff-style), or has the analysis stayed at the level of stated positions without descending to the metaphors that structure the positions?
  3. Has the analysis surfaced what each frame *obscures* as well as what it makes visible, or has it presented each frame as if the frame had no blind spots?
  4. Has irreducibility been honored — i.e., has the analysis resisted the temptation to translate one frame into the other's vocabulary, when such translation distorts?

- **Per-pipeline-stage guidance:**
  - **Depth.** Each frame articulated on own terms; core conceptual metaphors surfaced (Lakoff-style); blind-spots paired with visibilities; cross-frame translation difficulty noted explicitly where present.
  - **Breadth.** Scan multiple frame typologies (Lakoff political-moral; cognitive-policy frames; cultural-cosmology frames; epistemic-tradition frames).
  - **Evaluation.** Four critical questions plus failure modes (asymmetric-articulation, surface-position-only, blind-spot-omission, false-translation).
  - **Consolidation.** Eight required sections: frames named and described; core metaphors per frame; moral or value commitments per frame; what each frame makes visible; what each frame obscures; cross-frame translation difficulty; residual irreducibility; confidence per finding.

- **Source tradition:** Lakoff *Moral Politics* (1996/2002) for the strict-father / nurturant-parent application; Goffman *Frame Analysis* (1974) for the foundational sociological frame analysis; Douglas *Cultural Theory* (Thompson, Ellis & Wildavsky 1990) for cultural-cosmology frames; Mannheim *Ideology and Utopia* (1929) for the sociology-of-knowledge tradition.

- **Lens dependencies:**
  - `lakoff-conceptual-metaphor`: Source-to-target metaphorical mappings carry inferential entailments; alternative metaphors structure the same target differently. (See `Framework — Argumentative Artifact Examination.md` Lens references for full description.)
  - `frame-typology-catalog`: Lakoff political-moral models; cognitive-policy frames (Schön & Rein); cultural cosmology types (hierarchical / egalitarian / individualist / fatalist per Cultural Theory); epistemic-tradition frames (positivist / interpretivist / critical / constructivist).

### Mode — worldview-cartography

- **Educational name:** worldview cartography (multi-paradigm comparison and synthesis)
- **Plain-language description:** Molecular composition that runs paradigm-suspension (full), frame-comparison (full), and dialectical-analysis (full — serving as synthesis stage rather than peer component). Synthesizes via three stages: paradigm-inventory (parallel-merge of paradigm-suspension and frame-comparison outputs); cross-paradigm-tension-surfacing (contradiction-surfacing — explicit naming of where paradigms make incompatible claims, where they speak past each other, where they share unrecognized common ground); dialectical-cartography (dialectical-resolution — synthetic positions where dialectical resolution is possible, residual incommensurabilities where it is not, meta-level reflection on what the cartography itself reveals about the problem space).

- **Critical questions:**
  1. Has each paradigm been articulated on its own terms with comparable depth, or has the analyst's familiar paradigm received fuller articulation?
  2. Have cross-paradigm tensions been surfaced explicitly, or has the synthesis collapsed irreducibilities prematurely?
  3. Is the dialectical-resolution stage producing genuine synthesis where possible (not forced consensus)?
  4. Is the meta-level reflection adding analytical purchase, or is it a vague gesture toward "all sides have something to say"?

- **Per-pipeline-stage guidance:**
  - **Composition.** Molecular: three full components, three synthesis stages.
  - **Consolidation.** Synthesis output: paradigm inventory; per-paradigm dominant claims and blindspots; cross-paradigm tensions; dialectical synthesis where possible; residual incommensurabilities; meta-level reflection; confidence map.

- **Source tradition:** Inherits from Kuhn, Lakatos, Lakoff, Goffman; adds Hegelian dialectical tradition for the synthesis stage; Habermas *Theory of Communicative Action* for the cross-paradigm communication question; Latour *Reassembling the Social* for the actor-network alternative to paradigm framing.

- **Lens dependencies:**
  - Inherits component lens dependencies (kuhn-paradigm-shift, lakatos-research-programmes, lakoff-conceptual-metaphor, goffman-frame-analysis); adds `hegelian-dialectical-synthesis`.

- **For molecular modes:** Composition specified above. Paired execution framework: this framework supplies the synthesis-stage scaffolding directly.

## Cross-territory adjacencies

**T9 ↔ T1 (Argumentative Artifact).** "Are you evaluating this single argument's frame, or comparing different paradigms that frame the issue differently?" Single-artifact frame surfacing → T1 (Frame Audit); multi-paradigm comparison → T9.

**T9 ↔ T4 (Causal Investigation).** "Looking for the causes within how the problem is currently framed, or stepping back to ask whether the framing itself is generating the problem?" Within-frame → T4; frame-as-cause → T9.

**T9 ↔ T5 (Hypothesis Evaluation).** "Are you weighing competing explanations within a shared understanding of the problem, or are the explanations using such different frames that the disagreement is really about how to see the issue?" Within-frame hypothesis comparison → T5; inter-frame disagreement → T9.

**T9 ↔ T12 (Synthesis).** "Stepping back to examine the paradigms, or integrating across paradigms?" Examining → T9; integrating → T12.

## Lens references

### kuhn-paradigm-shift

**Core insight.** Scientific change does not proceed by accumulation. It proceeds by a sequence: *normal science* (puzzle-solving within a paradigm) → *anomaly accumulation* (puzzles that resist solution) → *crisis* (anomalies become unignorable; alternative paradigms proliferate) → *revolution* (one alternative achieves dominance; the field reconstructes its problems and standards) → *new normal science* (puzzle-solving within the new paradigm).

**Key claims.**
- *Paradigms.* A paradigm is more than a theory: it includes the exemplary problems and solutions, the methodological commitments, the relevant communities, and the standards by which work is judged.
- *Incommensurability.* Successive paradigms are not merely different theories of the same data; they reconfigure what counts as a problem, what counts as data, what counts as a solution. Translation between paradigms is partial and lossy.
- *Theory-ladenness of observation.* What scientists observe depends on the paradigm they hold. The same instrument-reading may be a confirmation under one paradigm and an anomaly under another.

**Application.** When a debate appears intractable and the parties seem to talk past each other rather than disagree on facts, the Kuhnian frame predicts that the underlying disagreement is paradigm-level. The diagnostic question: do the parties share what counts as the relevant data and what counts as a solution to the problem?

**Common misapplications.** Treating every theoretical disagreement as paradigm-level (most disagreements are within-paradigm); using "paradigm shift" as rhetorical inflation for ordinary theory revision; treating incommensurability as total rather than partial.

### lakatos-research-programmes

**Core insight.** Lakatos refines Kuhn by distinguishing two structural elements within a research programme: the *hard core* (foundational assumptions immune to revision — abandoning them would dissolve the programme itself) and the *protective belt* (auxiliary hypotheses, methodological assumptions, instrument calibrations — revised when anomalies arrive). When an anomaly threatens the hard core, the protective belt is revised to absorb the anomaly while preserving the core.

**Progressive vs. degenerating programmes.**
- *Progressive programme.* The protective-belt revisions predict novel facts that the original programme would not have predicted — the programme grows in empirical content.
- *Degenerating programme.* The protective-belt revisions only absorb known anomalies post-hoc; the programme makes no novel predictions; the revisions are ad hoc.

The progressive/degenerating distinction is the rationality criterion in Lakatos's framework: programmes with progressive revisions are rational to continue; programmes with only degenerating revisions are rational to abandon.

**Application.** When examining a paradigm under stress, identify the hard core (what is immune to revision) and the protective belt (what is being revised to absorb the anomaly). Ask: are the revisions producing novel predictions, or only absorbing the known anomaly? The answer indicates whether the paradigm is progressive or degenerating.

**Common misapplications.** Treating any auxiliary-hypothesis revision as ad hoc (some are genuinely predictive); treating hard-core revision as impossible (it sometimes happens, dissolving the programme); using progressive/degenerating as a stick to beat disliked programmes.

### lakoff-conceptual-metaphor

(See full description in `Framework — Argumentative Artifact Examination.md` Lens references.)

### goffman-frame-analysis

(See full description in `Framework — Argumentative Artifact Examination.md` Lens references.)

### frame-typology-catalog

**Core structure.** Catalog of frame typologies useful for naming frames when comparing across them.

**Lakoff political-moral models.** Strict-father (hierarchical, discipline, internalized punishment) vs. nurturant-parent (egalitarian, care, internalized empathy). Applied to American political moral reasoning. (One application; the underlying methodology generalizes.)

**Schön & Rein cognitive-policy frames.** Frames in policy disputes that organize what counts as the problem and what counts as the solution. Frame-reflective dialogue as the proposed method for moving past frame-trapped disputes.

**Cultural Theory cosmologies (Thompson, Ellis & Wildavsky 1990).** Four ways of life — Hierarchical (stratified roles, classifications, controls), Egalitarian (cohesive group with weak internal differentiation), Individualist (negotiated networks, weak group), Fatalist (accepts external classification, weak group). Each cosmology supports characteristic risk perceptions, justice intuitions, and trust patterns.

**Epistemic-tradition frames.** Positivist (objective methods, value-free, observation-grounded) vs. interpretivist (meaning-centered, hermeneutical) vs. critical (power-conscious, transformative) vs. constructivist (knowledge as constructed, plural).

**Application.** When comparing frames, name the typology being used and locate each frame within it. Comparison is more analytically tractable when the frames are positioned in a typology than when they are described in their own incommensurable vocabularies.

### hegelian-dialectical-synthesis

**Core structure.** Thesis → antithesis → synthesis. The thesis encounters its negation (antithesis); the synthesis preserves what is essential in both while transcending the conflict.

**Operational reading for cross-paradigm cartography.** When two paradigms make incompatible claims, the dialectical move is not adjudication but synthesis: identify what each paradigm captures correctly, what each misses, and construct a third position that preserves both insights while resolving the contradiction at a higher level. The synthesis may itself become a thesis facing new antithesis; dialectic is open-ended.

**Honoring irreducibility.** Not every contradiction admits dialectical synthesis. Some are *aporias* — paradoxes that cannot be resolved without losing what makes each side valuable. Worldview Cartography honors irreducibility where it appears, distinguishing genuine synthesis from forced consensus.

## Open debates

T9 carries debates relevant to frame examination but no architecture-level debates that bear on territory operation. Notes from frame examination:
- The Lakoff family-models analysis is *one application* of conceptual-metaphor methodology, not the methodology itself; mode operation is generalized.
- The Kuhn-Lakatos-Feyerabend-Popper debate over paradigm-revision rationality is foundational to T9 but does not dictate mode operation; modes treat each tradition as analytical lens without adjudicating among them.

## Citations and source-tradition attributions

**Paradigm and research-programme tradition.**
- Kuhn, Thomas S. (1962/1996). *The Structure of Scientific Revolutions* (3rd ed.). University of Chicago Press.
- Lakatos, Imre (1978). *The Methodology of Scientific Research Programmes*. Cambridge University Press.
- Feyerabend, Paul (1975). *Against Method*. New Left Books.
- Popper, Karl R. (1959). *The Logic of Scientific Discovery*. Hutchinson.
- Hacking, Ian (1983). *Representing and Intervening*. Cambridge University Press.

**Frame analysis (cognitive, sociological, communicative).**
- Lakoff, George, and Mark Johnson (1980). *Metaphors We Live By*. University of Chicago Press.
- Lakoff, George (1996/2002). *Moral Politics*. University of Chicago Press.
- Goffman, Erving (1974). *Frame Analysis*. Harvard University Press.
- Schön, Donald A., and Martin Rein (1994). *Frame Reflection: Toward the Resolution of Intractable Policy Controversies*. Basic Books.

**Cultural cosmology and sociology of knowledge.**
- Thompson, Michael, Richard Ellis, and Aaron Wildavsky (1990). *Cultural Theory*. Westview.
- Mannheim, Karl (1929/1936). *Ideology and Utopia*. Harcourt, Brace.
- Berger, Peter L., and Thomas Luckmann (1966). *The Social Construction of Reality*. Doubleday.

**Dialectical and communicative tradition.**
- Hegel, Georg Wilhelm Friedrich (1807). *Phenomenology of Spirit*.
- Habermas, Jürgen (1981/1984). *The Theory of Communicative Action*. Beacon Press.
- Latour, Bruno (2005). *Reassembling the Social: An Introduction to Actor-Network Theory*. Oxford University Press.

*End of Framework — Paradigm and Assumption Examination.*
