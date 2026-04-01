"""Credential storage using system keyring (macOS Keychain on this machine)."""

import keyring


def credential_store(action: str, service: str, username: str, value: str = None) -> str:
    try:
        if action == "store":
            if value is None:
                return "Error: value required for store action"
            keyring.set_password(service, username, value)
            return f"Credential stored: {service}/{username}"
        elif action == "retrieve":
            result = keyring.get_password(service, username)
            if result is None:
                return f"No credential found: {service}/{username}"
            return result
        else:
            return f"Unknown action: {action}. Use 'store' or 'retrieve'."
    except Exception as e:
        return f"Credential error: {str(e)}"
