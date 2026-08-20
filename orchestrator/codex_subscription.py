"""Isolated ChatGPT subscription transport backed by the Codex Python SDK.

The SDK owns browser login, refresh, keychain persistence, model discovery,
and turns.  Ora supplies only a dedicated ``CODEX_HOME`` and a locked-down
completion surface; direct OpenAI API credentials are deliberately scrubbed
so this transport can never fall through to metered API billing.
"""
from __future__ import annotations

import importlib
import json
import math
import tempfile
import threading
from pathlib import Path
from typing import Any

try:
    from . import runtime_paths
except ImportError:  # direct script-style import from sys.path
    import runtime_paths  # type: ignore


CODEX_HOME = Path(runtime_paths.DATA_DIR) / "codex-subscription"

_CONFIG_OVERRIDES = (
    'cli_auth_credentials_store="keyring"',
    'model_provider="openai"',
    'forced_login_method="chatgpt"',
    "features.shell_tool=false",
    "features.multi_agent=false",
    "features.multi_agent_v2={enabled=false,max_concurrent_threads_per_session=1}",
    'web_search="disabled"',
    "mcp_servers={}",
)

_DEVELOPER_INSTRUCTIONS = (
    "Act only as a completion model for Ora. Do not call tools, run "
    "commands, browse the web, inspect the working directory, or read files. "
    "Use only the system instructions, conversation transcript, and any image "
    "supplied in this turn, and return only the assistant response."
)

_state_lock = threading.RLock()
_lifecycle_lock = threading.Lock()
_client: Any | None = None
_login_handle: Any | None = None
_login_auth_url: str | None = None
_login_generation = 0
_last_error: "CodexSubscriptionError | None" = None
_reauth_required = False
_catalog_revision = 0
_model_fingerprint: tuple[
    tuple[str, str, tuple[str, ...], tuple[str, ...]], ...
] = ()

_SELECTOR_COST_FIELD = "_subscription_selector_cost_per_m"
_INHERITED_METRIC_FIELDS = (
    "aa_intelligence_index",
    "aa_coding_index",
    "aa_agentic_index",
    "intelligence_score",
    "size_bucket",
    "parameters_b",
    "release_date",
    "output_tokens_per_second",
    "or_throughput_tps",
    "latency_ttft_seconds",
    "latency_total_seconds",
    "or_ttft_ms",
    "reasoning_model",
    "reasoning_capable",
    "forced_reasoning",
)


class CodexSubscriptionError(RuntimeError):
    """A classified, browser-safe failure from the subscription boundary."""

    def __init__(self, kind: str, safe_message: str):
        super().__init__(safe_message)
        self.kind = kind
        self.safe_message = safe_message


def is_configured() -> bool:
    """Whether Ora has ever initiated its isolated ChatGPT connection."""
    return CODEX_HOME.is_dir()


def _sdk_module():
    try:
        return importlib.import_module("openai_codex")
    except Exception:
        raise CodexSubscriptionError(
            "dependency_unavailable",
            "ChatGPT subscription support is unavailable because the "
            "openai-codex package is not installed. Re-run the Ora installer.",
        ) from None


def _classified_error(exc: BaseException) -> CodexSubscriptionError:
    if isinstance(exc, CodexSubscriptionError):
        return exc
    text = f"{type(exc).__name__}: {exc}".lower()
    if any(token in text for token in (
        "keyring", "credential storage", "credentials store",
        "secret service", "secure storage", "password storage",
    )):
        return CodexSubscriptionError(
            "secure_storage_unavailable",
            "Secure OS credential storage is unavailable. Configure a system "
            "keychain backend, then try connecting again.",
        )
    if any(token in text for token in (
        "usage limit", "rate limit", "rate_limit", "too many requests",
        "status 429", "http 429", "usage_limit_exceeded",
    )):
        return CodexSubscriptionError(
            "rate_limited",
            "The ChatGPT subscription is currently rate-limited. Try again "
            "after the account's usage window resets.",
        )
    if any(token in text for token in (
        "unauthorized", "authentication", "not logged in", "login required",
        "requires openai auth", "requires_openai_auth", "token expired",
        "reauth", "sign in",
    )):
        return CodexSubscriptionError(
            "reauth_required",
            "ChatGPT sign-in is required. Disconnect and reconnect the Ora "
            "account in Settings.",
        )
    return CodexSubscriptionError(
        "unavailable",
        "The ChatGPT subscription connection is unavailable. Restart Ora or "
        "try again later.",
    )


