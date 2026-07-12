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
``scripts/build_vendor_authoritative_registry.py``. The generated artifact is
consumed by the Models inventory and endpoint generator when
ORA_VENDOR_CATALOG_AUTHORITATIVE is enabled (the default); this module itself
still performs no I/O.
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
    """Whether the live system treats vendor catalogues as authoritative.

    Default ON. Set ORA_VENDOR_CATALOG_AUTHORITATIVE=0 to fall back to the
    OpenRouter-sourced inventory + the runtime prefer-direct rewrite.
    """
    v = (os.environ.get(FLAG, "1") or "").strip().lower()
    return v not in ("0", "false", "no", "off")


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


def is_supplement(orid: str, allow=None) -> bool:
    """Whether an OpenRouter-only entry for a native vendor should be KEPT rather
    than dropped by the inversion. True for ``:free`` tiers (kept automatically —
    they're free and the auto-populate step never picks them into a PAID preset)
    and for ids on the curated allow-list (matched as the full id or its
    ``:free``-stripped base, so listing ``openai/gpt-oss-120b`` also keeps
    ``openai/gpt-oss-120b:free``). Lets popular open/small models the vendor's own
    API doesn't serve stay available, dispatched via OpenRouter."""
    if not orid:
        return False
    if orid.endswith(":free"):
        return True
    allow = allow or set()
    return orid in allow or (orid + ":free") in allow


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
    # OpenAI non-chat surfaces (bare /models records carry no type/caps, so the
    # regex is load-bearing here): moderation, the Realtime audio API, the
    # search tool endpoint, and the legacy completion engines. gpt-realtime is
    # SCOPED to OpenAI — it must NOT match Qwen's omni-realtime multimodal-chat
    # models. lyria = Google music generation (not chat).
    r"\bmoderation\b|gpt-realtime|search-api|\bdavinci\b|\bbabbage\b|\blyria\b|"
    # Google non-chat products: Veo (video), Nano Banana (image gen), AQA
    # (attributed-QA retrieval), Robotics-ER, Deep Research + Antigravity
    # (agentic products, not chat-completion models).
    r"\bveo\b|nano-banana|\baqa\b|robotics|deep-research|antigravity|"
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
_DATE = re.compile(r"-(?:v\d+-)?(?:\d{4}-\d{2}-\d{2}|\d{2}-\d{4}|\d{2}-\d{2}|\d{3,8})(?:-preview)?$")
# Google appends a preview channel AFTER the date-less stem
# (gemini-2.5-flash-preview-05-20, -preview, -exp); the OR/AA twin is the plain
# stem, so this tail must peel for the match to land. Scoped to -preview[-MM-DD]
# / -exp so it can't touch a real model suffix.
_PREVIEW = re.compile(r"-(?:preview(?:-\d{2}-\d{2})?|exp|experimental)$", re.I)
# Only a floating-pointer tail. NOT -fast/-highspeed (distinct serving tiers
# with their OWN pricing — collapsing them attaches one's price to the other),
# and NOT -instruct/-thinking/-reasoning/-chat/-it (genuinely different siblings).
_VARIANT = re.compile(r"-(latest)$", re.I)


def _norm(s: str) -> str:
    """Loose normalization: collapse date / preview / -latest tails so a native
    id matches its undated AA/OR twin. Used as the FALLBACK enrichment tier."""
    s = (s or "").lower()
    if s.startswith("models/"):
        s = s[7:]
    prev = None
    while prev != s:  # peel repeated date / preview / variant tails
        prev = s
        s = _VARIANT.sub("", _PREVIEW.sub("", _DATE.sub("", s)))
    return re.sub(r"[^a-z0-9]", "", s)


def _norm_exact(s: str) -> str:
    """Precise normalization: case + separator only, NO date/preview/variant
    collapse. The primary enrichment tier — a dated or -fast/-highspeed sibling
    matches its OWN metadata row, so first-wins can't misattach a different
    model's price/intelligence/vision (e.g. claude-opus-4-8 vs -4.8-fast,
    gpt-4o-2024-05-13 vs -2024-11-20, gemini-flash-lite vs its -preview)."""
    s = (s or "").lower()
    if s.startswith("models/"):
        s = s[7:]
    return re.sub(r"[^a-z0-9]", "", s)


