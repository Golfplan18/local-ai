#!/usr/bin/env python3
"""campaign_run.py — Comparative Evaluation Campaign runner (2026-06-12).

Reproducible capture harness for the 198-entry campaign described in
the vault doc "Working — Campaign Run Plan 2026-06-06" and published on
ora-ai.app. For each selected campaign entry it takes prompt #1 (the prime)
and runs it through six lanes, capturing text, visual artifact,
token usage, and cost:

  premium      — Ora server, campaign-premium configuration (gear 4)
  qwen9b       — Ora server, campaign-qwen9b (qwen/qwen3.5-9b in every slot)
  optimum      — Ora server, campaign-optimum configuration (gear 4)
  optimum-plus — campaign-optimum with ONE upgraded cell: the flagship in
                 the consolidation slot (step 7). Data lane for the
                 "spend your money on the consolidator" hypothesis
                 (experiment 2026-06-12); whether it ships as a preset
                 default is decided AFTER the sweep.
  single-pass  — ONE bare API call to the flagship model, no harness.
                 The flagship is whatever the premium configuration's
                 big-1 slot picked (auto-selected by the same picker
                 algorithm that baked the configs).
  single-pass-9b — ONE bare ~9B call, no harness. Control twin for qwen9b.

Subcommands
-----------
  bake-configs   Re-bake the premium/optimum presets with the live picker
                 algorithm, copy them to campaign-premium / campaign-optimum,
                 generate campaign-qwen9b and campaign-optimum-plus, stamp
                 rag_isolation=web_only on the Ora lanes, and snapshot
                 per-model pricing.
  list           Parse the corpus; print counts + technique ids.
  run            Execute the sweep. --techniques all | some | id[,id...]
                 --pipelines premium,qwen9b,optimum,optimum-plus,single-pass,
                             single-pass-9b
                 Resumable: completed (technique, pipeline) pairs are
                 skipped on re-run via the manifest.
  aggregate      Build cost tables (per pipeline + grand total) from the
                 manifest → cost-summary.md / cost-summary.json.
  render-doc     Assemble the long capture document (one section per
                 campaign entry: prompt, then the six answers + visuals).
  all            bake-configs → run → aggregate → render-doc.

Reproducibility notes for third parties
---------------------------------------
* Requires a running Ora server (./start.sh) and the trigger-prompt
  corpus markdown (default: the vault copy; pass --corpus to point at
  the published copy downloaded from ora-ai.app).
* `bake-configs` derives the model picks from YOUR registry/catalog via
  the same auto-populate algorithm the Models pane uses — so the run
  reflects the models available to you at run time. The pricing snapshot
  in campaign-configs-snapshot.json records what was picked and at what
  per-1M rates.
* single-pass needs an API key: the flagship's direct vendor key when
  you have one (e.g. Anthropic), else your OpenRouter key.
* PNG rasterization needs `pip install playwright && playwright install
  chromium`. Without it the run still captures SVG.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from orchestrator import network_policy

# Resolve relative to the runner's own checkout by default.  ``~/ora`` was a
# historical deployment assumption; it made an accepted-runtime checkout read
# a different repository's traces and falsely fail otherwise valid reruns.
# ORA_HOME remains an explicit override for packaged/custom layouts.
ORA_HOME = Path(
    os.environ.get("ORA_HOME") or Path(__file__).resolve().parent.parent
).resolve()
CONFIG_DIR = ORA_HOME / "config"
CONFIGURATIONS_DIR = CONFIG_DIR / "configurations"


def resolve_campaign_dir(ora_home: Path = ORA_HOME,
                         user_home: Path | None = None,
                         env: dict | None = None) -> Path:
    """Resolve the authoritative append-only campaign store.

    New/check-out-local campaigns live under the checkout.  The completed
    reference campaign predates the accepted runtime checkout and remains at
    ``~/ora/data/campaign``.  Prefer an explicit ORA_CAMPAIGN_DIR, then a local
    manifest, then that historical authoritative manifest.  This keeps code,
    configuration, and trace validation anchored in the accepted checkout
    without requiring the obsolete ORA_HOME override merely to audit evidence.
    """
    source_env = os.environ if env is None else env
    explicit = str(source_env.get("ORA_CAMPAIGN_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    local = Path(ora_home).resolve() / "data" / "campaign"
    if (local / "campaign-manifest.jsonl").is_file():
        return local
    home = Path.home() if user_home is None else Path(user_home)
    historical = home / "ora" / "data" / "campaign"
    if (historical / "campaign-manifest.jsonl").is_file():
        return historical.resolve()
    return local


CAMPAIGN_DIR = resolve_campaign_dir()
CAPTURES_DIR = CAMPAIGN_DIR / "captures"
MANIFEST_PATH = CAMPAIGN_DIR / "campaign-manifest.jsonl"
SNAPSHOT_PATH = CAMPAIGN_DIR / "campaign-configs-snapshot.json"
TRACES_DIR = ORA_HOME / "data" / "pipeline-traces"
RENDER_ENVELOPE_JS = (
    ORA_HOME / "server" / "static" / "ora-visual-compiler" / "tools" / "render-envelope.js"
)
DEFAULT_CORPUS = Path.home() / "Documents" / "vault" / "Projects" / "Ora" / \
    "Reference — Trigger Prompt Corpus.md"
DEFAULT_SERVER = "http://localhost:5000"

ORA_PIPELINES = {
    "premium": "campaign-premium",
    "qwen9b": "campaign-qwen9b",
    "optimum": "campaign-optimum",
    "optimum-plus": "campaign-optimum-plus",
}
ALL_PIPELINES = ["premium", "qwen9b", "optimum", "optimum-plus",
                 "single-pass", "single-pass-9b"]
MAIN_PIPELINES = ["premium", "qwen9b", "optimum", "single-pass"]

# Same pattern orchestrator/visual_adversarial.py uses to find envelopes.
VISUAL_FENCE = re.compile(r"```ora-visual\s*\n(.*?)\n```", re.DOTALL)

# The 'some' subset: a representative spread for a quick self-verification
# run — 4 analysis modes, 4 visual tools, 4 high-recognition lenses.
# 12 techniques × 4 pipelines = 48 captures (vs 792 for the full sweep).
SOME_SUBSET = [
    # analysis modes
    "argument-audit", "cui-bono", "decision-under-uncertainty", "wicked-problems",
    # visual tools
    "ach-matrix", "bow-tie-diagram", "causal-loop-diagram", "decision-tree",
    # lenses
    "anchoring", "availability-heuristic", "incentives", "second-order-thinking",
]

# All ten cell paths a campaign configuration carries (mirrors the
# qwen-9b-only layout — gear2_rag_lookup is optional and inherits).
QWEN9B_CELL_PATHS = [
    ("utility", "step1_cleanup"),
    ("utility", "classification"),
    ("utility", "rag_planner"),
    ("analysis", "gear4", "depth"),
    ("analysis", "gear4", "breadth"),
    ("analysis", "gear3", "depth"),
    ("analysis", "gear3", "breadth"),
    ("post_analysis", "consolidation"),
    ("post_analysis", "verification"),
    ("post_analysis", "formatter"),
]
QWEN9B_MODEL = "qwen/qwen3.5-9b"

# single-pass-9b — the BARE control twin of the qwen9b harness lane: ONE
# unharnessed OpenRouter call to the same 9B model (no framework/system
# injection, no tools, text only). Quantifies, within our own rubric, how much
# the harness lifts the 9B; its cost.json is the same FLAT one-model record the
# single-pass flagship lane writes (not the per-model harness shape).
SINGLE_PASS_9B_MODEL = QWEN9B_MODEL

RAG_NOTE = ("CAMPAIGN-RAG-BYPASS — campaign configurations run with "
            "rag_isolation=web_only so captures reflect a clean install "
            "(no vault/conversation RAG), reproducible by third parties.")

# Subscription-premium (decision 2026-06-12): the premium lane can run on
# the user's Claude subscription via the local Claude Code CLI instead of
# the metered API — same models, zero marginal dollars, throughput
# governed by the subscription's rolling rate windows. Opus carries the
# big + post-analysis slots; Haiku the fast + utility slots (single-family
# adversarial pair — the cross-vendor diversity tradeoff is deliberate).
CLAUDE_CODE_OPUS = "claude-code:claude-opus-4.8"
CLAUDE_CODE_HAIKU = "claude-code:claude-haiku-4.5"
CLAUDE_CODE_ENDPOINTS = [
    {"id": CLAUDE_CODE_OPUS, "model_id": "claude-opus-4-8",
     "display_name": "Claude Opus 4.8 (subscription via Claude Code)",
     "api_equivalent": "anthropic/claude-opus-4.8"},
    {"id": CLAUDE_CODE_HAIKU, "model_id": "claude-haiku-4-5",
     "display_name": "Claude Haiku 4.5 (subscription via Claude Code)",
     "api_equivalent": "anthropic/claude-haiku-4.5"},
]
SUBSCRIPTION_PIPELINES = {"premium"}  # lanes that ride the subscription
                                      # when --premium subscription baked


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─── Corpus parsing ───────────────────────────────────────────────────────


# Visual-tool technique id → the ora-visual envelope ``type`` it should
# produce. Threaded to the server as ``manual_visual_type`` so multi-kind
# modes (decision-under-uncertainty, information-density, process-mapping)
# emit the technique's specific kind instead of the mode's first listed type.
VISUAL_TOOL_KINDS = {
    "ach-matrix": "ach_matrix",
    "bow-tie-diagram": "bow_tie",
    "c4-architecture": "c4",
    "causal-dag": "causal_dag",
    "causal-loop-diagram": "causal_loop_diagram",
    "comparison-chart": "comparison",
    "concept-map": "concept_map",
    "decision-tree": "decision_tree",
    "distribution-plot": "distribution",
    "fishbone-diagram": "fishbone",
    "flowchart": "flowchart",
    "heatmap": "heatmap",
    "ibis-argument": "ibis",
    "influence-diagram": "influence_diagram",
    "pro-con-tree": "pro_con",
    "quadrant-matrix": "quadrant_matrix",
    "scatter-plot": "scatter",
    "sequence-diagram": "sequence",
    "state-diagram": "state",
    "stock-and-flow": "stock_and_flow",
    "time-series": "time_series",
    "tornado-chart": "tornado",
}


@dataclass
class Technique:
    id: str
    kind: str            # "mode" | "visual" | "lens"
    intended_mode: str
    prompt: str
    target_visual: str | None = None   # ora-visual type for "visual" techniques
    key: str = ""        # stable manifest key: "<kind>:<id>"
    capture_slug: str = ""  # filesystem/conversation slug; kind-prefixed on collisions


_BACKTICK_ID = re.compile(r"`([^`]+)`")


def parse_corpus(path: Path) -> list[Technique]:
    """Parse the trigger-prompt corpus into (id, kind, intended_mode,
    prompt #1) records.

    Section shapes (verified against the 2026-06-06 corpus):
      ## Modes (by territory)  → entries at ####, mode line "**Intended mode:**"
      ## Visual tools          → entries at ###,  mode line "**Routes to:**"
      ## Lenses                → entries at ####, mode line "**Host mode:**"
    Prompt #1 is the first numbered list item ("1. …") in the entry.
    """
    text = Path(path).read_text(encoding="utf-8")
    lines = text.split("\n")

    section = None          # None | mode | visual | lens
    entry_id = None
    entry_kind = None
    entry_mode = None
    entry_prompt = None
    out: list[Technique] = []

    def _flush():
        nonlocal entry_id, entry_mode, entry_prompt
        if entry_id:
            if not entry_mode or not entry_prompt:
                raise ValueError(
                    f"corpus entry `{entry_id}` is missing "
                    f"{'a mode line' if not entry_mode else 'prompt #1'}")
            target_visual = (VISUAL_TOOL_KINDS.get(entry_id)
                             if entry_kind == "visual" else None)
            out.append(Technique(entry_id, entry_kind, entry_mode, entry_prompt,
                                 target_visual=target_visual))
        entry_id = entry_mode = entry_prompt = None

    for line in lines:
        if line.startswith("## "):
            _flush()
            h = line[3:].strip()
            if h.startswith("Modes"):
                section = "mode"
            elif h.startswith("Visual tools"):
                section = "visual"
            elif h.startswith("Lenses"):
                section = "lens"
            else:
                section = None
            continue
        if section is None:
            continue
        # Entry headings: visual tools sit at ###; modes/lenses at ####
        # (### inside those sections is a territory grouping, not an entry).
        is_entry = (
            (section == "visual" and line.startswith("### `"))
            or (section in ("mode", "lens") and line.startswith("#### `"))
        )
        if is_entry:
            _flush()
            m = _BACKTICK_ID.search(line)
            entry_id = m.group(1) if m else None
            entry_kind = section
            continue
        if entry_id is None:
            continue
        if entry_mode is None:
            for marker in ("**Intended mode:**", "**Routes to:**", "**Host mode:**"):
                if line.startswith(marker):
                    m = _BACKTICK_ID.search(line[len(marker):])
                    if m:
                        entry_mode = m.group(1)
                    break
        if entry_prompt is None and re.match(r"^1\.\s+", line):
            entry_prompt = re.sub(r"^1\.\s+", "", line).strip()
    _flush()
    counts = {}
    for tech in out:
        counts[tech.id] = counts.get(tech.id, 0) + 1
    for tech in out:
        tech.key = f"{tech.kind}:{tech.id}"
        tech.capture_slug = (
            f"{tech.kind}-{tech.id}" if counts.get(tech.id, 0) > 1 else tech.id
        )
    return out


def select_techniques(all_techniques: list[Technique], spec: str) -> list[Technique]:
    """Resolve --techniques: 'all' | 'some' | comma-separated ids.

    Bare ids are accepted when unique. Colliding ids (e.g. a mode and a visual
    tool with the same public name) must be selected as ``kind:id`` so a resume
    run cannot silently pick the wrong corpus entry.
    """
    by_id: dict[str, list[Technique]] = {}
    by_key = {t.key: t for t in all_techniques}
    for tech in all_techniques:
        by_id.setdefault(tech.id, []).append(tech)
    if spec == "all":
        return list(all_techniques)
    if spec == "some":
        wanted = SOME_SUBSET
    else:
        wanted = [s.strip() for s in spec.split(",") if s.strip()]
    missing = [
        w for w in wanted
        if w not in by_key and (w not in by_id or len(by_id[w]) != 1)
    ]
    if missing:
        ambiguous = [
            f"{w} ({', '.join(t.key for t in by_id[w])})"
            for w in wanted if w in by_id and len(by_id[w]) > 1
        ]
        hint = f"; ambiguous id(s): {', '.join(ambiguous)}" if ambiguous else ""
        raise SystemExit(
            f"unknown technique id(s): {', '.join(missing)} — "
            f"run `campaign_run.py list` for the full catalog{hint}")
    picked = []
    for w in wanted:
        if w in by_key:
            picked.append(by_key[w])
        else:
            picked.append(by_id[w][0])
    return picked


def manifest_key_for_record(rec: dict) -> str:
    """Return the stable technique key for old and new manifest rows."""
    key = rec.get("technique_key")
    if key:
        return key
    kind = rec.get("kind")
    technique = rec.get("technique")
    if kind and technique:
        return f"{kind}:{technique}"
    return technique or ""


def _captures_dir(campaign_dir: Path | None = None) -> Path:
    """Return the capture root for the active or explicitly audited campaign."""
    if campaign_dir is None:
        return CAPTURES_DIR
    return Path(campaign_dir).expanduser().resolve() / "captures"


def capture_output_dir(tech: Technique, pipe: str,
                       campaign_dir: Path | None = None) -> Path:
    """Directory used for new captures.

    ``parse_corpus`` assigns a kind-qualified slug only when a public id
    collides.  That is the writer's existing layout: unique ids use the bare
    id, while duplicate ids get one independent root per kind.
    """
    return _captures_dir(campaign_dir) / (tech.capture_slug or tech.id) / pipe


def _legacy_capture_dir(tech: Technique, pipe: str,
                        campaign_dir: Path | None = None) -> Path:
    return _captures_dir(campaign_dir) / tech.id / pipe


def capture_read_dir(tech: Technique, pipe: str,
                     campaign_dir: Path | None = None) -> Path:
    """Directory used when reading a capture.

    A duplicate id must resolve only to its kind-qualified root.  Falling back
    to ``captures/<id>/<pipeline>`` would make two declared cells read the
    same historical capture.  Unique ids already use that bare path, so their
    legacy layout remains compatible without a special fallback.
    """
    return capture_output_dir(tech, pipe, campaign_dir)


_CAPTURE_REQUIRED_FILES = ("answer.md", "cost.json")

# The capture sidecar. A capture directory that cannot name its own cell
# cannot be checked against one, and a collision in this layer is invisible
# by construction — which is exactly how four duplicate-id cells overwrote
# four others and still audited clean. Every capture now records the cell it
# belongs to and the prompt it answers.
CAPTURE_SIDECAR = "capture.json"
CAPTURE_SIDECAR_SCHEMA = 1

# How the bytes in a capture directory came to be there.
#   direct    — written by this runner from a live model call.
#   recovered — reconstructed from a preserved session transcript after the
#               original capture was lost. Provably the right prompt and the
#               right cell, but no trace survives to hash the request against,
#               so it can never reach ``verified``.
EVIDENCE_DIRECT = "direct"
EVIDENCE_RECOVERED = "recovered"


def prompt_fingerprint(prompt: str) -> str:
    """Stable hash of a corpus prompt, whitespace-normalized.

    Normalizing means a capture does not lose its identity to a reflowed
    corpus line, while any change to the words themselves still breaks the
    match — which is the signal we want.
    """
    normalized = " ".join((prompt or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def read_capture_sidecar(root: Path) -> dict | None:
    """Return the sidecar for a capture directory, or None if unreadable."""
    path = Path(root) / CAPTURE_SIDECAR
    if path.is_symlink() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def claim_capture_dir(tech: Technique, pipe: str, out_dir: Path) -> None:
    """Refuse to write into a directory another cell already owns.

    This is the guarantee behind "every declared cell maps to one independent
    capture root", enforced when the bytes are written rather than discovered
    at audit time. Without it, two cells sharing a directory silently produce
    one surviving answer and two ``ok`` manifest rows.
    """
    existing = read_capture_sidecar(out_dir)
    if not existing:
        return
    owner = existing.get("technique_key")
    expected = tech.key or f"{tech.kind}:{tech.id}"
    if owner and owner != expected:
        raise RuntimeError(
            f"capture directory {out_dir} is owned by {owner}; "
            f"{expected} must not overwrite it")


def write_capture_sidecar(tech: Technique, pipe: str, out_dir: Path,
                          evidence: str = EVIDENCE_DIRECT,
                          source: dict | None = None) -> Path:
    """Record which cell owns this capture and which prompt it answers."""
    payload = {
        "schema_version": CAPTURE_SIDECAR_SCHEMA,
        "technique_key": tech.key or f"{tech.kind}:{tech.id}",
        "technique": tech.id,
        "kind": tech.kind,
        "pipeline": pipe,
        "capture_slug": tech.capture_slug or tech.id,
        "prompt": tech.prompt,
        "prompt_sha256": prompt_fingerprint(tech.prompt),
        "evidence": evidence,
        "written_at": _now_iso(),
    }
    if source:
        payload["source"] = source
    path = Path(out_dir) / CAPTURE_SIDECAR
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def _sidecar_violations(tech: Technique, pipe: str,
                        sidecar: dict) -> list[dict]:
    """Return disagreements between a sidecar and the cell it sits in."""
    violations: list[dict] = []
    expected_key = tech.key or f"{tech.kind}:{tech.id}"
    actual_key = sidecar.get("technique_key")
    if actual_key != expected_key:
        violations.append({
            "kind": "capture_sidecar_key_mismatch",
            "expected": expected_key,
            "actual": actual_key,
            "detail": "capture sidecar names a different cell",
        })
    if sidecar.get("pipeline") != pipe:
        violations.append({
            "kind": "capture_sidecar_key_mismatch",
            "expected": pipe,
            "actual": sidecar.get("pipeline"),
            "detail": "capture sidecar names a different pipeline",
        })
    expected_hash = prompt_fingerprint(tech.prompt)
    actual_hash = sidecar.get("prompt_sha256")
    if actual_hash != expected_hash:
        violations.append({
            "kind": "capture_sidecar_prompt_mismatch",
            "expected": expected_hash,
            "actual": actual_hash,
            "detail": "capture answers a different prompt than the corpus "
                      "declares for this cell",
        })
    return violations


def _manifest_identity_violations(tech: Technique, pipe: str,
                                  rec: dict) -> list[dict]:
    """Return mismatches between a manifest row and its declared cell.

    ``technique_key`` and ``capture_slug`` were added after the first
    campaign runs, so their absence is compatible with older records.  The
    original manifest fields are the cell identity and must always agree.
    """
    expected = {
        "technique": tech.id,
        "kind": tech.kind,
        "pipeline": pipe,
    }
    violations = []
    for field, value in expected.items():
        actual = rec.get(field)
        if actual != value:
            violations.append({
                "kind": "manifest_identity_mismatch",
                "field": field,
                "expected": value,
                "actual": actual,
                "detail": f"manifest {field} does not match declared cell",
            })
    for field, value in (
        ("technique_key", tech.key or f"{tech.kind}:{tech.id}"),
        ("capture_slug", tech.capture_slug or tech.id),
    ):
        actual = rec.get(field)
        if actual is not None and actual != value:
            violations.append({
                "kind": "manifest_identity_mismatch",
                "field": field,
                "expected": value,
                "actual": actual,
                "detail": f"manifest {field} does not match declared cell",
            })
    return violations


def verify_capture_integrity(tech: Technique, pipe: str,
                             rec: dict | None = None,
                             campaign_dir: Path | None = None) -> dict:
    """Verify one declared campaign cell against its physical capture.

    Manifest status is necessary but not sufficient.  The expected root must
    exist independently, contain the files written by every capture lane, and
    contain valid JSON in ``cost.json``.  For a duplicate public id, the bare
    id directory is deliberately reported as invalid evidence rather than
    accepted as a fallback.
    """
    root = capture_output_dir(tech, pipe, campaign_dir)
    legacy = _legacy_capture_dir(tech, pipe, campaign_dir)
    duplicate_id = bool(tech.capture_slug and tech.capture_slug != tech.id)
    violations: list[dict] = []

    if not rec:
        violations.append({
            "kind": "manifest_missing",
            "detail": "no manifest record for declared cell",
        })
    elif rec.get("status") != "ok":
        violations.append({
            "kind": "manifest_not_ok",
            "status": rec.get("status"),
            "detail": "manifest status is not an accepted capture",
        })
    else:
        violations.extend(_manifest_identity_violations(tech, pipe, rec))

    if root.is_symlink():
        violations.append({
            "kind": "capture_root_symlink",
            "root": str(root),
            "detail": "capture roots must be independent directories",
        })
    elif not root.exists():
        if duplicate_id and legacy.exists():
            violations.append({
                "kind": "legacy_bare_id_root",
                "root": str(legacy),
                "detail": (
                    "duplicate public ids cannot use a shared bare-id "
                    "capture root"),
            })
        violations.append({
            "kind": "capture_root_missing",
            "root": str(root),
            "detail": "expected kind-qualified capture root is absent",
        })
    elif not root.is_dir():
        violations.append({
            "kind": "capture_root_not_directory",
            "root": str(root),
            "detail": "expected capture root is not a directory",
        })
    else:
        for filename in _CAPTURE_REQUIRED_FILES:
            path = root / filename
            if path.is_symlink() or not path.is_file():
                violations.append({
                    "kind": "capture_file_missing",
                    "file": str(path),
                    "detail": f"required capture file is absent: {filename}",
                })
        cost_path = root / "cost.json"
        if cost_path.is_file() and not cost_path.is_symlink():
            try:
                cost = json.loads(cost_path.read_text(encoding="utf-8"))
                if not isinstance(cost, dict):
                    raise ValueError("cost record is not an object")
            except (OSError, UnicodeDecodeError, json.JSONDecodeError,
                    ValueError) as exc:
                violations.append({
                    "kind": "capture_file_invalid",
                    "file": str(cost_path),
                    "detail": f"invalid cost.json: {exc}",
                })

    # What the surviving bytes can actually prove about this cell.
    #
    #   verified          — a sidecar written by the runner from a live call,
    #                       naming this cell and hashing to this prompt.
    #   attested          — a sidecar for a capture recovered from a preserved
    #                       transcript. Right cell, right prompt, but no trace
    #                       survives to hash the request against.
    #   unverified_legacy — the capture predates the sidecar. It exists and the
    #                       manifest accepts it, but nothing ties these bytes to
    #                       this cell. Honest, and not a new defect.
    #   missing           — nothing to certify.
    #
    # A legacy capture stays ``ok``. Every capture written before the sidecar
    # landed is legacy, so failing them would mark the whole campaign for
    # rerun over a bookkeeping change rather than an evidence problem.
    sidecar = read_capture_sidecar(root) if root.is_dir() else None
    if sidecar:
        sidecar_problems = _sidecar_violations(tech, pipe, sidecar)
        violations.extend(sidecar_problems)
        if sidecar_problems:
            evidence = "sidecar_mismatch"
        elif sidecar.get("evidence") == EVIDENCE_RECOVERED:
            evidence = "attested"
        else:
            evidence = "verified"
    elif any(v["kind"] in {"capture_root_missing", "capture_file_missing",
                           "capture_root_not_directory",
                           "capture_root_symlink"} for v in violations):
        evidence = "missing"
    else:
        evidence = "unverified_legacy"

    return {
        "technique_key": tech.key or f"{tech.kind}:{tech.id}",
        "technique": tech.id,
        "kind": tech.kind,
        "pipeline": pipe,
        "root": str(root),
        "legacy_root": str(legacy),
        "evidence": evidence,
        "ok": not violations,
        "violations": violations,
    }


def verify_campaign_captures(techniques: list[Technique],
                             pipelines: list[str], done: dict,
                             campaign_dir: Path | None = None) -> dict:
    """Verify every declared cell and return the exact affected set."""
    cells: dict[tuple[str, str], dict] = {}
    affected: list[dict] = []
    affected_by_pipeline: dict[str, list[str]] = {p: [] for p in pipelines}
    for tech in techniques:
        for pipe in pipelines:
            result = verify_capture_integrity(
                tech, pipe, done.get((tech.key, pipe)), campaign_dir)
            cells[(tech.key, pipe)] = result
            if not result["ok"]:
                affected.append(result)
                affected_by_pipeline.setdefault(pipe, []).append(tech.key)
    evidence_counts: dict[str, int] = {}
    for result in cells.values():
        state = result.get("evidence", "unknown")
        evidence_counts[state] = evidence_counts.get(state, 0) + 1
    return {
        "cells": cells,
        "affected_cells": affected,
        "affected_by_pipeline": affected_by_pipeline,
        "checked_cells": len(cells),
        "valid_cells": len(cells) - len(affected),
        "evidence_counts": evidence_counts,
    }


def select_resume_cells(techniques: list[Technique], pipelines: list[str],
                        done: dict, force: bool = False) -> list[tuple[Technique, str]]:
    """Return only cells not accepted by both manifest and physical verifier."""
    verification = verify_campaign_captures(techniques, pipelines, done)
    return [
        (tech, pipe)
        for tech in techniques
        for pipe in pipelines
        if force or not verification["cells"][(tech.key, pipe)]["ok"]
    ]


_SEVERITY_RANK = {
    "clean": 0,
    "info": 1,
    "review": 2,
    "verification_gap": 3,
    "critical": 4,
}


def classify_contingency(name: str) -> dict:
    """Classify a step-health contingency for campaign audit triage."""
    if "both-analysts-degraded" in name or "cross-eval-on-error-string" in name:
        return {
            "severity": "critical",
            "category": "analysis_degraded",
            "meaning": "A primary analysis stream degraded; inspect before publishing.",
        }
    if "scrub-fellback-to-consolidated-corpus" in name:
        return {
            "severity": "critical",
            "category": "deliverable_fallback",
            "meaning": "The formatted deliverable was unusable and fell back.",
        }
    if "consolidator-degraded" in name or "formatter-degraded" in name:
        return {
            "severity": "critical",
            "category": "post_analysis_degraded",
            "meaning": "A load-bearing post-analysis step degraded.",
        }
    if "verifier-BROKEN" in name:
        return {
            "severity": "verification_gap",
            "category": "verification_gap",
            "meaning": "The verifier broke; structural checks may have unblocked the cycle, but real verification did not happen.",
        }
    if "rejected-revised-again" in name:
        return {
            "severity": "info",
            "category": "normal_correction_cycle",
            "meaning": "The verifier rejected a draft and the pipeline revised again.",
        }
    if "reviser-degraded" in name or "evaluator-degraded" in name:
        return {
            "severity": "review",
            "category": "recoverable_step_degradation",
            "meaning": "A step degraded and the reliability layer substituted a recoverable fallback.",
        }
    if "deliverable-scrub-stripped-leak" in name or "formatter-leak-relabelled" in name:
        return {
            "severity": "review",
            "category": "surface_scrub",
            "meaning": "The final surface was cleaned by the scrubber; inspect for formatter prompt drift.",
        }
    return {
        "severity": "review",
        "category": "unclassified",
        "meaning": "Unrecognized contingency; inspect and classify.",
    }


def _max_severity(labels: list[str]) -> str:
    severity = "clean"
    for label in labels:
        classified = classify_contingency(label)["severity"]
        if _SEVERITY_RANK[classified] > _SEVERITY_RANK[severity]:
            severity = classified
    return severity


# ─── Configuration baking ────────────────────────────────────────────────


def _load_registry_pricing() -> dict:
    """id → {input_per_million_usd, output_per_million_usd} from the live
    registry. Missing pricing → nulls (cost rows show 'unpriced')."""
    reg_path = CONFIG_DIR / "model-registry.json"
    out: dict = {}
    try:
        models = json.loads(reg_path.read_text()).get("models") or {}
    except Exception:
        return out
    for mid, m in models.items():
        p = m.get("pricing") or {}
        ipt, opt = p.get("input_per_token"), p.get("output_per_token")
        out[mid] = {
            "input_per_million_usd": round(ipt * 1e6, 4) if ipt is not None else None,
            "output_per_million_usd": round(opt * 1e6, 4) if opt is not None else None,
        }
    return out


def _stamp_campaign_fields(config: dict, name: str, source: str) -> dict:
    config["name"] = name
    config["preset_lineage"] = "campaign"
    config["rag_isolation"] = "web_only"
    config["_rag_isolation_note"] = RAG_NOTE
    config["_campaign_source"] = source
    config["_campaign_baked_at"] = _now_iso()
    return config


def _config_models(config: dict) -> dict:
    """The five card-visible model picks (2 big, 2 fast, 1 small)."""
    cells = config.get("cells") or {}
    def cell(*path):
        node = cells
        for k in path:
            node = (node or {}).get(k) or {}
        return node.get("primary") if isinstance(node, dict) else None
    return {
        "big1": cell("analysis", "gear4", "depth"),
        "big2": cell("analysis", "gear4", "breadth"),
        "fast1": cell("analysis", "gear3", "depth"),
        "fast2": cell("analysis", "gear3", "breadth"),
        "small": cell("utility", "step1_cleanup"),
    }


def _poke_router_reload(server: str = DEFAULT_SERVER) -> bool:
    """Ask the running server to reload its singleton Router after this
    process edited routing-config.json on disk. An EMPTY per-slot merge
    (``POST /config/routing/slots`` with ``{"slots": {}}``) changes
    nothing but runs the route's save + router-reload hook — the same
    hook the Settings panel autosave uses. Best-effort: when the server
    is down (bake before start), startup loads fresh anyway."""
    try:
        req = urllib.request.Request(
            f"{server}/config/routing/slots",
            data=json.dumps({"slots": {}}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            out = json.loads(r.read())
        reloaded = bool(out.get("router_reloaded"))
        if not reloaded:
            print("[bake] server saved config but router reload reported "
                  "False — restart the server before a subscription run")
        return reloaded
    except Exception as exc:
        print(f"[bake] router reload poke skipped ({str(exc)[:120]}) — "
              f"if the server was already running, restart it to pick up "
              f"the new endpoints")
        return False


def ensure_claude_code_endpoints() -> None:
    """Register the subscription (Claude Code CLI) endpoints in
    routing-config.json when absent. Their ids live outside the catalog
    namespace, so the automatic endpoint sync preserves them."""
    rc_path = CONFIG_DIR / "routing-config.json"
    rc = json.loads(rc_path.read_text())
    by_id = {(e.get("id") or e.get("name")): e for e in rc.get("endpoints") or []}
    added = 0
    for spec in CLAUDE_CODE_ENDPOINTS:
        if spec["id"] in by_id:
            continue
        rc["endpoints"].append({
            "id": spec["id"],
            "type": "api",
            "status": "active",
            "enabled": True,
            "provider": "anthropic",
            "display_name": spec["display_name"],
            "service": "claude-code",
            "model_id": spec["model_id"],
            "dispatch": "subscription",
            "vision_capable": True,
            "context_window": 200000,
            "capabilities": {"tool_access": False, "file_system_access": False,
                             "web_access": False,
                             "retrieval_approach": "pre-assembled"},
            "_note": ("Subscription execution via the local Claude Code CLI "
                      "(claude -p). Zero marginal API cost; campaign cost "
                      "tables price its tokens at the API-equivalent rate."),
        })
        added += 1
    if added:
        tmp = rc_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rc, indent=2) + "\n")
        os.replace(tmp, rc_path)
        print(f"[bake] registered {added} claude-code subscription endpoint(s)")
        if _poke_router_reload():
            print("[bake] running server reloaded its router")


def build_subscription_premium() -> dict:
    """The user-specified subscription premium: Opus 4.8 in both big
    slots + all post-analysis cells; Haiku 4.5 in the fast pair and the
    utility cells. No fallbacks — a failed call fails loudly (and the
    fidelity gate keeps any drift out of the captures)."""
    def cell(mid):
        return {"primary": mid, "fallback": []}
    cells = {
        "utility": {
            "step1_cleanup": cell(CLAUDE_CODE_HAIKU),
            "classification": cell(CLAUDE_CODE_HAIKU),
            "rag_planner": cell(CLAUDE_CODE_HAIKU),
            "gear2_rag_lookup": cell(CLAUDE_CODE_HAIKU),
        },
        "analysis": {
            "gear4": {"depth": cell(CLAUDE_CODE_OPUS),
                      "breadth": cell(CLAUDE_CODE_OPUS)},
            "gear3": {"depth": cell(CLAUDE_CODE_HAIKU),
                      "breadth": cell(CLAUDE_CODE_HAIKU)},
        },
        "post_analysis": {
            "consolidation": cell(CLAUDE_CODE_OPUS),
            "verification": cell(CLAUDE_CODE_OPUS),
            "formatter": cell(CLAUDE_CODE_OPUS),
        },
    }
    return {
        "name": "campaign-premium",
        "description": (
            "Subscription premium: Claude Opus 4.8 in both big slots and "
            "all post-analysis cells, Claude Haiku 4.5 in fast + utility — "
            "executed through the user's Claude subscription via the local "
            "Claude Code CLI (service=claude-code), not the metered API. "
            "Single-family adversarial pair by deliberate tradeoff. Cost "
            "tables report API-equivalent token pricing."),
        "diversity_override": False,
        "cells": cells,
        "toggles": {"adversarial_diversity": True, "vision_only": False},
    }


def build_optimum_plus(optimum_config: dict, consolidator_id: str) -> dict:
    """Exact duplicate of campaign-optimum with ONE change: the
    consolidation primary (step 7 — the call that reads both adversarial
    streams and writes what the user sees) becomes the flagship. Every
    other field — fallback chains included — stays identical (user spec
    2026-06-12). A throttled flagship falling back to the chain is caught
    by the fidelity gate's required-subscription-models check, not by
    emptying the chain."""
    import copy
    cfg = copy.deepcopy(optimum_config)
    cfg["cells"]["post_analysis"]["consolidation"]["primary"] = consolidator_id
    cfg["description"] = (
        "Optimum+ — exact duplicate of campaign-optimum with one change: "
        f"the consolidation primary is {consolidator_id}. Captures whether "
        "a premium consolidator alone lifts the cheap pipeline's "
        "deliverable (experiment 2026-06-12: 11-0-1 for the variant).")
    return cfg


def bake_configs(rebake_presets: bool = True, premium_mode: str = "api") -> dict:
    """Build the three campaign configurations + the pricing snapshot.

    premium/optimum come from a FRESH preset bake (the picker algorithm
    against the live catalog + probe-verified registry), then copied to
    campaign-* names so later pane edits / re-bakes can't drift the
    campaign mid-run. qwen9b is generated (single model in every cell).

    ``premium_mode``: "api" (picker-baked, metered) or "subscription"
    (Opus/Haiku through the user's Claude subscription via Claude Code;
    cost tables then carry API-equivalent pricing for that lane).
    """
    sys.path.insert(0, str(ORA_HOME))
    from orchestrator import active_configuration as ac

    if rebake_presets:
        baked = ac.bake_missing_presets(force=True)
        print(f"[bake] presets re-baked from live catalog: {baked}")

    snapshot: dict = {"baked_at": _now_iso(), "configs": {},
                      "premium_mode": premium_mode}
    pricing = _load_registry_pricing()
    # claude-code ids price at their API twin's rate (API-equivalent).
    for spec in CLAUDE_CODE_ENDPOINTS:
        eq = pricing.get(spec["api_equivalent"])
        if eq:
            pricing[spec["id"]] = dict(eq, cost_basis="api_equivalent")
            pricing[spec["model_id"]] = pricing[spec["id"]]

    # campaign-optimum now derives from the renamed "budget" preset (the
    # old "optimum"). The campaign pipeline + config keep the "optimum"
    # name for continuity (campaign-optimum is the live active config);
    # only the SOURCE preset changed. A fuller campaign-harness rename is
    # a separate decision.
    pairs = [("budget", "campaign-optimum")]
    if premium_mode == "api":
        pairs.insert(0, ("premium", "campaign-premium"))
    else:
        ensure_claude_code_endpoints()
        config = build_subscription_premium()
        _stamp_campaign_fields(config, "campaign-premium",
                               source="subscription:opus-4.8+haiku-4.5")
        (CONFIGURATIONS_DIR / "campaign-premium.json").write_text(
            json.dumps(config, indent=2) + "\n")
        models = _config_models(config)
        snapshot["configs"]["campaign-premium"] = {
            "models": models,
            "pricing": {m: pricing.get(m) for m in set(filter(None, models.values()))},
            "cost_basis": "api_equivalent",
        }
        print(f"[bake] campaign-premium (subscription): {models}")

    for preset, campaign_name in pairs:
        src = CONFIGURATIONS_DIR / f"{preset}.json"
        config = json.loads(src.read_text())
        config["description"] = (
            f"Campaign copy of the auto-baked '{preset}' preset "
            f"(picker algorithm, {config.get('_auto_populate_metadata', {}).get('preset', preset)}). "
            f"Frozen for the Comparative Evaluation Campaign; not re-baked by the pane.")
        _stamp_campaign_fields(config, campaign_name, source=f"preset:{preset}")
        (CONFIGURATIONS_DIR / f"{campaign_name}.json").write_text(
            json.dumps(config, indent=2) + "\n")
        models = _config_models(config)
        snapshot["configs"][campaign_name] = {
            "models": models,
            "pricing": {m: pricing.get(m) for m in set(filter(None, models.values()))},
        }
        print(f"[bake] {campaign_name}: {models}")

    # campaign-optimum-plus — optimum with the flagship in the ONE cell the
    # 2026-06-12 experiment showed concentrates intelligence-per-dollar:
    # consolidation (step 7). Captured as its own lane so the full-sweep
    # data exists BEFORE deciding whether the optimum preset default
    # changes (n=12 verdict: 11-0-1 for the variant, ~+$0.25/run).
    # The consolidator is premium's big-1 AS PICKED — in subscription mode
    # that is the claude-code endpoint (user spec 2026-06-12: "the Opus 4.8
    # from my subscription account"), so the 198 consolidation calls cost
    # zero marginal dollars and the tables price them API-equivalent (†).
    # Third parties baking with --premium api get the metered flagship.
    consolidator_id = snapshot["configs"]["campaign-premium"]["models"]["big1"]
    opt_plus = build_optimum_plus(
        json.loads((CONFIGURATIONS_DIR / "campaign-optimum.json").read_text()),
        consolidator_id)
    _stamp_campaign_fields(opt_plus, "campaign-optimum-plus",
                           source=f"optimum+consolidator:{consolidator_id}")
    (CONFIGURATIONS_DIR / "campaign-optimum-plus.json").write_text(
        json.dumps(opt_plus, indent=2) + "\n")
    models_plus = _config_models(opt_plus)
    plus_ids = set(filter(None, models_plus.values())) | {consolidator_id}
    snapshot["configs"]["campaign-optimum-plus"] = {
        "models": dict(models_plus, consolidator=consolidator_id),
        "pricing": {m: pricing.get(m) for m in plus_ids},
    }
    print(f"[bake] campaign-optimum-plus: optimum + consolidation→{consolidator_id}")

    # campaign-qwen9b — one model, every cell, no fallbacks.
    cells: dict = {}
    for path in QWEN9B_CELL_PATHS:
        node = cells
        for k in path[:-1]:
            node = node.setdefault(k, {})
        node[path[-1]] = {"primary": QWEN9B_MODEL, "fallback": []}
    qwen = {
        "name": "campaign-qwen9b",
        "description": (
            "Single-model campaign configuration: qwen/qwen3.5-9b in every "
            "slot via OpenRouter — the full-precision twin of the local "
            "OptiQ 4-bit MLX bundle anyone can download from Hugging Face. "
            "Demonstrates what Ora's architecture lifts a 9B model to. "
            "No fallbacks: if the model fails, the step genuinely degrades."),
        "diversity_override": False,
        "cells": cells,
        "toggles": {"adversarial_diversity": True, "vision_only": False},
    }
    _stamp_campaign_fields(qwen, "campaign-qwen9b", source="generated:qwen3.5-9b")
    (CONFIGURATIONS_DIR / "campaign-qwen9b.json").write_text(
        json.dumps(qwen, indent=2) + "\n")
    snapshot["configs"]["campaign-qwen9b"] = {
        "models": _config_models(qwen),
        "pricing": {QWEN9B_MODEL: pricing.get(QWEN9B_MODEL)},
    }
    print(f"[bake] campaign-qwen9b: {QWEN9B_MODEL} in all {len(QWEN9B_CELL_PATHS)} cells")

    # The single-pass flagship = premium's big-1 pick, and it FOLLOWS the
    # premium execution mode: subscription bake → the bare control call
    # also rides the subscription (same model, same serving stack; cost
    # tables price it API-equivalent). Third parties running the
    # downloadable framework bake with --premium api and get the metered
    # call instead.
    flagship = snapshot["configs"]["campaign-premium"]["models"]["big1"]
    snapshot["single_pass_flagship"] = {
        "model_id": flagship,
        "pricing": pricing.get(flagship),
    }
    print(f"[bake] single-pass flagship (premium big-1): {flagship}")

    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2) + "\n")
    print(f"[bake] snapshot → {SNAPSHOT_PATH}")
    return snapshot


# ─── Manifest (resume + retry bookkeeping) ───────────────────────────────


def load_manifest(manifest_path: Path | None = None) -> dict:
    """(technique_key, pipeline) → latest record."""
    done: dict = {}
    source = Path(manifest_path or MANIFEST_PATH)
    if source.exists():
        for line in source.read_text().splitlines():
            try:
                rec = json.loads(line)
                done[(manifest_key_for_record(rec), rec["pipeline"])] = rec
            except (json.JSONDecodeError, KeyError):
                continue
    return done


_MANIFEST_LOCK = __import__("threading").Lock()


def append_manifest(rec: dict) -> None:
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    with _MANIFEST_LOCK:
        with open(MANIFEST_PATH, "a") as f:
            f.write(json.dumps(rec) + "\n")


# ─── Ora-pipeline capture (POST /chat — synchronous, file-as-truth) ──────

# Oversight-health banners the server prepends to assistant replies when
# its meta-layer daemon looks stale. Operational noise, not part of the
# answer — strip from captures. (Pipeline degradation signals are NOT
# stripped: those describe the run itself and belong in the record.)
_OVERSIGHT_BANNER = re.compile(
    r"^> [^\n]*\*\*Meta-layer oversight[^\n]*\n(?:>[^\n]*\n)*\s*---\s*\n+",
)


def strip_system_banners(text: str) -> str:
    out = text.lstrip("\n")
    while True:
        m = _OVERSIGHT_BANNER.match(out)
        if not m:
            return out
        out = out[m.end():].lstrip("\n")


def run_ora_pipeline(server: str, config_name: str, technique: Technique,
                     conv_id: str, timeout: int = 2400) -> dict:
    """One pipeline run. Returns {text, trace_dir} or raises RuntimeError.

    V3 protocol (file-as-source-of-truth, 2026-04-30): ``POST /chat``
    runs the pipeline SYNCHRONOUSLY and replies once with
    ``{"status": "ok"|"errored", "conversation_id", "chunk_id", ...}`` —
    no SSE, no streaming. The final user-facing text (post-visual-hook,
    so suppressed envelopes are gone and synthesized repairs spliced in)
    is then read from the conversation API.
    """
    payload = {
        "message": technique.prompt,
        "panel_id": conv_id,
        "history": [],
        "config_name": config_name,
        "manual_mode_selection": technique.intended_mode,
        # Thread the technique's target visual kind so the server's visual hook
        # emits THAT diagram (multi-kind modes otherwise default to their first
        # listed type). Empty for non-visual techniques → no override.
        "manual_visual_type": technique.target_visual or "",
    }
    assistant_count_before = 0
    try:
        with urllib.request.urlopen(
                f"{server}/api/conversation/{conv_id}", timeout=30) as prior_resp:
            prior = json.loads(prior_resp.read())
        assistant_count_before = sum(
            1 for m in (prior.get("messages") or [])
            if m.get("role") == "assistant")
    except Exception:
        pass

    req = urllib.request.Request(
        f"{server}/chat", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        d = json.loads(resp.read())
    if d.get("status") != "ok":
        raise RuntimeError(
            f"pipeline {d.get('status') or 'failed'}: "
            f"{str(d.get('failure_summary') or d)[:300]}")
    # The /chat write and the conversation read model are intentionally
    # file-backed. On a busy run, the synchronous response can arrive a few
    # milliseconds before the new assistant turn is visible through the read
    # endpoint. Poll for an assistant count increase so a retry cannot consume
    # an older result or declare a successfully persisted turn missing.
    assistant = []
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                    f"{server}/api/conversation/{conv_id}", timeout=30) as r:
                conv = json.loads(r.read())
            assistant = [m for m in (conv.get("messages") or [])
                         if m.get("role") == "assistant"]
            if len(assistant) > assistant_count_before:
                break
        except Exception:
            pass
        time.sleep(0.25)
    if len(assistant) <= assistant_count_before:
        raise RuntimeError(
            "new assistant message not visible in conversation after run")
    result_message = assistant[-1]
    text = strip_system_banners(result_message.get("content") or "")
    if not text.strip():
        raise RuntimeError("empty assistant response")
    trace_ref = str(result_message.get("trace_ref") or "").strip()
    trace_dir = str(TRACES_DIR / trace_ref) if trace_ref else _latest_trace_dir(conv_id)
    return {"text": text, "trace_dir": trace_dir}


def _latest_trace_dir(conv_id: str) -> str | None:
    base = TRACES_DIR / conv_id
    if not base.is_dir():
        return None
    turns = sorted(p.name for p in base.iterdir() if p.is_dir())
    return str(base / turns[-1]) if turns else None


def price_usage_records(trace_dir: str | None, rate_map: dict,
                        subscription_only: bool = False) -> float | None:
    """Price a trace's usage.jsonl against a rate map (endpoint_id /
    model_id → {input_per_million_usd, output_per_million_usd}).

    Fallback for lanes whose endpoint ids aren't in the model registry —
    the subscription endpoints (claude-code:*) cost $0 marginal, so the
    campaign prices their tokens at the API-equivalent rate to keep the
    published comparison honest.

    Counts every input token once at the standard input rate — uncached
    prompt PLUS cache_creation PLUS cache_read. Pricing only the uncached
    prompt understated the subscription lanes massively (a premium run's input
    is ~99.7% cache-creation tokens). The 1× (uncached) basis is used rather
    than the 1.25×-write/0.1×-read cache schedule because the pipelines write
    caches they never reread (cache_read ≈ 0), so a non-subscriber would send
    the context uncached. When ``subscription_only`` is set, only claude-code:*
    calls are priced — used to add the API-equivalent of subscription work to a
    metered lane's real cost (e.g. optimum-plus's Opus consolidator)."""
    if not trace_dir or not rate_map:
        return None
    path = Path(trace_dir) / "usage.jsonl"
    if not path.exists():
        return None
    total, any_priced = 0.0, False
    for line in path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        eid = rec.get("endpoint_id") or ""
        if subscription_only and not eid.startswith("claude-code:"):
            continue
        rate = rate_map.get(eid) or rate_map.get(rec.get("model_id"))
        if not rate or rate.get("input_per_million_usd") is None:
            continue
        ipm = rate["input_per_million_usd"]
        # Price ALL input (uncached prompt + cache writes + cache reads) at the
        # standard input rate. The campaign pipelines write caches they never
        # reread (cache_read ≈ 0), so prompt caching only ADDS the 1.25× write
        # premium for no benefit — a non-subscriber would rationally send the
        # context uncached at 1×. Counting every input token once at 1× is the
        # honest "what they'd actually pay" basis (verified 2026-06-13: premium
        # cache_read ≈ 0 against ~620K cache_create/run).
        input_toks = ((rec.get("prompt_tokens") or 0)
                      + (rec.get("cache_creation_tokens") or 0)
                      + (rec.get("cache_read_tokens") or 0))
        total += (input_toks / 1e6 * ipm
                  + (rec.get("completion_tokens") or 0) / 1e6
                  * rate["output_per_million_usd"])
        any_priced = True
    return round(total, 6) if any_priced else None


def _sum_usage_tokens(trace_dir: str | None) -> dict:
    """Sum a trace's usage.jsonl token counts, including cache tokens, so the
    aggregate's token columns reflect true input (not just the uncached
    sliver the manifest records)."""
    out = {"prompt": 0, "completion": 0, "cache_read": 0, "cache_create": 0}
    if not trace_dir:
        return out
    path = Path(trace_dir) / "usage.jsonl"
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        out["prompt"] += rec.get("prompt_tokens") or 0
        out["completion"] += rec.get("completion_tokens") or 0
        out["cache_read"] += rec.get("cache_read_tokens") or 0
        out["cache_create"] += rec.get("cache_creation_tokens") or 0
    return out


def read_trace_cost(trace_dir: str | None) -> dict:
    """Totals from the trace's cost-summary.json (rates embedded at run
    time — the de-facto price snapshot per run)."""
    empty = {"prompt_tokens": 0, "completion_tokens": 0, "total_cost_usd": None,
             "models": []}
    if not trace_dir:
        return empty
    path = Path(trace_dir) / "cost-summary.json"
    if not path.exists():
        return empty
    try:
        cs = json.loads(path.read_text())
    except json.JSONDecodeError:
        return empty
    totals = cs.get("totals") or {}
    return {
        "prompt_tokens": totals.get("prompt_tokens", 0),
        "completion_tokens": totals.get("completion_tokens", 0),
        "total_cost_usd": totals.get("total_cost_usd"),
        "models": [r.get("model_id") for r in (cs.get("models") or [])],
    }


# ─── Fidelity gate: only the specified models may serve ─────────────────


def load_expected_primaries(config_name: str) -> set:
    """Every cell primary in the campaign configuration — the ONLY models
    allowed to record usage during a run. Fallback-chain entries are
    deliberately excluded: a 429/throttle that cascades to a fallback
    model invalidates the capture (the comparison is between SPECIFIED
    model sets, not whatever happened to answer)."""
    config = json.loads((CONFIGURATIONS_DIR / f"{config_name}.json").read_text())
    expected: set = set()

    def walk(node):
        if isinstance(node, dict):
            if "primary" in node:
                if node.get("primary"):
                    expected.add(node["primary"])
            else:
                for v in node.values():
                    walk(v)
    walk(config.get("cells") or {})
    return expected


def load_fidelity_contract(config_name: str) -> dict:
    """Load the exact cell-primary contract for one frozen campaign lane."""
    config = json.loads((CONFIGURATIONS_DIR / f"{config_name}.json").read_text())
    return {
        "config_name": config_name,
        "cells": config.get("cells") or {},
    }


def _call_contract_primary(contract: dict, call: dict) -> str | None:
    """Resolve the primary that an authenticated physical call should use."""
    slot = str(call.get("slot") or "")
    gear = call.get("gear")
    cells = contract.get("cells") or {}
    path = None
    if slot in {"sidebar", "step1_cleanup"}:
        path = ("utility", "step1_cleanup")
    elif slot in {"fast", "gear2_rag_lookup"}:
        path = ("utility", "gear2_rag_lookup")
    elif slot in {"rag_planner", "classification"}:
        path = ("utility", slot)
    elif slot in {"depth", "breadth"} and gear in {3, 4}:
        path = ("analysis", f"gear{gear}", slot)
    elif slot in {"consolidator", "consolidation"}:
        path = ("post_analysis", "consolidation")
    elif slot in {"evaluator", "verification"}:
        path = ("post_analysis", "verification")
    elif slot in {"formatter", "formatting"}:
        path = ("post_analysis", "formatter")
    if path is None:
        return None
    node = cells
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node.get("primary") if isinstance(node, dict) else None


_OK_FINISH = {"", "stop", "end_turn", "stop_sequence", "eos", "none"}


def _finish_ok(finish_reason) -> bool:
    """Normalize the per-wrapper finish_reason shapes (OpenAI 'stop',
    Anthropic 'end_turn', Gemini's enum repr 'FinishReason.STOP') and
    answer whether the call terminated normally."""
    if finish_reason is None:
        return True
    s = str(finish_reason).split(".")[-1].strip().lower()
    return s in _OK_FINISH


def verify_trace_fidelity(trace_dir: str | None, expected: set,
                          contract: dict | None = None) -> dict:
    """Audit a completed run's trace against the configured primaries.

    Checks:
      1. Every usage.jsonl record's endpoint_id is one of the expected
         primaries (a fallback model serving = violation). Direct-vendor
         and OpenRouter transports record the same endpoint_id, so a
         same-model transport fallback passes — only a MODEL substitution
         fails.
      2. When a cell contract is supplied, each physical call must name that
         configuration and execute the primary for its exact slot and gear.
         Unused cells are not required: path-legal Gear-1/2/3 runs must not be
         rejected because a Gear-4 consolidator correctly did not execute.
      3. No step file recorded ok=false (silent step degradation).
      4. finish_reason anomalies (length/content_filter/429 markers) are
         surfaced as warnings — the step may have self-healed, but the
         reviewer should know.

    Returns {ok, violations, warnings, executed} — executed is
    endpoint_id → call count for the manifest record.
    """
    result = {"ok": False, "violations": [], "warnings": [], "executed": {}}
    if not trace_dir:
        result["violations"].append({"kind": "no_trace",
                                     "detail": "no trace directory found"})
        return result
    tdir = Path(trace_dir)
    usage_path = tdir / "usage.jsonl"
    if not usage_path.exists():
        result["violations"].append({"kind": "no_usage",
                                     "detail": "trace has no usage.jsonl"})
        return result
    for line in usage_path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        eid = rec.get("endpoint_id") or rec.get("model_id") or "?"
        result["executed"][eid] = result["executed"].get(eid, 0) + 1
        if eid not in expected:
            result["violations"].append({
                "kind": "unexpected_model", "model": eid,
                "step_hint": rec.get("step_hint"),
                "service": rec.get("service")})
        fr = rec.get("finish_reason")
        if not _finish_ok(fr):
            result["warnings"].append({
                "kind": "finish_reason", "model": eid,
                "finish_reason": str(fr), "step_hint": rec.get("step_hint")})
    if contract is not None:
        call_path = tdir / "model-call-config.jsonl"
        if not call_path.exists():
            result["violations"].append({
                "kind": "no_call_contract",
                "detail": "trace has no authenticated physical-call records",
            })
        else:
            calls = []
            for line in call_path.read_text().splitlines():
                try:
                    call = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if call.get("physical_attempt"):
                    calls.append(call)
            if not calls:
                result["violations"].append({
                    "kind": "no_call_contract",
                    "detail": "trace has no physical model-call records",
                })
            for call in calls:
                eid = call.get("endpoint_id") or call.get("model_id") or "?"
                declared_config = call.get("config_name")
                if declared_config != contract.get("config_name"):
                    result["violations"].append({
                        "kind": "configuration_identity_mismatch",
                        "model": eid,
                        "declared_config": declared_config,
                        "expected_config": contract.get("config_name"),
                        "step": call.get("step"),
                    })
                    continue
                primary = _call_contract_primary(contract, call)
                if primary is None:
                    result["violations"].append({
                        "kind": "unbound_model_call",
                        "model": eid,
                        "step": call.get("step"),
                        "slot": call.get("slot"),
                        "gear": call.get("gear"),
                    })
                elif eid != primary:
                    result["violations"].append({
                        "kind": "cell_primary_mismatch",
                        "model": eid,
                        "expected_model": primary,
                        "step": call.get("step"),
                        "slot": call.get("slot"),
                        "gear": call.get("gear"),
                    })
    step_files = sorted(tdir.glob("step*.json"))

    # A bounded quality-gate correction deliberately leaves the failed first
    # inspection in the trace.  That record is evidence for why correction
    # fired, not the terminal release decision.  Gear 3 writes an explicit
    # summary after all inspections; Gear 4 writes numbered pass records, so
    # its highest pass number is authoritative.  Auditing every file as if it
    # were terminal made a successful FAIL -> correction -> PASS sequence
    # impossible to accept and needlessly re-executed paid campaign lanes.
    quality_summaries = {
        path for path in step_files
        if re.fullmatch(r"step\d+(?:_\d+)?-quality-gate", path.stem)
    }
    numbered_quality_passes: list[tuple[int, Path]] = []
    for path in step_files:
        match = re.fullmatch(
            r"step\d+(?:_\d+)?-quality-gate-pass-?(\d+)", path.stem)
        if match:
            numbered_quality_passes.append((int(match.group(1)), path))
    terminal_quality_files = set(quality_summaries)
    if not quality_summaries and numbered_quality_passes:
        terminal_quality_files.add(max(numbered_quality_passes)[1])

    for step_file in step_files:
        try:
            d = json.loads(step_file.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(d, dict) and "ok" in d and d.get("ok") is False:
            result["violations"].append({
                "kind": "step_failed", "step": step_file.stem,
                "detail": str(d.get("reason"))[:200]})
        if (
            isinstance(d, dict)
            and step_file in terminal_quality_files
            and (d.get("released") is False
                 or str(d.get("verdict_resolved") or "").upper()
                 in {"FAIL", "BROKEN"})
        ):
            result["violations"].append({
                "kind": "quality_gate_not_passed",
                "step": step_file.stem,
                "verdict": d.get("verdict_resolved"),
                "released": d.get("released"),
            })
    # Legacy traces do not have cell-bound physical-call records. Preserve the
    # old subscription-presence safeguard only for that compatibility path.
    # Current captures use the stronger slot-level check above, which detects
    # same-config fallback without treating path-legal non-use as failure.
    if contract is None:
        for mid in expected:
            if mid.startswith("claude-code:") and mid not in result["executed"]:
                result["violations"].append({
                    "kind": "required_model_missing", "model": mid,
                    "detail": "subscription primary never executed — its step "
                              "was served by a fallback or skipped"})
    result["ok"] = not result["violations"]
    return result


# ─── Single-pass flagship (bare API call, usage captured) ────────────────


def _keyring_get(name: str) -> str | None:
    try:
        import keyring
        return keyring.get_password("ora", name)
    except Exception:
        return None


def _claude_code_env() -> dict:
    """Environment for standalone Claude Code subscription calls.

    The campaign runner may be launched from a long-lived Claude Code session.
    Do not inherit that session's refresh context into child ``claude -p``
    processes; force the CLI to use its own local auth refresh. Also drop
    ANTHROPIC_API_KEY so a subscription lane can never silently bill the
    metered API.
    """
    scrub = {
        "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_SESSION_ID",
        "CLAUDE_CODE_SDK_HAS_OAUTH_REFRESH",
        "CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH",
        "CLAUDE_CODE_ENTRYPOINT",
    }
    return {k: v for k, v in os.environ.items() if k not in scrub}


def resolve_flagship_endpoint(flagship_id: str) -> dict:
    """Find the routing-config endpoint for the flagship id (registered by
    the endpoint sync; dispatch=direct when the vendor key exists)."""
    rc = json.loads((CONFIG_DIR / "routing-config.json").read_text())
    for ep in rc.get("endpoints") or []:
        if (ep.get("id") or ep.get("name")) == flagship_id:
            return ep
    raise SystemExit(
        f"no endpoint registered for flagship {flagship_id!r} — open the "
        f"Models pane and hit Refresh (runs the endpoint sync), then retry")


def _single_pass_claude_code(endpoint: dict, prompt: str,
                             timeout: int) -> dict:
    """Bare flagship call through the Claude Code CLI (subscription).
    Mirrors boot's claude-code service: no system prompt, no tools,
    usage from the requested model's modelUsage entry, served-model
    verified."""
    import subprocess
    model_id = endpoint.get("model_id") or "claude-opus-4-8"
    env = _claude_code_env()
    cli = os.environ.get("ORA_CLAUDE_CODE_BIN") or "claude"
    r = subprocess.run(
        [cli, "-p", "--model", model_id, "--output-format", "json",
         "--tools", ""],
        input=prompt, capture_output=True, text=True, timeout=timeout,
        env=env)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()[:300]
        kind = "rate-limited: " if ("limit" in err.lower()
                                    or "rate" in err.lower()) else ""
        raise RuntimeError(f"claude-code {kind}{err}")
    d = json.loads(r.stdout)
    if d.get("is_error"):
        err = str(d.get("result") or "")[:300]
        kind = "rate-limited: " if "limit" in err.lower() else ""
        raise RuntimeError(f"claude-code {kind}{err}")
    mu = d.get("modelUsage") or {}
    main_key = next((k for k in mu if k.startswith(model_id)), None)
    if mu and main_key is None:
        raise RuntimeError(
            f"single-pass fidelity: requested {model_id}, served {sorted(mu)}")
    usage = (mu.get(main_key) or {}) if main_key else {}
    top = d.get("usage") or {}
    return {"text": d.get("result") or "",
            "prompt_tokens": usage.get("inputTokens",
                                       top.get("input_tokens", 0)),
            "completion_tokens": usage.get("outputTokens",
                                           top.get("output_tokens", 0)),
            "model_id": model_id,
            "served_model": main_key or model_id,
            "via": "claude-code-subscription"}


def single_pass_call(endpoint: dict, prompt: str, max_tokens: int = 16000,
                     timeout: int = 600) -> dict:
    """Bare one-model call with usage capture. Returns
    {text, prompt_tokens, completion_tokens, model_id, via}."""
    service = endpoint.get("service")
    model_id = endpoint.get("model_id") or endpoint.get("id")
    if service == "claude-code":
        return _single_pass_claude_code(endpoint, prompt, timeout)
    if service == "claude":
        key = _keyring_get("anthropic-api-key") or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("no Anthropic API key (keyring ora/anthropic-api-key)")
        body = {"model": model_id, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode(),
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            d = json.loads(resp.read())
        text = "".join(b.get("text", "") for b in d.get("content") or []
                       if b.get("type") == "text")
        usage = d.get("usage") or {}
        served = d.get("model") or model_id
        if not served.startswith(model_id):
            # Fidelity: the API must serve the requested model (a dated
            # variant of it is fine: claude-opus-4-8-20260301 etc.).
            raise RuntimeError(f"single-pass fidelity: requested {model_id}, "
                               f"served {served}")
        return {"text": text, "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "model_id": model_id, "served_model": served,
                "via": "anthropic-direct"}
    # Everything else (incl. service openai/gemini without special-casing
    # their bare-completion APIs) goes through OpenRouter under the
    # canonical slug — the third-party-reproducible floor.
    key = _keyring_get("openrouter-api-key") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("no OpenRouter API key (keyring ora/openrouter-api-key)")
    slug = endpoint.get("openrouter_fallback_model_id") or endpoint.get("id")
    body = {"model": slug, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    raw, _destination = network_policy.openrouter_request_bytes(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
        timeout=timeout,
        max_bytes=16 * 1024 * 1024,
    )
    d = json.loads(raw)
    choice = (d.get("choices") or [{}])[0]
    usage = d.get("usage") or {}
    served = d.get("model") or slug
    base = slug.split(":", 1)[0]
    # Fidelity: OpenRouter must serve the requested slug, not a
    # router-substituted sibling. A dated snapshot of the requested model
    # (e.g. qwen/qwen3.5-9b-20260310) IS the requested model — accept it,
    # matching the Anthropic branch's startswith semantics; a genuinely
    # different model still fails.
    if not (served == base or served.startswith(base)):
        raise RuntimeError(f"single-pass fidelity: requested {slug}, "
                           f"served {served}")
    return {"text": (choice.get("message") or {}).get("content") or "",
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "model_id": slug, "served_model": served, "via": "openrouter"}


def price_single_pass(rec: dict, pricing: dict | None) -> float | None:
    if not pricing or pricing.get("input_per_million_usd") is None:
        return None
    return round(
        rec["prompt_tokens"] / 1e6 * pricing["input_per_million_usd"]
        + rec["completion_tokens"] / 1e6 * pricing["output_per_million_usd"], 6)


# ─── Visual capture: extract → SVG → PNG ─────────────────────────────────


def extract_visuals(text: str) -> tuple[str, list[str]]:
    """Split the final response into (prose-with-placeholder, envelope
    JSON strings). The input is the POST-hook text the user saw, so
    suppressed envelopes are already gone and synthesized repairs are
    already spliced in."""
    envelopes = [m.group(1) for m in VISUAL_FENCE.finditer(text)]
    prose = VISUAL_FENCE.sub("*(visual rendered — see artifact)*", text).strip()
    return prose, envelopes


def render_svg(envelope_json: str, out_svg: Path) -> bool:
    """Envelope JSON → SVG via the compiler's node CLI. Fail-soft."""
    if not RENDER_ENVELOPE_JS.exists():
        return False
    try:
        r = subprocess.run(
            ["node", str(RENDER_ENVELOPE_JS)], input=envelope_json,
            capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and r.stdout.strip().startswith("<"):
            out_svg.write_text(r.stdout)
            return True
        print(f"    [visual] render-envelope failed rc={r.returncode}: "
              f"{(r.stderr or '')[:200]}")
    except Exception as exc:
        print(f"    [visual] render-envelope error: {exc}")
    return False


def render_visuals_browser(server: str, envelopes: list[str],
                           out_dir: Path, width: int = 1400) -> tuple[int, int]:
    """Render envelopes with the REAL compiler in real Chromium and
    rasterize each artifact — the exact render Ora's visual pane shows
    (browser layout + the app's theme), unlike the jsdom CLI whose
    missing getBBox degrades geometry. Loads the V3 app once (it boots
    the full compiler incl. schema-validated Ajv), calls
    ``OraVisualCompiler.compileWithNav`` per envelope, injects the SVG
    into a clean host styled by the app's stylesheet, and element-
    screenshots it at 2× scale. Returns (svg_count, png_count).
    Raises ImportError when Playwright is unavailable (caller falls back
    to the jsdom SVG-only path)."""
    from playwright.sync_api import sync_playwright

    theme_css = ""
    theme_path = (ORA_HOME / "server" / "static" / "ora-visual-compiler"
                  / "ora-visual-theme.css")
    if theme_path.exists():
        theme_css = theme_path.read_text()

    svg_n = png_n = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(device_scale_factor=2, color_scheme="light",
                          viewport={"width": width + 120, "height": 1400})
        page.goto(f"{server}/", wait_until="networkidle", timeout=60000)
        page.wait_for_function(
            "window.OraVisualCompiler && window.OraVisualCompiler.compileWithNav",
            timeout=30000)
        # The app page doesn't link the compiler's theme stylesheet (the
        # visual pane styles artifacts through its own layer), so inject
        # it — without it every SVG fill defaults to black. Force light mode
        # here so artifact captures stay readable even when Ora's chrome is
        # running in a dark user theme.
        page.evaluate(
            """(css) => {
                const s = document.createElement('style');
                s.id = 'campaign-visual-theme';
                s.textContent = css;
                document.head.appendChild(s);
            }""", theme_css)
        for vi, env in enumerate(envelopes, start=1):
            (out_dir / f"visual-{vi}.json").write_text(env)
            result = page.evaluate(
                """async (envJson) => {
                    let env;
                    try { env = JSON.parse(envJson); }
                    catch (e) { return {svg: '', errors: ['envelope_parse: ' + e.message]}; }
                    let r;
                    try {
                        r = window.OraVisualCompiler.compileWithNav(env);
                        if (r && typeof r.then === 'function') r = await r;
                    } catch (e) { return {svg: '', errors: ['compile_threw: ' + e.message]}; }
                    return {
                        svg: (r && r.svg) || '',
                        errors: ((r && r.errors) || []).map(
                            e => (e.code || '') + ': ' + String(e.message || '').slice(0, 200)),
                    };
                }""", env)
            if not result.get("svg"):
                print(f"    [visual] compile failed: "
                      f"{'; '.join(result.get('errors') or [])[:300]}")
                continue
            (out_dir / f"visual-{vi}.svg").write_text(result["svg"])
            svg_n += 1
            ok = page.evaluate(
                """([markup, w]) => {
                    let host = document.getElementById('campaign-raster-host');
                    if (!host) {
                        host = document.createElement('div');
                        host.id = 'campaign-raster-host';
                        host.style.cssText =
                            'position:fixed;left:0;top:0;z-index:999999;' +
                            'background:var(--ora-vis-bg, #FCFCFA);' +
                            'padding:24px;width:max-content;';
                        document.body.appendChild(host);
                    }
                    host.innerHTML = markup;
                    const svg = host.querySelector('svg');
                    if (!svg) return false;
                    svg.style.width = w + 'px';
                    svg.style.height = 'auto';
                    svg.style.display = 'block';
                    return true;
                }""", [result["svg"], width])
            if ok:
                page.wait_for_timeout(200)  # font/layout settle
                el = page.query_selector("#campaign-raster-host")
                if el:
                    el.screenshot(path=str(out_dir / f"visual-{vi}.png"))
                    png_n += 1
        b.close()
    return svg_n, png_n


# ─── The sweep ────────────────────────────────────────────────────────────


def run_sweep(args) -> int:
    techniques = select_techniques(parse_corpus(Path(args.corpus)), args.techniques)
    pipelines = [p.strip() for p in args.pipelines.split(",") if p.strip()]
    unknown = [p for p in pipelines if p not in ALL_PIPELINES]
    if unknown:
        raise SystemExit(f"unknown pipeline(s): {unknown}; choose from {ALL_PIPELINES}")

    if not SNAPSHOT_PATH.exists():
        raise SystemExit("run `campaign_run.py bake-configs` first")
    snapshot = json.loads(SNAPSHOT_PATH.read_text())
    flagship = (snapshot.get("single_pass_flagship") or {}).get("model_id")
    flagship_pricing = (snapshot.get("single_pass_flagship") or {}).get("pricing")
    flagship_ep = resolve_flagship_endpoint(flagship) if "single-pass" in pipelines else None

    # single-pass-9b: a constructed endpoint (NOT resolved from routing-config)
    # so the bare control call ALWAYS goes through OpenRouter under the canonical
    # 9B slug — the same transport the qwen9b lane's cells use. Pricing is the
    # snapshot's 9B rate (any config that carries it).
    sp9b_pricing = None
    for _c in (snapshot.get("configs") or {}).values():
        _pr = (_c.get("pricing") or {}).get(SINGLE_PASS_9B_MODEL)
        if _pr:
            sp9b_pricing = _pr
            break
    sp9b_ep = ({"id": SINGLE_PASS_9B_MODEL, "service": "openrouter",
                "openrouter_fallback_model_id": SINGLE_PASS_9B_MODEL}
               if "single-pass-9b" in pipelines else None)

    # Preflight: server reachable + campaign configs present.
    if any(p in ORA_PIPELINES for p in pipelines):
        try:
            urllib.request.urlopen(f"{args.server}/api/model-registry/reach/status",
                                   timeout=10)
        except Exception as exc:
            raise SystemExit(f"Ora server not reachable at {args.server} ({exc}) — ./start.sh first")
        for p in pipelines:
            cfg = ORA_PIPELINES.get(p)
            if cfg and not (CONFIGURATIONS_DIR / f"{cfg}.json").exists():
                raise SystemExit(f"missing {cfg}.json — run bake-configs")
        # The server's Router singleton caches routing-config AND named
        # configurations from process start / first use. Campaign configs
        # baked or edited after that are invisible until a reload — twice
        # observed live: 'claude-code:… not registered' (subscription
        # endpoints), and a whole-lane fidelity wipeout where the server
        # executed a previous bake's optimum models against the current
        # file's expected set. Always poke before any Ora-lane sweep.
        _poke_router_reload(args.server)

    # Fidelity expectations per Ora pipeline: only these models may
    # record usage during a run. Loaded once up front so a config edit
    # mid-sweep can't shift the goalposts between runs.
    expected_primaries = {
        p: load_expected_primaries(cfg) for p, cfg in ORA_PIPELINES.items()
        if p in pipelines
    }
    fidelity_contracts = {
        p: load_fidelity_contract(cfg) for p, cfg in ORA_PIPELINES.items()
        if p in pipelines
    }

    # Rate map for API-equivalent pricing of lanes the registry can't
    # price (subscription endpoints): union of every config's bake-time
    # pricing snapshot + the flagship's.
    rate_map: dict = {}
    for c in (snapshot.get("configs") or {}).values():
        for mid, rate in (c.get("pricing") or {}).items():
            if rate:
                rate_map[mid] = rate
    fp = (snapshot.get("single_pass_flagship") or {})
    if fp.get("pricing"):
        rate_map[fp.get("model_id")] = fp["pricing"]

    subscription_lanes = (
        {p for p in pipelines if p in SUBSCRIPTION_PIPELINES}
        if snapshot.get("premium_mode") == "subscription" else set())
    # Single-pass follows the premium execution mode: a claude-code
    # flagship makes the control lane a subscription lane too (serial +
    # window-paced, API-equivalent pricing).
    if (flagship or "").startswith("claude-code:") and "single-pass" in pipelines:
        subscription_lanes.add("single-pass")

    done = load_manifest()
    force = bool(getattr(args, "force_rerun", False))
    todo = select_resume_cells(techniques, pipelines, done, force=force)
    total = len(techniques) * len(pipelines)
    print(f"[run] {len(techniques)} techniques × {len(pipelines)} pipelines = "
          f"{total} captures ({total - len(todo)} already complete, {len(todo)} to run)")
    if args.limit:
        todo = todo[: args.limit]
        print(f"[run] --limit {args.limit} → running {len(todo)} this invocation")
    if args.dry_run:
        for t, p in todo:
            print(f"  would run: {t.id} × {p}")
        return 0

    ctx = {
        "flagship_ep": flagship_ep,
        "flagship_pricing": flagship_pricing,
        "sp9b_ep": sp9b_ep,
        "sp9b_pricing": sp9b_pricing,
        "expected_primaries": expected_primaries,
        "fidelity_contracts": fidelity_contracts,
        "rate_map": rate_map,
        "subscription_lanes": subscription_lanes,
    }

    # Lane-parallel execution: each pipeline is a lane; lanes always run
    # concurrently (they hit disjoint providers); --concurrency adds
    # workers WITHIN the API lanes. Subscription lanes default to 1 worker —
    # the rolling rate window is the bottleneck, and pacing handles it — but
    # --subscription-concurrency raises that for an attended burst on a
    # high-tier account with window headroom.
    import queue as _queue
    import threading as _threading

    by_pipe: dict[str, list] = {}
    for t, p in todo:
        by_pipe.setdefault(p, []).append(t)
    lanes = {}
    for p, items in by_pipe.items():
        q: _queue.Queue = _queue.Queue()
        for t in items:
            q.put(t)
        workers = (max(1, getattr(args, "subscription_concurrency", 1))
                   if p in subscription_lanes
                   else max(1, args.concurrency))
        lanes[p] = (q, min(workers, len(items)))

    progress = {"done": 0, "failures": 0, "lock": _threading.Lock()}

    def _lane_worker(pipe: str, q: "_queue.Queue") -> None:
        while True:
            try:
                tech = q.get_nowait()
            except _queue.Empty:
                return
            ok = _execute_capture(tech, pipe, args, ctx)
            with progress["lock"]:
                progress["done"] += 1
                if not ok:
                    progress["failures"] += 1
                done_n, fail_n = progress["done"], progress["failures"]
            print(f"[run] progress {done_n}/{len(todo)}"
                  + (f" ({fail_n} failed)" if fail_n else ""), flush=True)

    threads = []
    for pipe, (q, workers) in lanes.items():
        for _ in range(workers):
            th = _threading.Thread(target=_lane_worker, args=(pipe, q),
                                   daemon=True)
            th.start()
            threads.append(th)
    for th in threads:
        th.join()

    failures = progress["failures"]
    print(f"[run] complete — {len(todo) - failures} ok, {failures} failed "
          f"(failed pairs re-run on the next invocation)")
    return 1 if failures else 0


def _default_mode_gear(tech: Technique) -> int | None:
    """Read the pinned mode's declared runtime gear from the frozen source."""
    mode_id = str(tech.intended_mode or "").strip()
    if not mode_id:
        return None
    path = ORA_HOME / "modes" / f"{mode_id}.md"
    try:
        text = path.read_text()
    except OSError:
        return None
    match = re.search(
        r"^## DEFAULT GEAR\s*$[\s\S]{0,120}?^Gear\s+([1-4])\s*$",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    return int(match.group(1)) if match else None


def _subscription_probe_endpoint(tech: Technique, contract: dict) -> str | None:
    """Return the subscription model reachable on the pinned mode's path."""
    gear = _default_mode_gear(tech)
    cells = contract.get("cells") or {}
    if gear == 1:
        paths = [("utility", "classification")]
    elif gear == 2:
        paths = [
            ("utility", "gear2_rag_lookup"),
            ("utility", "step1_cleanup"),
        ]
    elif gear == 3:
        paths = [
            ("analysis", "gear3", "depth"),
            ("analysis", "gear3", "breadth"),
        ]
    elif gear == 4:
        paths = [
            ("analysis", "gear4", "depth"),
            ("analysis", "gear4", "breadth"),
        ]
    else:
        return None
    for path in paths:
        node = cells
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        primary = node.get("primary") if isinstance(node, dict) else None
        if str(primary or "").startswith("claude-code:"):
            return primary
    return None


def _wait_for_subscription_window(endpoint_id: str = CLAUDE_CODE_OPUS,
                                  max_wait_s: int = 86400) -> None:
    """Block until the Claude subscription accepts calls again. Probes
    with a tiny completion from the exact subscription model reachable on
    this capture's declared path; on a rate-limit reply, sleeps 15 min
    and re-probes (the 5-hour rolling windows and weekly caps mean a
    long sweep simply pauses instead of failing or falling back to the
    metered API).

    Gear-4 captures therefore probe Opus, while Gear-1/2/3 captures that can
    legally execute only Haiku do not wait on an unreachable Opus cell."""
    import subprocess
    cli = os.environ.get("ORA_CLAUDE_CODE_BIN") or "claude"
    env = _claude_code_env()
    model_id = next(
        (ep["model_id"] for ep in CLAUDE_CODE_ENDPOINTS
         if ep["id"] == endpoint_id),
        endpoint_id.split(":", 1)[-1],
    )
    waited = 0
    while True:
        try:
            r = subprocess.run(
                [cli, "-p", "--model", model_id,
                 "--output-format", "text", "--tools", ""],
                input="Reply with exactly: OK", capture_output=True,
                text=True, timeout=180, env=env)
            blob = ((r.stdout or "") + (r.stderr or "")).lower()
        except Exception as exc:
            raise RuntimeError(
                f"subscription probe failed before a rate-window verdict: {exc}"
            ) from exc

        rate_markers = ("limit", "rate limit", "usage cap", "capacity")
        auth_markers = (
            "not logged in", "please run /login", "authentication",
            "unauthorized", "oauth", "invalid credentials",
        )
        if r.returncode == 0 and not any(m in blob for m in rate_markers):
            return
        if any(m in blob for m in auth_markers):
            detail = ((r.stderr or r.stdout or "").strip()[:240]
                      or "Claude CLI authentication unavailable")
            raise RuntimeError(
                f"subscription authentication unavailable: {detail}")
        if not any(m in blob for m in rate_markers):
            detail = ((r.stderr or r.stdout or "").strip()[:240]
                      or f"Claude CLI exited {r.returncode}")
            raise RuntimeError(f"subscription probe failed: {detail}")
        if r.returncode == 0:
            # Some CLI builds report a rate-window warning in a successful
            # envelope. It is still closed for campaign purposes.
            pass
        if waited >= max_wait_s:
            raise RuntimeError(
                f"subscription window did not reopen within {max_wait_s}s")
        print(f"    [pacing] {model_id} window closed — sleeping 15 min",
              flush=True)
        time.sleep(900)
        waited += 900


def _execute_capture(tech: Technique, pipe: str, args, ctx: dict) -> bool:
    """One (technique, pipeline) capture: run, fidelity-gate, persist,
    manifest. Returns True on an accepted capture. Thread-safe (manifest
    writes locked; per-capture output dir is exclusive to this pair)."""
    out_dir = capture_output_dir(tech, pipe)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Refuse the write before spending a model call on it: a directory another
    # cell already owns must not be overwritten.
    claim_capture_dir(tech, pipe, out_dir)
    tag = f"[{pipe}] {tech.key or tech.id}"
    print(f"{tag} …", flush=True)
    started = time.time()
    rec = {"technique": tech.id, "technique_key": tech.key,
           "capture_slug": tech.capture_slug, "kind": tech.kind,
           "mode": tech.intended_mode, "pipeline": pipe,
           "at": _now_iso(), "attempts": 0}
    last_err = None
    subscription_probe = (
        _subscription_probe_endpoint(tech, ctx["fidelity_contracts"][pipe])
        if pipe in ctx["subscription_lanes"] and pipe in ctx["fidelity_contracts"]
        else None
    )
    for attempt in (1, 2):  # one retry on transient failure
        rec["attempts"] = attempt
        try:
            if pipe in ctx["subscription_lanes"]:
                # Don't start a long pipeline run into a closed window, but
                # probe only a subscription model reachable on this pinned
                # mode's path. An unused Gear-4 Opus cell must not block a
                # legitimate Gear-2 Haiku capture.
                if subscription_probe:
                    _wait_for_subscription_window(subscription_probe)
            if pipe == "single-pass":
                sp = single_pass_call(ctx["flagship_ep"], tech.prompt)
                cost = price_single_pass(sp, ctx["flagship_pricing"])
                (out_dir / "answer.md").write_text(sp["text"])
                (out_dir / "cost.json").write_text(json.dumps({
                    "model_id": sp["model_id"], "via": sp["via"],
                    "prompt_tokens": sp["prompt_tokens"],
                    "completion_tokens": sp["completion_tokens"],
                    "pricing_per_million": ctx["flagship_pricing"],
                    "total_cost_usd": cost}, indent=2))
                rec.update(status="ok", cost_usd=cost,
                           prompt_tokens=sp["prompt_tokens"],
                           completion_tokens=sp["completion_tokens"],
                           visuals=0, via=sp["via"],
                           executed_models={sp["served_model"]: 1})
                if sp["via"] == "claude-code-subscription":
                    rec["cost_basis"] = "api_equivalent"
            elif pipe == "single-pass-9b":
                # Bare 9B control: same capture shape as single-pass, but a
                # metered OpenRouter call to qwen3.5-9b (real $, not subscription).
                # qwen3.5-9b is a reasoning model — its hidden chain-of-thought
                # burns completion tokens before the visible answer, so give it
                # generous headroom (env-overridable) to avoid truncating the
                # bare model's real single-pass output. OpenRouter clamps to the
                # model's own max if this is higher.
                sp = single_pass_call(
                    ctx["sp9b_ep"], tech.prompt,
                    max_tokens=int(os.environ.get(
                        "ORA_SINGLE_PASS_9B_MAX_TOKENS", "64000")))
                cost = price_single_pass(sp, ctx["sp9b_pricing"])
                (out_dir / "answer.md").write_text(sp["text"])
                (out_dir / "cost.json").write_text(json.dumps({
                    "model_id": sp["model_id"], "via": sp["via"],
                    "prompt_tokens": sp["prompt_tokens"],
                    "completion_tokens": sp["completion_tokens"],
                    "pricing_per_million": ctx["sp9b_pricing"],
                    "total_cost_usd": cost}, indent=2))
                rec.update(status="ok", cost_usd=cost,
                           prompt_tokens=sp["prompt_tokens"],
                           completion_tokens=sp["completion_tokens"],
                           visuals=0, via=sp["via"],
                           executed_models={sp["served_model"]: 1})
            else:
                conv_id = f"campaign-{tech.capture_slug or tech.id}-{pipe}"
                res = run_ora_pipeline(args.server, ORA_PIPELINES[pipe],
                                       tech, conv_id, timeout=args.timeout)
                # Fidelity gate BEFORE the capture counts: every model
                # that recorded usage must be a configured primary — a
                # 429/throttle cascade to a fallback model, or a silently
                # failed step, invalidates the run.
                fidelity = verify_trace_fidelity(
                    res["trace_dir"],
                    ctx["expected_primaries"][pipe],
                    ctx["fidelity_contracts"][pipe],
                )
                rec["executed_models"] = fidelity["executed"]
                rec["fidelity_warnings"] = fidelity["warnings"]
                if not fidelity["ok"]:
                    raise RuntimeError(
                        "fidelity violations: "
                        + json.dumps(fidelity["violations"][:6]))
                prose, envelopes = extract_visuals(res["text"])
                (out_dir / "answer.md").write_text(prose)
                n_png = 0
                if envelopes:
                    try:
                        _, n_png = render_visuals_browser(
                            args.server, envelopes, out_dir)
                    except ImportError:
                        # No Playwright: jsdom SVG only, no raster.
                        for vi, env in enumerate(envelopes, start=1):
                            (out_dir / f"visual-{vi}.json").write_text(env)
                            render_svg(env, out_dir / f"visual-{vi}.svg")
                    except Exception as vex:
                        print(f"{tag} [visual] browser render failed "
                              f"({str(vex)[:200]}); jsdom SVG fallback")
                        for vi, env in enumerate(envelopes, start=1):
                            (out_dir / f"visual-{vi}.json").write_text(env)
                            render_svg(env, out_dir / f"visual-{vi}.svg")
                cost = read_trace_cost(res["trace_dir"])
                if cost["total_cost_usd"] is None:
                    equiv = price_usage_records(res["trace_dir"],
                                                ctx["rate_map"])
                    if equiv is not None:
                        cost["total_cost_usd"] = equiv
                        rec["cost_basis"] = "api_equivalent"
                if res["trace_dir"]:
                    src = Path(res["trace_dir"]) / "cost-summary.json"
                    if src.exists():
                        (out_dir / "cost.json").write_text(src.read_text())
                rec.update(status="ok", trace_dir=res["trace_dir"],
                           cost_usd=cost["total_cost_usd"],
                           prompt_tokens=cost["prompt_tokens"],
                           completion_tokens=cost["completion_tokens"],
                           visuals=len(envelopes), visuals_png=n_png)
            # Written only on the accepted path, so a failed attempt never
            # leaves a sidecar claiming a capture that does not exist.
            write_capture_sidecar(
                tech, pipe, out_dir,
                source={"trace_dir": rec.get("trace_dir")}
                if rec.get("trace_dir") else None)
            rec["wall_seconds"] = round(time.time() - started, 1)
            append_manifest(rec)
            cost_str = (f"${rec.get('cost_usd'):.4f}" if rec.get("cost_usd")
                        else "unpriced")
            if rec.get("cost_basis") == "api_equivalent":
                cost_str += " (API-equivalent)"
            executed = rec.get("executed_models") or {}
            models_str = (" — models: " + ", ".join(
                f"{m}×{n}" for m, n in sorted(executed.items()))
                ) if executed else ""
            warn_str = (f" — {len(rec.get('fidelity_warnings') or [])} warning(s)"
                        if rec.get("fidelity_warnings") else "")
            print(f"{tag} ok in {rec['wall_seconds']}s — {cost_str}, "
                  f"{rec.get('visuals', 0)} visual(s){models_str}{warn_str}")
            return True
        except Exception as exc:
            last_err = str(exc)[:400]
            print(f"{tag} attempt {attempt} failed: {last_err}")
            # A rate-limited subscription mid-run: wait for the window
            # before the retry instead of burning it immediately.
            if "rate-limited" in last_err and pipe in ctx["subscription_lanes"]:
                try:
                    if subscription_probe:
                        _wait_for_subscription_window(subscription_probe)
                except RuntimeError:
                    break
                time.sleep(5)
            elif (("required_model_missing" in last_err
                   or "cell_primary_mismatch" in last_err)
                  and pipe in ctx["subscription_lanes"]):
                # A subscription cell fell through to another configured
                # primary. Revalidate the exact path model before retrying.
                try:
                    if subscription_probe:
                        _wait_for_subscription_window(subscription_probe)
                except RuntimeError:
                    break
                time.sleep(5)
            else:
                time.sleep(5)
    rec.update(status="failed", error=last_err,
               wall_seconds=round(time.time() - started, 1))
    append_manifest(rec)
    return False


# ─── Aggregation: cost tables ────────────────────────────────────────────


def aggregate() -> dict:
    done = load_manifest()
    snapshot = json.loads(SNAPSHOT_PATH.read_text()) if SNAPSHOT_PATH.exists() else {}
    # API-equivalent rate map: registry rates for every metered model, plus
    # claude-code:* priced at their API twin. The manifest records $0 for
    # subscription calls, so their real-world (non-subscriber) cost — which is
    # dominated by prompt-cache-creation input tokens — must be priced from
    # each run's usage.jsonl here, cache-aware.
    rate_map = _load_registry_pricing()
    for spec in CLAUDE_CODE_ENDPOINTS:
        eq = rate_map.get(spec["api_equivalent"])
        if eq:
            rate_map[spec["id"]] = dict(eq)
            rate_map[spec["model_id"]] = rate_map[spec["id"]]
    per: dict = {}
    for (tech_key, pipe), rec in done.items():
        if rec.get("status") != "ok":
            continue
        row = per.setdefault(pipe, {"runs": 0, "prompt_tokens": 0,
                                    "completion_tokens": 0, "cost_usd": 0.0,
                                    "unpriced_runs": 0, "visuals": 0,
                                    "wall_seconds": 0.0,
                                    "api_equivalent_runs": 0})
        row["runs"] += 1
        td = rec.get("trace_dir")
        toks = _sum_usage_tokens(td)
        # Token columns show TRUE input (incl. prompt-cache tokens); fall back
        # to the manifest's uncached counts only when no trace is available.
        if toks["prompt"] or toks["completion"] or toks["cache_create"]:
            row["prompt_tokens"] += (toks["prompt"] + toks["cache_create"]
                                     + toks["cache_read"])
            row["completion_tokens"] += toks["completion"]
        else:
            row["prompt_tokens"] += rec.get("prompt_tokens") or 0
            row["completion_tokens"] += rec.get("completion_tokens") or 0
        row["visuals"] += rec.get("visuals") or 0
        row["wall_seconds"] += rec.get("wall_seconds") or 0
        # Cost = API-equivalent. Lanes already api-equivalent-priced at run
        # time (single-pass) get a full cache-aware re-price; otherwise keep
        # the real metered cost and ADD the cache-aware API-equivalent of any
        # subscription (claude-code:*) calls the run made.
        if rec.get("cost_basis") == "api_equivalent":
            full = price_usage_records(td, rate_map)
            run_cost = full if full is not None else rec.get("cost_usd")
            if run_cost is not None:
                row["cost_usd"] += run_cost
                row["api_equivalent_runs"] += 1
            else:
                row["unpriced_runs"] += 1
        else:
            sub = price_usage_records(td, rate_map, subscription_only=True)
            base = rec.get("cost_usd")
            if base is None and sub is None:
                row["unpriced_runs"] += 1
            else:
                row["cost_usd"] += (base or 0.0) + (sub or 0.0)
                if sub:
                    row["api_equivalent_runs"] += 1

    grand = {"runs": sum(r["runs"] for r in per.values()),
             "cost_usd": round(sum(r["cost_usd"] for r in per.values()), 4),
             "prompt_tokens": sum(r["prompt_tokens"] for r in per.values()),
             "completion_tokens": sum(r["completion_tokens"] for r in per.values())}
    summary = {"generated_at": _now_iso(), "per_pipeline": per, "grand_total": grand}
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    (CAMPAIGN_DIR / "cost-summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    lines = ["# Campaign cost summary", "",
             f"_Generated {summary['generated_at']}_", ""]
    # Per-configuration model + rate descriptions (capture-time snapshot).
    cfgs = (snapshot.get("configs") or {})
    if cfgs:
        lines += ["## Configurations (models + per-1M rates at bake time)", ""]
        for cname, c in cfgs.items():
            models = c.get("models") or {}
            lines.append(f"### {cname}")
            lines.append("")
            lines.append("| slot | model | $/1M in | $/1M out |")
            lines.append("|---|---|---|---|")
            for slot in ("big1", "big2", "fast1", "fast2", "small"):
                m = models.get(slot)
                pr = (c.get("pricing") or {}).get(m) or {}
                lines.append(
                    f"| {slot} | {m or '—'} | "
                    f"{pr.get('input_per_million_usd', '—')} | "
                    f"{pr.get('output_per_million_usd', '—')} |")
            lines.append("")
        fp = snapshot.get("single_pass_flagship") or {}
        if fp:
            pr = fp.get("pricing") or {}
            lines += [f"### single-pass flagship", "",
                      f"`{fp.get('model_id')}` — "
                      f"${pr.get('input_per_million_usd', '?')}/1M in, "
                      f"${pr.get('output_per_million_usd', '?')}/1M out", ""]
    lines += ["## Per-pipeline totals", "",
              "| pipeline | runs | prompt tok | completion tok | visuals | wall (min) | cost (USD) | **$ / run** | **min / run** |",
              "|---|---|---|---|---|---|---|---|---|"]
    any_equiv = False
    for pipe in ALL_PIPELINES:
        r = per.get(pipe)
        if not r:
            continue
        unpriced = f" ({r['unpriced_runs']} unpriced)" if r["unpriced_runs"] else ""
        equiv = "†" if r.get("api_equivalent_runs") else ""
        any_equiv = any_equiv or bool(equiv)
        per_run_cost = r["cost_usd"] / r["runs"] if r["runs"] else 0.0
        per_run_min = r["wall_seconds"] / 60 / r["runs"] if r["runs"] else 0.0
        lines.append(
            f"| {pipe}{equiv} | {r['runs']} | {r['prompt_tokens']:,} | "
            f"{r['completion_tokens']:,} | {r['visuals']} | "
            f"{r['wall_seconds']/60:.1f} | ${r['cost_usd']:.4f}{unpriced} | "
            f"**${per_run_cost:.4f}** | **{per_run_min:.1f}** |")
    per_run_grand = grand["cost_usd"] / grand["runs"] if grand["runs"] else 0.0
    lines += ["",
              f"**Grand total: {grand['runs']} runs — ${grand['cost_usd']:.4f}** "
              f"({grand['prompt_tokens']:,} prompt + {grand['completion_tokens']:,} "
              f"completion tokens) — **${per_run_grand:.4f} per run**", ""]
    if any_equiv:
        lines += ["† includes Claude-subscription work (Claude Code) priced at "
                  "the API-equivalent rate — what a non-subscriber would pay; "
                  "$0 actual out-of-pocket for those calls. All input tokens "
                  "(incl. prompt-cache writes/reads) are priced once at the "
                  "standard input rate — the pipelines write caches they never "
                  "reread, so the uncached 1× basis is the honest figure.", ""]
    (CAMPAIGN_DIR / "cost-summary.md").write_text("\n".join(lines))
    print(f"[aggregate] → {CAMPAIGN_DIR / 'cost-summary.md'}")
    return summary


# ─── Campaign audit: completeness + accepted-trace health ────────────────


def _read_step_health(trace_dir: str | None) -> dict | None:
    if not trace_dir:
        return None
    path = Path(trace_dir) / "step-health.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"_parse_error": str(path)}


def audit_campaign(corpus_path: Path,
                   pipelines: list[str] | None = None,
                   campaign_dir: Path | None = None) -> dict:
    """Read corpus + latest manifest records and summarize campaign state.

    The audit intentionally looks at the latest accepted manifest record per
    ``technique_key × pipeline``. Old failed attempts remain in the append-only
    manifest for history, but they do not count against a pair once a later
    accepted capture exists.
    """
    selected_pipelines = pipelines or ALL_PIPELINES
    corpus_path = Path(corpus_path).expanduser().resolve()
    source_dir = Path(campaign_dir or CAMPAIGN_DIR).expanduser().resolve()
    manifest_path = source_dir / "campaign-manifest.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            "authoritative campaign manifest not found: "
            f"{manifest_path}; pass --campaign-dir explicitly")
    techs = parse_corpus(corpus_path)
    done = load_manifest(manifest_path)
    corpus_keys = {t.key for t in techs}
    verification = verify_campaign_captures(
        techs, selected_pipelines, done, campaign_dir=source_dir)
    verified_cells = verification["cells"]
    main4_verification = verify_campaign_captures(
        techs, MAIN_PIPELINES, done, campaign_dir=source_dir)
    main4_cells = main4_verification["cells"]

    duplicates: dict[str, list[str]] = {}
    by_public_id: dict[str, list[Technique]] = {}
    for tech in techs:
        by_public_id.setdefault(tech.id, []).append(tech)
    for public_id, rows in by_public_id.items():
        if len(rows) > 1:
            duplicates[public_id] = [t.key for t in rows]

    per_pipeline: dict[str, dict] = {}
    missing_by_pipeline: dict[str, list[str]] = {}
    failed_latest_by_pipeline: dict[str, list[dict]] = {}
    for pipe in selected_pipelines:
        pipe_rows = {"ok": 0, "failed": 0, "missing": 0, "total": len(techs)}
        missing: list[str] = []
        failed: list[dict] = []
        for tech in techs:
            rec = done.get((tech.key, pipe))
            cell = verified_cells[(tech.key, pipe)]
            status = (rec or {}).get("status")
            if cell["ok"]:
                pipe_rows["ok"] += 1
            elif status == "failed":
                pipe_rows["failed"] += 1
                failed.append({
                    "technique_key": tech.key,
                    "error": str((rec or {}).get("error") or "")[:240],
                    "at": (rec or {}).get("at"),
                })
            else:
                pipe_rows["missing"] += 1
                missing.append(tech.key)
        per_pipeline[pipe] = pipe_rows
        missing_by_pipeline[pipe] = missing
        failed_latest_by_pipeline[pipe] = failed

    complete_main4 = sum(
        1 for tech in techs
        if all(main4_cells[(tech.key, p)]["ok"]
               for p in MAIN_PIPELINES)
    )
    complete_selected = sum(
        1 for tech in techs
        if all(verified_cells[(tech.key, p)]["ok"]
               for p in selected_pipelines)
    )

    label_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {k: 0 for k in _SEVERITY_RANK}
    traces_with_contingencies: list[dict] = []
    accepted_trace_count = 0
    bare_control_records_excluded = 0
    accepted_trace_missing_health: list[dict] = []

    for tech in techs:
        for pipe in selected_pipelines:
            cell = verified_cells[(tech.key, pipe)]
            rec = done.get((tech.key, pipe)) or {}
            if not cell["ok"]:
                continue
            # Both bare controls intentionally have no Ora pipeline trace.
            # Counting either as missing step-health turns control shape into
            # a false runtime-integrity finding.
            if pipe in {"single-pass", "single-pass-9b"}:
                bare_control_records_excluded += 1
                continue
            accepted_trace_count += 1
            health = _read_step_health(rec.get("trace_dir"))
            if health is None:
                accepted_trace_missing_health.append({
                    "technique_key": tech.key,
                    "pipeline": pipe,
                    "trace_dir": rec.get("trace_dir"),
                })
                continue
            labels = list(health.get("contingencies_fired") or [])
            if not labels:
                severity_counts["clean"] += 1
                continue
            severity = _max_severity(labels)
            severity_counts[severity] += 1
            for label in labels:
                label_counts[label] = label_counts.get(label, 0) + 1
                category = classify_contingency(label)["category"]
                category_counts[category] = category_counts.get(category, 0) + 1
            traces_with_contingencies.append({
                "technique_key": tech.key,
                "pipeline": pipe,
                "severity": severity,
                "contingencies": labels,
                "trace_dir": rec.get("trace_dir"),
            })

    stale_manifest_keys = sorted({
        key for key, _pipe in done.keys()
        if key and key not in corpus_keys
    })

    accepted_trace_with_health = (
        accepted_trace_count - len(accepted_trace_missing_health))
    snapshot_at = max(
        (str(rec.get("at") or "") for rec in done.values()),
        default="",
    ) or None
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    corpus_sha256 = hashlib.sha256(corpus_path.read_bytes()).hexdigest()

    return {
        # Deterministic: rerunning against unchanged canonical inputs produces
        # byte-identical evidence instead of changing only a wall-clock stamp.
        "generated_at": snapshot_at,
        "source": {
            "campaign_dir": str(source_dir),
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "corpus_path": str(corpus_path),
            "corpus_sha256": corpus_sha256,
        },
        "corpus": {
            "entries": len(techs),
            "unique_keys": len(corpus_keys),
            "by_kind": {
                kind: sum(1 for t in techs if t.kind == kind)
                for kind in ("mode", "visual", "lens")
            },
            "duplicate_public_ids": duplicates,
        },
        "pipelines": selected_pipelines,
        "completeness": {
            "complete_main4": complete_main4,
            "complete_selected": complete_selected,
            "per_pipeline": per_pipeline,
            "missing_by_pipeline": missing_by_pipeline,
            "failed_latest_by_pipeline": failed_latest_by_pipeline,
        },
        "capture_integrity": {
            "checked_cells": verification["checked_cells"],
            "valid_cells": verification["valid_cells"],
            "affected_cells": verification["affected_cells"],
            "affected_by_pipeline": verification["affected_by_pipeline"],
            "evidence_counts": verification["evidence_counts"],
            "evidence_states": {
                "verified": "sidecar written from a live call; prompt hash "
                            "matches the corpus entry for this cell",
                "attested": "recovered from a preserved transcript; right cell "
                            "and prompt, but no surviving trace to hash the "
                            "request against",
                "unverified_legacy": "capture predates the sidecar; the bytes "
                                     "are not tied to this cell by anything",
                "missing": "no capture to certify",
                "sidecar_mismatch": "the sidecar names a different cell or "
                                    "prompt than this capture root declares",
            },
        },
        "accepted_trace_health": {
            "accepted_trace_count": accepted_trace_count,
            "accepted_trace_with_health": accepted_trace_with_health,
            "accepted_trace_missing_health": accepted_trace_missing_health,
            "bare_control_records_excluded": bare_control_records_excluded,
            "historical_step_health_limitation": (
                f"{len(accepted_trace_missing_health)} of "
                f"{accepted_trace_count} accepted Ora pipeline traces predate "
                "step-health persistence or lack a retained step-health file. "
                "This historical coverage gap is distinct from campaign-row "
                "completeness and is not represented as trace-health success."
            ),
            "severity_counts": severity_counts,
            "category_counts": category_counts,
            "contingency_label_counts": label_counts,
            "traces_with_contingencies": traces_with_contingencies,
        },
        "stale_manifest_keys": stale_manifest_keys,
    }


# ``outputs/`` holds finished records, not working output. An audit written
# there is a receipt for one run at one moment, kept alongside a closeout note
# that fingerprints it.
ACCEPTED_EVIDENCE_ROOT = ORA_HOME / "outputs"


def is_accepted_evidence_dir(destination: Path) -> bool:
    """True when ``destination`` lands inside the accepted-record tree."""
    try:
        from orchestrator import runtime_paths as _rp
        return bool(_rp.within_base(destination, ACCEPTED_EVIDENCE_ROOT))
    except Exception:
        # The path layer is not importable from every invocation of this
        # script. Path.is_relative_to compares components rather than string
        # prefixes, so it is boundary-anchored too; it only lacks the Windows
        # case-folding within_base adds.
        try:
            return destination.resolve().is_relative_to(
                ACCEPTED_EVIDENCE_ROOT.resolve())
        except (OSError, ValueError):
            return False


def write_campaign_audit(summary: dict,
                         output_dir: Path | None = None,
                         allow_accepted_overwrite: bool = False) -> tuple[Path, Path]:
    destination = Path(output_dir or CAMPAIGN_DIR).expanduser().resolve()
    if not allow_accepted_overwrite and is_accepted_evidence_dir(destination):
        raise SystemExit(
            f"[audit] refusing to overwrite accepted evidence in {destination}\n"
            "        This audit reads pipeline traces and a campaign manifest that\n"
            "        are deliberately temporary and git-ignored — traces are swept\n"
            "        after 30 days — so a re-run measures a corpus that no longer\n"
            "        matches the one the record was taken from. It cannot reproduce\n"
            "        the recorded numbers, only replace them with today's.\n"
            "        outputs/g1-2 was overwritten this way on 2026-08-19 and had to\n"
            "        be restored from git.\n"
            "        Write somewhere else:      --output-dir /tmp/campaign-audit\n"
            "        Or replace the record on purpose:  --allow-accepted-overwrite"
        )
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "campaign-audit.json"
    md_path = destination / "campaign-audit.md"
    json_path.write_text(json.dumps(summary, indent=2) + "\n")

    comp = summary["completeness"]
    integrity = summary["capture_integrity"]
    health = summary["accepted_trace_health"]
    lines = [
        "# Campaign Audit",
        "",
        f"_Generated {summary['generated_at']}_",
        "",
        "## Authenticated Sources",
        "",
        f"- Manifest: `{summary['source']['manifest_path']}`",
        f"- Manifest SHA-256: `{summary['source']['manifest_sha256']}`",
        f"- Corpus: `{summary['source']['corpus_path']}`",
        f"- Corpus SHA-256: `{summary['source']['corpus_sha256']}`",
        "",
        "## Corpus",
        "",
        f"- Entries: {summary['corpus']['entries']}",
        f"- Unique keys: {summary['corpus']['unique_keys']}",
        f"- By kind: {summary['corpus']['by_kind']}",
        f"- Duplicate public ids: {summary['corpus']['duplicate_public_ids'] or 'none'}",
        "",
        "## Completeness",
        "",
        f"- Complete main four lanes: {comp['complete_main4']} / {summary['corpus']['entries']}",
        f"- Complete selected lanes: {comp['complete_selected']} / {summary['corpus']['entries']}",
        "",
        "| pipeline | ok | failed latest | missing | total |",
        "|---|---:|---:|---:|---:|",
    ]
    for pipe, row in comp["per_pipeline"].items():
        lines.append(
            f"| {pipe} | {row['ok']} | {row['failed']} | {row['missing']} | {row['total']} |"
        )
    premium_resume = integrity["affected_by_pipeline"].get("premium") or []
    if premium_resume:
        lines += [
            "",
            "### Premium Resume Selector",
            "",
            "Use this after deciding to continue the subscription-paced lane:",
            "",
            "```text",
            ",".join(premium_resume),
            "```",
        ]

    lines += [
        "",
        "## Capture Integrity",
        "",
        f"- Declared cells checked by the physical verifier: {integrity['checked_cells']}",
        f"- Cells accepted by both manifest and capture verifier: {integrity['valid_cells']}",
        f"- Verifier-reported affected cells: {len(integrity['affected_cells'])}",
        "",
        "Evidence state counts. Only `verified` and `attested` tie a capture's "
        "bytes to the cell that claims them; `unverified_legacy` is an honest "
        "record of captures written before the sidecar existed.",
        "",
        "| evidence | cells |",
        "|---|---|",
    ]
    for state, count in sorted(integrity.get("evidence_counts", {}).items()):
        lines.append(f"| {state} | {count} |")
    lines += [
        "",
        "### Verifier-Reported Resume Selectors",
        "",
        "These selectors are derived from the current manifest and physical "
        "capture check; they are not a hard-coded exception list.",
        "",
    ]
    for pipe, keys in integrity["affected_by_pipeline"].items():
        if keys:
            lines += [f"#### {pipe}", "", "```text", ",".join(keys), "```", ""]

    lines += [
        "",
        "## Accepted Trace Health",
        "",
        f"- Bare control rows excluded from trace-health accounting: {health['bare_control_records_excluded']}",
        f"- Accepted Ora pipeline traces in scope: {health['accepted_trace_count']}",
        f"- Accepted Ora traces with retained step-health: {health['accepted_trace_with_health']}",
        f"- Historical Ora traces missing step-health: {len(health['accepted_trace_missing_health'])}",
        f"- Traces with contingencies: {len(health['traces_with_contingencies'])}",
        f"- Severity counts: {health['severity_counts']}",
        "",
        "### Historical Coverage Limitation",
        "",
        health["historical_step_health_limitation"],
        "",
        "Campaign-row completeness and trace-health coverage are separate. "
        "The 198/198 result certifies accepted row presence in every lane; "
        "it does not claim that historical step-health exists for every Ora trace.",
        "",
        "### Contingency Categories",
        "",
    ]
    for category, count in sorted(health["category_counts"].items(),
                                  key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- {category}: {count}")
    lines += ["", "### Top Contingency Labels", ""]
    for label, count in sorted(health["contingency_label_counts"].items(),
                               key=lambda kv: (-kv[1], kv[0]))[:20]:
        info = classify_contingency(label)
        lines.append(f"- {count} x `{label}` - {info['severity']} / {info['category']}")
    lines += ["", "### Highest-Severity Trace Samples", ""]
    for item in sorted(
        health["traces_with_contingencies"],
        key=lambda r: (-_SEVERITY_RANK.get(r["severity"], 0), r["technique_key"], r["pipeline"]),
    )[:40]:
        lines.append(
            f"- {item['severity']}: `{item['technique_key']}` / `{item['pipeline']}` - "
            + "; ".join(f"`{c}`" for c in item["contingencies"])
        )
    if summary["stale_manifest_keys"]:
        lines += ["", "## Stale Manifest Keys", ""]
        for key in summary["stale_manifest_keys"][:80]:
            lines.append(f"- `{key}`")
    md_path.write_text("\n".join(lines) + "\n")
    return json_path, md_path


# ─── Capture document ────────────────────────────────────────────────────

DOC_PIPELINE_ORDER = [
    ("premium", "Premium (Ora, gear 4)"),
    ("qwen9b", "Qwen 3.5 9B (Ora, gear 4 — single 9B model)"),
    ("optimum", "Optimum (Ora, gear 4)"),
    ("optimum-plus", "Optimum+ (Ora, gear 4 — flagship consolidator)"),
    ("single-pass", "Single-pass flagship (bare model, no harness)"),
    ("single-pass-9b", "Single-pass 9B (bare qwen3.5-9b, no harness)"),
]


def render_doc(corpus_path: Path) -> Path:
    techniques = parse_corpus(corpus_path)
    done = load_manifest()
    kind_label = {"mode": "Analysis mode", "visual": "Visual tool", "lens": "Lens"}
    lines = ["# Comparative Evaluation Campaign — captures", "",
             f"_Assembled {_now_iso()}. One section per campaign entry: the prime "
             f"prompt, then the six lane answers. Visuals are embedded "
             f"as PNG (SVG + envelope JSON sit alongside in captures/)._", ""]
    included = 0
    for tech in techniques:
        recs = {p: done.get((tech.key, p)) for p, _ in DOC_PIPELINE_ORDER}
        if not any((r or {}).get("status") == "ok" for r in recs.values()):
            continue
        included += 1
        lines += [f"## `{tech.id}` — {kind_label.get(tech.kind, tech.kind)} "
                  f"(mode: `{tech.intended_mode}`)", "",
                  f"> {tech.prompt}", ""]
        for pipe, label in DOC_PIPELINE_ORDER:
            rec = recs.get(pipe)
            if not rec or rec.get("status") != "ok":
                lines += [f"### {label}", "", "_not captured_", ""]
                continue
            cost = rec.get("cost_usd")
            meta = (f"{rec.get('prompt_tokens', 0):,} in / "
                    f"{rec.get('completion_tokens', 0):,} out tokens · "
                    + (f"${cost:.4f}" if cost is not None else "unpriced")
                    + f" · {rec.get('wall_seconds', 0):.0f}s")
            lines += [f"### {label}", "", f"_{meta}_", ""]
            cap = capture_read_dir(tech, pipe)
            answer = cap / "answer.md"
            if answer.exists():
                lines += [answer.read_text().strip(), ""]
            for png in sorted(cap.glob("visual-*.png")):
                rel = png.relative_to(CAMPAIGN_DIR)
                lines += [f"![{tech.id} visual]({rel})", ""]
        lines.append("---")
        lines.append("")
    out = CAMPAIGN_DIR / "campaign-capture.md"
    out.write_text("\n".join(lines))
    print(f"[render-doc] {included} technique sections → {out}")
    return out


# ─── CLI ─────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Comparative Evaluation Campaign runner.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("bake-configs", help="Bake campaign-premium/-optimum/-qwen9b + pricing snapshot.")
    sp.add_argument("--no-rebake", action="store_true",
                    help="Copy the presets as-is instead of re-baking them first.")
    sp.add_argument("--premium", choices=("api", "subscription"), default="api",
                    help="Premium lane execution: 'api' (picker-baked, metered) "
                         "or 'subscription' (Opus 4.8 big + Haiku 4.5 fast/small "
                         "via the local Claude Code CLI on your subscription; "
                         "cost tables show API-equivalent pricing).")
    sp.set_defaults(func=lambda a: (bake_configs(
        rebake_presets=not a.no_rebake, premium_mode=a.premium), 0)[1])

    sp = sub.add_parser("list", help="Parse the corpus; print counts + ids.")
    sp.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("run", help="Execute the sweep (resumable).")
    sp.add_argument("--techniques", default="all",
                    help="'all' | 'some' (12-technique sampler) | comma-separated ids")
    sp.add_argument("--pipelines", default=",".join(ALL_PIPELINES))
    sp.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    sp.add_argument("--server", default=DEFAULT_SERVER)
    sp.add_argument("--timeout", type=int, default=2400, help="per-run seconds")
    sp.add_argument("--limit", type=int, default=0, help="cap runs this invocation")
    sp.add_argument("--concurrency", type=int, default=1,
                    help="workers WITHIN each API lane (lanes always run in "
                         "parallel; subscription lanes default to 1 — the rate "
                         "window is their bottleneck).")
    sp.add_argument("--subscription-concurrency", type=int, default=1,
                    help="workers WITHIN subscription lanes (premium). Default "
                         "1 — rate-window-safe for the unattended sweep. Raise "
                         "for an ATTENDED burst on a high-tier account with "
                         "window headroom: it saturates the available rate "
                         "budget; a mid-call throttle just fails-and-retries "
                         "through the existing pacing loop.")
    sp.add_argument("--force-rerun", action="store_true",
                    help="Ignore completed manifest entries for the selected "
                         "scope (re-capture after a config change).")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(func=run_sweep)

    sp = sub.add_parser("aggregate", help="Cost tables from the manifest.")
    sp.set_defaults(func=lambda a: (aggregate(), 0)[1])

    sp = sub.add_parser("audit", help="Audit campaign completeness and trace health.")
    sp.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    sp.add_argument("--pipelines", default=",".join(ALL_PIPELINES))
    sp.add_argument(
        "--campaign-dir",
        default=str(CAMPAIGN_DIR),
        help="authoritative campaign directory containing campaign-manifest.jsonl; "
             "defaults to the checkout-local manifest, then the historical "
             "~/ora reference-campaign manifest",
    )
    sp.add_argument(
        "--output-dir",
        default="",
        help="write campaign-audit.json/.md here (default: campaign source dir)",
    )
    sp.add_argument("--no-write", action="store_true",
                    help="print the summary without writing campaign-audit.*")
    sp.add_argument("--allow-accepted-overwrite", action="store_true",
                    help="permit writing into outputs/, replacing an accepted "
                         "record; refused by default because the audit's inputs "
                         "are temporary and a re-run cannot reproduce them")
    sp.set_defaults(func=cmd_audit)

    sp = sub.add_parser("render-doc", help="Assemble the capture document.")
    sp.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    sp.set_defaults(func=lambda a: (render_doc(Path(a.corpus)), 0)[1])

    sp = sub.add_parser("all", help="bake-configs → run → aggregate → render-doc.")
    sp.add_argument("--techniques", default="all")
    sp.add_argument("--pipelines", default=",".join(ALL_PIPELINES))
    sp.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    sp.add_argument("--server", default=DEFAULT_SERVER)
    sp.add_argument("--timeout", type=int, default=2400)
    sp.add_argument("--limit", type=int, default=0)
    sp.add_argument("--concurrency", type=int, default=1)
    sp.add_argument("--force-rerun", action="store_true")
    sp.add_argument("--premium", choices=("api", "subscription"), default="api")
    sp.set_defaults(func=cmd_all)

    return p


def cmd_list(args) -> int:
    techs = parse_corpus(Path(args.corpus))
    by_kind: dict = {}
    id_counts: dict[str, int] = {}
    for t in techs:
        by_kind.setdefault(t.kind, []).append(t)
        id_counts[t.id] = id_counts.get(t.id, 0) + 1
    for kind in ("mode", "visual", "lens"):
        items = by_kind.get(kind, [])
        print(f"{kind}: {len(items)}")
        for tech in items:
            suffix = f" [select as {tech.key}]" if id_counts.get(tech.id, 0) > 1 else ""
            print(f"  {tech.id}{suffix}")
    print(f"total: {len(techs)}")
    missing_some = [s for s in SOME_SUBSET if s not in {t.id for t in techs}]
    if missing_some:
        print(f"WARNING: 'some' subset ids not in corpus: {missing_some}")
    return 0


def cmd_audit(args) -> int:
    pipelines = [p.strip() for p in args.pipelines.split(",") if p.strip()]
    unknown = [p for p in pipelines if p not in ALL_PIPELINES]
    if unknown:
        raise SystemExit(f"unknown pipeline(s): {unknown}; choose from {ALL_PIPELINES}")
    summary = audit_campaign(
        Path(args.corpus),
        pipelines=pipelines,
        campaign_dir=Path(args.campaign_dir),
    )
    comp = summary["completeness"]
    health = summary["accepted_trace_health"]
    print(
        f"[audit] entries={summary['corpus']['entries']} "
        f"complete_main4={comp['complete_main4']} "
        f"complete_selected={comp['complete_selected']}"
    )
    for pipe, row in comp["per_pipeline"].items():
        print(
            f"[audit] {pipe}: ok={row['ok']} failed={row['failed']} "
            f"missing={row['missing']} total={row['total']}"
        )
    print(
        f"[audit] ora_traces={health['accepted_trace_count']} "
        f"health_present={health['accepted_trace_with_health']} "
        f"with_contingencies={len(health['traces_with_contingencies'])} "
        f"historical_missing_health={len(health['accepted_trace_missing_health'])} "
        f"bare_controls_excluded={health['bare_control_records_excluded']}"
    )
    integrity = summary["capture_integrity"]
    print(
        f"[audit] capture_cells={integrity['checked_cells']} "
        f"capture_valid={integrity['valid_cells']} "
        f"capture_affected={len(integrity['affected_cells'])}"
    )
    print(f"[audit] capture_evidence={integrity.get('evidence_counts', {})}")
    print(f"[audit] severity_counts={health['severity_counts']}")
    print(
        f"[audit] manifest={summary['source']['manifest_path']} "
        f"sha256={summary['source']['manifest_sha256']}"
    )
    print(
        f"[audit] corpus={summary['source']['corpus_path']} "
        f"sha256={summary['source']['corpus_sha256']}"
    )
    if not args.no_write:
        output_dir = Path(args.output_dir) if args.output_dir else None
        json_path, md_path = write_campaign_audit(
            summary, output_dir=output_dir,
            allow_accepted_overwrite=args.allow_accepted_overwrite,
        )
        print(f"[audit] wrote {json_path}")
        print(f"[audit] wrote {md_path}")
    return 0 if comp["complete_selected"] == summary["corpus"]["entries"] else 1


def cmd_all(args) -> int:
    bake_configs(premium_mode=getattr(args, "premium", "api"))
    rc = run_sweep(args)
    aggregate()
    render_doc(Path(args.corpus))
    return rc


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
