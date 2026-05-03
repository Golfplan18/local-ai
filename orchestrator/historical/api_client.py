"""Anthropic API client wrapper for Phase 1 cleanup.

Wraps the `anthropic` Python SDK with:
  - Keyring-based authentication (`keyring.get_password("ora",
    "anthropic-api-key")`) with `ANTHROPIC_API_KEY` env-var override
  - Default model: Haiku 4.5 (configurable per call)
  - Per-call usage capture (input/output tokens) + cumulative stats
  - Cost estimation against published Haiku 4.5 rates
  - Bounded retry on 429 / 5xx with exponential backoff
  - Thread-safe stat tracking for parallel callers

Concurrency model: the underlying `anthropic.Anthropic` client is
thread-safe, so a single `AnthropicClient` instance can be shared
across a `ThreadPoolExecutor`. The `call_batch` helper provides the
parallel-execution loop the cleanup orchestrator (Phase 1.11) will
drive on.
"""

from __future__ import annotations

import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence


# ---------------------------------------------------------------------------
# Defaults + cost rates (published Haiku 4.5 prices as of 2026-04)
# ---------------------------------------------------------------------------

DEFAULT_MODEL          = "claude-haiku-4-5"
# Generous defaults — long stream-of-consciousness pairs need real model
# capacity, and the user explicitly removed speed/cost constraints.
# Output 64K = Sonnet 4.5 max so a ~52K-token input can be fully reproduced.
# Timeout 600s gives Sonnet room to think on big content before retry kicks in.
DEFAULT_MAX_TOKENS     = 64000
DEFAULT_TIMEOUT_SECS   = 600
DEFAULT_MAX_RETRIES    = 4
KEYRING_SERVICE        = "ora"
KEYRING_USERNAME       = "anthropic-api-key"

# USD per 1M tokens, by model. Add entries as needed.
_PRICING_USD_PER_M = {
    "claude-haiku-4-5":   {"input": 1.0,  "output": 5.0},
    "claude-haiku-4-7":   {"input": 1.0,  "output": 5.0},
    "claude-sonnet-4-5":  {"input": 3.0,  "output": 15.0},
    "claude-sonnet-4-7":  {"input": 3.0,  "output": 15.0},
    "claude-opus-4-6":    {"input": 15.0, "output": 75.0},
}


def estimate_tokens(text: str) -> int:
    """Cheap pre-call token estimator (~4 chars per token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD given token counts and a known model."""
    rates = _PRICING_USD_PER_M.get(model)
    if not rates:
        return 0.0
    return (input_tokens / 1_000_000.0) * rates["input"] + \
           (output_tokens / 1_000_000.0) * rates["output"]


# ---------------------------------------------------------------------------
# Per-call response record
# ---------------------------------------------------------------------------


@dataclass
class CallResult:
    """Outcome of one API call. `text` is empty on failure; `error` set."""
    text:           str = ""
    model:          str = ""
    input_tokens:   int = 0
    output_tokens: int  = 0
    cost_usd:       float = 0.0
    error:          str = ""
    attempts:       int = 0
    duration_secs:  float = 0.0


# ---------------------------------------------------------------------------
# Cumulative stats
# ---------------------------------------------------------------------------


