"""Canonical credential mutation tool using the system keyring.

G1.22A deliberately does not expose credential values to a model-facing tool.
Provider execution reads its own exact key internally; this surface can store,
delete, or report existence only for registry-declared ``ora`` accounts.
"""

import keyring

try:
    import provider_registry
except ImportError:  # pragma: no cover
    from orchestrator import provider_registry


def _allowed_usernames() -> set[str]:
    return set(provider_registry.keyring_username_map().values())


def credential_store(action: str, service: str, username: str, value: str = None) -> str:
    try:
        action = str(action or "").strip().lower()
        if service != "ora":
            return "Error: credential service must be 'ora'"
        if username not in _allowed_usernames():
            return "Error: credential account is not declared by the provider registry"
        if action == "store":
            if value is None:
                return "Error: value required for store action"
            try:
                import system_protection as _sp
            except ImportError:  # pragma: no cover
                from orchestrator import system_protection as _sp
            _sp.require_active_execution(
                "credential_store:store", f"credential:ora/{username}",
            )
            keyring.set_password(service, username, value)
            return f"Credential stored: {service}/{username}"
        elif action == "status":
            result = keyring.get_password(service, username)
            if result is None:
                return f"No credential found: {service}/{username}"
            return f"Credential present: {service}/{username}"
        elif action == "delete":
            try:
                import system_protection as _sp
            except ImportError:  # pragma: no cover
                from orchestrator import system_protection as _sp
            _sp.require_active_execution(
                "credential_store:delete", f"credential:ora/{username}",
            )
            try:
                keyring.delete_password(service, username)
            except Exception:
                pass
            return f"Credential absent: {service}/{username}"
        elif action == "retrieve":
            return "Error: credential values are unavailable on model/tool surfaces"
        else:
            return f"Unknown action: {action}. Use 'store', 'status', or 'delete'."
    except Exception as e:
        return f"Credential error: {str(e)}"
