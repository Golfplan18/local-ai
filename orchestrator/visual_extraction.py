"""Visual extraction (WP-4.3) — invoke a vision-capable model with an image
and parse the response into a ``spatial_representation`` JSON object so
text-only downstream models can consume the structured layout as context.

Public API
----------

``extract_spatial_from_image(image_path, extractor_endpoint, confidence_threshold=0.5)``
    Invokes the vision model with a structured prompt, parses its response,
    runs ``visual_validator.validate_spatial_representation`` against the
    authoritative schema, attempts a single repair pass on common mistakes,
    computes an overall confidence, and returns an ``ExtractionResult``.

Design notes
------------

* Single HTTP/SDK surface: reuses ``boot.call_model`` so the full
  endpoint-type matrix (api / local / browser) is handled uniformly.
  ``call_model`` already knows how to attach an image via
  ``images=[{"name","mime","base64"}]``; we just build that list here.
* Prompt is stored as a module constant so tests can assert on it, and so
  ``extractor_endpoint['extraction_prompt_override']`` can replace it
  wholesale for future tuning. No interpolation in the constant — the
  request image itself carries the content.
* Parse repair is minimal on purpose: we recover from two common LLM
  mistakes (missing ``id`` on an entity, missing ``position``), then give
  up. Wrestling with arbitrarily malformed output is the extractor
  model's problem to solve — we record the failure and let the caller
  decide (WP-4.4 surfaces this to the user).
* Low-confidence responses are still returned but flagged with a
  ``W_LOW_CONFIDENCE_EXTRACTION`` entry on ``parse_errors`` so the
  caller can surface a soft warning without blocking the pipeline.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Prompt — structured extraction instruction for the vision model.
# ---------------------------------------------------------------------------
# This prompt is intentionally terse and directive. The vision model's job
# is to output a single JSON object conforming to the schema at
# ``config/visual-schemas/spatial_representation.json``. No prose, no
# markdown fences, no apologies.
#
# When the extractor endpoint carries ``extraction_prompt_override``, that
# string replaces this constant wholesale — useful for per-model tuning
# (e.g. stricter schemas for Gemini, looser for GPT-4o).

EXTRACTION_PROMPT = """\
You are a visual-structure extractor. Analyze the attached image and output ONE JSON object describing the spatial layout of its contents. Follow these rules exactly:

1. Output ONLY the JSON object. No prose, no markdown fences, no "Here is the JSON:" preamble, no trailing commentary. Nothing outside the braces.
2. The JSON MUST conform to this shape:
   {
     "entities": [
       {"id": "e-1", "position": [x, y], "label": "short text", "confidence": 0.0-1.0}
     ],
     "relationships": [
       {"source": "e-1", "target": "e-2", "type": "causal|associative|hierarchical|temporal", "strength": 0.0-1.0, "confidence": 0.0-1.0}
     ],
     "clusters": [
       {"members": ["e-1","e-2"], "label": "group name"}
     ],
     "hierarchy": [
       {"parent": "e-1", "children": ["e-2","e-3"], "type": "abstraction|containment|composition"}
     ]
   }
   Only ``entities`` is required. Omit the other arrays when empty.
3. ``position`` is ``[x, y]`` with coordinates NORMALIZED to the range [0.0, 1.0] relative to the image's top-left corner (x grows right, y grows down). Estimate from the visual centroid of each element.
4. ``id`` is a short slug (``e-1``, ``e-2``, ...). Use unique ids; references in ``relationships``, ``clusters``, and ``hierarchy`` MUST resolve to declared entity ids.
5. ``confidence`` per entity and per relationship is your own estimate of how sure you are that element exists and is correctly labeled — 1.0 = certain, 0.0 = pure guess.
6. Extraction strategy by image type:
   - Diagram or drawing (boxes, arrows, node-link structure): each visual element is an entity; arrows/lines become relationships with the closest matching type.
   - Text or handwriting: capture each distinct text block as an entity with that text as its label.
   - Ambiguous, blurry, or low-detail: emit fewer, more confident entities rather than guessing. It is better to return 3 high-confidence entities than 12 low-confidence ones.
7. Keep ``label`` under 80 characters. If the source text is longer, summarize.
8. If the image is blank, undecipherable, or contains no extractable structure, return ``{"entities": []}`` — a valid empty extraction is preferred over hallucination.

