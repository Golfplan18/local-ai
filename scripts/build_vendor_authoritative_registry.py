#!/usr/bin/env python3
"""Build a vendor-catalogue-authoritative model registry and report the diff.

PR-A tool. Reads the current OpenRouter+AA registry (config/model-registry.json),
the OpenRouter catalog (config/openrouter-catalog.json), and live-fetches each
keyed, pay-as-you-go direct vendor's own /models. It then produces a
vendor-authoritative registry (vendor catalogues replace those vendors'
OpenRouter entries; AA/OpenRouter metadata matched on field-by-field) and writes
it to a SEPARATE file plus prints an old-vs-new diff. It does NOT modify the live
registry — wiring that in is a later, flag-gated PR.

    python scripts/build_vendor_authoritative_registry.py [--out PATH] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ORA_HOME = Path(os.environ.get("ORA_HOME") or (Path.home() / "ora"))
sys.path.insert(0, str(ORA_HOME / "orchestrator"))

import provider_registry as reg          # noqa: E402
import direct_catalog as dc              # noqa: E402
import vendor_catalog_registry as vcr    # noqa: E402

CONFIG = ORA_HOME / "config"


def _key_for(entry: dict) -> str:
    ev = entry.get("env_var")
    if ev and os.environ.get(ev, "").strip():
        return os.environ[ev].strip()
    try:
        import keyring
        return keyring.get_password("ora", entry["keyring_username"]) or ""
    except Exception:
        return ""


def _fetch_records(entry: dict, key: str) -> list:
    """Full native /models records (not just ids), or [] on failure."""
    req = dc._models_request(entry, key)
    if req is None or not key:
        return []
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as e:
        print(f"  ! {entry['id']}: /models fetch failed: {e}", file=sys.stderr)
        return []
    items = data.get("data") if isinstance(data, dict) else data
    out = []
    for it in (items or []):
        if isinstance(it, dict) and it.get("id"):
            out.append(it)
        elif isinstance(it, str):
            out.append({"id": it})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(CONFIG / "model-registry.vendor-authoritative.json"))
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args()

    base = json.loads((CONFIG / "model-registry.json").read_text())
    base_models = base.get("models") or {}
    try:
        or_models = (json.loads((CONFIG / "openrouter-catalog.json").read_text()).get("models")) or []
    except Exception:
        or_models = []

    vendor_catalogs: dict = {}
    skipped: dict = {}
    for p in reg.catalog_authoritative_providers():
        k = _key_for(p)
        if not k:
            skipped[p["id"]] = "no key"
            continue
        recs = _fetch_records(p, k)
        if not recs:
            skipped[p["id"]] = "catalogue unreachable"
            continue
        vendor_catalogs[p["id"]] = recs

    new_models, report = vcr.build_authoritative_registry(base_models, vendor_catalogs, or_models)

    out = dict(base)
    out["models"] = new_models
    out["_vendor_authoritative"] = True
    out["_authoritative_vendors"] = sorted(vendor_catalogs.keys())
    Path(args.out).write_text(json.dumps(out, indent=2))

    summary = {
        "base_model_count": len(base_models),
        "new_model_count": len(new_models),
        "authoritative_vendors": sorted(vendor_catalogs.keys()),
        "skipped": skipped,
        "per_vendor": report,
        "out": args.out,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    print(f"\nVENDOR-AUTHORITATIVE REGISTRY DIFF")
    print(f"  base models:  {len(base_models)}")
    print(f"  new models:   {len(new_models)}")
    print(f"  authoritative vendors: {', '.join(summary['authoritative_vendors']) or '(none keyed)'}")
    if skipped:
        print(f"  skipped: " + ", ".join(f"{k} ({v})" for k, v in skipped.items()))
    print(f"\n  {'vendor':12} {'OR→':>4} {'+direct':>8} {'-nonchat':>9} {'intel':>7} {'price':>7}")
    for vid, r in report.items():
        c = r["count"] or 1
        print(f"  {vid:12} {r['openrouter_removed']:>4} {r['native_chat_added']:>8} "
              f"{r['non_chat_dropped']:>9} "
              f"{r['intelligence_coverage']:>3}/{r['count']:<3} "
              f"{r['price_coverage']:>3}/{r['count']:<3}")
    print(f"\n  wrote {args.out}")
    print("  (live registry untouched — this is a preview artifact)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
