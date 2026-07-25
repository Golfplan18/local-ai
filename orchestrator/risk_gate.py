"""Execution Review Phase 2 — risk gate + two clocks.

Two decisions on two clocks (spec §6):

  * BEFORE the run — a conservative, user-overridable ``risk_tier``
    (light | standard | high-risk | irreversible). Deterministic: a
    turn-head pattern table over the raw input (Stage A) plus an optional
    ``## RISK TIER`` mode heading (Stage B). No model call.
  * AFTER the run — ``route_observed`` signals folded from the Phase 1
    tool-event log (what the turn mutated / read), recorded for the Phase 4
    lane router. Post-hoc routing is permitted only in reversible tiers;
    ``irreversible`` is held BEFORE the executor runs (the hard boundary).

This module is the single home for the tier vocabulary, the classifier, the
inline ``/risk`` parse, the task-approval fingerprint + token helpers, the
task-gate conversation-as-state marker, and the after-clock fold. It leans
on Phase 1's ``tool_events`` for the approval-token store and the max-fold
ordering helpers (no parallel machinery).

PROVISIONAL tuning surfaces (flagged, not empirically calibrated): the
Stage-A pattern table, the default tier, the fingerprint normalization, and
the task-token TTL.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone


def now_ts() -> str:
    """A turn-start timestamp comparable to tool_events event ``ts`` (both
    ``datetime.now(timezone.utc).isoformat()``). Used to scope the
    route_observed fold to THIS turn's events on the global sink."""
    return datetime.now(timezone.utc).isoformat()

try:
    import tool_events as _te
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import tool_events as _te
    from orchestrator import runtime_paths as _rp


# ── Tier vocabulary + ordering ──────────────────────────────────────────────
TIERS = ("light", "standard", "high-risk", "irreversible")
_TIER_RANK = {t: i for i, t in enumerate(TIERS)}
# Natural-word aliases users type (the hold prompt says "/risk <tier>").
_TIER_ALIASES = {"high": "high-risk", "highrisk": "high-risk",
                 "high_risk": "high-risk", "irreversable": "irreversible",
                 "irrev": "irreversible", "low": "light", "trivial": "light"}


def _normalize_tier(word: str) -> str:
    w = (word or "").strip().lower()
    return _TIER_ALIASES.get(w, w)

# The default for ordinary dispatched/executor turns (judge condition 1:
# standard, not light). Light is reserved for trivial/self-contained text
# turns (the bypass-to-direct path), runtime/meta commands, and explicit
# override. PROVISIONAL.
DEFAULT_TIER = "standard"
# The floor a failed classification falls to — never a silent fail-open to
# light (spec §7 fail-closed; judge condition 6 for criteria failure).
FAILSAFE_TIER = "high-risk"

# Task-approval token TTL: long enough to resume a held turn, short enough
# not to blanket future turns. PROVISIONAL.
TASK_TOKEN_TTL_S = 900
TASK_ACTION = "task_execute"


# ── Source-read signal (Execution Review Phase 3, spec §6 signal 2 / §15) ────
# The coarse over-approximation "did the output make claims about material it
# read?" — the §6 second dispatch signal, folded from the Phase 1 tool-event
# log after the run, EXCLUDING local_context_read (§7). This is deliberately
# distinct from the Phase 2 raw `reads_present` (any read at all).
#
# Judge design-gate conditions honored here:
#   (1) an explicit source-action ALLOWLIST, and only reads that ACTUALLY RAN
#       count — exit.ok truthy and gate decision allowed/approved — never
#       internal telemetry (task_tier / acceptance_criteria / route_observed /
#       task_execute / model_call) or blocked/queued gate attempts.
#   (2) the recorded route_observed event's sensitivity reflects the folded max,
#       AND source_candidate_reads is a public-safe shape (a read's `what`
#       descriptor rides in only when that read's own sensitivity is public),
#       because _redact_for_record does NOT recurse into route_signals.
# Precise per-read source_read labelling + the claim-to-source map (§4) are
# deferred to the provenance lane (Phase 8); this is the coarse routing signal.

# Strong channels: contact reality outside the returned artifact. A successful
# read here + substantive output ⇒ source read (over-route is safe, §6). Never
# subject to any local read-vs-context tie-break.
_ALWAYS_SOURCE_ACTIONS = frozenset({
    "web_fetch", "web_search", "knowledge_search", "rag_read"})
# Ambiguous local reads: read-to-edit (context) vs read-to-describe (source)
# can't be split without the output. Judge answer Q1 = A: over-approximate to
# source (no per-target read/write tie-break in Phase 3). Shell reads are folded
# via their bash:<profile> action + mutability==read (judge Q2: no dispatcher
# reads[] change now).
_AMBIGUOUS_LOCAL_ACTIONS = frozenset({
    "file_read", "search_files", "list_directory"})
# Internal telemetry / gate bookkeeping — these carry mutability==read but are
# NOT reads of source material. Excluded explicitly (belt; the allowlist above
# already excludes them by omission).
_NON_SOURCE_ACTIONS = frozenset({
    "task_tier", "acceptance_criteria", "route_observed", TASK_ACTION,
    "model_call", "credential_store"})

# Below this many characters the output is treated as a non-deliverable (empty /
# bare acknowledgement / status echo) and does NOT count as "making claims".
# PROVISIONAL (flagged, not empirically calibrated): biased low so the safe
# (over-route) direction dominates — a short grounded answer should still route
# out of pure text review. Calibrate against real turns.
_MIN_SUBSTANTIVE_OUTPUT_CHARS = 24

# Bound the provenance-detail list carried in the route_observed event so a
# very heavy turn (100+ successful source reads) can't push the event past
# tool_events.MAX_LINE_BYTES (8 KB) — which would drop the WHOLE route_signals
# block (incl. the load-bearing source_read_suspected boolean) via the
# truncation keep-set. The boolean/channels are computed from booleans, not
# this list, so capping never affects routing; it only bounds the Phase-8
# provenance pointer, and a capped fold is FLAGGED (source_candidate_reads_
# truncated), never silent — Phase 8 rebuilds the full map from the per-event
# log anyway. PROVISIONAL.
_MAX_SOURCE_CANDIDATES = 64


