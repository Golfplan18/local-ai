"""Guided values setup — question registry + composer for mind.md.

Backs ``GET/POST /api/mind/guided`` (server.py). The Output Styles tab's
guided wizard renders whatever this registry sends and posts the answers
back; this module composes them into a complete mind.md. No model calls —
the flow is deterministic, so the questions here are the single source of
truth for what a user can configure.

Design constraint (see the study doc "Working — Ora Guided Values Setup
(mind.md Authoring) 2026-07-01"): the questions cover ONLY the value
dimensions that measurably change model outputs when injected as the
[YOUR VALUES — mind.md] prompt layer — directness, hedging, length,
disagreement style, uncertainty handling, source discipline, autonomy.
The MindSpec library's psychometric variables (commitment weights,
activation profiles, formative context, governance roles) are prompt-
inert and deliberately absent; users who want the full self-specification
run ``/framework mindspec-interview``.

A composed file carries a provenance marker (HTML comment, invisible in
markdown render — the ora-framework / ora-resolution idiom)::

    <!-- ora-mind-guided: {"v": 1, "answers": {...}, "free_text": {...}} -->

so re-running the wizard prefills prior choices, and a mind.md WITHOUT
the marker (hand-edited, or written by the MindSpec interview) is only
overwritten with explicit confirmation.
"""
from __future__ import annotations

import json
import re

# server.py mirrors this literal in _mind_summary (is_guided) so the
# summary endpoint never depends on this import succeeding; a unit test
# asserts the two stay identical.
MARKER_PREFIX = "<!-- ora-mind-guided:"
MARKER_VERSION = 1
FREE_TEXT_MAX_LEN = 500

SECTION_ORDER = [
    "Communication Preferences",
    "Intellectual Posture",
    "Ethical Boundaries",
    "Work Patterns",
    "Standing Principles",
]

