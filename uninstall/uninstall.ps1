# Ora uninstall — Windows entry point (PowerShell).
# Thin wrapper that defers to uninstall.py. Pass through any flags
# (--dry-run, --include-models, --include-conversations).

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }

& $Python "$ScriptDir/uninstall.py" $args
exit $LASTEXITCODE
