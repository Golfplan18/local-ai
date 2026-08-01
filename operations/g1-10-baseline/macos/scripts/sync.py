#!/usr/bin/env python3
"""
Cloud Ora vault sync.

Bidirectional sync between the local Obsidian vault and the cloud Ora server
over Tailscale via rsync.

  Mac -> cloud: non-`private`-tagged vault content -> REMOTE_VAULT_PATH
  cloud -> Mac: new MSI articles -> vault (MSI News/); general/atomics content
                -> local inbox (~/cloud-ora-sync/inbox), not the vault

Triggered by launchd (every 15 min plus RunAtLoad). Sync filter is tag-based:
any Markdown file whose YAML frontmatter contains `private` as a tag (or
`private: true` as a top-level field) is excluded from the Mac -> cloud
direction. The exclude list is rebuilt on every run.

Remote paths are the live production paths (phase (b) landed 2026-05-19):
REMOTE_VAULT_PATH is the server's real RAG-input directory, and REMOTE_OUTBOX
is the live MSI publication mirror the cloud -> Mac pull reads from.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

VAULT_DIR = Path.home() / "Documents" / "vault"

REMOTE_HOST = "cloud-ora"
REMOTE_USER = "oracle"

REMOTE_VAULT_PATH = "/home/oracle/ora/vault-sync"
REMOTE_OUTBOX = "/home/oracle/cloud-outbox"  # live production path: cloud-ora:~/msi_vault_outbox.sh mirrors MSI published news to cloud-outbox/msi-news/ every 30 min; pulled cloud -> Mac (see REMOTE_MSI_NEWS below for the exact remote path; the Mac-local mirror folder is capitalized "MSI News/" per LOCAL_MSI_NEWS -- the two names refer to different locations)

WORK_DIR = Path.home() / "cloud-ora-sync" / "var"
EXCLUDE_FILE = WORK_DIR / "exclude.txt"
LOG_FILE = WORK_DIR / "sync.log"
LOCAL_INBOX = Path.home() / "cloud-ora-sync" / "inbox"

STATIC_EXCLUDES = [
    ".git/",
    ".obsidian/",
    ".trash/",
    ".DS_Store",
    "*.tmp",
    "node_modules/",
    "__pycache__/",
    # MSI News/ (local vault folder) is a one-way mirror of the server's
    # cloud-outbox/msi-news/ into the vault (see
    # rsync_cloud_msi_news_to_vault below). Exclude from the Mac->cloud
    # direction so the published articles don't round-trip back to the
    # server's vault-sync as a second copy. Added 2026-05-28.
    "MSI News/",
]

# Server-side mirror of MSI published news lives at cloud-outbox/msi-news/
# (populated by cloud-ora:~/msi_vault_outbox.sh every 30 min). We pull
# those into the vault at ~/Documents/vault/MSI News/ for personal
# reference + future RAG. The vault location is a normal vault folder so
# Obsidian shows them in the file tree.
REMOTE_MSI_NEWS = "/home/oracle/cloud-outbox/msi-news"
LOCAL_MSI_NEWS = VAULT_DIR / "MSI News"

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
PRIVATE_TOPLEVEL_RE = re.compile(r"^private:\s*true\s*$", re.MULTILINE)
PRIVATE_LIST_ITEM_RE = re.compile(r"^\s*-\s*['\"]?private['\"]?\s*$", re.MULTILINE)
PRIVATE_INLINE_RE = re.compile(r"\[[^\]]*?\bprivate\b[^\]]*?\]")

# rsync --itemize-changes parsing for the MSI News mirror pull. The flag
# field width varies by rsync flavor: macOS's /usr/bin/rsync is openrsync
# ("rsync 2.6.9 compatible") and emits a 9-char field (e.g. `>f+++++++`),
# while GNU rsync 3.x emits 11 chars (YXcstpoguax, e.g. `>f+++++++++`).
# Match width-tolerantly: a received/updated file starts with `>f` (received)
# or `cf` (created); a deletion line is `*deleting <name>`.
# Used to feed the knowledge-index hook exactly the synced delta.
_ITEMIZE_RECV_RE = re.compile(r"^[>c]f\S+ (.+)$")
_ITEMIZE_DELETE_RE = re.compile(r"^\*deleting\s+(.+)$")


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"(log write failed: {e})", file=sys.stderr)


def has_private_tag(frontmatter: str) -> bool:
    """Return True if the frontmatter marks this file as private.

    Three forms are recognised:
      - Top-level field:  `private: true`
      - YAML block list:  `- private` on a line of its own (typical under `tags:`)
      - YAML inline list: any `[..., private, ...]` array (typical under `tags:`)

    The match is intentionally permissive: privacy false-positives (excluding a
    public file) are acceptable; false-negatives (leaking a private file) are not.
    """
    if PRIVATE_TOPLEVEL_RE.search(frontmatter):
        return True
    if PRIVATE_LIST_ITEM_RE.search(frontmatter):
        return True
    if PRIVATE_INLINE_RE.search(frontmatter):
        return True
    return False


def scan_vault_for_private() -> tuple[list[Path], int]:
    """Scan vault for private-tagged files. Returns (private_files, total_md_scanned).

    The total-scanned count is returned so the caller can detect a degenerate
    scan (zero files found) — which means either the vault path is wrong,
    the directory is unreadable (e.g., macOS TCC denied), or the vault is
    empty. In all of those cases the safe thing is to abort, not to rsync
    with an empty exclude list and risk leaking private content.
    """
    private_files: list[Path] = []
    total = 0
    for md in VAULT_DIR.rglob("*.md"):
        if any(part in (".git", ".obsidian", ".trash") for part in md.parts):
            continue
        total += 1
        try:
            with open(md, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(4096)
        except Exception as e:
            log(f"warn: could not read {md}: {e}")
            continue
        m = FRONTMATTER_RE.match(head)
        if not m:
            continue
        if has_private_tag(m.group(1)):
            private_files.append(md)
    return private_files, total


def write_exclude_file(private_files: list[Path]) -> None:
    EXCLUDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(EXCLUDE_FILE, "w") as f:
        for pat in STATIC_EXCLUDES:
            f.write(pat + "\n")
        for path in private_files:
            try:
                rel = path.relative_to(VAULT_DIR)
            except ValueError:
                continue
            f.write("/" + str(rel) + "\n")


def rsync_mac_to_cloud(dry_run: bool = False) -> int:
    cmd = [
        "rsync",
        "-az",
        "--delete",
        "--exclude-from", str(EXCLUDE_FILE),
        str(VAULT_DIR) + "/",
        f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_VAULT_PATH}/",
    ]
    if dry_run:
        cmd.insert(1, "--dry-run")
        cmd.insert(2, "--stats")
    log("Mac -> cloud: " + " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"Mac -> cloud FAILED (rc={result.returncode})")
        if result.stderr:
            for line in result.stderr.strip().splitlines()[-10:]:
                log("  stderr: " + line)
    else:
        out = result.stdout.strip().splitlines()
        log(f"Mac -> cloud OK ({len(out)} rsync output lines)")
    return result.returncode


def rsync_cloud_to_mac(dry_run: bool = False) -> int:
    LOCAL_INBOX.mkdir(parents=True, exist_ok=True)
    cmd = [
        "rsync",
        "-az",
        # msi-news/ is handled by the dedicated vault-mirror sync (see
        # rsync_cloud_msi_news_to_vault below); excluding it from the
        # general inbox pull avoids a second copy of every MSI article
        # landing in ~/cloud-ora-sync/inbox/msi-news/.
        "--exclude=msi-news/",
        f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_OUTBOX}/",
        str(LOCAL_INBOX) + "/",
    ]
    if dry_run:
        cmd.insert(1, "--dry-run")
        cmd.insert(2, "--stats")
    log("cloud -> Mac: " + " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"cloud -> Mac FAILED (rc={result.returncode})")
        if result.stderr:
            for line in result.stderr.strip().splitlines()[-10:]:
                log("  stderr: " + line)
    else:
        out = result.stdout.strip().splitlines()
        log(f"cloud -> Mac OK ({len(out)} rsync output lines)")
    return result.returncode


def rsync_cloud_msi_news_to_vault(
    dry_run: bool = False,
) -> tuple[int, list[str], list[str]]:
    """Pull published MSI news from cloud-outbox into the vault as MSI News/.

    Uses ``--delete`` to mirror exactly what's in the server's outbox.
    Engrams and personal-vault content are not touched — only the
    MSI News/ folder is rewritten on each run.

    The Mac->cloud direction excludes ``MSI News/`` (see STATIC_EXCLUDES
    above), so MSI articles flowing INTO the vault here do not loop
    back as a second copy at ``cloud:~/ora/vault-sync/MSI News/``.
    """
    LOCAL_MSI_NEWS.mkdir(parents=True, exist_ok=True)
    cmd = [
        "rsync",
        "-az",
        "-i",  # itemize-changes, so the caller can index exactly the delta
        "--delete",
        f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_MSI_NEWS}/",
        str(LOCAL_MSI_NEWS) + "/",
    ]
    if dry_run:
        cmd.insert(1, "--dry-run")
        cmd.insert(2, "--stats")
    log("cloud MSI News -> Mac vault: " + " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    changed: list[str] = []
    deleted: list[str] = []
    if result.returncode != 0:
        log(f"cloud MSI News -> Mac vault FAILED (rc={result.returncode})")
        if result.stderr:
            for line in result.stderr.strip().splitlines()[-10:]:
                log("  stderr: " + line)
    else:
        for line in result.stdout.splitlines():
            dm = _ITEMIZE_DELETE_RE.match(line)
            rm = _ITEMIZE_RECV_RE.match(line)
            if dm and dm.group(1).strip().endswith(".md"):
                deleted.append(dm.group(1).strip())
            elif rm and rm.group(1).strip().endswith(".md"):
                changed.append(rm.group(1).strip())
        log(f"cloud MSI News -> Mac vault OK "
            f"({len(changed)} md changed, {len(deleted)} md deleted)")
    return result.returncode, changed, deleted


def index_synced_msi_news(changed: list[str], deleted: list[str]) -> None:
    """Index the just-synced MSI delta into the Ora `knowledge` collection.

    knowledge_v2 is local, so MSI news enters the conversational knowledge
    RAG here — right after the cloud->vault mirror updates (runtime
    indexing, no separate cron). The Ora injector forces the schema
    (type:resource + nexus:main-street-independent + the news/msi-news
    tags) at index time, so the mirror's unstamped files need no
    modification, and a knowledge_v2 doc persists through later rsync
    reverts. Fail-soft: never breaks the sync.
    """
    if not changed and not deleted:
        return
    try:
        ora_home = str(Path.home() / "ora")
        if ora_home not in sys.path:
            sys.path.insert(0, ora_home)
        from orchestrator.tools.index_msi_news import (
            index_msi_news, remove_paths,
        )
        if changed:
            stats = index_msi_news(
                [str(LOCAL_MSI_NEWS / n) for n in changed], force=True,
            )
            log(f"knowledge-index MSI delta: {stats}")
        if deleted:
            n = remove_paths([str(LOCAL_MSI_NEWS / n) for n in deleted])
            log(f"knowledge-index removed {n} deleted MSI article(s)")
    except Exception as e:
        log(f"knowledge-index hook failed (non-fatal): "
            f"{type(e).__name__}: {e}")


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    if not VAULT_DIR.is_dir():
        log(f"FATAL: vault directory not found at {VAULT_DIR}")
        return 2
    log(f"=== sync run start{' (DRY RUN)' if dry_run else ''} ===")
    private_files, total_scanned = scan_vault_for_private()
    log(f"scanned vault: {total_scanned} markdown file(s) total, {len(private_files)} private-tagged to exclude")
    if total_scanned == 0:
        log("FATAL: scanned 0 markdown files — vault unreadable, wrong path, or empty.")
        log("       Refusing to rsync with an empty exclude list (privacy guard).")
        log("       Common cause: launchd-spawned process lacks macOS TCC access to ~/Documents/.")
        log("       Fix: ensure the python interpreter in the launchd plist has Full Disk Access,")
        log("       or use an interpreter that already does (e.g., /opt/homebrew/bin/python3).")
        log("=== sync run end (aborted before rsync) ===")
        return 3
    write_exclude_file(private_files)
    rc1 = rsync_mac_to_cloud(dry_run=dry_run)
    rc2 = rsync_cloud_to_mac(dry_run=dry_run)
    rc3, msi_changed, msi_deleted = rsync_cloud_msi_news_to_vault(dry_run=dry_run)
    if not dry_run:
        index_synced_msi_news(msi_changed, msi_deleted)
    log(f"=== sync run end (mac->cloud={rc1}, cloud->mac={rc2}, "
        f"cloud->vault-msi-news={rc3}) ===")
    return 0 if (rc1 == 0 and rc2 == 0 and rc3 == 0) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
