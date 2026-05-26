#!/usr/bin/env python3
"""
refresh-mode-pages.py — Phase 2 autonomous Ora pipeline refresh

Walks the 80-entry Trigger Prompt Corpus (58 modes + 22 visuals), submits each
mode's prime prompt to Ora's local /chat endpoint with the mode pre-selected,
polls the resulting conversation.json for the assistant output, and patches the
matching vault Paper file by replacing the placeholder line with the real
output. Logs progress, writes a state file for --resume, commits + pushes to
the vault every 5 entries.

Designed to be safe to interrupt and resume. Per-mode try/except — a single
failure logs and continues to the next.

Usage:
    python3 ~/ora/scripts/refresh-mode-pages.py
    python3 ~/ora/scripts/refresh-mode-pages.py --resume
    python3 ~/ora/scripts/refresh-mode-pages.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# ─── Paths ────────────────────────────────────────────────────────────────────
VAULT = Path.home() / "Documents" / "vault"
CORPUS_PATH = VAULT / "Trigger Prompt Corpus — Canonical 2026-05-15.md"
RECMAP_PATH = VAULT / "Working — Mode Site Reconciliation Map 2026-05-15.md"
PORT_FILE = Path("/tmp/ora-port.txt")
LOG_PATH = Path.home() / "Documents" / "conversations" / "refresh-mode-pages-log-2026-05-15.txt"
STATE_PATH = Path.home() / "Documents" / "conversations" / "refresh-mode-pages-state.json"

# Canonical conversation output directory. Ora writes the final conversation
# as ~/Documents/conversations/YYYY-MM-DD_HH-MM_<slug>.md with the panel_id
# embedded inside the Context block: `panel '<panel_id>'`. The filename is
# content-derived, so we can't construct it directly — we glob the directory
# and find by content + mtime instead. (The earlier ~/ora/sessions/<panel_id>/
# and ~/Documents/conversations/<panel_id>/ paths used by the script were
# wrong — Ora's conversation persistence uses content-derived filenames at
# the top level of conversations/, not a per-panel subdir.)
CANONICAL_CONV_DIR = Path.home() / "Documents" / "conversations"

PLACEHOLDER_LINE = (
    "*[Ora response to this prompt will be populated by the autonomous "
    "comparison-refresh run — placeholder until the Ora pipeline output lands.]*"
)

POLL_INTERVAL_SEC = 15
TIMEOUT_SEC = 30 * 60  # 30 minutes per prompt
COMMIT_EVERY = 5

# ─── Logging ──────────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    """Print to stdout and append to the log file."""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # logging is best-effort; never blocks the run


# ─── Corpus + reconciliation-map parsing ──────────────────────────────────────
def parse_corpus(path: Path) -> list[dict]:
    """
    Parse the Trigger Prompt Corpus and return a list of entries.

    Each entry: {
        "kind": "mode" | "visual",
        "slug": str,
        "prime_prompt": str,
    }

    Mode entries use h4 headings: #### `<slug>`
    Visual entries use h3 headings: ### `<slug>` (and live under the
    "## Visual tools" section, after the 21 mode-territory groups).

    The prime prompt is the first numbered list item beneath the
    "**Prime prompt..." subhead in each entry.
    """
    text = path.read_text(encoding="utf-8")

    # Split into chunks at each h3/h4 heading.
    # We process linearly so we can track which section (modes vs visuals)
    # we're in.
    entries: list[dict] = []
    in_visuals = False
    current: Optional[dict] = None
    capturing_prime = False
    prime_buf: list[str] = []

    def flush_current():
        nonlocal current, capturing_prime, prime_buf
        if current is not None:
            # Final the prime prompt — take the first numbered list line.
            prime = ""
            for line in prime_buf:
                m = re.match(r"^\s*1\.\s+(.+)$", line.strip())
                if m:
                    prime = m.group(1).strip()
                    break
            current["prime_prompt"] = prime
            if current.get("slug"):
                entries.append(current)
        current = None
        capturing_prime = False
        prime_buf = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        # Section boundary: the "## Visual tools" heading flips the mode flag.
        if line.startswith("## Visual tools"):
            in_visuals = True
            flush_current()
            continue

        # h4 heading: `#### `slug`` → mode entry. h3 heading inside the
        # visuals section: `### `slug`` → visual entry. Use a strict regex
        # against backticked slugs to avoid false positives from territory
        # headings like `### T1-argumentative-artifact-examination` which
        # do NOT have backticks.
        if line.startswith("#### "):
            flush_current()
            m = re.match(r"^####\s+`([^`]+)`\s*$", line)
            if m:
                current = {"kind": "mode", "slug": m.group(1).strip()}
            continue
        if in_visuals and line.startswith("### "):
            flush_current()
            m = re.match(r"^###\s+`([^`]+)`\s*$", line)
            if m:
                current = {"kind": "visual", "slug": m.group(1).strip()}
            continue

        if current is None:
            continue

        # Within a current entry: detect the "Prime prompt" label, then
        # capture lines until we reach the next heading or "Other examples".
        if "**Prime prompt" in line:
            capturing_prime = True
            continue
        if line.startswith("**Other examples"):
            capturing_prime = False
            continue
        if capturing_prime:
            prime_buf.append(line)

    flush_current()
    return entries


def parse_reconciliation_map(path: Path) -> dict[str, dict]:
    """
    Parse the reconciliation map and return a slug → row dict.

    Each row carries the columns of the mode reconciliation table:
        territory, paper_path, stub, action

    Used to:
      - skip `simple` (OUT-OF-SCOPE)
      - resolve the Paper file path per mode
    """
    text = path.read_text(encoding="utf-8")
    rows: dict[str, dict] = {}

    # Mode reconciliation table rows look like:
    # | mode-slug | T<n>-... | /path/to/Paper — ....md | stub | ACTION |
    table_row_re = re.compile(
        r"^\|\s*([a-z][a-z0-9-]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([A-Z-]+)\s*\|\s*$"
    )
    for raw_line in text.splitlines():
        m = table_row_re.match(raw_line)
        if not m:
            continue
        slug, territory, paper_col, stub, action = (
            m.group(1).strip(),
            m.group(2).strip(),
            m.group(3).strip(),
            m.group(4).strip(),
            m.group(5).strip(),
        )
        # Skip the header divider row (where slug is "Mode slug" — but it
        # won't match the slug pattern anyway since it has a space).
        if slug.startswith("Mode") or slug.startswith("Visual"):
            continue
        # If the paper column says MISSING we have no path yet; we'll
        # derive the path conventionally as Paper — <Title Case Slug>.md
        # in the same directory.
        rows[slug] = {
            "territory": territory,
            "paper_path_in_map": paper_col,
            "stub": stub,
            "action": action,
        }
    return rows


def slug_to_title(slug: str) -> str:
    """
    Convert kebab-slug → Title Case for naming Paper files. The vault has
    canonical Paper files using Title Case with hyphens preserved between
    multi-word phrases (e.g. 'pre-mortem-fragility' → 'Pre-Mortem Fragility').
    """
    parts = slug.split("-")
    # Use Title Case for each part, preserving acronym-like all-caps if
    # given in source (rare; the corpus is all-lowercase kebab).
    return " ".join(p.capitalize() for p in parts)


def derive_paper_path(slug: str, kind: str) -> Path:
    """
    Resolve the vault Paper file path for a given slug.

    For modes: Paper — <Title Case>.md, with special-case overrides where
    this batch's drafting agents used custom filenames to avoid slug
    collisions (causal-dag → "Paper — Causal DAG Mode.md", terrain-mapping
    → "Paper — Terrain Mapping T14.md").

    For visuals: Paper — <Title Case>.md using the visual's canonical name.
    The Trigger Prompt Corpus uses underscored slugs (ach_matrix, bow_tie,
    etc.) but the vault filenames use hyphenated / human-readable forms.
    Provide a lookup table.
    """
    # Mode special-cases — slug collisions or hyphen/preposition variations
    # in vault Paper filenames.
    mode_overrides = {
        "causal-dag": "Paper — Causal DAG Mode.md",
        "terrain-mapping": "Paper — Terrain Mapping T14.md",
        "red-team-advocate": "Paper — Red-Team Advocate.md",
        "red-team-assessment": "Paper — Red-Team Assessment.md",
        "place-reading-genius-loci": "Paper — Place Reading and Genius Loci.md",
        "multi-criteria-decision": "Paper — Multi-Criteria Decision.md",
        "pre-mortem-action": "Paper — Pre-Mortem Action.md",
        "pre-mortem-fragility": "Paper — Pre-Mortem Fragility.md",
    }
    # Mode RENAME cases reuse the existing paired-execution paper.
    rename_overrides = {
        "argument-audit": "Paper — Argument Audit Analysis Framework.md",
        "bayesian-hypothesis-network": "Paper — Bayesian Hypothesis Network Analysis Framework.md",
        "decision-architecture": "Paper — Decision Architecture Analysis Framework.md",
        "decision-clarity": "Paper — Decision Clarity Analysis Framework.md",
        "domain-induction": "Paper — Domain Induction Analysis Framework.md",
        "wicked-future": "Paper — Wicked-Future Analysis Framework.md",
        "worldview-cartography": "Paper — Worldview Cartography Analysis Framework.md",
    }
    # Mode REUSE cases (singleton-territory modes whose framework page IS
    # the mode page).
    reuse_overrides = {
        "mechanism-understanding": "Paper — Mechanism Understanding Framework.md",
        "strategic-interaction": "Paper — Strategic Interaction Framework.md",
    }

    # Visual slug → canonical Paper filename. The vault has 22 visual papers
    # named with human-readable hyphenation; the corpus uses underscored
    # slugs.
    visual_filenames = {
        "ach_matrix":         "Paper — ACH Matrix.md",
        "bow_tie":            "Paper — Bow-Tie Diagram.md",
        "c4":                 "Paper — C4 Architecture.md",
        "causal_dag":         "Paper — Causal DAG.md",
        "causal_loop_diagram":"Paper — Causal Loop Diagram.md",
        "comparison":         "Paper — Comparison Chart.md",
        "concept_map":        "Paper — Concept Map.md",
        "decision_tree":      "Paper — Decision Tree.md",
        "distribution":       "Paper — Distribution Plot.md",
        "fishbone":           "Paper — Fishbone Diagram.md",
        "flowchart":          "Paper — Flowchart.md",
        "heatmap":            "Paper — Heatmap.md",
        "ibis":               "Paper — IBIS Argument.md",
        "influence_diagram":  "Paper — Influence Diagram.md",
        "pro_con":            "Paper — Pro-Con Tree.md",
        "quadrant_matrix":    "Paper — Quadrant Matrix.md",
        "scatter":            "Paper — Scatter Plot.md",
        "sequence":           "Paper — Sequence Diagram.md",
        "state":              "Paper — State Diagram.md",
        "stock_and_flow":     "Paper — Stock and Flow.md",
        "time_series":        "Paper — Time Series.md",
        "tornado":            "Paper — Tornado Chart.md",
    }

    if kind == "visual":
        fname = visual_filenames.get(slug, f"Paper — {slug_to_title(slug.replace('_','-'))}.md")
        return VAULT / fname

    # mode kind
    if slug in mode_overrides:
        return VAULT / mode_overrides[slug]
    if slug in rename_overrides:
        return VAULT / rename_overrides[slug]
    if slug in reuse_overrides:
        return VAULT / reuse_overrides[slug]
    return VAULT / f"Paper — {slug_to_title(slug)}.md"


# ─── State management ────────────────────────────────────────────────────────
def load_state() -> dict:
    """Read state file (or return fresh empty state)."""
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            log(f"[WARN] state file unreadable, starting fresh: {STATE_PATH}")
    return {"done": [], "failed": [], "skipped": []}


def save_state(state: dict) -> None:
    """Atomically replace state file."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


