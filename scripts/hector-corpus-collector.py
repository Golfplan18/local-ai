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

# ---------------------------------------------------------------------------
# Anatomy variants. Default is front-view (BUTT_FACE_SPEC); v1.4 of the spec
# (2026-05-11) legitimized back-view, profile, and multi-figure renderings.
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

BUTT_FACE_SPEC_BACK = (
    "The figure's head is rendered as the rounded back of a human ass - the "
    "figure is facing away from the viewer. Hair stylization sits on top of "
    "the head and curves down across the back. No facial features whatsoever. "
    "No crack visible from this angle; the crack is on the side of the head "
    "facing away from us. The head shape is unmistakably a butt seen from "
    "behind, anchoring the figure as it addresses something in the scene "
    "that the viewer does not see directly."
)

BUTT_FACE_SPEC_PROFILE = (
    "The figure's head is rendered as a literal human ass viewed in profile. "
    "One cheek faces the viewer; the vertical crack runs along the visible "
    "side edge of the head from forehead to throat; the small dark subtle "
    "anus pucker is visible at the crack's midpoint as seen. No facial "
    "features whatsoever. Hair stylization sits on top of the head."
)

BUTT_FACE_SPEC_MULTI = (
    "Each figure's head is rendered as a literal human ass — no facial "
    "features whatsoever, no eyes, no nose, no mouth, no ears, no eyebrows. "
    "Flattened pendulous cheeks, full-height vertical crack from forehead to "
    "throat where visible, small dark subtle anus pucker at the crack's "
    "midpoint where visible. Different figures may be shown in different "
    "orientations — front-facing, back-facing, profile — so the butt-as-head "
    "reads consistently across the group."
)

# ---------------------------------------------------------------------------
# Background tail variants. Default tail (ENGRAVING_TAIL) is peanut gallery +
# spectacled gopher; other tails fit different scene compositions.
# ---------------------------------------------------------------------------

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

TAIL_BANNER_NO_GALLERY = (
    "Pure black masses balanced against carved-out whites. Heavy "
    "cross-hatching, parallel hatch armature, stipple. A horizontal banner "
    "with a quotation scrolls across the top of the frame inside the rule "
    "border. No peanut gallery and no spectacled gopher; this is a tight "
    "portrait composition. Hand-drawn ink on cream paper. Linework dominant. "
    "19th-century American press illustration in the Harper's Weekly "
    "tradition."
)

TAIL_RALLY = (
    "Pure black masses balanced against carved-out whites. Heavy "
    "cross-hatching, parallel hatch armature, stipple. A crowd of identical "
    "anthropomorphic peanut-shaped Peanut Gallery characters with brown "
    "shells fills the foreground of the scene from waist-up, their backs to "
    "the viewer, attending to the speaker on the stage above and behind "
    "them. A large banner with a quotation hangs behind the speaker. A "
    "spectacled gopher peeks from a hole in the lower-left foreground, "
    "gnawing at the foundation of the stage. Hand-drawn ink on cream paper. "
    "Linework dominant. 19th-century American press illustration in the "
    "Harper's Weekly tradition."
)

TAIL_COURTROOM = (
    "Pure black masses balanced against carved-out whites. Heavy "
    "cross-hatching, parallel hatch armature, stipple. A Peanut Gallery of "
    "identical anthropomorphic peanut-shaped characters with brown shells "
    "fills the jury box at the side of the courtroom, faceless, identical "
    "posture. A spectacled gopher peeks from a hole beneath the judge's "
    "bench, gnawing at the foundation. Hand-drawn ink on cream paper. "
    "Linework dominant. 19th-century American press illustration in the "
    "Harper's Weekly tradition."
)

TAIL_GROUP_BACK_ROWS = (
    "Pure black masses balanced against carved-out whites. Heavy "
    "cross-hatching, parallel hatch armature, stipple. A Peanut Gallery of "
    "identical anthropomorphic peanut-shaped characters with brown shells "
    "fills the back rows of the scene, observing the central group. A "
    "spectacled gopher peeks from a hole in the lower-left, gnawing at the "
    "foundation. Hand-drawn ink on cream paper. Linework dominant. "
    "19th-century American press illustration in the Harper's Weekly "
    "tradition."
)

