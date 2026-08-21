export const meta = {
  name: 'sweep-conversation-project-coverage',
  description: 'Classify segments no project route ever reached against the whole project roster',
  phases: [{ title: 'Sweep', detail: 'one Haiku agent per segment batch' }],
}

const SCHEMA = {
  type: 'object',
  properties: {
    batch: { type: 'number' },
    judged: { type: 'number' },
    placed: { type: 'number' },
    wrote_file: { type: 'boolean' },
    missing_ids: { type: 'array', items: { type: 'string' } },
  },
  required: ['batch', 'judged', 'placed', 'wrote_file'],
  additionalProperties: false,
}

// Workspace root from the environment (ORA_HOME, else <home>/ora) — these
// paths are pasted into agent prompts, so they must be absolute AND must
// not name whoever packaged the repo.
const ORA_HOME =
  process.env.ORA_HOME ||
  `${process.env.HOME || process.env.USERPROFILE}/ora`
const ROOT = `${ORA_HOME}/data/conversation-projects`
const pad = (n) => String(n).padStart(3, '0')

function promptFor(batch) {
  const inPath = `${ROOT}/sweep-input-unretrieved/batch-${pad(batch)}.json`
  const outPath = `${ROOT}/sweep-output-unretrieved/batch-${pad(batch)}.json`
  return `You are filing archived conversation segments under the projects they belong to.

STEP 1. Read this input file in full:
${inPath}

It contains:
- "projects": the complete roster of 43 registered projects, each with a nexus id, a name, what it is about, and its objectives. These are the ONLY valid nexus ids.
- "expected_candidate_ids": the EXACT list of segment ids you must return an answer for. Every one, no more, no fewer.
- "segments": each has candidate_id, subject (a one-line description of that segment), turn_range, and excerpts of the actual conversation text.

STEP 2. For EACH segment, decide which projects on the roster it belongs to. Zero, one, or several.

These segments reached no project's retrieval routes, so the honest default is that many belong nowhere. Do not reach for a project to avoid an empty answer. Most segments should get an empty list.

Assign a project when the segment contains real engagement with it: work on it, planning for it, or substantive discussion of its subject matter. A sustained discussion counts even when it sits inside a conversation about something else. Do NOT assign for a name in a list, an index, a passing clause, or generic methodology talk that merely echoes a project's mission wording.

Assign several projects when the segment genuinely engages several. That is expected and wanted -- these projects share a world, and one planning conversation can be real work on many of them at once.

Judge each project independently on the evidence in front of you.

STEP 3. Write your answers as JSON to:
${outPath}

Exact shape:
{"batch": ${batch}, "placements": [{"candidate_id": "...", "nexuses": ["golf", "insight"], "confidence": "high", "reason": "..."}, ...]}

Rules for the file:
- "nexuses" is a list of nexus ids copied EXACTLY from the roster. An empty list [] means the segment belongs to no registered project.
- Never invent a nexus id. Every id you write must appear in "projects".
- Include one entry for EVERY id in expected_candidate_ids, in that order.
- Do NOT invent candidate_ids. Check your list against expected_candidate_ids before writing; they must match exactly.
- "reason" names a concrete detail from THAT segment, under 15 words. For an empty list, say briefly what the segment is actually about.

STEP 4. You MUST return your answer by calling the StructuredOutput tool. Do not reply with prose. Report the counts you actually wrote, set wrote_file true only if the Write succeeded, and list in missing_ids any expected id you could not answer for.`
}

const items = (args || []).map(Number)
log(`sweeping ${items.length} batches`)

const results = await parallel(items.map((batch) => () =>
  agent(promptFor(batch), {
    label: `sweep:${pad(batch)}`,
    model: 'haiku',
    phase: 'Sweep',
    schema: SCHEMA,
  })
))

const ok = results.filter(Boolean)
return {
  batches: items.length,
  returned: ok.length,
  judged: ok.reduce((a, r) => a + (r.judged || 0), 0),
  placed: ok.reduce((a, r) => a + (r.placed || 0), 0),
  failed_batches: items.filter((_, i) => !results[i]),
  claimed_no_file: ok.filter((r) => !r.wrote_file).map((r) => r.batch),
}
