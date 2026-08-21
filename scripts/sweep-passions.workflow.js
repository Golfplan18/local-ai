export const meta = {
  name: 'sweep-unbound-into-passions',
  description: 'File conversations that landed under no project against the 12 defined Passions',
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
  const inPath = `${ROOT}/sweep-input-unbound/batch-${pad(batch)}.json`
  const outPath = `${ROOT}/sweep-output-unbound/batch-${pad(batch)}.json`
  return `You are filing archived conversation segments under the Passions they belong to.

STEP 1. Read this input file in full:
${inPath}

It contains:
- "projects": the roster of the user's 12 defined Passions, each with a nexus id, a name, what it is about, and its objectives. These are the ONLY valid nexus ids.
- "expected_candidate_ids": the EXACT list of segment ids you must return an answer for. Every one, no more, no fewer.
- "segments": each has candidate_id, subject (a one-line description of that segment), turn_range, and excerpts of the actual conversation text.

STEP 2. For EACH segment, decide which Passions it belongs to. Zero, one, or several.

Every segment here already failed to place under any of the user's 43 projects, so a Project's standard has already been applied and found wanting. A PASSION is a different thing and takes a different standard.

A Passion is an ongoing area of exploration with NO finite deliverable. It is not a project that produces an artifact; it is a subject the user lives in. Reading, tracking, analysing and asking about its subject matter IS the Passion being pursued, not evidence that nothing is happening. The Golf passion's stated practice is to play and observe golf attentively; the Politics passion's is to track political events and claims through source-backed notes. Sustained engagement with the subject counts, even when nothing is being built and no artifact results.

Look at each roster entry's "about", "objectives", "practices" and "directions_of_travel" — the practices in particular say what living that Passion looks like.

ASSIGN when the segment is real engagement with the Passion's subject: analysis, tracking, reading, questioning, working through it, or personal experience of it.
DO NOT ASSIGN for:
- greetings, test messages, "no image attached" notices, and other administrative exchanges;
- a bare single-fact lookup with no engagement ("what time is the game");
- technical support for an unrelated tool;
- a subject that simply is not any of these Passions.

Many segments here genuinely belong nowhere and an empty list is the right answer for them. But do not withhold a Passion from a segment that plainly sits inside its subject just because nothing is being produced.

Assign several Passions when the segment genuinely engages several.

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