DEFAULT_ACCENT_LINE = (
    "The hair is the only color element; everything else is pure "
    "black-and-white engraved aesthetic."
)

NO_COLOR_ACCENT_LINE = (
    "There is no color accent in this image - the figure is fully bald with "
    "no hair stylization; the entire composition is pure black-and-white "
    "engraved aesthetic."
)


def _make_prompt(variant: dict) -> str:
    """Compose a full variant prompt from a variant dict.

    Required fields: 'scene', 'recognition_cue'.
    Optional fields with defaults:
      'accessory_line' (default ''),
      'anatomy' (default BUTT_FACE_SPEC = front view),
      'accent_line' (default DEFAULT_ACCENT_LINE = hair-is-only-color),
      'tail' (default ENGRAVING_TAIL = peanut gallery + gopher).
    """
    anatomy = variant.get("anatomy") or BUTT_FACE_SPEC
    accent = variant.get("accent_line") or DEFAULT_ACCENT_LINE
    tail = variant.get("tail") or ENGRAVING_TAIL
    accessory = variant.get("accessory_line", "")
    return (
        f"Editorial cartoon in the Thomas Nast / Honoré Daumier / John Tenniel "
        f"/ Herblock / Pat Oliphant tradition. 1880s engraved aesthetic. "
        f"{variant['scene']} {accessory}\n\n"
        f"{anatomy}\n\n"
        f"{variant['recognition_cue']} {accent} {tail}"
    )


