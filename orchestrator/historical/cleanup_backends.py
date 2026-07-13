"""Pluggable model-call backends for the cleanup pipeline.

The cleanup orchestrator talks to models through one small interface —
``client.call(system=..., user=..., model=..., max_tokens=...,
temperature=...) -> CallResult`` plus ``client.stats()`` — implemented
by four interchangeable backends:

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
  * ``OpenRouterClient`` (here) — an explicit, OpenRouter-only route.
    Every call POSTs to ``https://openrouter.ai/api/v1`` with the
    keyring OpenRouter key; the request never reaches Anthropic's
    metered API and never spawns the ``claude`` CLI. The pipeline's
    internal model hints (e.g. ``claude-sonnet-4-5``) are mapped to
    OpenRouter slugs (e.g. ``anthropic/claude-sonnet-4.5``) so the
    historical stages keep their tier/provenance semantics while
    OpenRouter remains the sole model-call provider.

Backends never appear in framework documents; the framework speaks in
tiers ("light"/"heavy") and the backend maps tiers to whatever serves
them. Select a backend with ``build_client(name)`` — names: ``api``,
``claude-cli``, ``ora-slots``, ``openrouter``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from typing import Any, Optional

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
# OpenRouter backend (explicit OpenRouter-only route)
# ---------------------------------------------------------------------------
#
# The request always POSTs to https://openrouter.ai/api/v1 and authenticates
# with the keyring OpenRouter key. It never imports the ``anthropic`` SDK and
# never spawns the ``claude`` CLI, so OpenRouter is the sole model-call
# provider on this path. The historical stages pass Anthropic-style model
# hints (e.g. ``claude-sonnet-4-5``); we map those to OpenRouter slugs so the
# stage prompt, JSON parsing, token accounting, and manifest semantics are
# preserved byte-for-byte — only the transport changes.

OPENROUTER_BASE_URL          = "https://openrouter.ai/api/v1"
OPENROUTER_KEYRING_SERVICE   = "ora"
OPENROUTER_KEYRING_USERNAME  = "openrouter-api-key"
ENV_OPENROUTER_KEY           = "OPENROUTER_API_KEY"
# Force ONE OpenRouter slug for every call (overrides the hint map).
ENV_OPENROUTER_MODEL         = "ORA_OPENROUTER_MODEL"

DEFAULT_OPENROUTER_TIMEOUT   = 600
DEFAULT_OPENROUTER_RETRIES    = 4
OPENROUTER_RECOMMENDED_MAX_WORKERS = 6

# Pipeline hint -> OpenRouter slug. The heavy extraction hint
# ``claude-sonnet-4-5`` maps to the OpenRouter-served Sonnet 4.5, billed by
# OpenRouter. The request reaches openrouter.ai, never api.anthropic.com.
_OPENROUTER_MODEL_MAP = {
    "claude-sonnet-4-5":  "anthropic/claude-sonnet-4.5",
    "claude-sonnet-4-7":  "anthropic/claude-sonnet-4.5",
    "claude-sonnet-4-6":  "anthropic/claude-sonnet-4.5",
    "claude-opus-4-6":    "anthropic/claude-opus-4.5",
    "claude-opus-4-5":    "anthropic/claude-opus-4.5",
    "claude-haiku-4-5":   "anthropic/claude-haiku-4.5",
}
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-sonnet-4.5"

# USD per 1M tokens for the slugs we route to. OpenRouter bills on its own
# side; these mirror the underlying provider rates so the manifest's
# ``cost_usd`` accounting stays honest. Unknown slugs record $0.0 (read the
# real spend from the OpenRouter dashboard).
_OPENROUTER_PRICING_USD_PER_M = {
    "anthropic/claude-sonnet-4.5": {"input": 3.0,  "output": 15.0},
    "anthropic/claude-opus-4.5":   {"input": 15.0, "output": 75.0},
    "anthropic/claude-haiku-4.5":  {"input": 1.0,  "output": 5.0},
}


def _estimate_openrouter_cost_usd(
    model: str, input_tokens: int, output_tokens: int,
) -> float:
    rates = _OPENROUTER_PRICING_USD_PER_M.get(model)
    if not rates:
        return 0.0
    return (input_tokens / 1_000_000.0) * rates["input"] + \
           (output_tokens / 1_000_000.0) * rates["output"]


class OpenRouterClient:
    """Model calls via OpenRouter's OpenAI-compatible gateway.

    Interface-compatible with ``AnthropicClient`` (``call()`` + ``stats()``)
    so the historical stages swap it in transparently. Thread-safe: a single
    instance is shared across the ``ThreadPoolExecutor`` (the underlying
    ``openai.OpenAI`` client is thread-safe, like ``anthropic.Anthropic``).
    """

    # One-time redacted route log so a pilot can prove the endpoint + model
    # without exposing credentials. Set under the stats lock.
    _route_logged = False

    def __init__(self,
                 *,
                 model:        str = DEFAULT_OPENROUTER_MODEL,
                 timeout_secs: int = DEFAULT_OPENROUTER_TIMEOUT,
                 max_retries:  int = DEFAULT_OPENROUTER_RETRIES,
                 api_key:      Optional[str] = None,
                 client:       Optional[Any] = None):
        self.default_model = model
        self.timeout_secs  = timeout_secs
        self.max_retries   = max_retries
        self._stats        = ClientStats()
        self._lock         = threading.Lock()
        if client is not None:
            self._client = client
            return
        key = api_key or self._resolve_api_key()
        if not key:
            raise RuntimeError(
                "OpenRouter API key not found. Set keyring entry "
                f"service='{OPENROUTER_KEYRING_SERVICE}', "
                f"username='{OPENROUTER_KEYRING_USERNAME}', or export "
                f"{ENV_OPENROUTER_KEY}."
            )
        import openai
        # Disable SDK-level retries — our wrapper handles retry/backoff.
        self._client = openai.OpenAI(
            api_key=key, base_url=OPENROUTER_BASE_URL,
            timeout=timeout_secs, max_retries=0,
        )

    @staticmethod
    def _resolve_api_key() -> str:
        env_key = os.environ.get(ENV_OPENROUTER_KEY, "")
        if env_key:
            return env_key
        try:
            import keyring
            return keyring.get_password(
                OPENROUTER_KEYRING_SERVICE, OPENROUTER_KEYRING_USERNAME,
            ) or ""
        except Exception:
            return ""

    @staticmethod
    def resolve_model(model_id: Optional[str]) -> str:
        """Map a pipeline hint to an OpenRouter slug (env override wins)."""
        forced = os.environ.get(ENV_OPENROUTER_MODEL, "").strip()
        if forced:
            return forced
        mid = (model_id or "").lower()
        return _OPENROUTER_MODEL_MAP.get(mid, DEFAULT_OPENROUTER_MODEL)

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
            self._stats.cost_usd += result.cost_usd

    def _log_route_once(self, slug: str) -> None:
        with self._lock:
            if OpenRouterClient._route_logged:
                return
            OpenRouterClient._route_logged = True
        import sys as _sys
        print(f"[openrouter] route POST {OPENROUTER_BASE_URL}"
              f"/chat/completions  model={slug}  key=***",
              file=_sys.stderr, flush=True)

    # ----- call -----

    def call(self,
             *,
             system:      str = "",
             user:        str = "",
             messages:    Optional[list[dict]] = None,
             model:       Optional[str] = None,
             max_tokens:  Optional[int] = None,
             temperature: float = 0.0) -> CallResult:
        if messages is not None:
            user = "\n\n".join(
                m.get("content", "") for m in messages if m.get("role") == "user"
            )
        if not user:
            raise ValueError("call() needs user text")

        slug = self.resolve_model(model) if model else self.default_model
        self._log_route_once(slug)
        result = CallResult(model=f"openrouter:{slug}")
        start = time.monotonic()

        msg_payload: list[dict] = []
        if system:
            msg_payload.append({"role": "system", "content": system})
        msg_payload.append({"role": "user", "content": user})

        for attempt in range(1, self.max_retries + 1):
            result.attempts = attempt
            try:
                kwargs: dict = {
                    "model":       slug,
                    "messages":    msg_payload,
                    "temperature": temperature,
                }
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                resp = self._client.chat.completions.create(**kwargs)
                choice = resp.choices[0] if getattr(resp, "choices", None) else None
                text = ""
                if choice is not None:
                    msg = getattr(choice, "message", None)
                    text = (getattr(msg, "content", "") or "") if msg else ""
                text = text.strip()
                usage = getattr(resp, "usage", None)
                in_tok = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
                out_tok = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
                if not in_tok and not out_tok:
                    # Some gateways omit usage on refusals; estimate so the
                    # manifest still records token accounting.
                    in_tok = estimate_tokens(system) + estimate_tokens(user)
                    out_tok = estimate_tokens(text)
                result.text          = text
                result.input_tokens  = in_tok
                result.output_tokens  = out_tok
                result.cost_usd      = _estimate_openrouter_cost_usd(
                    slug, in_tok, out_tok,
                )
                result.error = ""
                break
            except Exception as e:
                err_text = str(e)
                if self._is_retriable(e, err_text) and attempt < self.max_retries:
                    time.sleep(self._backoff(attempt))
                    continue
                result.text  = ""
                result.error = err_text[:500]
                break

        result.duration_secs = time.monotonic() - start
        self._record(result)
        return result

    @staticmethod
    def _is_retriable(exc: Exception, msg: str) -> bool:
        cls_name = type(exc).__name__
        if any(t in cls_name for t in (
            "RateLimitError", "APIConnectionError", "APITimeoutError",
            "Timeout", "Overloaded", "InternalServerError",
        )):
            return True
        status = getattr(exc, "status_code", None)
        if status is None:
            status = getattr(exc, "http_status", None)
        if status in (408, 425, 429, 500, 502, 503, 504):
            return True
        msg_l = msg.lower()
        if any(t in msg_l for t in (
            "rate limit", "ratelimit", "429", "overloaded", "timeout",
            "temporarily", "connection",
        )):
            return True
        return False

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(60.0, 1.5 ** attempt)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

BACKEND_API        = "api"
BACKEND_CLAUDE_CLI = "claude-cli"
BACKEND_ORA_SLOTS  = "ora-slots"
BACKEND_OPENROUTER = "openrouter"
BACKEND_CHOICES    = (
    BACKEND_API, BACKEND_CLAUDE_CLI, BACKEND_ORA_SLOTS, BACKEND_OPENROUTER,
)


def build_client(backend: str = BACKEND_API):
    """Construct the model-call client for the named backend."""
    if backend == BACKEND_API:
        from orchestrator.historical.api_client import AnthropicClient
        return AnthropicClient()
    if backend == BACKEND_CLAUDE_CLI:
        return ClaudeCLIClient()
    if backend == BACKEND_ORA_SLOTS:
        return OraSlotClient()
    if backend == BACKEND_OPENROUTER:
        return OpenRouterClient()
    raise ValueError(
        f"unknown backend '{backend}' — choose from {BACKEND_CHOICES}"
    )


__all__ = [
    "BACKEND_API",
    "BACKEND_CLAUDE_CLI",
    "BACKEND_ORA_SLOTS",
    "BACKEND_OPENROUTER",
    "BACKEND_CHOICES",
    "CLI_RECOMMENDED_MAX_WORKERS",
    "OPENROUTER_RECOMMENDED_MAX_WORKERS",
    "OPENROUTER_BASE_URL",
    "DEFAULT_OPENROUTER_MODEL",
    "ClaudeCLIClient",
    "OraSlotClient",
    "OpenRouterClient",
    "build_client",
]
