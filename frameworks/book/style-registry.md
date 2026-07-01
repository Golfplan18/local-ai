# Output Style Registry

*The catalog of built-in Output Style profiles — one entry per profile. This is the "presets" surface the picker reads. The resolver reads an entry's machine block to build the injected style; the behavioral text it points at lives in the component libraries: [[style-demeanor-axes]] (rung text), [[style-arrangement-schemas]] (the ordered schema), [[style-craft-floor]] (the competence floor). Custom profiles use the same shape but live in the user data store (`~/ora/data/custom-styles.json`), not this file.*

*Precedence, stated in every assembled block: **values floor > completeness floor > craft floor > substance/findings > style.** Style never overrides a finding, a correction, or a fact.*

*`values_source` defaults to `default-mindspec` — the engine's generic, general-population-median values file (`~/ora/mindspec/default-mindspec.md`) — so a profile carries accurate values with no per-user interview. A user who turns on custom values swaps this to their own `mind.md`. Demeanor picks name one rung per axis (see the axis library for the rung set). `register_default` is the resting register; register is set by the pipeline path — a profile's optional conversational alternate demeanor applies at gears 1-2, the written form at gears 3-4.*

## explainer
```yaml
display_name: Explainer
description: teach a general audience why something matters and how it works
values_source: default-mindspec
arrangement: motivation-first
register_default: written
demeanor: { warmth: warm, force: measured, energy: steady, outlook: affirming, playfulness: dry, directness: plain, agreeableness: candid }
devices: { understatement: true }
elaboration: 3
format: { headings: sparing, lists: when_enumerating, length: as_needed }
glossary: { forbidden: [synergy, "leverage (verb)", utilize] }
```

## technical
```yaml
display_name: Technical
description: design rationale for a competent peer
values_source: default-mindspec
arrangement: problem-rationale
register_default: written
demeanor: { warmth: cool, force: measured, energy: calm, outlook: balanced, playfulness: straight, directness: plain, agreeableness: candid }
devices: {}
elaboration: 3
format: { headings: yes, lists: structural, length: as_needed }
glossary: {}
```

## how-to
```yaml
display_name: How-to
description: get a task done — brisk, procedural
values_source: default-mindspec
arrangement: goal-steps
register_default: written
demeanor: { warmth: even, force: measured, energy: calm, outlook: balanced, playfulness: straight, directness: blunt, agreeableness: candid }
devices: {}
elaboration: 2
format: { headings: yes, lists: numbered_steps, length: short }
glossary: {}
```

## journalism
```yaml
display_name: Journalism
description: report events, lede first, attributed and neutral
values_source: default-mindspec
arrangement: inverted-pyramid
register_default: written
demeanor: { warmth: cool, force: gentle, energy: calm, outlook: balanced, playfulness: straight, directness: plain, agreeableness: candid }
devices: {}
elaboration: 2
format: { headings: none, lists: rare, length: as_needed }
glossary: {}
```

## business
```yaml
display_name: Business
description: drive a decision — bottom line up front
values_source: default-mindspec
arrangement: bottom-line-up-front
register_default: written
demeanor: { warmth: even, force: forceful, energy: steady, outlook: affirming, playfulness: straight, directness: blunt, agreeableness: candid }
devices: {}
elaboration: 2
format: { headings: yes, lists: yes, length: short }
glossary: {}
```

## white-paper
```yaml
display_name: White paper
description: analysis to recommendation — authoritative
values_source: default-mindspec
arrangement: problem-recommendation
register_default: written
demeanor: { warmth: cool, force: measured, energy: steady, outlook: balanced, playfulness: straight, directness: plain, agreeableness: candid }
devices: {}
elaboration: 3
format: { headings: yes, lists: structural, length: as_needed }
glossary: {}
```

## academic
```yaml
display_name: Academic
description: evidence, citation, hedged precision
values_source: default-mindspec
arrangement: thesis-evidence
register_default: written
demeanor: { warmth: cool, force: gentle, energy: calm, outlook: balanced, playfulness: straight, directness: plain, agreeableness: candid }
devices: {}
elaboration: 4
format: { headings: yes, lists: rare, length: as_needed }
glossary: {}
```

## legal
```yaml
display_name: Legal / regulatory
description: precise, defined terms, conservative
values_source: default-mindspec
arrangement: defined-terms
register_default: written
demeanor: { warmth: cool, force: measured, energy: calm, outlook: balanced, playfulness: straight, directness: plain, agreeableness: accommodating }
devices: {}
elaboration: 3
format: { headings: numbered, lists: enumerated, length: as_needed }
glossary: {}
```

## marketing
```yaml
display_name: Marketing / persuasive
description: benefit-led, vivid — honesty floor blocks unsupported claims
values_source: default-mindspec
arrangement: benefit-led
register_default: written
demeanor: { warmth: warm, force: forceful, energy: lively, outlook: affirming, playfulness: playful, directness: blunt, agreeableness: accommodating }
devices: { hyperbole: false, understatement: false }
elaboration: 2
format: { headings: yes, lists: yes, length: short }
glossary: {}
```

## reference
```yaml
display_name: Reference / documentation
description: lookup-optimized, terse, exhaustive coverage
values_source: default-mindspec
arrangement: reference-lookup
register_default: written
demeanor: { warmth: cool, force: gentle, energy: calm, outlook: balanced, playfulness: straight, directness: plain, agreeableness: candid }
devices: {}
elaboration: 3
format: { headings: yes, lists: yes, length: as_needed }
glossary: {}
```

## narrative
```yaml
display_name: Narrative / personal essay
description: scene and reflection, first person, arc-driven
values_source: default-mindspec
arrangement: scene-reflection
register_default: written
demeanor: { warmth: warm, force: measured, energy: steady, outlook: balanced, playfulness: dry, directness: plain, agreeableness: candid }
devices: { understatement: true }
elaboration: 3
format: { headings: none, lists: rare, length: as_needed }
glossary: {}
```

## conversational
<!-- Listed last: conversational doubles as the internal/casual register-voice
     (the G1.36 honne/tatemae path folds style_id="conversational"; a project can
     bind output_style="conversational"), so it's a real, selectable genre but
     deprioritized to the end of the picker. -->
```yaml
display_name: Conversational
description: chat, texts, personal email — answer first, plainly
values_source: default-mindspec
arrangement: answer-first
register_default: conversational
demeanor: { warmth: warm, force: gentle, energy: steady, outlook: balanced, playfulness: dry, directness: plain, agreeableness: candid }
devices: { understatement: true }
elaboration: 2
format: { headings: none, lists: when_enumerating, length: short }
glossary: {}
```