@dataclass
class ClientStats:
    calls:           int = 0
    successes:       int = 0
    failures:        int = 0
    retries:         int = 0
    input_tokens:    int = 0
    output_tokens:   int = 0
    cost_usd:        float = 0.0
    # Rate-limit telemetry — populated from Anthropic's response headers
    # on each call so we can size concurrency to the user's API tier.
    rate_limit_requests_limit:        int = 0
    rate_limit_requests_remaining:    int = 0
    rate_limit_input_tokens_limit:    int = 0
    rate_limit_input_tokens_remaining: int = 0
    rate_limit_output_tokens_limit:   int = 0
    rate_limit_output_tokens_remaining: int = 0
    rate_limit_min_requests_seen:     int = 0   # tightest headroom we've seen
    rate_limit_429_count:             int = 0   # outright rate-limit hits


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class AnthropicClient:
    """Thread-safe Anthropic API client with retries + usage tracking."""

    def __init__(self,
                 model:        str = DEFAULT_MODEL,
                 max_tokens:   int = DEFAULT_MAX_TOKENS,
                 timeout_secs: int = DEFAULT_TIMEOUT_SECS,
                 max_retries:  int = DEFAULT_MAX_RETRIES,
                 api_key:      Optional[str] = None,
                 client:       Any = None):
        """Construct the client.

        Args:
          model:         default model id (overridable per call)
          max_tokens:    default max_tokens for completions
          timeout_secs:  per-request timeout
          max_retries:   total retries before giving up on transient errors
          api_key:       explicit key override (else keyring → env)
          client:        injected SDK client (used by tests; bypasses keyring)
        """
        self.model        = model
        self.max_tokens   = max_tokens
        self.timeout_secs = timeout_secs
        self.max_retries  = max_retries
        self._stats       = ClientStats()
        self._lock        = threading.Lock()

        if client is not None:
            self._client = client
            return

        key = api_key or self._resolve_api_key()
        if not key:
            raise RuntimeError(
                "Anthropic API key not found. Set keyring entry "
                f"service='{KEYRING_SERVICE}', username='{KEYRING_USERNAME}', "
                "or export ANTHROPIC_API_KEY."
            )
        import anthropic
        # Disable SDK-level retries — our wrapper handles retry above.
        # Letting the SDK retry compounds timeouts (e.g. 600s × 3 = 30 min
        # before our exception handler even sees the failure).
        self._client = anthropic.Anthropic(
            api_key=key, timeout=timeout_secs, max_retries=0,
        )

    @staticmethod
    def _resolve_api_key() -> str:
        env_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if env_key:
            return env_key
        try:
            import keyring
            return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME) or ""
        except Exception:
            return ""

    # ----- Stats -----

    def stats(self) -> ClientStats:
        """Snapshot of cumulative stats. Thread-safe."""
        with self._lock:
            return ClientStats(
                calls=self._stats.calls,
                successes=self._stats.successes,
                failures=self._stats.failures,
                retries=self._stats.retries,
                input_tokens=self._stats.input_tokens,
                output_tokens=self._stats.output_tokens,
                cost_usd=self._stats.cost_usd,
                rate_limit_requests_limit=self._stats.rate_limit_requests_limit,
                rate_limit_requests_remaining=self._stats.rate_limit_requests_remaining,
                rate_limit_input_tokens_limit=self._stats.rate_limit_input_tokens_limit,
                rate_limit_input_tokens_remaining=self._stats.rate_limit_input_tokens_remaining,
                rate_limit_output_tokens_limit=self._stats.rate_limit_output_tokens_limit,
                rate_limit_output_tokens_remaining=self._stats.rate_limit_output_tokens_remaining,
                rate_limit_min_requests_seen=self._stats.rate_limit_min_requests_seen,
                rate_limit_429_count=self._stats.rate_limit_429_count,
            )

    def _record_outcome(self, result: CallResult) -> None:
        with self._lock:
            self._stats.calls += 1
            if result.error:
                self._stats.failures += 1
                # Cheap classification of "this was a rate-limit failure".
                err_l = result.error.lower()
                if "rate" in err_l or "429" in err_l or "ratelimit" in err_l:
                    self._stats.rate_limit_429_count += 1
            else:
                self._stats.successes += 1
            self._stats.retries += max(0, result.attempts - 1)
            self._stats.input_tokens += result.input_tokens
            self._stats.output_tokens += result.output_tokens
            self._stats.cost_usd += result.cost_usd

    # Header keys Anthropic returns on every successful response.
    _RL_HEADERS = (
        "anthropic-ratelimit-requests-limit",
        "anthropic-ratelimit-requests-remaining",
        "anthropic-ratelimit-input-tokens-limit",
        "anthropic-ratelimit-input-tokens-remaining",
        "anthropic-ratelimit-output-tokens-limit",
        "anthropic-ratelimit-output-tokens-remaining",
    )

    def _record_rate_limit_headers(self, headers: dict) -> None:
        """Update ClientStats from Anthropic's rate-limit response headers.

        Headers come lowercase. We track the latest values plus the
        tightest-headroom-seen for requests (so we know how close we
        got to the ceiling at peak).
        """
        # Normalize keys to lowercase since httpx keeps original casing.
        norm = {k.lower(): v for k, v in headers.items()}
        def _int(key: str) -> int:
            v = norm.get(key)
            try:
                return int(v) if v is not None else 0
            except (ValueError, TypeError):
                return 0
        with self._lock:
            self._stats.rate_limit_requests_limit       = _int("anthropic-ratelimit-requests-limit")        or self._stats.rate_limit_requests_limit
            self._stats.rate_limit_requests_remaining   = _int("anthropic-ratelimit-requests-remaining")
            self._stats.rate_limit_input_tokens_limit   = _int("anthropic-ratelimit-input-tokens-limit")    or self._stats.rate_limit_input_tokens_limit
            self._stats.rate_limit_input_tokens_remaining = _int("anthropic-ratelimit-input-tokens-remaining")
            self._stats.rate_limit_output_tokens_limit  = _int("anthropic-ratelimit-output-tokens-limit")   or self._stats.rate_limit_output_tokens_limit
            self._stats.rate_limit_output_tokens_remaining = _int("anthropic-ratelimit-output-tokens-remaining")
            # Track minimum requests-remaining we've seen across the run
            # — the lower this gets, the closer we are to the ceiling.
            req_rem = self._stats.rate_limit_requests_remaining
            if req_rem and (self._stats.rate_limit_min_requests_seen == 0
                            or req_rem < self._stats.rate_limit_min_requests_seen):
                self._stats.rate_limit_min_requests_seen = req_rem
            # Periodic print (every ~50 calls) for live visibility.
            if self._stats.calls > 0 and self._stats.calls % 50 == 0:
                import sys as _sys
                lim_r  = self._stats.rate_limit_requests_limit
                rem_r  = self._stats.rate_limit_requests_remaining
                lim_in = self._stats.rate_limit_input_tokens_limit
                rem_in = self._stats.rate_limit_input_tokens_remaining
                lim_out = self._stats.rate_limit_output_tokens_limit
                rem_out = self._stats.rate_limit_output_tokens_remaining
                print(f"  [ratelimit] req {rem_r}/{lim_r}, "
                      f"in-tok {rem_in}/{lim_in}, "
                      f"out-tok {rem_out}/{lim_out}, "
                      f"min-req-seen {self._stats.rate_limit_min_requests_seen}, "
                      f"429-hits {self._stats.rate_limit_429_count}",
                      file=_sys.stderr, flush=True)

    # ----- Single call -----

    def call(self,
             *,
             system:         str = "",
             user:           str = "",
             messages:       Optional[list[dict]] = None,
             model:          Optional[str] = None,
             max_tokens:     Optional[int] = None,
             temperature:    float = 0.0) -> CallResult:
        """One synchronous Anthropic API call with retry on transient errors.

        Provide either `messages` (list of role/content dicts) or `user`
        (a single user message string) — not both. `system` is the
        system prompt, optional.

        Returns a CallResult; never raises for transient API errors —
        result.error will be non-empty on terminal failure. Hard config
        errors (no API key, programmer error) still raise.
        """
        if messages is None:
            if not user:
                raise ValueError("call() needs either messages or user")
            messages = [{"role": "user", "content": user}]
        target_model = model or self.model
        target_max   = max_tokens or self.max_tokens

        result = CallResult(model=target_model)
        start  = time.monotonic()
        # Estimate input size for diagnostic log
        approx_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
        approx_tokens += estimate_tokens(system) if system else 0

        for attempt in range(1, self.max_retries + 1):
            result.attempts = attempt
            attempt_start = time.monotonic()
            try:
                kwargs: dict[str, Any] = {
                    "model":      target_model,
                    "max_tokens": target_max,
                    "messages":   messages,
                }
                if system:
                    kwargs["system"] = system
                if temperature is not None:
                    kwargs["temperature"] = temperature
                # Streaming keeps the HTTP connection alive while Sonnet
                # generates a long response, avoiding read-timeout failures
                # for 30K+ token outputs.
                text_parts: list[str] = []
                final_message = None
                stream_response_headers = None
                with self._client.messages.stream(**kwargs) as stream:
                    for chunk in stream.text_stream:
                        text_parts.append(chunk)
                    final_message = stream.get_final_message()
                    # Capture rate-limit headers if the SDK exposes them.
                    try:
                        stream_response_headers = dict(stream.response.headers)
                    except Exception:
                        stream_response_headers = None
                if stream_response_headers:
                    self._record_rate_limit_headers(stream_response_headers)
                # Per-call diagnostic for slow calls (>30s) — printed to
                # stderr so they appear in the pilot log alongside batch
                # progress.
                elapsed = time.monotonic() - attempt_start
                if elapsed > 30.0:
                    import sys as _sys
                    print(f"  [api] {target_model} ~{approx_tokens}tok in "
                          f"{elapsed:.0f}s (attempt {attempt})",
                          file=_sys.stderr, flush=True)
                result.text = "".join(text_parts)
                usage = getattr(final_message, "usage", None) if final_message else None
                if usage is not None:
                    result.input_tokens  = int(getattr(usage, "input_tokens", 0))
                    result.output_tokens = int(getattr(usage, "output_tokens", 0))
                result.cost_usd = estimate_cost_usd(
                    target_model, result.input_tokens, result.output_tokens,
                )
                result.error = ""
                break
            except Exception as e:
                err_text = str(e)
                elapsed = time.monotonic() - attempt_start
                # Classify retriable vs terminal.
                is_retriable = self._is_retriable(e, err_text)
                import sys as _sys
                print(f"  [api] {target_model} ~{approx_tokens}tok FAILED in "
                      f"{elapsed:.0f}s (attempt {attempt}): "
                      f"{type(e).__name__}: {err_text[:120]}",
                      file=_sys.stderr, flush=True)
                if is_retriable and attempt < self.max_retries:
                    # Prefer Anthropic's retry-after header on 429s — it's
                    # the only sleep duration that actually matches when the
                    # rate-limit window refills. Exponential backoff alone
                    # races through retries in seconds and re-hits the wall.
                    retry_after = self._extract_retry_after(e)
                    if retry_after is not None:
                        sleep_for = retry_after
                        print(f"  [api] honoring retry-after={sleep_for:.1f}s "
                              f"(attempt {attempt})",
                              file=_sys.stderr, flush=True)
                    else:
                        sleep_for = self._backoff(attempt)
                    time.sleep(sleep_for)
                    continue
                result.text  = ""
                result.error = err_text[:500]
                break

        result.duration_secs = time.monotonic() - start
        self._record_outcome(result)
        return result

    @staticmethod
    def _is_retriable(exc: Exception, msg: str) -> bool:
        # anthropic SDK exposes typed exceptions but we keep this loose so
        # the wrapper works with mocked clients in tests too.
        cls_name = type(exc).__name__
        if "RateLimit" in cls_name or "Overloaded" in cls_name:
            return True
        if "APIConnectionError" in cls_name or "Timeout" in cls_name:
            return True
        # status code probing
        status = getattr(exc, "status_code", None)
        if status in (408, 425, 429, 500, 502, 503, 504):
            return True
        msg_l = msg.lower()
        if any(t in msg_l for t in ("rate limit", "overloaded", "timeout",
                                       "temporarily")):
            return True
        return False

    @staticmethod
    def _backoff(attempt: int) -> float:
        base = min(60.0, 1.5 ** attempt)
        return base + random.uniform(0.0, base * 0.25)

    # Sanity cap on retry-after — anything bigger is treated as "give up
    # for this attempt" and falls back to standard backoff. 600s = the
    # per-call timeout already in place; longer waits aren't useful.
    _RETRY_AFTER_MAX_SECS = 600.0

    @classmethod
    def _extract_retry_after(cls, exc: Exception) -> Optional[float]:
        """Parse `retry-after` (seconds) from an Anthropic exception's
        response headers. Returns None if absent, malformed, or out of
        range. Caller falls back to exponential backoff in those cases.

        Anthropic returns the header on 429 RateLimitError (and sometimes
        on 529 Overloaded). The SDK exposes the raw httpx response on
        `exc.response`; headers come back lowercase via httpx but we
        normalize defensively.
        """
        response = getattr(exc, "response", None)
        if response is None:
            return None
        headers = getattr(response, "headers", None)
        if headers is None:
            return None
        # httpx headers are case-insensitive but we normalize anyway.
        raw = None
        try:
            raw = headers.get("retry-after")
        except Exception:
            try:
                raw = {k.lower(): v for k, v in dict(headers).items()}.get(
                    "retry-after"
                )
            except Exception:
                return None
        if raw is None:
            return None
        try:
            secs = float(raw)
        except (ValueError, TypeError):
            return None
        if secs <= 0 or secs > cls._RETRY_AFTER_MAX_SECS:
            return None
        return secs

    # ----- Concurrent batch -----

    def call_batch(self,
                    items:        Sequence[Any],
                    fn:           Callable[[Any], dict],
                    max_workers:  int = 8) -> list[CallResult]:
        """Run `fn(item) → kwargs-for-call()` for each item across a thread
        pool. Returns CallResults in the SAME ORDER as `items`.

        Rate-limit / retry handling lives in `call()`; this just
        provides the concurrency loop.
        """
        results: list[Optional[CallResult]] = [None] * len(items)
        if not items:
            return []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self.call, **fn(item)): i
                for i, item in enumerate(items)
            }
            for fut in as_completed(futures):
                idx = futures[fut]
                results[idx] = fut.result()
        return [r for r in results if r is not None]


__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_TIMEOUT_SECS",
    "DEFAULT_MAX_RETRIES",
    "KEYRING_SERVICE",
    "KEYRING_USERNAME",
    "estimate_tokens",
    "estimate_cost_usd",
    "CallResult",
    "ClientStats",
    "AnthropicClient",
]
