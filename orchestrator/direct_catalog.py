"""Direct-vendor model catalogue resolver for prefer-direct routing.

When Ora is about to dispatch an OpenRouter ``vendor/model`` id and the user
has the vendor's own key, prefer-direct wants to call the vendor directly.
But the OpenRouter id minus its prefix is NOT always the vendor's native
model id (Anthropic dotted vs hyphen; Mistral/Qwen ``*-latest`` aliases;
DeepSeek/Moonshot dated snapshots; Meta/NVIDIA namespaced + CamelCase). A
blind prefix-strip sends an id the vendor rejects, so the call fails and Ora
falls back to OpenRouter (no markup saved, wasted round-trip every call).

This module makes prefer-direct catalogue-aware: it fetches each vendor's own
model list (``GET <base>/models``, cached) and resolves the OpenRouter
remainder to the correct native id — or reports the model isn't offered
directly, so the caller skips the direct attempt and uses OpenRouter with no
wasted call.

Safety is the overriding rule. The reactive OpenRouter fallback can catch a
direct call that *errors*, but it CANNOT catch a wrong-but-valid id that
returns 200 from a different model. So resolution only returns ``"direct"``
when the catalogue id is provably the SAME model — an exact match, a pure
format fix (dotted→hyphen), a vendor ``-latest`` alias for an *unpinned*
request, or a catalogue id that reduces (namespace + date-snapshot strip) to
exactly the requested id. Anything ambiguous → ``"skip"`` → OpenRouter.

Public API
----------
``resolve(entry, or_remainder, key) -> (decision, model_id)`` where decision is
  * ``"direct"``   — offered directly; call with ``model_id`` (native id)
  * ``"skip"``     — catalogue fetched, model NOT offered directly → OpenRouter
  * ``"unknown"``  — catalogue unreachable / resolver off → ``model_id`` is the
                     bare remainder; caller may try optimistically (old behaviour)

Tuning (env)
------------
* ``ORA_DIRECT_CATALOG``          — off when 0/false/no/off (default on)
* ``ORA_DIRECT_CATALOG_TTL_H``    — catalogue cache lifetime, hours (default 12)
* ``ORA_DIRECT_CATALOG_TIMEOUT_S``— per-fetch network timeout, seconds (default 4)
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request

try:  # pragma: no cover - import shim
    from orchestrator import network_policy
except ImportError:  # pragma: no cover
    import network_policy

# in-memory caches
#   _CATALOG_CACHE: provider_id -> (expiry_epoch, frozenset(native_ids) | None)
#   _RESOLVE_CACHE: (provider_id, or_remainder) -> (decision, model_id)
#   _PID_LOCKS:     provider_id -> Lock  (single-flight per vendor fetch)
_CATALOG_CACHE: dict = {}
_RESOLVE_CACHE: dict = {}
_PID_LOCKS: dict = {}
_lock = threading.Lock()

# A model list is tiny (well under 1 MB); cap the read so a hostile/broken
# endpoint streaming an unbounded body can't exhaust memory or stall forever.
_MAX_BODY_BYTES = 8 * 1024 * 1024


def _enabled() -> bool:
    v = (os.environ.get("ORA_DIRECT_CATALOG", "1") or "").strip().lower()
    return v not in ("0", "false", "no", "off")


def _ttl_seconds() -> float:
    try:
        return float(os.environ.get("ORA_DIRECT_CATALOG_TTL_H", "12")) * 3600.0
    except (TypeError, ValueError):
        return 12 * 3600.0


def _timeout_seconds() -> float:
    try:
        return max(1.0, float(os.environ.get("ORA_DIRECT_CATALOG_TIMEOUT_S", "4")))
    except (TypeError, ValueError):
        return 4.0


def _cache_dir() -> str:
    home = os.environ.get("ORA_HOME") or os.path.expanduser("~/ora")
    return os.path.join(home, "cache", "direct-catalogs")


# ── catalogue fetch ──────────────────────────────────────────────────────────

def _models_request(entry: dict, key: str):
    """Return a urllib Request that lists the vendor's models, or None when we
    don't know how to list this provider's catalogue."""
    pid = entry.get("id")
    base = (entry.get("base_url") or "").rstrip("/")
    if pid == "anthropic":
        # Native Messages API has no base_url in the registry; /v1/models is the
        # documented list endpoint (x-api-key + anthropic-version).
        return urllib.request.Request(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            method="GET",
        )
    if not base:
        return None
    # OpenAI-compatible (incl. the OpenAI + Gemini-compat bases): GET {base}/models
    return urllib.request.Request(
        base + "/models",
        headers={"Authorization": "Bearer " + key},
        method="GET",
    )


def _parse_ids(payload) -> set:
    """Pull model ids from an OpenAI-/Anthropic-style ``{"data": [{"id": …}]}``
    (also tolerates ``{"models": [...]}`` and bare lists)."""
    ids = set()
    items = None
    if isinstance(payload, dict):
        items = payload.get("data")
        if items is None:
            items = payload.get("models")
    elif isinstance(payload, list):
        items = payload
    for it in (items or []):
        if isinstance(it, dict):
            mid = it.get("id") or it.get("name") or it.get("model")
            if isinstance(mid, str) and mid:
                # Gemini's compat list prefixes "models/"; strip it.
                ids.add(mid.split("/", 1)[1] if mid.startswith("models/") else mid)
        elif isinstance(it, str) and it:
            ids.add(it)
    return ids


def _fetch_ids(entry: dict, key: str):
    """Fetch the vendor's model-id set. Returns a set, or None on any failure.

    Bounded: a per-op timeout plus a hard cap on bytes read, so a slow or
    unbounded ``/models`` body can't stall the live dispatch indefinitely.
    """
    req = _models_request(entry, key)
    if req is None or not key:
        return None
    try:
        if entry.get("id") == "openrouter":
            raw, _destination = network_policy.openrouter_request_bytes(
                req.full_url,
                headers=dict(req.header_items()),
                timeout=_timeout_seconds(),
                max_bytes=_MAX_BODY_BYTES,
            )
        else:
            with urllib.request.urlopen(req, timeout=_timeout_seconds()) as resp:
                raw = resp.read(_MAX_BODY_BYTES + 1)
        if len(raw) > _MAX_BODY_BYTES:
            return None  # implausibly large for a model list — treat as unreachable
        data = json.loads(raw.decode("utf-8", "replace"))
        ids = _parse_ids(data)
        return ids or None
    except Exception:
        return None


def _disk_path(pid: str) -> str:
    return os.path.join(_cache_dir(), pid + ".json")


def _read_disk(pid: str):
    try:
        with open(_disk_path(pid), "r", encoding="utf-8") as f:
            rec = json.load(f)
        if (time.time() - float(rec.get("fetched_at", 0))) < _ttl_seconds():
            ids = rec.get("ids")
            if isinstance(ids, list) and ids:
                return set(ids)
    except Exception:
        pass
    return None


def _write_disk(pid: str, ids: set) -> None:
    try:
        os.makedirs(_cache_dir(), exist_ok=True)
        tmp = _disk_path(pid) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"fetched_at": time.time(), "ids": sorted(ids)}, f)
        os.replace(tmp, _disk_path(pid))
    except Exception:
        pass


def _pid_lock(pid: str) -> threading.Lock:
    with _lock:
        lk = _PID_LOCKS.get(pid)
        if lk is None:
            lk = threading.Lock()
            _PID_LOCKS[pid] = lk
        return lk


def _load_catalog(entry: dict, key: str):
    """Return the vendor's native model-id set (cached), or None if unavailable.

    Single-flight per vendor: only the first thread fetches; concurrent
    same-vendor callers block on the per-pid lock and reuse the result rather
    than each firing their own ``/models`` request (the network fetch holds
    only the per-pid lock, so other vendors aren't blocked).
    """
    pid = entry.get("id")
    with _lock:
        hit = _CATALOG_CACHE.get(pid)
        if hit and hit[0] > time.time():
            return hit[1]
    with _pid_lock(pid):
        # double-checked: another thread may have just populated the cache
        with _lock:
            hit = _CATALOG_CACHE.get(pid)
            if hit and hit[0] > time.time():
                return hit[1]
        ids = _read_disk(pid)
        if ids is None:
            ids = _fetch_ids(entry, key)
            if ids:
                _write_disk(pid, ids)
        with _lock:
            # full TTL on success; brief TTL on a miss so a flaky network
            # recovers reasonably without a fetch storm.
            ttl = _ttl_seconds() if ids else 300.0
            _CATALOG_CACHE[pid] = (time.time() + ttl, ids)
        return ids


# ── id matching ──────────────────────────────────────────────────────────────

# Trailing date / snapshot decoration: -0324, -2411, -v3-0324, -0711-preview,
# ISO -2025-04-16, Cohere-style -08-2024. Used to recognise that two ids are
# the same model at different snapshots — never to re-point a pinned request.
_DATE_SUFFIX = re.compile(
    r"-(?:v\d+-)?(?:\d{4}-\d{2}-\d{2}|\d{2}-\d{4}|\d{3,8})(?:-preview)?$"
)


def _base_id(or_id: str) -> str:
    """Strip a trailing date / snapshot suffix (``deepseek-chat-v3-0324`` →
    ``deepseek-chat``)."""
    return _DATE_SUFFIX.sub("", or_id)


def _is_pinned(or_id: str) -> bool:
    """True when the id carries an explicit date/snapshot the caller chose."""
    return _base_id(or_id) != or_id


def _reduce(model_id: str) -> str:
    """Reduce a catalogue id to its model identity: drop a leading ``vendor/``
    namespace and a trailing date snapshot, lowercased. Two ids that reduce to
    the same string are the same model (modulo namespace/snapshot)."""
    x = model_id.split("/")[-1]
    return _base_id(x).lower()


def _candidates(or_id: str) -> list:
    """Ordered exact-match candidate forms for an OpenRouter remainder.

    Only safe, identity-preserving transforms: the id itself, a dotted→hyphen
    version fix, and — *only for an unpinned request* — the vendor ``-latest``
    alias. We deliberately do NOT synthesise a ``-latest``/base alias for a
    request that pinned an explicit snapshot, because that would re-point it to
    a different snapshot (a silent wrong-model).
    """
    out: list = []

    def add(x):
        if x and x not in out:
            out.append(x)

    add(or_id)
    if "." in or_id:
        add(re.sub(r"(?<=\d)\.(?=\d)", "-", or_id))
    if not _is_pinned(or_id):
        add(or_id + "-latest")
    return out


def _match(or_id: str, catalog: set):
    """Resolve an OpenRouter remainder to a native id in ``catalog``, or None.

    Returns a hit ONLY when it is provably the same model:
      1. exact over the candidate forms,
      2. case-insensitive over the candidate forms,
      3. a UNIQUE catalogue id whose namespace/snapshot-reduced form equals the
         request (or, for an unpinned request, its base) — this catches NVIDIA
         namespacing and dated-only snapshots without ever accepting a
         containment of a *different* model (``grok-3`` ≠ ``grok-3-mini``).
    Ambiguity or no structural equality → None (caller uses OpenRouter).
    """
    cands = _candidates(or_id)
    # 1. exact (case-sensitive)
    for c in cands:
        if c in catalog:
            return c
    # 2. case-insensitive
    low = {m.lower(): m for m in catalog}
    for c in cands:
        if c.lower() in low:
            return low[c.lower()]
    # 3. structural equality (namespace + snapshot reduced), UNIQUE only
    targets = {c.lower() for c in cands}
    if not _is_pinned(or_id):
        targets.add(_base_id(or_id).lower())
    hits = [m for m in catalog if _reduce(m) in targets]
    if len(hits) == 1:
        return hits[0]
    return None


# ── public API ───────────────────────────────────────────────────────────────

def resolve(entry: dict, or_remainder: str, key: str):
    """Resolve an OpenRouter ``vendor/model`` remainder for direct dispatch.

    Returns ``(decision, model_id)``:
      ("direct", native_id)  offered directly — call with native_id
      ("skip", None)         catalogue fetched, model not offered directly
      ("unknown", remainder) resolver off / catalogue unreachable — optimistic
    """
    if not _enabled():
        return ("unknown", or_remainder)
    pid = entry.get("id")
    rk = (pid, or_remainder)
    with _lock:
        cached = _RESOLVE_CACHE.get(rk)
    if cached is not None:
        return cached

    catalog = _load_catalog(entry, key)
    if not catalog:
        # Don't cache "unknown" — recover once the catalogue loads.
        return ("unknown", or_remainder)
    native = _match(or_remainder, catalog)
    res = ("direct", native) if native else ("skip", None)
    with _lock:
        _RESOLVE_CACHE[rk] = res  # caches negatives too, so a not-listed model
        #                           isn't re-resolved on every call
    return res


def reset_caches() -> None:
    """Test helper — clear in-memory caches."""
    with _lock:
        _CATALOG_CACHE.clear()
        _RESOLVE_CACHE.clear()
        _PID_LOCKS.clear()


__all__ = ["resolve", "reset_caches"]
