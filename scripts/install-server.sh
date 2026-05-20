#!/usr/bin/env bash
#
# scripts/install-server.sh — minimal API-only Ora server install for Linux.
#
# Stands up a headless Ora install for cloud / server use. No local models,
# no Flask exposure beyond localhost, no worker pool. Designed for the
# MSI publication cadence on a small Linux box (tested on Hetzner CX33,
# Ubuntu 24.04, 8 GB RAM).
#
# What it does:
#   1. Verifies Linux + Python 3.11+; apt-installs python3-venv, pip, git, curl
#      if missing.
#   2. Creates a virtualenv at .venv/ and installs the Linux subset of
#      Ora's Python deps (no mlx-lm).
#   3. Installs ollama and pulls nomic-embed-text for ChromaDB embeddings.
#   4. Rewrites config/routing-config.json's slot_assignments + default
#      endpoint to OpenRouter-routed picks (qwen3.6-plus for analysis,
#      qwen3.6-35b-a3b for utility) so nothing references a local MLX model
#      and the server only needs one API key.
#   5. Prompts for OPENROUTER_API_KEY (and optionally ANTHROPIC_API_KEY)
#      and writes them to ~/.config/ora-server.env (600 perms).
#   6. Runs a smoke test that loads the config, resolves a slot endpoint,
#      and reports the install state.
#
# What it does NOT do:
#   - HuggingFace local-model downloads (no GPU).
#   - MLX setup (Apple Silicon only).
#   - Worker pool / concurrency primitives (gated on the concurrency
#     architecture thread — single-process is fine for MSI's cadence).
#   - systemd / cron configuration — the MSI cadence is configured
#     separately (see docs/cloud-ora-cron.md once written, or hand-roll).
#   - Public Flask exposure — chat UI is not bound on the server.
#
# Re-run safety: idempotent. Skips steps whose state is already present.
#
# Usage:
#   # On the server, from inside a fresh git clone of ora-commons/ora:
#   ./scripts/install-server.sh
#
# Flags:
#   --skip-ollama   Don't install ollama or pull the embedding model
#                   (ChromaDB RAG will not work without it).
#   --skip-key      Don't prompt for API keys (assumes they're already in
#                   the environment or ~/.config/ora-server.env).
#   --dry-run       Print what would happen without changing anything.

set -euo pipefail

# ─── flags ─────────────────────────────────────────────────────────────
SKIP_OLLAMA=0
SKIP_KEY=0
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --skip-ollama) SKIP_OLLAMA=1 ;;
    --skip-key)    SKIP_KEY=1 ;;
    --dry-run)     DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "[install-server] Unknown flag: $arg" >&2
      exit 1
      ;;
  esac
done

# ─── helpers ───────────────────────────────────────────────────────────
log() { printf '[install-server] %s\n' "$*" >&2; }
run() {
  if (( DRY_RUN )); then
    printf '[install-server] DRY: %s\n' "$*" >&2
  else
    eval "$@"
  fi
}

# ─── 1. preflight ──────────────────────────────────────────────────────
log "Step 1/6: Preflight checks"

if [[ "$(uname -s)" != "Linux" ]]; then
  log "✗ This script targets Linux. On macOS use scripts/install.py instead."
  exit 1
fi

if [[ ! -f scripts/install-server.sh ]]; then
  log "✗ Run from the ora repo root (where scripts/install-server.sh lives)."
  exit 1
fi

# apt-installable deps; we only sudo if something's missing.
NEEDED_APT=()
command -v python3       >/dev/null || NEEDED_APT+=("python3")
command -v pip3          >/dev/null || NEEDED_APT+=("python3-pip")
python3 -c 'import venv' 2>/dev/null || NEEDED_APT+=("python3-venv")
command -v git           >/dev/null || NEEDED_APT+=("git")
command -v curl          >/dev/null || NEEDED_APT+=("curl")

