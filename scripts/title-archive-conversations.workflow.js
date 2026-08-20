export const meta = {
  name: 'title-archive-conversations',
  description: 'Give each multi-topic archived conversation a title that says what it is about',
  phases: [{ title: 'Title', detail: 'one Haiku agent per batch of conversations' }],
}

const SCHEMA = {
  type: 'object',
  properties: {
    batch: { type: 'number' },
    titled: { type: 'number' },
    wrote_file: { type: 'boolean' },
    missing_ids: { type: 'array', items: { type: 'string' } },
  },
  required: ['batch', 'titled', 'wrote_file'],
  additionalProperties: false,
}

const ROOT = '/Users/oracle/ora/data/conversation-projects'
const pad = (n) => String(n).padStart(3, '0')

function promptFor(batch) {
  return `You are titling archived conversations so their owner can recognise them in a list.

STEP 1. Read this file in full:
${ROOT}/title-input/batch-${pad(batch)}.json

Each entry has a conversation_id, the projects it belongs to, and "subjects" — one line describing each topical segment of that conversation, in order. Some conversations wander across many subjects; that is why they need a title.

STEP 2. Write ONE title per conversation.

A good title names the actual subject matter, the way a person would refer to the conversation later. Rules:
- 3 to 9 words. Never a full sentence, never trailing punctuation.
- Concrete and specific. Name the thing: "Wobble model double-slit appendix", not "Physics discussion".
- For a conversation spanning several subjects, name what ties them together, or the two or three that dominate: "Vault architecture, RAG tiering, and archiving policy". Do not simply repeat the first subject — that is the failure being corrected.
- Do not invent content. Everything in the title must be supported by the subjects given.
- Do not use the words "conversation", "discussion", "thread", "chat", "exploring", "various", or "topics" unless the conversation is genuinely about one of those things.
- Sentence case. Keep proper nouns and project names as written.
- If the subjects are genuinely uninformative, say what little is there rather than inventing: "Unlabelled code snippet" is better than a guess.

STEP 3. Write your titles as JSON to:
${ROOT}/title-output/batch-${pad(batch)}.json

Exact shape:
{"batch": ${batch}, "titles": [{"conversation_id": "...", "title": "..."}]}

Include one entry for EVERY id in expected_ids, in that order. Never invent a conversation_id — check your list against expected_ids before writing.

STEP 4. You MUST return your answer by calling the StructuredOutput tool. Do not reply with prose. Set wrote_file true only if the Write succeeded.`
}

const items = (args || []).map(Number)
log(`titling ${items.length} batches`)

const results = await parallel(items.map((batch) => () =>
  agent(promptFor(batch), { label: `title:${pad(batch)}`, model: 'haiku', phase: 'Title', schema: SCHEMA })
))

const ok = results.filter(Boolean)
return {
  batches: items.length,
  returned: ok.length,
  titled: ok.reduce((a, r) => a + (r.titled || 0), 0),
  failed_batches: items.filter((_, i) => !results[i]),
  claimed_no_file: ok.filter((r) => !r.wrote_file).map((r) => r.batch),
}
