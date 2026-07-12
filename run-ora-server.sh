#!/usr/bin/env bash
# Canonical foreground Ora server launcher.
#
# This file is the single source for runtime feature flags and the server
# command. launchd executes it directly and keeps this process alive; start.sh
# may background it only when no supervised service is installed.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
WORKSPACE="${ORA_HOME:-$SCRIPT_DIR}"
if [[ ! -d "$WORKSPACE" ]]; then
  echo "ERROR: ORA_HOME is not a directory: $WORKSPACE" >&2
  exit 1
fi
WORKSPACE="$(cd -- "$WORKSPACE" && pwd -P)"

# Guarantee stable path resolution throughout the process tree, including
# launchd sessions whose inherited environment is intentionally sparse.
if [[ -z "${HOME:-}" ]]; then
  HOME="$(cd ~ && pwd -P)"
fi
export HOME
export ORA_HOME="$WORKSPACE"
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"

# launchd and generated .app processes inherit a deliberately sparse PATH.
# Prepend Ora's supported user/Homebrew locations while preserving any caller
# additions so npx MCPs, Claude, Pandoc/Typst, ffmpeg, and other runtime tools
# resolve the same way they do in an interactive shell.
export PATH="$HOME/.local/bin:$HOME/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin:/usr/sbin:/sbin}"

# Runtime feature policy. An explicit caller value (including 0) wins, which
# keeps diagnostic opt-outs possible without maintaining another launcher.
export ORA_RAG_SELECTION="${ORA_RAG_SELECTION:-1}"
export ORA_RAG_FIT_GATE_SLOT="${ORA_RAG_FIT_GATE_SLOT:-sidebar}"
export ORA_WEB_EXTRACTION="${ORA_WEB_EXTRACTION:-1}"
export ORA_RUNTIME_ENGRAM_PROMOTION="${ORA_RUNTIME_ENGRAM_PROMOTION:-1}"
export ORA_RUNTIME_ENGRAM_AUTOCOMMIT="${ORA_RUNTIME_ENGRAM_AUTOCOMMIT:-1}"
export ORA_DELIVERABLE_SCRUB="${ORA_DELIVERABLE_SCRUB:-1}"
export ORA_OR_STATS="${ORA_OR_STATS:-1}"
export ORA_EXECUTION_LOOP="${ORA_EXECUTION_LOOP:-1}"

if [[ -n "${ORA_PYTHON:-}" ]]; then
  if [[ "$ORA_PYTHON" == */* ]]; then
    PYTHON="$ORA_PYTHON"
  else
    PYTHON="$(command -v -- "$ORA_PYTHON" 2>/dev/null || true)"
  fi
elif [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV:-}/bin/python" ]]; then
  # An activated virtual environment is an explicit interpreter selection.
  # Resolve it before the launchd-oriented PATH fallback so interactive Linux,
  # WSL, and developer starts use the environment that owns their dependencies.
  PYTHON="${VIRTUAL_ENV}/bin/python"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV:-}/bin/python3" ]]; then
  # Some minimal environments expose only python3 inside the venv.
  PYTHON="${VIRTUAL_ENV}/bin/python3"
else
  # PATH above already includes Apple Silicon and Intel Homebrew locations,
  # followed by the caller/system path, so one resolution path covers macOS,
  # Linux, WSL, and relocatable test environments.
  PYTHON="$(command -v python3 2>/dev/null || true)"
fi

if [[ -z "${PYTHON:-}" || ! -x "$PYTHON" ]]; then
  echo "ERROR: python3 not found. Install Python 3.10+ or set ORA_PYTHON." >&2
  exit 1
fi

oversight=1
server_args=()
for arg in "$@"; do
  if [[ "$arg" == "--no-oversight" ]]; then
    oversight=0
  else
    server_args+=("$arg")
  fi
done

cd "$WORKSPACE"
if (( oversight )); then
  if (( ${#server_args[@]} )); then
    exec "$PYTHON" "$WORKSPACE/server/server.py" --oversight "${server_args[@]}"
  else
    # macOS still ships Bash 3.2, where expanding an empty array under
    # `set -u` raises "unbound variable". launchd normally supplies no args.
    exec "$PYTHON" "$WORKSPACE/server/server.py" --oversight
  fi
else
  if (( ${#server_args[@]} )); then
    exec "$PYTHON" "$WORKSPACE/server/server.py" "${server_args[@]}"
  else
    exec "$PYTHON" "$WORKSPACE/server/server.py"
  fi
fi
