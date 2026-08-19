export const meta = {
  name: 'verify-conversation-project-accepts',
  description: 'Re-judge accepted segments whose recorded reason did not describe them',
  phases: [{ title: 'Judge', detail: 'one Haiku agent per candidate batch' }],
}

const SCHEMA = {
  type: 'object',
  properties: {
    nexus: { type: 'string' },
    batch: { type: 'number' },
    judged: { type: 'number' },
    accepted: { type: 'number' },
    wrote_file: { type: 'boolean' },
    missing_ids: { type: 'array', items: { type: 'string' } },
  },
  required: ['nexus', 'batch', 'judged', 'accepted', 'wrote_file'],
  additionalProperties: false,
}

const ROOT = '/Users/oracle/ora/data/conversation-projects'

function pad(n) { return String(n).padStart(3, '0') }

function promptFor(nexus, batch) {
  const inPath = `${ROOT}/verify-input/${nexus}/batch-${pad(batch)}.json`
  const outPath = `${ROOT}/verify-output/${nexus}/batch-${pad(batch)}.json`
  return `You are judging whether archived conversation segments belong to a specific project.

STEP 1. Read this input file in full:
${inPath}

It contains:
- "project": the project's nexus, name, Core Essence, Resolution Statement, Objectives, Excluded Outcomes and distinctive entities. This is the definition you judge against. Nothing else.
- "expected_candidate_ids": the EXACT list of candidate_id strings you must return a verdict for. Every one, no more, no fewer.
- "candidates": each has candidate_id, subject (a one-line description of what that segment of the conversation is about), conversation_title, date, matched_routes, and excerpts of the actual conversation text.

These candidates were all ACCEPTED for this project in an earlier pass, but the recorded reason did not describe the candidate it was attached to -- the earlier judge was writing one summary across a whole batch instead of reading each segment. Ignore that earlier verdict entirely. Judge each candidate fresh, on its own excerpts, and expect to overturn some of them.

STEP 2. For EACH candidate decide: does this segment belong to THIS project?

The excerpts are not the opening of the exchange. They are the passages of it densest in this project's own vocabulary — the part that made the segment match. Judge on what those passages actually say.

ACCEPT when the segment contains real engagement with this project: work on it, planning for it, discussion of its subject matter, or material that belongs to it. A sustained discussion of the project counts even when it sits inside a longer conversation about something else and even when the segment's one-line subject names that other thing. Several sentences of the user describing the project, its scope, or what they intend to do with it is engagement, not a mention.

REJECT when the connection is nominal:
- the project's name appearing in a list, an index, a table of matrices, a set of wikilinks, or a status roll-up;
- a single clause referring to the project in passing while the passage is about something else;
- generic methodology, framework, or writing-process discussion that echoes the project's mission language without touching its subject;
- a DIFFERENT project that shares vocabulary with this one.

The test is not "is this project the segment's headline topic". It is "would someone researching this project want to read this segment". Vector similarity retrieved these candidates at roughly 50-60% precision, so expect to reject many — but do not reject genuine engagement merely because the segment is filed under another subject.

A segment may legitimately belong to several projects; that is fine. Judge only THIS project, independently.

Set confidence "high" when the excerpts settle it, "medium" when the subject line settles it but the excerpts are thin, "low" when you are guessing.

Each "reason" must name a concrete detail from THAT candidate — the actual topic, artifact, or phrase you judged on. Under 15 words. Do not reuse one wording across candidates; a reason that would fit any candidate in the batch is not a reason.

STEP 3. Write your verdicts as JSON to:
${outPath}

Exact shape:
{"nexus": "${nexus}", "batch": ${batch}, "verdicts": [{"candidate_id": "...", "verdict": "yes", "confidence": "high", "reason": "..."}, ...]}

Rules for the file:
- verdict is exactly "yes" or "no".
- Include one entry for EVERY id in expected_candidate_ids, in that order.
- Do NOT invent candidate_ids. Before writing, check your id list against expected_candidate_ids; they must match exactly. A previous run of this campaign had ids invented outright, so this is checked.

STEP 4. You MUST return your answer by calling the StructuredOutput tool. Do not reply with prose. Report the counts you actually wrote, set wrote_file true only if the Write succeeded, and list in missing_ids any expected id you could not judge.`
}

const items = (args || []).map((raw) => {
  if (typeof raw !== 'string') return raw
  const cut = raw.lastIndexOf(':')
  return { nexus: raw.slice(0, cut), batch: Number(raw.slice(cut + 1)) }
})
log(`judging ${items.length} batches`)

const results = await parallel(items.map((item) => () =>
  agent(promptFor(item.nexus, item.batch), {
    label: `judge:${item.nexus}:${pad(item.batch)}`,
    model: 'haiku',
    phase: 'Judge',
    schema: SCHEMA,
  })
))

const ok = results.filter(Boolean)
const failed = items.filter((_, i) => !results[i])
const noFile = ok.filter((r) => !r.wrote_file)
const judged = ok.reduce((a, r) => a + (r.judged || 0), 0)
const accepted = ok.reduce((a, r) => a + (r.accepted || 0), 0)

return {
  batches: items.length,
  returned: ok.length,
  judged,
  accepted,
  failed_batches: failed,
  claimed_no_file: noFile.map((r) => `${r.nexus}:${r.batch}`),
}
