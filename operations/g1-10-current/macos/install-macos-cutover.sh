#!/usr/bin/env bash
set -euo pipefail

ROOT="${ORA_HOME:-$HOME/ora}"
MANIFEST="$ROOT/operations/g1-10-baseline/manifest.json"
BACKUP="$HOME/Library/Application Support/Ora/g1-10-launchagents-before"
STATE="$HOME/Library/Application Support/Ora/g1-10-macos-cutover.json"
LOCK="$HOME/Library/Application Support/Ora/.g1-10-macos-cutover.lock.d"
mkdir -p "$BACKUP"

if [[ -n "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ]]; then
  echo "tracked runtime worktree is dirty; refusing Mac cutover" >&2
  exit 1
fi
DEPLOYMENT_COMMIT="$(git -C "$ROOT" rev-parse HEAD)"
CURRENT_MANIFEST="$ROOT/operations/g1-10-current/manifest.json"

if ! mkdir "$LOCK" 2>/dev/null; then
  echo "G1.10 Mac cutover already in progress or stale lock exists: $LOCK" >&2
  exit 75
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

python3 - "$MANIFEST" "$BACKUP" <<'PY'
import hashlib, json, pathlib, sys
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
active_root = pathlib.Path.home() / "Library" / "LaunchAgents"
backup_root = pathlib.Path(sys.argv[2])
retired = {name: digest for name, digest in manifest["macos_launchagents"].items()
           if name != "com.ora.server.plist"}
for name, expected in retired.items():
    active = active_root / name
    backup = backup_root / name
    present = []
    for label, path in (("active", active), ("backup", backup)):
        if path.exists():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                raise SystemExit(f"{label} LaunchAgent drift: {path}: {actual} != {expected}")
            present.append(label)
    if not present:
        raise SystemExit(f"LaunchAgent missing from active and recovery state: {name}")
server = active_root / "com.ora.server.plist"
expected = manifest["macos_launchagents"][server.name]
actual = hashlib.sha256(server.read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit(f"server LaunchAgent drift: {actual} != {expected}")
PY

for label in \
  com.cloud-ora.sync \
  com.msi.image-mirror \
  com.msi.repo-pullsync \
  com.ora.vault-derive-sync \
  com.ora.vault-git-autocommit
do
  plist="$HOME/Library/LaunchAgents/$label.plist"
  recovery="$BACKUP/$label.plist"
  if [[ -e "$plist" ]]; then
    if launchctl print "gui/$UID/$label" >/dev/null 2>&1; then
      launchctl bootout "gui/$UID" "$plist"
    fi
    if [[ -e "$recovery" ]]; then
      cmp -s "$plist" "$recovery" || { echo "ambiguous recovery state: $label" >&2; exit 1; }
      rm "$plist"
    else
      mv "$plist" "$recovery"
    fi
  fi
done

python3 - "$STATE" "$ROOT" "$BACKUP" "$DEPLOYMENT_COMMIT" \
  "$MANIFEST" "$CURRENT_MANIFEST" <<'PY'
import hashlib, json, os, pathlib, sys, tempfile
path = pathlib.Path(sys.argv[1])
record = {
    "schema_version": 1,
    "status": "completed",
    "runtime_root": str(pathlib.Path(sys.argv[2]).resolve()),
    "recovery_directory": str(pathlib.Path(sys.argv[3]).resolve()),
    "git_commit": sys.argv[4],
    "baseline_manifest_sha256": hashlib.sha256(
        pathlib.Path(sys.argv[5]).read_bytes()).hexdigest(),
    "current_manifest_sha256": hashlib.sha256(
        pathlib.Path(sys.argv[6]).read_bytes()).hexdigest(),
    "retired_labels": [
        "com.cloud-ora.sync", "com.msi.image-mirror", "com.msi.repo-pullsync",
        "com.ora.vault-derive-sync", "com.ora.vault-git-autocommit",
    ],
    "preserved_label": "com.ora.server",
    "server_plist_preserved": True,
}
path.parent.mkdir(parents=True, exist_ok=True)
fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
with os.fdopen(fd, "w") as handle:
    json.dump(record, handle, indent=2, sort_keys=True)
    handle.flush(); os.fsync(handle.fileno())
os.replace(tmp, path)
PY
echo "G1.10 Mac cadence agents retired; recovery copies at $BACKUP"
