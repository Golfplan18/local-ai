"""Load Ora's optional in-process first-party features.

Each configured package exports ``register(context)`` and returns a standard
descriptor containing its HTTP routes, browser assets, lifecycle hooks, and
optional provider rows. The host owns Flask and provider registration.

This remains an explicit trusted source list, not plugin discovery or an
extension platform. An absent or broken feature is logged and skipped without
preventing Ora or another feature from loading.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from pathlib import Path
import re
from typing import Any, Callable

from flask import send_from_directory
import provider_registry as _provider_registry


_ASSET_RE = re.compile(r"^[A-Za-z0-9_./-]+$")


@dataclass(frozen=True)
class FeaturePluginContext:
    """The complete Ora boundary visible to a feature plugin.

    The five lifecycle helpers let plugin routes join the same per-Dialogue
    barrier and tombstone policy as core writers. The file helpers keep
    plugin-owned writes inside Ora-owned roots and prevent upload symlink
    traversal. The remaining callables are read/service adapters: settings,
    declared credentials, tag lookup, execution telemetry, and the existing
    async-capability registry. No server module or application object crosses
    this boundary.
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
    has_credential: Callable[[str], bool]
    get_credential: Callable[[str], str | None]


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
    providers: tuple[dict, ...] = ()
    on_release: Callable[[str], Any] | None = None
    on_quiesce: Callable[[str], Any] | None = None
    on_clear: Callable[[str], Any] | None = None


@dataclass(frozen=True)
class FeaturePluginSource:
    plugin_id: str
    module_name: str
    package_dir: Path


@dataclass(frozen=True)
class LoadedFeaturePlugins:
    descriptors: dict[str, FeaturePlugin]

    def asset_tags(self) -> str:
        lines: list[str] = []
        for plugin_id, plugin in self.descriptors.items():
            base = f"/plugins/{plugin_id}"
            for path in plugin.styles:
                lines.append(f'<link rel="stylesheet" href="{base}/{path}">')
            for path in plugin.scripts:
                lines.append(f'<script src="{base}/{path}" defer></script>')
        return "\n".join(lines)

    def run_lifecycle(self, phase: str, conversation_id: str) -> dict:
        if phase not in {"release", "quiesce", "clear"}:
            raise ValueError(f"unknown feature-plugin lifecycle phase: {phase}")
        results: dict[str, Any] = {}
        errors: list[str] = []
        for plugin_id, plugin in self.descriptors.items():
            callback = getattr(plugin, f"on_{phase}")
            if callback is None:
                continue
            try:
                result = callback(conversation_id)
                results[plugin_id] = result
                if isinstance(result, dict):
                    errors.extend(f"{plugin_id}: {item}"
                                  for item in result.get("errors") or [])
            except Exception as exc:  # optional feature must fail open
                message = f"{plugin_id}: {exc}"
                print(f"[feature-plugins] {phase} failed for {message}", flush=True)
                errors.append(message)
        return {"results": results, "errors": errors}


