#!/opt/homebrew/bin/python3
"""vault-derive-sync-launch.py — launchd entry point for WS0.

WHY THIS EXISTS: a launchd-spawned /bin/bash cannot read ~/Documents/vault —
macOS TCC blocks the Documents folder for background agents, so the bare
vault-derive-sync.sh got `find: .../Documents/vault: Operation not permitted`
and derived nothing.

Homebrew's /opt/homebrew/bin/python3 DOES hold Full Disk Access (granted by the
user for the com.cloud-ora.sync agent, whose python rglobs the vault and shells
out to rsync against it every 15 min). Child processes a TCC-granted process
spawns inherit that access — that is exactly how com.cloud-ora.sync's rsync
child reads the vault. So launchd runs THIS file under that same python, and we
spawn the bash reconcile as a child; its find/node grandchildren inherit the
grant and can read ~/Documents/vault.

Invoke exactly as: /opt/homebrew/bin/python3 vault-derive-sync-launch.py [--push]
(the leading python path must be /opt/homebrew/bin/python3 — the FDA grant is
attached to that binary).
"""
import subprocess
import sys

SCRIPT = "/Users/oracle/sites/scripts/vault-derive-sync.sh"

sys.exit(subprocess.call([SCRIPT, *sys.argv[1:]]))
