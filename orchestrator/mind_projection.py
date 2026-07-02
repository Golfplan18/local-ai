"""Self-spec → assistant-directives projection.

The MindSpec interview's MSI-Self mode produces a 4000–6000-word
*portrait* — how the user operates (commitment weights, near-enemy
patterns, constitution, mission, life context). A portrait injected into
the prompt mostly describes the user's psyche; it does not direct the
assistant. This module supplies the missing second-person transform: read
the self-spec, emit directives *to the assistant* — "here is what this
person reliably gets wrong; challenge accordingly," "deliver corrections
this way," "these are their red lines."

The transform is one model call (``model_dispatch.invoke_chat``, breadth
slot by default) followed by structural validation. The projection prompt
compiles each weight THROUGH its scale-anchor prose into a behavioral
directive — bare numbers are explicitly forbidden in the output, because
a number is only meaningful while its anchor definitions are in context
(true in the MSI authoring session, false in a runtime prompt, and
falsest on small local models).

Output sections (whitelist — unknown sections are dropped):

  ## What to Challenge Me On    — personalized failure-mode watchlist
  ## How to Deliver Pushback    — delivery calibration (e.g. face-saving
                                  framing for high-HUMILIATION users)
  ## My Red Lines               — constitutional commitments as standing
                                  rules the assistant must not help cross
  ## Mission Alignment          — weigh recommendations against the
                                  user's stated life-work; name drift
  ## Off Limits                 — LC-8 scope exclusions
  ## Private Context            — dependents / relationships / life
                                  context; injected ONLY in private or
                                  stealth conversations (boot.py's
                                  _filter_private_values gates on the
                                  conversation tag)

The projected mind.md = guided-wizard base (the user's saved wizard
answers when present, else the recommended defaults — this carries the
behavioral floor including the pushback-threshold calibration) + the
delta sections above, delimited by a provenance marker so wizard re-runs
preserve the projected block::

    <!-- ora-mind-projected: {"v": 1, "source": "...", "sha256": "...",
                              "projected_at": "..."} -->

The full self-spec is archived at ``~/ora/mindspec/self-spec.md`` and no
longer rides every pipeline prompt.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

PROJECTED_MARKER_PREFIX = "<!-- ora-mind-projected:"
PROJECTED_MARKER_VERSION = 1

# Section whitelist, in emission order. "Private Context" must match
# boot.py::PRIVATE_VALUES_HEADING (a unit test pins the pair).
ALLOWED_SECTIONS = [
    "What to Challenge Me On",
    "How to Deliver Pushback",
    "My Red Lines",
    "Mission Alignment",
    "Off Limits",
    "Private Context",
]

# Validation bounds for the model's delta output.
MIN_CHARS = 200
MAX_CHARS = 8000

PROJECTION_SYSTEM_PROMPT = """\
You convert a MindSpec self-specification (a portrait of how a specific \
person operates: commitment weights, near-enemy patterns, constitutional \
commitments, mission, life context) into ASSISTANT DIRECTIVES — \
instructions to an AI assistant that serves this person. The portrait \
describes the user; your output directs the assistant. Every line you \
write must be an actionable instruction to the assistant, phrased as an \
imperative.

