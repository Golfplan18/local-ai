"""Test-only proof that a second trusted feature can join the Ora host."""

from server.feature_plugins import FeaturePlugin


LAST_CONTEXT = None


def register(context):
    global LAST_CONTEXT
    LAST_CONTEXT = context
    return FeaturePlugin(
        plugin_id="settings_probe",
        static_root=context.plugin_root / "static",
        scripts=("settings-probe.js",),
        providers=(
            {
                "id": "settings_probe",
                "label": "Settings probe",
                "category": "metadata",
                "keyring_username": "settings-probe-api-key",
                "signup_url": "https://example.invalid/settings-probe/signup",
                "console_url": "https://example.invalid/settings-probe/keys",
                "transport": "Used only by the settings-probe feature",
                "note": "Test-only feature provider.",
            },
        ),
    )
