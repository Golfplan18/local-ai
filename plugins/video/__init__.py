"""Ora's removable first-party video feature plugin."""

from server.feature_plugins import FeaturePlugin

from . import runtime


def register(context):
    """Bind the video feature to Ora's documented in-process boundary."""
    runtime.configure(context)
    from . import routes

    return FeaturePlugin(
        plugin_id="video",
        static_root=context.plugin_root / "static",
        styles=(
            "styles/capture-controls.css",
            "styles/video-editing.css",
            "styles/timeline-editor.css",
            "styles/preview-monitor.css",
            "styles/transcript-panel.css",
            "styles/render-controls.css",
            "styles/video-settings.css",
        ),
        scripts=(
            "video-shortcuts.js",
            "capture-controls.js",
            "media-library.js",
            "timeline-editor.js",
            "preview-monitor.js",
            "transcript-panel.js",
            "render-controls.js",
            "capability-video-generates.js",
            "v3-canvas-to-library.js",
            "video-settings.js",
            "video-plugin.js",
        ),
        routes=routes.build_routes(context),
        on_release=routes.on_release,
        on_quiesce=routes.on_quiesce,
        on_clear=routes.on_clear,
    )