if (( ${#NEEDED_APT[@]} > 0 )); then
  log "Installing apt packages: ${NEEDED_APT[*]}"
  run "sudo apt-get update -qq"
  run "sudo apt-get install -y ${NEEDED_APT[*]}"
else
  log "  ✓ python3, pip, venv, git, curl already present"
fi

# Python version check (need 3.11+ for current type-hint syntax in some modules).
PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION#*.}"
if (( PY_MAJOR < 3 )) || (( PY_MAJOR == 3 && PY_MINOR < 11 )); then
  log "✗ Python ${PY_VERSION} found; need 3.11+. Install a newer Python."
  exit 1
fi
log "  ✓ python ${PY_VERSION}"

# ─── 2. venv + Python deps ─────────────────────────────────────────────
log "Step 2/6: Virtualenv + Python dependencies"

if [[ ! -d .venv ]]; then
  log "Creating virtualenv at .venv/"
  run "python3 -m venv .venv"
else
  log "  ✓ .venv/ already exists"
fi

# shellcheck source=/dev/null
if (( ! DRY_RUN )); then source .venv/bin/activate; fi

log "Upgrading pip"
run "python3 -m pip install --quiet --upgrade pip"

log "Installing Python deps (Linux subset — no mlx-lm)"
# Pinned-low deps that match the orchestrator's actual usage; no version
# locks because Ora doesn't ship a requirements.txt yet. If a dep breaks
# at a later version, pin here.
DEPS=(
  flask
  flask-cors
  requests
  pyyaml
  jsonschema
  referencing
  pydantic
  chromadb
  python-pptx
  python-docx
  xlsxwriter
  anthropic
  openai
  google-generativeai
)
run "python3 -m pip install --quiet ${DEPS[*]}"
log "  ✓ Installed ${#DEPS[@]} packages"

# ─── 3. ollama for embeddings ──────────────────────────────────────────
log "Step 3/6: ollama (for ChromaDB embeddings)"

if (( SKIP_OLLAMA )); then
  log "  ⊘ --skip-ollama set; skipping ollama install and embedding model pull"
else
  if ! command -v ollama >/dev/null; then
    log "Installing ollama (curl https://ollama.com/install.sh | sh)"
    run "curl -fsSL https://ollama.com/install.sh | sh"
  else
    log "  ✓ ollama already installed"
  fi
  log "Pulling nomic-embed-text embedding model"
  run "ollama pull nomic-embed-text"
fi

# ─── 4. rewrite routing-config.json to API-only slots ─────────────────
log "Step 4/6: Configure API-only slot assignments"

if (( DRY_RUN )); then
  log "  DRY: would rewrite config/routing-config.json::slot_assignments + default_endpoint"
else
  python3 scripts/install_server_config.py
fi

# ─── 5. API keys ───────────────────────────────────────────────────────
log "Step 5/6: API key configuration"

ENV_FILE="${HOME}/.config/ora-server.env"

if (( SKIP_KEY )); then
  log "  ⊘ --skip-key set; assuming OPENROUTER_API_KEY is already configured"
else
  if [[ -f "$ENV_FILE" ]]; then
    log "  ✓ ${ENV_FILE} exists; not overwriting (rm and re-run to change keys)"
  else
    log "  Configuring ${ENV_FILE}"
    mkdir -p "$(dirname "$ENV_FILE")"
    : > "$ENV_FILE"
    chmod 600 "$ENV_FILE"

    if (( ! DRY_RUN )); then
      printf 'OpenRouter API key (starts with sk-or-...): '
      read -rs OPENROUTER_KEY
      echo
      printf 'OPENROUTER_API_KEY=%s\n' "$OPENROUTER_KEY" >> "$ENV_FILE"

      printf 'Anthropic API key (optional, press Enter to skip): '
      read -rs ANTHROPIC_KEY
      echo
      if [[ -n "$ANTHROPIC_KEY" ]]; then
        printf 'ANTHROPIC_API_KEY=%s\n' "$ANTHROPIC_KEY" >> "$ENV_FILE"
      fi
    fi
  fi
fi

# ─── 6. smoke test ─────────────────────────────────────────────────────
log "Step 6/6: Smoke test"

if (( DRY_RUN )); then
  log "  DRY: would run scripts/install_server_smoke.py"
else
  # Load the env file so the smoke test can see the keys.
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    set -a; source "$ENV_FILE"; set +a
  fi
  python3 scripts/install_server_smoke.py
fi

# ─── done ──────────────────────────────────────────────────────────────
cat >&2 <<'EOF'

[install-server] Install complete.

To activate the venv in a future shell:
  source ~/ora/.venv/bin/activate
  set -a; source ~/.config/ora-server.env; set +a

Next steps (manual for now):
  - Configure cron / systemd-timer for the MSI publication cycle.
  - Point the Mac-side vault-sync agent at this server's vault path (see
    Working — Project — Cloud Ora Implementation Plan.md phase (c-finalize)).
  - Verify routing-config.json's slot picks match your cost preferences.

EOF
