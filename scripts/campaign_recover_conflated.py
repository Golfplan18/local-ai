#!/usr/bin/env python3
"""One-shot repair for campaign captures lost to a shared capture directory.

Background
----------
Two public ids appear twice in the Trigger Prompt Corpus: ``causal-dag`` is
both a reasoning mode and a visual renderer, and ``fishbone-diagram`` is both a
visual renderer and a lens. Four corpus entries, six lanes each, twenty-four
declared cells. All twenty-four ran and the manifest recorded each one
honestly. But both entries of a pair wrote into one directory named after the
shared public id, so whichever finished second overwrote the first: twelve
surviving files backing twenty-four cells.

This script repairs the capture tree without rerunning anything that can be
recovered from evidence already on disk.

  * The twelve survivors move into the kind-qualified root of the cell that
    actually produced them. Ownership is established by matching each capture
    file's modification time against the timestamp of the last assistant turn
    in the preserved session transcript, and — on the two subscription lanes,
    which keep no transcript — by scoring the answer against the distinctive
    vocabulary of the two candidate prompts.
  * The eight overwritten multi-agent cells are rebuilt from those same
    transcripts, which still hold the lost answer in full, including its
    embedded ``ora-visual`` diagram spec.
  * Every repaired cell gets a capture sidecar marked ``recovered``, carrying
    the proof. None of them can ever be ``verified`` — no trace survives to
    hash the original request against — and the audit reports them as
    ``attested`` permanently rather than pretending otherwise.

The four subscription-lane cells with no transcript are left ``missing``. They
are one prompt and one model call each and are cheaper to rerun than to argue
about.

``data/campaign/`` is outside Git, so this script takes its own snapshot of
the capture tree and the manifest before the first mutation and prints the
restore command. That snapshot is the rollback point.

The manifest is deliberately not written to. It was never wrong.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import campaign_run as C  # noqa: E402

DEFAULT_SESSIONS = Path.home() / "ora-purge-hold-2026-08-15" / "sessions"

# Words too common to tell two prompts apart.
_STOPWORDS = {
    "what", "would", "happen", "with", "that", "this", "from", "into", "your",
    "their", "which", "when", "does", "keep", "using", "include", "between",
    "relationship", "causes", "cause", "root", "diagram", "categories",
    "category", "analysis", "these", "there", "about", "have", "been",
}


def _log(msg: str) -> None:
    print(msg, flush=True)


def distinctive_terms(prompt: str, other: str) -> set[str]:
    """Words that appear in one prompt and not the other."""
    def words(text: str) -> set[str]:
        return {w for w in re.findall(r"[a-z]{4,}", text.lower())}
    return words(prompt) - words(other) - _STOPWORDS


def score_answer(answer: str, terms: set[str]) -> int:
    """How many of a prompt's distinctive words the answer actually uses."""
    body = answer.lower()
    return sum(1 for term in terms if term in body)


def load_transcript(sessions_dir: Path, slug: str, lane: str) -> list[dict]:
    path = sessions_dir / f"campaign-{slug}-{lane}" / "conversation.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    msgs = data.get("messages") if isinstance(data, dict) else data
    return [m for m in (msgs or []) if isinstance(m, dict)]


def _norm(text: str) -> str:
    return " ".join((text or "").split()).lower()


def turns_for_prompt(msgs: list[dict], prompt: str) -> list[tuple[int, dict]]:
    """User turns matching a prompt, paired with the assistant reply after."""
    target = _norm(prompt)
    out = []
    for i, m in enumerate(msgs):
        if m.get("role") != "user":
            continue
        if _norm(str(m.get("content") or "")) != target:
            continue
        if i + 1 < len(msgs) and msgs[i + 1].get("role") == "assistant":
            out.append((i + 1, msgs[i + 1]))
    return out