def _new_client(create_home: bool):
    global _client
    with _state_lock:
        if _client is not None:
            return _client
        if not CODEX_HOME.is_dir():
            if not create_home:
                return None
            CODEX_HOME.mkdir(parents=True, exist_ok=True)
        sdk = _sdk_module()
        config = sdk.CodexConfig(
            cwd=str(CODEX_HOME),
            env={
                "CODEX_HOME": str(CODEX_HOME),
                "OPENAI_API_KEY": "",
                "CODEX_API_KEY": "",
                "CODEX_ACCESS_TOKEN": "",
            },
            config_overrides=_CONFIG_OVERRIDES,
        )
        try:
            _client = sdk.Codex(config)
        except Exception as exc:
            _client = None
            raise _classified_error(exc) from None
        return _client


def _enum_value(value: Any) -> str:
    if value is None:
        return ""
    value = getattr(value, "value", value)
    return str(value)


def _account_root(client: Any) -> Any | None:
    response = client.account(refresh_token=False)
    account = getattr(response, "account", None)
    return getattr(account, "root", account)


def _is_chatgpt_account(account: Any) -> bool:
    return bool(account) and _enum_value(getattr(account, "type", "")).lower() == "chatgpt"


def _base_status(state: str, message: str = "") -> dict:
    with _state_lock:
        revision = _catalog_revision
    return {
        "state": state,
        "connected": state == "connected",
        "configured": is_configured(),
        "message": message,
        "catalog_revision": revision,
    }


def _connected_status(account: Any) -> dict:
    payload = _base_status("connected")
    plan = _enum_value(getattr(account, "plan_type", ""))
    payload.update({
        "email": str(getattr(account, "email", "") or ""),
        "plan": plan.replace("_", " ").replace("-", " ").title(),
    })
    return payload


def status() -> dict:
    """Return a token-free, browser-safe account status snapshot."""
    global _last_error
    try:
        _sdk_module()
    except CodexSubscriptionError as exc:
        return _base_status(exc.kind, exc.safe_message)

    if not is_configured():
        return _base_status("disconnected", "Not connected.")

    with _state_lock:
        reauth = _reauth_required
        connecting = _login_handle is not None
        last_error = _last_error
    if reauth:
        return _base_status(
            "error",
            "ChatGPT sign-in is required. Disconnect and reconnect the Ora "
            "account in Settings.",
        )

    try:
        client = _new_client(create_home=False)
        account = _account_root(client) if client is not None else None
    except Exception as exc:
        err = _classified_error(exc)
        with _state_lock:
            _last_error = err
        return _base_status("error", err.safe_message)

    if _is_chatgpt_account(account):
        with _state_lock:
            _last_error = None
        return _connected_status(account)
    if connecting:
        return _base_status(
            "connecting", "Complete ChatGPT sign-in in the browser."
        )
    if last_error is not None:
        return _base_status("error", last_error.safe_message)
    if account:
        return _base_status(
            "error",
            "Ora's isolated Codex session is not signed in with ChatGPT. "
            "Disconnect it and connect again.",
        )
    return _base_status("disconnected", "Not connected.")