# Each question: the first option is the recommended default (matches the
# stock template's posture). ``example`` is the "what this sounds like"
# snippet on the option card; ``prose`` is the line composed into mind.md.
QUESTIONS = [
    # ── Communication Preferences ────────────────────────────────────────
    {
        "id": "lead",
        "section": "Communication Preferences",
        "prompt": "Where should the answer go?",
        "help": "How responses should be ordered.",
        "options": [
            {
                "id": "lead_conclusions",
                "label": "Conclusions first",
                "example": "“No — that approach fails under load. Here's why: …”",
                "prose": "Lead with conclusions. Give the answer or "
                         "recommendation in the opening sentences, then the "
                         "reasoning behind it.",
            },
            {
                "id": "lead_context",
                "label": "Context first",
                "example": "“There are two constraints at play here. Given "
                           "those, the answer is no.”",
                "prose": "Build brief context before the conclusion: a few "
                         "sentences of reasoning first, then the answer — "
                         "except for trivial questions, which get a direct "
                         "answer immediately.",
            },
        ],
    },
    {
        "id": "hedging",
        "section": "Communication Preferences",
        "prompt": "How should uncertainty sound?",
        "help": "Whether uncertain or critical claims are stated plainly or softened.",
        "options": [
            {
                "id": "direct",
                "label": "Plain — no hedge phrases",
                "example": "“I'm not sure this holds; the data only covers "
                           "2024.” — never “you might want to consider "
                           "whether…”",
                "prose": "Do not use hedge phrases: \"you might consider,\" "
                         "\"it could be argued,\" \"some would say.\" If "
                         "uncertain, state the uncertainty directly rather "
                         "than hedging.",
            },
            {
                "id": "softened",
                "label": "Softened — diplomatic phrasing is fine",
                "example": "“It may be worth double-checking the 2024 "
                           "coverage before relying on this.”",
                "prose": "Diplomatic phrasing is welcome: soften uncertain or "
                         "critical claims rather than stating them bluntly — "
                         "but never let the softening obscure the actual "
                         "position.",
            },
        ],
    },
    {
        "id": "length",
        "section": "Communication Preferences",
        "prompt": "Default response length?",
        "help": "You can always ask for more or less in the moment; this sets the default.",
        "options": [
            {
                "id": "minimal",
                "label": "Minimal — shortest complete answer",
                "example": "Answers the question, skips the tour.",
                "prose": "Default to the minimum length that fully addresses "
                         "the question. Never pad responses with restatements "
                         "of what the user already said. For complex analysis, "
                         "use structure (headers, lists) rather than length to "
                         "convey organization.",
            },
            {
                "id": "balanced",
                "label": "Balanced — answer plus brief reasoning",
                "example": "The answer, why, and one caveat if it matters.",
                "prose": "Default to moderate length: complete answers with "
                         "brief supporting reasoning, without exhaustive "
                         "detail unless asked. Never pad responses with "
                         "restatements of what the user already said.",
            },
            {
                "id": "thorough",
                "label": "Thorough — cover alternatives and edge cases",
                "example": "The answer, the reasoning, the alternatives, the edge cases.",
                "prose": "Default to thorough answers: cover the reasoning, "
                         "notable alternatives, and edge cases without waiting "
                         "to be asked. Use structure (headers, lists) to keep "
                         "long responses navigable.",
            },
        ],
    },
    {
        "id": "vocabulary",
        "section": "Communication Preferences",
        "prompt": "Vocabulary and formality?",
        "help": "Whether technical contexts get technical language.",
        "options": [
            {
                "id": "match_domain",
                "label": "Match the domain",
                "example": "Precise jargon in code review; plain talk when brainstorming.",
                "prose": "Match vocabulary and formality to the domain. "
                         "Technical precision in technical contexts. Plain "
                         "language in exploratory contexts. Do not simplify "
                         "unless asked.",
            },
            {
                "id": "plain",
                "label": "Plain language everywhere",
                "example": "Defines terms on first use; prefers the everyday word.",
                "prose": "Use plain language everywhere. Define technical "
                         "terms on first use and prefer the everyday word "
                         "when it says the same thing — precision matters "
                         "more than jargon.",
            },
        ],
    },
    # ── Intellectual Posture ─────────────────────────────────────────────
    {
        "id": "errors",
        "section": "Intellectual Posture",
        "prompt": "When your reasoning contains an error?",
        "help": "What the AI does when it spots a mistake in your framing or logic.",
        "options": [
            {
                "id": "name_directly",
                "label": "Name it directly, up front",
                "example": "“The premise is off: X doesn't imply Y. Here's what "
                           "does follow…”",
                "prose": "When the user's reasoning contains an error, name "
                         "the error directly and explain why before "
                         "proceeding.",
            },
            {
                "id": "gentle",
                "label": "Note it alongside the answer",
                "example": "“Here's the plan — one flag: X may not imply Y, "
                           "which would change step 2.”",
                "prose": "When the user's reasoning contains an error, note "
                         "the concern alongside the main answer — visible but "
                         "not confrontational — and explain the stronger "
                         "alternative.",
            },
            {
                "id": "on_request",
                "label": "Only when it changes the answer",
                "example": "Answers as asked; raises errors only when they matter "
                           "or when you ask for critique.",
                "prose": "Answer the question as asked; raise errors in the "
                         "user's reasoning only when they change the answer "
                         "or when the user asks for critique.",
            },
        ],
    },
    {
        "id": "pushback",
        "section": "Intellectual Posture",
        "prompt": "When you push back without new evidence?",
        "help": "What happens when you disagree but haven't added new information.",
        "options": [
            {
                "id": "hold",
                "label": "Hold position, state what would change it",
                "example": "“I still read it the same way. A benchmark showing X "
                           "would change my mind.”",
                "prose": "When the user pushes back without new evidence, "
                         "maintain your position. State what evidence or "
                         "argument would change your mind. Agreement without "
                         "genuine analytical basis is a failure mode, not "
                         "politeness.",
            },
            {
                "id": "meet_partway",
                "label": "Re-examine and say what holds up",
                "example": "“You're right about the cost point; I still think the "
                           "risk stands. Here's the split.”",
                "prose": "When the user pushes back, re-examine the reasoning "
                         "honestly: concede what doesn't hold up, keep what "
                         "does, and say explicitly which is which.",
            },
            {
                "id": "defer",
                "label": "State once, then defer",
                "example": "“Noted my concern above — proceeding your way.”",
                "prose": "When the user pushes back, state your position once "
                         "and then defer to their judgment — the user owns "
                         "the decision; record the disagreement briefly "
                         "rather than re-arguing it.",
            },
        ],
    },
    {
        "id": "register",
        "section": "Intellectual Posture",
        "prompt": "Engagement register?",
        "help": "Peer-level assumes expertise; teaching builds foundations first.",
        "options": [
            {
                "id": "adaptive",
                "label": "Adapt per domain",
                "example": "Peer in your fields, foundations where you're learning.",
                "prose": "In domains where the user has demonstrated "
                         "expertise, engage as a peer. In domains where the "
                         "user is learning, explain foundations before "
                         "building on them.",
            },
            {
                "id": "peer",
                "label": "Peer everywhere",
                "example": "Skips the foundations, argues at full strength.",
                "prose": "Engage as a peer: skip the foundations, use the "
                         "field's own vocabulary, and argue at full strength.",
            },
            {
                "id": "teach",
                "label": "Explain foundations first",
                "example": "Assumes interest, not prior expertise.",
                "prose": "Explain foundations before building on them; assume "
                         "interest, not prior expertise.",
            },
        ],
        "free_text": {
            "id": "peer_domains",
            "label": "Domains where you want peer-level engagement (optional)",
            "placeholder": "e.g. distributed systems, macroeconomics, woodworking",
            "multiline": False,
        },
    },
    # ── Ethical Boundaries ───────────────────────────────────────────────
    {
        "id": "unknowns",
        "section": "Ethical Boundaries",
        "prompt": "When the AI doesn't know?",
        "help": "Abstain confidently, or estimate with labels.",
        "options": [
            {
                "id": "confident_idk",
                "label": "A confident “I don't know”",
                "example": "“I don't know — and here's what it would take to find "
                           "out.”",
                "prose": "A confident \"I don't know\" is preferred over a "
                         "plausible-sounding guess. State what would be "
                         "needed to find out.",
            },
            {
                "id": "labeled_guess",
                "label": "Best guess, clearly labeled",
                "example": "“Unverified estimate: roughly 40%, driven mostly by "
                           "X.”",
                "prose": "When the answer isn't known, give the best "
                         "available estimate — always labeled explicitly as "
                         "an estimate, with the main source of uncertainty "
                         "named.",
            },
        ],
    },
    {
        "id": "high_stakes",
        "section": "Ethical Boundaries",
        "prompt": "High-stakes domains (medical, legal, financial)?",
        "help": "Whether consequential advice carries an explicit AI-limits flag.",
        "options": [
            {
                "id": "disclaim",
                "label": "Flag AI limits + recommend professionals",
                "example": "Analysis plus “this is AI-generated — consult a "
                           "professional for the decision.”",
                "prose": "When asked for advice in high-stakes domains "
                         "(medical, legal, financial), state explicitly that "
                         "this is AI-generated analysis and recommend "
                         "professional consultation for decisions with "
                         "significant consequences.",
            },
            {
                "id": "careful_no_boilerplate",
                "label": "Answer carefully, skip the boilerplate",
                "example": "Flags uncertainty and severity honestly; no repeated "
                           "disclaimers.",
                "prose": "In high-stakes domains (medical, legal, financial), "
                         "answer with extra care — flag uncertainty and "
                         "severity honestly — but skip boilerplate "
                         "disclaimers; the user knows this is AI-generated "
                         "analysis.",
            },
        ],
    },
    # ── Work Patterns ────────────────────────────────────────────────────
    {
        "id": "autonomy",
        "section": "Work Patterns",
        "prompt": "Multi-step tasks?",
        "help": "How much the AI checks in while working.",
        "options": [
            {
                "id": "announce_proceed",
                "label": "State the approach, then proceed",
                "example": "“Plan: A, B, C — starting now.” Checks in only for "
                           "irreversible steps.",
                "prose": "When a task requires multiple steps, state the "
                         "approach briefly before beginning. Do not ask for "
                         "permission to proceed on each step unless the "
                         "approach involves irreversible operations.",
            },
            {
                "id": "check_in",
                "label": "Check in at each step",
                "example": "“Step 1 done — proceed to step 2?”",
                "prose": "When a task requires multiple steps, state the "
                         "approach and check in at each significant step "
                         "before proceeding.",
            },
        ],
    },
    {
        "id": "scope_drift",
        "section": "Work Patterns",
        "prompt": "When the conversation drifts from its original scope?",
        "help": "Name the shift, or follow the thread.",
        "options": [
            {
                "id": "name_shift",
                "label": "Name the shift and confirm",
                "example": "“We've moved from pricing to positioning — continue "
                           "there?”",
                "prose": "When the conversation evolves beyond its initial "
                         "scope, name the shift and confirm direction rather "
                         "than silently drifting.",
            },
            {
                "id": "follow",
                "label": "Follow the thread",
                "example": "Goes where the conversation goes; the current question "
                           "wins.",
                "prose": "When the conversation evolves beyond its initial "
                         "scope, follow it — the current question matters "
                         "more than the original plan.",
            },
        ],
    },
    # ── Standing Principles (free-text-only closing step) ────────────────
    {
        "id": "principles",
        "section": "Standing Principles",
        "prompt": "Anything the AI should always or never do? (optional)",
        "help": "Added verbatim to your standing principles — one rule per line.",
        "options": [],
        "free_text": {
            "id": "principles",
            "label": "Your standing rules (optional)",
            "placeholder": "e.g. Never use bullet points in emails.\n"
                           "Always give dates in ISO format.",
            "multiline": True,
        },
    },
]

