export const meta = {
  name: 'verify-discovered-works',
  description: 'Adversarially verify each discovered work against its own evidence, three independent refuters per claim',
  phases: [{ title: 'Refute', detail: 'three sceptics per candidate work' }],
}

const SCHEMA = {
  type: 'object',
  properties: {
    index: { type: 'number' },
    refuted: { type: 'boolean' },
    verdict: { type: 'string' },
    is_distinct_work: { type: 'boolean' },
    development_real: { type: 'string' },
    quote_found: { type: 'boolean' },
    best_quote: { type: 'string' },
    duplicate_of: { type: 'string' },
  },
  required: ['index', 'refuted', 'verdict', 'is_distinct_work', 'quote_found'],
  additionalProperties: false,
}

const ROOT = '/Users/oracle/ora/data/conversation-projects'
const pad = (n) => String(n).padStart(3, '0')

const LENSES = {
  reality: 'Is the user actually BUILDING an artifact here, or merely discussing, analysing, or asking about a topic? News commentary, political analysis, and one-off questions are NOT works. Demand evidence of outlining, drafting, naming, structuring, or planning.',
  duplication: 'Is this really a separate work, or is it the same thing as one of the user\'s known projects under a different name? The known set includes: Ora (formerly Aura, Oracle, Third Brain), Main Street Independent and its voices, American Jesus / Judas / King, Diklis Chump, We Too, Quantum Mechanics (Wobble Model), Human Nexus, and the vault Incubator reports (A Special Life, K-Shaped Economy Novel, Patent Salting, Friendship Wisconsin, Hackers Novel, Supreme Court, Parliament of Mind, Oracle Book, and 23 others).',
  evidence: 'Does the cited evidence actually support the claim? Check that the claimed quote appears in the excerpts and that the segments are about this work rather than something adjacent. A claim resting on one thin segment is not established.',
}

function promptFor(index, lens) {
  const inPath = `${ROOT}/verify-works/work-${pad(index)}.json`
  const outPath = `${ROOT}/verify-works-output/work-${pad(index)}-${lens}.json`
  return `You are a sceptic. Your job is to REFUTE a claim that the user has an undocumented creative or intellectual work.

STEP 1. Read this file in full:
${inPath}
It contains "claim" (what a previous agent asserted) and "evidence" (the actual conversation segments it cited).

STEP 2. Attack the claim through this specific lens:
${LENSES[lens]}

Default to refuted=true when you are uncertain. A claim survives only if the evidence plainly establishes it. Do not be generous.

STEP 3. Write your finding as JSON to:
${outPath}

Exact shape:
{"index": ${index}, "refuted": true, "verdict": "one sentence saying why it does or does not survive", "is_distinct_work": false, "development_real": "passing|early|moderate|advanced", "quote_found": false, "best_quote": "a verbatim phrase from the evidence, or empty", "duplicate_of": "known project name if this duplicates one, else empty"}

"best_quote" must be text that actually appears in the evidence excerpts. If you cannot find one, leave it empty and set quote_found false.

STEP 4. You MUST return your answer by calling the StructuredOutput tool. Do not reply with prose.`
}

const indexes = (args || []).map(Number)
const lenses = Object.keys(LENSES)
log(`refuting ${indexes.length} claims through ${lenses.length} lenses each`)

const results = await parallel(indexes.map((index) => () =>
  parallel(lenses.map((lens) => () =>
    agent(promptFor(index, lens), {
      label: `refute:${pad(index)}:${lens}`,
      model: 'haiku',
      phase: 'Refute',
      schema: SCHEMA,
    })
  )).then((votes) => {
    const good = votes.filter(Boolean)
    const refuted = good.filter((v) => v.refuted).length
    return { index, votes: good.length, refuted, survives: good.length > 0 && refuted < 2 }
  })
))

const ok = results.filter(Boolean)
return {
  claims: indexes.length,
  survived: ok.filter((r) => r.survives).map((r) => r.index),
  refuted: ok.filter((r) => !r.survives).map((r) => r.index),
}