def _finish_login(handle: Any, generation: int) -> None:
    global _login_handle, _login_auth_url, _last_error
    global _reauth_required, _catalog_revision
    try:
        completed = handle.wait()
        success = bool(getattr(completed, "success", False))
        if not success:
            error = CodexSubscriptionError(
                "login_failed",
                "ChatGPT sign-in did not complete. Try connecting again.",
            )
            account = None
        else:
            try:
                client = _new_client(create_home=False)
                account = _account_root(client) if client is not None else None
                error = None if _is_chatgpt_account(account) else CodexSubscriptionError(
                    "login_failed",
                    "ChatGPT sign-in did not complete. Try connecting again.",
                )
            except Exception as exc:
                account = None
                error = _classified_error(exc)
    except Exception as exc:
        account = None
        error = _classified_error(exc)

    with _state_lock:
        if generation != _login_generation or handle is not _login_handle:
            return
        _login_handle = None
        _login_auth_url = None
        if _is_chatgpt_account(account):
            _last_error = None
            _reauth_required = False
            _catalog_revision += 1
        else:
            _last_error = error


def connect() -> dict:
    """Start one browser login and return its URL without waiting."""
    global _login_handle, _login_auth_url, _login_generation, _last_error
    global _reauth_required

    # Import before creating CODEX_HOME: a missing optional dependency must
    # not make a never-configured user look configured.
    try:
        _sdk_module()
    except CodexSubscriptionError as exc:
        return _base_status(exc.kind, exc.safe_message)

    with _lifecycle_lock:
        try:
            client = _new_client(create_home=True)
        except Exception as exc:
            err = _classified_error(exc)
            with _state_lock:
                _last_error = err
            return _base_status("error", err.safe_message)

        with _state_lock:
            if _login_handle is not None:
                payload = _base_status(
                    "connecting", "Complete ChatGPT sign-in in the browser."
                )
                payload["auth_url"] = _login_auth_url
                return payload
            reauth = _reauth_required

        if not reauth:
            try:
                account = _account_root(client)
                if _is_chatgpt_account(account):
                    return _connected_status(account)
            except Exception as exc:
                err = _classified_error(exc)
                if err.kind not in {"reauth_required"}:
                    with _state_lock:
                        _last_error = err
                    return _base_status("error", err.safe_message)

        try:
            handle = client.login_chatgpt()
            auth_url = str(getattr(handle, "auth_url", "") or "")
            if not auth_url.startswith(("https://", "http://")):
                try:
                    handle.cancel()
                except Exception:
                    pass
                raise CodexSubscriptionError(
                    "login_failed",
                    "ChatGPT sign-in could not be started. Try connecting again.",
                )
        except Exception as exc:
            err = _classified_error(exc)
            with _state_lock:
                _last_error = err
            return _base_status("error", err.safe_message)

        with _state_lock:
            _login_generation += 1
            generation = _login_generation
            _login_handle = handle
            _login_auth_url = auth_url
            _last_error = None
            _reauth_required = False

        threading.Thread(
            target=_finish_login,
            args=(handle, generation),
            name="ora-chatgpt-login",
            daemon=True,
        ).start()
        payload = _base_status(
            "connecting", "Complete ChatGPT sign-in in the browser."
        )
        payload["auth_url"] = auth_url
        return payload


def disconnect() -> dict:
    """Cancel any login and log out only Ora's dedicated Codex home."""
    global _login_handle, _login_auth_url, _login_generation, _last_error
    global _reauth_required, _catalog_revision, _model_fingerprint

    if not is_configured():
        return _base_status("disconnected", "Not connected.")

    with _lifecycle_lock:
        with _state_lock:
            _login_generation += 1
            handle = _login_handle
            _login_handle = None
            _login_auth_url = None
        if handle is not None:
            try:
                handle.cancel()
            except Exception:
                pass
        try:
            client = _new_client(create_home=False)
            if client is not None:
                client.logout()
        except Exception as exc:
            err = _classified_error(exc)
            with _state_lock:
                _last_error = err
            return _base_status("error", err.safe_message)
        with _state_lock:
            _last_error = None
            _reauth_required = False
            _model_fingerprint = ()
            _catalog_revision += 1
    return status()