# ─── Ora chat submission + polling ───────────────────────────────────────────
def read_port() -> int:
    """Read Ora server port from /tmp/ora-port.txt. Fall back to 5000."""
    try:
        return int(PORT_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return 5000


def submit_chat(port: int, slug: str, prompt: str) -> tuple[str, float]:
    """
    POST the prompt to Ora's /chat with the mode pre-selected. Returns
    (panel_id, submit_time). The caller polls the canonical conversations
    directory for a file referencing this panel_id. The body matches the V3
    contract documented in server.py::chat().
    """
    import urllib.request

    panel_id = f"refresh-{slug}-{int(time.time())}"
    body = {
        "message": prompt,
        "history": [],
        "panel_id": panel_id,
        "is_main_feed": True,
        "tag": "",
        "manual_mode_selection": slug,
        "framework_selected": "",
        "attachments": [],
    }
    req = urllib.request.Request(
        f"http://localhost:{port}/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    submit_time = time.time()
    # /chat is a streaming SSE endpoint, but we only need to know the
    # submission landed. Open the connection briefly so the server records
    # the submission, then drop the reader — Ora is async-by-design; the
    # actual pipeline keeps running and writes the canonical conversation
    # markdown file when done.
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            # Drain a tiny amount so the server flushes the first event,
            # then close. We don't rely on this stream for the output.
            try:
                resp.read(1)
            except Exception:
                pass
    except Exception as exc:
        # Timeout-on-read is expected with SSE; we only care that the POST
        # was accepted, which it was if we got this far without a connection
        # error.
        msg = str(exc)
        if "timed out" not in msg.lower() and "incomplete" not in msg.lower():
            raise
    return panel_id, submit_time


def find_canonical_conversation(prompt: str, submit_time: float) -> Optional[Path]:
    """
    Find the canonical conversation .md file matching a submitted prompt.

    Ora writes conversations to ~/Documents/conversations/YYYY-MM-DD_HH-MM_<slug>.md
    with the user prompt verbatim in the `**User:**` block of the Exchange
    section. The filename is content-derived; the Context block (which used
    to carry `panel '<id>'`) is now an AI-generated summary that doesn't
    contain a stable panel reference. So we match by the user-prompt body.

    Match strategy: take a distinctive substring of the submitted prompt
    (chars 0-200) and search for it inside each candidate file's
    `**User:**` block. The submitted prompt should appear verbatim there.
    """
    # Use the first 200 chars (or full prompt if shorter) as the match
    # needle. Most prime prompts have distinctive openings; 200 chars is
    # plenty to disambiguate. We strip whitespace to handle minor
    # formatting drift between submit and file write.
    needle = " ".join(prompt.strip().split())[:200]
    if len(needle) < 30:
        # Too short to disambiguate reliably; give up.
        return None
    try:
        candidates = []
        for f in CANONICAL_CONV_DIR.glob("*.md"):
            # Only look at top-level conversations/, skip raw/, processed/, etc.
            if f.parent != CANONICAL_CONV_DIR:
                continue
            # Skip files written by Ora's startup-recovery code path
            # (filename contains "_recovered_"). These are stub records for
            # crashed submissions, not real assistant outputs — they would
            # otherwise outrank the real conversation file on mtime sort.
            if "_recovered_" in f.name:
                continue
            try:
                # Only check files modified after submission (5s slack for
                # filesystem timestamp variance).
                if f.stat().st_mtime < submit_time - 5:
                    continue
                text = f.read_text(encoding="utf-8")
                # Extract the **User:** block (between **User:** and **Assistant:**).
                if "**User:**" not in text or "**Assistant:**" not in text:
                    continue
                user_block = text.split("**User:**", 1)[1].split("**Assistant:**", 1)[0]
                # Normalize whitespace in the user block for the substring match.
                user_block_norm = " ".join(user_block.split())
                if needle in user_block_norm:
                    # Also require a substantive assistant body (>500 chars
                    # after stripping wrapping) — guards against catching a
                    # file mid-write or a stub with just the user prompt.
                    asst = text.split("**Assistant:**", 1)[1].strip()
                    if len(asst) >= 500:
                        candidates.append((f.stat().st_mtime, f))
            except Exception:
                continue
        # Return the earliest match — in the rare case multiple files match
        # (e.g., the script re-tried a mode), the first one is what we want.
        candidates.sort()
        return candidates[0][1] if candidates else None
    except Exception:
        pass
    return None


def extract_assistant_body(full_md: str) -> Optional[str]:
    """
    Extract clean analytical prose from a canonical conversation file.

    Skips frontmatter, the Context heading, the User block, and the
    `**Assistant:**` marker. Also strips any leading meta-layer oversight
    warning blockquote (a `> ⚠️ ...` block followed by a `---` separator
    inserted by oversight_health.py when the daemon heartbeats are stale).
    Returns the trailing analytical body, or None if the structure can't
    be parsed.
    """
    if "**Assistant:**" not in full_md:
        return None
    body = full_md.split("**Assistant:**", 1)[1].strip()

    # If the body starts with a blockquote (Meta-layer oversight warning),
    # skip past it. The warning is followed by a "---" separator line, then
    # the real analytical content.
    if body.lstrip().startswith(">"):
        lines = body.split("\n")
        sep_idx = None
        for i, line in enumerate(lines):
            if line.strip() == "---":
                sep_idx = i
                break
        if sep_idx is not None:
            body = "\n".join(lines[sep_idx + 1:]).strip()

    return body if body else None


def poll_completion(prompt: str, submit_time: float, timeout_sec: int = TIMEOUT_SEC) -> Optional[str]:
    """
    Poll the canonical conversations directory every POLL_INTERVAL_SEC
    seconds until the matching conversation file lands (or timeout).
    Returns the cleaned assistant body (no frontmatter, no User block, no
    oversight warning), or None on timeout.
    """
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        path = find_canonical_conversation(prompt, submit_time)
        if path is not None:
            try:
                text = path.read_text(encoding="utf-8")
                body = extract_assistant_body(text)
                # Require substantive output — guards against catching the
                # file mid-write or before the assistant turn lands.
                if body and len(body) > 100:
                    return body
            except Exception as exc:
                log(f"[WARN] canonical conversation read failed: {exc}")
        time.sleep(POLL_INTERVAL_SEC)
    return None


# ─── Paper file patching ─────────────────────────────────────────────────────
def patch_paper(paper_path: Path, ora_output: str) -> bool:
    """
    Replace the placeholder line in the Paper file with the Ora output,
    formatted as a blockquote. Returns True on success, False if the
    placeholder is not found.
    """
    if not paper_path.exists():
        log(f"[ERROR] Paper file missing: {paper_path}")
        return False

    text = paper_path.read_text(encoding="utf-8")
    if PLACEHOLDER_LINE not in text:
        log(f"[WARN] placeholder not found in {paper_path.name} — skipping patch")
        return False

    # Render the Ora output as a blockquote so it visually separates from
    # the Paper prose. Preserve internal blank lines.
    quoted_lines = []
    for ln in ora_output.splitlines():
        quoted_lines.append(f"> {ln}" if ln.strip() else ">")
    quoted = "\n".join(quoted_lines).rstrip()

    new_text = text.replace(PLACEHOLDER_LINE, quoted)
    paper_path.write_text(new_text, encoding="utf-8")
    return True


# ─── Git commit + push ───────────────────────────────────────────────────────
def commit_and_push(reason: str) -> None:
    """Stage all vault changes and commit + push. Best-effort; logs failures."""
    try:
        subprocess.run(
            ["git", "-C", str(VAULT), "add", "-A"],
            check=True, capture_output=True,
        )
        # Skip the commit if there's nothing staged.
        status = subprocess.run(
            ["git", "-C", str(VAULT), "diff", "--cached", "--quiet"],
            capture_output=True,
        )
        if status.returncode == 0:
            return  # nothing to commit
        subprocess.run(
            ["git", "-C", str(VAULT), "commit", "-m", f"refresh-mode-pages: {reason}"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(VAULT), "push"],
            check=True, capture_output=True,
        )
        log(f"[OK] committed + pushed: {reason}")
    except subprocess.CalledProcessError as exc:
        log(f"[WARN] git commit/push failed ({reason}): {exc.stderr.decode('utf-8','replace')[:300]}")


# ─── Main run loop ───────────────────────────────────────────────────────────
def build_entry_list() -> list[dict]:
    """
    Parse both inputs and build the actionable run list. Filters out
    `simple` (out of scope per reconciliation map note 6). Each entry
    is annotated with the resolved Paper path.
    """
    corpus_entries = parse_corpus(CORPUS_PATH)
    recmap = parse_reconciliation_map(RECMAP_PATH)

    out: list[dict] = []
    for entry in corpus_entries:
        slug = entry["slug"]
        # Recmap drives the skip decision for modes. Visuals are not in
        # the mode table but are always in scope.
        if entry["kind"] == "mode":
            row = recmap.get(slug)
            if row and row.get("action") == "OUT-OF-SCOPE":
                continue
            if slug == "simple":
                continue
        entry["paper_path"] = derive_paper_path(slug, entry["kind"])
        out.append(entry)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip entries already marked done in the state file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse inputs, list what would be done, and exit. No HTTP, no edits.",
    )
    args = parser.parse_args()

    if not CORPUS_PATH.exists():
        print(f"[ERROR] missing corpus: {CORPUS_PATH}", file=sys.stderr)
        return 2
    if not RECMAP_PATH.exists():
        print(f"[ERROR] missing reconciliation map: {RECMAP_PATH}", file=sys.stderr)
        return 2

    entries = build_entry_list()
    log(f"loaded {len(entries)} actionable entries (modes + visuals, simple excluded)")

    # Dry-run reporting: dump the entry list with paper paths + prime prompt
    # excerpts and exit. This is the contractual verification path.
    if args.dry_run:
        modes = [e for e in entries if e["kind"] == "mode"]
        visuals = [e for e in entries if e["kind"] == "visual"]
        print(f"\n=== DRY RUN ===")
        print(f"modes:   {len(modes)}")
        print(f"visuals: {len(visuals)}")
        print(f"total:   {len(entries)}")
        print()
        for e in entries:
            paper = e["paper_path"]
            exists = "EXISTS" if paper.exists() else "MISSING"
            placeholder = ""
            if paper.exists():
                try:
                    txt = paper.read_text(encoding="utf-8")
                    placeholder = "[ph]" if PLACEHOLDER_LINE in txt else "[no-ph]"
                except Exception:
                    placeholder = "[?]"
            prime = (e.get("prime_prompt") or "")[:90]
            print(f"  {e['kind']:6s} {e['slug']:38s} {exists:8s} {placeholder:8s} → {paper.name}")
            print(f"            prime: {prime}...")
        return 0

    # Live run.
    state = load_state() if args.resume else {"done": [], "failed": [], "skipped": []}
    done_set = set(state.get("done", []))
    failed_set = set(state.get("failed", []))

    port = read_port()
    log(f"using Ora port {port}")

    processed_since_commit = 0
    succeeded = 0
    failed = 0
    skipped = 0

    for entry in entries:
        slug = entry["slug"]
        key = f"{entry['kind']}:{slug}"

        if args.resume and key in done_set:
            log(f"[skip] {key} already done")
            skipped += 1
            continue

        prime = entry.get("prime_prompt") or ""
        if not prime:
            log(f"[skip] {key} no prime prompt parsed")
            state.setdefault("skipped", []).append(key)
            save_state(state)
            skipped += 1
            continue

        paper_path = entry["paper_path"]
        if not paper_path.exists():
            log(f"[skip] {key} Paper file missing: {paper_path.name}")
            state.setdefault("skipped", []).append(key)
            save_state(state)
            skipped += 1
            continue

        try:
            log(f"[start] {key} → {paper_path.name}")
            panel_id, submit_time = submit_chat(port, slug, prime)
            log(f"[submitted] {key} panel_id={panel_id}")
            output = poll_completion(prime, submit_time, TIMEOUT_SEC)
            if output is None:
                log(f"[TIMEOUT] {key} after {TIMEOUT_SEC}s")
                state.setdefault("failed", []).append({"key": key, "reason": "timeout"})
                save_state(state)
                failed += 1
                continue
            patched = patch_paper(paper_path, output)
            if patched:
                state.setdefault("done", []).append(key)
                save_state(state)
                log(f"[OK] {key} patched ({len(output)} chars)")
                succeeded += 1
                processed_since_commit += 1
                if processed_since_commit >= COMMIT_EVERY:
                    commit_and_push(f"+{processed_since_commit} entries")
                    processed_since_commit = 0
            else:
                state.setdefault("failed", []).append({"key": key, "reason": "patch_failed"})
                save_state(state)
                failed += 1
        except Exception as exc:
            log(f"[FAIL] {key} exception: {exc}")
            state.setdefault("failed", []).append({"key": key, "reason": str(exc)})
            save_state(state)
            failed += 1
            continue

    # Final commit catches the tail.
    if processed_since_commit > 0:
        commit_and_push(f"+{processed_since_commit} entries (final)")

    log(f"=== final report: succeeded={succeeded} failed={failed} skipped={skipped} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