def _validate_descriptor(
    plugin: FeaturePlugin,
    source: FeaturePluginSource,
    app: Any,
) -> tuple[tuple[str, str, Callable[..., Any], tuple[str, ...]], ...]:
    """Validate one complete package before Flask or provider mutation."""

    if not isinstance(plugin, FeaturePlugin):
        raise TypeError("register(context) must return FeaturePlugin")
    if plugin.plugin_id != source.plugin_id:
        raise ValueError(
            f"descriptor id {plugin.plugin_id!r} does not match "
            f"source id {source.plugin_id!r}"
        )
    static_root = plugin.static_root.resolve()
    if static_root != (source.package_dir / "static").resolve():
        raise ValueError("plugin static_root must be its own static/ directory")
    for asset in (*plugin.scripts, *plugin.styles):
        if (not _ASSET_RE.fullmatch(asset) or asset.startswith("/")
                or ".." in Path(asset).parts):
            raise ValueError(f"unsafe plugin asset path: {asset!r}")
        if not (static_root / asset).is_file():
            raise ValueError(f"plugin asset is missing: {asset}")
    registrations: list[tuple[str, str, Callable[..., Any], tuple[str, ...]]] = []
    for route in plugin.routes:
        if not isinstance(route, PluginRoute):
            raise TypeError("plugin routes must contain PluginRoute values")
        if not isinstance(route.rule, str) or not route.rule.startswith("/"):
            raise ValueError(f"invalid plugin route rule: {route.rule!r}")
        if not isinstance(route.endpoint, str) or not route.endpoint:
            raise ValueError("plugin route endpoint is required")
        if not callable(route.handler):
            raise TypeError(f"plugin route handler is not callable: {route.endpoint}")
        if (not route.methods
                or any(not isinstance(method, str) or not method.strip()
                       for method in route.methods)):
            raise ValueError(f"plugin route methods are invalid: {route.endpoint}")
        registrations.append((
            route.rule,
            f"plugin_{plugin.plugin_id}_{route.endpoint}",
            route.handler,
            tuple(method.upper() for method in route.methods),
        ))

    def serve_asset(filename: str, root=plugin.static_root) -> Any:
        return send_from_directory(str(root), filename)

    registrations.append((
        f"/plugins/{plugin.plugin_id}/<path:filename>",
        f"serve_{plugin.plugin_id}_plugin_asset",
        serve_asset,
        ("GET",),
    ))

    existing_rules = tuple(app.url_map.iter_rules())
    endpoints = set(app.view_functions)
    endpoints.update(item.endpoint for item in existing_rules)
    occupied = [
        (item.rule, frozenset(item.methods or ())) for item in existing_rules
    ]
    for rule, endpoint, _handler, declared_methods in registrations:
        if endpoint in endpoints:
            raise ValueError(f"plugin endpoint collision: {endpoint}")
        collision_methods = {method.upper() for method in declared_methods}
        if "GET" in collision_methods:
            collision_methods.add("HEAD")
        flask_methods = set(collision_methods)
        if ("OPTIONS" not in flask_methods
                and app.config.get("PROVIDE_AUTOMATIC_OPTIONS", True)):
            flask_methods.add("OPTIONS")
        probe_rule = app.url_rule_class(
            rule,
            endpoint=endpoint,
            methods=flask_methods,
        )
        probe_rule.bind(app.url_map)
        if any(
            occupied_rule == rule
            and collision_methods.intersection(occupied_methods)
            for occupied_rule, occupied_methods in occupied
        ):
            raise ValueError(f"plugin URL/method collision: {rule}")
        endpoints.add(endpoint)
        occupied.append((rule, frozenset(collision_methods)))

    if plugin.providers:
        _provider_registry.register_provider_batch(
            plugin.plugin_id,
            plugin.providers,
            commit=False,
        )
    return tuple(registrations)


def load_feature_plugins(
    app: Any,
    context_factory: Callable[[str, Path], FeaturePluginContext],
    *,
    sources: tuple[FeaturePluginSource, ...],
) -> LoadedFeaturePlugins:
    """Load each explicit source independently and return successful features."""

    loaded: dict[str, FeaturePlugin] = {}
    for source in sources:
        if not source.package_dir.is_dir():
            print(
                f"[feature-plugins] no {source.plugin_id} feature at "
                f"{source.package_dir}; continuing",
                flush=True,
            )
            continue

        try:
            module = importlib.import_module(source.module_name)
            plugin = module.register(
                context_factory(source.plugin_id, source.package_dir)
            )
            registrations = _validate_descriptor(plugin, source, app)
            for rule, endpoint, handler, methods in registrations:
                app.add_url_rule(
                    rule,
                    endpoint=endpoint,
                    view_func=handler,
                    methods=list(methods),
                )
            if plugin.providers:
                _provider_registry.register_provider_batch(
                    plugin.plugin_id,
                    plugin.providers,
                )
            loaded[plugin.plugin_id] = plugin
            print(f"[feature-plugins] loaded {plugin.plugin_id}", flush=True)
        except Exception as exc:  # optional features fail open, loudly
            print(
                f"[feature-plugins] failed to load {source.module_name}: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
    return LoadedFeaturePlugins(loaded)


def configured_feature_plugin_sources(
    ora_home: str | Path,
) -> tuple[FeaturePluginSource, ...]:
    override = str(os.environ.get("ORA_FEATURE_PLUGINS_DIR") or "").strip()
    plugins_root = Path(override).expanduser() if override else Path(ora_home) / "plugins"
    return (FeaturePluginSource("video", "plugins.video", plugins_root / "video"),)