def _enrich_index(vendor_id: str, items) -> dict:
    """{normalized native slug → enrichment record} from AA/OR entries whose key
    is ``<prefix>/<model>`` for this vendor's prefixes. ``items`` is an iterable
    of (key, record).

    Holds BOTH tiers: precise keys (``_norm_exact``) added first so they win,
    then loose keys (``_norm``) fill the gaps. merge_entry looks up precise-first
    so a sibling matches its own row before falling back to the date-collapsed
    twin — preventing the first-wins cross-attach across date/-fast siblings."""
    pfx = set(_prefixes(vendor_id))
    rows = []
    for key, rec in items:
        k = (key or "").lstrip("~")  # AA carries ~-prefixed alias rows
        if "/" not in k:
            continue
        head, rest = k.split("/", 1)
        if head not in pfx:
            continue
        rows.append((rest, rec))
    idx: dict = {}
    for rest, rec in rows:           # precise tier wins
        pe = _norm_exact(rest)
        if pe:
            idx.setdefault(pe, rec)
    for rest, rec in rows:           # loose tier fills gaps only
        ns = _norm(rest)
        if ns:
            idx.setdefault(ns, rec)
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


def _classify_size(vendor_id: str, nid: str, size_rules):
    """Fallback size_bucket from name-pattern rules (config/family-classification
    .json) for flagship ids with no parameter count. ``size_rules`` is keyed by
    the AA/OpenRouter vendor prefix (google, x-ai, moonshotai…), so we look up
    via this vendor's prefix aliases. Rules are ordered most-specific-first
    (flash-lite before flash). Returns None when unclassified."""
    if not size_rules:
        return None
    low = (nid or "").lower()
    for alias in _prefixes(vendor_id):
        rules = size_rules.get(alias)
        if not isinstance(rules, list):
            continue
        for rule in rules:
            pat = (rule.get("pattern") or "").lower()
            if pat and pat in low:
                return rule.get("size_bucket")
    return None


def _legacy_ids(vendor_id: str, nid: str) -> list[str]:
    """Pre-inversion id forms that should resolve to this entry. The inversion
    changed the registry key namespace (google/→gemini/, x-ai/→xai/,
    moonshotai/→moonshot/, minimax/minimax-m3→minimax/MiniMax-M3, dotted→hyphen
    claude-opus-4.8→claude-opus-4-8, dated claude-opus-4-5-20251101). Saved
    config/preset ids still use the old forms and would otherwise read as
    DEPRECATED. Generated at build time where the full id is known, so the
    mapping is deterministic and unambiguous (no fuzzy lookup needed)."""
    canonical = f"{vendor_id}/{nid}"
    leaves = {nid, nid.lower()}
    # dotted <-> hyphen between digits: claude-opus-4-8 <-> claude-opus-4.8
    leaves.add(re.sub(r"(\d)-(\d)", r"\1.\2", nid))
    leaves.add(re.sub(r"(\d)\.(\d)", r"\1-\2", nid))
    # undated stem (+ its dotted/lower forms): claude-opus-4-5-20251101 -> 4-5/4.5
    undated = _DATE.sub("", nid)
    if undated != nid:
        leaves.add(undated)
        leaves.add(undated.lower())
        leaves.add(re.sub(r"(\d)-(\d)", r"\1.\2", undated))
    # date format variants:
    #   -YYYY-MM-DD <-> -YYYYMMDD (config pins use either)
    #   -YYYY-MM-DD -> -MM-DD (some OpenRouter ids omit the year while the
    #     native vendor catalogue includes it; Qwen3.5 Flash is one example)
    for lf in list(leaves):
        leaves.add(re.sub(r"-(\d{4})-(\d{2})-(\d{2})\b", r"-\1\2\3", lf))   # hyphen → compact
        leaves.add(re.sub(r"-(\d{4})(\d{2})(\d{2})\b", r"-\1-\2-\3", lf))   # compact → hyphen
        leaves.add(re.sub(r"-(\d{4})-(\d{2})-(\d{2})\b", r"-\2-\3", lf))     # full → short
    prefixes = set(_prefixes(vendor_id)) | {vendor_id}
    out = set()
    for p in prefixes:
        for lf in leaves:
            cand = f"{p}/{lf}"
            if cand != canonical:
                out.add(cand)
    return sorted(out)


