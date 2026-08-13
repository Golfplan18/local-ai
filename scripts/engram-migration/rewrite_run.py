#!/usr/bin/env python3
"""Rewrite every merged note from the FULL text of its own source notes.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

Replaces stage5_run.py, which implemented the approach that failed. Every choice
here is a measurement, not a preference:

  FULL SOURCE TEXT, never extracts. The previous pass received member titles plus
  a list of "specifics" mined from the bodies -- isolated keywords, bare dates,
  filename debris. It assembled those fragments into fluent Instance lines, and a
  50-note audit found every edited note needed its evidence line changed. The
  qualifying clauses that carry the claims ("despite the dual mandate of price
  stability and full employment", "without any elected official casting a vote")
  live in the bodies, so a writer that never saw the bodies could not keep them.
  56% of notes lost at least one claim.

  BATCH 1. Blind-judged on 8 notes with 2 judges: Opus met the owner's bar 16/16
  at batch 1 and 12/16 at batch 8. Batching costs about a quarter of the quality.
  --batch is available for measuring, but 1 is the measured default.

  MODEL ROUTE. The original run used Opus. Further work uses the explicit
  ``codex-cli`` backend and GPT-5.6 Sol; validate a representative pilot before
  completing the remaining work so a transport change cannot silently lower the
  writing standard.

  SHARDING, so N independent processes cannot collide. Resume works by checking
  which output files exist, which means two processes sharing a worklist would both
  claim the same undone note. --shard k/N partitions deterministically by a hash of
  the note filename, so eight terminals, eight machines, or eight sessions can each
  take a slice with no coordination and no overlap.

  ONE OUTPUT FILE PER NOTE. 64k small files rather than shard-sized aggregates:
  resume is an existence check, a killed process loses at most the calls in flight,
  and no two writers ever touch the same file.

Dry run by default. --apply performs the model calls and writes results. Nothing
here modifies the vault; stage7 does that, from these results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ORA_HOME = os.environ.get("ORA_HOME", str(Path.home() / "ora"))
if ORA_HOME not in sys.path:
    sys.path.insert(0, ORA_HOME)

ARCHIVE_SUBDIR = "Archive/Engram Absorbed Sources 2026-08"
MODEL_HINT = "gpt-5.6-sol"
# Each backend's pinned model. Both are non-Opus by construction; the explicit
# Opus refusal below is what enforces that intent, rather than an enumeration
# that has to be widened every time a transport is added.
BACKEND_MODELS = {"codex-cli": MODEL_HINT, "minimax": "MiniMax-M3"}

_CHILD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "body"],
    "properties": {
        "title": {"type": "string", "minLength": 1},
        "body": {"type": "string", "minLength": 1},
    },
}
_NOTE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "note_id", "verdict", "title", "body", "conversion",
        "domain_bound", "split_second_note",
    ],
    "properties": {
        "note_id": {"type": "string", "minLength": 1},
        "verdict": {"type": "string", "enum": ["KEEP", "SPLIT", "ARCHIVE"]},
        "title": {"type": "string", "minLength": 1},
        "body": {"type": "string", "minLength": 1},
        "conversion": {"type": "string", "minLength": 1},
        "domain_bound": {"type": "boolean"},
        "split_second_note": {"anyOf": [_CHILD_SCHEMA, {"type": "null"}]},
    },
}
REWRITE_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["notes"],
    "properties": {
        "notes": {"type": "array", "minItems": 1, "items": _NOTE_SCHEMA},
    },
}

_ABSORBED = re.compile(r"^absorbed_from:\s*\n((?:[ \t]*-[ \t]+\S.*\n)+)", re.M)
_H1 = re.compile(r"^#\s+(.+)$", re.M)
_FENCE = re.compile(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", re.DOTALL)
_lock = threading.Lock()


def body_of(text: str) -> str:
    parts = text.split("---", 2)
    s = parts[2] if len(parts) > 2 else text
    return re.sub(r"\n##\s+Source\b.*$", "", s, flags=re.S).strip()


def absorbed_of(text: str) -> list[str]:
    m = _ABSORBED.search(text)
    if not m:
        return []
    return [ln.strip().lstrip("-").strip().strip("'\"")
            for ln in m.group(1).splitlines() if ln.strip()]


def shard_of(name: str, n: int) -> int:
    """Deterministic, stable across processes and runs. Not Python's hash(),
    which is salted per interpreter and would reshard on every launch."""
    return int(hashlib.sha1(name.encode("utf-8")).hexdigest()[:8], 16) % n


def _balanced(raw: str, start: int) -> str | None:
    """Extract the balanced JSON value starting at raw[start], respecting strings
    and escapes. A first-brace-to-last-brace slice breaks whenever the CLI appends
    anything after the JSON (a status line, a rate-limit notice), which is the
    failure this replaces."""
    opener = raw[start]
    closer = {"{": "}", "[": "]"}[opener]
    depth, i, in_str, esc = 0, start, False, False
    while i < len(raw):
        c = raw[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return raw[start:i + 1]
        i += 1
    return None


def _contains_json_value(raw: str) -> bool:
    for i, char in enumerate(raw):
        if char not in "{[":
            continue
        candidate = _balanced(raw, i)
        if not candidate:
            continue
        try:
            json.loads(candidate)
        except json.JSONDecodeError:
            continue
        return True
    return False


def parse_reply(text: str) -> dict | None:
    raw = (text or "").strip()
    m = _FENCE.search(raw)
    if m:
        prefix = raw[:m.start()].strip()
        suffix = raw[m.end():].strip()
        if _contains_json_value(prefix) or _contains_json_value(suffix):
            return None
        raw = m.group(1).strip()
    # Try every plausible JSON start. Accept a complete wrapper only when any
    # surrounding text is plain CLI prose: braces/brackets in surrounding text
    # are ambiguous and could hide a conflicting duplicate from batch-level ID
    # validation.
    starts = [i for i, c in enumerate(raw) if c in "{["]
    for i in starts[:6]:
        cand = _balanced(raw, i)
        if not cand:
            continue
        try:
            v = json.loads(cand)
        except json.JSONDecodeError:
            continue
        wrapped = None
        if isinstance(v, dict) and isinstance(v.get("notes"), list):
            wrapped = v
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            wrapped = {"notes": v}
        if wrapped is not None:
            prefix = raw[:i].strip()
            tail = raw[i + len(cand):].strip()
            if _contains_json_value(prefix) or _contains_json_value(tail):
                return None
            return wrapped
        # Do not return the first bare note object here. A malformed response may
        # contain duplicate or unexpected note IDs; the scavenger below must keep
        # every candidate so batch validation can reject that ambiguity.
    # Last resort: scavenge every balanced object that looks like a note. Covers a
    # malformed wrapper around a multi-note reply, where no single start yields a
    # usable value.
    found = []
    for i, c in enumerate(raw):
        if c != "{":
            continue
        cand = _balanced(raw, i)
        if not cand:
            continue
        try:
            v = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(v, dict) and v.get("note_id") and v.get("title"):
            found.append(v)
    if found:
        return {"notes": found}
    return None


def _text_error(value: object, label: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return f"{label} must be a non-empty string"
    return None


def _note_text_error(title: object, body: object, prefix: str = "") -> str | None:
    error = _text_error(title, f"{prefix}title")
    if error:
        return error
    assert isinstance(title, str)
    if title != title.strip() or "\n" in title or "\r" in title:
        return f"{prefix}title must be one trimmed line"
    if any(mark in title for mark in ("*", "_", "`", "#")):
        return f"{prefix}title contains forbidden markdown"
    error = _text_error(body, f"{prefix}body")
    if error:
        return error
    assert isinstance(body, str)
    lines = body.strip().splitlines()
    if not lines or any(not line.startswith("- ") for line in lines):
        return f"{prefix}body must contain only non-empty '- ' bullet lines"
    if any(line.strip() == "---" for line in lines):
        return f"{prefix}body contains a diagnostic separator"
    return None


def record_error(rec: object, *, expected_note_id: str | None = None,
                 expected_sources: list[str] | None = None) -> str | None:
    """Return why a rewrite record is unsafe to persist, or ``None``.

    ``conversion`` and ``domain_bound`` are diagnostic fields: new structured
    output requires them, but older recovered records may omit them without
    losing any field used to build a note. If present, their types remain strict.
    """
    if not isinstance(rec, dict):
        return "record must be an object"
    allowed = {
        "note_id", "verdict", "title", "body", "conversion", "domain_bound",
        "split_second_note", "source_files",
    }
    unknown = sorted(set(rec) - allowed)
    if unknown:
        return f"unexpected fields: {', '.join(unknown)}"
    note_id = rec.get("note_id")
    if not isinstance(note_id, str) or not note_id:
        return "note_id must be a non-empty string"
    if expected_note_id is not None and note_id != expected_note_id:
        return f"note_id {note_id!r} does not match {expected_note_id!r}"
    verdict = rec.get("verdict")
    if verdict not in {"KEEP", "SPLIT", "ARCHIVE"}:
        return f"invalid verdict {verdict!r}"
    error = _note_text_error(rec.get("title"), rec.get("body"))
    if error:
        return error
    if "conversion" in rec:
        error = _text_error(rec["conversion"], "conversion")
        if error:
            return error
    if "domain_bound" in rec and not isinstance(rec["domain_bound"], bool):
        return "domain_bound must be a boolean"
    child = rec.get("split_second_note")
    if verdict == "SPLIT":
        if not isinstance(child, dict):
            return "SPLIT requires split_second_note"
        child_allowed = {"title", "body"}
        child_unknown = sorted(set(child) - child_allowed)
        if child_unknown:
            return f"split_second_note has unexpected fields: {', '.join(child_unknown)}"
        error = _note_text_error(child.get("title"), child.get("body"), "split ")
        if error:
            return error
    elif child is not None:
        return f"{verdict} must not contain split_second_note"
    if expected_sources is not None:
        sources = rec.get("source_files")
        if sources != expected_sources:
            return "source_files do not exactly match the note's absorbed_from list"
    elif "source_files" in rec:
        sources = rec["source_files"]
        if (not isinstance(sources, list)
                or any(not isinstance(item, str) or not item for item in sources)):
            return "source_files must be a list of non-empty strings"
    return None


def output_file_error(path: Path, *, note_id: str,
                      expected_sources: list[str]) -> str | None:
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return f"cannot read valid JSON: {exc}"
    return record_error(
        rec, expected_note_id=note_id, expected_sources=expected_sources,
    )


def build_user(units: list[dict]) -> str:
    """Full source text. No extracts, no truncation of the claims themselves."""
    payload = [{
        "note_id": u["note_id"],
        "current_note": u["current_note"],
        "originals": [{"file": o["file"], "full_text": o["full_text"]} for o in u["originals"]],
    } for u in units]
    n = len(units)
    return (
        f"Rewrite {'this note' if n == 1 else f'each of these {n} notes'} from the "
        f"full text of its own source notes.\n\n"
        "`current_note` is the previous attempt. It is evidence of a failure mode, "
        "NOT a draft to edit — write fresh from the sources.\n\n"
        "Return ONLY a JSON object: {\"notes\": [{\"note_id\": ..., \"verdict\": "
        "\"KEEP\"|\"SPLIT\"|\"ARCHIVE\", \"title\": ..., \"body\": ..., "
        "\"conversion\": ..., \"domain_bound\": true|false, \"split_second_note\": "
        "null|{\"title\": ..., \"body\": ...}}]}\n\n"
        "`body` is the bullet lines, each starting \"- \". Use SPLIT when the "
        "sources carry two claims one note would have to fudge — 20% of "
        "multi-source groups do, and 8% actually contradict each other. Split "
        "only claims that are independently reusable; never split away a "
        "qualification whose absence would make the first note misleading. Each "
        "child must itself be coherent; do not bundle incompatible alternatives "
        "under one generic child title. Put "
        "the second claim in split_second_note; otherwise set it to null. Use ARCHIVE "
        "only when the general form would be a truism. Put no headings, separators, "
        "or editorial commentary in body.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", default=str(Path.home() / "engram-work"))
    ap.add_argument("--out", default=None, help="default <vault>/.migration/rewrite")
    ap.add_argument("--prompt", default=str(Path(__file__).with_name("rewrite_prompt.md")))
    ap.add_argument("--backend", default="codex-cli",
                    choices=tuple(BACKEND_MODELS),
                    help="non-Opus transport. 'codex-cli' runs GPT-5.6 Sol with a "
                         "generation-time JSON schema, and has NOT yet met this "
                         "writing bar (PLAN.md 8.5: two pilots needed substantive "
                         "correction). 'minimax' runs MiniMax-M3 with thinking ON, "
                         "which blind judging measured as the better writer here — "
                         "17/12 met the bar against Opus's 11 (PLAN.md 4).")
    ap.add_argument("--model", default=None,
                    help="override this backend's pinned model. Opus is refused on "
                         "this path regardless of backend.")
    ap.add_argument("--batch", type=int, default=1,
                    help="notes per model call. 1 is measured-optimal; 8 costs ~25%% "
                         "of quality. Raise only to re-measure.")
    ap.add_argument("--workers", type=int, default=8,
                    help="concurrent calls. Pure throughput, no quality effect — "
                         "the real ceiling is the provider's rate limit.")
    ap.add_argument("--shard", default=None, metavar="K/N",
                    help="process only shard K of N (0-indexed). Lets N independent "
                         "processes run with no coordination and no overlap.")
    ap.add_argument("--worklist", default=None,
                    help="JSON list of note filenames to process, e.g. "
                         "<vault>/.migration/opus_worklist.json from prescan.py. "
                         "Without it the runner walks all 64,144 merged notes, which "
                         "is 16x the work: the prescan finds 4,038 with a detectable "
                         "defect and re-running a clean note measurably damages it.")
    ap.add_argument("--apply", action="store_true", help="make the calls (default: dry run)")
    args = ap.parse_args()

    if not args.worklist:
        print("[rewrite] refusing to run without an explicit --worklist", file=sys.stderr)
        return 2

    model_name = args.model or BACKEND_MODELS[args.backend]
    if "opus" in model_name.lower():
        print(f"[rewrite] refusing Opus on this path: {model_name}", file=sys.stderr)
        return 2

    vault = Path(args.vault)
    engrams = vault / "Engrams"
    archive = vault / ARCHIVE_SUBDIR
    outdir = Path(args.out) if args.out else vault / ".migration" / "rewrite"
    for p in (engrams, archive):
        if not p.is_dir():
            print(f"[rewrite] missing {p}", file=sys.stderr)
            return 2
    outdir.mkdir(parents=True, exist_ok=True)
    system = Path(args.prompt).read_text(encoding="utf-8")

    shard_k = shard_n = None
    if args.shard:
        try:
            shard_k, shard_n = (int(x) for x in args.shard.split("/"))
            assert 0 <= shard_k < shard_n
        except Exception:
            print("[rewrite] --shard must look like 3/8 with 0 <= K < N", file=sys.stderr)
            return 2

    worklist: set[str] | None = None
    if args.worklist:
        wl = json.loads(Path(args.worklist).read_text())
        if (not isinstance(wl, list)
                or any(not isinstance(item, str) or not item for item in wl)):
            print("[rewrite] worklist must be a JSON list of filenames", file=sys.stderr)
            return 2
        names = [Path(item).name for item in wl]
        if len(set(names)) != len(names):
            print("[rewrite] worklist contains duplicate filenames", file=sys.stderr)
            return 2
        worklist = set(names)
        print(f"[rewrite] worklist: {len(worklist):,} notes from {args.worklist}")
        expected_outputs = {
            Path(name).with_suffix(".json").name for name in worklist
        }
        extras = sorted(
            path.name for path in outdir.glob("*.json")
            if path.name not in expected_outputs
        )
        if extras:
            print(f"[rewrite] refusing output outside worklist: {extras[0]} "
                  f"({len(extras):,} total)", file=sys.stderr)
            return 2

    print("[rewrite] indexing archived source notes...", flush=True)
    arch: dict[str, str] = {}
    for p in archive.glob("*.md"):
        arch[p.name] = body_of(p.read_text(encoding="utf-8", errors="replace"))
    print(f"[rewrite]   {len(arch):,} originals")

    units: list[dict] = []
    skipped_no_src = 0
    valid_existing = 0
    invalid_existing = 0
    accounted: set[str] = set()
    missing_source_refs: list[tuple[str, str]] = []
    for p in sorted(engrams.glob("*.md")):
        if worklist is not None and p.name not in worklist:
            continue
        if shard_n is not None and shard_of(p.name, shard_n) != shard_k:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if "migration: permanent-note" not in text:
            continue
        dest = outdir / (p.stem + ".json")
        absorbed = absorbed_of(text)
        missing = [name for name in absorbed if name not in arch]
        if missing:
            missing_source_refs.extend((p.name, name) for name in missing)
            continue
        srcs = [{"file": fn, "full_text": arch[fn]} for fn in absorbed if fn in arch]
        if not srcs:
            skipped_no_src += 1
            continue
        accounted.add(p.name)
        source_files = [item["file"] for item in srcs]
        existing_error = None
        if dest.exists():
            existing_error = output_file_error(
                dest, note_id=p.stem, expected_sources=source_files,
            )
            if existing_error is None:
                valid_existing += 1
                continue
            invalid_existing += 1
        units.append({"note_id": p.stem, "dest": dest,
                      "current_note": body_of(text), "originals": srcs,
                      "existing_error": existing_error})
    if missing_source_refs:
        note, source = missing_source_refs[0]
        print(f"[rewrite] refusing partial-source rewrite: {note} references "
              f"missing archive source {source} "
              f"({len(missing_source_refs):,} missing references total)",
              file=sys.stderr)
        return 2
    if worklist is not None:
        expected_worklist = {
            name for name in worklist
            if shard_n is None or shard_of(name, shard_n) == shard_k
        }
        unaccounted = sorted(expected_worklist - accounted)
        if unaccounted:
            print(f"[rewrite] worklist note was not eligible or had no sources: "
                  f"{unaccounted[0]} ({len(unaccounted):,} total)", file=sys.stderr)
            return 2
    batches = [units[i:i + args.batch] for i in range(0, len(units), args.batch)]
    src_chars = sum(len(o["full_text"]) for u in units for o in u["originals"])
    print(f"[rewrite] worklist={'yes' if worklist else 'NO — all notes'}  "
          f"shard={args.shard or 'all'}  todo={len(units):,}  "
          f"already valid={valid_existing:,}  invalid={invalid_existing:,}  "
          f"no-sources={skipped_no_src:,}")
    print(f"[rewrite] batch={args.batch} workers={args.workers} "
          f"backend={args.backend} model={model_name}")
    print(f"[rewrite] source text {src_chars/1e6:.1f}M chars (~{src_chars//4:,} tok) "
          f"+ {len(system)//4:,} tok system per call (cacheable)")
    if not units:
        print("[rewrite] nothing to do")
        return 0
    if not args.apply:
        print("\n[rewrite] DRY RUN. Sample payload (truncated):\n")
        print(build_user(batches[0])[:1200])
        print(f"\n[rewrite] re-run with --apply to make {len(batches):,} calls")
        return 0

    if args.backend == "minimax":
        from orchestrator.historical.cleanup_backends import MiniMaxClient
        # No generation-time schema on this transport: the reply is free-form
        # JSON recovered by parse_reply, and every record still has to clear
        # record_error before it can become a note. max_tokens is floored at
        # 32768 inside the client — M3's <think> block alone ran past 8192.
        client = MiniMaxClient(model=model_name)
    else:
        from orchestrator.historical.cleanup_backends import CodexCLIClient
        client = CodexCLIClient(
            model=model_name, output_schema=REWRITE_RESPONSE_SCHEMA,
        )
    agg = {"ok": 0, "failed": 0, "notes": 0, "split": 0, "archive": 0,
           "id_mismatch": 0, "in": 0, "out": 0, "cost": 0.0}
    start = time.monotonic()

    def run(batch: list[dict]) -> None:
        res = client.call(system=system, user=build_user(batch),
                          model=model_name, max_tokens=8192 * len(batch),   # headroom: a KEEP+SPLIT reply carries two notes
                          temperature=0.0)
        with _lock:
            agg["in"] += getattr(res, "input_tokens", 0) or 0
            agg["out"] += getattr(res, "output_tokens", 0) or 0
            agg["cost"] += getattr(res, "cost_usd", 0.0) or 0.0
        if getattr(res, "error", ""):
            with _lock:
                agg["failed"] += 1
            return
        parsed = parse_reply(res.text)
        recs = (parsed or {}).get("notes") if isinstance(parsed, dict) else parsed
        if not isinstance(recs, list) or not recs:
            # Write the raw reply next to the output so the failure can be read
            # rather than theorised about. Three rounds of guessing at these cost
            # more than the disk ever will.
            faildir = outdir.parent / "rewrite_failures"
            faildir.mkdir(parents=True, exist_ok=True)
            (faildir / (batch[0]["note_id"] + ".txt")).write_text(
                (res.text or "<EMPTY REPLY>"), encoding="utf-8")
            with _lock:
                agg["failed"] += 1
            print(f"[rewrite] unusable reply for {batch[0]['note_id'][:48]} "
                  f"({len(res.text or '')} chars, saved)", file=sys.stderr)
            return
        by_id = {u["note_id"]: u for u in batch}
        prepared: list[tuple[dict, dict]] = []
        seen: set[str] = set()
        for rec in recs:
            rec_id = rec.get("note_id") if isinstance(rec, dict) else None
            u = by_id.get(rec_id)
            if not u or rec_id in seen:
                with _lock:
                    agg["id_mismatch"] += 1
                    agg["failed"] += 1
                print(f"[rewrite] response id mismatch or duplicate: {rec_id!r}",
                      file=sys.stderr)
                return
            error = record_error(rec, expected_note_id=u["note_id"])
            if error:
                faildir = outdir.parent / "rewrite_failures"
                faildir.mkdir(parents=True, exist_ok=True)
                (faildir / (u["note_id"] + ".txt")).write_text(
                    (res.text or "<EMPTY REPLY>"), encoding="utf-8")
                with _lock:
                    agg["failed"] += 1
                print(f"[rewrite] invalid record for {u['note_id'][:48]}: {error} "
                      "(raw reply saved)", file=sys.stderr)
                return
            saved = dict(rec)
            saved["source_files"] = [o["file"] for o in u["originals"]]
            error = record_error(
                saved, expected_note_id=u["note_id"],
                expected_sources=saved["source_files"],
            )
            if error:
                with _lock:
                    agg["failed"] += 1
                print(f"[rewrite] refused unsafe saved record: {error}", file=sys.stderr)
                return
            seen.add(rec_id)
            prepared.append((saved, u))
        if seen != set(by_id):
            with _lock:
                agg["id_mismatch"] += len(set(by_id) - seen)
                agg["failed"] += 1
            print("[rewrite] response omitted one or more requested note ids", file=sys.stderr)
            return
        for rec, u in prepared:
            if u["dest"].exists():
                raw = u["dest"].read_bytes()
                digest = hashlib.sha256(raw).hexdigest()[:12]
                faildir = outdir.parent / "rewrite_failures"
                faildir.mkdir(parents=True, exist_ok=True)
                backup = faildir / f"{u['note_id']}.invalid-{digest}.json"
                if not backup.exists():
                    backup.write_bytes(raw)
            tmp = u["dest"].with_suffix(".tmp")
            tmp.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
            tmp.replace(u["dest"])
            with _lock:
                agg["notes"] += 1
                if rec.get("verdict") == "SPLIT":
                    agg["split"] += 1
                elif rec.get("verdict") == "ARCHIVE":
                    agg["archive"] += 1
        with _lock:
            agg["ok"] += 1

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = [pool.submit(run, b) for b in batches]
            done = 0
            for f in as_completed(futs):
                try:
                    f.result()
                except Exception as e:
                    with _lock:
                        agg["failed"] += 1
                    print(f"[rewrite] worker error: {type(e).__name__}: {e}", file=sys.stderr)
                done += 1
                if done % 25 == 0 or done == len(batches):
                    el = time.monotonic() - start
                    rate = done / max(0.1, el)
                    eta = (len(batches) - done) / max(1e-6, rate) / 3600
                    per = (agg["in"] + agg["out"]) / max(1, agg["notes"])
                    print(f"[rewrite] {done:,}/{len(batches):,}  notes={agg['notes']:,}  "
                          f"{el/60:.0f}m  ETA {eta:.1f}h  {per:.0f} tok/note  "
                          f"${agg['cost']:.2f}  fail={agg['failed']}", flush=True)
    finally:
        # Not every transport holds resources: CodexCLIClient manages a temp
        # CODEX_HOME and must be closed, MiniMaxClient is stateless urllib.
        close = getattr(client, "close", None)
        if callable(close):
            close()

    el = time.monotonic() - start
    print(f"\n[rewrite] done in {el/3600:.2f}h — {agg['ok']:,} calls ok, "
          f"{agg['failed']:,} failed, {agg['notes']:,} notes written")
    print(f"[rewrite]   SPLIT={agg['split']:,}  ARCHIVE={agg['archive']:,}"
          f"  id_mismatch={agg['id_mismatch']:,}")
    print(f"[rewrite]   estimated tokens in={agg['in']:,} out={agg['out']:,} "
          f"({(agg['in']+agg['out'])/max(1,agg['notes']):.0f}/note)  cost=${agg['cost']:.2f}")
    print("[rewrite] re-run the same command to retry failures and continue")
    return 1 if agg["failed"] or agg["id_mismatch"] else 0


if __name__ == "__main__":
    sys.exit(main())