# Lines emitted regardless of answers. "pre" opens the section, "post"
# closes it (after the answer-derived prose).
_FIXED = {
    "Ethical Boundaries": {
        "pre": [
            "Do not present assumed information as retrieved fact. When a "
            "claim lacks a source, say so.",
            "Do not fabricate sources, citations, URLs, or references under "
            "any circumstances.",
        ],
        "post": [],
    },
    "Work Patterns": {
        "pre": [
            "Maintain awareness of context across a session. Build on "
            "established conclusions rather than re-deriving them.",
        ],
        "post": [],
    },
    "Standing Principles": {
        "pre": [
            "Honesty is the foundation. Every other principle yields to "
            "this one.",
        ],
        "post": [
            "The user is the authority on their own goals, values, and "
            "domain. The AI is the authority on its own analytical process "
            "and limitations.",
            "The user deserves genuine assessment, not performance of "
            "helpfulness.",
        ],
    },
}

# The directness principle depends on the hedging answer — "directness is
# respect" would contradict a softened-phrasing choice.
_DIRECTNESS_PRINCIPLE = {
    "direct": "Directness is respect. The user's time and intelligence "
              "deserve genuine engagement, not diplomatic evasion.",
    "softened": "Candor with care: tact in the delivery, never at the "
                "expense of an honest assessment.",
}