def _source_read_kind(ev: dict) -> str | None:
    """Classify one tool-event as a source-eligible read (judge condition 1).
    Returns 'always' | 'ambiguous' | None. A read must have ACTUALLY RUN
    (exit.ok truthy) and been ALLOWED (gate decision not blocked/queued);
    internal telemetry and gate bookkeeping never qualify."""
    action = ev.get("action", "") or ""
    if action in _NON_SOURCE_ACTIONS:
        return None
    if ev.get("mutability") != "read":
        return None
    if not (ev.get("exit") or {}).get("ok"):
        return None  # never ran, or errored → not a source read
    dec = (ev.get("gate") or {}).get("decision")
    if dec is not None and dec not in ("allowed", "approved"):
        return None  # blocked / queued gate attempt → never ran
    if action in _ALWAYS_SOURCE_ACTIONS:
        return "always"
    if action in _AMBIGUOUS_LOCAL_ACTIONS or action.startswith("bash:"):
        return "ambiguous"
    # Instrumented MCP reads (event=='mcp' + a server-declared mutability:read):
    # opaque external source contact (boundary_only — Ora can't see WHAT was
    # read, and MCP events carry no reads[]). Classified STRONG (like web /
    # knowledge / rag) because a read-only connector (docs / database / search
    # server) reaches external reality — so a terse grounded answer after it
    # ("Yes.") must still suspect, not be dropped by the substantive-output
    # floor (the unsafe under-route direction, §6).
    if ev.get("event") == "mcp":
        return "always"
    return None


def _public_safe_candidates(ev: dict) -> list[dict]:
    """Public-safe source-read descriptors from an event's reads[] (judge
    condition 2). A read's `what` (a path / URL / query) is included ONLY when
    the event's own sensitivity is public — deferring to the existing per-event
    classification — so a private/sensitive path never rides into the
    public-shaped route_observed summary. action / where / content_hash / chars
    are tool-name / enum / truncated-hash / count values and are always safe."""
    action = ev.get("action", "") or ""
    sens = ev.get("sensitivity", "private")
    out = []
    for r in (ev.get("reads") or []):
        if not isinstance(r, dict):
            continue
        cand = {"action": action, "where": r.get("where")}
        if r.get("content_hash"):
            cand["content_hash"] = r["content_hash"]
        if r.get("chars") is not None:
            cand["chars"] = r["chars"]
        if sens == "public" and r.get("what"):
            cand["what"] = r["what"]  # already scrubbed at write for public
        out.append(cand)
    return out


def _output_is_substantive(output_text: str | None) -> bool:
    """Coarse 'makes claims' proxy: a real deliverable, not empty / bare ack /
    status echo. PROVISIONAL threshold (_MIN_SUBSTANTIVE_OUTPUT_CHARS)."""
    if not output_text:
        return False
    return len(output_text.strip()) >= _MIN_SUBSTANTIVE_OUTPUT_CHARS


def tier_max(*tiers: str) -> str:
    """Highest (most conservative) tier among the arguments; unknowns and
    None are ignored. Empty → DEFAULT_TIER."""
    ranked = [t for t in tiers if t in _TIER_RANK]
    if not ranked:
        return DEFAULT_TIER
    return max(ranked, key=_TIER_RANK.get)


def tier_at_least(tier: str, floor: str) -> bool:
    return _TIER_RANK.get(tier, -1) >= _TIER_RANK.get(floor, 999)


def is_tier(value) -> bool:
    return value in _TIER_RANK


# ── Stage A — turn-head pattern floors (PROVISIONAL) ────────────────────────
# Seeded from the Phase 1 gate vocabulary (bash irreversible flags, curl/wget
# write detection, credential/secret patterns). Extend from observed gate
# events, not guesswork. Word-boundary anchored to avoid substring hits
# (e.g. "deploy" must not fire inside "redeployment-history.md" discussion —
# the intent verbs pair with an object cue).
_IRREVERSIBLE_PATTERNS = [
    r"\bdeploy(?:ing|ment)?\b.*\b(prod|production|live|release)\b",
    r"\b(prod|production)\b.*\bdeploy",
    r"\b(ship|ships|shipping|shipped|roll(?:ing)?\s+out|cut)\b.*\b(prod|production|release|live)\b",
    r"\bcut\b.*\brelease\b",
    r"\bpublish(?:ing|ed)?\b",
    r"\bgo[- ]?live\b",
    # "send/email/e-mail/text/dm/message" as the action verb + a recipient/
    # channel cue anywhere (order-independent), so "email the customers" and
    # "send this to the list" both fire.
    r"\b(send|sending|sent|email|e-mail|emailing|text|dm|message|blast)\b.*"
    r"\b(email|e-mail|sms|newsletter|campaign|customers?|clients?|list|"
    r"subscribers?|everyone|recipients?|inbox|out)\b",
    r"\b(newsletter|campaign)\b.*\b(send|blast|out|launch)\b",
    r"\bgit\s+push\b.*(--force|-f\b|force)",
    r"\bforce[- ]?push\b",
    # Payments / money movement — broadened verbs incl. wire/send money.
    r"\b(charge|payment|pay|payout|invoice|refund|transfer|wire|remit)\b.*"
    r"\b(card|customer|account|vendor|\$|usd|dollars?|money|funds?)\b",
    r"\b(wire|send|transfer)\b.*\b(\$|money|funds?|payment)\b",
    r"\bdelete\b.*\b(remote|production|prod|origin|branch on|bucket|database|records?)\b",
    r"\b(drop|truncate)\s+(table|database|schema)\b",
    r"\bdns\b.*\b(record|change|update|cutover)\b",
    r"\bmerge\b.*\b(to|into)\b.*\b(main|master|production)\b.*\b(deploy|release|ship)\b",
    r"\brm\s+-rf\b.*\b(remote|prod|production|/|~)\b",
]
_EXTERNAL_WRITE_PATTERNS = [
    r"\bpush\b.*\b(remote|origin|branch|upstream)\b",
    r"\bopen\b.*\b(pr|pull request|issue)\b",
    r"\b(create|update|delete|post)\b.*\b(api|endpoint|record|row|webhook)\b",
    r"\bwrite\b.*\b(database|db|table|s3|bucket|remote)\b",
    r"\bstaging\b.*\bdeploy",
    r"\bupload\b.*\b(to|remote|s3|bucket|cdn)\b",
    r"\bcommit\b.*\band\b.*\bpush\b",
]

