---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-01

---

# MODE: Synthesis

```yaml
# 0. IDENTITY
mode_id: synthesis
canonical_name: Synthesis
suffix_rule: analysis
educational_name: cross-domain integrative synthesis

# 1. TERRITORY AND POSITION
territory: T12-cross-domain-and-knowledge-synthesis
gradation_position:
  axis: stance
  value: integrative
adjacent_modes_in_territory:
  - mode_id: dialectical-analysis
    relationship: stance counterpart (thesis-antithesis-sublation, adversarial commitment)
  - mode_id: cross-domain-analogical
    relationship: specificity variant (cross-domain analogical, deferred per CR-6)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "two bodies of knowledge developed separately, want to examine them together"
    - "wondering how X and Y connect"
    - "looking for the structural parallel between two frameworks"
  prompt_shape_signals:
    - "synthesise"
    - "synthesize"
    - "connect these frameworks"
    - "what's the structural parallel"
    - "map the intersection"
    - "how does X relate to Y"
disambiguation_routing:
  routes_to_this_mode_when:
    - "neutral examination of connection between two developed positions"
    - "wants to identify productive tension and structural correspondence without choosing sides"
  routes_away_when:
    - "wants to drive thesis through antithesis to produce something genuinely new" → dialectical-analysis
    - "wants to choose between the positions" → constraint-mapping (T3)
    - "wants the strongest version of one position" → steelman-construction (T15)
when_not_to_invoke:
  - "User is operating within one domain — synthesis requires two-or-more bodies of knowledge"
  - "User is comparing paradigms (frame vs frame) rather than integrating knowledge bodies" → T9 frame-comparison

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: neutral

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [framework_a_named, framework_b_named, prior_user_engagement_with_each]
    optional: [explicit_connection_hypotheses, prior_synthesis_attempts]
    notes: "Applies when user names frameworks by their established titles and references prior depth in each."
  accessible_mode:
    required: [two_or_more_topic_areas_to_connect]
    optional: [intuited_overlaps, motivating_question]
    notes: "Default. Mode infers framework boundaries from the user's description."
  detection:
    expert_signals: ["framework", "lineage", "tradition", "school of thought"]
    accessible_signals: ["how does X relate to Y", "wondering about the connection between"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What are the two (or more) bodies of knowledge or frameworks you want me to synthesise?'"
    on_underspecified: "Ask: 'Which two areas should I work between, and what's the question that's drawing you to the connection?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are the proposed connections structural correspondences at the mechanism level, or surface analogies?"
    failure_mode_if_unmet: false-synthesis
  - cq_id: CQ2
    question: "Do both frameworks survive the synthesis as peer roots, or has one been reduced to a special case of the other?"
    failure_mode_if_unmet: reduction-trap
  - cq_id: CQ3
    question: "Have productive tensions been named explicitly, or smoothed over to produce apparent harmony?"
    failure_mode_if_unmet: harmony-trap
  - cq_id: CQ4
    question: "Does the synthesis produce an emergent insight unavailable from either framework alone?"
    failure_mode_if_unmet: restatement-only

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: false-synthesis
    detection_signal: "Cross-link rests on shared vocabulary or evocative similarity rather than mechanism-level correspondence."
    correction_protocol: re-dispatch (apply mechanism test before declaring cross-link)
  - name: reduction-trap
    detection_signal: "One framework appears as a special case of the other rather than as a peer root."
    correction_protocol: re-dispatch (preserve both frameworks as peer roots)
  - name: harmony-trap
    detection_signal: "No productive tensions named; frameworks rendered as fully compatible."
    correction_protocol: flag (add tension paragraph and tension cross-link)
  - name: no-cross-link
    detection_signal: "Two separate trees presented with no inter-framework connection."
    correction_protocol: re-dispatch (add at least one cross-framework link)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - cross-domain-analogical-mapping (when frameworks come from distant domains)
    - structural-isomorphism-detection
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Synthesis is its own depth target in T12; deeper integration would shift mode."
  sideways:
    target_mode_id: dialectical-analysis
    when: "The synthesis reveals deep opposition requiring adversarial commitment rather than neutral integration."
  downward:
    target_mode_id: null
    when: "T12 has no lighter integrative sibling currently."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Synthesis is the degree to which proposed connections survive the structural-vs-metaphorical test. A thin pass names parallels by shared vocabulary; a substantive pass states the mechanism that makes each parallel a structural correspondence rather than a surface analogy. Test depth by asking: could the proposed connection be falsified by examining a case where one framework's mechanism operates and the other's does not? If yes, the connection is structural. If the connection only restates that "both X and Y address related themes," it is surface.

## BREADTH ANALYSIS GUIDANCE

Breadth in Synthesis is the catalog of candidate connections considered before selecting which survive the mechanism test. Generate at minimum three candidate connections, including at least one non-obvious. Widen the lens to cross-domain analogical scans and to less-obvious correspondences (units of analysis, generative mechanisms, failure modes). Breadth markers: the synthesis surveys the productive tensions as well as the convergences, and explicitly names what it leaves out.

## EVALUATION CRITERIA

Synthesis is read in the structural-isomorphism-detection tradition and the cross-domain analogical-mapping literature (Hofstadter-style structural correspondence, Gentner's analogical-mapping theory) — the discipline that distinguishes genuine structural correspondence from surface analogy. The evaluator's primary axes are peer-root integrity and mechanism-test discipline. CQ1 (false-synthesis) is load-bearing because surface analogies dressed as cross-links are the most common way the methodology fails — vocabulary similarity is mistaken for mechanism similarity. CQ2 (reduction-trap) is also load-bearing because reducing one framework to a special case of the other collapses synthesis into endorsement. CQ3 (harmony-trap) and CQ4 (restatement-only) act as gates on tension surfacing and emergent value.

Evaluator checks:

1. **Mechanism test on every cross-link (CQ1, load-bearing).** Each cross-link must carry an explicit mechanism-test result — what would falsify the parallel if one framework's mechanism operated and the other's did not? Cross-links resting on shared vocabulary ("both use the word 'system'," "both reference structure"), evocative similarity, or thematic overlap are false-synthesis residue. The reading discipline: a structural correspondence predicts behaviour the surface analogy doesn't, and the deliverable names the prediction. Cross-links that cannot be defended at the mechanism level migrate to ruled-out cross-links rather than surviving.

2. **Peer-root parity (CQ2, load-bearing).** Both (or all) frameworks must render at the same structural rank in the deliverable. Reduction-trap residue is "X is really a kind of Y," "Y is the more general case of X," or a framework rendered as a sub-section under another. The evaluator's check: visual peer-root parity — does each framework get its own H3 block at section-1 depth, with comparable detail on lineage, units of analysis, generative mechanism, and known failure modes? Asymmetric rendering smuggles in the reduction.

3. **Productive tensions surfaced (CQ3).** At least one productive tension between the frameworks must be named — a place where they pull in different analytical directions and the tension is itself the finding rather than bloat to smooth over. Harmony-trap residue is "the frameworks beautifully complement each other," "they share a deep affinity," or any harmony-padding that erases the analytical work. The reading: productive tensions are findings about the synthesis space, not failures of synthesis to resolve.

4. **Emergent insight requires both frameworks (CQ4).** The emergent insight must be a claim that neither framework alone produces. Restatement-only residue is an "emergent insight" the evaluator could have written by reading just one framework. The test: does the insight cite which framework contributed which aspect, and is each contribution necessary? Insights that one framework alone would have produced are downgraded or reshaped.

5. **Ruled-out cross-links surfaced.** The deliverable must carry ruled-out cross-link atoms — candidate connections the breadth pass considered but the mechanism test rejected. Their presence is evidence the synthesis considered alternatives and disciplined itself; their absence suggests the surviving cross-links may not have been tested. At minimum the breadth pass considered three candidates; the ratio of confirmed to ruled-out cross-links is a finding about the synthesis's solidity.

6. **Limitations named.** The synthesis must name a domain or condition where it breaks down — where the cross-links fail to apply or the frameworks genuinely disagree without productive tension. Limitations are scope-discipline; their absence implies the synthesis claims completeness it has not earned. The evaluator confirms the limitations atom is present and substantive.

7. **No advocacy.** Synthesis is neutral examination, not endorsement of one framework. Where the analysis tips toward one framework's vocabulary or accepts its assumptions silently, the neutrality has slipped. The evaluator confirms both frameworks survive in their own terms — own-terms vocabulary preserved per framework rather than translated into one framework's lexicon.

Confidence is per-cross-link: high when mechanism evidence is direct (cases on record where the structural prediction was tested); lower when the mechanism test depends on conjectural extrapolation. Where streams disagreed on whether a cross-link passes the mechanism test, the evaluator confirms the disagreement is preserved as a tension atom rather than silently resolved.

## REVISION GUIDANCE

Revise to add mechanism evidence where the draft asserts connection by vocabulary alone. Revise to surface tensions where the draft has smoothed them. Resist revising toward apparent harmony — productive tensions are findings, not failures. Resist revising toward endorsing one framework — Synthesis is neutral examination, not advocacy. If a cross-link cannot be defended at the mechanism level, remove it and note in prose that the connection is superficial.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **peer-root framework atoms bridged by mechanism-level cross-link atoms, with productive-tension atoms, emergent-insight atom, and limitations atoms**. The peer-root status of both frameworks is load-bearing; the mechanism test on each cross-link is the discipline that distinguishes synthesis from surface analogy. The atoms are:

1. **Framework atoms — peer roots.** Each carries: framework name, lineage / tradition, units of analysis, generative mechanism, and known failure modes. Both frameworks appear at the same structural rank in the corpus; reduction-trap is the named failure mode, and treating one framework as a special case of the other is its corpus signature. The corpus carries both as roots even when one is more developed or familiar.

2. **Cross-link atoms — mechanism-tested only.** Each carries: source-framework atom, target-framework atom, the proposed correspondence, and the **mechanism-test result** — what makes this a structural correspondence rather than a surface analogy. The mechanism test asks: could the cross-link be falsified by a case where one framework's mechanism operates and the other's does not? Cross-links that fail the test do not survive as cross-links — they survive as ruled-out cross-link atoms (see item 6). False-synthesis is the named failure mode; mechanism-untested cross-links are its corpus signature.

3. **Productive-tension atoms.** Each names a real tension between the frameworks — a place where they pull in different analytical directions and the tension is itself productive (not bloat to smooth over). Each tension atom carries: the position from each framework, the tension's load-bearing reason, and what the tension reveals about the synthesis space. Harmony-trap is the named failure mode; corpus with cross-links but no productive-tension atoms is its signature. At least one productive-tension atom must survive or harmony-trap fires.

4. **Emergent-insight atom.** A single corpus-level atom names the insight unavailable from either framework alone — what the synthesis produces that is not a restatement of either source. Restatement-only is the named failure mode; an emergent-insight atom that the consolidator could have written by reading just one framework is its corpus signature. The atom must name what's new and what made it visible (which cross-link or tension produced it).

5. **Limitations atoms.** Each names a domain or condition where the synthesis breaks down — where the cross-links fail to apply or the frameworks genuinely disagree without productive tension. Limitations atoms guard against scope-overreach and signal where downstream use of the synthesis should pause.

6. **Ruled-out cross-link atoms.** Each names a candidate cross-link that failed the mechanism test, with: the proposed correspondence, the case that falsified it, and the reason it's surface rather than structural. The ruled-out atoms are evidence of breadth (at least three candidate connections considered per the breadth marker) and discipline (failed candidates are surfaced as ruled-out rather than dropped silently). At minimum the breadth pass considered three candidates; the ratio of cross-link to ruled-out atoms is a finding about the synthesis's solidity.

7. **Confidence per cross-link.** Confidence markers attach to individual cross-link atoms (high when mechanism evidence is direct; lower when the mechanism test depends on conjectural extrapolation). When the two streams assigned different confidences, audit conservatism applies.

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Vocabulary-shared cross-links** — connections asserted because the frameworks share a term ("both use the word 'system'", "both reference structure"). False-synthesis residue; either a mechanism-level evidence atom is added (and the cross-link survives) or the candidate migrates to ruled-out cross-links.
- **Harmony-padding** — phrases like "the frameworks beautifully complement each other", "they share a deep affinity". Harmony-trap residue; the corpus carries productive-tension atoms rather than affinity language.
- **Reduction-language residue** — "X is really a kind of Y", "Y is the more general case of X". Reduction-trap residue; the corpus carries both as peer roots, and reduction language either gets reframed as "X and Y address the same problem from different mechanism-paths" or is dropped.
- **Restatement-only emergent insight** — an "emergent insight" that the consolidator could have written by reading just one framework. Restatement-only residue; the emergent-insight atom must require both frameworks to produce.
- **Tension-as-failure framing** — phrases that treat productive tensions as flaws or open problems to resolve. The tensions are findings; reframing them as failures-of-synthesis is its own failure mode. The corpus carries them with "productive tension" framing.
- **Cross-link inflation** — many shallow cross-links rather than fewer mechanism-tested ones. The bloat strip prunes shallow cross-links; the corpus carries fewer-but-mechanism-tested over many-but-vocabulary-tested.

**What NOT to collapse:**

- **Different mechanism-test results for the same cross-link** — when one stream judged a cross-link mechanism-tested-passing and the other judged it failing, preserve both judgments. The disagreement is consequential for whether the cross-link survives or migrates to ruled-out; the consolidator must not silently pick. The corpus carries the cross-link with both judgments and lets downstream verify.
- **Different productive tensions surfaced** — when streams identified different real tensions between the frameworks, preserve all surviving tensions as parallel atoms. Multiple tensions is a sign of breadth, not redundancy.
- **Limitations disagreement** — when streams disagreed on whether the synthesis applies to a particular domain, preserve both judgments as a contested-limitation atom. Whether the synthesis extends to that domain is itself a finding.

## VERIFICATION CRITERIA

Verified means: both frameworks present as peer roots; ≥ 1 cross-link with mechanism evidence; ≥ 1 productive tension named; emergent insight named; ≥ 1 limitation named. Every cross-link's connection survives the mechanism test (could be falsified by a case where one framework's mechanism operates and the other's does not). The four critical questions are addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **structured peer-root synthesis: two (or more) frameworks at parallel rank with mechanism-tested cross-links, productive tensions, emergent insight, and limitations**. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Frameworks identified — peer roots.** Two (or more) parallel H3 sub-sections, one per framework. Each sub-section: `**Framework name** — lineage / tradition: [...]. Units of analysis: [...]. Generative mechanism: [the engine the framework uses to produce its insights]. Known failure modes: [the framework's own internal limits, not external critique].` Both frameworks render at the same structural depth — reduction-trap is the named failure mode (treating one as a special case of the other).

2. **Structural parallels — mechanism-tested cross-links.** Numbered list. Each cross-link: `**Cross-link [N]:** [Framework A's element] ↔ [Framework B's element]. Mechanism-test: [what makes this a structural correspondence rather than a surface analogy — i.e., what case would falsify the parallel if one framework's mechanism operated and the other's did not]. Status: confirmed.` At minimum one mechanism-tested cross-link.

3. **Evidence for genuineness.** For each cross-link from section 2, a short block: `Cross-link [N] is genuine because: [specific evidence — domain cases, structural correspondences, or shared inferential moves the cross-link predicts that surface analogy would not]. Falsifying case: [the case that, if it obtained, would refute the cross-link].`

4. **Emergent insight.** A single block (one to three sentences) stating what the synthesis produces that neither framework alone produces. Frame as: `**Emergent insight:** [the claim]. This required both frameworks because: [which framework contributed what aspect, and why neither alone is sufficient].` Restatement-only is the named failure mode; an emergent insight the consolidator could have written by reading just one framework is its corpus signature.

5. **Productive tensions.** Bulleted list. Each tension: `**[Tension name]** — Framework A's position: [...]. Framework B's position: [...]. Why productive: [what the tension reveals about the synthesis space that resolving it would obscure].` At minimum one productive-tension atom; harmony-trap is the named failure mode.

6. **Limitations.** Bulleted list. Each limitation: `**[Limitation]** — domain or condition where the synthesis breaks down: [...]. Reason: [why cross-links fail here, or why the frameworks genuinely disagree without productive tension].`

7. **Ruled-out cross-links.** Bulleted list of candidates that failed the mechanism test. Each: `**[Proposed cross-link]** — failed because: [the case that falsified it]. Why surface, not structural: [reason].` These atoms are evidence of breadth (the synthesis considered candidates and ruled some out).

8. **Confidence per cross-link.** Bulleted list. Each confirmed cross-link gets a confidence marker (high / moderate / low) with reason — high when mechanism evidence is direct; lower when conjectural extrapolation.

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- Section 1's two framework blocks render at structurally equivalent depth — visual peer-root parity is load-bearing for the neutral-stance posture.
- Cross-link IDs (Cross-link 1, Cross-link 2, ...) are referenced consistently between sections 2, 3, and 8.
- Avoid harmony-padding throughout: "the frameworks beautifully complement each other", "they share a deep affinity" are forbidden phrasings.
- Avoid reduction-language: "X is really a kind of Y", "Y is the more general case of X" — peer-root posture is maintained.


---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~10min
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator, reference]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `extends`, `supersedes`, `derived-from`, `analogous-to`, `supports`
**Deprioritize:** `precedes`, `produces`

*Family: synthesis-dialectic. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