def _object_value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _read_model_map(path: Path) -> dict[str, dict]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    models = payload.get("models") if isinstance(payload, dict) else None
    if isinstance(models, dict):
        return {
            str(model_id): model
            for model_id, model in models.items()
            if isinstance(model, dict)
        }
    if isinstance(models, list):
        return {
            str(model.get("id")): model
            for model in models
            if isinstance(model, dict) and model.get("id")
        }
    return {}


def _metric_sources() -> tuple[dict[str, dict], dict[str, dict]]:
    return (
        _read_model_map(runtime_paths.model_catalog_path()),
        _read_model_map(runtime_paths.model_registry_path()),
    )


def _enrich_endpoint(
    endpoint: dict,
    catalog_models: dict[str, dict],
    registry_models: dict[str, dict],
) -> dict:
    """Borrow selection facts only from the exact OpenAI API counterpart."""
    native_model = str(endpoint.get("model_id") or "").strip()
    counterpart_id = f"openai/{native_model}"
    catalog_row = catalog_models.get(counterpart_id) or {}
    registry_row = registry_models.get(counterpart_id) or {}
    if not catalog_row and not registry_row:
        return endpoint

    enriched = dict(endpoint)
    for field in _INHERITED_METRIC_FIELDS:
        value = registry_row.get(field)
        if value is None:
            value = catalog_row.get(field)
        if value is not None:
            enriched[field] = value

    context = catalog_row.get("context_window")
    if context is None:
        context = registry_row.get("context_length")
    if context is not None:
        enriched["context_window"] = context
        enriched["context_length"] = context

    if any(enriched.get(field) is not None for field in _INHERITED_METRIC_FIELDS):
        enriched["metrics_inherited_from"] = counterpart_id

    return enriched


def _published_blended_cost(
    counterpart_id: str,
    catalog_models: dict[str, dict],
    registry_models: dict[str, dict],
) -> float | None:
    catalog_row = catalog_models.get(counterpart_id) or {}
    value = (catalog_row.get("openrouter_pricing") or {}).get("blended_per_m")
    if value is None:
        pricing = (registry_models.get(counterpart_id) or {}).get("pricing") or {}
        value = pricing.get("blended_per_m")
        if value is None:
            input_per_token = pricing.get("input_per_token")
            output_per_token = pricing.get("output_per_token")
            if input_per_token is not None or output_per_token is not None:
                value = (
                    0.75 * float(input_per_token or 0)
                    + 0.25 * float(output_per_token or 0)
                ) * 1_000_000
    try:
        cost = float(value)
    except (TypeError, ValueError):
        return None
    return cost if math.isfinite(cost) and cost >= 0 else None


def _mark_reauth_required() -> None:
    global _reauth_required, _last_error, _catalog_revision, _model_fingerprint
    with _state_lock:
        if not _reauth_required:
            _catalog_revision += 1
        _reauth_required = True
        _model_fingerprint = ()
        _last_error = CodexSubscriptionError(
            "reauth_required",
            "ChatGPT sign-in is required. Disconnect and reconnect the Ora "
            "account in Settings.",
        )


