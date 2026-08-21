export const meta = {
  name: 'discover-undocumented-work',
  description: 'Find named books, papers and projects in the archive that no registered project or Incubator artifact covers',
  phases: [{ title: 'Discover', detail: 'one Haiku agent per segment batch' }],
}

const SCHEMA = {
  type: 'object',
  properties: {
    batch: { type: 'number' },
    segments_read: { type: 'number' },
    works_found: { type: 'number' },
    wrote_file: { type: 'boolean' },
  },
  required: ['batch', 'segments_read', 'works_found', 'wrote_file'],
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

const KNOWN = `Registered projects and passions (43): AI Assisted Writing, American Jesus, American Judas, American King, Audio Diaries 1990s, Autism Acceptance, Diklis Chump, Divorce, Einstein Resonance, Executor Instructions, Expanding Awareness, Golf, Golf Course Design, Human Nexus, Image Generation, Incubator, Insight, Main Street Independent, Marketing, Obsidian, Ora, Ora AI App, Ora AI Org, Chokepoint Response, Ora Foundation, Framework Library, Knowledge Library, Pen Names, Photo Books James, Politics, Project Workshop, Prompt Engineering, Property, Publishing, Old Cypress Publishing, Quantum Mechanics, Real Estate Book, Relationships, Science, Technology, We Too, Writing, Writing Fiction.

Already documented in the vault Incubator (38): AHI Novel, Adventurous Mind, Angel Fallon Romance, Ashley Romance, Cosmology Preprint, Destiny Ministry, Disingenuous Bullshitters, Distribution Novel, Friendship Wisconsin, Hackers Novel, Hard Problem of Consciousness, How to Learn, Human Nexus White Paper / Extending Human Cognition, Internal Parliament Model, K-Shaped Economy Novel (Trumponomics Fiction), Lamrim Commentary, Mira and the Human Nexus, Moral Indictments, Opinion Inversion Engine, Oracle Afterlife Novel, Oracle Book, Parliament of Mind Books 1-3, Patent Salting / Prior Art Saboteur, Receipts-Based Argumentation, Shit-Testing the Tyrant, Spiritual Practice, Supreme Court, A Special Life (special-needs parenting), Divorce/Marriage Memoir, The Real American Communist Manifesto, Method Writing / Golden Shadow, Civilizational Collapse / Neurological Hits, The Vault memoir.`

function promptFor(batch) {
  const inPath = `${ROOT}/sweep-input-all/batch-${pad(batch)}.json`
  const outPath = `${ROOT}/discovery-output/batch-${pad(batch)}.json`
  return `You are searching an archive of the user's AI conversations for substantial creative or intellectual WORK that has no home yet.

STEP 1. Read this input file in full:
${inPath}
Use only its "segments" array — each has candidate_id, subject, and excerpts of the real conversation. Ignore its "projects" array.

STEP 2. Find every distinct named or clearly-identifiable WORK the user is developing: a book, a novel, a memoir, a white paper, an essay or article series, a named framework or methodology, a product, a service, a business, a website, or a research programme.

Report a work only when the user is genuinely DEVELOPING it — outlining, drafting, naming, structuring, planning, or arguing it out. Do NOT report:
- a topic merely discussed, analysed, or asked about;
- news commentary, political analysis, or personal conversation with no artifact being built;
- a passing idea with no development;
- generic AI/tooling questions.

This is ALREADY KNOWN and must NOT be reported:
${KNOWN}

Report a work even if it seems adjacent to something known, when it is plainly its own artifact with its own title, thesis, or structure — but say what it is adjacent to. When you are unsure whether it duplicates a known item, report it and set "possible_duplicate_of".

STEP 3. Write your findings as JSON to:
${outPath}

Exact shape:
{"batch": ${batch}, "works": [{
  "title": "the user's own name for it, or a precise descriptive title",
  "kind": "book|novel|memoir|paper|essay-series|framework|product|service|business|website|research",
  "description": "2-3 sentences: what it is, its thesis or structure",
  "development": "passing|early|moderate|advanced",
  "evidence_ids": ["candidate_id", ...],
  "quote": "one short verbatim phrase from the excerpts showing the user developing it",
  "possible_duplicate_of": "known item name, or empty string"
}]}

Rules:
- Every candidate_id in evidence_ids MUST come from this batch's segments. Never invent one.
- "quote" must be text that actually appears in the excerpts.
- An empty works list is a perfectly good answer and will be common. Do not manufacture findings.

STEP 4. You MUST return your answer by calling the StructuredOutput tool. Do not reply with prose. Set wrote_file true only if the Write succeeded.`
}

const items = (args || []).map(Number)
log(`discovery over ${items.length} batches`)

const results = await parallel(items.map((batch) => () =>
  agent(promptFor(batch), {
    label: `discover:${pad(batch)}`,
    model: 'haiku',
    phase: 'Discover',
    schema: SCHEMA,
  })
))

const ok = results.filter(Boolean)
return {
  batches: items.length,
  returned: ok.length,
  segments_read: ok.reduce((a, r) => a + (r.segments_read || 0), 0),
  works_found: ok.reduce((a, r) => a + (r.works_found || 0), 0),
  failed_batches: items.filter((_, i) => !results[i]),
  claimed_no_file: ok.filter((r) => !r.wrote_file).map((r) => r.batch),
}
