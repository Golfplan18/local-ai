#!/usr/bin/env bash
set -euo pipefail

ROOT="${ORA_HOME:-$HOME/ora}"
CURRENT="$ROOT/operations/g1-10-current/cloud"
BASELINE="$ROOT/operations/g1-10-baseline/cloud"
MANIFEST="$ROOT/operations/g1-10-baseline/manifest.json"
BACKUP="$HOME/.local/state/ora/g1-10-cloud-cutover"
STATE="$HOME/.local/state/ora/g1-10-cloud-cutover.json"
mkdir -p "$BACKUP"
exec 9>"$HOME/.local/state/ora/.g1-10-cloud-cutover.lock"
flock -x 9

if [[ -n "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ]]; then
  echo "tracked cloud runtime worktree is dirty; refusing cutover" >&2
  exit 1
fi
DEPLOYMENT_COMMIT="$(git -C "$ROOT" rev-parse HEAD)"
CURRENT_MANIFEST="$ROOT/operations/g1-10-current/manifest.json"

crontab -l > "$BACKUP/crontab.observed"
python3 - "$MANIFEST" "$CURRENT" "$BACKUP" <<'PY'
import hashlib, json, pathlib, shutil, sys
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
current_root = pathlib.Path(sys.argv[2])
backup = pathlib.Path(sys.argv[3])

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

for name, baseline_digest in manifest["cloud_scripts"].items():
    installed = pathlib.Path.home() / name
    current = current_root / "scripts" / name
    actual = digest(installed)
    allowed = {baseline_digest, digest(current)}
    if actual not in allowed:
        raise SystemExit(f"installed cloud source drift: {installed}: {actual}")
    preserved = backup / name
    if not preserved.exists():
        baseline = pathlib.Path(sys.argv[1]).parent / "cloud" / "scripts" / name
        shutil.copy2(baseline, preserved)
    if digest(preserved) != baseline_digest:
        raise SystemExit(f"rollback source drift: {preserved}")

new_helper = pathlib.Path.home() / "gear4-expiration.py"
current_helper = current_root / "scripts" / new_helper.name
if new_helper.exists() and digest(new_helper) != digest(current_helper):
    raise SystemExit(f"unowned deadline-helper collision: {new_helper}")

observed_cron = backup / "crontab.observed"
baseline_cron = pathlib.Path(sys.argv[1]).parent / "cloud" / "crontab.before"
current_cron = current_root / "crontab.after"
observed_digest = digest(observed_cron)
if observed_digest not in {digest(baseline_cron), digest(current_cron)}:
    raise SystemExit(f"installed crontab drift: {observed_digest}")
preserved_cron = backup / "crontab.before"
if not preserved_cron.exists():
    shutil.copy2(baseline_cron, preserved_cron)
if digest(preserved_cron) != digest(baseline_cron):
    raise SystemExit("rollback crontab drift")
PY

for script in "$CURRENT"/scripts/*; do
  [[ -f "$script" ]] || continue
  install -m 0755 "$script" "$HOME/$(basename "$script")"
done
crontab "$CURRENT/crontab.after"

python3 - "$STATE" "$ROOT" "$CURRENT" "$DEPLOYMENT_COMMIT" \
  "$MANIFEST" "$CURRENT_MANIFEST" <<'PY'
import hashlib, json, os, pathlib, sys, tempfile
path = pathlib.Path(sys.argv[1])
current = pathlib.Path(sys.argv[3])
record = {
    "schema_version": 1,
    "status": "completed",
    "runtime_root": str(pathlib.Path(sys.argv[2]).resolve()),
    "git_commit": sys.argv[4],
    "baseline_manifest_sha256": hashlib.sha256(
        pathlib.Path(sys.argv[5]).read_bytes()).hexdigest(),
    "current_manifest_sha256": hashlib.sha256(
        pathlib.Path(sys.argv[6]).read_bytes()).hexdigest(),
    "crontab_sha256": hashlib.sha256((current / "crontab.after").read_bytes()).hexdigest(),
    "installed_scripts": {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((current / "scripts").iterdir()) if p.is_file()
    },
}
fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
with os.fdopen(fd, "w") as handle:
    json.dump(record, handle, indent=2, sort_keys=True)
    handle.flush(); os.fsync(handle.fileno())
os.replace(tmp, path)
PY
echo "G1.10 cloud cutover installed; rollback at $BACKUP"
