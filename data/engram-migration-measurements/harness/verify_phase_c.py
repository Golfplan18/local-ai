"""Verify the Phase C run touched only the 11,744 notes it was given.

Strict edge counting: an edge is a line beginning `- type: ` at column 0 inside
the frontmatter relationships block. An earlier loose version counted any
stripped line starting `- `, which also caught folded `>-` continuation lines
whose text happens to begin with a hyphen — e.g.

    target: >-
      ... treats executive function
      - executive function as its own variable.

That over-counted by exactly 87 edges and produced the phantom gap against the
recorded baseline of 604,099. Do not reintroduce it.

Usage:  python3 verify_phase_c.py
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import subprocess

ENGRAMS = pathlib.Path(os.path.expanduser("~/engram-work/Engrams"))
WORKTREE = pathlib.Path(os.path.expanduser("~/engram-work"))
PATHS_FILE = pathlib.Path(
    os.path.expanduser("~/engram-work/.migration/phase_c_paths.txt")
)
BASELINE_NOTES = 64_090
BASELINE_EDGES = 604_099

FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
BLOCK_RE = re.compile(r"\nrelationships:\s*\n((?:[ \t]+.*\n|[ \t]*-.*\n)+)")


def scan() -> tuple[int, int, str]:
    """(notes_with_edges, total_edges, fingerprint) over the whole corpus."""
    per_note: list[tuple[str, int]] = []
    total = 0
    for f in sorted(ENGRAMS.glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        m = FM_RE.match(text)
        if not m:
            continue
        block = BLOCK_RE.search("\n" + m.group(1) + "\n")
        if not block:
            continue
        n = sum(1 for ln in block.group(1).splitlines()
                if ln.startswith("- type: "))
        if n:
            per_note.append((f.stem, n))
            total += n
    h = hashlib.sha256()
    for name, n in sorted(per_note):
        h.update(f"{name}:{n}\n".encode())
    return len(per_note), total, h.hexdigest()


def main() -> int:
    targets = {ln.strip() for ln in PATHS_FILE.read_text().splitlines() if ln.strip()}
    changed = subprocess.run(
        ["git", "-C", str(WORKTREE), "diff", "--name-only", "--", "Engrams"],
        capture_output=True, text=True, check=True,
    ).stdout.split("\n")
    changed_abs = {str(WORKTREE / c) for c in changed if c.strip()}

    outside = changed_abs - targets
    notes, edges, fp = scan()

    print(f"notes changed on disk : {len(changed_abs):,}")
    print(f"  of which off-list   : {len(outside):,}   <- must be 0")
    for p in sorted(outside)[:10]:
        print(f"      OFF-LIST: {p}")
    print()
    print(f"notes with edges now  : {notes:,}   (baseline {BASELINE_NOTES:,})")
    print(f"edges now             : {edges:,}   (baseline {BASELINE_EDGES:,})")
    print(f"  net new notes       : {notes - BASELINE_NOTES:,}")
    print(f"  net new edges       : {edges - BASELINE_EDGES:,}")
    print(f"fingerprint (strict)  : {fp}")
    print()
    ok = not outside and notes >= BASELINE_NOTES and edges >= BASELINE_EDGES
    print("PASS — no pre-existing note lost edges, nothing off-list touched"
          if ok else "FAIL — investigate before committing")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