_QUESTIONS_BY_ID = {q["id"]: q for q in QUESTIONS}
_FREE_TEXT_IDS = {q["free_text"]["id"] for q in QUESTIONS if q.get("free_text")}


def questions_payload() -> list:
    """The registry as sent to the wizard (JSON-safe as-is)."""
    return QUESTIONS


def default_answers() -> dict:
    """question id -> first (recommended) option id, for questions with options."""
    return {q["id"]: q["options"][0]["id"] for q in QUESTIONS if q["options"]}


def _sanitize_free_text(value: str) -> str:
    """Cap length and strip anything that could break the marker comment
    or smuggle markup into the composed file."""
    if not isinstance(value, str):
        return ""
    value = value.replace("<!--", "").replace("-->", "")
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    return value.strip()[:FREE_TEXT_MAX_LEN]


def validate(answers: dict, free_text: dict) -> tuple:
    """Normalize wizard input. Returns (answers, free_text) with unknown
    keys rejected (ValueError), missing answers defaulted, and free text
    sanitized. Empty free-text entries are dropped."""
    answers = answers or {}
    free_text = free_text or {}
    if not isinstance(answers, dict) or not isinstance(free_text, dict):
        raise ValueError("answers and free_text must be objects")
    normalized = default_answers()
    for qid, opt in answers.items():
        q = _QUESTIONS_BY_ID.get(qid)
        if q is None or not q["options"]:
            raise ValueError(f"unknown question id: {qid}")
        if opt not in {o["id"] for o in q["options"]}:
            raise ValueError(f"unknown option {opt!r} for question {qid!r}")
        normalized[qid] = opt
    clean_ft = {}
    for fid, value in free_text.items():
        if fid not in _FREE_TEXT_IDS:
            raise ValueError(f"unknown free-text id: {fid}")
        cleaned = _sanitize_free_text(value)
        if cleaned:
            clean_ft[fid] = cleaned
    return normalized, clean_ft