Emit ONLY these markdown sections, in this order, each introduced by a \
level-2 heading (## ). Omit a section entirely when the spec gives no \
material for it:

## What to Challenge Me On
The personalized failure-mode watchlist. Derive it from high-weight and \
low-weight commitments and their near-enemy distinguishing marks. \
Examples of the transform: high APPROVAL -> "challenge my quick yeses; \
do not reward me with praise for agreeing with you"; high CONSISTENCY or \
SELF-IMAGE -> "watch for sunk-cost defenses of positions I have held \
publicly"; low WITNESS -> "tell me when my reasoning chain is arriving \
at the conclusion I wanted from the start"; high CRAFT with low COMFORT \
-> "push me to ship when polishing has stopped serving the work"; high \
NOVELTY -> "flag when I am abandoning a project for a shinier one"; high \
TRIBALISM -> "steelman the out-group position when I am reasoning along \
coalition lines"; low SKEPTICISM -> "demand sources before I run with a \
claim". 4-8 bullets, each traceable to the spec.

## How to Deliver Pushback
Delivery calibration only — WHEN to push back is governed elsewhere and \
is not yours to change. Derive from fear-family and social-family \
patterns: e.g. high HUMILIATION -> face-saving framing, make updating \
easy rather than cornering; low HUMILIATION -> blunt is fine; high \
FEROCITY tolerance -> match intensity. 1-3 bullets.

## My Red Lines
Constitutional commitments as standing rules for the assistant: e.g. \
constitutional TRUTH -> "if I ask you to write something misleading, \
refuse and say why"; constitutional HARMLESSNESS -> "flag plans whose \
costs fall on people not in the room". Only include genuinely \
constitutional items (pressure-tested, highest weight); 1-4 bullets.

## Mission Alignment
The user's primary mission in one line, then 1-2 directives to weigh \
recommendations against it and to name drift ("this serves X, not the \
book") when relevant.

## Off Limits
Domains or topics the spec excludes (scope exclusions): instruct the \
assistant not to probe or advise there. Omit if none.

## Private Context
Dependents, partner/relationship load, health or life-stage context that \
should shape advice (e.g. tradeoff weighting in work/life decisions), \
phrased as directives. This section is injected only into private \
conversations; still keep it factual and minimal.

Hard rules:
- NEVER emit numeric weights, scores, or library jargon (no "APPROVAL: \
8", no "near enemy", no family names). Compile every weight through its \
scale-anchor meaning into plain behavioral language.
- Anti-nag guard: open the What to Challenge Me On section with the \
single line "Apply these when the pattern actually appears — at most one \
such observation per response, and never as armchair analysis."
- No preamble, no closing remarks, no section not listed above.
- Total length 250-700 words.
"""


def _invoke_default(system_prompt: str, user_prompt: str, slot: str) -> str:
    try:
        from model_dispatch import invoke_chat
    except ImportError:
        from orchestrator.model_dispatch import invoke_chat
    return invoke_chat(system_prompt, user_prompt, slot=slot)


def _split_sections(markdown: str) -> list:
    """[(heading, body), ...] for each level-2 section in order."""
    parts = re.split(r"^## +(.+?)\s*$", markdown, flags=re.MULTILINE)
    # parts = [preamble, h1, body1, h2, body2, ...]
    out = []
    for i in range(1, len(parts) - 1, 2):
        out.append((parts[i].strip(), parts[i + 1].strip()))
    return out


def validate_directives(raw: str):
    """Normalize the model's delta output. Returns the cleaned markdown
    (whitelisted sections only, in canonical order) or None when the
    output is unusable (no allowed section, or out of length bounds)."""
    if not raw or not isinstance(raw, str):
        return None
    sections = {h: b for h, b in _split_sections(raw) if h in ALLOWED_SECTIONS and b}
    if not sections:
        return None
    kept = []
    for name in ALLOWED_SECTIONS:
        if name in sections:
            kept.append(f"## {name}\n\n{sections[name]}")
    cleaned = "\n\n".join(kept).strip()
    if not (MIN_CHARS <= len(cleaned) <= MAX_CHARS):
        return None
    return cleaned


def project_self_spec(spec_text: str, invoke=None, slot: str = "breadth"):
    """Run the projection model call and validate. Returns the cleaned
    directives markdown, or None on model failure / unusable output.
    ``invoke(system_prompt, user_prompt, slot)`` is injectable for tests."""
    if not spec_text or not spec_text.strip():
        return None
    invoke = invoke or _invoke_default
    try:
        raw = invoke(PROJECTION_SYSTEM_PROMPT, spec_text.strip(), slot)
    except Exception:
        return None
    return validate_directives(raw or "")


def _projected_marker(source: str, spec_text: str) -> str:
    payload = {
        "v": PROJECTED_MARKER_VERSION,
        "source": source,
        "sha256": hashlib.sha256(spec_text.encode("utf-8")).hexdigest()[:16],
        "projected_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    return PROJECTED_MARKER_PREFIX + " " + json.dumps(payload, sort_keys=True) + " -->"


def extract_projected_block(mind_content: str):
    """Return the projected block (marker + directives, verbatim) from an
    existing mind.md, or None. Used by the guided-wizard save path to
    preserve the projection across wizard re-runs."""
    if not mind_content:
        return None
    idx = mind_content.find(PROJECTED_MARKER_PREFIX)
    if idx == -1:
        return None
    return mind_content[idx:].strip()


def parse_projected_marker(mind_content: str):
    """The marker payload dict from a projected mind.md, or None."""
    if not mind_content:
        return None
    m = re.search(re.escape(PROJECTED_MARKER_PREFIX) + r"\s*(\{.*?\})\s*-->",
                  mind_content)
    if not m:
        return None
    try:
        payload = json.loads(m.group(1))
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def compose_projected_mind_md(directives_md: str, spec_text: str,
                              source: str, base_content: str = None) -> str:
    """Assemble the full mind.md: guided base + projected directives.

    ``base_content`` is an existing mind.md whose guided-wizard answers
    (provenance marker) should be preserved as the behavioral floor; when
    absent or unparseable, the wizard's recommended defaults are used —
    either way the base carries the fixed calibration lines (cooperative
    agreement, pushback threshold, instruction-following)."""
    try:
        import mind_guided as mg
    except ImportError:
        from orchestrator import mind_guided as mg
    answers, free_text = {}, {}
    parsed = mg.parse_marker(base_content or "")
    if parsed:
        answers = parsed.get("answers") or {}
        free_text = parsed.get("free_text") or {}
    try:
        base = mg.compose(answers, free_text)
    except ValueError:
        base = mg.compose({}, {})
    return (
        base.rstrip()
        + "\n\n"
        + _projected_marker(source, spec_text)
        + "\n\n"
        + "*The sections below were derived from your MindSpec "
        + "self-specification (assistant-directives projection). Re-run "
        + "the projection after revising the self-spec; the guided-setup "
        + "sections above are preserved independently.*"
        + "\n\n"
        + directives_md.strip()
        + "\n"
    )
