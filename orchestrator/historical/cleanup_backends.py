"""Pluggable model-call backends for the cleanup pipeline.

The cleanup orchestrator talks to models through one small interface —
``client.call(system=..., user=..., model=..., max_tokens=...,
temperature=...) -> CallResult`` plus ``client.stats()`` — implemented
by three interchangeable backends:

  * ``AnthropicClient`` (api_client.py) — direct Anthropic API,
    pay-per-token, keyring auth. The original backend.
  * ``ClaudeCLIClient`` (here) — shells out to the ``claude`` CLI in
    print mode. Calls are billed to the user's Claude subscription,
    not an API key. Slower per call (process startup) and subject to
    subscription rate windows; the batch manifest's resume logic makes
    interruption safe.
  * ``OraSlotClient`` (here) — dispatches through Ora's own slot
    routing (``orchestrator.model_dispatch.invoke_chat``). No model
    names appear here or in any framework: the slot's meaning is
    "light cleanup" vs "heavy cleanup" and the publisher's
    routing-config decides what serves it.

Backends never appear in framework documents; the framework speaks in
tiers ("light"/"heavy") and the backend maps tiers to whatever serves
them. Select a backend with ``build_client(name)`` — names: ``api``,
``claude-cli``, ``ora-slots``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from typing import Optional

from orchestrator.historical.api_client import (
    CallResult,
    ClientStats,
    estimate_tokens,
)


# ---------------------------------------------------------------------------
# Claude CLI backend (subscription-billed)
# ---------------------------------------------------------------------------

# The CLI accepts model aliases; we map the pipeline's internal model ids
# onto capability aliases so no exact model version is pinned here.
_CLI_ALIAS_LIGHT = "haiku"
_CLI_ALIAS_HEAVY = "sonnet"

# Env overrides:
#   ORA_CLAUDE_CLI            — path to the claude binary (default: "claude")
#   ORA_CLEANUP_CLI_MODEL     — force ONE alias/model for every call
ENV_CLI_BIN   = "ORA_CLAUDE_CLI"
ENV_CLI_MODEL = "ORA_CLEANUP_CLI_MODEL"

DEFAULT_CLI_TIMEOUT_SECS = 600
DEFAULT_CLI_MAX_RETRIES  = 3

# Concurrency above this thrashes subscription rate windows and spawns
# that many CLI processes at once; run_batch caps to it for this backend.
CLI_RECOMMENDED_MAX_WORKERS = 3


class ClaudeCLIClient:
    """Model calls via ``claude -p`` — billed to the Claude subscription.

    Interface-compatible with ``AnthropicClient`` for everything the
    cleanup pipeline uses: ``call()`` and ``stats()``. Token counts are
    estimates (the CLI does not report usage in text mode) and cost is
    recorded as 0.0 — subscription usage has no per-call dollar figure.
    """

    def __init__(self,
                 timeout_secs: int = DEFAULT_CLI_TIMEOUT_SECS,
                 max_retries:  int = DEFAULT_CLI_MAX_RETRIES,
                 binary:       Optional[str] = None):
        self.timeout_secs = timeout_secs
        self.max_retries  = max_retries
        requested_binary = binary or os.environ.get(ENV_CLI_BIN, "claude")
        self._stats       = ClientStats()
        self._lock        = threading.Lock()
        resolved_binary = shutil.which(requested_binary)
        if resolved_binary is None:
            raise RuntimeError(
                f"claude CLI not found ('{requested_binary}'). Install Claude "
                f"Code or set {ENV_CLI_BIN} to the binary path."
            )
        # Preserve the exact executable that passed validation. On Windows,
        # PATHEXT may resolve an extensionless request to ``claude.cmd``.
        self.binary = resolved_binary
        # Neutral, empty working directory: the CLI auto-discovers
        # project context (CLAUDE.md etc.) from its cwd, and cleanup
        # calls must run context-free.
        import tempfile
        self._cwd = os.path.join(tempfile.gettempdir(), "ora-cleanup-cli-cwd")
        os.makedirs(self._cwd, exist_ok=True)

    # ----- model mapping -----

    @staticmethod
    def _cli_model(model_id: Optional[str]) -> str:
        forced = os.environ.get(ENV_CLI_MODEL, "").strip()
        if forced:
            return forced
        mid = (model_id or "").lower()
        if "haiku" in mid:
            return _CLI_ALIAS_LIGHT
        if "sonnet" in mid:
            return _CLI_ALIAS_HEAVY
        if "opus" in mid:
            return "opus"
        return _CLI_ALIAS_HEAVY if mid else _CLI_ALIAS_LIGHT

    # ----- stats -----

    def stats(self) -> ClientStats:
        with self._lock:
            return ClientStats(
                calls=self._stats.calls,
                successes=self._stats.successes,
                failures=self._stats.failures,
                retries=self._stats.retries,
                input_tokens=self._stats.input_tokens,
                output_tokens=self._stats.output_tokens,
                cost_usd=self._stats.cost_usd,
            )

    def _record(self, result: CallResult) -> None:
        with self._lock:
            self._stats.calls += 1
            if result.error:
                self._stats.failures += 1
            else:
                self._stats.successes += 1
            self._stats.retries += max(0, result.attempts - 1)
            self._stats.input_tokens += result.input_tokens
            self._stats.output_tokens += result.output_tokens

    # ----- call -----

    def call(self,
             *,
             system:      str = "",
             user:        str = "",
             messages:    Optional[list[dict]] = None,
             model:       Optional[str] = None,
             max_tokens:  Optional[int] = None,   # accepted, CLI decides
             temperature: float = 0.0) -> CallResult:      # noqa: ARG002
        """One CLI call. The user text goes via stdin (no ARG_MAX limit);
        the system prompt goes via ``--system-prompt``. Never raises for
        transient failures — ``result.error`` is set on terminal failure.
        """
        if messages is not None:
            user = "\n\n".join(
                m.get("content", "") for m in messages if m.get("role") == "user"
            )
        if not user:
            raise ValueError("call() needs user text")

        cli_model = self._cli_model(model)
        result = CallResult(model=f"cli:{cli_model}")
        start = time.monotonic()

        # Lockdown: the archive text is adversarial by construction
        # (39K conversations full of literal instructions), and in print
        # mode the CLI is otherwise a tool-armed agent. Disable every
        # tool, load no settings (no allowlists, no hooks), persist no
        # sessions, and run in an empty cwd so no project context leaks
        # into cleanup calls. The call must be a pure text transform.
        cmd = [self.binary, "-p", "--output-format", "text",
               "--model", cli_model,
               "--tools", "",
               "--setting-sources", "",
               "--no-session-persistence"]
        if system:
            cmd += ["--system-prompt", system]

        for attempt in range(1, self.max_retries + 1):
            result.attempts = attempt
            try:
                proc = subprocess.run(
                    cmd, input=user, capture_output=True, text=True,
                    timeout=self.timeout_secs, cwd=self._cwd,
                )
            except subprocess.TimeoutExpired:
                result.error = f"claude CLI timeout after {self.timeout_secs}s"
                if attempt < self.max_retries:
                    time.sleep(5 * attempt)
                    continue
                break
            except OSError as e:
                result.error = f"claude CLI spawn failed: {e}"
                break

            if proc.returncode == 0 and proc.stdout.strip():
                result.text  = proc.stdout.strip()
                result.error = ""
                break

            stderr_tail = (proc.stderr or "").strip()[-300:]
            result.error = (f"claude CLI exit {proc.returncode}: "
                            f"{stderr_tail or 'empty output'}")
            if attempt < self.max_retries:
                # Rate-window pushback tends to clear on the order of
                # tens of seconds; back off harder than for plain errors.
                low = (stderr_tail or "").lower()
                wait = 60 if ("rate" in low or "limit" in low or
                              "usage" in low) else 10 * attempt
                time.sleep(wait)

        result.input_tokens  = estimate_tokens(system) + estimate_tokens(user)
        result.output_tokens = estimate_tokens(result.text)
        result.cost_usd      = 0.0   # subscription-billed
        result.duration_secs = time.monotonic() - start
        self._record(result)
        return result


# ---------------------------------------------------------------------------
# Ora slot backend (future daily path)
# ---------------------------------------------------------------------------

# Tier → slot mapping. Slots are capability names; routing-config decides
# what model serves them. "haiku"-tier work (typical pairs) maps to the
# cleanup slot; "sonnet"-tier work (long pairs) to the high-context slot.
SLOT_LIGHT = "step1_cleanup"
SLOT_HEAVY = "breadth"


class OraSlotClient:
    """Model calls via Ora's slot routing (``model_dispatch.invoke_chat``).

    This is the path Ora itself uses when the pipeline runs as an Ora
    framework: no model names anywhere — the slot's configured endpoint
    does the work, whatever it is.
    """

    def __init__(self, slot_light: str = SLOT_LIGHT,
                 slot_heavy: str = SLOT_HEAVY):
        self.slot_light = slot_light
        self.slot_heavy = slot_heavy
        self._stats = ClientStats()
        self._lock  = threading.Lock()

    @staticmethod
    def _is_heavy(model_id: Optional[str]) -> bool:
        mid = (model_id or "").lower()
        return "sonnet" in mid or "opus" in mid or "hermes" in mid

    def stats(self) -> ClientStats:
        with self._lock:
            return ClientStats(
                calls=self._stats.calls,
                successes=self._stats.successes,
                failures=self._stats.failures,
                input_tokens=self._stats.input_tokens,
                output_tokens=self._stats.output_tokens,
                cost_usd=self._stats.cost_usd,
            )

    def call(self,
             *,
             system:      str = "",
             user:        str = "",
             messages:    Optional[list[dict]] = None,
             model:       Optional[str] = None,
             max_tokens:  Optional[int] = None,   # slot endpoint decides
             temperature: float = 0.0) -> CallResult:      # noqa: ARG002
        if messages is not None:
            user = "\n\n".join(
                m.get("content", "") for m in messages if m.get("role") == "user"
            )
        if not user:
            raise ValueError("call() needs user text")

        slot = self.slot_heavy if self._is_heavy(model) else self.slot_light
        result = CallResult(model=f"slot:{slot}")
        start = time.monotonic()
        try:
            from orchestrator.model_dispatch import invoke_chat
            text = invoke_chat(system, user, slot=slot, context="batch")
            result.text = (text or "").strip()
            if not result.text:
                result.error = f"slot '{slot}' returned empty response"
        except Exception as e:
            result.error = f"slot dispatch failed: {e}"
        result.attempts      = 1
        result.input_tokens  = estimate_tokens(system) + estimate_tokens(user)
        result.output_tokens = estimate_tokens(result.text)
        result.cost_usd      = 0.0   # slot endpoint's own accounting applies
        result.duration_secs = time.monotonic() - start
        with self._lock:
            self._stats.calls += 1
            if result.error:
                self._stats.failures += 1
            else:
                self._stats.successes += 1
            self._stats.input_tokens += result.input_tokens
            self._stats.output_tokens += result.output_tokens
        return result


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

BACKEND_API        = "api"
BACKEND_CLAUDE_CLI = "claude-cli"
BACKEND_ORA_SLOTS  = "ora-slots"
BACKEND_CHOICES    = (BACKEND_API, BACKEND_CLAUDE_CLI, BACKEND_ORA_SLOTS)


def build_client(backend: str = BACKEND_API):
    """Construct the model-call client for the named backend."""
    if backend == BACKEND_API:
        from orchestrator.historical.api_client import AnthropicClient
        return AnthropicClient()
    if backend == BACKEND_CLAUDE_CLI:
        return ClaudeCLIClient()
    if backend == BACKEND_ORA_SLOTS:
        return OraSlotClient()
    raise ValueError(
        f"unknown backend '{backend}' — choose from {BACKEND_CHOICES}"
    )


__all__ = [
    "BACKEND_API",
    "BACKEND_CLAUDE_CLI",
    "BACKEND_ORA_SLOTS",
    "BACKEND_CHOICES",
    "CLI_RECOMMENDED_MAX_WORKERS",
    "ClaudeCLIClient",
    "OraSlotClient",
    "build_client",
]
