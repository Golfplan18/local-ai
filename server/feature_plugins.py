"""Load Ora's optional in-process video feature.

``plugins.video`` exports one ``register(context)`` function and returns a
standard descriptor containing its HTTP routes, browser assets, and
conversation-lifecycle hooks.  The loader owns Flask registration and static
serving, so video never imports ``server.app`` or receives the Flask app.

This is deliberately one optional first-party feature, not plugin discovery or
an extension platform.  An absent folder is normal; a broken video package is
logged loudly and skipped without preventing Ora from booting.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from pathlib import Path
import re
from typing import Any, Callable


_ASSET_RE = re.compile(r"^[A-Za-z0-9_./-]+$")


@dataclass(frozen=True)
class FeaturePluginContext:
    """The complete Ora boundary visible to a feature plugin.

    The five lifecycle helpers let plugin routes join the same per-Dialogue
    barrier and tombstone policy as core writers.  The file helpers keep
    plugin-owned writes inside Ora-owned roots and prevent upload symlink
    traversal.  The remaining callables are read/service adapters: settings,
    tag lookup, execution telemetry, and the existing async-capability
    registry.  No server module or application object crosses this boundary.
    """

    ora_home: Path
    plugin_root: Path
    valid_live_conversation_id: Callable[[str], bool]
    conversation_lifecycle_lock: Callable[[str], Any]
    is_conversation_deleted: Callable[[str], bool]
    ensure_artifact_envelope: Callable[[str, str], tuple[str, bool]]
    conversation_read_scope: Callable[[str], Any]
    safe_owned_subdir: Callable[..., Path]
    atomic_write_text: Callable[..., None]
    save_upload: Callable[[Any, str], None]
    cross_site_mutation_response: Callable[[], Any]
    protected_media_reference_delete: Callable[..., bool]
    get_setting: Callable[[str, Any], Any]
    get_conversation_tag: Callable[[str], str]
    record_tool_event: Callable[[dict], None]
    tool_manifest_axes: Callable[[str], dict]
    load_async_capability_registry: Callable[[str], Any]


@dataclass(frozen=True)
class PluginRoute:
    rule: str
    endpoint: str
    handler: Callable[..., Any]
    methods: tuple[str, ...] = ("GET",)


@dataclass(frozen=True)
class FeaturePlugin:
    plugin_id: str
    static_root: Path
    scripts: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()
    routes: tuple[PluginRoute, ...] = ()
    on_release: Callable[[str], Any] | None = None
    on_quiesce: Callable[[str], Any] | None = None
    on_clear: Callable[[str], Any] | None = None


@dataclass(frozen=True)
class LoadedVideoPlugin:
    descriptor: FeaturePlugin | None = None

    def asset_tags(self) -> str:
        plugin = self.descriptor
        if plugin is None:
            return ""
        lines: list[str] = []
        base = "/plugins/video"
        for path in plugin.styles:
            lines.append(f'<link rel="stylesheet" href="{base}/{path}">')
        for path in plugin.scripts:
            lines.append(f'<script src="{base}/{path}" defer></script>')
        return "\n".join(lines)

    def static_root(self) -> Path | None:
        return self.descriptor.static_root if self.descriptor else None

    def run_lifecycle(self, phase: str, conversation_id: str) -> dict:
        if phase not in {"release", "quiesce", "clear"}:
            raise ValueError(f"unknown feature-plugin lifecycle phase: {phase}")
        plugin = self.descriptor
        if plugin is None:
            return {"results": {}, "errors": []}
        errors: list[str] = []
        callback = getattr(plugin, f"on_{phase}")
        if callback is None:
            return {"results": {}, "errors": []}
        try:
            result = callback(conversation_id)
            if isinstance(result, dict):
                errors.extend(f"video: {item}" for item in result.get("errors") or [])
            return {"results": {"video": result}, "errors": errors}
        except Exception as exc:  # optional video feature must fail open
            message = f"video: {exc}"
            print(f"[feature-plugins] {phase} failed for {message}", flush=True)
            return {"results": {}, "errors": [message]}


def _validate_descriptor(plugin: FeaturePlugin, package_dir: Path) -> None:
    if not isinstance(plugin, FeaturePlugin):
        raise TypeError("register(context) must return FeaturePlugin")
    if plugin.plugin_id != "video":
        raise ValueError("plugins.video descriptor id must be 'video'")
    static_root = plugin.static_root.resolve()
    if static_root != (package_dir / "static").resolve():
        raise ValueError("plugin static_root must be its own static/ directory")
    for asset in (*plugin.scripts, *plugin.styles):
        if (not _ASSET_RE.fullmatch(asset) or asset.startswith("/")
                or ".." in Path(asset).parts):
            raise ValueError(f"unsafe plugin asset path: {asset!r}")
        target = static_root / asset
        if not target.is_file():
            raise ValueError(f"plugin asset is missing: {asset}")
    endpoints: set[str] = set()
    for route in plugin.routes:
        if not isinstance(route, PluginRoute):
            raise TypeError("plugin routes must contain PluginRoute values")
        if route.endpoint in endpoints:
            raise ValueError(f"duplicate plugin endpoint: {route.endpoint}")
        endpoints.add(route.endpoint)


def load_video_plugin(
    app: Any,
    context_factory: Callable[[Path], FeaturePluginContext],
    *,
    plugin_root: str | Path,
) -> LoadedVideoPlugin:
    """Load ``plugins.video`` once when its folder is installed."""

    package_dir = Path(plugin_root)
    if not package_dir.is_dir():
        print(f"[feature-plugins] no video plugin at {package_dir}; continuing")
        return LoadedVideoPlugin()

    try:
        module = importlib.import_module("plugins.video")
        plugin = module.register(context_factory(package_dir))
        _validate_descriptor(plugin, package_dir)
        for route in plugin.routes:
            app.add_url_rule(
                route.rule,
                endpoint=f"plugin_video_{route.endpoint}",
                view_func=route.handler,
                methods=list(route.methods),
            )
        print("[feature-plugins] loaded video", flush=True)
        return LoadedVideoPlugin(plugin)
    except Exception as exc:  # optional video feature fails open, loudly
        print(
            f"[feature-plugins] failed to load plugins.video: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return LoadedVideoPlugin()


def configured_video_plugin_root(ora_home: str | Path) -> Path:
    override = str(os.environ.get("ORA_FEATURE_PLUGINS_DIR") or "").strip()
    plugins_root = Path(override).expanduser() if override else Path(ora_home) / "plugins"
    return plugins_root / "video"
