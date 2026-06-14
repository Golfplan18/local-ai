"""
visual_synthesis.py — Phase 1 emission reliability.

When a visual-expecting analytical turn fails to produce a VALID ``ora-visual``
envelope (the analytical model emitted ASCII art, malformed JSON, a
schema-violating shape, or nothing at all), this module synthesizes a valid
envelope from the analyst's prose via a narrow, schema-anchored model call
wrapped in a validate -> repair loop.

The point: relieve the *analytical* model of the burden of emitting strict
JSON. Any model can be weak at JSON because a narrow synthesis call plus a
deterministic repair loop closes the gap — the OUTCOME becomes
model-independent. The schema itself stays strict (honesty + deterministic
render); only the producer changes.

Pure logic: :func:`synthesize_envelope` takes a ``call_fn(prompt) -> str`` so it
is unit-testable with a mock model. ``boot.py`` binds the real ``call_fn`` to a
resolved, JSON-reliable endpoint.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

SCHEMAS_ROOT = Path(os.path.expanduser("~/ora/config/visual-schemas"))
SCHEMA_VERSION = "0.2"

# Total model calls = 1 + MAX_REPAIR_ROUNDS. Two repairs is enough to converge
# in practice (Protocol §11 Fork A used the same "switch if >3 retries" bar).
MAX_REPAIR_ROUNDS = 2

_FENCE_RE = re.compile(r"```(?:ora-visual|json)?\s*\n?(.*?)\n?```", re.DOTALL)

SYSTEM_PROMPT = (
    "You are a precise JSON-emitting compiler. You output exactly one valid "
    "JSON object and nothing else — no prose, no markdown, no code fence."
)


def _load_example(vtype: str) -> dict | None:
    """Load the known-good example fixture for ``vtype`` (anchors the shape)."""
    try:
        p = SCHEMAS_ROOT / "examples" / f"{vtype}.valid.json"
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return None


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a model response (fenced or raw)."""
    if not text:
        return None
    candidates: list[str] = []
    m = _FENCE_RE.search(text)
    if m:
        candidates.append(m.group(1).strip())
    candidates.append(text.strip())
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{"): text.rfind("}") + 1])
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def autofill(env: dict, mode: str, vtype: str, idx: int = 1) -> dict:
    """Fill the mechanical envelope fields the model shouldn't have to author,
    and guarantee a minimal ``semantic_description`` so accessibility is never
    the thing that blocks a render. Never overwrites authored content.
    """
    env = dict(env)
    env.setdefault("schema_version", SCHEMA_VERSION)
    env.setdefault("id", f"fig-{idx}")
    env.setdefault("mode_context", mode or "unknown")
    if not env.get("type"):
        env["type"] = vtype
    env.setdefault("relation_to_prose", "integrated")

    sd = env.get("semantic_description")
    pretty = vtype.replace("_", " ")
    title = (env.get("title") or pretty)
    if not isinstance(sd, dict):
        sd = {}
    if not (sd.get("short_alt") or "").strip():
        sd["short_alt"] = f"{pretty}: {title}"
    sd.setdefault("level_1_elemental", f"A {pretty} titled '{title}'.")
    sd.setdefault("level_2_statistical", "See surrounding prose.")
    sd.setdefault("level_3_perceptual", "See surrounding prose.")
    env["semantic_description"] = sd
    return env


def _build_prompt(prose: str, mode: str, vtype: str,
                  errors: list[str] | None = None, prior: dict | None = None) -> str:
    parts: list[str] = [
        f"Convert the analyst's prose below into ONE valid `ora-visual` JSON "
        f"envelope of type `{vtype}`.",
        "Output ONLY the JSON object.",
    ]
    example = _load_example(vtype)
    if example is not None:
        parts.append("VALID example of this exact type — match its shape exactly:")
        parts.append(json.dumps(example, indent=2))
    parts.append("ANALYST PROSE (extract the structure from this):")
    parts.append((prose or "")[:6000])
    if errors:
        parts.append(
            "Your previous attempt was INVALID. Fix exactly these problems and "
            "re-emit the FULL corrected JSON object:"
        )
        parts.append("\n".join(f"- {e}" for e in errors[:12]))
        if prior is not None:
            parts.append("Previous (invalid) attempt:")
            parts.append(json.dumps(prior)[:4000])
    return "\n\n".join(parts)


