"""One bounded outbound email action for the Fastmail/JMAP channel.

This module deliberately has no scheduler, retry loop, inbox reader, or mail
store.  It prepares an exact message locally, resolves the selected Persona
into the visible sender/disclosure, and only then enters the existing System
Protection approval/receipt boundary before contacting Fastmail.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formataddr, getaddresses, parseaddr
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:
    import network_policy as _network_policy
except ImportError:  # pragma: no cover - package import context
    from orchestrator import network_policy as _network_policy

try:
    import runtime_paths as _runtime_paths
except ImportError:  # pragma: no cover - package import context
    from orchestrator import runtime_paths as _runtime_paths

try:
    import keyring
except ImportError:  # pragma: no cover - only needed by the real provider
    keyring = None

try:
    import persona as _persona
    import provider_registry as _provider_registry
    import system_protection as _protection
    import tool_events as _tool_events
except ImportError:  # pragma: no cover - package import context
    from orchestrator import persona as _persona
    from orchestrator import provider_registry as _provider_registry
    from orchestrator import system_protection as _protection
    from orchestrator import tool_events as _tool_events


ACTION = "email_send"
PROVIDER_ID = "fastmail"
DISCLOSURE = "Sent by {persona}, an AI assistant, on behalf of the account holder."
MAX_RECIPIENTS = 64
MAX_SUBJECT = 998
MAX_BODY = 200_000
CONFIG_RELATIVE_PATH = "config.json"
FASTMAIL_SESSION_URL = "https://api.fastmail.com/jmap/session"


class EmailChannelError(RuntimeError):
    """The exact email cannot be prepared or sent."""


class EmailInputError(ValueError):
    """The user supplied an invalid exact message."""


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _address(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EmailInputError(f"{label} is required")
    raw = value.strip()
    name, address = parseaddr(raw)
    if name or address != raw or "@" not in address or any(
        char.isspace() for char in address
    ):
        raise EmailInputError(f"{label} must be one bare email address")
    local, domain = address.rsplit("@", 1)
    if not local or not domain or "." not in domain:
        raise EmailInputError(f"{label} must be one valid email address")
    return f"{local}@{domain}"  # preserve case; the exact message is user-owned


def _recipients(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple)):
        values = list(value)
    else:
        raise EmailInputError("to must be a non-empty list of email addresses")
    if not values or len(values) > MAX_RECIPIENTS:
        raise EmailInputError(f"to must contain 1-{MAX_RECIPIENTS} addresses")
    result = []
    for item in values:
        # getaddresses rejects display names here: recipients are an exact
        # selector and must not be silently changed by a parser.
        parsed = getaddresses([item]) if isinstance(item, str) else []
        address = _address(item, "recipient")
        if len(parsed) != 1 or parsed[0][0] or parsed[0][1] != address:
            raise EmailInputError("recipient must be one bare email address")
        result.append(address)
    if len(set(result)) != len(result):
        raise EmailInputError("to may not contain duplicate addresses")
    return tuple(result)


def _resolve_persona(persona_id: Any) -> dict:
    identifier = str(persona_id or "ora").strip()
    try:
        return _persona.resolve_persona(global_id=identifier)
    except Exception as exc:
        raise EmailInputError(f"Persona {identifier!r} is unavailable: {exc}") from exc


def _config_path() -> str:
    return str((Path(_runtime_paths.ORA_HOME) / CONFIG_RELATIVE_PATH).resolve())


def _email_config() -> dict[str, Any]:
    """Read the non-secret email policy from the one runtime config file."""
    path = Path(_config_path())
    if not path.is_file():
        raise EmailInputError(
            "email channel is not configured; add channel.email to config.json"
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EmailInputError(f"email channel configuration is unreadable: {exc}") from exc
    channel = document.get("channel") if isinstance(document, dict) else None
    email = channel.get("email") if isinstance(channel, dict) else None
    if not isinstance(email, dict) or email.get("enabled") is not True:
        raise EmailInputError("email channel is disabled; enable channel.email in config.json")
    endpoint = str(email.get("endpoint_base_url") or FASTMAIL_SESSION_URL).strip()
    if endpoint != FASTMAIL_SESSION_URL:
        raise EmailInputError(
            "channel.email.endpoint_base_url must be the Fastmail JMAP session endpoint"
        )
    sender = _address(email.get("mask_mailbox"), "channel.email.mask_mailbox")
    allowlist = email.get("recipient_allowlist")
    if not isinstance(allowlist, list) or not allowlist:
        raise EmailInputError(
            "channel.email.recipient_allowlist must contain at least one address"
        )
    try:
        allowed = tuple(sorted({_address(item, "recipient_allowlist").casefold()
                                for item in allowlist}))
    except EmailInputError:
        raise
    return {"sender": sender, "allowlist": allowed}


def normalize_action(raw: Mapping[str, Any]) -> dict:
    """Validate and canonicalize an ``email_send`` Trigger action."""
    if not isinstance(raw, Mapping) or raw.get("kind") != ACTION:
        raise EmailInputError("email action kind must be email_send")
    allowed = {"kind", "to", "subject", "body", "from_email", "persona_id"}
    unknown = set(raw) - allowed
    if unknown:
        raise EmailInputError(
            "email_send fields are invalid: " + ", ".join(sorted(unknown)))
    subject = raw.get("subject")
    body = raw.get("body")
    if not isinstance(subject, str) or not subject.strip() or len(subject) > MAX_SUBJECT:
        raise EmailInputError(f"subject must contain 1-{MAX_SUBJECT} characters")
    if not isinstance(body, str) or not body.strip() or len(body) > MAX_BODY:
        raise EmailInputError(f"body must contain 1-{MAX_BODY} characters")
    config = _email_config()
    configured_sender = config["sender"]
    supplied_sender = raw.get("from_email")
    if supplied_sender is not None and _address(supplied_sender, "from_email") != configured_sender:
        raise EmailInputError(
            "from_email must match the configured channel.email.mask_mailbox"
        )
    recipients = _recipients(raw.get("to"))
    disallowed = [address for address in recipients
                  if address.casefold() not in config["allowlist"]]
    if disallowed:
        raise EmailInputError(
            "recipient is outside channel.email.recipient_allowlist: "
            + ", ".join(disallowed)
        )
    persona_id = str(raw.get("persona_id") or "ora").strip() or "ora"
    # Resolve during authoring so a draft cannot be created with an identity
    # that will disappear before activation.  The resulting display name is
    # bound again while preparing the exact message.
    selected = _resolve_persona(persona_id)
    return {
        "kind": ACTION,
        "to": list(recipients),
        "subject": subject,
        "body": body,
        "from_email": configured_sender,
        "persona_id": selected["id"],
    }


@dataclass(frozen=True)
class PreparedEmail:
    """The immutable, inspectable message that a provider may receive."""

    to: tuple[str, ...]
    subject: str
    body: str
    from_email: str
    persona_id: str
    persona_name: str
    disclosure: str
    mime: bytes
    digest: str

    @property
    def visible_body(self) -> str:
        return f"{self.disclosure}\n\n{self.body}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": PROVIDER_ID,
            "from": {"name": self.persona_name, "email": self.from_email},
            "to": list(self.to),
            "subject": self.subject,
            "body": self.visible_body,
            "disclosure": self.disclosure,
            "mime": self.mime.decode("utf-8"),
            "message_digest": self.digest,
        }


def prepare_message(action: Mapping[str, Any]) -> PreparedEmail:
    """Build the exact local message without contacting a provider."""
    normalized = normalize_action(action)
    selected = _resolve_persona(normalized["persona_id"])
    display_name = str(selected["display_name"]).strip()
    disclosure = DISCLOSURE.format(persona=display_name)
    message = EmailMessage(policy=SMTP)
    message["From"] = formataddr((display_name, normalized["from_email"]))
    message["To"] = ", ".join(normalized["to"])
    message["Subject"] = normalized["subject"]
    message["X-Ora-Assistant"] = f"{display_name}; {disclosure}"
    message.set_content(f"{disclosure}\n\n{normalized['body']}")
    mime = message.as_bytes(policy=SMTP)
    canonical = {
        "provider": PROVIDER_ID,
        "to": normalized["to"],
        "subject": normalized["subject"],
        "body": normalized["body"],
        "from_email": normalized["from_email"],
        "persona_id": selected["id"],
        "persona_name": display_name,
        "disclosure": disclosure,
        "mime_sha256": hashlib.sha256(mime).hexdigest(),
    }
    return PreparedEmail(
        to=tuple(normalized["to"]), subject=normalized["subject"],
        body=normalized["body"], from_email=normalized["from_email"],
        persona_id=selected["id"], persona_name=display_name,
        disclosure=disclosure, mime=mime, digest=_digest(canonical),
    )


def inspect_message(action: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact local message shown before any provider call."""
    return prepare_message(action).as_dict()