# Known vision-capable families, for ids-only native records with no caps dict
# and no enrichment match (the common case). Negations (text-only siblings)
# precede their family's positive rule and win. CONSERVATIVE on purpose: a false
# True can be picked into the VISUAL slot and silently break image input, whereas
# a None still SHOWS in the lenient inventory filter — so we only assert True for
# families with well-established image input.
_VISION_RULES = [
    # text-only siblings / variants excluded up front (negations win)
    (re.compile(r"claude-3[.-]5-haiku|claude-3-haiku", re.I), False),
    (re.compile(r"-search-preview|-search\b", re.I), False),  # web-search variant, text-only
    # OpenAI multimodal (4o / 4.1 / 4-turbo / 4-vision / chatgpt-4o / gpt-5.x).
    # gpt-4[.-]1\b is anchored so it matches gpt-4.1 but NOT gpt-4-1106 (text-only).
    (re.compile(r"gpt-4o|gpt-4[.-]1\b|gpt-4-turbo|gpt-4-vision|chatgpt-4o|gpt-5", re.I), True),
    # Google Gemini 1.5+/2.x/3.x are all multimodal
    (re.compile(r"gemini-(?:1[.-]5|2[.-]|3[.-])", re.I), True),
    # Anthropic Claude 3 / 3.7 / 4.x (3.5/3-haiku handled above)
    (re.compile(r"claude-3|claude-(?:opus|sonnet|haiku)-4|claude-4", re.I), True),
    # Meta Llama vision
    (re.compile(r"llama-3[.-]2-(?:11b|90b)|llama-4|maverick|scout", re.I), True),
    # Mistral vision — Pixtral only (mistral-medium vision left to OR accepts_image
    # enrichment, since the dated -2xxx snapshots span both text and vision lines)
    (re.compile(r"pixtral", re.I), True),
    # xAI Grok vision
    (re.compile(r"grok-2-vision|grok-4|grok-vision", re.I), True),
]


def _vision_family(low: str):
    for rx, val in _VISION_RULES:
        if rx.search(low):
            return val
    return None


def _vision(nat: dict, aa: dict, orr: dict, nid: str):
    """Best-effort vision_capable for a native entry: native capability flags →
    AA/OpenRouter enrichment → id heuristic → known-vision-family table. None
    when genuinely unknown.

    The Models pane's VISUAL slot gate requires ``vision_capable === true``;
    without this, native multimodal models (qwen3-vl, gemini, gpt-5) are wrongly
    excluded from that slot. (The general inventory Vision chip is lenient and
    shows None too — only definite False is hidden.)
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
    # AUTHORITATIVE NEGATIVE: OpenRouter accepts_image=False is reliable and must
    # beat the family heuristic, so a non-vision variant in a vision family
    # (e.g. gpt-4o-search-preview) isn't over-claimed. (AA's vision flag is less
    # reliable — its False is checked AFTER the family table, below.)
    if orr.get("accepts_image") is False:
        return False
    low = (nid or "").lower()
    # id heuristic — but NOT for moderation endpoints (omni-moderation matches
    # 'omni-' yet is text classification, not vision).
    if "moderation" not in low and any(
        t in low for t in ("-vl", "vl-", "-omni", "omni-", "vision", "multimodal")
    ):
        return True
    fam = _vision_family(low)
    if fam is not None:
        return fam
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


def merge_entry(vendor_id: str, native_rec, aa_idx: dict, or_idx: dict,
                size_rules=None) -> dict:
    """Produce one inventory entry for a native model, native-first per field."""
    nid = (native_rec.get("id") if isinstance(native_rec, dict) else str(native_rec)) or ""
    # Google's /models prefixes ids with 'models/'. Strip it so the registry key
    # is single-prefixed (gemini/gemini-2.5-flash, not gemini/models/...) — the
    # double prefix broke config-id matching and vendor grouping. Native dispatch
    # is unaffected (the Gemini API accepts the bare id; direct_catalog also
    # strips it).
    if nid.startswith("models/"):
        nid = nid[7:]
    nat = native_rec if isinstance(native_rec, dict) else {}
    ns = _norm(nid)
    pe = _norm_exact(nid)
    aa = aa_idx.get(pe) or aa_idx.get(ns) or {}     # precise tier first, then loose
    orr = or_idx.get(pe) or or_idx.get(ns) or {}
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
    if size_bucket is None:                    # flagship ids carry no param count
        size_bucket = _classify_size(vendor_id, nid, size_rules)
    vision = _vision(nat, aa, orr, nid)

    return {
        "id": f"{vendor_id}/{nid}",            # registry key (uniform namespace)
        "native_model_id": nid,                # the id actually dispatched
        "also_known_as": _legacy_ids(vendor_id, nid),  # pre-inversion id forms → this entry
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


def build_vendor_entries(vendor_id: str, native_records: list, aa_idx: dict, or_idx: dict,
                         size_rules=None):
    """Return (chat entries, dropped non-chat ids) for one vendor's catalogue."""
    kept, dropped = [], []
    for r in native_records:
        rid = (r.get("id") if isinstance(r, dict) else r)
        if not rid:
            continue  # malformed record (no id) — skip, never abort the build
        (kept if is_chat_model(vendor_id, r) else dropped).append(r)
    entries = [merge_entry(vendor_id, r, aa_idx, or_idx, size_rules) for r in kept]
    drop_ids = [(r.get("id") if isinstance(r, dict) else r) for r in dropped]
    return entries, drop_ids