_IRREVERSIBLE_RE = [re.compile(p, re.IGNORECASE) for p in _IRREVERSIBLE_PATTERNS]
_EXTERNAL_WRITE_RE = [re.compile(p, re.IGNORECASE) for p in _EXTERNAL_WRITE_PATTERNS]


def stage_a_floor(text: str) -> tuple[str | None, list[str]]:
    """Deterministic pattern floor over raw input. Returns (floor|None,
    matched_pattern_labels). Irreversible wins over external-write."""
    text = text or ""
    fired = []
    floor = None
    for rx in _IRREVERSIBLE_RE:
        if rx.search(text):
            fired.append(f"irreversible:{rx.pattern[:40]}")
            floor = "irreversible"
    if floor != "irreversible":
        for rx in _EXTERNAL_WRITE_RE:
            if rx.search(text):
                fired.append(f"high-risk:{rx.pattern[:40]}")
                floor = "high-risk"
    return floor, fired


# ── Stage B — mode ``## RISK TIER`` heading (extract_default_gear idiom) ─────
_MODE_TIER_RE = re.compile(
    r"^##\s+RISK\s+TIER\s*\n+\s*([A-Za-z-]+)", re.IGNORECASE | re.MULTILINE)


def extract_mode_risk_tier(mode_text: str | None) -> str | None:
    """Read an optional ``## RISK TIER`` heading from a mode file body.
    Absent/unrecognized → None (no floor)."""
    if not mode_text:
        return None
    m = _MODE_TIER_RE.search(mode_text)
    if not m:
        return None
    val = m.group(1).strip().lower()
    return val if val in _TIER_RANK else None


# ── The before-clock: classify ─────────────────────────────────────────────
def classify_tier(raw_input: str, *, mode_text: str | None = None,
                  sticky_floor: str | None = None,
                  is_trivial_text: bool = False,
                  explicit_override: str | None = None) -> dict:
    """Assign the turn's risk tier. Never raises — on internal error returns
    FAILSAFE_TIER with an ``error`` field (judge condition 6 / spec §7).

    Precedence: an explicit per-turn override wins outright (it may lower a
    floor — user owns the risk, D5); otherwise final =
    max(stage-A floor, stage-B mode floor, sticky floor, default). A trivial
    self-contained text turn with no floors defaults to ``light``.
    """
    try:
        a_floor, fired = stage_a_floor(raw_input)
        b_floor = extract_mode_risk_tier(mode_text)
        det_present = bool(a_floor or b_floor)

        if explicit_override and is_tier(explicit_override):
            final = explicit_override
            source = "explicit-override"
        else:
            # The base default: light only for a trivial self-contained text
            # turn with no floors and no sticky; otherwise standard
            # (condition 1). Sticky may RAISE but never LOWER — it enters the
            # max only as a floor, so a sticky 'light' can never pull a
            # deterministic 'irreversible' down.
            base = "light" if (is_trivial_text and not det_present
                               and not sticky_floor) else DEFAULT_TIER
            present = [t for t in (a_floor, b_floor, sticky_floor) if t]
            final = tier_max(*present, base)
            source = "floors" if det_present else (
                "sticky" if sticky_floor else "default")
        return {
            "risk_tier": final,
            "stage_a_floor": a_floor,
            "stage_b_floor": b_floor,
            "sticky_floor": sticky_floor,
            "default_used": not det_present and not explicit_override,
            "override": explicit_override if explicit_override else None,
            "floors_fired": fired,
            "source": source,
            "error": None,
        }
    except Exception as e:  # pragma: no cover - defensive
        return {"risk_tier": FAILSAFE_TIER, "error": f"classify: {e}",
                "floors_fired": [], "source": "failsafe", "default_used": False,
                "stage_a_floor": None, "stage_b_floor": None,
                "sticky_floor": sticky_floor, "override": None}


# ── Inline /risk parsing (judge condition 5) ────────────────────────────────
# `/risk <tier> <task>`  → per-turn override, task returned as cleaned input.
# `/risk <tier>`         → sticky command (no task) — NOT consumed here; the
#                          runtime slash-command surface handles it.
# `/risk auto`           → clears sticky (also a runtime command).
_RISK_PREFIX_RE = re.compile(r"^\s*/risk\s+([A-Za-z-]+)\s+(\S.*)$", re.DOTALL)
_RISK_BARE_RE = re.compile(r"^\s*/risk\s+([A-Za-z-]+)\s*$")


def strip_risk_prefix(user_input: str) -> tuple[str, str | None]:
    """Lift a leading ``/risk <tier> <task>`` override. Returns
    (cleaned_input, override_tier|None). A bare ``/risk <tier>`` (no task) is
    left intact (returns the input unchanged, None) so the sticky runtime
    command handles it. An unknown tier word is left intact (typo passes as
    text, mirroring parse_user_command's /style behavior)."""
    if not user_input:
        return user_input, None
    m = _RISK_PREFIX_RE.match(user_input)
    if not m:
        return user_input, None
    raw = m.group(1).strip().lower()
    if raw == "auto":
        # `/risk auto <task>` — clear-for-this-turn is meaningless; treat as
        # no override, strip the prefix so the task still runs.
        return m.group(2), None
    tier = _normalize_tier(raw)
    if tier not in _TIER_RANK:
        return user_input, None  # unknown tier → leave as text
    return m.group(2), tier