def selectors(message: PreparedEmail, trigger_id: str) -> tuple[str, ...]:
    """Exact logical scopes used by System Protection and approval binding."""
    recipients = ",".join(message.to)
    entry = _provider_registry.by_id(PROVIDER_ID) or {}
    credential_user = str(entry.get("keyring_username") or "")
    credential_selector = (
        f"credential:ora/{credential_user}" if credential_user else ""
    )
    return tuple(sorted({
        f"email:provider/{PROVIDER_ID}",
        f"email:config/{PROVIDER_ID}",
        f"email:trigger/{trigger_id}",
        f"email:sender/{message.from_email}",
        f"email:persona/{message.persona_id}",
        f"email:recipients/{recipients}",
        f"email:message/{message.digest}",
        f"email:allowlist/{_digest(list(_email_config()['allowlist']))}",
        f"path:{_config_path()}",
        credential_selector,
    } - {""}))


def _states(exact_selectors: Sequence[str]) -> list[dict[str, Any]]:
    return [_protection.capture_selector_identity(selector)
            for selector in exact_selectors]


def approval_fingerprint(action: Mapping[str, Any], trigger_id: str) -> tuple[str, dict, tuple[str, ...], list[dict]]:
    """Return the same protected request identity used by authorize/send."""
    message = prepare_message(action)
    exact = selectors(message, trigger_id)
    pre_state = _states(exact)
    params = {
        "trigger_id": trigger_id,
        "provider": PROVIDER_ID,
        "message": message.as_dict(),
    }
    safe_params = {
        "action": ACTION,
        "selectors": list(exact),
        "params_digest": _protection.params_digest(params),
        "pre_state": pre_state,
    }
    approval_action = f"system_protection:{ACTION}"
    args_hash = _tool_events.normalize_args_hash(approval_action, safe_params)
    return args_hash, params, exact, pre_state