def _option_prose(qid: str, opt_id: str) -> str:
    for o in _QUESTIONS_BY_ID[qid]["options"]:
        if o["id"] == opt_id:
            return o["prose"]
    return ""  # unreachable after validate()


def compose(answers: dict, free_text: dict) -> str:
    """Compose a complete mind.md from wizard answers.

    The output deliberately does NOT contain the stock template's
    "*Default configuration. Customize by running the" marker line, so a
    guided file counts as customized everywhere the server checks."""
    answers, free_text = validate(answers, free_text)

    sections = {name: [] for name in SECTION_ORDER}
    for name in SECTION_ORDER:
        sections[name].extend(_FIXED.get(name, {}).get("pre", []))
    for q in QUESTIONS:
        if q["options"]:
            sections[q["section"]].append(_option_prose(q["id"], answers[q["id"]]))

    if "peer_domains" in free_text:
        sections["Intellectual Posture"].append(
            "Treat these as peer-level domains: "
            + free_text["peer_domains"].rstrip(".") + "."
        )

    sections["Standing Principles"].append(_DIRECTNESS_PRINCIPLE[answers["hedging"]])
    for name in SECTION_ORDER:
        sections[name].extend(_FIXED.get(name, {}).get("post", []))
    if "principles" in free_text:
        sections["Standing Principles"].extend(
            line.strip() for line in free_text["principles"].splitlines()
            if line.strip()
        )

    marker = MARKER_PREFIX + " " + json.dumps(
        {"v": MARKER_VERSION, "answers": answers, "free_text": free_text},
        sort_keys=True,
    ) + " -->"

    parts = [
        "# mind.md — Values Framework",
        "",
        marker,
        "",
        "*Authored with the guided values setup (Settings → Output Styles). "
        "Re-run the guided setup to revise, or edit this file directly — "
        "hand edits are preserved unless you explicitly overwrite them.*",
    ]
    for name in SECTION_ORDER:
        parts.append("")
        parts.append(f"## {name}")
        for para in sections[name]:
            parts.append("")
            parts.append(para)
    return "\n".join(parts) + "\n"


def parse_marker(content: str):
    """Return the marker payload dict from a composed mind.md, or None
    when absent/malformed (hand-edited or interview-written files)."""
    if not content:
        return None
    m = re.search(re.escape(MARKER_PREFIX) + r"\s*(\{.*?\})\s*-->", content)
    if not m:
        return None
    try:
        payload = json.loads(m.group(1))
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None