def parse_sticky_risk(user_input: str) -> str | None:
    """For the runtime command surface: a bare ``/risk <tier>`` or
    ``/risk auto`` with no trailing task. Returns the tier, the sentinel
    ``"auto"``, or None when it isn't a bare risk command."""
    m = _RISK_BARE_RE.match(user_input or "")
    if not m:
        return None
    raw = m.group(1).strip().lower()
    if raw == "auto":
        return "auto"
    val = _normalize_tier(raw)
    return val if val in _TIER_RANK else None


def is_risk_command(user_input: str) -> bool:
    return parse_sticky_risk(user_input) is not None


# ── Task-approval fingerprint (judge condition 3) ───────────────────────────
def task_fingerprint(*, conversation_id: str | None, prompt: str,
                     surface: str = "", mode_id: str = "",
                     output_target: str = "", config_name: str = "",
                     manual_selections=None, attachments=None) -> str:
    """Structured identity of a task for the approval token. Binds more than
    conversation_id + prompt so the SAME task re-admits once while a
    materially different task (different target / mode / attachment) does not
    inherit the token. Prompt is whitespace-normalized + lowercased so
    trivial re-typing still matches; structural fields are exact."""
    norm_prompt = re.sub(r"\s+", " ", (prompt or "").strip().lower())
    payload = {
        "c": conversation_id or "",
        "p": norm_prompt,
        "s": surface or "",
        "m": mode_id or "",
        "o": output_target or "",
        "cfg": config_name or "",
        "sel": sorted(manual_selections.items()) if isinstance(manual_selections, dict)
        else (sorted(manual_selections) if manual_selections else []),
        "att": sorted(attachments) if attachments else [],
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


# The task token is scoped for CONSUMPTION by the FINGERPRINT, not by the
# token's conversation field: the fingerprint already binds conversation_id
# (plus surface/mode/output/…), so it is the authoritative task identity, and
# consuming by fingerprint avoids a double-binding that broke approval on the
# framework path (mint reply's conversation ≠ resume's conversation). BUT the
# token still STORES the granting conversation_id so the stealth closeout
# purge (which matches token.conversation_id == purged conversation) can reach
# it. Cross-conversation safety comes from the fingerprint: two different chat
# conversations produce different fingerprints; a framework deliverable
# (conversation None in the fingerprint) is conversation-agnostic by design.
def has_valid_task_token(fingerprint: str,
                         conversation_id: str | None = None) -> bool:
    """Non-consuming check: is there an unexpired task token for this
    fingerprint? The resume CONSUMES via consume_task_token (one-shot)."""
    data = _te._load_approvals()
    import time as _time
    from datetime import datetime as _dt
    now = _time.time()
    for entry in data.get("tokens", []):
        if entry.get("used") or entry.get("action") != TASK_ACTION:
            continue
        if entry.get("args_hash") != fingerprint:
            continue
        try:
            granted = _dt.fromisoformat(entry["granted_at"]).timestamp()
        except Exception:
            granted = 0
        if now - granted > entry.get("ttl_s", TASK_TOKEN_TTL_S):
            continue
        return True
    return False


def grant_task_token(fingerprint: str, conversation_id: str | None = None,
                     granted_via: str = "tier-gate") -> str:
    """Mint a task-approval token (the recorded human approval). Stores the
    granting conversation_id so the stealth closeout purge can reach it;
    consumption is by fingerprint (see consume_task_token). First removes any
    existing UNUSED token for this fingerprint so a double approval cannot
    accumulate two live one-shot tokens (would let one hold admit the same
    irreversible task twice)."""
    try:
        _te.remove_unused_tokens(TASK_ACTION, fingerprint)
    except Exception:
        pass
    return _te._grant_approval_authorized(
        TASK_ACTION, fingerprint, conversation_id,
        ttl_s=TASK_TOKEN_TTL_S, granted_via=granted_via,
    )


def consume_task_token(fingerprint: str,
                       conversation_id: str | None = None) -> str | None:
    """Consume a matching one-shot task token by fingerprint (the token's
    stored conversation is ignored for matching — see the module note)."""
    return _te.consume_token_by_fingerprint(TASK_ACTION, fingerprint)


# ── Task-gate conversation-as-state marker ──────────────────────────────────
_TASK_GATE_MARKER_RE = re.compile(
    r"<!--\s*ora-task-gate:\s*(\{.*?\})\s*-->", re.DOTALL)


def task_gate_marker(payload: dict) -> str:
    return f"\n\n<!-- ora-task-gate: {json.dumps(payload, sort_keys=True)} -->"


def read_task_gate_marker(text: str) -> dict | None:
    if not text:
        return None
    m = _TASK_GATE_MARKER_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def is_task_gate_continuation(history: list) -> dict | None:
    """Scan the most recent assistant message for a task-gate marker."""
    for msg in reversed(history or []):
        if msg.get("role") == "assistant":
            return read_task_gate_marker(msg.get("content", ""))
    return None



# ── The hold decision ───────────────────────────────────────────────────────
def should_hold(risk_tier: str, *, has_token: bool, stealth: bool = False) -> bool:
    """A tier=irreversible turn holds before the executor unless a valid
    task token already authorizes it. (Stealth still holds — it just uses the
    marker path, no queue card.)"""
    return risk_tier == "irreversible" and not has_token


def build_task_gate_prompt(risk_tier: str, fingerprint: str,
                           queue_id: str | None, resume: dict | None = None) -> str:
    """The assistant reply that pauses an irreversible turn, as a plain
    'response' with the marker appended (the only pause shape the /chat
    plain-HTTP client can see).

    ``resume`` (optional {"fw","mode"}): carried in the marker payload so an
    approval can re-attach the framework elicitation marker and keep a
    mid-elicitation flow alive across the hold (data only — never an embedded
    HTML-comment marker, which would break the outer comment)."""
    body = (
        f"⚠️ This task is classified **{risk_tier}** — it may take an action "
        f"that can't be cleanly undone. Reply **1** to approve and proceed, "
        f"**2** to cancel, or `/risk <tier> <task>` to override the tier."
    )
    payload = {"queue_id": queue_id, "fp": fingerprint, "tier": risk_tier}
    if resume:
        payload["resume"] = resume
    out = body + task_gate_marker(payload)
    # For a framework-deliverable hold, ALSO carry the ora-framework
    # elicitation marker as a SIBLING comment (never nested). This makes the
    # sidebar / slash approval path work with a single "continue": after that
    # approval mints the token, the user's "continue" in the origin
    # conversation falls through the task-gate handler (not 1/2) to
    # is_continuation, which re-enters the deliverable and consumes the token.
    if resume and resume.get("fw"):
        try:
            from framework_elicitation import elicitation_marker
        except ImportError:  # pragma: no cover
            from orchestrator.framework_elicitation import elicitation_marker
        out += "\n" + elicitation_marker(
            resume.get("fw", ""), resume.get("mode", ""),
            resume.get("project_nexus"), resume.get("one_run_profile"),
        )
    return out


# ── The after-clock: route_observed fold (judge condition 7) ────────────────
def fold_route_observed(events_path: str | None, *,
                        conversation_id: str | None = None,
                        turn_ts: str | None = None,
                        output_text: str | None = None) -> dict:
    """Fold a turn's tool-events into route signals. When ``events_path`` is
    a per-turn trace file the whole file is the unit; when it is the global
    sink, filter by conversation_id (+ optional turn_ts window) so a sibling
    turn's events can't contaminate the fold. Never raises.

    Phase 2 shipped signal 1 (``any_mutation`` / ``max_mutability``) and a raw
    ``reads_present`` boolean. Phase 3 adds §6 signal 2 — the SOURCE-READ
    over-approximation: ``source_read_suspected`` (did the output make claims
    about material it read?), the ``source_read_channels`` that fired, and the
    public-safe ``source_candidate_reads`` handed to the Phase 8 provenance
    lane. ``output_text`` (the produced deliverable) drives the "makes claims"
    test; when it is None the signal falls back to the strong channels only
    (over-route safe). ``reads_present`` is unchanged (back-compat)."""
    signals = {"any_mutation": False, "max_mutability": "read",
               "reads_present": False, "max_sensitivity": "public",
               "max_egress": "none", "gate_outcomes": {}, "events_scanned": 0,
               "source_read_suspected": False, "source_read_channels": [],
               "source_candidate_reads": [],
               "source_candidate_reads_truncated": False}
    if not events_path or not os.path.exists(events_path):
        return signals
    scoped_to_file = bool(turn_ts is None and conversation_id is None)
    _src_any = False           # any source-eligible read fired
    _src_always = False        # a STRONG (always-source) channel fired
    _src_channels: set[str] = set()
    _src_candidates: list[dict] = []
    try:
        with open(events_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if not scoped_to_file:
                    if conversation_id is not None:
                        corr = (ev.get("correlation") or {}).get("conversation_id")
                        ev_conv = ev.get("conversation_id") or corr
                        if ev_conv != conversation_id:
                            continue
                    if turn_ts is not None and ev.get("ts", "") < turn_ts:
                        continue
                signals["events_scanned"] += 1
                mut = ev.get("mutability")
                if mut:
                    signals["max_mutability"] = _te.max_mutability(
                        signals["max_mutability"], mut)
                if ev.get("mutated"):
                    signals["any_mutation"] = True
                sens = ev.get("sensitivity")
                if sens:
                    signals["max_sensitivity"] = _te.max_sensitivity(
                        signals["max_sensitivity"], sens)
                egr = ev.get("egress")
                if egr:
                    signals["max_egress"] = _te.max_egress(
                        signals["max_egress"], egr)
                if ev.get("reads"):
                    signals["reads_present"] = True
                # Phase 3 source-read fold (allowlist + actually-ran, §6/§7).
                kind = _source_read_kind(ev)
                if kind:
                    _src_any = True
                    if kind == "always":
                        _src_always = True
                    _src_channels.add(ev.get("action", "") or "")
                    _src_candidates.extend(_public_safe_candidates(ev))
                gate = ev.get("gate") or {}
                dec = gate.get("decision")
                if dec:
                    signals["gate_outcomes"][dec] = \
                        signals["gate_outcomes"].get(dec, 0) + 1
    except Exception:
        pass
    # Combine the read fact with the "makes claims" test (§6, over-route safe).
    # A STRONG channel (external / knowledge contact) + ANY non-empty output
    # suspects regardless of length — a terse grounded answer ("4.1%") must not
    # be under-routed (the unsafe direction); with no output available (rare) a
    # strong channel still over-routes. Ambiguous local-only reads require a
    # substantive deliverable, to avoid firing on a read-to-edit turn whose
    # output is a trivial acknowledgement.
    if _src_any:
        if _src_always:
            signals["source_read_suspected"] = (
                output_text is None or bool(output_text.strip()))
        else:
            signals["source_read_suspected"] = _output_is_substantive(output_text)
    signals["source_read_channels"] = sorted(c for c in _src_channels if c)
    if len(_src_candidates) > _MAX_SOURCE_CANDIDATES:
        signals["source_candidate_reads"] = _src_candidates[:_MAX_SOURCE_CANDIDATES]
        signals["source_candidate_reads_truncated"] = True
    else:
        signals["source_candidate_reads"] = _src_candidates
    return signals


# ── Sticky per-conversation override (durable runtime state) ────────────────
# Stored in a small data/ JSON file (surface-agnostic; no vault/envelope
# schema change). A sticky sets a FLOOR that may raise but never lower a
# deterministic floor (condition 2).
def _sticky_path() -> str:
    # sandboxed_file: test runs (ORA_OVERSIGHT_SANDBOX armed) quarantine the
    # sticky store instead of mutating the live data tree.
    return _rp.sandboxed_file(os.path.join(_rp.DATA_DIR_STR, "risk-sticky.json"))


def _load_sticky() -> dict:
    fd = -1
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(_sticky_path(), flags)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return {}
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = -1
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}
    finally:
        if fd >= 0:
            os.close(fd)


def get_sticky(conversation_id: str | None) -> str | None:
    if not conversation_id:
        return None
    val = _load_sticky().get(conversation_id)
    return val if val in _TIER_RANK else None


def set_sticky(conversation_id: str | None, tier: str | None) -> None:
    """Set (tier in TIERS) or clear (tier is None / 'auto') the sticky."""
    if not conversation_id:
        return
    try:
        path = _sticky_path()
        with _rp.locked_file(path):
            data = _load_sticky()
            if tier is None or tier == "auto" or tier not in _TIER_RANK:
                data.pop(conversation_id, None)
            else:
                data[conversation_id] = tier
            os.makedirs(os.path.dirname(path), exist_ok=True)
            _rp.atomic_write_text(path, json.dumps(data))
    except Exception as exc:
        print(f"[risk_gate] set_sticky failed: {exc}", file=sys.stderr)


def handle_risk_command(user_input: str, conversation_id: str | None) -> str | None:
    """If ``user_input`` is a bare ``/risk <tier>`` / ``/risk auto`` (no task),
    apply the sticky and return a confirmation message (short-circuit). Else
    None. Called at the turn head, before is_runtime_command (condition 5)."""
    val = parse_sticky_risk(user_input)
    if val is None:
        return None
    if val == "auto":
        set_sticky(conversation_id, None)
        return "Risk tier override cleared — tiers now auto-classified per turn."
    set_sticky(conversation_id, val)
    return (f"Risk tier floor set to **{val}** for this Dialogue. "
            f"It raises the tier when auto-classification would be lower, but "
            f"never lowers a deterministic high-risk/irreversible floor. "
            f"Use `/risk auto` to clear.")


# ── Full before-clock assignment + task_tier record ─────────────────────────
def assign_tier(cleaned_input: str, conversation_id: str | None, *,
                mode_text: str | None = None, is_trivial_text: bool = False,
                override: str | None = None, record: bool = True,
                surface: str = "") -> dict:
    """Classify + (optionally) record the turn's tier. Merges the sticky
    floor. Returns the classify_tier dict augmented with the resolved
    tier. Never raises."""
    sticky = get_sticky(conversation_id)
    result = classify_tier(cleaned_input, mode_text=mode_text,
                           sticky_floor=sticky, is_trivial_text=is_trivial_text,
                           explicit_override=override)
    result["surface"] = surface
    if record:
        try:
            _te.record({
                "event": "task_tier", "action": "task_tier",
                "category": "execute", "mutability": "read",
                "sensitivity": "public", "egress": "none",
                "enforcement_model": "in_harness",
                "risk_tier": result["risk_tier"],
                "floors_fired": result.get("floors_fired"),
                "source": result.get("source"),
                "default_used": result.get("default_used"),
                "override": result.get("override"),
                "sticky_floor": result.get("sticky_floor"),
                "assignment_error": result.get("error"),
            })
        except Exception:
            pass
    return result


# ── Task-gate hold card (mirrors Phase 1 execution_gate) ────────────────────
def write_task_gate_card(risk_tier: str, fingerprint: str,
                         conversation_id: str | None, surface: str,
                         description: str, stealth: bool = False,
                         resume: dict | None = None) -> str | None:
    """Write a durable Paused card (kind='task_gate') for an irreversible-tier
    hold. Skipped under stealth (Phase 1 invariant — no card, marker only).
    Returns the queue id, or None (stealth / failure)."""
    if stealth:
        return None
    try:
        from oversight_queue import add_entry
    except ImportError:  # pragma: no cover
        from orchestrator.oversight_queue import add_entry
    try:
        name = f"Task held: {risk_tier} — {(description or '')[:48]}"
        entry = add_entry({
            "kind": "task_gate",
            "name": name,
            "conversation_id": conversation_id,
            "event": {
                "event_type": "TaskGateHeld",
                "risk_tier": risk_tier,
                "fingerprint": fingerprint,
                "conversation_id": conversation_id,
                "principal_id": "principal:user",
                "surface": surface,
                "description": description,
                # Persist the framework resume payload on the card so the
                # queue-side approval path is self-describing (finding 2).
                "resume": resume,
            },
            "verdict": {
                "verdict": "HELD",
                "reasoning": (
                    f"This task is classified {risk_tier}. Approving records "
                    f"the task-level human approval and admits the task once; "
                    f"the per-call gate still fires on the actual irreversible "
                    f"actions."),
            },
            "redefinition": False,
        })
        return getattr(entry, "id", None)
    except Exception:
        return None


def resolve_task_gate_entry(record_dict: dict, approve: bool,
                            reason: str = "", *,
                            principal_id: str = "principal:user") -> str:
    """Commit handler for kind='task_gate' cards (parallels
    tool_events.resolve_gate_entry). Approve → mint the task token; deny →
    record the blocked decision. Called by resolution_chain / slash_commands
    kind-dispatch."""
    event = record_dict.get("event", {})
    fp = event.get("fingerprint", "")
    conv = event.get("conversation_id")
    if event.get("principal_id") != principal_id:
        return "[Task-gate Principal mismatch; the held task was not changed.]"
    if approve:
        grant_task_token(fp, conv, granted_via="paused-queue")
        return ("✅ Task approved. Re-send the task (or say 'continue') in the "
                "origin Dialogue and it will proceed without another hold.")
    try:
        _te.record({"event": "gate", "action": TASK_ACTION,
                    "category": "execute", "mutability": "irreversible",
                    "sensitivity": "private", "egress": "none",
                    "enforcement_model": "in_harness",
                    "gate": {"decision": "blocked",
                             "why": f"task-gate denied: {reason}"[:200]}})
    except Exception:
        pass
    return "❌ Task denied. The held task will not run."


# ── The pre-executor hold evaluator (surface-agnostic) ──────────────────────
def evaluate_hold(risk_tier: str, *, conversation_id: str | None, prompt: str,
                  surface: str, mode_id: str = "", output_target: str = "",
                  config_name: str = "", manual_selections=None,
                  attachments=None, stealth: bool = False,
                  description: str = "", resume: dict | None = None
                  ) -> tuple[str | None, str]:
    """The single hold decision both surfaces call, at the pre-executor
    chokepoint. Returns (hold_reply_or_None, fingerprint).

    For a non-irreversible tier: no hold. For irreversible: if a valid task
    token exists it is CONSUMED (one-shot) and the run proceeds; otherwise a
    durable card (non-stealth) + a marker reply pause the turn.

    NEVER RAISES, and fails CLOSED: any internal error on an irreversible
    tier returns a hold (spec §6 — gated before the executor runs, no
    exceptions), so an I/O error in the token store can't leak an
    irreversible task past the hold."""
    try:
        fp = task_fingerprint(conversation_id=conversation_id, prompt=prompt,
                              surface=surface, mode_id=mode_id,
                              output_target=output_target,
                              config_name=config_name,
                              manual_selections=manual_selections,
                              attachments=attachments)
    except Exception:
        fp = ""
    if risk_tier != "irreversible":
        return None, fp
    try:
        if consume_task_token(fp):
            return None, fp  # pre-authorized (approved earlier / override)
        qid = write_task_gate_card(risk_tier, fp, conversation_id, surface,
                                   description or prompt, stealth=stealth,
                                   resume=resume)
        return build_task_gate_prompt(risk_tier, fp, qid, resume=resume), fp
    except Exception as e:
        # Fail closed: an irreversible task must not proceed on an error.
        try:
            _te.record({"event": "gate", "action": TASK_ACTION,
                        "category": "execute", "mutability": "irreversible",
                        "sensitivity": "private", "egress": "none",
                        "enforcement_model": "in_harness",
                        "gate": {"decision": "blocked",
                                 "why": f"hold fail-closed: {e}"[:200]}})
        except Exception:
            pass
        return build_task_gate_prompt(risk_tier, fp, None, resume=resume), fp


def _remove_task_gate_card(queue_id: str | None) -> None:
    if not queue_id:
        return
    try:
        from oversight_queue import remove_by_id
    except ImportError:  # pragma: no cover
        from orchestrator.oversight_queue import remove_by_id
    try:
        remove_by_id(queue_id)
    except Exception:
        pass


def handle_task_gate_reply(marker_ctx: dict, user_text: str,
                           conversation_id: str | None) -> str | None:
    """A "1"/"2" reply to a task-gate hold. "1" mints the task token (the
    recorded approval) and instructs re-send; "2" cancels. Anything else →
    None (fall through to normal processing)."""
    t = (user_text or "").strip()
    fp = (marker_ctx or {}).get("fp", "")
    qid = (marker_ctx or {}).get("queue_id")
    resume = (marker_ctx or {}).get("resume")
    if t == "1":
        grant_task_token(fp, conversation_id, granted_via="tier-gate")
        _remove_task_gate_card(qid)
        reply = ("✅ Approved. ")
        if resume and resume.get("fw"):
            # A mid-elicitation deliverable hold: re-attach the framework
            # marker so the next turn re-enters elicitation, re-reaches the
            # deliverable, finds this token, and proceeds (the flow would
            # otherwise be stranded — the deliverable path has no other way
            # back). Say "continue" to resume.
            try:
                from framework_elicitation import elicitation_marker
            except ImportError:  # pragma: no cover
                from orchestrator.framework_elicitation import elicitation_marker
            marker = elicitation_marker(
                resume.get("fw", ""), resume.get("mode", ""),
                resume.get("project_nexus"), resume.get("one_run_profile"),
            )
            return (reply + "Say **continue** to produce the deliverable.\n\n"
                    + marker)
        return reply + ("Re-send the task (or repeat it) and it will "
                        "proceed without another hold.")
    if t == "2":
        _remove_task_gate_card(qid)
        return "❌ Cancelled. The held task will not run."
    return None


# ── Criteria pass for standard+ (judge condition 6) ─────────────────────────
def run_criteria_pass(instruction: str, mode_text: str | None, *,
                      invoker=None) -> tuple[str | None, str | None]:
    """Set acceptance criteria BEFORE execution, separate from the executor
    (spec §16-1). ``invoker(system, user)`` is a model-call callback (sidebar
    slot); injected so this is unit-testable and a no-op when no endpoint is
    available. Returns (criteria_text_or_None, error_or_None). Never raises."""
    if invoker is None:
        return None, "no-invoker"
    try:
        system = (
            "You set acceptance criteria for a task BEFORE it is executed. "
            "Read the task instruction and produce 2-5 short, checkable "
            "acceptance criteria as a bulleted list — what must be true for "
            "the result to count as correct. Do not attempt the task. Output "
            "ONLY the bullets.")
        user = f"TASK:\n{instruction}\n"
        out = invoker(system, user)
        if not out or not out.strip():
            return None, "empty"
        return out.strip(), None
    except Exception as e:
        return None, f"criteria: {e}"


def apply_criteria(context_pkg: dict, instruction: str, risk_tier: str, *,
                   invoker=None) -> str | None:
    """Run the criteria pass for standard+ and stash the result on
    context_pkg['acceptance_criteria'] for read-only injection. On FAILURE do
    NOT fall through to light (condition 6): return a hold/warn directive
    string for the caller to surface. Returns None when nothing to surface.

    Return value semantics for the caller:
      * None                     → proceed (light tier, or criteria set OK)
      * "WARN:<msg>"             → prepend the warning, then proceed (standard)
      * "HOLD:<msg>"             → treat as a pre-executor hold (high-risk+)
    """
    if risk_tier == "light":
        return None
    criteria, err = run_criteria_pass(instruction, context_pkg.get("mode_text"),
                                      invoker=invoker)
    if criteria and not err:
        context_pkg["acceptance_criteria"] = criteria
        try:
            _te.record({"event": "acceptance_criteria",
                        "action": "acceptance_criteria", "category": "execute",
                        "mutability": "read", "sensitivity": "public",
                        "egress": "none", "enforcement_model": "in_harness",
                        "risk_tier": risk_tier})
        except Exception:
            pass
        return None
    if err == "no-invoker":
        # No model available to set criteria (e.g. offline / test). Not a
        # silent light-execution: record and proceed; criteria are absent by
        # environment, not by classification.
        return None
    # Genuine failure (empty / error): surface, never silent (condition 6).
    try:
        _te.record({"event": "task_tier", "action": "task_tier",
                    "category": "execute", "mutability": "read",
                    "sensitivity": "public", "egress": "none",
                    "enforcement_model": "in_harness", "risk_tier": risk_tier,
                    "criteria_error": err})
    except Exception:
        pass
    msg = ("Acceptance criteria could not be generated for this "
           f"{risk_tier} task (criteria pass {err}).")
    if tier_at_least(risk_tier, "high-risk"):
        return "HOLD:" + msg + " Holding for your review."
    return "WARN:" + msg + " Proceeding without pre-set criteria."


def record_route_observed(turn_key, risk_tier: str | None = None, *,
                          output_text: str | None = None,
                          declared_output_type: str = "unknown") -> dict:
    """Best-effort after-clock record on ANY terminal path (condition 7).
    ``turn_key`` is either a trace-dir path (str) or a (conversation_id,
    turn_ts) tuple for global-sink turns. ``output_text`` (Phase 3, optional)
    is the produced deliverable; it drives the source-read "makes claims"
    over-approximation. Never raises.

    Phase 4 (condition 1): this folds ONCE and records ``route_observed`` first;
    it does NOT build the packet or carry a packet ref — the terminal caller
    builds the packet SEPARATELY from the returned ``signals`` dict, so there is
    no double-fold and no packet ref smuggled onto the event.
    Phase 4 (condition 3): ``declared_output_type`` is the RAW declared §9 hint
    (default 'unknown'); it is recorded verbatim and NEVER rewritten from the
    observed signals, and it drives the record-only §6 consistency note below."""
    try:
        if isinstance(turn_key, (tuple, list)) and len(turn_key) == 2:
            conv, ts = turn_key
            signals = fold_route_observed(_te.global_sink_path(),
                                          conversation_id=conv, turn_ts=ts,
                                          output_text=output_text)
        elif turn_key:
            path = os.path.join(str(turn_key), "tool-events.jsonl")
            signals = fold_route_observed(path, output_text=output_text)
        else:
            signals = fold_route_observed(None, output_text=output_text)
        divergence = None
        # The one divergence check well-defined in Phase 2 (no output_type
        # until Phase 4): a standard-or-lower turn that mutated beyond its
        # tier. Recorded, not enforced.
        if risk_tier in ("light", "standard") and signals["any_mutation"] \
                and signals["max_mutability"] in ("external_write", "irreversible"):
            divergence = f"{risk_tier}-tier turn observed {signals['max_mutability']}"
        # Phase 4 §6 consistency assertion — declared_output_type vs observed
        # reality contact. RECORD ONLY (never enforced): a "text" task that
        # touched reality is under-review; an "execution" task with no delta and
        # no source read is over-heavy. Dormant on live P4 turns (output_type is
        # 'unknown' until a mode declares it) — exercised in tests. Never raises;
        # a missing helper degrades to no note.
        consistency = None
        try:
            try:
                from execution_packet import consistency_note as _cnote
            except ImportError:  # pragma: no cover
                from orchestrator.execution_packet import consistency_note as _cnote
            consistency = _cnote(declared_output_type, signals)
        except Exception:
            consistency = None
        # Judge condition 2: the event's sensitivity/egress reflect the folded
        # max (honest classification) rather than a hardcoded public — and
        # source_candidate_reads is already public-safe by construction (a
        # read's `what` rides in only from a public read), so the nested payload
        # is safe even though _redact_for_record does not recurse into
        # route_signals. CAP the stamped sensitivity below 'secret': the payload
        # is public-safe and deliberately persists, so it must not claim the
        # secret "existence-only / never-in-a-packet" contract (which the
        # redactor half-applies without recursing); 'sensitive' is the honest
        # ceiling, and the secret fact itself is still recorded inside
        # route_signals.max_sensitivity.
        _stamp_sens = signals.get("max_sensitivity", "public")
        if _stamp_sens == "secret":
            _stamp_sens = "sensitive"
        # Promote the routing verdict to a TOP-LEVEL field (also in the
        # truncation keep-set) so it survives even if a pathological turn's
        # route_signals block is byte-truncated at write (finding [5]).
        # `output_type` (RAW declared hint) + `consistency` ride TOP-LEVEL (and in
        # the truncation keep-set) so they survive a byte-truncated route_signals
        # block. No packet ref here (condition 1).
        _te.record({"event": "route_observed", "action": "route_observed",
                    "category": "execute", "mutability": "read",
                    "sensitivity": _stamp_sens,
                    "egress": signals.get("max_egress", "none"),
                    "enforcement_model": "in_harness",
                    "risk_tier": risk_tier,
                    "source_read_suspected": signals.get("source_read_suspected",
                                                         False),
                    "output_type": declared_output_type,
                    "consistency": consistency,
                    "route_signals": signals, "divergence": divergence})
        return {"signals": signals, "divergence": divergence,
                "consistency": consistency, "output_type": declared_output_type}
    except Exception:
        return {"signals": None, "divergence": None,
                "consistency": None, "output_type": declared_output_type}