class FastmailJMAPProvider:
    """Small real Fastmail/JMAP sender.

    Tests inject a deterministic provider object into :func:`send_trigger`,
    so this network adapter is never needed for local proof.
    """

    session_url = FASTMAIL_SESSION_URL

    def __init__(self, *, token: str | None = None,
                 opener: Callable[..., Any] | None = None):
        self._token = token
        # ``network_policy`` owns all public HTTP(S) transport.  The optional
        # callable is a deterministic test double, adapted to the transport
        # interface without creating a second network path.
        self._opener = opener

    def _token_value(self) -> str:
        if self._token:
            return self._token
        entry = _provider_registry.by_id(PROVIDER_ID)
        if not entry:
            raise EmailChannelError("Fastmail is not declared by the provider registry")
        if keyring is None:
            raise EmailChannelError("system keyring is unavailable")
        selector = f"credential:ora/{entry['keyring_username']}"
        _protection.require_active_execution(ACTION, selector)
        value = keyring.get_password("ora", entry["keyring_username"])
        if not value:
            raise EmailChannelError("Fastmail credential is not configured in the system keyring")
        return value

    def _request(self, url: str, *, payload: bytes | None = None,
                 token: str, content_type: str = "application/json",
                 required_origin: str = "https://api.fastmail.com") -> dict:
        headers = {"Authorization": f"Bearer {token}",
                   "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = content_type
        try:
            opener = None
            if self._opener is not None:
                callback = self._opener

                class _CallableOpener:
                    def open(self, request, timeout=30):
                        return callback(request, timeout=timeout)

                opener = _CallableOpener()
            data, _destination = _network_policy.urllib_request_bytes(
                url, headers=headers, data=payload, timeout=30,
                required_origin=required_origin, max_redirects=0,
                opener=opener,
            )
        except Exception as exc:
            raise EmailChannelError(f"Fastmail request failed: {exc}") from exc
        try:
            decoded = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EmailChannelError("Fastmail returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise EmailChannelError("Fastmail returned a non-object response")
        return decoded

    def _method_call(self, api_url: str, account_id: str, token: str,
                     method: str, arguments: dict, *, using: Sequence[str]) -> dict:
        result = self._request(
            api_url,
            payload=json.dumps({
                "using": list(using),
                "methodCalls": [[method, arguments, "ora-call"]],
            }, separators=(",", ":")).encode("utf-8"),
            token=token,
        )
        responses = result.get("methodResponses")
        self._validate_method_responses(responses, expected=(method,))
        return responses[0][1]

    def send(self, message: PreparedEmail, *,
             on_provider_contact: Callable[[], None] | None = None) -> dict[str, Any]:
        token = self._token_value()
        contact_marked = False

        def mark_contact() -> None:
            nonlocal contact_marked
            if not contact_marked and on_provider_contact is not None:
                on_provider_contact()
                contact_marked = True

        mark_contact()
        session = self._request(self.session_url, token=token)
        api_url = session.get("apiUrl")
        account_id = (session.get("primaryAccounts") or {}).get("urn:ietf:params:jmap:mail")
        if not isinstance(api_url, str) or not api_url.startswith("https://"):
            raise EmailChannelError("Fastmail session omitted a valid HTTPS apiUrl")
        if not isinstance(account_id, str) or not account_id:
            raise EmailChannelError("Fastmail session omitted a mail account")
        mailbox = self._method_call(
            api_url, account_id, token, "Mailbox/query",
            {"accountId": account_id, "filter": {"role": "draft"}},
            using=("urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"),
        )
        draft_ids = mailbox.get("ids")
        if not isinstance(draft_ids, list) or not draft_ids:
            raise EmailChannelError("Fastmail has no draft mailbox for the exact message")
        identities = self._method_call(
            api_url, account_id, token, "Identity/get",
            {"accountId": account_id, "ids": None},
            using=("urn:ietf:params:jmap:core", "urn:ietf:params:jmap:submission"),
        )
        identity = next(
            (row for row in identities.get("list", [])
             if isinstance(row, dict) and row.get("email") == message.from_email),
            None,
        )
        if not identity or not identity.get("id"):
            raise EmailChannelError(
                "Fastmail has no identity matching the exact from_email"
            )
        # JMAP's Email/set creates a normal draft Email object.  The earlier
        # Email/import + ``#ora-email`` path relied on provider-specific blob
        # import behavior and did not create a standards-bound draft for the
        # subsequent submission reference.
        visible_body = message.visible_body
        payload = {
            "using": ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail",
                      "urn:ietf:params:jmap:submission"],
            "methodCalls": [[
                "Email/set",
                {"accountId": account_id, "create": {
                    "ora-draft": {
                        "mailboxIds": {draft_ids[0]: True},
                        "keywords": {"$draft": True},
                        "from": [{"email": message.from_email,
                                   "name": message.persona_name}],
                        "to": [{"email": address} for address in message.to],
                        "subject": message.subject,
                        "bodyStructure": {
                            "type": "text/plain", "partId": "body",
                            "charset": "utf-8",
                        },
                        "bodyValues": {
                            "body": {"value": visible_body,
                                      "isEncodingProblem": False},
                        },
                    },
                }},
                "ora-draft-create",
            ], [
                "EmailSubmission/set",
                {"accountId": account_id, "create": {
                    "ora-submission": {
                        "identityId": identity["id"], "emailId": "#ora-draft",
                    },
                }},
                "ora-submit",
            ]],
        }
        result = self._request(
            api_url, payload=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            token=token, required_origin="https://api.fastmail.com",
        )
        responses = result.get("methodResponses")
        self._validate_method_responses(
            responses, expected=("Email/set", "EmailSubmission/set"),
            required_created_ids=("ora-draft", "ora-submission"),
        )
        return {"provider": PROVIDER_ID, "message_digest": message.digest,
                "jmap": "EmailSubmission/set", "provider_contacted": True}

    @staticmethod
    def _validate_method_responses(
        responses: Any, *, expected: Sequence[str],
        required_created_ids: Sequence[str] = (),
    ) -> None:
        """Reject JMAP errors and incomplete create responses."""
        if not isinstance(responses, list) or len(responses) != len(expected):
            raise EmailChannelError("Fastmail returned an incomplete JMAP response")
        for index, response in enumerate(responses):
            if not isinstance(response, list) or len(response) < 2:
                raise EmailChannelError("Fastmail returned an invalid JMAP response")
            method, arguments = response[0], response[1]
            if method == "error":
                raise EmailChannelError(f"Fastmail JMAP failed: {arguments}")
            if method != expected[index] or not isinstance(arguments, dict):
                raise EmailChannelError(
                    f"Fastmail returned unexpected JMAP response {method!r}"
                )
            for field in ("notCreated", "notUpdated", "notDestroyed"):
                failures = arguments.get(field)
                if isinstance(failures, dict) and failures:
                    raise EmailChannelError(
                        f"Fastmail {method} failed: {field}={failures}"
                    )
            if required_created_ids:
                required_id = required_created_ids[index]
                created = arguments.get("created")
                entry = created.get(required_id) if isinstance(created, dict) else None
                if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
                    raise EmailChannelError(
                        f"Fastmail {method} omitted created result for {required_id}"
                    )


def _default_provider() -> FastmailJMAPProvider:
    return FastmailJMAPProvider()


def send_trigger(action: Mapping[str, Any], trigger_id: str, *,
                 provider: Any | None = None,
                 on_provider_contact: Callable[[], None] | None = None) -> dict[str, Any]:
    """Authorize and send one exact Trigger message through Fastmail."""
    message = prepare_message(action)
    args_hash, params, exact, pre_state = approval_fingerprint(action, trigger_id)
    decision = _protection.authorize_channel_action(
        ACTION, selectors=exact, params=params, pre_state=pre_state,
    )
    try:
        with _protection.protected_effect(decision):
            sender = provider or _default_provider()
            result = sender.send(message, on_provider_contact=on_provider_contact)
        completion = _protection.complete_execution(
            decision, ok=True, result=result, post_state=pre_state,
        )
    except BaseException as exc:
        # A provider failure still gets a terminal authenticated receipt.  A
        # provider is considered contacted once its send method was entered;
        # no recall promise is made after that boundary.
        try:
            _protection.complete_execution(
                decision, ok=False,
                result={"error": f"{type(exc).__name__}: {exc}",
                        "message_digest": message.digest},
                post_state=pre_state,
            )
        except Exception:
            pass
        raise
    _tool_events.record({
        "event": "email_send", "action": ACTION,
        "category": "execute", "mutability": "irreversible",
        "sensitivity": "private", "egress": "external",
        "args_redacted": {"args_hash": args_hash,
                           "message_digest": message.digest,
                           "recipient_count": len(message.to)},
        "result": {"result_digest": _digest(result),
                   "provider_contacted": True},
        "enforcement_model": "in_harness",
    })
    return {"outcome": "sent", "kind": ACTION, "provider": PROVIDER_ID,
            "message_digest": message.digest, "provider_contacted": True,
            "receipt_digest": completion["record_digest"]}


def rollback_authority(action: Mapping[str, Any], trigger_id: str) -> dict[str, int]:
    """Revoke unused email approval authority before provider contact."""
    args_hash, _params, _selectors, _pre_state = approval_fingerprint(action, trigger_id)
    approval_action = f"system_protection:{ACTION}"
    removed_tokens = _tool_events.remove_unused_tokens(approval_action, args_hash)
    removed_cards = 0
    try:
        import oversight_queue as _queue
        for entry in list(_queue.list_paused()):
            event = entry.event or {}
            if (entry.kind == "execution_gate"
                    and event.get("action") == approval_action
                    and event.get("args_hash") == args_hash):
                nonce = event.get("approval_nonce")
                if nonce:
                    _tool_events._discard_pending_approval(str(nonce))
                if _queue.remove_by_id(entry.id):
                    removed_cards += 1
    except Exception:
        # Token revocation is the authority guarantee.  A stale UI card is
        # harmless once its pending request has been removed, and cleanup is
        # allowed to fail open rather than blocking Trigger retirement.
        pass
    _tool_events.clear_queued_hash(None, args_hash)
    return {"tokens_revoked": removed_tokens, "queue_cards_removed": removed_cards}


__all__ = [
    "ACTION", "EmailChannelError", "EmailInputError", "FastmailJMAPProvider",
    "PreparedEmail", "approval_fingerprint", "inspect_message",
    "normalize_action", "prepare_message", "rollback_authority",
    "selectors", "send_trigger",
]