def model_endpoints() -> list[dict]:
    """Discover the connected account's visible Codex models at runtime."""
    global _catalog_revision, _model_fingerprint
    if status().get("state") != "connected":
        return []
    try:
        client = _new_client(create_home=False)
        response = client.models(include_hidden=False)
        rows = list(getattr(response, "data", None) or [])
    except Exception as exc:
        err = _classified_error(exc)
        if err.kind == "reauth_required":
            _mark_reauth_required()
        return []

    catalog_models, registry_models = _metric_sources()
    endpoints: list[dict] = []
    for row in rows:
        if bool(_object_value(row, "hidden", False)):
            continue
        sdk_id = str(_object_value(row, "id", "") or "").strip()
        native_model = str(_object_value(row, "model", "") or sdk_id).strip()
        if not sdk_id or not native_model:
            continue
        modalities = {
            _enum_value(value).lower()
            for value in (_object_value(row, "input_modalities", None) or [])
        }
        if modalities and "text" not in modalities:
            continue
        input_modalities = (
            [value for value in ("text", "image") if value in modalities]
            + sorted(modalities.difference({"text", "image"}))
        ) if modalities else ["text"]
        output_values = {
            _enum_value(value).lower()
            for value in (_object_value(row, "output_modalities", None) or [])
        }
        output_modalities = (
            [value for value in ("text", "image") if value in output_values]
            + sorted(output_values.difference({"text", "image"}))
        ) or ["text"]
        display_name = str(
            _object_value(row, "display_name", "") or native_model
        )
        endpoint_id = f"codex-subscription:{sdk_id}"
        endpoint = {
            "id": endpoint_id,
            "type": "api",
            "status": "active",
            "enabled": True,
            "provider": "openai",
            "display_name": display_name,
            "description": str(_object_value(row, "description", "") or ""),
            "service": "codex-subscription",
            "model_id": native_model,
            "dispatch": "subscription",
            "vision_capable": "image" in modalities,
            "input_modalities": input_modalities,
            "output_modalities": output_modalities,
            "capabilities": {
                "tool_access": False,
                "file_system_access": False,
                "web_access": False,
                "retrieval_approach": "pre-assembled",
            },
            "subscription_provider": "OpenAI",
            "subscription_transport": "ChatGPT via the bundled Codex runtime",
            "subscription_default": bool(_object_value(row, "is_default", False)),
        }
        endpoints.append(_enrich_endpoint(
            endpoint, catalog_models, registry_models,
        ))

    endpoints.sort(key=lambda endpoint: endpoint["id"])
    fingerprint = tuple(
        (
            endpoint["id"], endpoint["model_id"],
            tuple(endpoint.get("input_modalities") or ()),
            tuple(endpoint.get("output_modalities") or ()),
        )
        for endpoint in endpoints
    )
    with _state_lock:
        if fingerprint != _model_fingerprint:
            _model_fingerprint = fingerprint
            _catalog_revision += 1
    return endpoints


def selector_candidates(endpoints: list[dict] | None = None) -> list[dict]:
    """Return connected, exact-counterpart candidates for paid preset bakes.

    The penny values are selection weights only. They never replace API
    pricing on the registry endpoint and generated profiles serialize only
    the subscription endpoint id.
    """
    if endpoints is None:
        source = model_endpoints()
        if not source:
            return []
        catalog_models, registry_models = _metric_sources()
    else:
        catalog_models, registry_models = _metric_sources()
        source = [
            _enrich_endpoint(dict(endpoint), catalog_models, registry_models)
            for endpoint in endpoints
        ]
    ranked: list[tuple[float, str, str, dict]] = []
    for endpoint in source:
        counterpart_id = endpoint.get("metrics_inherited_from")
        if not counterpart_id or endpoint.get("aa_intelligence_index") is None:
            continue
        published_cost = _published_blended_cost(
            counterpart_id, catalog_models, registry_models,
        )
        if published_cost is None:
            continue
        release = str(endpoint.get("release_date") or "9999-12-31")
        ranked.append((published_cost, release, endpoint["id"], endpoint))

    candidates: list[dict] = []
    for rank, (_cost, _release, _endpoint_id, endpoint) in enumerate(
        sorted(ranked, key=lambda item: item[:3]), start=1,
    ):
        candidate = dict(endpoint)
        candidate.update({
            "category": "chat",
            "is_free": False,
            _SELECTOR_COST_FIELD: rank / 100.0,
        })
        candidates.append(candidate)
    return candidates


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content or "")


def _compile_messages(messages: list[dict]) -> tuple[str | None, str]:
    system_parts: list[str] = []
    transcript: list[str] = []
    for message in messages or []:
        role = str(message.get("role") or "user").lower()
        text = _message_text(message.get("content"))
        if role == "system":
            if text:
                system_parts.append(text)
            continue
        transcript.append(f"[{role.upper()}]\n{text}")
    prompt = "\n\n".join(transcript).strip()
    if not prompt:
        prompt = "[USER]\nRespond to the supplied system instructions."
    return ("\n\n".join(system_parts).strip() or None), prompt