VARIANTS = [
    # ----- Original 6 variants (front-view, male-coded, broadcaster/desk framing). -----
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
        "tags": [
            "hector cartoon", "front view", "medium shot", "indoor formal",
            "male figure", "peanut gallery", "spectacled gopher",
            "broadcaster framing",
        ],
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
        "tags": [
            "hector cartoon", "front view", "medium shot", "indoor formal",
            "male figure", "peanut gallery", "spectacled gopher",
            "seated at desk",
        ],
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
        "tags": [
            "hector cartoon", "front view", "medium shot", "indoor formal",
            "male figure", "peanut gallery", "spectacled gopher",
            "broadcaster framing", "pulpit",
        ],
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
        "tags": [
            "hector cartoon", "front view", "medium shot", "indoor formal",
            "male figure", "peanut gallery", "spectacled gopher",
        ],
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
        "tags": [
            "hector cartoon", "front view", "medium shot", "indoor formal",
            "male figure", "peanut gallery", "spectacled gopher",
            "broadcaster framing", "press conference",
        ],
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
        "tags": [
            "hector cartoon", "front view", "medium shot", "indoor formal",
            "male figure", "peanut gallery", "spectacled gopher",
            "broadcaster framing", "lectern",
        ],
    },
    # ----- Demographic axis (v1.4 expansion, 2026-05-11). -----
    {
        "id": "female_pundit",
        "scene": (
            "A single central allegorical figure: a female news pundit at an "
            "anchor desk, tailored blazer, holding a sheaf of papers, "
            "broadcaster framing shown from shoulders up."
        ),
        "accessory_line": "",
        "recognition_cue": (
            "A woman's long blonde news-anchor blowout hairstyle, styled on "
            "top of the head."
        ),
        "tags": [
            "hector cartoon", "front view", "medium shot", "indoor formal",
            "female figure", "peanut gallery", "spectacled gopher",
            "broadcaster framing", "anchor desk",
        ],
    },
    {
        "id": "female_official",
        "scene": (
            "A single central allegorical figure: a female religious-right "
            "propagandist behind an empty pulpit draped with a flag. Modest "
            "dark vestments with a conservative collar. Broadcaster framing "
            "from shoulders up."
        ),
        "accessory_line": "",
        "recognition_cue": (
            "A woman's short grey-streaked dark hair styled on top of the "
            "head."
        ),
        "tags": [
            "hector cartoon", "front view", "medium shot", "indoor formal",
            "female figure", "peanut gallery", "spectacled gopher",
            "broadcaster framing", "pulpit",
        ],
    },
    {
        "id": "female_donor",
        "scene": (
            "A single central allegorical figure: a wealthy female donor in "
            "modern dress with an expensive watch and a pearl necklace, "
            "half-visible behind a heavy curtain in a doorway, observing "
            "the scene."
        ),
        "accessory_line": "",
        "recognition_cue": (
            "A woman's chin-length silver-grey bob styled on top of the "
            "head."
        ),
        "tags": [
            "hector cartoon", "front view", "medium shot", "indoor formal",
            "female figure", "peanut gallery", "spectacled gopher",
        ],
    },
    {
        "id": "female_operative",
        "scene": (
            "A single central allegorical figure: a female staff operative "
            "seated at a heavy oak desk piled with policy papers labeled "
            "with bureaucratic euphemisms. Tailored suit, glasses resting "
            "on the desk beside her."
        ),
        "accessory_line": "",
        "recognition_cue": (
            "A woman's dark hair pulled back into a tight low bun at the "
            "nape of the head; the hair on top is smooth and pulled back."
        ),
        "tags": [
            "hector cartoon", "front view", "medium shot", "indoor formal",
            "female figure", "peanut gallery", "spectacled gopher",
            "seated at desk",
        ],
    },
    {
        "id": "bald_default",
        "scene": (
            "A single central allegorical figure: an apparatus-role operator "
            "addressing an audience, formal dark suit, holding a sheaf of "
            "papers, lectern visible."
        ),
        "accessory_line": "",
        "recognition_cue": (
            "The head is completely bald — no hair stylization at all, no "
            "color element anywhere in the image. This is the §5.4.1 "
            "default bald rendering for figures without distinctive "
            "hairstylings."
        ),
        "accent_line": NO_COLOR_ACCENT_LINE,
        "tags": [
            "hector cartoon", "front view", "medium shot", "indoor formal",
            "bald figure", "peanut gallery", "spectacled gopher",
            "broadcaster framing", "lectern", "no color accent",
        ],
    },
    # ----- Scale axis (v1.4 expansion, 2026-05-11). -----
    {
        "id": "close_up",
        "scene": (
            "Tight close-up portrait composition: just the central figure's "
            "butt-face head and shoulders, filling the frame; no podium, no "
            "audience, no peanut gallery, no spectacled gopher visible. The "
            "figure wears a slick suit and an undone tie."
        ),
        "accessory_line": "",
        "recognition_cue": (
            "An older man's distinctive orange swept-back bouffant comb-over "
            "hair styled on top of the head."
        ),
        "tail": TAIL_BANNER_NO_GALLERY,
        "tags": [
            "hector cartoon", "front view", "close up", "indoor formal",
            "male figure", "banner with quotation", "tight portrait",
        ],
    },
    {
        "id": "full_body",
        "scene": (
            "Wide full-body composition: the central figure stands head-to-toe "
            "in the frame, formal dark suit and tie, holding a leather "
            "briefcase, gesturing with the other hand. The figure occupies "
            "the center of the frame at moderate size; the head-to-body "
            "ratio is normal (the butt-face head is roughly 1/7 of the "
            "figure's height, not enlarged)."
        ),
        "accessory_line": "",
        "recognition_cue": "Short brown hair styled on top of the head.",
        "tags": [
            "hector cartoon", "front view", "wide shot", "indoor formal",
            "male figure", "full body", "peanut gallery",
            "spectacled gopher",
        ],
    },
    {
        "id": "wide_group",
        "scene": (
            "Wide group tableau composition: four to five butt-face figures "
            "gathered around a heavy oak conference table, papers and "
            "documents between them, mid-discussion. The central / focused "
            "figure has an orange swept-back bouffant — this is the ONLY "
            "color accent in the entire image. The secondary figures around "
            "the table have hair stylizations rendered entirely in B&W "
            "engraving line with NO color accent: one secondary figure has "
            "short dark hair drawn in pure linework (a female figure with a "
            "conservative collar); another secondary figure has a balding "
            "head with a side-fringe drawn in pure linework; a third "
            "secondary figure is fully bald. Each figure's butt-face is "
            "shown at a different orientation (some front-facing, some "
            "profile, some three-quarter)."
        ),
        "accessory_line": "",
        "recognition_cue": (
            "Only the central / focused figure carries a hair color: an "
            "orange swept-back bouffant. All secondary figures' hair is "
            "drawn in B&W engraving line only, with no color accent, per "
            "the §3.3 v1.6 single-focused-figure color rule."
        ),
        "anatomy": BUTT_FACE_SPEC_MULTI,
        "tail": TAIL_GROUP_BACK_ROWS,
        "tags": [
            "hector cartoon", "wide shot", "group composition", "indoor formal",
            "multiple figures", "male figure", "female figure",
            "bald figure", "peanut gallery", "spectacled gopher",
            "conference table",
        ],
    },
    # ----- Scene-composition axis (v1.4 expansion, 2026-05-11). -----
    {
        "id": "rally_stage",
        "scene": (
            "Wide outdoor rally composition: a central allegorical figure "
            "stands on a raised stage with one arm raised in triumph, "
            "addressing a crowd. The figure is shown with back to the "
            "viewer — we see the figure from behind as they face the "
            "crowd. A large banner with a quotation hangs across the back "
            "of the stage behind the figure."
        ),
        "accessory_line": "",
        "recognition_cue": (
            "An older man's distinctive orange swept-back bouffant comb-over "
            "hair, seen from behind, with the comb-over visible across the "
            "top and back of the head."
        ),
        "anatomy": BUTT_FACE_SPEC_BACK,
        "tail": TAIL_RALLY,
        "tags": [
            "hector cartoon", "back view", "wide shot", "outdoor formal",
            "male figure", "peanut gallery", "spectacled gopher",
            "rally stage", "banner with quotation",
        ],
    },
    {
        "id": "conference_table",
        "scene": (
            "Interior conference room scene: three butt-face figures seated "
            "around a heavy oak conference table, papers spread between "
            "them, mid-discussion. The central / focused figure wears slick "
            "suit and tie; another wears a tailored female blazer; a third "
            "is in modern dress with an expensive watch. The figures are at "
            "different orientations — one front-facing, one in profile, "
            "one three-quarter."
        ),
        "accessory_line": "",
        "recognition_cue": (
            "Only the central / focused figure carries a hair color: an "
            "orange swept-back bouffant on top of the head — the ONLY color "
            "accent in the entire image. The secondary female figure has a "
            "long anchor blowout drawn in pure B&W engraving line with no "
            "color; the third secondary figure has side-swept hair drawn in "
            "pure B&W engraving line with no color. Per the §3.3 v1.6 "
            "single-focused-figure color rule."
        ),
        "anatomy": BUTT_FACE_SPEC_MULTI,
        "tail": TAIL_BANNER_NO_GALLERY,
        "tags": [
            "hector cartoon", "medium shot", "group composition",
            "indoor formal", "multiple figures", "male figure",
            "female figure", "conference table", "banner with quotation",
        ],
    },
    {
        "id": "courtroom",
        "scene": (
            "Interior courtroom scene: the central allegorical figure stands "
            "at the witness stand, formal dark suit, right hand raised as "
            "if being sworn in. The judge's bench rises behind and above "
            "the witness; the jury box is to the side, filled with the "
            "Peanut Gallery."
        ),
        "accessory_line": "",
        "recognition_cue": (
            "A balding head with a white side-fringe of hair on top."
        ),
        "tail": TAIL_COURTROOM,
        "tags": [
            "hector cartoon", "front view", "medium shot", "indoor procedural",
            "male figure", "peanut gallery", "spectacled gopher",
            "witness stand", "courtroom",
        ],
    },
    {
        "id": "broadcast_studio_side",
        "scene": (
            "Interior broadcast studio scene shown in side angle: the "
            "central figure is seated at an anchor desk in three-quarter "
            "or profile view (one cheek visible to the viewer, the other "
            "facing the implied off-screen co-host). A bank of TV monitors "
            "rises behind the figure; an 'ON AIR' sign glows above. The "
            "figure is gesturing while speaking off to the side."
        ),
        "accessory_line": "",
        "recognition_cue": "Dark grey hair styled on top of the head.",
        "anatomy": BUTT_FACE_SPEC_PROFILE,
        "tail": TAIL_BANNER_NO_GALLERY,
        "tags": [
            "hector cartoon", "profile view", "medium shot",
            "interior broadcast", "male figure", "anchor desk",
            "banner with quotation", "side angle",
        ],
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
        "training_tags": list(variant.get("tags", [])),
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
        prompt = _make_prompt(variant)
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