def snapshot(campaign_dir: Path, out_dir: Path) -> Path:
    """Tar the capture tree and manifest. This is the rollback point."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    archive = out_dir / f"campaign-captures-before-g12-{stamp}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(campaign_dir / "captures", arcname="captures")
        manifest = campaign_dir / "campaign-manifest.jsonl"
        if manifest.is_file():
            tar.add(manifest, arcname="campaign-manifest.jsonl")
    _log(f"[snapshot] {archive} ({archive.stat().st_size:,} bytes)")
    _log(f"[snapshot] restore with:\n"
         f"    tar -xzf {archive} -C {campaign_dir}")
    return archive


def cost_from_manifest(rec: dict | None) -> dict:
    """Rebuild a cost record from the manifest row for the same run.

    The manifest kept each cell's real cost even though the capture file was
    overwritten, so this is the recorded cost of this exact run rather than an
    invented number. It is marked as reconstructed so nobody later mistakes it
    for a figure read off a trace.
    """
    rec = rec or {}
    return {
        "status": "reconstructed_from_manifest",
        "note": "Capture file was lost to a shared capture directory; these "
                "figures come from the manifest row for this cell's run.",
        "model_id": None,
        "via": rec.get("via"),
        "prompt_tokens": rec.get("prompt_tokens"),
        "completion_tokens": rec.get("completion_tokens"),
        "total_cost_usd": rec.get("cost_usd"),
        "cost_basis": rec.get("cost_basis"),
        "manifest_at": rec.get("at"),
    }


def resolve_owner(pair: list, lane: str, legacy_dir: Path,
                  sessions_dir: Path) -> dict:
    """Decide which of two colliding cells produced the surviving capture."""
    answer_path = legacy_dir / "answer.md"
    answer = answer_path.read_text(encoding="utf-8", errors="replace")
    mtime = datetime.fromtimestamp(answer_path.stat().st_mtime)
    slug = pair[0].id

    msgs = load_transcript(sessions_dir, slug, lane)
    if msgs:
        # The runner wrote the capture at the moment the last assistant turn
        # landed. Matching those two timestamps names the owner outright.
        last = None
        for i, m in enumerate(msgs):
            if m.get("role") == "assistant":
                last = (i, m)
        if last:
            ts = str(last[1].get("timestamp") or "")
            if ts and abs((datetime.fromisoformat(ts) - mtime).total_seconds()) <= 2:
                for tech in pair:
                    hits = turns_for_prompt(msgs, tech.prompt)
                    if any(idx == last[0] for idx, _ in hits):
                        return {
                            "owner": tech,
                            "method": "transcript_mtime_match",
                            "proof": {
                                "session": str(
                                    sessions_dir / f"campaign-{slug}-{lane}"),
                                "message_index": last[0],
                                "turn_timestamp": ts,
                                "capture_mtime": mtime.isoformat(),
                            },
                        }

    # No transcript (the subscription lanes keep none). Fall back to which
    # prompt's distinctive vocabulary the answer actually speaks.
    a, b = pair
    score_a = score_answer(answer, distinctive_terms(a.prompt, b.prompt))
    score_b = score_answer(answer, distinctive_terms(b.prompt, a.prompt))
    if score_a == score_b:
        raise RuntimeError(
            f"cannot attribute {legacy_dir}: {a.key} and {b.key} score "
            f"equally ({score_a})")
    owner, loser, hi, lo = ((a, b, score_a, score_b) if score_a > score_b
                            else (b, a, score_b, score_a))
    return {
        "owner": owner,
        "method": "prompt_vocabulary_score",
        "proof": {
            "winner": owner.key, "winner_score": hi,
            "runner_up": loser.key, "runner_up_score": lo,
            "capture_mtime": mtime.isoformat(),
        },
    }


def recover_from_transcript(tech, lane: str, sessions_dir: Path,
                            manifest_rec: dict | None, dest: Path,
                            dry_run: bool) -> dict | None:
    """Rebuild an overwritten cell from its preserved session transcript."""
    msgs = load_transcript(sessions_dir, tech.id, lane)
    if not msgs:
        return None
    hits = turns_for_prompt(msgs, tech.prompt)
    if len(hits) != 1:
        raise RuntimeError(
            f"{tech.key}/{lane}: expected exactly one turn for this prompt in "
            f"the transcript, found {len(hits)} — refusing to guess")
    idx, msg = hits[0]
    text = str(msg.get("content") or "")
    prose, envelopes = C.extract_visuals(text)
    proof = {
        "session": str(sessions_dir / f"campaign-{tech.id}-{lane}"),
        "message_index": idx,
        "turn_timestamp": msg.get("timestamp"),
        "recovered_because": "capture overwritten by a colliding capture slug",
    }
    if dry_run:
        return {"prose_bytes": len(prose), "visuals": len(envelopes),
                "proof": proof}

    dest.mkdir(parents=True, exist_ok=True)
    (dest / "answer.md").write_text(prose)
    (dest / "cost.json").write_text(
        json.dumps(cost_from_manifest(manifest_rec), indent=2) + "\n")
    rendered = 0
    for vi, env in enumerate(envelopes, start=1):
        (dest / f"visual-{vi}.json").write_text(env)
        try:
            C.render_svg(env, dest / f"visual-{vi}.svg")
            rendered += 1
        except Exception as exc:  # renderer absent or envelope unrenderable
            _log(f"    [visual] {tech.key}/{lane} figure {vi} not rendered: "
                 f"{str(exc)[:160]}")
    proof["visuals_recovered"] = len(envelopes)
    proof["visuals_rendered"] = rendered
    C.write_capture_sidecar(tech, lane, dest,
                            evidence=C.EVIDENCE_RECOVERED, source=proof)
    return {"prose_bytes": len(prose), "visuals": len(envelopes),
            "rendered": rendered, "proof": proof}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, default=C.DEFAULT_CORPUS)
    ap.add_argument("--sessions", type=Path, default=DEFAULT_SESSIONS,
                    help="preserved session tree holding the lost answers")
    ap.add_argument("--campaign-dir", type=Path, default=C.CAMPAIGN_DIR)
    ap.add_argument("--snapshot-dir", type=Path, default=None,
                    help="where the pre-migration tarball is written "
                         "(default: <campaign-dir>/_g12-rollback)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would happen and touch nothing")
    args = ap.parse_args()

    campaign_dir = args.campaign_dir.expanduser().resolve()
    captures = campaign_dir / "captures"
    techs = C.parse_corpus(args.corpus)
    done = C.load_manifest(campaign_dir / "campaign-manifest.jsonl")

    pairs: dict[str, list] = {}
    for tech in techs:
        pairs.setdefault(tech.id, []).append(tech)
    pairs = {tid: group for tid, group in pairs.items() if len(group) > 1}
    if not pairs:
        _log("[recover] no duplicate public ids in the corpus — nothing to do")
        return 0
    _log(f"[recover] duplicate ids: {', '.join(sorted(pairs))}")

    if not args.dry_run:
        snapshot(campaign_dir,
                 args.snapshot_dir or (campaign_dir / "_g12-rollback"))

    moved = recovered = left_missing = 0
    for tid, pair in sorted(pairs.items()):
        legacy_root = captures / tid
        for lane in C.ALL_PIPELINES:
            legacy = legacy_root / lane
            if not (legacy / "answer.md").is_file():
                _log(f"  {tid}/{lane}: no legacy capture — skipped")
                continue

            verdict = resolve_owner(pair, lane, legacy, args.sessions)
            owner = verdict["owner"]
            loser = next(t for t in pair if t.key != owner.key)
            _log(f"  {tid}/{lane}: owner={owner.key} "
                 f"via {verdict['method']}")

            dest = C.capture_output_dir(owner, lane, campaign_dir)
            if not args.dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    raise RuntimeError(f"destination already exists: {dest}")
                shutil.move(str(legacy), str(dest))
                C.write_capture_sidecar(
                    owner, lane, dest, evidence=C.EVIDENCE_RECOVERED,
                    source={"rehoused_from": str(legacy),
                            "attribution_method": verdict["method"],
                            **verdict["proof"]})
            moved += 1

            result = recover_from_transcript(
                loser, lane, args.sessions,
                done.get((loser.key, lane)),
                C.capture_output_dir(loser, lane, campaign_dir),
                args.dry_run)
            if result:
                _log(f"      recovered {loser.key}: "
                     f"{result['prose_bytes']:,} chars, "
                     f"{result['visuals']} visual(s)")
                recovered += 1
            else:
                _log(f"      {loser.key}: no transcript — left for rerun")
                left_missing += 1

        if not args.dry_run and legacy_root.exists():
            leftovers = list(legacy_root.iterdir())
            if leftovers:
                raise RuntimeError(
                    f"legacy root {legacy_root} not empty: {leftovers}")
            legacy_root.rmdir()
            _log(f"  removed shared legacy root {legacy_root}")

    _log(f"[recover] rehoused {moved}, recovered {recovered}, "
         f"left for rerun {left_missing}"
         + (" (dry run — nothing written)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