def validate_image_input(
    messages: list[dict],
    images: list[dict] | None,
    input_modalities: list[str] | None,
) -> dict | None:
    """Return the sole valid current-canvas image, without runtime effects."""
    if not images:
        return None
    advertised = {
        _enum_value(value).lower() for value in (input_modalities or [])
    }
    if "image" not in advertised:
        raise CodexSubscriptionError(
            "text_only_image_input",
            "The selected ChatGPT subscription model is text-only and "
            "cannot accept the current Exhibits canvas image.",
        )
    user_has_text = any(
        str(message.get("role") or "").lower() == "user"
        and _message_text(message.get("content")).strip()
        for message in messages or []
    )
    if (
        len(images) != 1
        or not user_has_text
        or not isinstance(images[0], dict)
        or images[0].get("source") != "v3_canvas_preview"
        or images[0].get("mime") != "image/png"
        or not isinstance(images[0].get("base64"), str)
        or not images[0]["base64"]
    ):
        raise CodexSubscriptionError(
            "invalid_image_input",
            "ChatGPT subscription image input requires exactly one current "
            "V3 Exhibits canvas PNG submitted with text.",
        )
    return images[0]


def run_completion(
    messages: list[dict],
    model: str,
    *,
    images: list[dict] | None = None,
    input_modalities: list[str] | None = None,
) -> dict:
    """Run one ephemeral, deny-all Codex turn."""
    if not model:
        raise CodexSubscriptionError(
            "invalid_model", "No ChatGPT subscription model was requested."
        )
    account_status = status()
    if account_status.get("state") != "connected":
        if _reauth_required:
            raise CodexSubscriptionError(
                "reauth_required",
                "ChatGPT sign-in is required. Disconnect and reconnect the "
                "Ora account in Settings.",
            )
        raise CodexSubscriptionError(
            "not_connected",
            "ChatGPT is not connected in Ora Settings.",
        )

    base_instructions, prompt = _compile_messages(messages)
    run_input: Any = prompt
    submitted_image = validate_image_input(
        messages, images, input_modalities,
    )

    sdk = _sdk_module()
    client = _new_client(create_home=False)
    if submitted_image is not None:
        data_url = (
            "data:image/png;base64," + submitted_image["base64"]
        )
        run_input = [
            sdk.TextInput(prompt),
            sdk.ImageInput(data_url),
        ]
    try:
        with tempfile.TemporaryDirectory(
            prefix="ora-codex-turn-", dir=str(CODEX_HOME)
        ) as isolated_cwd:
            thread = client.thread_start(
                approval_mode=sdk.ApprovalMode.deny_all,
                base_instructions=base_instructions,
                cwd=isolated_cwd,
                developer_instructions=_DEVELOPER_INSTRUCTIONS,
                ephemeral=True,
                model=model,
                model_provider="openai",
                sandbox=sdk.Sandbox.read_only,
            )
            result = thread.run(
                run_input,
                approval_mode=sdk.ApprovalMode.deny_all,
                cwd=isolated_cwd,
                model=model,
                sandbox=sdk.Sandbox.read_only,
            )
    except Exception as exc:
        err = _classified_error(exc)
        if err.kind == "reauth_required":
            _mark_reauth_required()
        raise err from None

    text = str(getattr(result, "final_response", "") or "")
    if not text.strip():
        raise CodexSubscriptionError(
            "empty_response", "The ChatGPT subscription returned an empty response."
        )
    if submitted_image is not None:
        submitted_image["_codex_subscription_image_submitted"] = True
    usage = getattr(getattr(result, "usage", None), "last", None)
    return {
        "text": text,
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "cached_input_tokens": getattr(usage, "cached_input_tokens", None),
    }
