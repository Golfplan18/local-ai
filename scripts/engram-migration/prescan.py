#!/usr/bin/env python3
"""Prescan: find which merged notes need rewriting, using NO model calls.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

WHY THIS EXISTS
---------------
The obvious plan is "rewrite the notes that need it", and I had assumed finding
them required a model pass costing about a third of a rewrite each -- which at the
audit's 52% failure rate saves only ~11% over rewriting everything, and is
therefore barely worth doing.

That was wrong. The failures the 48-note audit measured have mechanical
signatures, so the triage is free and only the repair costs anything:

  D1 KEYWORD-DUMP INSTANCE LINE (13.5% of the corpus). The evidence line was
     assembled from Stage 3's extracted fragments. Signature: four or more
     comma-separated segments most of which are bare noun phrases with no verb,
     or the same term twice in different case, or an orphan token like "A+" or a
     bare number-word. Real example: "Concept and Positioning, Audience Analysis,
     Concept and positioning, Title options, ... A+, Goodreads/Amazon, Publisher
     Rocket, AI, four, and mandatory inputs structure book marketing generation."

  D2 IMPORTED TERM OF ART (15% asserted something false, mostly this). The
     rewrite introduced a named concept the sources never used -- "the framing
     effect", "photographic memory", "identity-protective cognition" -- each
     naming a different mechanism than the note's own content. Detection: the
     title contains a known term of art, and that term appears nowhere in any of
     the note's source texts. Purely a string search, and the source is the
     ground truth.

  D3 DROPPED QUALIFYING CLAUSE (the dominant failure, 56% lost a claim). A source
     asserts something DESPITE / EVEN WHEN / ONLY IF / WITHOUT / RATHER THAN some
     condition, and that condition is the whole force of the claim. Detection:
     find those clauses in the sources, take their content words, and check
     whether any survived into the merged note. "Despite the dual mandate of price
     stability and full employment" leaves a trace -- mandate, stability,
     employment -- and its absence is measurable.

  D4 TAUTOLOGY. The first mechanism bullet restates the title, which is what
     happens when the qualifying clause is gone and only the circular core is
     left. Detection: high content-word overlap between title and first bullet.

D3 is a recall-oriented test: it flags notes where a qualifier plausibly went
missing, and some flags will be paraphrases that kept the meaning in different
words. It is deliberately tuned that way -- a false flag costs one rewrite, while
a miss leaves a de-fanged note in the corpus forever.

Writes prescan.json listing every flagged note with its reasons, which is the
worklist for rewrite_run.py.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

ARCHIVE_SUBDIR = "Archive/Engram Absorbed Sources 2026-08"

_ABSORBED = re.compile(r"^absorbed_from:\s*\n((?:[ \t]*-[ \t]+\S.*\n)+)", re.M)
_H1 = re.compile(r"^#\s+(.+)$", re.M)
_VERB = re.compile(r"\b(is|are|was|were|be|been|has|have|had|does|do|did|can|may|must|"
                   r"should|would|will|shall|\w+s|\w+ed|\w+ing)\b")

# Clause openers whose content is load-bearing. Each captures to the end of the
# clause so the condition's own words can be recovered.
# STRONG markers only. "rather than" / "instead of" were dropped: they are
# ordinary contrastive phrasing that a faithful paraphrase routinely rewords, so
# they produced false positives at scale ("rather than accurate assessment" was
# flagged as lost on a note whose bullets stated exactly that in other words).
# The clauses the audit found actually being DROPPED were concessive and
# exclusive ones -- "despite the dual mandate", "without any elected official
# casting a vote" -- where the condition is the force of the claim.
_QUAL = re.compile(
    r"\b(despite|even when|even if|even though|only if|only when|only for|"
    r"without any|without ever|regardless of|in spite of|unless)\b"
    r"([^.;\n]{8,140})", re.I)

# Named concepts a note may claim. Presence in a title with absence from every
# source is the false-label signature.
_TERMS = [
    "framing effect", "photographic memory", "identity-protective cognition",
    "confirmation bias", "moral hazard", "regulatory capture", "cognitive dissonance",
    "sunk cost", "survivorship bias", "dunning-kruger", "anchoring bias",
    "loss aversion", "prisoner's dilemma", "tragedy of the commons", "moral licensing",
    "fundamental attribution error", "just-world", "halo effect", "availability heuristic",
    "goodhart", "campbell's law", "conway's law", "parkinson's law", "gresham's law",
    "principal-agent", "adverse selection", "information asymmetry", "network effect",
    "path dependence", "regression to the mean", "base rate", "selection effect",
    "operant conditioning", "classical conditioning", "learned helplessness",
    "cognitive load", "flow state", "deliberate practice", "growth mindset",
    "objective correlative", "routinization of charisma", "techniques of neutralization",
    "reciprocal determinism", "choice architecture", "diffusion of responsibility",
    "bystander effect", "groupthink", "overton window", "motte and bailey",
    "equivocation", "argumentation scheme", "ambiguous loss", "parentification",
    "divide and rule", "regulatory arbitrage", "major questions doctrine",
    "consciousness raising", "malicious envy", "benign envy", "costly signaling",
    "salience bias", "status quo bias", "endowment effect", "hedonic treadmill",
]

STOP = set("""a an the and or but if of to in on at by for with from as is are was were be
been being this that these those it its they their there he she his her him them not no nor
so than then when where which who whom whose what how why can could may might will would
shall should must do does did done have has had having more most less least very much many
few some any all both each other another same into onto over under about above below between
through during before after while because you your i me my we us our own such per via up
down out off again further once here only also just even still yet""".split())


def content_words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z\-']{2,}", (s or "").lower()) if w not in STOP}


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


def instance_line(body: str) -> str | None:
    for ln in body.splitlines():
        t = ln.strip().lstrip("-").strip()
        if t.lower().startswith("instance:"):
            return t[len("instance:"):].strip()
    return None


def mechanism_bullets(body: str) -> list[str]:
    """Mechanism lines only. The `# title` heading must be excluded: counting it
    made D4 compare the title against itself and flag 100% of the corpus."""
    out = []
    for ln in body.splitlines():
        raw = ln.strip()
        if raw.startswith("#"):
            continue
        t = raw.lstrip("-").strip()
        if t and not t.lower().startswith(("instance:", "case:")):
            out.append(t)
    return out


def d1_keyword_dump(inst: str | None) -> bool:
    if not inst or "none recorded in source" in inst.lower():
        return False
    segs = [x.strip() for x in inst.split(",") if x.strip()]
    if len(segs) < 4:
        return False
    bare = sum(1 for x in segs if len(x.split()) <= 4 and not _VERB.search(x.lower()))
    dupcase = len({x.lower() for x in segs}) != len(segs)
    orphan = any(re.fullmatch(r"(one|two|three|four|five|six|seven|eight|nine|ten|\w{1,2}\+?)",
                              x, re.I) for x in segs)
    return bare >= max(3, int(0.6 * len(segs))) or dupcase or orphan


def d2_imported_term(title: str, source_blob: str) -> list[str]:
    tl = title.lower()
    sl = source_blob.lower()
    return [t for t in _TERMS if t in tl and t not in sl]


def d3_dropped_qualifier(source_blob: str, note_text: str) -> list[str]:
    """Qualifying clauses in the sources whose content left no trace in the note."""
    note_w = content_words(note_text)
    lost = []
    for m in _QUAL.finditer(source_blob):
        clause = (m.group(1) + m.group(2)).strip()
        cw = content_words(m.group(2))
        if len(cw) < 3:          # two-word conditions are usually phrasing, not force
            continue
        # Survived if a third or more of the clause's content words appear in the
        # note. A paraphrase normally carries several of them; a dropped clause
        # carries almost none.
        if len(cw & note_w) / len(cw) < 0.25:
            lost.append(" ".join(clause.split())[:120])
    return lost


def d4_tautology(title: str, bullets: list[str]) -> bool:
    if not bullets:
        return False
    tw = content_words(title)
    if len(tw) < 4:
        return False
    bw = content_words(bullets[0])
    if not bw:
        return False
    return len(tw & bw) / len(tw) >= 0.7


# ---------------------------------------------------------------------------
# HISTORICAL MODE (--historical)
#
# The D1-D4 checks above measure MIGRATION damage: they compare a merged note
# against the archived originals it absorbed. Engrams/Historical Atomics/ never
# went through the migration -- 14,049 notes extracted July 2026, no
# absorbed_from, no archived sources, and its own source conversations are 85%
# missing from disk. So there is nothing to diff against.
#
# What it CAN be scanned for is the defect that motivated this whole project: the
# extraction prompt in force at the time required naming the actor in every
# bullet, so notes came out welded to whatever example happened to arise. On a
# 45-note sample of the original corpus ~60% could not be applied outside their
# source domain. That is detectable from the note alone.
# ---------------------------------------------------------------------------

_YEAR = re.compile(r"\b(19|20)\d\d\b")
_HEDGE = re.compile(r"\b(can|may|might|often|typically|sometimes|tends? to|generally|usually)\b", re.I)
_ABS = re.compile(r"\b(never|always|cannot|proves|all|every)\b", re.I)
_MECH = re.compile(r"\b(because|when|by \w+ing|through \w+ing|so that|which \w+s|"
                   r"causes?|produces?|creates?|leads? to|forces?|turns? .* into|"
                   r"prevents?|enables?|requires?)\b", re.I)
_PERISH = re.compile(r"\b(Trump|Biden|Harris|Paxton|Cornyn|Hegseth|Senate|House|midterm|runoff|"
                     r"polling|primary|tariff|indictment|pardon|impeach|election|Fed|CHIPS Act|"
                     r"Supreme Court|Congress)\b")
_BENIGN_CAPS = set("""The A An In On At By For With When Where What How Why This That These Those It Its
They Their There If As But And Or So Not No One Two Three Four Five Each Every Both Any All Some Most
Many Few Such Once Only Even Still Yet Using Placing Treating Framing Naming Making Because""".split())


def title_proper_nouns(title: str, whole_note: str) -> set[str]:
    """Mid-sentence capitalised tokens in the title that never appear lowercase
    anywhere in the note. Sentence-initial capitals are excluded -- an earlier
    checker counted them and reported a phantom 92% failure rate."""
    lower = {w.lower() for w in re.findall(r"\b[a-z][a-z\-']{2,}\b", whole_note)}
    out = set()
    for tok in re.findall(r"\S+", title)[1:]:
        m = re.match(r"([A-Z][a-zA-Z][a-zA-Z\-'\.]{1,})", tok)
        if m:
            w = m.group(1).rstrip(".")
            if w not in _BENIGN_CAPS and w.lower() not in lower:
                out.add(w)
    return out


def scan_historical(note_text: str) -> tuple[list[str], dict]:
    body = body_of(note_text)
    m = _H1.search(body)
    title = m.group(1).strip() if m else ""
    bullets = mechanism_bullets(body)
    reasons: list[str] = []
    detail: dict = {}

    pn = title_proper_nouns(title, note_text)
    if pn:
        reasons.append("P1_instance_locked")
        detail["proper_nouns"] = sorted(pn)[:6]
    if _YEAR.search(title):
        reasons.append("P2_dated_title")
    if _PERISH.search(title):
        reasons.append("P3_perishable_subject")
    if _HEDGE.search(title):
        reasons.append("P4_hedged_title")
    if _ABS.search(title):
        reasons.append("P5_absolute_title")
    if title and not _MECH.search(title):
        reasons.append("P6_no_mechanism")   # states a fact, not how something works
    if d4_tautology(title, bullets):
        reasons.append("P7_tautology")
    if not bullets:
        reasons.append("P8_no_bullets")
    return reasons, detail


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", default=str(Path.home() / "engram-work"))
    ap.add_argument("--out", default=None, help="default <vault>/.migration/prescan.json")
    ap.add_argument("--examples", type=int, default=0, help="print N examples per defect")
    ap.add_argument("--historical", action="store_true",
                    help="scan Engrams/Historical Atomics/ for PRE-migration defects "
                         "(instance-locked titles, dated or perishable subjects, "
                         "fact-not-mechanism) instead of migration damage. Those notes "
                         "have no archived sources to diff against, so D1-D4 cannot run.")
    args = ap.parse_args()

    vault = Path(args.vault)
    engrams = vault / "Engrams"
    archive = vault / ARCHIVE_SUBDIR
    out = Path(args.out) if args.out else vault / ".migration" / "prescan.json"

    if args.historical:
        return _run_historical(engrams / "Historical Atomics", out, args.examples)

    print("[prescan] indexing archived sources...", flush=True)
    arch = {p.name: body_of(p.read_text(encoding="utf-8", errors="replace"))
            for p in archive.glob("*.md")}
    print(f"[prescan]   {len(arch):,} originals")

    stats = collections.Counter()
    flagged: list[dict] = []
    examples: dict[str, list] = collections.defaultdict(list)
    total = 0

    for p in sorted(engrams.glob("*.md")):
        text = p.read_text(encoding="utf-8", errors="replace")
        if "migration: permanent-note" not in text:
            continue
        total += 1
        body = body_of(text)
        m = _H1.search(body)
        title = m.group(1).strip() if m else ""
        srcs = absorbed_of(text)
        blob = " ".join(arch.get(fn, "") for fn in srcs)
        bullets = mechanism_bullets(body)
        inst = instance_line(body)

        reasons: list[str] = []
        detail: dict = {}
        if d1_keyword_dump(inst):
            reasons.append("D1_keyword_dump")
        terms = d2_imported_term(title, blob) if blob else []
        if terms:
            reasons.append("D2_imported_term")
            detail["terms"] = terms
        lost = d3_dropped_qualifier(blob, body) if blob else []
        if lost:
            reasons.append("D3_dropped_qualifier")
            detail["lost_clauses"] = lost[:4]
        if d4_tautology(title, bullets):
            reasons.append("D4_tautology")

        for r in reasons:
            stats[r] += 1
            if args.examples and len(examples[r]) < args.examples:
                examples[r].append((p.name, title, detail))
        if reasons:
            stats["ANY"] += 1
            stats[f"n_reasons_{len(reasons)}"] += 1
            flagged.append({"note": p.name, "title": title, "n_sources": len(srcs),
                            "reasons": reasons, **detail})
        else:
            stats["CLEAN"] += 1

    print(f"\n[prescan] merged notes scanned: {total:,}")
    print(f"[prescan]   CLEAN (no detectable defect): {stats['CLEAN']:,} "
          f"({stats['CLEAN']/max(1,total)*100:.1f}%)")
    print(f"[prescan]   FLAGGED for rewrite:         {stats['ANY']:,} "
          f"({stats['ANY']/max(1,total)*100:.1f}%)")
    for k in ("D1_keyword_dump", "D2_imported_term", "D3_dropped_qualifier", "D4_tautology"):
        print(f"[prescan]     {k:24s} {stats[k]:>7,}  ({stats[k]/max(1,total)*100:5.1f}%)")
    print(f"[prescan]   notes with 2+ defects: "
          f"{sum(v for k, v in stats.items() if k.startswith('n_reasons_') and k != 'n_reasons_1'):,}")

    for r, ex in examples.items():
        print(f"\n--- {r} examples ---")
        for name, title, detail in ex:
            print(f"  {name[:66]}")
            print(f"    title: {title[:110]}")
            for k, v in detail.items():
                print(f"    {k}: {str(v)[:200]}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(flagged, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n[prescan] worklist -> {out}  ({len(flagged):,} notes)")
    print(f"[prescan] cost of this scan: 0 tokens")
    return 0


def _run_historical(root: Path, out: Path, n_examples: int) -> int:
    if not root.is_dir():
        print(f"[prescan] missing {root}", file=sys.stderr)
        return 2
    stats = collections.Counter()
    flagged: list[dict] = []
    examples: dict[str, list] = collections.defaultdict(list)
    total = 0
    for p in sorted(root.rglob("*.md")):
        text = p.read_text(encoding="utf-8", errors="replace")
        total += 1
        reasons, detail = scan_historical(text)
        m = _H1.search(body_of(text))
        title = m.group(1).strip() if m else ""
        for r in reasons:
            stats[r] += 1
            if n_examples and len(examples[r]) < n_examples:
                examples[r].append((title, detail))
        if reasons:
            stats["ANY"] += 1
            flagged.append({"note": str(p.relative_to(root)), "title": title,
                            "reasons": reasons, **detail})
        else:
            stats["CLEAN"] += 1

    print(f"[prescan] Historical Atomics scanned: {total:,}")
    print(f"[prescan]   CLEAN (no detectable defect): {stats['CLEAN']:,} "
          f"({stats['CLEAN']/max(1,total)*100:.1f}%)")
    print(f"[prescan]   FLAGGED:                     {stats['ANY']:,} "
          f"({stats['ANY']/max(1,total)*100:.1f}%)")
    for k in ("P1_instance_locked", "P2_dated_title", "P3_perishable_subject",
              "P4_hedged_title", "P5_absolute_title", "P6_no_mechanism",
              "P7_tautology", "P8_no_bullets"):
        if stats[k]:
            print(f"[prescan]     {k:24s} {stats[k]:>7,}  ({stats[k]/max(1,total)*100:5.1f}%)")
    for r, ex in examples.items():
        print(f"\n--- {r} ---")
        for title, detail in ex:
            print(f"  {title[:112]}")
            if detail:
                print(f"    {detail}")
    out = out.with_name("prescan-historical.json")
    out.write_text(json.dumps(flagged, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n[prescan] worklist -> {out}  ({len(flagged):,} notes)   0 tokens")
    return 0


if __name__ == "__main__":
    sys.exit(main())
