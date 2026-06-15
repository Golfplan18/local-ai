"""Vendor-catalogue-authoritative model inventory (build-time transform).

The inversion: when a vendor has a usable direct pay-as-you-go key, that
vendor's OWN ``/models`` (chat models) becomes the menu for that vendor, and
its OpenRouter entries are dropped. OpenRouter (config/openrouter-catalog.json)
and Artificial-Analysis (config/model-registry.json) data are matched on for
DISPLAY metadata only — field by field, native-first. The dispatch id is always
the vendor's own native id, so there is no id translation at call time and no
"wrong model" failure mode; a wrong/absent metadata match only blanks a cell.

This module is the pure transform (data in → data out), unit-tested with stubs.
Live fetching + file I/O + the old-vs-new diff live in
``scripts/build_vendor_authoritative_registry.py``. Wiring it into the live
registry/endpoint generation is gated by ORA_VENDOR_CATALOG_AUTHORITATIVE and
happens in later PRs; this module changes no live behaviour on its own.
"""
from __future__ import annotations

import os
import re

try:  # import shim (bare module vs package)
    import provider_registry as _reg  # noqa: F401
except ImportError:  # pragma: no cover
    from orchestrator import provider_registry as _reg  # noqa: F401

FLAG = "ORA_VENDOR_CATALOG_AUTHORITATIVE"