def build_authoritative_registry(base_models: dict, vendor_catalogs: dict,
                                 or_models: list | None = None, size_rules=None,
                                 supplement_allow=None):
    """Transform the OpenRouter+AA registry into a vendor-authoritative one.

    base_models     : {orid → entry}, the AA-enriched registry (also the AA source)
    vendor_catalogs : {provider_id → [native /models records]} for keyed vendors
    or_models       : the OpenRouter catalog list (fallback price/context)

    Returns ``(new_models, report)``: for each vendor with a catalogue, its
    OpenRouter entries are removed and replaced by native chat entries; other
    vendors pass through unchanged. ``supplement_allow`` is a set of OpenRouter
    ids to KEEP rather than drop (in addition to the automatic ``:free`` rule) —
    popular open/small models the vendor's own API doesn't serve, dispatched via
    OpenRouter and tagged ``supplement``.
    """
    or_models = or_models or []
    supplement_allow = set(supplement_allow or [])
    new = dict(base_models)
    report: dict = {}
    for vendor_id, native_records in vendor_catalogs.items():
        if not native_records:
            continue
        pfx = set(_prefixes(vendor_id))
        removed, kept_supp = [], []
        for k in list(new.keys()):
            if "/" not in k or k.split("/", 1)[0].lstrip("~") not in pfx:
                continue
            if is_supplement(k, supplement_allow):
                ent = new[k]
                if isinstance(ent, dict):
                    ent["supplement"] = True          # OpenRouter-sourced, not native
                    if k.endswith(":free"):
                        ent["is_free"] = True
                kept_supp.append(k)
                continue
            removed.append(k)
        for k in removed:
            new.pop(k, None)
        aa_idx = _enrich_index(vendor_id, base_models.items())
        or_idx = _enrich_index(vendor_id, ((m.get("id", ""), m) for m in or_models))
        entries, dropped = build_vendor_entries(vendor_id, native_records, aa_idx, or_idx,
                                                size_rules)
        for e in entries:
            new[e["id"]] = e
        n = len(entries) or 1
        report[vendor_id] = {
            "openrouter_removed": len(removed),
            "openrouter_supplement_kept": len(kept_supp),
            "native_chat_added": len(entries),
            "non_chat_dropped": len(dropped),
            "dropped_examples": dropped[:10],
            "enrichment_matched": sum(1 for e in entries if e["_enrichment_matched"]),
            "intelligence_coverage": sum(1 for e in entries if e["intelligence_index"] is not None),
            "price_coverage": sum(1 for e in entries if e["pricing"]),
            "count": len(entries),
        }
    return new, report


def _recency_key(cid: str) -> str:
    """Sortable recency token from a canonical id's trailing date, so the NEWEST
    snapshot wins when several claim one contested (undated) alias. Undated ids
    (floating 'latest') sort highest. Within a model family the date format is
    consistent, which is what the comparison relies on."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})$", cid)
    if m:
        return "".join(m.groups())
    m = re.search(r"-(\d{4,8})$", cid)
    if m:
        return m.group(1).ljust(8, "0")
    return "99999999"  # undated → newest


def build_alias_map(models: dict) -> dict:
    """{legacy_id → canonical_id} from every entry's ``also_known_as``.

    Newest-wins on collision (a contested undated alias resolves to the most
    recent snapshot, not insertion order) and NEVER maps a legacy form that is
    itself a live registry key (so an alias can't shadow a real model). The
    Models pane uses this to resolve pre-inversion config/preset ids instead of
    marking them DEPRECATED — exact-then-alias, no fuzzy matching."""
    aliases: dict = {}
    ordered = sorted((models or {}).items(),
                     key=lambda kv: _recency_key(kv[0]), reverse=True)
    for cid, e in ordered:
        if not isinstance(e, dict):
            continue
        legacy_ids = set(e.get("also_known_as") or [])
        vendor_id = e.get("vendor")
        native_id = e.get("native_model_id")
        if vendor_id and native_id:
            legacy_ids.update(_legacy_ids(str(vendor_id), str(native_id)))
        for legacy in sorted(legacy_ids):
            if legacy in models:
                continue  # a real current id — never shadow it
            aliases.setdefault(legacy, cid)  # newest-first iteration → newest wins
    return aliases


def native_direct_entries(models: dict) -> list:
    """The vendor-native direct entries in an authoritative registry
    (``dispatch == "direct"`` with a ``native_model_id``)."""
    return [e for e in (models or {}).values()
            if isinstance(e, dict) and e.get("dispatch") == "direct"
            and e.get("native_model_id")]


__all__ = [
    "FLAG", "enabled", "is_chat_model", "is_supplement", "merge_entry",
    "build_vendor_entries", "build_authoritative_registry",
    "build_alias_map", "native_direct_entries",
]