# How many acceptable kinds to attempt before giving up. The first is the
# requested/preferred kind; the rest are the routed mode's fallbacks. Trying a
# second kind lets a multi-kind mode degrade gracefully — e.g. if a 2x2 won't
# build from constraint-mapping prose, a pro_con tree still ships; if a fresh
# c4 won't build, a concept_map still ships — instead of returning no visual.
MAX_TARGET_KINDS = 2


def _synthesize_one(prose: str, mode: str, vtype: str, call_fn, idx: int):
    """Run the validate→repair loop for ONE target kind. Returns
    ``(envelope | None, attempts)``."""
    from visual_validator import validate_envelope
    from visual_adversarial import review_envelope
    try:
        from visual_recovery import repair_spec
    except Exception:
        repair_spec = lambda e, t=None: e  # noqa: E731 — fail-open

    attempts: list[dict] = []
    errors: list[str] | None = None
    prior: dict | None = None

    for round_i in range(MAX_REPAIR_ROUNDS + 1):
        prompt = _build_prompt(prose, mode, vtype, errors=errors, prior=prior)
        try:
            raw = call_fn(prompt)
        except Exception as exc:
            attempts.append({"round": round_i, "ok": False, "kind": vtype,
                             "reason": f"call_fn error: {exc}"})
            break

        env = _extract_json(raw)
        if env is None:
            attempts.append({"round": round_i, "ok": False, "kind": vtype,
                             "reason": "no JSON object in response"})
            errors = ["Your output was not parseable JSON. Emit ONLY a JSON object."]
            prior = None
            continue

        env = autofill(env, mode, vtype, idx=idx)
        # Deterministic spec repair (drop schema-forbidden extras, fill required
        # fields the model commonly omits — e.g. quadrant axes_independence_
        # rationale, item bounds). Closes the gap between a structurally-sound
        # answer and a schema-valid envelope without another model round-trip.
        env = repair_spec(env, vtype)

        vres = validate_envelope(env)
        if not vres.valid:
            errs = [f"{e.get('code')}: {e.get('message')}" for e in vres.as_dict().get("errors", [])]
            attempts.append({"round": round_i, "ok": False, "kind": vtype,
                             "reason": "schema/structural invalid", "errors": errs})
            errors, prior = errs, env
            continue

        review = review_envelope(env, mode)
        if review.blocks:
            errs = [f"{b.rule}: {b.message}" for b in review.blocks]
            attempts.append({"round": round_i, "ok": False, "kind": vtype,
                             "reason": "adversarial Critical", "errors": errs})
            errors, prior = errs, env
            continue

        attempts.append({"round": round_i, "ok": True, "kind": vtype})
        return env, attempts

    return None, attempts


def synthesize_envelope(prose: str, mode: str, target_types, call_fn, idx: int = 1):
    """Synthesize a valid ``ora-visual`` envelope from ``prose``.

    Args:
        prose: the analyst's text to derive structure from.
        mode: the Ora mode name (used for ``mode_context`` + adversarial routing).
        target_types: ordered list of acceptable visual ``type`` strings; the
            first is the preferred target. Up to ``MAX_TARGET_KINDS`` are tried
            in order, so a multi-kind mode degrades to its next acceptable kind
            rather than returning nothing.
        call_fn: ``call_fn(prompt: str) -> str`` — a bound model caller.
        idx: figure index for the default ``id``.

    Returns:
        ``(envelope | None, attempts)`` where ``attempts`` is a list of
        per-round ``{round, kind, ok, reason?, errors?}`` dicts (telemetry).
    """
    kinds = list(target_types) or ["concept_map"]
    all_attempts: list[dict] = []
    for vtype in kinds[:MAX_TARGET_KINDS]:
        env, attempts = _synthesize_one(prose, mode, vtype, call_fn, idx)
        all_attempts.extend(attempts)
        if env is not None:
            return env, all_attempts
    return None, all_attempts


__all__ = ["synthesize_envelope", "autofill", "SCHEMA_VERSION", "MAX_REPAIR_ROUNDS"]