def enabled() -> bool:
    """Whether the live system should treat vendor catalogues as authoritative.

    Defaults OFF. The build/diff tool runs regardless; this only gates live use
    (added in a later PR).
    """
    v = (os.environ.get(FLAG, "0") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


# Our provider id → the vendor prefixes used in the AA registry / OpenRouter
# catalog (those are keyed OpenRouter-style ``<prefix>/<model>``).
_ENRICH_PREFIXES = {
    "anthropic": ["anthropic"],
    "openai": ["openai"],
    "gemini": ["google"],
    "xai": ["x-ai"],
    "mistral": ["mistralai", "mistral"],
    "deepseek": ["deepseek"],
    "qwen": ["qwen", "alibaba"],
    "moonshot": ["moonshotai", "moonshot"],
    "minimax": ["minimax", "minimaxai"],
    "xiaomi": ["xiaomi"],
    "meta": ["meta-llama", "meta"],
    "nvidia": ["nvidia"],
}


def _prefixes(vendor_id: str) -> list[str]:
    return _ENRICH_PREFIXES.get(vendor_id, [vendor_id])


# ── chat-modality filter ─────────────────────────────────────────────────────
# Non-chat surfaces a chat picker shouldn't list. Conservative: a model that
# slips through just errors on use (recoverable); the build reports every drop
# so the filter can be tuned against real catalogues.
_NONCHAT_RE = re.compile(
    r"(embedding|text-embedding|-?embed(?:qa|code)?\b|/embed|\bbge-|rerank|reranker|"
    r"\bimage\b|-image|qwen-image|wan[0-9]|z-image|flux|imagen|stable-?diffusion|sora|"
    r"\btts\b|-tts|\baudio\b|speech|sambert|cosyvoice|-voice\b|\basr\b|transcrib|whisper|"
    r"\bocr\b|translation|-translate|livetranslate|qwen-mt[- ]|-mt-(?:flash|turbo|plus|lite|max)\b|"
    r"\bvideo\b|-video|tingwu|ccai|\bs2s\b|\bvc-|\bvd-|"
    r"nvclip|gliner|-reward\b|nemoretriever|nemotron-parse|\bdeplot\b)",
    re.I,
)


def is_chat_model(vendor_id: str, record) -> bool:
    rid = (record.get("id") if isinstance(record, dict) else str(record)) or ""
    if isinstance(record, dict):
        caps = record.get("capabilities")
        if isinstance(caps, dict) and "completion_chat" in caps:
            return bool(caps.get("completion_chat"))
        t = record.get("type")
        if isinstance(t, str):
            tl = t.lower()
            if any(w in tl for w in ("embed", "image", "audio", "moderation", "rerank")):
                return False
    return not _NONCHAT_RE.search(rid)


# ── id normalization for (benign) enrichment matching ────────────────────────
_DATE = re.compile(r"-(?:v\d+-)?(?:\d{4}-\d{2}-\d{2}|\d{2}-\d{4}|\d{3,8})(?:-preview)?$")
# Only true serving-noise tails. NOT -instruct/-thinking/-reasoning/-chat/-it:
# those distinguish genuinely different sibling models, so collapsing them would
# attach one sibling's metadata to another.
_VARIANT = re.compile(r"-(highspeed|fast|preview|latest)$", re.I)


def _norm(s: str) -> str:
    s = (s or "").lower()
    if s.startswith("models/"):
        s = s[7:]
    prev = None
    while prev != s:  # peel repeated date / variant tails
        prev = s
        s = _VARIANT.sub("", _DATE.sub("", s))
    return re.sub(r"[^a-z0-9]", "", s)


def _enrich_index(vendor_id: str, items) -> dict:
    """{normalized native slug → enrichment record} from AA/OR entries whose key
    is ``<prefix>/<model>`` for this vendor's prefixes. ``items`` is an iterable
    of (key, record)."""
    pfx = set(_prefixes(vendor_id))
    idx: dict = {}
    for key, rec in items:
        k = (key or "").lstrip("~")  # AA carries ~-prefixed alias rows
        if "/" not in k:
            continue
        head, rest = k.split("/", 1)
        if head not in pfx:
            continue
        ns = _norm(rest)
        if ns and ns not in idx:
            idx[ns] = rec
    return idx


# ── field-level merge ────────────────────────────────────────────────────────

def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


_PARAM_RE = re.compile(r"[-/](\d{1,4})b\b", re.I)  # …-235b, -27b, -3b, /480b


def _size_from_id(mid: str):
    """(size_bucket, parameters_b) from a parameter count in the id, else
    (None, None). Native ids without a count (gpt-5, grok-4.3, qwen-plus) stay
    unsized — the Models pane's include-unsized opt-in admits them."""
    m = _PARAM_RE.search(mid or "")
    if not m:
        return None, None
    p = int(m.group(1))
    bucket = "small" if p < 12 else ("midsize" if p <= 50 else "large")
    return bucket, p


def _vision(nat: dict, aa: dict, orr: dict, nid: str):
    """Best-effort vision_capable for a native entry: native capability flags →
    AA/OpenRouter enrichment → id heuristic. None when genuinely unknown.

    The Models pane's vision filter + VISUAL slot gate require ``vision_capable
    === true``; without this, native multimodal models (qwen3-vl, gemini, gpt-5)
    are wrongly hidden whenever vision-only is active (most presets ship it on).
    """
    caps = nat.get("capabilities") if isinstance(nat, dict) else None
    if isinstance(nat, dict):
        if nat.get("supports_image_in") is True:
            return True
        if isinstance(caps, dict):
            for f in ("vision", "image_input", "image", "image_understanding"):
                if caps.get(f) is True:
                    return True
        im = nat.get("input_modalities")
        if isinstance(im, list) and any(str(x).lower() == "image" for x in im):
            return True
    if aa.get("vision_capable") is True:
        return True
    if orr.get("accepts_image") is True:
        return True
    im = orr.get("input_modalities")
    if isinstance(im, list) and any(str(x).lower() == "image" for x in im):
        return True
    low = (nid or "").lower()
    if any(t in low for t in ("-vl", "vl-", "-omni", "omni-", "vision", "multimodal")):
        return True
    if aa.get("vision_capable") is False:
        return False
    if isinstance(caps, dict) and caps.get("vision") is False:
        return False
    return None


def _aa_intelligence(aa: dict):
    # ONLY the Artificial Analysis Intelligence Index (≈0–70). NOT
    # intelligence_score, which is an Arena Elo (≈1000–1500) — a different
    # scale entirely; conflating them shows nonsense like "1325".
    return aa.get("aa_intelligence_index")


def _aa_pricing(aa: dict):
    p = aa.get("pricing")
    if isinstance(p, dict):
        i = p.get("input_per_token", p.get("prompt"))
        o = p.get("output_per_token", p.get("completion"))
        if i is not None or o is not None:
            return {"input_per_token": _num(i), "output_per_token": _num(o)}
    return None


def _or_pricing(orr: dict):
    pm = orr.get("pricing_per_million")
    if isinstance(pm, dict):
        i = _num(pm.get("prompt"))
        o = _num(pm.get("completion"))
        if i is not None or o is not None:
            return {"input_per_token": (i / 1e6 if i is not None else None),
                    "output_per_token": (o / 1e6 if o is not None else None)}
    return None


def merge_entry(vendor_id: str, native_rec, aa_idx: dict, or_idx: dict) -> dict:
    """Produce one inventory entry for a native model, native-first per field."""
    nid = (native_rec.get("id") if isinstance(native_rec, dict) else str(native_rec)) or ""
    nat = native_rec if isinstance(native_rec, dict) else {}
    ns = _norm(nid)
    aa = aa_idx.get(ns) or {}
    orr = or_idx.get(ns) or {}
    src: dict = {}

    def pick(field, *cands):
        for label, val in cands:
            if val not in (None, "", [], {}):
                src[field] = label
                return val
        return None

    display = pick("display_name",
                   ("native", nat.get("display_name") or nat.get("name")),
                   ("aa", aa.get("display_name")),
                   ("openrouter", orr.get("display_name"))) or nid
    context = pick("context_length",
                   ("native", nat.get("max_context_length") or nat.get("context_length")
                    or nat.get("max_input_tokens")),
                   ("aa", aa.get("context_length")),
                   ("openrouter", orr.get("context_length")))
    # Intelligence + tokens/sec exist ONLY in AA (verified) — or blank.
    intelligence = _aa_intelligence(aa)
    if intelligence is not None:
        src["intelligence"] = "aa"
    tps = aa.get("output_tokens_per_second")
    if tps is not None:
        src["output_tokens_per_second"] = "aa"
    # Price: AA (per-token) → OpenRouter (per-million → per-token) → blank.
    pricing = _aa_pricing(aa)
    if pricing:
        src["pricing"] = "aa"
    else:
        pricing = _or_pricing(orr)
        if pricing:
            src["pricing"] = "openrouter"
    reasoning = pick("reasoning_model",
                     ("native", nat.get("supports_reasoning")),
                     ("aa", aa.get("reasoning_model")))
    size_bucket, params_b = _size_from_id(nid)
    vision = _vision(nat, aa, orr, nid)

    return {
        "id": f"{vendor_id}/{nid}",            # registry key (uniform namespace)
        "native_model_id": nid,                # the id actually dispatched
        "provider": vendor_id,
        "vendor": vendor_id,
        "dispatch": "direct",
        "display_name": display,
        "context_length": context,
        "aa_intelligence_index": intelligence,              # field the Models pane reads
        "intelligence_index": intelligence,                 # AA Index (≈0–70)
        "intelligence_score": aa.get("intelligence_score"),  # Arena Elo (≈1000–1500)
        "intelligence_rank": aa.get("intelligence_rank"),
        "output_tokens_per_second": tps,
        "pricing": pricing,
        "reasoning_model": reasoning,
        "size_bucket": size_bucket,
        "parameters_b": params_b,
        "vision_capable": vision,
        "release_date": nat.get("created") or aa.get("release_date") or orr.get("created"),
        "_enrichment_source": src,
        "_enrichment_matched": bool(aa) or bool(orr),
    }


def build_vendor_entries(vendor_id: str, native_records: list, aa_idx: dict, or_idx: dict):
    """Return (chat entries, dropped non-chat ids) for one vendor's catalogue."""
    kept, dropped = [], []
    for r in native_records:
        rid = (r.get("id") if isinstance(r, dict) else r)
        if not rid:
            continue  # malformed record (no id) — skip, never abort the build
        (kept if is_chat_model(vendor_id, r) else dropped).append(r)
    entries = [merge_entry(vendor_id, r, aa_idx, or_idx) for r in kept]
    drop_ids = [(r.get("id") if isinstance(r, dict) else r) for r in dropped]
    return entries, drop_ids


def build_authoritative_registry(base_models: dict, vendor_catalogs: dict,
                                 or_models: list | None = None):
    """Transform the OpenRouter+AA registry into a vendor-authoritative one.

    base_models     : {orid → entry}, the AA-enriched registry (also the AA source)
    vendor_catalogs : {provider_id → [native /models records]} for keyed vendors
    or_models       : the OpenRouter catalog list (fallback price/context)

    Returns ``(new_models, report)``: for each vendor with a catalogue, its
    OpenRouter entries are removed and replaced by native chat entries; other
    vendors pass through unchanged.
    """
    or_models = or_models or []
    new = dict(base_models)
    report: dict = {}
    for vendor_id, native_records in vendor_catalogs.items():
        if not native_records:
            continue
        pfx = set(_prefixes(vendor_id))
        removed = [k for k in list(new.keys())
                   if "/" in k and k.split("/", 1)[0].lstrip("~") in pfx]
        for k in removed:
            new.pop(k, None)
        aa_idx = _enrich_index(vendor_id, base_models.items())
        or_idx = _enrich_index(vendor_id, ((m.get("id", ""), m) for m in or_models))
        entries, dropped = build_vendor_entries(vendor_id, native_records, aa_idx, or_idx)
        for e in entries:
            new[e["id"]] = e
        n = len(entries) or 1
        report[vendor_id] = {
            "openrouter_removed": len(removed),
            "native_chat_added": len(entries),
            "non_chat_dropped": len(dropped),
            "dropped_examples": dropped[:10],
            "enrichment_matched": sum(1 for e in entries if e["_enrichment_matched"]),
            "intelligence_coverage": sum(1 for e in entries if e["intelligence_index"] is not None),
            "price_coverage": sum(1 for e in entries if e["pricing"]),
            "count": len(entries),
        }
    return new, report


def native_direct_entries(models: dict) -> list:
    """The vendor-native direct entries in an authoritative registry
    (``dispatch == "direct"`` with a ``native_model_id``)."""
    return [e for e in (models or {}).values()
            if isinstance(e, dict) and e.get("dispatch") == "direct"
            and e.get("native_model_id")]


__all__ = [
    "FLAG", "enabled", "is_chat_model", "merge_entry",
    "build_vendor_entries", "build_authoritative_registry",
    "native_direct_entries",
]
