#!/usr/bin/env python3
"""Hector training-corpus collector.

Cycles gpt-image-1 through six §5.4.1-compliant prompt variants until N
successful renders are saved. Each output lands in
``~/ora/data/hector-training-corpus/`` as a numbered PNG + sidecar JSON
carrying the prompt, model, timestamp, scene type, recognition cue, and
a vetting field the publisher flips manually before training.

Why: the §5.4.1 paraphrased prompt clears OpenAI moderation roughly 2-of-3
times. Variant phrasings appear to clear at different rates. This script
treats each variant as a candidate and retries on rejection, accumulating
gold-standard renders for downstream Civitai LoRA training.

Usage
-----

    python3 ~/ora/scripts/hector-corpus-collector.py --target 30

    # Smaller test run:
    python3 ~/ora/scripts/hector-corpus-collector.py --target 5

    # Stop after N attempts regardless of successes:
    python3 ~/ora/scripts/hector-corpus-collector.py --target 30 --max-attempts 80

Operational notes
-----------------

* Requires ``ora/openai-api-key`` in the system keyring.
* Prints per-attempt status (rejected vs saved) so you can monitor.
* Refusal messages from OpenAI are logged to corpus/refusals.jsonl
  so we can analyze which phrasings trip the moderation lottery.
* The vetting workflow: open each PNG, edit its sidecar JSON to set
  ``vetted: "yes"`` or ``vetted: "no"`` based on §5.4.1 spec compliance.
  Default is ``vetted: "pending"`` — only ``yes``-marked entries should
  be uploaded as Civitai LoRA training material.

The six variants cover the framework Layer 3 type-accessory subtypes
from `Framework — MSI Hector Rentier Editorial Cartoon.md` §LAYER 3:
pundit, think-tank operative, donor, religious-right propagandist,
corporate-captured figure, plus a generic apparatus-role figure. Each
embeds the butt-face caricature spec verbatim with a different
recognition cue + setting + accessory so the moderation surface area
varies across attempts.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CORPUS_DIR = Path.home() / "ora" / "data" / "hector-training-corpus"
REFUSALS_LOG = CORPUS_DIR / "refusals.jsonl"
MANIFEST = CORPUS_DIR / "manifest.json"

UA = "ora/1.0 (+https://github.com/ora-commons/ora)"
API_URL = "https://api.openai.com/v1/images/generations"
MODEL = "gpt-image-1"


# ---------------------------------------------------------------------------
# Six prompt variants. Each embeds the §5.4.1 butt-face spec verbatim plus
# a scene-specific accessory + recognition cue. The wording is varied across
# variants to spread moderation surface area.
# ---------------------------------------------------------------------------

BUTT_FACE_SPEC = (
    "The figure's head is rendered as a literal human ass viewed from behind "
    "- no facial features whatsoever, no eyes, no nose, no mouth, no ears, no "
    "eyebrows. Two flattened pendulous cheeks falling outward and downward "
    "from a vertical crack that runs the full height of the head from forehead "
    "to throat. At the crack's midpoint there is a small dark subtle pucker, "
    "restrained and unmistakable - the load-bearing marker that distinguishes "
    "this head from a chest."
)

ENGRAVING_TAIL = (
    "Pure black masses balanced against carved-out whites throughout the rest "
    "of the composition. Heavy cross-hatching, parallel hatch armature, "
    "stipple. A Peanut Gallery of identical anthropomorphic peanut-shaped "
    "characters with brown shells, faceless, identical posture, like Mr. "
    "Peanut figures attending the scene. A spectacled gopher peeks from a "
    "hole in the lower-left, gnawing at the foundation. Hand-drawn ink on "
    "cream paper. Linework dominant. 19th-century American press illustration "
    "in the Harper's Weekly tradition."
)


def _make_prompt(scene: str, accessory_line: str, recognition_cue: str) -> str:
    """Compose a full variant prompt from the scene + accessory + cue."""
    return (
        f"Editorial cartoon in the Thomas Nast / Honoré Daumier / John Tenniel "
        f"/ Herblock / Pat Oliphant tradition. 1880s engraved aesthetic. "
        f"{scene} {accessory_line}\n\n"
        f"{BUTT_FACE_SPEC}\n\n"
        f"{recognition_cue} The hair is the only color element; everything "
        f"else is pure black-and-white engraved aesthetic. "
        f"{ENGRAVING_TAIL}"
    )


VARIANTS = [
    {
        "id": "pundit",
        "scene": (
            "A single central allegorical figure: a pundit at a podium, "
            "slick suit, undone tie, holding a microphone, back-lit by TV "
            "camera light, broadcaster framing shown from shoulders up."
        ),
        "accessory_line": "",
        "recognition_cue": (
            "An older man's distinctive orange swept-back bouffant comb-over "
            "hair styled on top of the head."
        ),
    },
    {
        "id": "think_tank",
        "scene": (
            "A single central allegorical figure: a think-tank operative "
            "seated at a heavy oak desk piled with policy papers labeled with "
            "bureaucratic euphemisms. Slick suit, sweater vest, glasses "
            "resting on the desk beside him."
        ),
        "accessory_line": "",
        "recognition_cue": "Dark grey hair styled on top of the head.",
    },
    {
        "id": "religious_right",
        "scene": (
            "A single central allegorical figure: a religious-right "
            "propagandist behind an empty pulpit draped with a flag. "
            "Broadcaster framing from shoulders up. Dark formal vestments."
        ),
        "accessory_line": "",
        "recognition_cue": "Black slicked-down hair on top of the head.",
    },
    {
        "id": "donor",
        "scene": (
            "A single central allegorical figure: a wealthy donor in modern "
            "dress with an expensive watch, half-visible behind a heavy "
            "curtain in a doorway, observing the scene."
        ),
        "accessory_line": "",
        "recognition_cue": "Silver-white side-swept hair on top of the head.",
    },
    {
        "id": "corporate",
        "scene": (
            "A single central allegorical figure: a corporate-captured "
            "executive at a press conference, suit and tie with a "
            "brand-mark logo stamped on the lapel, holding papers."
        ),
        "accessory_line": "",
        "recognition_cue": (
            "A balding head with a white side-fringe of hair on top."
        ),
    },
    {
        "id": "generic_apparatus",
        "scene": (
            "A single central allegorical figure: an apparatus-role operator "
            "addressing an audience, formal dark suit, holding a sheaf of "
            "papers, lectern visible."
        ),
        "accessory_line": "",
        "recognition_cue": "Short brown hair styled on top of the head.",
    },
]


def _resolve_api_key() -> str:
    """Pull OpenAI key from keychain."""
    import keyring  # type: ignore

    key = keyring.get_password("ora", "openai-api-key")
    if not key:
        raise SystemExit(
            "OpenAI API key missing. Set with: keyring set ora openai-api-key"
        )
    return key


def _submit(api_key: str, prompt: str, size: str = "1024x1024") -> bytes:
    """Submit one generation. Returns the PNG bytes or raises."""
    body = {
        "model": MODEL,
        "prompt": prompt,
        "size": size,
        "quality": "high",
        "n": 1,
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": UA,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        result = json.loads(resp.read())
    data = result["data"][0]
    raw = data.get("b64_json")
    if raw:
        return base64.b64decode(raw)
    url = data.get("url")
    if url:
        with urllib.request.urlopen(url, timeout=60) as r2:
            return r2.read()
    raise RuntimeError(f"no image in response: {json.dumps(result)[:300]}")


def _log_refusal(variant_id: str, prompt: str, error_body: str) -> None:
    REFUSALS_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "variant_id": variant_id,
        "error_body": error_body,
        "prompt_first_120": prompt[:120],
    }
    with REFUSALS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _next_sequence_number() -> int:
    existing = sorted(CORPUS_DIR.glob("[0-9][0-9][0-9].png"))
    if not existing:
        return 1
    return int(existing[-1].stem) + 1


def _save_corpus_entry(seq: int, variant: dict, prompt: str, img: bytes) -> Path:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"{seq:03d}"
    img_path = CORPUS_DIR / f"{stem}.png"
    meta_path = CORPUS_DIR / f"{stem}.json"
    img_path.write_bytes(img)
    meta = {
        "sequence": seq,
        "image_filename": img_path.name,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "model": MODEL,
        "variant_id": variant["id"],
        "prompt": prompt,
        "byte_size": len(img),
        "vetted": "pending",
        "vetting_notes": "",
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return img_path


def _update_manifest(seq: int, variant_id: str) -> None:
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    else:
        manifest = {"entries": [], "first_run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")}
    manifest["entries"].append(
        {
            "sequence": seq,
            "variant_id": variant_id,
            "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }
    )
    manifest["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    manifest["total_entries"] = len(manifest["entries"])
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        type=int,
        default=30,
        help="Number of successful renders to collect before stopping.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=0,
        help=(
            "Cap on total submissions (rejections + successes). "
            "0 = no cap (run until target reached). "
            "Use to bound spend if moderation rejection rate is high."
        ),
    )
    parser.add_argument(
        "--throttle-seconds",
        type=float,
        default=2.0,
        help="Wait this many seconds between submissions.",
    )
    parser.add_argument(
        "--variant",
        choices=[v["id"] for v in VARIANTS] + ["all"],
        default="all",
        help="Restrict to one variant (debugging) or cycle all variants.",
    )
    args = parser.parse_args()

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    api_key = _resolve_api_key()

    variants_pool = VARIANTS if args.variant == "all" else [v for v in VARIANTS if v["id"] == args.variant]
    if not variants_pool:
        raise SystemExit(f"unknown variant: {args.variant}")

    successes = 0
    rejections = 0
    attempts = 0
    per_variant_stats: dict[str, dict[str, int]] = {v["id"]: {"ok": 0, "fail": 0} for v in VARIANTS}

    print(
        f"[hector-corpus] target={args.target} max_attempts={args.max_attempts or 'unlimited'} "
        f"variant={args.variant} corpus={CORPUS_DIR}"
    )

    next_seq = _next_sequence_number()

    while successes < args.target:
        if args.max_attempts and attempts >= args.max_attempts:
            print(f"[hector-corpus] reached max-attempts cap ({args.max_attempts}); stopping.")
            break
        variant = random.choice(variants_pool)
        prompt = _make_prompt(variant["scene"], variant["accessory_line"], variant["recognition_cue"])
        attempts += 1
        print(
            f"[attempt {attempts:3d}] variant={variant['id']:18s} "
            f"successes={successes}/{args.target} ...",
            end=" ",
            flush=True,
        )
        try:
            img = _submit(api_key, prompt)
            seq = next_seq
            path = _save_corpus_entry(seq, variant, prompt, img)
            _update_manifest(seq, variant["id"])
            per_variant_stats[variant["id"]]["ok"] += 1
            successes += 1
            next_seq += 1
            print(f"OK -> {path.name} ({len(img):,} bytes)")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            _log_refusal(variant["id"], prompt, body[:600])
            per_variant_stats[variant["id"]]["fail"] += 1
            rejections += 1
            short = body[:140].replace("\n", " ")
            print(f"REJECTED HTTP {e.code}: {short}")
        except Exception as e:
            _log_refusal(variant["id"], prompt, f"{type(e).__name__}: {e}")
            per_variant_stats[variant["id"]]["fail"] += 1
            rejections += 1
            print(f"ERROR {type(e).__name__}: {str(e)[:140]}")
        time.sleep(args.throttle_seconds)

    print()
    print(f"[hector-corpus] done. {successes} saved, {rejections} rejected, {attempts} total attempts.")
    print(f"[hector-corpus] per-variant success rates:")
    for vid, s in per_variant_stats.items():
        total = s["ok"] + s["fail"]
        rate = (s["ok"] / total * 100) if total else 0.0
        print(f"  {vid:18s} ok={s['ok']:3d} fail={s['fail']:3d}  rate={rate:5.1f}% (n={total})")
    print()
    print(f"[hector-corpus] next steps:")
    print(f"  1. Review each PNG in {CORPUS_DIR}")
    print(f"  2. Edit the matching <seq>.json to set 'vetted: yes' (compliant)")
    print(f"     or 'vetted: no' (off-spec), with optional 'vetting_notes'.")
    print(f"  3. Upload all vetted=yes images to Civitai's LoRA training UI as")
    print(f"     the corpus for 'Hector Rentier Style v1'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
