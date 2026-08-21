#!/usr/bin/env python3
"""Ora install script (source-install path — Solo public profile).

Solo is the only supported public install profile today. Hybrid and
Organization remain design targets for the future multi-machine /
concurrency work; the script keeps their names reserved so stale docs and
operators get a clear "not yet" message instead of a silent shape change.

Steps the script performs in order:

  1. Pre-flight: Python 3.11+, ≥5GB disk, write perms, and a look at whether
     OpenRouter is answering. An outage there is reported, not fatal, and the
     report states the same policy step 5 implements (CATALOG_OUTAGE_POLICY):
     the install falls back to the catalog packaged with this checkout, and
     halts only if there is no usable one. Also creates the vault when the
     resolved vault path does not exist yet — root plus the folder skeleton
     the runtime reads. An existing vault is reported and left untouched;
     nothing is ever written into one. A creation that fails part-way
     removes the directories it just made, so a re-run never inherits a
     half-built vault.
  2. Python dependencies from requirements.txt, plus the pinned MCP runtime
     and its exact Playwright browser. Falls back to an isolated .venv/ when
     the interpreter is PEP 668 externally managed. The MCP half needs Node
     and npm on PATH and halts the install without them, so they are as much
     a prerequisite as Python is.
  3. Document converters — Ora renders Word (.docx) and PDF by handing its
     markdown to Pandoc, with Typst as the PDF engine. Neither program ships
     in this repository (Pandoc is GPL; vendoring it would be redistribution),
     so scripts/converters.py uses whatever the machine already has and
     otherwise downloads the publishers' own pinned, checksum-verified
     releases into data/converters/bin. No package manager is required. This
     step never halts the install: Word and PDF export are all that depend on
     it, so a failure prints the cause and one retry command and moves on.
  4. Deployment profile selection (Solo today; Hybrid / Organization future)
  5. Catalog refresh — fetches OpenRouter operational fields and writes
     config/model-catalog.json, the file the model picker reads. A copy of
     that catalog ships in the repository, so the refresh makes it current
     rather than bringing it into existence: a refresh that cannot complete
     falls back to the packaged copy, says what is stale about it, and the
     install carries on. It halts here only when no usable catalog exists.
  6. Model-registry sync — fetches OpenRouter + LiteLLM + Chatbot Arena
      and runs the empirical vision-capability probe, writing
      config/model-registry.json. This replaces the prior Artificial
      Analysis (AA) dependency: intelligence rankings come from Chatbot
      Arena's free public dataset, and vision capability is empirically
      verified rather than trusted from any single provider's metadata.
      An optional AA key improves the registry path after install, but it is
      not required for installation.
  7. Auto-populate the user-pipeline configuration from the Budget preset,
     then bake all four presets the Models pane promises — Free, Budget,
     Speed and Premium — through the runtime's own baker. A promised preset
     that does not exist afterwards — or that exists with a model in none of
     its slots, which is the same blank card by another route — halts the
     install, naming which one and why, instead of leaving it for the user
     to find later. The user-pipeline is read back against that same test,
     because the two halves do not resolve the model catalog identically and
     it is the configuration Ora actually serves requests from.
  8. Smoke test: populate a throwaway Free configuration, then make one tiny
     OpenRouter chat round-trip when a key is already available. Without a
     key, the smoke test validates config and tells the user to add keys
     later in Settings → External APIs.
  9. Optional account/API orientation: explain ChatGPT browser sign-in and
     the recommended API-key set, open official provider pages one at a time
     if the user wants them, and print the install-complete summary. The tail
     of ~/ora/install.log lands a deterministic marker the test protocol
     grep-checks.

Design properties:
  - Idempotent: re-run safely; existing state is honored, not clobbered
  - Resumable: completed steps are tracked in ~/ora/install-state.json
  - Verbose by default: every step prints what it's doing
  - Pre-flight gated: fails fast on missing prerequisites
  - --reset rolls back the install state (does NOT delete vault or
     conversations — that's uninstall's job)
  - --dry-run previews actions without making changes

What this script does NOT do yet:
  - Package a double-click installer (download is currently a source install)
  - Support Hybrid / Organization as public profiles (future G1.27+ work)
  - Download local models in the main flow (`install.py models` does that)

Usage:
    python3 scripts/install.py                # interactive install
    python3 scripts/install.py --profile solo # non-interactive
    python3 scripts/install.py --dry-run      # preview, no changes
    python3 scripts/install.py --reset        # clear install state
    python3 scripts/install.py --resume       # continue from last completed step
    python3 scripts/install.py converters     # re-run only the Pandoc/Typst step
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Settle ORA_HOME before the first orchestrator import, by the same rule the
# launchers use and ``_converter_environment`` applies to child processes: a
# setting that names a path wins, and a missing, empty or whitespace-only one
# becomes this clone. ``runtime_paths`` bakes its roots the moment it is
# imported and answers "$HOME/ora" when nobody has set the variable, so an
# installer running from a clone anywhere else would otherwise read and write
# another checkout's presets and catalogs while claiming to install this one.
if not os.environ.get("ORA_HOME", "").strip():
    os.environ["ORA_HOME"] = str(REPO_ROOT)

from orchestrator import network_policy

STATE_PATH = REPO_ROOT / "install-state.json"
LOG_PATH = REPO_ROOT / "install.log"
COMPLETION_MARKER = "INSTALL_COMPLETE: 0 warnings, 0 errors"
# The one line a user retypes when Word/PDF converters did not download.
CONVERTER_RETRY_COMMAND = "python3 scripts/install.py converters"

# ─── What an OpenRouter outage does to the install ───────────────────────
#
# Ora ships a model catalog inside the repository (config/model-catalog.json).
# A fresh clone therefore already knows which models exist, what they cost and
# how they rank; step 5's refresh is how that knowledge becomes *current*, not
# how it comes into existence. Every preset in the Models pane bakes correctly
# from the packaged copy alone, with no network at all.
#
# So the install's answer to a provider outage is written once, here, and
# quoted by both pre-flight and step 5 — the two used to disagree, pre-flight
# calling an outage survivable and step 5 halting the install on it.
CATALOG_OUTAGE_POLICY = (
    "An unreachable OpenRouter does not stop the install: step 5 falls back to "
    "the model catalog packaged with this checkout. The install halts there "
    "only if that packaged catalog is missing or unusable."
)
# The one line a user retypes to get a current catalog once the network is back.
CATALOG_REFRESH_RETRY_COMMAND = "python3 scripts/refresh-catalog.py"


def _catalog_path() -> Path:
    """The catalog file everyone in this chain agrees on.

    ``refresh-catalog.py`` writes it, ``auto-populate-configuration.py`` reads
    it and the runtime's preset baker reads it, and all three honor
    ``ORA_MODEL_CATALOG_PATH``. Resolving it the same way here is what lets
    pre-flight and step 5 talk about the same file the refresh would replace.
    """
    override = os.environ.get("ORA_MODEL_CATALOG_PATH", "").strip()
    return Path(override) if override else REPO_ROOT / "config" / "model-catalog.json"


def _catalog_baseline(path: Path | None = None) -> tuple[bool, str]:
    """Is there a usable model catalog on disk, and what is in it?

    Returns ``(usable, description)``. "Usable" is deliberately the low bar
    the rest of the install actually needs — a readable JSON object holding at
    least one model with an id — because that is the whole of what the model
    picker requires to fill a preset. The description is one plain line for
    the install log: what the catalog holds and how old it is when it can be
    used, and the exact reason it cannot be when it cannot.

    ``path`` says which catalog to describe, and defaults to the one the
    picker CLI reads. Step 7's preset half hands in the baker's own resolved
    path instead: a message about picks that came out empty has to describe
    the file those picks actually came from, and on a machine with a runtime
    overlay that is not the same file.
    """
    path = _catalog_path() if path is None else path
    if not path.exists():
        return False, f"there is no catalog at {path}"
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return False, (
            f"the catalog at {path} could not be read "
            f"({type(exc).__name__}: {exc})"
        )
    models = (data or {}).get("models") if isinstance(data, dict) else None
    if not isinstance(models, list) or not models:
        return False, f"the catalog at {path} lists no models"
    usable = [
        m for m in models
        if isinstance(m, dict) and str(m.get("id") or "").strip()
    ]
    if not usable:
        return False, f"no entry in the catalog at {path} carries a model id"
    free = sum(1 for m in usable if m.get("is_free"))
    scored = sum(1 for m in usable if m.get("aa_intelligence_index") is not None)
    refreshed = str((data.get("_refreshed_at") or "")).strip() or "an unrecorded date"
    return True, (
        f"{len(usable)} models ({free} free, {scored} with an intelligence "
        f"score), last refreshed {refreshed}"
    )


def _log_catalog_outage_policy() -> None:
    """State the outage policy and where this checkout stands under it.

    Pre-flight calls this to predict what step 5 will do; step 5 runs the same
    baseline check to do it. One statement from one place, so an install can
    never promise a survivable outage and then halt on one.
    """
    log(f"    {CATALOG_OUTAGE_POLICY}")
    usable, description = _catalog_baseline()
    if usable:
        log(f"    This checkout's packaged catalog is usable: {description}.")
    else:
        log(f"    This checkout has no usable catalog to fall back on: {description}.")
        log("    If the refresh cannot complete, step 5 will halt the install.")


DEPLOYMENT_PROFILES = {
    "solo": {
        "description": "Supported public source install. Single user, local models where available, optional OpenRouter/API fallback.",
        "supported_now": True,
        "local_models": True,
        # 0 = unbounded API concurrency (Solo expects no API endpoints; if
        # one is added, no cap is the right fallback so calls don't deadlock)
        "api_pool_size": 0,
    },
    "hybrid": {
        "description": "Future multi-machine / local-plus-API profile. Reserved until G1.27 network discovery and concurrency validation land.",
        "supported_now": False,
        "local_models": True,
        "api_pool_size": 8,
    },
    "organization": {
        "description": "Future shared / API-pool deployment profile. Reserved until the organization concurrency path is tested.",
        "supported_now": False,
        "local_models": False,
        "api_pool_size": 32,
    },
}

PREFLIGHT_MIN_PYTHON = (3, 11)
PREFLIGHT_MIN_DISK_GB = 5

# The folder skeleton a brand-new vault needs, expressed as path segments
# below the resolved vault root.
#
# This is the set the runtime actually reads or watches, not a tidy-looking
# copy of the author's vault:
#   Projects/Ora   — runtime_paths.VAULT_ORA; the Problem Evolution framework,
#                    the Trusted Web Sources registry and the periodic-
#                    maintenance control doc are all read from here.
#   Sessions       — conversation_closeout._DEFAULT_VAULT_SESSIONS and the
#                    vault_export destination.
#   Engrams        — knowledge_index / engram_promotion root, and one of the
#                    two collections runtime_event_dispatcher classifies.
#   Resources      — resources_watcher's reading copy, and the other
#                    dispatcher-classified collection.
#   Administration — canonical Master Matrix location (vault_export).
#
# Deliberately absent: Archive / Workshop / Templates / Modes / Lenses appear
# in the code only inside skip-lists and maturity tables — nothing reads or
# writes them. Incubator, Matrix, Corpus Instances and Daily Notes are each
# created by their own writer on first use (document_input carries an explicit
# comment saying the Incubator must not be assumed to exist on a fresh
# install). MSI News belongs to a project plugin, not to Ora.
VAULT_SKELETON: tuple[tuple[str, ...], ...] = (
    ("Projects", "Ora"),
    ("Sessions",),
    ("Engrams",),
    ("Resources",),
    ("Administration",),
)

# Import name -> pip distribution.  The Solo source installer does not mutate
# an existing Python environment; it fails preflight with one exact install
# command instead of letting the runtime watcher discover a missing converter
# after the user drops a document into Ora Resources.
DOCUMENT_CONVERSION_DEPENDENCIES = {
    "pdfplumber": "pdfplumber",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "openpyxl": "openpyxl",
    "markdownify": "markdownify",
    "bs4": "beautifulsoup4",
    "striprtf": "striprtf",
}
MCP_RUNTIME_DIR = REPO_ROOT / "mcp-runtime"
MCP_RUNTIME_PACKAGES = {
    "@modelcontextprotocol/server-filesystem": "2026.7.10",
    "@playwright/mcp": "0.0.79",
    "@modelcontextprotocol/server-github": "2025.4.8",
}


def _converter_environment() -> dict[str, str]:
    """The child environment for ``scripts/converters.py``, ``ORA_HOME`` settled.

    ``converters.py`` asks ``runtime_paths`` where Ora's home is, and that
    answer picks the directory the downloaded Pandoc and Typst land in. The
    running server never asks — ``run-ora-server.sh``, ``start.sh`` and
    ``start.bat`` each decide for themselves, by one rule: an ``ORA_HOME``
    that actually names something wins, and anything else falls back to the
    checkout the launcher itself lives in.

    This helper applies that rule by the same test the launchers use, so the
    installer writes where the server reads in *every* case rather than only
    the common one:

    * **``ORA_HOME`` naming a path** — left exactly as it is, because the
      launchers honor it and the server really will read from there.
    * **``ORA_HOME`` missing, empty, or nothing but whitespace** — replaced
      with this clone, because that is what the launchers fall back to.
      ``${ORA_HOME:-$SCRIPT_DIR}`` counts an exported-but-empty value as no
      value at all, and ``runtime_paths`` strips a setting before deciding
      whether anybody set one, so a blank ``ORA_HOME`` names a home for
      nobody. Passed through blank it would not stay blank for long:
      ``runtime_paths`` would answer ``$HOME/ora``, and a clone that is not at
      ``~/ora`` would have its converters downloaded into a directory the
      server never looks in — the installer reporting Word and PDF ready while
      the toolbar kept them greyed out.

    Wherever a launcher will start a server, then, the installer downloads
    into the directory that server reads from. (Whitespace alone starts no
    server anywhere: the launchers reject it as "not a directory" before any
    Python runs, so there is no reading side left to disagree with, and the
    clone is the only answer left that is any use.)

    Overriding rather than following would only turn that failure around
    instead of removing it: the launcher would honor the user's ``ORA_HOME``
    while the installer wrote into the clone, and the toolbar would stay
    exactly as grey.
    """
    env = os.environ.copy()
    if not env.get("ORA_HOME", "").strip():
        env["ORA_HOME"] = str(REPO_ROOT)
    return env


def _missing_document_dependencies() -> list[str]:
    return [
        distribution
        for module, distribution in DOCUMENT_CONVERSION_DEPENDENCIES.items()
        if importlib.util.find_spec(module) is None
    ]

EXTERNAL_API_GROUPS = [
    {
        "title": "Recommended minimal package",
        "providers": [
            {
                "name": "OpenRouter",
                "url": "https://openrouter.ai/settings/keys",
                "cost": "free models available; paid/usage-based models require credits",
                "why": "opens the broad cloud-model catalog and avoids relying only on rate-limited free models",
            },
            {
                "name": "Tavily",
                "url": "https://app.tavily.com/",
                "cost": "free tier, then usage-based plans",
                "why": "gives Ora a search API built for AI agents and RAG workflows",
            },
            {
                "name": "Artificial Analysis",
                "url": "https://artificialanalysis.ai/api-key-management-redirect",
                "cost": "free model-benchmark API; commercial data exists separately",
                "why": "improves model-selector intelligence with independent benchmark and provider data",
            },
        ],
    },
    {
        "title": "Additional search options",
        "providers": [
            {
                "name": "Exa",
                "url": "https://dashboard.exa.ai/api-keys",
                "cost": "trial/free credits, then usage-based",
                "why": "adds semantic web search when Tavily is not the best fit",
            },
            {
                "name": "Brave Search API",
                "url": "https://api-dashboard.search.brave.com/app/keys",
                "cost": "monthly free credits, then usage-based",
                "why": "adds an independent web-search source for the search cascade",
            },
        ],
    },
    {
        "title": "Direct model-provider keys",
        "providers": [
            {
                "name": "Anthropic",
                "url": "https://platform.claude.com/settings/keys",
                "cost": "usually usage-based; provider terms vary",
                "why": "direct Claude API access when you want to skip OpenRouter's gateway markup",
            },
            {
                "name": "OpenAI",
                "url": "https://platform.openai.com/api-keys",
                "cost": "usage-based",
                "why": "direct OpenAI API access for chat, vision, and OpenAI speech/image features",
            },
            {
                "name": "Google Gemini",
                "url": "https://aistudio.google.com/app/apikey",
                "cost": "free tier for some models, paid tier varies by use",
                "why": "direct Gemini API access when Google models are the best fit",
            },
            {
                "name": "Mistral AI",
                "url": "https://console.mistral.ai/api-keys",
                "cost": "usage-based",
                "why": "direct Mistral API access and OpenAI-compatible routing",
            },
            {
                "name": "DeepSeek",
                "url": "https://platform.deepseek.com/api_keys",
                "cost": "usage-based",
                "why": "direct DeepSeek API access and OpenAI-compatible routing",
            },
            {
                "name": "Alibaba Qwen",
                "url": "https://modelstudio.console.alibabacloud.com/?tab=playground#/api-key",
                "cost": "usage-based",
                "why": "direct Qwen/DashScope API access and OpenAI-compatible routing",
            },
        ],
    },
    {
        "title": "Speech, image, video, and speed-specialist APIs",
        "providers": [
            {
                "name": "AssemblyAI",
                "url": "https://www.assemblyai.com/dashboard/signup",
                "cost": "free trial or usage-based plans vary",
                "why": "optional cloud transcription when local Whisper is not enough",
            },
            {
                "name": "Deepgram",
                "url": "https://console.deepgram.com/signup",
                "cost": "free trial or usage-based plans vary",
                "why": "optional low-latency cloud transcription",
            },
            {
                "name": "ElevenLabs",
                "url": "https://elevenlabs.io/app/settings/api-keys",
                "cost": "free tier or usage-based plans vary",
                "why": "higher-quality text-to-speech than local macOS speech",
            },
            {
                "name": "Stability AI",
                "url": "https://platform.stability.ai/account/keys",
                "cost": "usage-based image generation",
                "why": "optional image and video generation backends for visual workflows",
            },
            {
                "name": "Replicate",
                "url": "https://replicate.com/account/api-tokens",
                "cost": "usage-based model hosting",
                "why": "long-tail image, video, and specialist model access",
            },
            {
                "name": "Tensor.Art",
                "url": "https://tams.tensor.art/apps",
                "cost": "usage-based image generation",
                "why": "optional image generation backend",
            },
        ],
    },
]


# ─── State + logging ─────────────────────────────────────────────────────


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"steps_completed": [], "profile": None, "started_at": None}
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"steps_completed": [], "profile": None, "started_at": None}


def save_state(state: dict, dry_run: bool = False) -> None:
    if dry_run:
        return
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def log(msg: str, dry_run: bool = False) -> None:
    """Print and append to install.log atomically per line."""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if dry_run:
        return
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def reset_install(dry_run: bool) -> None:
    if dry_run:
        log("[dry-run] would clear install-state.json and install.log")
        return
    for p in (STATE_PATH, LOG_PATH):
        if p.exists():
            p.unlink()
    log("Install state cleared. Vault, conversations, and downloaded models untouched.")


def _undo_created_vault(vault: Path, created: list[Path]) -> None:
    """Remove exactly the directories this run just made, deepest first.

    A half-made vault is worse than no vault: the root exists, so the next
    ``--resume`` takes the "found existing" branch, reports the vault as
    somebody's real work and installs on top of an incomplete skeleton.

    This is a deletion, so every step answers the same question — could it
    reach something this run did not create?

      * ``created`` is appended to only after a directory was made by this
        call, and only when the vault root did not exist when the call began;
        the "found existing" branch returns long before it is populated.
      * Each entry must be the recorded root itself or sit under it.
      * A symlink is never removed and never followed.
      * ``rmdir`` deletes empty directories only. A folder holding anything
        this run did not put there refuses to go, which is the answer we
        want: stop and report, rather than delete somebody's content.

    Anything that stops the removal is left exactly where it is and named in
    the log, so the operator can look at it before re-running.

    Nothing above the vault root is ever touched. A missing parent directory
    on the way to the vault is created along with it and then left: it is
    shared ground, and an empty folder that is not the vault path is not
    something a later run can mistake for a vault.
    """
    if not created:
        return
    for path in reversed(created):
        if path != vault and vault not in path.parents:
            log(f"  ⚠ Left {path} alone: it is not inside the vault this run created")
            return
        if path.is_symlink():
            log(f"  ⚠ Left {path} alone: it is a symlink, not a directory this run created")
            return
        if not path.exists():
            continue
        try:
            path.rmdir()
        except OSError as exc:
            log(
                f"  ⚠ Could not remove {path}: {exc}. Left in place — check it "
                "before re-running the installer."
            )
            return
    log(f"  ✓ Removed the partial vault this run created at {vault}")


def _ensure_vault(vault: Path, dry_run: bool) -> bool:
    """Create a missing vault; leave an existing one completely alone.

    An existing vault is somebody's real work. This never writes into one —
    not even to add a skeleton folder it happens to be missing — because a
    "repair" here is indistinguishable from damage. Only the case where there
    is no vault at all is ours to act on.

    Returns False when creation was attempted and failed, so the caller halts
    the install instead of reporting success into a product that cannot load.
    A failure part-way through takes the half-built vault with it, so the next
    run starts from the same clean state this one did.
    """
    if vault.exists():
        log(f"  ✓ Vault found at {vault} — left exactly as it is")
        return True

    folders = ", ".join("/".join(segments) for segments in VAULT_SKELETON)
    if dry_run:
        log(f"  [dry-run] would create the vault at {vault} ({folders})")
        return True

    created: list[Path] = []
    try:
        from orchestrator import runtime_paths as rp
        # Claim the root first and on its own, so a later failure has an
        # exact, complete list of what this run made. ``exist_ok`` is
        # deliberately off: if something has appeared at this path since the
        # check above, it is not ours to create — and so never ours to remove.
        vault.mkdir(parents=True)
        created.append(vault)
        # One level per call, so each success records one directory. The
        # skeleton's only nested entry is Projects/Ora; walking the prefixes
        # keeps the parent recorded separately from the child.
        for segments in VAULT_SKELETON:
            for depth in range(1, len(segments) + 1):
                branch = segments[:depth]
                if vault.joinpath(*branch).exists():
                    continue
                created.append(rp.safe_owned_subdir(vault, *branch, create=True))
    except Exception as exc:
        log(f"  ✗ Could not create the vault at {vault}: {exc}")
        _undo_created_vault(vault, created)
        return False

    log(f"  ✓ Created vault at {vault} ({folders})")
    return True


def _runtime_path_preflight(dry_run: bool) -> bool:
    """Resolve and report every user-storage root before install work starts."""
    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from orchestrator import runtime_paths as rp
        roots = rp.resolve_runtime_roots()
    except Exception as exc:
        log(f"  ✗ Runtime path configuration is invalid: {exc}")
        return False

    # Ora home first, and its source with it. An ORA_HOME nobody set — or
    # one set to nothing at all, which counts the same everywhere — is not
    # "unconfigured", it is "$HOME/ora" — so on any clone that is not at
    # ~/ora this line and the clone below it disagree, and every root derived
    # from Ora home follows the reported value rather than the checkout. That
    # silent disagreement is what sent the downloaded converters to a
    # directory the server never reads; reporting it makes it visible.
    log(f"  ✓ Ora home: {roots.ora_home} ({roots.sources['ora_home']})")
    log(f"    This clone: {REPO_ROOT}")
    if os.path.normcase(os.path.realpath(str(roots.ora_home))) != os.path.normcase(
        os.path.realpath(str(REPO_ROOT))
    ):
        log("    ⚠ Ora home is not this clone.")
        if roots.sources["ora_home"] == "ORA_HOME":
            # This branch is a home that names a path: a blank ORA_HOME
            # never reaches it, because runtime_paths discounts one. The
            # launchers honor a real setting, so the server reads from there,
            # and _converter_environment keeps it by the same test, so that is
            # where the converters install too. The disagreement left to
            # report is with the clone, not between the installer and the
            # server. Say so plainly, because running Ora out of a
            # directory that is not the checkout you installed from is worth
            # knowing either way.
            log("      ORA_HOME is set explicitly and the launchers honor it, "
                "so the running")
            log("      server reads from there, not from this clone. The "
                "Word/PDF converters")
            log("      install there too, so export will work — but every "
                "other root follows")
            log("      ORA_HOME as well. Unset it, or point it at this clone, "
                "if you meant to")
            log("      run Ora out of the checkout you are installing from.")
        else:
            log("      Nothing usable set ORA_HOME — it is unset, or set to "
                "nothing — so it")
            log("      defaults to $HOME/ora. But start.sh, start.bat and "
                "run-ora-server.sh read")
            log("      a blank one as no setting too, and export the checkout "
                "they live in, so")
            log("      the running server uses this clone. The Word/PDF "
                "converters install here")
            log("      to match, blank ORA_HOME included. Set ORA_HOME to this "
                "clone to make")
            log("      every other root agree as well.")
    log(f"  ✓ Documents: {roots.documents} ({roots.sources['documents']})")
    for label, path, source_key in (
        ("Vault", roots.vault, "vault"),
        ("Conversations", roots.conversations, "conversations"),
        ("Historical archive", roots.historical_archive, "historical_archive"),
        ("ChromaDB", roots.chromadb, "chromadb"),
    ):
        log(f"    {label}: {path} ({roots.sources[source_key]})")
    for warning in roots.warnings:
        log(f"  ⚠ {warning}")

    documents = roots.documents
    if not documents.is_dir():
        log(
            f"  ✗ Resolved Documents directory does not exist: {documents}. "
            "Set ORA_DOCUMENTS to the real location."
        )
        return False
    if dry_run:
        log(f"  [dry-run] would verify write permission at {documents}")
    else:
        probe_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=".ora-install-write-", dir=documents, delete=False
            ) as probe:
                probe_path = Path(probe.name)
            probe_path.unlink()
        except OSError as exc:
            if probe_path is not None:
                try:
                    probe_path.unlink()
                except OSError:
                    pass
            log(f"  ✗ Cannot write to resolved Documents directory {documents}: {exc}")
            return False
        log(f"  ✓ Write permission at resolved Documents directory {documents}")

    if roots.vault.exists() and not roots.vault.is_dir():
        log(f"  ✗ Resolved vault path exists but is not a directory: {roots.vault}")
        return False
    return _ensure_vault(roots.vault, dry_run)


# ─── Steps ───────────────────────────────────────────────────────────────


def step_preflight(state: dict, dry_run: bool) -> bool:
    log("Step 1/9: Pre-flight checks")
    ok = _runtime_path_preflight(dry_run)

    # Python version
    if sys.version_info < PREFLIGHT_MIN_PYTHON:
        log(f"  ✗ Python {'.'.join(map(str, PREFLIGHT_MIN_PYTHON))}+ required; you have {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        ok = False
    else:
        log(f"  ✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    missing_conversion = _missing_document_dependencies()
    if missing_conversion:
        # Not fatal: step 2 installs everything in requirements.txt. Halting
        # here is what made the published install path unusable on a clean
        # machine — the checker reported the gap and then refused to close it.
        log("  · Document-conversion dependencies not yet present: "
            + ", ".join(missing_conversion))
        log("    Step 2 will install these from requirements.txt.")
    else:
        log("  ✓ Document conversion dependencies importable")

    # Disk space
    try:
        free_bytes = shutil.disk_usage(REPO_ROOT).free
        free_gb = free_bytes / (1024 ** 3)
        if free_gb < PREFLIGHT_MIN_DISK_GB:
            log(f"  ✗ {PREFLIGHT_MIN_DISK_GB}GB free disk required; {free_gb:.1f}GB available at {REPO_ROOT}")
            ok = False
        else:
            log(f"  ✓ Disk space: {free_gb:.1f}GB free")
    except OSError as exc:
        log(f"  ⚠ Disk space check failed: {exc}")

    # OpenRouter reachable.
    #
    # A bad answer here is a warning rather than a failure, and the warning
    # states the policy step 5 actually implements — both come from
    # CATALOG_OUTAGE_POLICY, so the prediction and the behavior are one thing.
    try:
        req = urllib.request.Request("https://openrouter.ai/api/v1/models", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                log("  ✓ OpenRouter API reachable (no auth needed for catalog)")
            else:
                log(f"  ⚠ OpenRouter returned status {resp.status}; the step 5 catalog refresh may not complete")
                _log_catalog_outage_policy()
    except (urllib.error.URLError, OSError) as exc:
        log(f"  ⚠ Cannot reach OpenRouter ({exc})")
        _log_catalog_outage_policy()

    # Write perms
    try:
        test_path = REPO_ROOT / ".install-write-test"
        test_path.write_text("")
        test_path.unlink()
        log(f"  ✓ Write permission at {REPO_ROOT}")
    except (OSError, PermissionError) as exc:
        log(f"  ✗ Cannot write to {REPO_ROOT}: {exc}")
        ok = False

    if ok and not dry_run:
        state["steps_completed"].append("preflight")
        save_state(state)
    return ok


def step_dependencies(state: dict, dry_run: bool) -> bool:
    """Install Ora's Python dependencies from requirements.txt.

    Without this the published install path cannot produce a working Ora:
    server/app.py imports flask, requests, chromadb, keyring, openai and yaml
    at module scope, and nothing else in the repo installs them.
    """
    log("Step 2/9: Python dependencies")
    req = REPO_ROOT / "requirements.txt"
    if not req.exists():
        log(f"  ✗ {req} not found — cannot install dependencies")
        return False

    if os.name == "nt":
        venv_python = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        venv_python = REPO_ROOT / ".venv" / "bin" / "python3"
    target = sys.executable
    cmd = [target, "-m", "pip", "install", "-r", str(req)]
    if dry_run:
        log(f"  [dry-run] would run: {' '.join(cmd)}")
        log("  [dry-run] would fall back to a .venv/ if the interpreter is PEP 668 externally managed")
        return _install_mcp_runtime(dry_run=True)

    log(f"  · {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.returncode != 0 and "externally-managed-environment" in (proc.stderr or ""):
        # Homebrew and most distro Pythons are PEP 668 externally managed.
        # --user is blocked too, and --break-system-packages can damage the
        # host Python, so create an isolated venv — the same thing
        # scripts/install-server.sh does on Linux. run-ora-server.sh prefers
        # this .venv automatically.
        log("  ⚠ Interpreter is externally managed (PEP 668) — creating an isolated .venv/")
        if not venv_python.exists():
            mk = subprocess.run([sys.executable, "-m", "venv", str(REPO_ROOT / ".venv")],
                                capture_output=True, text=True)
            if mk.returncode != 0:
                log("  ✗ Could not create .venv/:")
                for line in (mk.stderr or "").strip().splitlines()[-4:]:
                    log(f"      {line}")
                return False
        target = str(venv_python)
        cmd = [target, "-m", "pip", "install", "-r", str(req)]
        log(f"  · {' '.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.returncode != 0:
        log("  ✗ pip install failed:")
        for line in (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]:
            log(f"      {line}")
        log(f"    Retry manually: {' '.join(cmd)}")
        return False

    # Verify in a fresh interpreter — packages installed into a venv or a user
    # site dir that did not exist at startup are not importable in-process.
    probe = "import flask, requests, chromadb, keyring, openai, yaml"
    check = subprocess.run([target, "-c", probe], capture_output=True, text=True)
    if check.returncode != 0:
        log("  ✗ Core imports still failing after install:")
        tail = (check.stderr or "").strip().splitlines()
        log(f"      {tail[-1] if tail else 'unknown error'}")
        return False

    log(f"  ✓ Dependencies installed and core imports verified ({target})")
    if target != sys.executable:
        log("    Ora will start against this .venv/ automatically.")
    if not _install_mcp_runtime(dry_run=False):
        return False
    state["steps_completed"].append("dependencies")
    save_state(state)
    return True


def _install_mcp_runtime(*, dry_run: bool) -> bool:
    """Install the exact repository lock and its matching Playwright browser."""

    npm = shutil.which("npm")
    node = shutil.which("node")
    lock = MCP_RUNTIME_DIR / "package-lock.json"
    if not npm or not node:
        log("  ✗ Node.js and npm are required for the three shipped MCP servers")
        return False
    if not lock.is_file():
        log(f"  ✗ {lock} not found — MCP runtime lock is unavailable")
        return False
    base = [npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"]
    offline = [*base, "--offline"]
    if dry_run:
        log(f"  [dry-run] would run from {MCP_RUNTIME_DIR}: {' '.join(offline)}")
        log("  [dry-run] would retry the same exact lock without --offline only if the cache is incomplete")
        cli = MCP_RUNTIME_DIR / "node_modules" / "playwright-core" / "cli.js"
        log(f"  [dry-run] would run: {node} {cli} install chromium (PLAYWRIGHT_BROWSERS_PATH=0)")
        return True
    proc = subprocess.run(offline, cwd=MCP_RUNTIME_DIR,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        log("  ⚠ Local npm cache is incomplete; installing the same exact lock from its registry URLs")
        proc = subprocess.run(base, cwd=MCP_RUNTIME_DIR,
                              capture_output=True, text=True)
    if proc.returncode != 0:
        log("  ✗ Pinned MCP runtime install failed:")
        for line in (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]:
            log(f"      {line}")
        return False
    for package, expected in MCP_RUNTIME_PACKAGES.items():
        metadata = MCP_RUNTIME_DIR / "node_modules" / package / "package.json"
        try:
            actual = str(json.loads(metadata.read_text(encoding="utf-8"))["version"])
        except Exception:
            log(f"  ✗ Installed MCP package metadata is missing: {package}")
            return False
        if actual != expected:
            log(f"  ✗ Installed MCP package version mismatch: {package} {actual} != {expected}")
            return False
    cli = MCP_RUNTIME_DIR / "node_modules" / "playwright-core" / "cli.js"
    if not cli.is_file():
        log("  ✗ Locked Playwright CLI is missing after npm ci")
        return False
    browser_env = dict(os.environ)
    browser_env["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    browser_cmd = [node, str(cli), "install", "chromium"]
    browser_install = subprocess.run(
        browser_cmd, cwd=MCP_RUNTIME_DIR, env=browser_env,
        capture_output=True, text=True,
    )
    if browser_install.returncode != 0:
        log("  ✗ Exact locked Playwright Chromium install failed:")
        for line in (browser_install.stderr or browser_install.stdout or "").strip().splitlines()[-8:]:
            log(f"      {line}")
        return False
    core = MCP_RUNTIME_DIR / "node_modules" / "playwright-core"
    probe = subprocess.run(
        [node, "-e", (
            "const {chromium}=require(process.argv[1]);"
            "process.stdout.write(chromium.executablePath())"
        ), str(core)],
        cwd=MCP_RUNTIME_DIR, env={"PLAYWRIGHT_BROWSERS_PATH": "0"},
        capture_output=True, text=True,
    )
    browser = Path((probe.stdout or "").strip()).resolve()
    local_root = (core / ".local-browsers").resolve()
    if (probe.returncode != 0 or not browser.is_file()
            or local_root not in browser.parents):
        log("  ✗ Exact locked Playwright Chromium is unavailable after install")
        return False
    log("  ✓ Pinned MCP runtime and exact Playwright Chromium installed")
    return True


def step_converters(state: dict, dry_run: bool) -> bool:
    """Make Word and PDF export work on a machine that has no converters.

    Ora renders those two formats by handing its markdown to Pandoc, with
    Typst as the PDF engine. ``scripts/converters.py`` uses whatever the
    machine already has and downloads the publishers' pinned releases when it
    has nothing — no Homebrew, WinGet or Chocolatey required.

    This step never halts the install. Export to Word and PDF is the only
    thing that depends on it, so a failed download costs the user those two
    formats and nothing else; the cause and the retry command are printed and
    the install carries on. The step is not recorded as completed unless it
    succeeded, so ``--resume`` picks it up again.

    The child resolves ``ORA_HOME`` by the launchers' own rule — a setting
    that names a path wins, and a missing, empty or whitespace-only one falls
    back to this clone, which is what ``${ORA_HOME:-$SCRIPT_DIR}`` does too;
    see ``_converter_environment`` — so the converters land where the
    launchers make the server look, whatever ``ORA_HOME`` happens to hold.
    """
    log("Step 3/9: Document converters (Pandoc + Typst, for Word/PDF export)")
    script = REPO_ROOT / "scripts" / "converters.py"
    if not script.exists():
        log(f"  ⚠ {script} missing — Word and PDF export stay unavailable")
        return True
    cmd = [sys.executable, str(script)]
    if dry_run:
        log(f"  [dry-run] would run: {' '.join(cmd)}")
        return True

    try:
        result = subprocess.run(
            cmd, cwd=str(REPO_ROOT), env=_converter_environment(),
            capture_output=True, text=True, timeout=1800,
        )
    except subprocess.TimeoutExpired:
        log("  ⚠ Converter provisioning timed out after 30 minutes")
        log("    Word (.docx) and PDF export stay unavailable; nothing else is affected.")
        log(f"    Retry with: {CONVERTER_RETRY_COMMAND}")
        return True

    for line in (result.stdout or "").strip().splitlines():
        log(f"  {line}")
    if result.returncode != 0:
        for line in (result.stderr or "").strip().splitlines()[-6:]:
            log(f"      {line}")
        log("  ⚠ Converters were not fully provisioned. The install continues:")
        log("    only Word (.docx) and PDF export are affected, and re-running the")
        log("    line below fixes them without re-running the whole install.")
        log(f"    Retry with: {CONVERTER_RETRY_COMMAND}")
        return True

    state["steps_completed"].append("converters")
    save_state(state)
    return True


def step_select_profile(state: dict, profile: str | None, dry_run: bool) -> bool:
    log("Step 4/9: Deployment profile selection")
    if profile is None:
        if sys.stdin.isatty():
            print()
            print("  Available profiles:")
            for name, info in DEPLOYMENT_PROFILES.items():
                supported = "✓" if info["supported_now"] else "(coming soon)"
                print(f"    {name:12s} {supported:14s} {info['description']}")
            print()
            chosen = input("  Pick a profile [solo]: ").strip().lower() or "solo"
        else:
            log("  Non-interactive run with no --profile flag; defaulting to 'solo'")
            chosen = "solo"
    else:
        chosen = profile.lower()

    if chosen not in DEPLOYMENT_PROFILES:
        log(f"  ✗ Unknown profile {chosen!r}; expected one of {list(DEPLOYMENT_PROFILES)}")
        return False

    if not DEPLOYMENT_PROFILES[chosen]["supported_now"]:
        log(f"  ✗ Profile {chosen!r} is reserved for future Ora installs, not supported today.")
        log("    Use 'solo' for the public source-install path. Hybrid / Organization")
        log("    return after G1.27 network discovery and concurrency validation.")
        return False

    log(f"  ✓ Profile selected: {chosen}")
    if not dry_run:
        state["profile"] = chosen
        state["steps_completed"].append("profile")
        save_state(state)
    return True


def _prompt_yes_no(prompt: str, default: bool = False) -> bool:
    """Interactive yes/no helper. Non-interactive callers should not use it."""
    suffix = " [Y/n]: " if default else " [y/N]: "
    answer = input(prompt + suffix).strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def _try_keyring_get(username: str) -> str:
    try:
        import keyring  # type: ignore
        return (keyring.get_password("ora", username) or "").strip()
    except Exception:
        return ""


def _openrouter_key() -> str:
    return (
        os.environ.get("OPENROUTER_API_KEY", "").strip()
        or _try_keyring_get("openrouter-api-key")
    )


def _open_provider_page(url: str) -> bool:
    try:
        return bool(webbrowser.open_new_tab(url))
    except Exception:
        return False


def _catalog_refresh_fallback(state: dict, reason: str) -> bool:
    """Apply the outage policy after a refresh that did not complete.

    Returns True when the install may carry on against the catalog already in
    the checkout, False when there is nothing to carry on with. Either way the
    reason the refresh failed is printed once, in full, so nobody has to guess
    whether it was the network, the script or the machine.
    """
    log(f"  ⚠ Catalog refresh did not complete — {reason}")
    usable, description = _catalog_baseline()
    if not usable:
        log(f"  ✗ There is no catalog to fall back on: {description}.")
        log("    Every later step picks models out of that file, so the install")
        log("    cannot produce a working configuration without it. Restore")
        log("    config/model-catalog.json (a clean clone ships one), then re-run")
        log("    with --resume.")
        return False
    log(f"  ✓ Continuing on the catalog packaged with this checkout: {description}.")
    log("    What this costs you: models released since that date are missing, and")
    log("    prices, context windows and rankings are as of that date. Nothing else")
    log("    changes — presets, the user pipeline and the smoke test all bake from")
    log("    this file exactly as they would from a fresh one.")
    log(f"    When the network is back, run: {CATALOG_REFRESH_RETRY_COMMAND}")
    state["steps_completed"].append("catalog")
    save_state(state)
    return True


def step_catalog_refresh(state: dict, dry_run: bool) -> bool:
    """Bring config/model-catalog.json up to date from OpenRouter.

    The refresh is how the catalog becomes current; it is not how the catalog
    comes to exist. One ships in the repository, and it is enough on its own to
    fill every preset and the user pipeline.

    So this step follows CATALOG_OUTAGE_POLICY, the same statement pre-flight
    prints: a refresh that cannot complete — no network, a provider outage, a
    missing script, a timeout — falls back to the packaged catalog and says
    plainly what is stale about it. The install stops here only when there is
    no usable packaged catalog to fall back on, and it says which of those two
    it is rather than reporting one failure as the other.
    """
    log("Step 5/9: Catalog refresh (OpenRouter operational fields)")
    log("")

    # Artificial Analysis intelligence-index check.
    #
    # AA enriches the model catalog with intelligence rankings. The
    # auto-populate engine walks the catalog with a Pareto +
    # percentage-floor + cost-sort algorithm. With no intelligence_index
    # field on catalog entries, every model scores the same on
    # "capability" and the algorithm falls through to pure cost sort —
    # meaning auto-populate will pick the cheapest model per slot
    # regardless of how capable it actually is. That is almost certainly
    # not what you want for production pipelines.
    # Intelligence rankings come from scripts/sync_model_registry.py
    # (OpenRouter + Chatbot Arena + Artificial Analysis), called below.
    # No key is required: AA data defaults to their public website; an
    # AA key (keyring 'ora/aa-api-key' or AA_API_KEY env) auto-switches
    # the sync to AA's official API.

    if dry_run:
        log("  [dry-run] would run scripts/refresh-catalog.py")
        log(f"  [dry-run] if that refresh could not complete: {CATALOG_OUTAGE_POLICY}")
        return True
    script = REPO_ROOT / "scripts" / "refresh-catalog.py"
    if not script.exists():
        return _catalog_refresh_fallback(
            state, f"{script} is missing from this checkout")
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return _catalog_refresh_fallback(
            state, "scripts/refresh-catalog.py did not finish within 120s")
    if result.returncode == 0:
        log("  ✓ Catalog refresh succeeded")
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                log(f"    {line}")
        state["steps_completed"].append("catalog")
        save_state(state)
        return True
    detail = (result.stderr or result.stdout or "").strip().splitlines()
    reason = f"scripts/refresh-catalog.py exited {result.returncode}"
    if detail:
        reason += f" — {detail[-1].strip()}"
    return _catalog_refresh_fallback(state, reason)


def step_model_registry_sync(state: dict, dry_run: bool) -> bool:
    """Populate config/model-registry.json from OpenRouter + LiteLLM +
    Chatbot Arena, then run the empirical vision-capability probe.

    The registry is the runtime source of truth for model capabilities
    (vision_capable, intelligence_score, context_length). Boot.py reads
    it via orchestrator/model_registry.py and overlays its values onto
    the routing-config endpoints at startup.

    No API key required (Chatbot Arena is a free public CSV; OpenRouter
    /api/v1/models is unauthenticated for listing; LiteLLM is a raw
    JSON on GitHub). The empirical probe is opt-in during install and
    only runs when ORA_INSTALL_PROBE=1 is set; if a key is unavailable,
    the sync path stays on metadata and public benchmark sources.

    Replaces the prior AA enrichment step.
    """
    log("Step 6/9: Sync curated model registry (OpenRouter + LiteLLM + Chatbot Arena + empirical probe)")
    if dry_run:
        log("  [dry-run] would run scripts/sync_model_registry.py sync")
        return True
    script = REPO_ROOT / "scripts" / "sync_model_registry.py"
    if not script.exists():
        log(f"  ⚠ {script} missing — skipping registry sync (boot.py will fall back to routing-config capabilities)")
        return True  # non-fatal: the system still works without the registry
    try:
        # Use --no-probe to keep install non-flaky; the probe can run
        # post-install via a manual `python3 scripts/sync_model_registry.py probe`
        # or via the periodic refresh cycle when implemented.
        # For installs that have an OpenRouter key set, the user can
        # opt into the probe via the ORA_INSTALL_PROBE=1 env var.
        cmd = [sys.executable, str(script), "sync"]
        if not os.environ.get("ORA_INSTALL_PROBE", "").strip():
            cmd.append("--no-probe")
        result = subprocess.run(
            cmd, cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            log("  ✓ Model registry synced")
            for line in result.stdout.strip().split("\n")[-6:]:  # last 6 lines = summary
                if line.strip():
                    log(f"    {line}")
            state["steps_completed"].append("registry_sync")
            save_state(state)
            return True
        log(f"  ⚠ Registry sync failed (exit {result.returncode}) — proceeding with capability fallback")
        log(f"    stderr: {result.stderr.strip()[:300]}")
        return True  # non-fatal: boot.py falls back to routing-config flags
    except subprocess.TimeoutExpired:
        log("  ⚠ Registry sync timed out after 300s — proceeding with capability fallback")
        return True
    except Exception as e:
        log(f"  ⚠ Registry sync errored ({e}) — proceeding with capability fallback")
        return True


def _refresh_local_model_inventory() -> str | None:
    """Record which local models this machine actually has.

    The Free preset is the only one that mixes locally installed models into
    its picks, and the code that does it refuses to guess: with no inventory
    file it raises rather than route to a model that may not be on disk. The
    Models pane therefore scans before it bakes, and so does this — same
    module, same call — otherwise a machine that has never downloaded a local
    model could not bake Free at all.

    A machine with no local models is a perfectly ordinary answer, not a
    failure: the scan simply records an empty inventory and Free keeps its
    cloud picks. Returns None on success, or the reason the scan failed.
    """
    try:
        from orchestrator import local_model_discovery, runtime_paths
        # `install.py models` downloads into this directory; on a fresh clone
        # it does not exist yet, and the scanner will not invent it.
        runtime_paths.local_models_dir().mkdir(parents=True, exist_ok=True)
        result = local_model_discovery.refresh(write=True)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    found = len(result.get("discovered") or [])
    refused = result.get("refused")
    if refused:
        log(f"  ⚠ Local-model inventory not updated: {refused}")
        return None
    log(f"  ✓ Local-model inventory recorded: {found} installed locally")
    return None


def _relay_baker_line(message: str) -> None:
    """Put a line the preset baker wrote into the install transcript.

    The baker runs in-process here rather than as a subprocess, so anything it
    writes for itself goes to the installer's terminal and stops there — while
    install.log, the file the install tells the user to open afterwards, never
    hears about it. That matters most for the one line saying a forced bake has
    just replaced an existing preset and overwritten any slots picked by hand:
    a warning about a destructive act that is missing from the record of the
    install only half-exists.

    So the baker's lines go through ``log`` like every other line of this step,
    indented to sit at the same level as the ✓ and ⚠ lines around them.
    """
    log(f"  {message}")


# The slots a configuration card puts a model in, in the order the card reads
# them. They are also the whole of what a configuration is *for*: the models
# the pipeline calls when that configuration is the one in use.
CARD_SLOTS = ("big1", "big2", "fast1", "fast2", "small")

# The configuration step 7 fills and Ora then serves requests from. Named once
# so the picker call and the read-back that checks it can never end up talking
# about different configurations.
ACTIVE_CONFIGURATION = "user-pipeline"


def _card_picks(summary: dict) -> list[str]:
    """The models a baked configuration actually put in its slots.

    Empty means the bake produced a file with a model in none of them — a card
    with nothing on it, and a configuration the pipeline cannot run from.
    """
    return [
        str(summary.get(slot)).strip()
        for slot in CARD_SLOTS
        if str(summary.get(slot) or "").strip()
    ]


def _report_no_model_in_any_slot(
    names: list[str],
    *,
    headline: str,
    subject: str,
    consequence: tuple[str, ...],
    catalog: Path | None = None,
) -> None:
    """Say why the install is stopping over a configuration holding nothing.

    One message for both halves of step 7. A preset card and the active
    user-pipeline fail the same test — a file that exists with a model in none
    of its slots — for the same reason, so the install says it in the same
    words: what came out empty, what was in the catalog it was picked from,
    what that leaves the user with, and the one command that gets a current
    catalog. Only the subject of the sentence changes.

    ``catalog`` is the file the picks in question came out of, and each half
    passes its own: the picker CLI's for ``user-pipeline``, the runtime
    baker's for the preset cards. Describing the wrong one is how this
    message once told a user their presets came from a 296-model catalog when
    they had come from a one-model file nobody named.
    """
    log(f"  ✗ {headline}: {', '.join(names)}")
    _usable, catalog_description = _catalog_baseline(catalog)
    log(f"    {subject} picked from a catalog holding {catalog_description}.")
    for line in consequence:
        log(f"    {line}")
    log("    Picks come from that catalog, narrowed by the model registry")
    log("    step 6 syncs; a catalog that never refreshed is the usual cause.")
    log(f"    Get a current one with `{CATALOG_REFRESH_RETRY_COMMAND}` (it")
    log("    needs OpenRouter reachable), then re-run the install with --resume.")


def _bake_promised_presets() -> bool:
    """Create every preset the install promises, through the runtime's baker.

    Ora promises four model presets — Free, Budget, Speed and Premium. They
    are declared in ``config/configuration-presets.json``, named in
    ``runtime_paths.PRESET_NAMES`` and in ``active_configuration.PRESET_ORDER``,
    and the Models pane draws one card per name.

    Until now the install created none of them. It produced a Budget-derived
    user pipeline and a Free smoke-test copy, and left the four cards to be
    baked the first time somebody opened the Models pane — where Speed had no
    file at all, Premium showed whatever snapshot happened to be committed to
    the repository, and a bake that failed became a blank card with no reason
    on it.

    This uses ``bake_missing_presets``, the very call the Models pane makes,
    rather than a second mechanism that could drift from it. ``force=True``
    because the install has just settled which catalog this machine will use:
    every preset should be picked from that catalog, not inherited from a
    snapshot committed months earlier.

    Returns False — halting the install — when a promised preset is absent
    after the bake, or present with a model in none of its slots. Anything
    between those and a full house is reported as a warning and finishes.
    """
    try:
        from orchestrator import active_configuration as ac
    except Exception as exc:
        log(f"  ✗ Could not load the preset baker: {type(exc).__name__}: {exc}")
        return False

    promised = list(ac.PRESET_ORDER)
    log(f"  · Baking the presets the Models pane shows: {', '.join(promised)}")
    inventory_error = _refresh_local_model_inventory()
    if inventory_error:
        log(f"  ⚠ Local-model scan failed ({inventory_error});"
            " Free will bake from cloud models only.")
    try:
        ac.bake_missing_presets(force=True, log=_relay_baker_line)
    except Exception as exc:
        log(f"  ✗ The preset bake failed outright: {type(exc).__name__}: {exc}")
        return False

    listing = ac.list_configurations()
    summaries = listing.get("presets") or {}
    causes = listing.get("preset_errors") or {}
    missing = [name for name in promised if not summaries.get(name)]
    if missing:
        log(f"  ✗ These presets do not exist after the bake: {', '.join(missing)}")
        for name in missing:
            log(f"      {name}: {causes.get(name) or 'no cause recorded'}")
        log("    Ora promises a card for each of these in Settings → Models, so")
        log("    the install stops rather than finish with one of them absent.")
        return False

    # A preset file can exist and still hold nothing. The bake writes one
    # whenever the picker returns without raising, and on a catalog with no
    # model the picker returns cleanly with every slot empty — which is how
    # this step used to print four warnings and then "All 4 promised presets
    # exist" over four blank cards.
    #
    # An empty preset is not a thin preset, it is an absent one: the card
    # shows nothing and the pipeline it feeds has nothing to call. So it fails
    # exactly as a missing preset does, above. A preset that filled some of
    # its slots and not others is the genuinely partial case and still passes,
    # with the warning further down.
    empty = [name for name in promised if not _card_picks(summaries[name] or {})]
    if empty:
        # Ask the baker's own resolver which catalog it read, exactly as the
        # user-pipeline read-back does. These picks came out of the baker's
        # file, so that is the file this message has to describe and name —
        # describing the picker's instead once told a user their empty presets
        # came from a 296-model catalog and sent them to refresh the one file
        # that was already fine.
        baker_catalog = ac._catalog_path()
        _report_no_model_in_any_slot(
            empty,
            headline="These presets baked with no model in any slot",
            subject="They were",
            consequence=(
                "Nothing in it reached those presets' slots, so their cards in",
                "Settings → Models would be blank and nothing could run from",
                "them. That is the same outcome as a preset that never baked, so",
                "the install stops here rather than report success over it.",
            ) + _catalog_split_note(
                baker_catalog,
                lead=(
                    "The user-pipeline line above can look healthy while these are",
                    "empty, because the two halves of this step read different",
                    "catalog files.",
                ),
            ),
            catalog=baker_catalog,
        )
        return False

    for name in promised:
        summary = summaries[name] or {}
        incomplete = bool(summary.get("incomplete"))
        log(f"  {'⚠' if incomplete else '✓'} {name}: "
            f"big {summary.get('big1') or '—'} · "
            f"fast {summary.get('fast1') or '—'} · "
            f"small {summary.get('small') or '—'}")
        if incomplete:
            log("      Some slots came out empty — the catalog held no candidate")
            log("      that fits this preset's rules. Pick models for the empty")
            log("      slots in Settings → Models, or refresh the catalog and")
            log("      re-bake from the pane's Refresh button.")
    log(f"  ✓ All {len(promised)} promised presets exist: {', '.join(promised)}")
    return True


def _catalog_split_note(baker_catalog: Path, *, lead: tuple[str, ...]) -> tuple[str, ...]:
    """Name both catalogs when step 7's two halves did not read the same one.

    Step 7's two halves do not find the model catalog the same way. The picker
    CLI takes ``ORA_MODEL_CATALOG_PATH`` or this checkout's own
    ``config/model-catalog.json``; the runtime's preset baker prefers the
    runtime overlay copy under ``data/runtime/`` whenever one is there — and
    one is there on any machine that has run Ora and refreshed its models.

    Normally both land on the same file and there is nothing to say. When they
    do not, one half can produce a perfectly healthy result out of one catalog
    while the other comes out blank from the other, and whichever half is
    halting has to say so — otherwise the user reads a halt sitting directly
    beside a success and has no way to see that both are true. Naming both
    files is also the only thing that tells them which one to repair: the
    refresh command below rewrites the picker's copy and never touches the
    overlay, so a user pointed at the wrong file simply re-runs into the same
    halt.

    ``lead`` is the one sentence that differs — which half is empty and which
    looks fine — because that is the only part of this note the two halves
    cannot share.
    """
    picker_catalog = _catalog_path()
    if picker_catalog == baker_catalog:
        return ()
    return lead + (
        f"The picker read {picker_catalog};",
        f"the preset baker read {baker_catalog}.",
    )


def _verify_active_configuration() -> bool:
    """Hold the configuration Ora serves from to the presets' own standard.

    The presets are read back after they bake and the install halts on one that
    exists with a model in no slot. ``user-pipeline`` had no such read-back,
    and it is the configuration the pipeline actually runs on — so an install
    could report ``INSTALL_COMPLETE`` over a Models pane with four healthy
    cards and a running configuration that cannot answer a single prompt.

    It is the same rule, so it is the same check and the same message: an
    entirely empty configuration halts, a partly filled one is the genuinely
    thin case and finishes with a warning.

    The read-back goes through the runtime's own reader rather than opening the
    file the picker just wrote, so what gets checked is the file the server
    will actually read — which, for this name, may be a runtime overlay copy
    sitting on top of it.
    """
    try:
        from orchestrator import active_configuration as ac
        listing = ac.list_configurations()
    except Exception as exc:
        log(f"  ✗ Could not read {ACTIVE_CONFIGURATION} back: "
            f"{type(exc).__name__}: {exc}")
        return False

    # It normally lands among the customs, but a configuration carrying a
    # preset lineage can be adopted into a preset slot when that preset has no
    # file of its own, so look everywhere rather than in the expected bucket.
    candidates = list(listing.get("customs") or [])
    candidates.extend(s for s in (listing.get("presets") or {}).values() if s)
    summary = next(
        (s for s in candidates if (s or {}).get("name") == ACTIVE_CONFIGURATION),
        None,
    )
    if summary is None:
        log(f"  ✗ {ACTIVE_CONFIGURATION} does not exist after the picker ran.")
        log("    Ora serves requests from it, so the install stops here rather")
        log("    than finish without the configuration it just promised.")
        return False

    if not _card_picks(summary):
        # Ask the baker's own resolver where it read its catalog rather than
        # restating its rule here — a second copy of that rule is exactly the
        # kind of drift this guard exists to catch.
        baker_catalog = ac._catalog_path()
        _report_no_model_in_any_slot(
            [ACTIVE_CONFIGURATION],
            headline="This configuration was picked with no model in any slot",
            subject="It was",
            consequence=(
                f"{ACTIVE_CONFIGURATION} is the configuration Ora serves",
                "requests from, so an empty one is not a thin install — it is",
                "an install that cannot answer a single prompt. That is the",
                "same outcome as a preset with nothing in it, so it stops the",
                "install the same way rather than report success over it.",
            ) + _catalog_split_note(
                baker_catalog,
                lead=(
                    "The preset cards above can look healthy while this one is empty,",
                    "because the two halves of this step read different catalog files.",
                ),
            ),
            catalog=_catalog_path(),
        )
        return False

    # Reported exactly as a preset card is, because it is the same read of the
    # same slots: the models it holds on one line, and the same warning under
    # it when some of them came out empty.
    incomplete = bool(summary.get("incomplete"))
    log(f"  {'⚠' if incomplete else '✓'} {ACTIVE_CONFIGURATION}: "
        f"big {summary.get('big1') or '—'} · "
        f"fast {summary.get('fast1') or '—'} · "
        f"small {summary.get('small') or '—'}")
    if incomplete:
        log("      Some slots came out empty — the catalog held no candidate")
        log("      that fits them. Pick models for the empty slots in")
        log("      Settings → Models, or refresh the catalog and re-run the")
        log("      install with --resume.")
    return True


def step_autopopulate(state: dict, dry_run: bool) -> bool:
    """Fill the user's pipeline and every preset the Models pane promises.

    Two halves: the running pipeline (``user-pipeline``, Budget rules) through
    the picker CLI, and the four preset cards through the runtime's own baker.
    The step fails if a promised preset does not exist afterwards, or exists
    with nothing in it, naming which one and why — a preset the install
    promised and did not deliver is not a success, and neither is an empty one.

    Both halves are then held to that one standard, because both halves can
    fail it. They resolve the model catalog by different rules, so a stale
    runtime overlay can have them picking from different files; the presets
    are read back after they bake and ``user-pipeline`` is read back too. It
    matters more than any single preset — it is what Ora serves requests from.
    """
    log("Step 7/9: User-pipeline configuration (Budget) and the four model presets")
    if dry_run:
        log("  [dry-run] would run scripts/auto-populate-configuration.py "
            f"budget {ACTIVE_CONFIGURATION}")
        log("  [dry-run] would bake the Free, Budget, Speed and Premium presets")
        return True
    script = REPO_ROOT / "scripts" / "auto-populate-configuration.py"
    if not script.exists():
        log(f"  ✗ {script} missing")
        return False
    try:
        result = subprocess.run(
            [sys.executable, str(script), "budget", ACTIVE_CONFIGURATION],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        log("  ✗ Auto-populate timed out after 60s")
        return False
    if result.returncode != 0:
        log(f"  ✗ Auto-populate failed (exit {result.returncode})")
        log(f"    stderr: {result.stderr.strip()}")
        return False
    log(f"  ✓ {ACTIVE_CONFIGURATION} configuration populated")
    for line in result.stdout.strip().split("\n"):
        if line.strip():
            log(f"    {line}")

    if not _bake_promised_presets():
        return False

    # Last, so the message about healthy preset cards can point at the ones
    # printed directly above it.
    if not _verify_active_configuration():
        return False

    state["steps_completed"].append("autopopulate")
    save_state(state)
    return True


def _extract_smoke_models(cfg: dict) -> list[str]:
    """Return Free-config model candidates in the order the user would hit them."""
    candidates: list[str] = []
    try:
        cell = cfg["cells"]["analysis"]["gear4"]["depth"]
        primary = cell.get("primary")
        if primary:
            candidates.append(primary)
        candidates.extend([m for m in cell.get("fallback", []) if m])
    except (KeyError, AttributeError, TypeError):
        pass
    if "openrouter/free" not in candidates:
        candidates.append("openrouter/free")
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(candidates))


def _openrouter_smoke_call(model_id: str, api_key: str) -> tuple[bool, str, bool]:
    """Attempt a tiny OpenRouter chat call.

    Returns (ok, message, auth_failure). Auth failures should stop install;
    free-model availability/rate failures are external and can fall back to
    config validation.
    """
    payload = json.dumps({
        "model": model_id,
        "messages": [
            {"role": "system", "content": "Reply with exactly: Ora install smoke ok"},
            {"role": "user", "content": "Smoke test."},
        ],
        "temperature": 0,
        "max_tokens": 12,
    }).encode("utf-8")
    try:
        raw, _destination = network_policy.openrouter_request_bytes(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ora-ai.app",
            "X-Title": "Ora installer smoke test",
            },
            timeout=45,
            max_bytes=8 * 1024 * 1024,
        )
        body = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        detail = network_policy.redact_sensitive_text(
            detail, secrets=(api_key,),
        )
        auth_failure = exc.code in {401, 403}
        return False, f"HTTP {exc.code}: {detail}", auth_failure
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        detail = network_policy.redact_sensitive_text(
            exc, secrets=(api_key,),
        )
        return False, f"{type(exc).__name__}: {detail}", False
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON response: {exc}", False
    except Exception as exc:
        detail = network_policy.redact_sensitive_text(
            exc, secrets=(api_key,),
        )
        return False, f"{type(exc).__name__}: {detail}", False

    content = ""
    try:
        content = (body["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        pass
    if not content:
        return False, "empty response from OpenRouter", False
    return True, content[:160], False


def step_smoke_test(state: dict, dry_run: bool) -> bool:
    log("Step 8/9: Smoke test (Free configuration + optional OpenRouter round-trip)")
    if dry_run:
        log("  [dry-run] would auto-populate Free + send one test prompt when an OpenRouter key is available")
        return True
    # Populate a free configuration first so the smoke test has something to hit.
    autopop = REPO_ROOT / "scripts" / "auto-populate-configuration.py"
    try:
        subprocess.run(
            [sys.executable, str(autopop), "free", "smoke-test-free"],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=60, check=True,
        )
    except subprocess.CalledProcessError as exc:
        log(f"  ✗ Could not populate the smoke-test configuration: {exc.stderr}")
        return False

    # Read the populated configuration and check that it has a primary model
    smoke_cfg_path = REPO_ROOT / "config" / "configurations" / "smoke-test-free.json"
    try:
        with open(smoke_cfg_path) as f:
            cfg = json.load(f)
        candidates = _extract_smoke_models(cfg)
    except (KeyError, TypeError):
        log("  ⚠ smoke-test-free configuration has no primary; the free catalog may be empty")
        return False

    if not candidates:
        log("  ⚠ smoke-test-free configuration has no model candidates; the free catalog may be empty")
        return False

    log(f"  ✓ Smoke-test configuration primary resolved: {candidates[0]}")
    api_key = _openrouter_key()
    if not api_key:
        log("  → No OpenRouter key found in env or keyring; skipping live chat round-trip.")
        log("    Add a key later in Settings → External APIs. The install remains usable with")
        log("    local models, an optional ChatGPT subscription connection, and any")
        log("    API keys you add after first launch.")
    else:
        log("  OpenRouter key found; attempting a tiny live chat round-trip.")
        last_error = ""
        for model_id in candidates[:5]:
            ok, message, auth_failure = _openrouter_smoke_call(model_id, api_key)
            if ok:
                log(f"  ✓ OpenRouter chat round-trip succeeded with {model_id}: {message!r}")
                break
            last_error = f"{model_id}: {message}"
            log(f"    {model_id} did not complete: {message}")
            if auth_failure:
                log("  ✗ OpenRouter rejected the key. Update it in Settings → External APIs or OPENROUTER_API_KEY.")
                return False
        else:
            log("  → Live OpenRouter chat did not complete with the current free candidates.")
            log(f"    Last result: {last_error}")
            log("    Free models are rate-limited and sometimes unavailable; configuration validation passed.")

    state["steps_completed"].append("smoke_test")
    save_state(state)
    return True


def step_external_api_walkthrough(state: dict, dry_run: bool) -> bool:
    log("Step 9/9: Optional ChatGPT subscription and External APIs orientation")
    log("")
    log("  Optional ChatGPT subscription route:")
    log("    - Open Settings → External APIs → OpenAI (ChatGPT), then click Connect.")
    log("    - Ora's installed openai-codex SDK opens browser sign-in and stores its")
    log("      isolated session in the system keychain; you do not paste an API key.")
    log("    - Available Codex access depends on your ChatGPT plan or workspace.")
    log("")
    log("  Ora can run without these keys, and every provider below can be added")
    log("  later in Settings → External APIs. Keys are stored in the system keychain,")
    log("  not in plaintext files.")
    log("")
    log("  Recommended minimal package: OpenRouter + Tavily + Artificial Analysis.")
    log("  FRED is intentionally skipped here; it is for specialized economic-data work.")
    log("")

    for group in EXTERNAL_API_GROUPS:
        log(f"  {group['title']}:")
        for provider in group["providers"]:
            log(f"    - {provider['name']}: {provider['why']}")
            log(f"      Cost: {provider['cost']}")
            log(f"      Link: {provider['url']}")
        log("")

    if dry_run:
        log("  [dry-run] would offer to open official provider pages")
        return True

    if sys.stdin.isatty() and _prompt_yes_no("  Open provider pages now?", default=False):
        for group in EXTERNAL_API_GROUPS:
            print()
            print(f"  {group['title']}")
            for provider in group["providers"]:
                print(f"    {provider['name']}: {provider['url']}")
                if _prompt_yes_no(f"    Open {provider['name']} page?", default=False):
                    if _open_provider_page(provider["url"]):
                        log(f"  ✓ Opened {provider['name']} page")
                    else:
                        log(f"  → Could not open browser automatically; copy this link: {provider['url']}")
    else:
        log("  Skipping browser-open prompts. Use the links above or Settings → External APIs later.")

    state["steps_completed"].append("external_api_walkthrough")
    save_state(state)
    return True


# ─── Main ────────────────────────────────────────────────────────────────


def _delegate_to_local_models(extra_argv: list[str]) -> int:
    """Re-entry point for `install.py models …`: defers to scripts/local_models.py.

    Lets users swap / add / remove local models any time post-install
    without re-running the full install pipeline.
    """
    script = REPO_ROOT / "scripts" / "local_models.py"
    if not script.exists():
        print(f"[install] {script} missing", file=sys.stderr)
        return 1
    return subprocess.call([sys.executable, str(script), *extra_argv])


def _delegate_to_converters(extra_argv: list[str]) -> int:
    """Re-entry point for `install.py converters`: defers to scripts/converters.py.

    This is the retry command the install step prints. It re-checks what the
    machine has and downloads only what is still missing, so running it twice
    is harmless. Like the install step it settles ``ORA_HOME`` by the
    launchers' rule — a setting that names a path is kept, a missing or blank
    one becomes this clone — so the retry writes to the same place the first
    attempt did, and the same place the server reads from.
    """
    script = REPO_ROOT / "scripts" / "converters.py"
    if not script.exists():
        print(f"[install] {script} missing", file=sys.stderr)
        return 1
    return subprocess.call(
        [sys.executable, str(script), *extra_argv],
        cwd=str(REPO_ROOT), env=_converter_environment(),
    )


def _next_launch_instructions(
    platform_name: str | None = None, os_name: str | None = None
) -> list[str]:
    platform_name = sys.platform if platform_name is None else platform_name
    os_name = os.name if os_name is None else os_name
    if platform_name == "darwin":
        return [
            "Next (recommended on macOS): install supervised auto-start with "
            "`./scripts/ora-launchd.sh install`, then open the origin for its printed Health URL.",
            "For one unsupervised session instead, run `./start.sh`.",
        ]
    if os_name == "nt":
        return ["Next: run `start.bat` and open the exact localhost port it reports."]
    return ["Next: run `./start.sh` and open the exact localhost port it reports."]


def main():
    # Subcommand support — primary path is the full install; secondary
    # path is `install.py models` which re-enters the local-model
    # selection flow standalone.
    if len(sys.argv) >= 2 and sys.argv[1] == "models":
        sys.exit(_delegate_to_local_models(sys.argv[2:]))
    if len(sys.argv) >= 2 and sys.argv[1] == "converters":
        sys.exit(_delegate_to_converters(sys.argv[2:]))

    parser = argparse.ArgumentParser(
        description=(
            "Ora source-install script (Solo public profile). Subcommands: "
            "'models' re-enters local-model selection; 'converters' re-runs the "
            "Pandoc + Typst download that Word/PDF export needs."
        ),
    )
    parser.add_argument("--profile", choices=list(DEPLOYMENT_PROFILES.keys()), help="Skip the interactive profile prompt.")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without making changes.")
    parser.add_argument("--reset", action="store_true", help="Clear install state and exit.")
    parser.add_argument("--resume", action="store_true", help="Continue from the last completed step.")
    args = parser.parse_args()

    if args.reset:
        reset_install(args.dry_run)
        return

    state = load_state()
    if not state.get("started_at"):
        state["started_at"] = datetime.now(timezone.utc).isoformat()
        save_state(state, dry_run=args.dry_run)

    log(f"Ora source install — Solo public profile — {'DRY RUN' if args.dry_run else 'LIVE'}")
    log(f"Repo root: {REPO_ROOT}")
    if args.resume and state.get("steps_completed"):
        log(f"Resuming after: {', '.join(state['steps_completed'])}")

    completed = set(state.get("steps_completed", []))
    pipeline = [
        ("preflight",      step_preflight,    (state, args.dry_run)),
        ("dependencies",   step_dependencies, (state, args.dry_run)),
        ("converters",     step_converters,   (state, args.dry_run)),
        ("profile",        step_select_profile, (state, args.profile, args.dry_run)),
        ("catalog",        step_catalog_refresh, (state, args.dry_run)),
        ("registry_sync",  step_model_registry_sync, (state, args.dry_run)),
        ("autopopulate",   step_autopopulate, (state, args.dry_run)),
        ("smoke_test",     step_smoke_test,   (state, args.dry_run)),
        ("external_api_walkthrough", step_external_api_walkthrough, (state, args.dry_run)),
    ]

    for step_name, fn, fn_args in pipeline:
        if args.resume and step_name in completed:
            log(f"  ✓ Step '{step_name}' already completed; skipping")
            continue
        if not fn(*fn_args):
            log(f"INSTALL_HALTED at step '{step_name}'. Fix the issue above and re-run with --resume.")
            sys.exit(1)

    log(COMPLETION_MARKER)
    log("")
    for line in _next_launch_instructions():
        log(line)
    log("Then open Settings → External APIs to connect ChatGPT and/or paste any API keys you created during setup.")


if __name__ == "__main__":
    main()