Return the JSON now.\
"""


# ---------------------------------------------------------------------------
# Result dataclass — what every extraction attempt returns.
# ---------------------------------------------------------------------------


@dataclass
class ExtractionResult:
    """Outcome of a single vision extraction attempt.

    ``spatial_representation`` is the parsed + validated JSON dict when
    extraction succeeded (possibly after repair), or ``None`` when the
    response could not be parsed or failed schema validation after repair.

    ``confidence`` is the mean of per-entity confidences (0.0-1.0); when no
    entities were extracted it is 0.0.

    ``parse_errors`` is a list of human-readable strings describing what
    went wrong during parsing / validation / repair. It may include the
    soft warning code ``W_LOW_CONFIDENCE_EXTRACTION`` even when extraction
    succeeded.

    ``raw_response`` is the model's full text response for debugging.

    ``extractor_model`` is the id (or display_name fallback) of the
    endpoint that produced this result, for logs and prompt injection.
    """

    spatial_representation: dict | None = None
    confidence: float = 0.0
    raw_response: str = ""
    parse_errors: list[str] = field(default_factory=list)
    extractor_model: str = ""

    def as_dict(self) -> dict:
        return {
            "spatial_representation": self.spatial_representation,
            "confidence": self.confidence,
            "raw_response": self.raw_response,
            "parse_errors": list(self.parse_errors),
            "extractor_model": self.extractor_model,
        }


# ---------------------------------------------------------------------------
# Image loading — read image into the {"name","mime","base64"} envelope
# that ``boot.call_model`` expects.
# ---------------------------------------------------------------------------


def _load_image_as_attachment(image_path: str) -> dict:
    """Read ``image_path`` from disk into the attachment dict shape that
    ``boot.call_model`` threads into Claude / OpenAI / Gemini / Ollama.

    Raises FileNotFoundError if the path doesn't exist so the caller can
    produce a clean parse_error line.
    """
    if not image_path or not os.path.exists(image_path):
        raise FileNotFoundError(f"image not found: {image_path}")

    mime, _ = mimetypes.guess_type(image_path)
    if not mime:
        # Conservative default — Claude accepts ``image/png``, Gemini accepts
        # most. If the file is actually a jpg the server APIs tolerate the
        # mismatch far better than a missing field.
        mime = "image/png"

    with open(image_path, "rb") as fh:
        data = fh.read()

    return {
        "name": os.path.basename(image_path),
        "mime": mime,
        "base64": base64.b64encode(data).decode("ascii"),
    }


# ---------------------------------------------------------------------------
# Response cleaning — strip the most common LLM response-shape mistakes.
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(
    r"```(?:json|JSON)?\s*(.*?)```",
    re.DOTALL,
)

# Trailing commas inside objects/arrays — ``{"a": 1,}`` or ``[1,2,]``.
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")

# Leading conversational prefix the model might emit despite instructions.
_PREAMBLE_RES = [
    re.compile(r"^\s*Here(?:'s| is)\s+(?:the\s+)?(?:JSON|output|result)[:\.\s]*", re.IGNORECASE),
    re.compile(r"^\s*Output[:\.\s]*", re.IGNORECASE),
    re.compile(r"^\s*JSON[:\.\s]*", re.IGNORECASE),
]


def _clean_response(raw: str) -> str:
    """Strip markdown fences, conversational preamble, and trailing commas
    from a model response so ``json.loads`` has the best chance of
    succeeding. Pure text transform — no JSON parse here.
    """
    if not raw:
        return ""

    text = raw.strip()

    # 1) If the whole thing is wrapped in a single fence, unwrap.
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    # 2) Strip common preamble phrases.
    for pat in _PREAMBLE_RES:
        text = pat.sub("", text, count=1).strip()

    # 3) If there's leading / trailing prose around the JSON, try to
    #    extract the first balanced ``{ ... }`` block. Lenient — the
    #    schema validator catches real structural issues.
    brace_start = text.find("{")
    if brace_start > 0:
        # Check if the prefix is all whitespace/preamble-ish; if it has
        # letters the model ignored the JSON-only instruction — slice
        # from the first brace anyway.
        text = text[brace_start:]

    brace_end = text.rfind("}")
    if brace_end != -1 and brace_end < len(text) - 1:
        text = text[: brace_end + 1]

    # 4) Kill trailing commas (``,}`` or ``,]``).
    text = _TRAILING_COMMA_RE.sub(r"\1", text)

    return text.strip()


# ---------------------------------------------------------------------------
# Repair — single-pass fix-up for two common model mistakes.
# ---------------------------------------------------------------------------


def _slugify_label(label: str, fallback: str) -> str:
    """Produce a terse id from a label. Non-alnum → ``-``. Lowercased."""
    if not isinstance(label, str) or not label.strip():
        return fallback
    slug = re.sub(r"[^A-Za-z0-9]+", "-", label.strip().lower()).strip("-")
    return slug or fallback


def _repair_spatial_representation(parsed: dict) -> tuple[dict, list[str]]:
    """Attempt a one-pass repair of common LLM spatial-representation mistakes.

    Fixes:
      * Entity missing ``id`` → synthesize from label via slug; collision →
        append ``-N``.
      * Entity missing ``position`` → default to ``[0.5, 0.5]`` (image
        centre) and append a ``W_POSITION_DEFAULTED`` note.
      * Entity missing ``label`` → use ``id`` as label (or ``"unknown"``
        if id is also missing). Rare — schema requires both.

    Does NOT attempt to repair relationships, clusters, or hierarchy —
    if those are missing ids the schema validator surfaces them and the
    caller fails cleanly.

    Note: ``confidence`` fields on entities/relationships are stripped
    upstream by ``_strip_confidence_fields`` (the authoritative schema
    declares ``additionalProperties: false`` and rejects them). This
    function operates on the post-stripped dict.

    Returns ``(repaired_dict, repair_notes)``.
    """
    notes: list[str] = []
    if not isinstance(parsed, dict):
        return parsed, notes

    entities = parsed.get("entities")
    if not isinstance(entities, list):
        return parsed, notes

    seen_ids: set[str] = set()
    for i, ent in enumerate(entities):
        if not isinstance(ent, dict):
            continue
        # Missing id → synthesize from label.
        if not ent.get("id"):
            base = _slugify_label(ent.get("label", ""), fallback=f"e-{i+1}")
            candidate = base
            n = 1
            while candidate in seen_ids:
                n += 1
                candidate = f"{base}-{n}"
            ent["id"] = candidate
            notes.append(f"entities[{i}].id synthesized → {candidate}")
        seen_ids.add(ent["id"])

        # Missing position → default to image centre.
        pos = ent.get("position")
        if not (isinstance(pos, list) and len(pos) == 2):
            ent["position"] = [0.5, 0.5]
            notes.append(f"entities[{i}].position defaulted → [0.5, 0.5]")

        # Missing label → last-ditch fallback so the schema accepts it.
        if not ent.get("label"):
            ent["label"] = ent.get("id") or "unknown"
            notes.append(f"entities[{i}].label defaulted → {ent['label']}")

    return parsed, notes


def _strip_confidence_fields(parsed: dict) -> tuple[dict, list[float], list[float]]:
    """Return ``(parsed_without_confidence, entity_confs, rel_confs)``.

    The authoritative ``spatial_representation.json`` schema declares
    ``additionalProperties: false`` on entities and relationships, so any
    ``confidence`` key the model emits per our extraction prompt causes
    schema rejection. We capture the per-entity / per-relationship
    confidences (so we can compute the mean), then delete them from the
    payload before validation. Same treatment for ``strength`` on
    relationships — it IS allowed by schema, so we keep it.
    """
    entity_confs: list[float] = []
    rel_confs: list[float] = []
    if not isinstance(parsed, dict):
        return parsed, entity_confs, rel_confs

    for ent in parsed.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        if "confidence" in ent:
            try:
                f = float(ent["confidence"])
                if f < 0.0:
                    f = 0.0
                elif f > 1.0:
                    f = 1.0
                entity_confs.append(f)
            except (TypeError, ValueError):
                pass
            del ent["confidence"]

    for rel in parsed.get("relationships") or []:
        if not isinstance(rel, dict):
            continue
        if "confidence" in rel:
            try:
                f = float(rel["confidence"])
                if f < 0.0:
                    f = 0.0
                elif f > 1.0:
                    f = 1.0
                rel_confs.append(f)
            except (TypeError, ValueError):
                pass
            del rel["confidence"]

    return parsed, entity_confs, rel_confs


# ---------------------------------------------------------------------------
# Confidence scoring — mean of per-entity confidences.
# ---------------------------------------------------------------------------


def _compute_mean_confidence(entity_confs: list[float]) -> float:
    """Return the mean of per-entity ``confidence`` values captured during
    ``_strip_confidence_fields``. Returns 0.0 when no confidences were
    present (the caller decides if that should be treated as success or
    as a soft failure)."""
    if not entity_confs:
        return 0.0
    return sum(entity_confs) / len(entity_confs)


# ---------------------------------------------------------------------------
# Model invocation wrapper — isolates the ``boot.call_model`` dependency
# so tests can monkey-patch just this helper.
# ---------------------------------------------------------------------------


def _invoke_vision_model(prompt: str,
                         image_attachment: dict,
                         extractor_endpoint: dict) -> str:
    """Call the vision-capable model with a system prompt + image and
    return the raw text response. Reuses ``boot.call_model`` so every
    endpoint type (api / local / browser) is handled uniformly.

    Tests should ``mock.patch('visual_extraction._invoke_vision_model',
    return_value=<raw_str>)`` rather than mocking boot.call_model across
    the codebase.
    """
    # Lazy import — avoid circular import at module load time.
    from boot import call_model

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Extract the spatial structure from the attached image."},
    ]
    return call_model(messages, extractor_endpoint, images=[image_attachment])


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


def extract_spatial_from_image(
    image_path: str,
    extractor_endpoint: dict,
    confidence_threshold: float = 0.5,
) -> ExtractionResult:
    """Invoke ``extractor_endpoint`` with ``image_path`` + the structured
    extraction prompt, parse the response, and return an
    ``ExtractionResult``.

    Never raises — failures become populated ``parse_errors`` + a
    ``spatial_representation=None`` result so the caller can treat
    extraction as best-effort.

    Parameters
    ----------
    image_path : str
        Absolute path to the image on disk. Usually produced by the
        server's ``_save_multipart_image`` and carried on
        ``context_pkg['image_path']``.
    extractor_endpoint : dict
        The endpoint dict returned by ``boot._pick_vision_extractor``.
        Must be vision-capable. Optional key
        ``extraction_prompt_override`` replaces the default prompt.
    confidence_threshold : float
        Mean confidence below which the result is still returned but
        tagged with ``W_LOW_CONFIDENCE_EXTRACTION``. Default 0.5.
    """
    model_id = (
        extractor_endpoint.get("id")
        or extractor_endpoint.get("display_name")
        or "unknown"
    )
    result = ExtractionResult(extractor_model=model_id)

    # 1) Load image into the attachment dict shape call_model expects.
    try:
        attachment = _load_image_as_attachment(image_path)
    except Exception as exc:
        result.parse_errors.append(f"image load failed: {exc}")
        return result

    # 2) Pick the prompt (per-endpoint override wins, else constant).
    prompt = (
        extractor_endpoint.get("extraction_prompt_override")
        or EXTRACTION_PROMPT
    )

    # 3) Invoke the model.
    try:
        raw = _invoke_vision_model(prompt, attachment, extractor_endpoint)
    except Exception as exc:
        result.parse_errors.append(f"model invocation failed: {exc}")
        return result

    result.raw_response = raw or ""
    if not result.raw_response:
        result.parse_errors.append("empty response from vision model")
        return result

    # ``call_model`` returns ``[Error ...]`` strings on failure — detect
    # and treat them as a failed extraction rather than schema-invalid
    # JSON (which would be misleading in logs).
    stripped = result.raw_response.strip()
    if stripped.startswith("[Error") or stripped.startswith("[No response"):
        result.parse_errors.append(f"model returned error: {stripped[:120]}")
        return result

    # 4) Clean + parse the JSON.
    cleaned = _clean_response(result.raw_response)
    if not cleaned:
        result.parse_errors.append("response was empty after cleanup")
        return result

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        result.parse_errors.append(f"JSON decode failed: {exc.msg} at pos {exc.pos}")
        return result

    if not isinstance(parsed, dict):
        result.parse_errors.append(
            f"parsed top-level is not an object (got {type(parsed).__name__})"
        )
        return result

    # 5) Strip confidence fields BEFORE validation — they're not in the
    #    authoritative schema (additionalProperties: false). Keep the
    #    captured values for mean-confidence computation.
    parsed, entity_confs, _rel_confs = _strip_confidence_fields(parsed)

    # 6) Validate against the schema; on failure, try one repair pass.
    from visual_validator import validate_spatial_representation

    validation = validate_spatial_representation(parsed)
    if not validation.valid:
        repaired, notes = _repair_spatial_representation(parsed)
        for n in notes:
            result.parse_errors.append(f"repair: {n}")
        validation2 = validate_spatial_representation(repaired)
        if not validation2.valid:
            for err in validation2.errors:
                msg = getattr(err, "message", str(err))
                path = getattr(err, "path", "")
                suffix = f" @{path}" if path else ""
                result.parse_errors.append(f"schema: {msg}{suffix}")
            return result
        parsed = repaired

    # 7) Compute mean confidence from the captured values; flag
    #    low-confidence but still return the extraction.
    mean_conf = _compute_mean_confidence(entity_confs)
    result.confidence = mean_conf
    result.spatial_representation = parsed

    if mean_conf < confidence_threshold:
        result.parse_errors.append(
            "W_LOW_CONFIDENCE_EXTRACTION: mean confidence "
            f"{mean_conf:.2f} < threshold {confidence_threshold:.2f}"
        )

    return result


__all__ = [
    "EXTRACTION_PROMPT",
    "ExtractionResult",
    "extract_spatial_from_image",
]
