#!/usr/bin/env python3
"""De-duplicate routing-config.json endpoints to one canonical per model.

The vendor-catalogue-authoritative inversion left duplicate endpoints: a native
direct endpoint PLUS the superseded OpenRouter-legacy form, dotted-vs-hyphen id
variants, case variants, gemini ``models/`` orphans, compact-vs-dashed date
forms, and a few cross-vendor resold copies (DashScope reselling DeepSeek/GLM).
This collapses each set to a single canonical endpoint and repoints every
reference to it.

What is a DUPLICATE (collapsed): endpoints whose ``model_id`` shares one essence
(vendor-prefix + ``models/`` stripped, dots->hyphens, compact dates dashed,
lowercased) — i.e. the SAME underlying model, differing only in id encoding or
dispatch route. What is KEPT distinct: a floating alias vs a dated pin, GA vs
-preview, -latest vs dated, distinct snapshots — different ``model_id`` essences,
different real dispatch targets.

Canonical selection (highest score wins; tiebreak shortest-then-lexicographic id):
dispatch==direct +100, service!=openrouter +50, no ``/models/`` segment +20,
dispatch set +10, native-vendor id head +5. Cross-vendor groups use an explicit
home-vendor override. When a collapsed endpoint had an OpenRouter path, the
surviving (direct) canonical gets ``openrouter_fallback_model_id`` so dispatch is
behavior-preserving (tries direct, falls back to OpenRouter) — safe whether or
not direct vendor keys are configured.

References are repointed with QUOTE-BOUND exact matching (ids nest — never raw
substring, never case-insensitive, never blind date-normalize) across the
routing-config slot/bucket/assignment sites and every config/configurations/
*.json (excluding *backup*). It aborts if any reference would be left dangling.

Idempotent: re-running on an already-deduped config is a no-op, so it is safe to
chain after scripts/sync_endpoints_from_catalog.py on every registry refresh
(which re-mints the legacy ids) — that makes the cleanup durable.

    python scripts/dedupe_routing_endpoints.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ORA = Path(os.environ.get("ORA_HOME") or (Path.home() / "ora"))
CONFIG = ORA / "config"
ROUTING = CONFIG / "routing-config.json"
ARTIFACT = CONFIG / "model-registry.vendor-authoritative.json"
CONFIGS_DIR = CONFIG / "configurations"

NATIVE_VENDORS = {"gemini", "openai", "anthropic", "mistral", "qwen",
                  "minimax", "moonshot", "xai", "deepseek", "xiaomi"}

# Cross-vendor (same model name resold by another vendor) canonical overrides,
# keyed by model essence -> the endpoint id to KEEP. Decided per the design:
# v4 deepseek lives on its home vendor (direct + referenced); v3.2 + glm have
# their direct path only via DashScope/qwen. Anything not listed falls back to
# the generic score.
CROSS_VENDOR_CANONICAL = {
    "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
    "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
    "deepseek-v3-2": "qwen/deepseek-v3.2",
    "glm-5-1": "qwen/glm-5.1",
}

# Non-endpoint tokens that appear at reference sites but must NEVER be rewritten.
ENGINE_TOKENS = {"gemini-api", "replicate", "stability", "local-diffusers"}


def _essence(model_id: str) -> str:
    s = (model_id or "").lower()
    if s.startswith("models/"):
        s = s[len("models/"):]
    if "/" in s:
        s = s.split("/", 1)[1]            # drop a vendor prefix (x-ai/grok-4.3 -> grok-4.3)
    s = s.replace(".", "-")
    s = re.sub(r"-(\d{4})(\d{2})(\d{2})\b", r"-\1-\2-\3", s)  # 20260420 -> 2026-04-20
    return s


def _vendor_of(eid: str) -> str:
    head = eid.split("/", 1)[0] if "/" in eid else eid
    if head.startswith("openrouter:"):
        head = head[len("openrouter:"):]
    # map OpenRouter vendor prefixes to our native id
    return {"x-ai": "xai", "google": "gemini", "mistralai": "mistral",
            "moonshotai": "moonshot", "alibaba": "qwen", "z-ai": "zai",
            "openrouter": "openrouter"}.get(head, head)


def _score(ep: dict) -> int:
    eid = ep.get("id", "")
    s = 0
    if ep.get("dispatch") == "direct":
        s += 100
    if ep.get("service") != "openrouter":
        s += 50
    if "/models/" not in eid:
        s += 20
    if ep.get("dispatch") is not None:
        s += 10
    head = eid.split("/", 1)[0] if "/" in eid else eid
    if head in NATIVE_VENDORS:
        s += 5
    return s


def _pick_canonical(group: list[dict], essence: str) -> dict:
    vendors = {_vendor_of(e["id"]) for e in group}
    if len(vendors) > 1 and essence in CROSS_VENDOR_CANONICAL:
        forced = CROSS_VENDOR_CANONICAL[essence]
        for e in group:
            if e["id"] == forced:
                return e
    return sorted(group, key=lambda e: (-_score(e), len(e["id"]), e["id"]))[0]


def _has_or_path(ep: dict) -> str | None:
    """The OpenRouter model id this endpoint would dispatch through, if any."""
    if ep.get("openrouter_fallback_model_id"):
        return ep["openrouter_fallback_model_id"]
    if ep.get("service") == "openrouter" or ep.get("dispatch") == "openrouter":
        return ep.get("model_id") or ep["id"]
    return None


def build_plan(routing: dict, aliases: dict) -> dict:
    eps = [e for e in routing.get("endpoints", []) if isinstance(e, dict) and e.get("id")]
    by_id = {e["id"]: e for e in eps}
    groups: dict[str, list[dict]] = {}
    for e in eps:
        groups.setdefault(_essence(e.get("model_id") or e["id"]), []).append(e)

    remove_to_canon: dict[str, str] = {}
    or_fallback_for: dict[str, str] = {}   # canonical id -> OR model id to preserve
    for essence, group in groups.items():
        # Only collapse PURE ENCODINGS — endpoints that dispatch via the same
        # two mechanisms the inversion duplicated across: native `direct` and
        # `openrouter`. NEVER fold in a DISTINCT dispatch target that merely
        # shares a model essence: claude-code:* (dispatch=subscription, no API
        # cost, referenced by campaign configs) and the legacy *-api-* flat-id
        # endpoints (dispatch=null) are separate routes and are preserved.
        group = [e for e in group if e.get("dispatch") in ("direct", "openrouter")]
        if len({e["id"] for e in group}) < 2:
            continue
        canon = _pick_canonical(group, essence)
        for e in group:
            if e["id"] == canon["id"]:
                continue
            remove_to_canon[e["id"]] = canon["id"]
            orm = _has_or_path(e)
            # preserve the OpenRouter route on a direct canonical that lacks one
            if orm and canon.get("dispatch") == "direct" and not canon.get("openrouter_fallback_model_id"):
                or_fallback_for.setdefault(canon["id"], orm)
    return {"by_id": by_id, "remove_to_canon": remove_to_canon,
            "or_fallback_for": or_fallback_for, "group_count": len(groups)}


# ── reference repointing ─────────────────────────────────────────────────────

def _config_files() -> list[Path]:
    return [p for p in sorted(CONFIGS_DIR.glob("*.json")) if "backup" not in p.name]


def _repoint_text(text: str, remove_to_canon: dict) -> tuple[str, int]:
    """Quote-bound exact replace of '"removed"' and '"openrouter:removed"'."""
    n = 0
    for removed, canon in remove_to_canon.items():
        for token, repl in ((f'"{removed}"', f'"{canon}"'),
                             (f'"openrouter:{removed}"', f'"{canon}"')):
            if token in text:
                cnt = text.count(token)
                text = text.replace(token, repl)
                n += cnt
    return text, n


def _all_reference_tokens(routing: dict) -> set[str]:
    """Every quote-bound token at a CONSUMER reference site (excludes each
    endpoint's own self-definition). Used for the dangling-ref proof."""
    consumer = dict(routing)
    consumer.pop("endpoints", None)
    toks = set(re.findall(r'"([^"]+)"', json.dumps(consumer)))
    for p in _config_files():
        toks |= set(re.findall(r'"([^"]+)"', p.read_text()))
    return toks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    routing = json.loads(ROUTING.read_text())
    try:
        aliases = json.loads(ARTIFACT.read_text()).get("aliases", {}) or {}
    except Exception:
        aliases = {}

    plan = build_plan(routing, aliases)
    by_id = plan["by_id"]
    remove_to_canon = plan["remove_to_canon"]
    or_fallback_for = plan["or_fallback_for"]

    if not remove_to_canon:
        print('{"removed": 0, "note": "already de-duplicated — nothing to do"}')
        return 0

    # every removed id's canonical must survive
    surviving = set(by_id) - set(remove_to_canon)
    bad = [c for c in remove_to_canon.values() if c not in surviving]
    if bad:
        print(f"ABORT: canonical(s) not surviving: {bad[:5]}", file=sys.stderr)
        return 2

    # repoint references everywhere
    consumer_keys = [k for k in routing if k != "endpoints"]
    consumer_blob = json.dumps({k: routing[k] for k in consumer_keys})
    consumer_blob, routing_refs = _repoint_text(consumer_blob, remove_to_canon)
    repointed = json.loads(consumer_blob)
    for k in consumer_keys:
        routing[k] = repointed[k]

    cfg_edits = {}
    cfg_refs = 0
    for p in _config_files():
        txt = p.read_text()
        new, n = _repoint_text(txt, remove_to_canon)
        if n:
            cfg_edits[p] = new
            cfg_refs += n

    # set OR fallback on surviving canonicals (behavior-preserving)
    for canon_id, orm in or_fallback_for.items():
        if canon_id in by_id:
            by_id[canon_id]["openrouter_fallback_model_id"] = orm

    # remove the collapsed endpoints
    routing["endpoints"] = [e for e in routing["endpoints"]
                            if not (isinstance(e, dict) and e.get("id") in remove_to_canon)]

    # ── dangling-ref proof: every consumer token resolves to a surviving id,
    # a self-resolving openrouter:/local synth token, or a pre-existing baseline.
    # Collect tokens from the POST-edit state: the repointed routing consumer
    # sites + each config's repointed text (cfg_edits) or original if untouched.
    surviving_ids = {e["id"] for e in routing["endpoints"] if isinstance(e, dict)}
    toks = set(re.findall(r'"([^"]+)"',
                          json.dumps({k: routing[k] for k in consumer_keys})))
    for p in _config_files():
        toks |= set(re.findall(r'"([^"]+)"', cfg_edits.get(p) or p.read_text()))
    new_dangle = []
    for t in toks:
        if t in surviving_ids:
            continue
        if t in ENGINE_TOKENS or t.startswith("openrouter:") or t.startswith("local-mlx") \
           or t.startswith("claude-code:") or "/" not in t:
            continue
        # was it a removed id we failed to repoint?
        if t in remove_to_canon:
            new_dangle.append(t)
    if new_dangle:
        print(f"ABORT: {len(new_dangle)} removed ids still referenced (repoint miss): "
              f"{sorted(new_dangle)[:8]}", file=sys.stderr)
        return 3

    summary = {
        "endpoints_before": len(by_id),
        "removed": len(remove_to_canon),
        "endpoints_after": len(routing["endpoints"]),
        "config_files_edited": len(cfg_edits),
        "config_refs_repointed": cfg_refs,
        "routing_refs_repointed": routing_refs,
        "or_fallbacks_set": len(or_fallback_for),
    }
    print(json.dumps(summary, indent=2))
    print("\nremovals (removed -> canonical):")
    for r, c in sorted(remove_to_canon.items()):
        print(f"  {r:46} -> {c}")
    if or_fallback_for:
        print("\nOpenRouter fallback preserved on canonicals:")
        for c, orm in sorted(or_fallback_for.items()):
            print(f"  {c:42} or_fallback={orm}")

    if args.dry_run:
        print("\n(dry-run — nothing written)")
        return 0

    # atomic writes
    def _atomic(path: Path, text: str):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text)
        os.replace(tmp, path)

    _atomic(ROUTING, json.dumps(routing, indent=2))
    for p, new in cfg_edits.items():
        _atomic(p, new)
    print(f"\nwrote {ROUTING} + {len(cfg_edits)} config file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
