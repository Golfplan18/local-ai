#!/usr/bin/env python3
"""Auto-commit + push the Obsidian vault on a launchd cadence (every 15 min).

Kills the manual "git commit the vault" step: edits accumulate in the working
tree and nobody runs git by hand, so the GitHub backup drifts. This commits any
dirty state, integrates remote changes (other machines), and pushes.

Launched THROUGH /opt/homebrew/bin/python3 (which holds Full Disk Access) so it
can read ~/Documents/vault; a bare /bin/bash entry point is TCC-blocked there
(same pattern as com.ora.vault-derive-sync).

Single-machine-safe: `pull --rebase --autostash` before push, and a conflicted
rebase is ABORTED rather than left half-applied (self-heals next cycle).
MULTI-MACHINE CAVEAT: until G1.27 designates a primary committer, only ONE
machine should run this job, or the two will race on main.
"""
import subprocess
import sys
import datetime
import pathlib

VAULT = pathlib.Path.home() / "Documents" / "vault"
LOG = pathlib.Path.home() / "sites" / ".vault-sync" / "vault-git-autocommit.log"


def git(*args):
    return subprocess.run(
        ["git", "-C", str(VAULT), *args], capture_output=True, text=True
    )


def log(msg):
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}\n"
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(line)
    except Exception:
        pass
    print(line, end="")


def main():
    if not (VAULT / ".git").exists():
        log("ERROR: vault is not a git repo; aborting")
        return 1

    # 1. Commit local changes, if any.
    status = git("status", "--porcelain").stdout
    dirty = [ln for ln in status.splitlines() if ln.strip()]
    if dirty:
        git("add", "-A")
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        commit = git("commit", "-m", f"vault auto-sync {ts} ({len(dirty)} change(s))")
        if commit.returncode == 0:
            log(f"committed {len(dirty)} change(s)")
        else:
            log(f"commit failed: {commit.stderr.strip() or commit.stdout.strip()}")

    # 2. Integrate remote (other machines) before pushing.
    pull = git("pull", "--rebase", "--autostash")
    if pull.returncode != 0:
        log(f"pull --rebase failed; aborting rebase to stay clean: {pull.stderr.strip()}")
        git("rebase", "--abort")
        return 1

    # 3. Push anything ahead of upstream.
    ahead = git("rev-list", "--count", "@{u}..HEAD").stdout.strip()
    if ahead and ahead != "0":
        push = git("push")
        if push.returncode == 0:
            log(f"pushed {ahead} commit(s)")
        else:
            log(f"push failed: {push.stderr.strip()}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
