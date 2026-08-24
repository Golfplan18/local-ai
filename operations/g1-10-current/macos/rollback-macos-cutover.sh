#!/usr/bin/env bash
set -euo pipefail

ROOT="${ORA_HOME:-$HOME/ora}"
MANIFEST="$ROOT/operations/g1-10-baseline/manifest.json"
RECOVERY="$HOME/Library/Application Support/Ora/g1-10-launchagents-before"
STATE="$HOME/Library/Application Support/Ora/g1-10-macos-cutover.json"

python3 - "$MANIFEST" "$RECOVERY" <<'PY'
import hashlib, json, pathlib, sys
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
active_root = pathlib.Path.home() / "Library" / "LaunchAgents"
recovery = pathlib.Path(sys.argv[2])
for name, expected in manifest["macos_launchagents"].items():
    if name in {"com.ora.server.plist", "com.cloud-ora.sync.plist"}:
        continue
    source = recovery / name
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise SystemExit(f"rollback source drift: {source}")
    active = active_root / name
    if active.exists() and hashlib.sha256(active.read_bytes()).hexdigest() != expected:
        raise SystemExit(f"refusing to overwrite unrelated LaunchAgent: {active}")
PY

for plist in "$RECOVERY"/*.plist; do
  label="$(basename "$plist" .plist)"
  [[ "$label" == "com.ora.server" || "$label" == "com.cloud-ora.sync" ]] && continue
  active="$HOME/Library/LaunchAgents/$label.plist"
  install -m 0644 "$plist" "$active"
  if ! launchctl print "gui/$UID/$label" >/dev/null 2>&1; then
    launchctl bootstrap "gui/$UID" "$active"
  fi
done
python3 - "$STATE" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
value = {"schema_version": 1, "status": "rolled_back"}
path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
PY
echo "Restored four recoverable pre-G1.10 cadence agents; cloud sync remains event-driven"
