#!/usr/bin/env bash
set -euo pipefail

ROOT="${ORA_HOME:-$HOME/ora}"
BASELINE="$ROOT/operations/g1-10-baseline/cloud"
CURRENT="$ROOT/operations/g1-10-current/cloud"
MANIFEST="$ROOT/operations/g1-10-baseline/manifest.json"
STATE="$HOME/.local/state/ora/g1-10-cloud-cutover.json"

python3 - "$MANIFEST" "$CURRENT" <<'PY'
import hashlib, json, pathlib, sys
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
current = pathlib.Path(sys.argv[2]) / "scripts"
for name, baseline_digest in manifest["cloud_scripts"].items():
    installed = pathlib.Path.home() / name
    actual = hashlib.sha256(installed.read_bytes()).hexdigest()
    current_digest = hashlib.sha256((current / name).read_bytes()).hexdigest()
    if actual not in {baseline_digest, current_digest}:
        raise SystemExit(f"refusing to overwrite unrelated cloud source: {installed}")
helper = pathlib.Path.home() / "gear4-expiration.py"
if helper.exists():
    expected = hashlib.sha256((current / helper.name).read_bytes()).hexdigest()
    if hashlib.sha256(helper.read_bytes()).hexdigest() != expected:
        raise SystemExit(f"refusing to remove unrelated helper: {helper}")
PY

for script in "$BASELINE"/scripts/*; do
  install -m 0755 "$script" "$HOME/$(basename "$script")"
done
helper="$HOME/gear4-expiration.py"
[[ ! -e "$helper" ]] || rm "$helper"
crontab "$BASELINE/crontab.before"
python3 - "$STATE" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({"schema_version": 1, "status": "rolled_back"},
                           indent=2, sort_keys=True) + "\n")
PY
echo "Restored tracked G1.10 pre-cutover cloud scripts and crontab"
