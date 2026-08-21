#!/usr/bin/env python3
"""Ora uninstall companion (install Chunk 9).

Removes runtime state created by ``scripts/install.py`` and the day-to-day
operation of Ora. By design:

  - **NEVER** touches the configured vault — that's the
    canonical persistence layer for the user's content.
  - Preserves the configured conversations directory by default. Pass
    ``--include-conversations`` to opt in to deleting them.
  - Preserves downloaded local model files by default (expensive to
    re-download). Pass ``--include-models`` to opt in.
  - Preserves the downloaded document converters (Pandoc + Typst, in
    ``data/converters/``) by default, for the same reason: they are large
    and ``python3 scripts/install.py converters`` fetches them again. Pass
    ``--include-converters`` to opt in.
  - Does NOT delete the git checkout itself (the source tree where the
    user ran git clone). That's the user's working copy.

Multi-step confirmation: requires the user to type the literal word
``DELETE`` to proceed. ``--dry-run`` previews without making changes;
``--yes`` is rejected for safety (the typed keyword is intentionally
human-only — automation should re-confirm by typing it on stdin).

This script lives in its own directory (``~/ora/uninstall/``) rather
than ``scripts/`` so accidental tab-completion in the wrong terminal
doesn't surface it alongside install.py and the dev tools.

Usage:
    python3 uninstall/uninstall.py                # interactive, preserve everything except runtime state
    python3 uninstall/uninstall.py --include-models           # also delete downloaded models
    python3 uninstall/uninstall.py --include-converters       # also delete Pandoc/Typst
    python3 uninstall/uninstall.py --include-conversations    # also delete conversations
    python3 uninstall/uninstall.py --dry-run                  # preview, no changes
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from orchestrator import runtime_paths as _rp  # noqa: E402

_ROOTS = _rp.resolve_runtime_roots()
VAULT = _ROOTS.vault
CONVERSATIONS = _ROOTS.conversations

# Paths the uninstaller removes by default. These are runtime artifacts
# only — no source code, no user content.
ALWAYS_REMOVE = [
    REPO_ROOT / "install-state.json",
    REPO_ROOT / "install.log",
    REPO_ROOT / "config" / "model-catalog.json",
    REPO_ROOT / "config" / "browser-models.json",     # deprecated subscription dispatch artifact
    REPO_ROOT / "data" / "model-catalog-changes.jsonl",
    REPO_ROOT / "data" / "chroma",                    # ChromaDB index — rebuildable from sources
    REPO_ROOT / "data" / "pipeline-traces",           # per-turn forensic traces
    REPO_ROOT / "data" / "oversight" / "events.jsonl",
    REPO_ROOT / "data" / "oversight" / "actions.jsonl",
    REPO_ROOT / "data" / "oversight" / "human-queue.jsonl",
    REPO_ROOT / "data" / "oversight" / "reeval-queue.jsonl",
    REPO_ROOT / "data" / "processing-manifest.json",
    REPO_ROOT / "cache",                              # ephemeral cache
    REPO_ROOT / "config" / ".direct-api-refresh-stamp",
    REPO_ROOT / "config" / "browser-sessions",        # already gone post-Chunk-1; harmless if absent
]

# Auto-populated configuration files (Chunk 5 output). Remove all *.json
# in config/configurations/. The directory itself is recreated on next
# install — keeping it would leave a confusing empty dir behind.
CONFIGURATIONS_DIR = REPO_ROOT / "config" / "configurations"

# Optional removals — explicit opt-in flags only.
OPT_IN_MODELS = [REPO_ROOT / "models"]
OPT_IN_CONVERSATIONS = [CONVERSATIONS]
# Pandoc and Typst, downloaded per machine by scripts/converters.py. Anchored
# to this clone because that is where the installer puts them: the launchers
# export ORA_HOME as the checkout they live in, so the clone is the runtime's
# Ora home whatever ORA_HOME happens to say in this shell.
OPT_IN_CONVERTERS = [REPO_ROOT / "data" / "converters"]

# Hard NEVER list — uninstaller refuses to touch these even with flags.
HARD_PRESERVE = [
    VAULT,                                            # vault is canonical
    REPO_ROOT / ".git",                               # the user's git history
    REPO_ROOT / "orchestrator",                       # source tree
    REPO_ROOT / "server",                             # source tree
    REPO_ROOT / "scripts",                            # source tree
    REPO_ROOT / "modes",                              # source tree
    REPO_ROOT / "frameworks",                         # source tree
    REPO_ROOT / "modules",                            # source tree
    REPO_ROOT / "knowledge",                          # user content (gitignored)
    REPO_ROOT / "boot",                               # system prompts
    REPO_ROOT / "mind.md",                            # personality layer
    REPO_ROOT / "CLAUDE.md",                          # operating rules
    REPO_ROOT / "FORKING.md",                         # docs
    REPO_ROOT / "uninstall",                          # this very script
]


def _is_hard_preserved(path: Path) -> bool:
    """Defense in depth — if removal target is anywhere under a HARD_PRESERVE
    path, refuse to proceed. Catches both the bare path and any descendant."""
    abs_path = path.resolve()
    for protected in HARD_PRESERVE:
        try:
            abs_path.relative_to(protected.resolve())
            return True
        except ValueError:
            continue
    return False


def _describe_path(path: Path) -> str:
    """Return a human description: size, type, existence."""
    if not path.exists():
        return f"  - {path} (does not exist; skipping)"
    if path.is_file():
        try:
            size = path.stat().st_size
            return f"  - {path} (file, {size:,} bytes)"
        except OSError:
            return f"  - {path} (file)"
    if path.is_dir():
        try:
            count = sum(1 for _ in path.rglob("*"))
            return f"  - {path}/ (directory, ~{count} entries)"
        except OSError:
            return f"  - {path}/ (directory)"
    return f"  - {path} (other)"


def _remove(path: Path, dry_run: bool) -> bool:
    """Remove a file or directory. Returns True on success or if absent."""
    if _is_hard_preserved(path):
        print(f"  ✗ REFUSING to touch hard-preserved path: {path}")
        return False
    if not path.exists():
        return True
    if dry_run:
        print(f"  [dry-run] would remove {path}")
        return True
    try:
        if path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
        print(f"  ✓ removed {path}")
        return True
    except OSError as exc:
        print(f"  ✗ failed to remove {path}: {exc}")
        return False


def _gather_targets(
    include_models: bool,
    include_conversations: bool,
    include_converters: bool = False,
) -> list[Path]:
    targets: list[Path] = []
    targets.extend(ALWAYS_REMOVE)

    # All custom configurations (Chunk 5 output)
    if CONFIGURATIONS_DIR.exists():
        for child in CONFIGURATIONS_DIR.glob("*.json"):
            targets.append(child)

    if include_models:
        targets.extend(OPT_IN_MODELS)
    if include_conversations:
        targets.extend(OPT_IN_CONVERSATIONS)
    if include_converters:
        targets.extend(OPT_IN_CONVERTERS)

    return targets


def _confirm() -> bool:
    """Multi-step typed-DELETE confirmation. Returns True if confirmed."""
    print()
    print("=" * 60)
    print("CONFIRMATION REQUIRED")
    print("=" * 60)
    print()
    print("This will remove Ora's runtime state (configurations, model")
    print("catalog, ChromaDB index, install log, etc.).")
    print()
    print("To proceed, type the literal word: DELETE")
    print("Anything else cancels.")
    print()
    try:
        response = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if response == "DELETE":
        return True
    print()
    print(f"Got {response!r} — not 'DELETE'. Cancelled.")
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Uninstall Ora runtime state. Vault and source tree are never touched.",
    )
    parser.add_argument(
        "--include-models", action="store_true",
        help="Also delete downloaded local model files (~/ora/models/). "
             "Default: preserved — re-downloading is expensive.",
    )
    parser.add_argument(
        "--include-converters", action="store_true",
        help="Also delete the downloaded Word/PDF converters "
             "(<clone>/data/converters/). Default: preserved — re-download "
             "them with `python3 scripts/install.py converters`.",
    )
    parser.add_argument(
        "--include-conversations", action="store_true",
        help="Also delete conversation history (~/Documents/conversations/). "
             "Default: preserved.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be removed without making changes.",
    )
    args = parser.parse_args()

    print("Ora uninstall — runtime state removal")
    print(f"Repo root:     {REPO_ROOT}")
    print(f"Documents:     {_ROOTS.documents}  ({_ROOTS.sources['documents']})")
    print(f"Vault:         {VAULT}  ({_ROOTS.sources['vault']}; NEVER touched)")
    print(f"Conversations: {CONVERSATIONS}  ({_ROOTS.sources['conversations']}; "
          f"{'WILL DELETE' if args.include_conversations else 'preserved'})")
    print(f"Models:        {REPO_ROOT / 'models'}  ({'WILL DELETE' if args.include_models else 'preserved'})")
    print(f"Converters:    {OPT_IN_CONVERTERS[0]}  "
          f"({'WILL DELETE' if args.include_converters else 'preserved'})")
    for warning in _ROOTS.warnings:
        print(f"WARNING: {warning}")
    print()

    targets = _gather_targets(
        args.include_models, args.include_conversations, args.include_converters)
    if not targets:
        print("Nothing to remove.")
        return

    print(f"Targets ({len(targets)} paths):")
    for t in targets:
        print(_describe_path(t))
    print()

    if args.dry_run:
        print("[dry-run] No changes made.")
        return

    if not _confirm():
        sys.exit(0)

    print()
    print("Removing...")
    failed = 0
    for t in targets:
        if not _remove(t, dry_run=False):
            failed += 1

    # Recreate the empty configurations directory so the next install has
    # a place to write to (avoids confusion vs "no configurations directory
    # ever existed").
    if CONFIGURATIONS_DIR.parent.exists() and not CONFIGURATIONS_DIR.exists():
        CONFIGURATIONS_DIR.mkdir(parents=True, exist_ok=True)
        print(f"  ✓ recreated empty {CONFIGURATIONS_DIR}/ for next install")

    print()
    if failed:
        print(f"UNINSTALL_COMPLETE_WITH_ERRORS: {failed} path(s) failed to remove.")
        sys.exit(1)
    print("UNINSTALL_COMPLETE: 0 errors")
    print()
    print("Vault and conversations preserved. Re-install with:")
    print("  python3 scripts/install.py --profile solo")


if __name__ == "__main__":
    main()
