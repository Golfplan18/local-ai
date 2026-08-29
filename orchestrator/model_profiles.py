"""Model Profile authority for G1.16.

The checked-in/runtime ``configurations/*.json`` files remain the execution
format.  This module gives that format the user-facing and runtime contract
the Project Integration Program calls a *Model Profile*:

* deterministic global -> project -> process -> step -> one-run precedence;
* immutable project bindings, including the profile, preset toggles, image
  model, and vision-routing mode that existed when the user bound it;
* four machine-readable health states; and
* preview/confirm migration with an append-only receipt.  Merely listing or
  previewing a deprecated profile can never mutate it.

The module intentionally owns no scheduler and performs no background repair.
Health is evaluated when a profile is read; migration occurs only after the
exact proposal is confirmed.
"""
from __future__ import annotations

import copy
import contextlib
import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from . import active_configuration as ac
    from . import project_meta as pm
    from . import runtime_paths as rp
except ImportError:  # direct script-style imports in the existing test suite
    import active_configuration as ac  # type: ignore
    import project_meta as pm  # type: ignore
    import runtime_paths as rp  # type: ignore


HEALTH_STATES = ("ok", "degraded", "deprecated", "unavailable")
LOCK_SCHEMA_VERSION = 2
MIGRATION_SCHEMA_VERSION = 1
LOCK_TOKEN_PREFIX = "project-lock:"

DATA_DIR = rp.DATA_DIR
MIGRATION_RECEIPTS_PATH = DATA_DIR / "model-profile-migrations.jsonl"

_lock = threading.RLock()


class ModelProfileError(ValueError):
    """Typed, user-correctable Model Profile contract error."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def profile_digest(profile: dict) -> str:
    """Content identity for the exact executable profile snapshot."""
    if not isinstance(profile, dict):
        raise ModelProfileError("model profile must be a JSON object")
    return _digest(profile)


def validate_profile_name(name: str) -> str:
    if not isinstance(name, str):
        raise ModelProfileError("model profile name must be a string")
    clean = name.strip()
    invalid = (
        not clean or len(clean) > 128 or clean in (".", "..")
        or any(ord(char) < 32 or char in '/\\<>:"|?*' for char in clean)
    )
    if invalid:
        raise ModelProfileError(
            "model profile name must be a 1-128 character portable file name"
        )
    return clean


def _read_profile(name: str) -> dict:
    name = validate_profile_name(name)
    try:
        profile = ac._load_config(name)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        raise ModelProfileError(f"model profile {name!r} is unavailable: {exc}") from exc
    if not isinstance(profile, dict):
        raise ModelProfileError(f"model profile {name!r} is not a JSON object")
    return profile


def _validate_ram_allocation(profile: dict) -> dict:
    """Apply the shared whole-profile RAM contract with this module's error type."""
    try:
        return ac.validate_profile_allocation(profile)
    except ValueError as exc:
        raise ModelProfileError(str(exc)) from exc


def validate_profile_allocation(profile_or_name: dict | str) -> dict:
    """Validate a live profile or named profile before it can execute."""
    profile = (
        _read_profile(profile_or_name)
        if isinstance(profile_or_name, str)
        else profile_or_name
    )
    if not isinstance(profile, dict):
        raise ModelProfileError("model profile must be a JSON object")
    return _validate_ram_allocation(profile)


def _iter_profile_cells(node: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], dict]]:
    if not isinstance(node, dict):
        return
    if "primary" in node:
        yield path, node
        return
    for key, value in node.items():
        if isinstance(value, dict):
            yield from _iter_profile_cells(value, (*path, str(key)))


def _profile_model_ids(profile: dict) -> list[str]:
    ids: list[str] = []
    for _path, cell in _iter_profile_cells(profile.get("cells") or {}):
        for value in [cell.get("primary"), *(cell.get("fallback") or [])]:
            if isinstance(value, str) and value and value not in ids:
                ids.append(value)
        visual = cell.get("vision_substitute")
        if isinstance(visual, str) and visual and visual not in ids:
            ids.append(visual)
    return ids


def _merge_inventory_record(
    records: dict[str, dict], model_id: str, incoming: dict, *, source: str,
) -> None:
    if not isinstance(model_id, str) or not model_id:
        return
    current = dict(records.get(model_id) or {})
    for key, value in incoming.items():
        if value is not None or key not in current:
            current[key] = value
    current.setdefault("id", model_id)
    sources = list(current.get("_profile_sources") or [])
    if source not in sources:
        sources.append(source)
    current["_profile_sources"] = sources
    records[model_id] = current


def load_model_inventory() -> dict:
    """Return exact current model records plus non-fuzzy aliases.

    The inventory joins the base registry, vendor-authoritative registry,
    routing endpoints, discovered local models, and the catalog.  A model is
    therefore not mislabeled deprecated merely because it is a direct,
    subscription, or local endpoint absent from the OpenRouter-derived base.
    """
    records: dict[str, dict] = {}
    aliases: dict[str, str] = {}

    def read_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    registry = read_json(rp.model_registry_path())
    for model_id, record in (registry.get("models") or {}).items():
        if isinstance(record, dict):
            _merge_inventory_record(records, model_id, record, source="registry")

    vendor = read_json(rp.vendor_authoritative_registry_path())
    for model_id, record in (vendor.get("models") or {}).items():
        if isinstance(record, dict):
            enriched = dict(record)
            if record.get("dispatch") == "direct":
                enriched.setdefault("reachable", True)
            _merge_inventory_record(records, model_id, enriched, source="vendor")
    for legacy, current in (vendor.get("aliases") or {}).items():
        if isinstance(legacy, str) and isinstance(current, str):
            aliases[legacy] = current

    routing = rp.expand_placeholders(read_json(rp.routing_config_path()))
    for endpoint in routing.get("endpoints", []) or []:
        if not isinstance(endpoint, dict):
            continue
        model_id = endpoint.get("id") or endpoint.get("name")
        if not isinstance(model_id, str) or not model_id:
            continue
        record = dict(endpoint)
        record["reachable"] = bool(
            endpoint.get("enabled", True)
            and endpoint.get("status", "active") == "active"
        )
        _merge_inventory_record(records, model_id, record, source="routing")
        for alias in endpoint.get("fallback_ids", []) or []:
            if isinstance(alias, str) and alias:
                aliases.setdefault(alias, model_id)

    # ChatGPT/Codex subscription endpoints exist only in the connected SDK
    # session, never in routing-config.json. Merge that live inventory without
    # persisting it so health validation sees the same exact ids Router can
    # resolve. Import here avoids coupling module initialization to the
    # optional SDK adapter.
    try:
        try:
            from . import codex_subscription
        except ImportError:
            import codex_subscription  # type: ignore
        if codex_subscription.is_configured():
            for endpoint in codex_subscription.model_endpoints():
                if not isinstance(endpoint, dict):
                    continue
                model_id = endpoint.get("id")
                if not isinstance(model_id, str) or not model_id:
                    continue
                record = dict(endpoint)
                record["reachable"] = bool(
                    endpoint.get("enabled", True)
                    and endpoint.get("status", "active") == "active"
                )
                _merge_inventory_record(
                    records, model_id, record, source="subscription",
                )
    except Exception:
        # A disconnected or unavailable optional transport must not prevent
        # ordinary registry/routing/local health evaluation.
        pass

    models_json = read_json(rp.models_json_path())
    for key in ("local_models", "commercial_models"):
        for record in models_json.get(key, []) or []:
            if not isinstance(record, dict):
                continue
            model_id = record.get("id")
            if not isinstance(model_id, str) or not model_id:
                continue
            enriched = dict(record)
            if key == "local_models":
                model_path = record.get("path") or record.get("model_path")
                enriched["reachable"] = bool(model_path and Path(model_path).exists())
            _merge_inventory_record(records, model_id, enriched, source="models")

    catalog = read_json(rp.model_catalog_path())
    for record in catalog.get("models", []) or []:
        if isinstance(record, dict) and isinstance(record.get("id"), str):
            _merge_inventory_record(records, record["id"], record, source="catalog")

    # Exact, case-insensitive self aliases improve compatibility without
    # guessing that two different model names refer to the same thing.
    for model_id in records:
        aliases.setdefault(model_id.lower(), model_id)
    return {"models": records, "aliases": aliases, "routing": routing}


def _canonical_model_id(model_id: str, inventory: dict) -> str | None:
    records = inventory.get("models") or {}
    aliases = inventory.get("aliases") or {}
    current = model_id
    seen: set[str] = set()
    while isinstance(current, str) and current not in seen:
        seen.add(current)
        if current in records:
            return current
        target = aliases.get(current)
        if target is None:
            target = aliases.get(current.lower())
        if not isinstance(target, str) or not target:
            return None
        current = target
    return current if current in records else None


def _required_profile_complete(profile: dict) -> bool:
    try:
        return bool(ac._is_baseline_complete(profile))
    except Exception:
        return False


def evaluate_profile_health(profile: dict, inventory: dict | None = None) -> dict:
    """Classify one exact profile as ok/degraded/deprecated/unavailable."""
    inventory = inventory or load_model_inventory()
    records = inventory.get("models") or {}
    details: list[dict] = []
    deprecated_ids: list[str] = []
    unavailable_paths: list[str] = []
    degraded_paths: list[str] = []

    if not isinstance(profile, dict) or not _required_profile_complete(profile):
        return {
            "status": "unavailable",
            "reason": "required Model Profile slots are incomplete",
            "details": [],
            "deprecated_model_ids": [],
        }

    for path, cell in _iter_profile_cells(profile.get("cells") or {}):
        chain = [cell.get("primary"), *(cell.get("fallback") or [])]
        chain = [value for value in chain if isinstance(value, str) and value]
        if not chain:
            continue
        resolved: list[tuple[str, str | None, bool | None]] = []
        for model_id in chain:
            canonical = _canonical_model_id(model_id, inventory)
            reachable = None
            if canonical is not None:
                value = records.get(canonical, {}).get("reachable")
                reachable = value if isinstance(value, bool) else None
            resolved.append((model_id, canonical, reachable))
            if canonical is None and model_id not in deprecated_ids:
                deprecated_ids.append(model_id)

        operational = [row for row in resolved if row[1] is not None and row[2] is not False]
        path_text = ".".join(path)
        if not operational:
            unavailable_paths.append(path_text)
        primary = resolved[0]
        if primary[1] is not None and primary[2] is not True and operational:
            degraded_paths.append(path_text)
        details.append({
            "cell": path_text,
            "chain": [
                {"model_id": mid, "resolved_id": canonical, "reachable": reachable}
                for mid, canonical, reachable in resolved
            ],
        })

    if unavailable_paths:
        status = "unavailable"
        reason = "no usable model remains for: " + ", ".join(unavailable_paths)
    elif deprecated_ids:
        status = "deprecated"
        reason = "profile references retired or unresolvable models"
    elif degraded_paths:
        status = "degraded"
        reason = "preferred model health is unconfirmed; a usable chain remains"
    else:
        status = "ok"
        reason = "all required model chains resolve"
    return {
        "status": status,
        "reason": reason,
        "details": details,
        "deprecated_model_ids": deprecated_ids,
    }


def profile_summary(name: str, inventory: dict | None = None) -> dict:
    try:
        profile = _read_profile(name)
    except ModelProfileError as exc:
        return {
            "name": name,
            "digest": None,
            "health": {
                "status": "unavailable", "reason": str(exc),
                "details": [], "deprecated_model_ids": [],
            },
        }
    return {
        "name": name,
        "digest": profile_digest(profile),
        "health": evaluate_profile_health(profile, inventory),
    }


def list_profile_summaries() -> list[dict]:
    inventory = load_model_inventory()
    names: set[str] = set()
    for directory in ac._configuration_dirs_for_read():
        if directory.exists():
            names.update(path.stem for path in directory.glob("*.json"))
    names.difference_update(ac.SYSTEM_CONFIGS)
    return [profile_summary(name, inventory) for name in sorted(names, key=str.casefold)]


def decorate_configuration_catalog(catalog: dict) -> dict:
    """Add health without changing the compatibility shape of /api/configurations."""
    result = copy.deepcopy(catalog)
    inventory = load_model_inventory()
    for summary in (result.get("presets") or {}).values():
        if isinstance(summary, dict) and summary.get("name"):
            summary["health"] = profile_summary(summary["name"], inventory)["health"]
    for summary in result.get("customs", []) or []:
        if isinstance(summary, dict) and summary.get("name"):
            summary["health"] = profile_summary(summary["name"], inventory)["health"]
    return result


def _locked_routing_values(routing: dict) -> dict:
    slots = routing.get("slots") or {}
    return {
        "image_model": copy.deepcopy((slots.get("image_generates") or {}).get("preferred")),
        "vision_mode": {
            "vision_extraction": copy.deepcopy(routing.get("vision_extraction") or {}),
            "image_extracts": copy.deepcopy(slots.get("image_extracts") or {}),
            "vision_input": copy.deepcopy(slots.get("vision_input") or {}),
        },
    }


def _binding_digest(locks: dict) -> str:
    body = {key: value for key, value in locks.items() if key != "binding_digest"}
    return _digest(body)


def capture_project_binding(
    profile_name: str,
    project_nexus: str,
    routing_config: dict | None = None,
) -> dict:
    """Capture a project-owned immutable execution snapshot before binding."""
    profile_name = validate_profile_name(profile_name)
    project_nexus = pm.validate_nexus(project_nexus)
    profile = _read_profile(profile_name)
    _validate_ram_allocation(profile)
    health = evaluate_profile_health(profile)
    if health["status"] == "unavailable":
        raise ModelProfileError(
            f"cannot bind unavailable Model Profile {profile_name!r}: {health['reason']}"
        )
    if routing_config is None:
        try:
            routing_config = rp.expand_placeholders(
                json.loads(rp.routing_config_path().read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelProfileError(f"cannot capture model routing locks: {exc}") from exc
    routing_values = _locked_routing_values(routing_config)
    locks = {
        "schema_version": LOCK_SCHEMA_VERSION,
        "project_nexus": project_nexus,
        "profile_name": profile_name,
        "profile_digest": profile_digest(profile),
        "profile_snapshot": copy.deepcopy(profile),
        "toggles": copy.deepcopy(ac.get_toggles(profile_name)),
        "image_model": routing_values["image_model"],
        "vision_mode": routing_values["vision_mode"],
        "captured_at": _utc_now(),
    }
    locks["binding_digest"] = _binding_digest(locks)
    return locks


def validate_project_binding(
    record: dict | None, *, expected_nexus: str | None = None,
) -> dict:
    if not isinstance(record, dict):
        raise ModelProfileError("project Model Profile record is unavailable")
    name = record.get("default_model_profile")
    locks = record.get("model_locks")
    if not isinstance(name, str) or not name:
        raise ModelProfileError("project has no Model Profile binding")
    if not isinstance(locks, dict):
        raise ModelProfileError("project Model Profile locks are absent")
    if locks.get("schema_version") != LOCK_SCHEMA_VERSION:
        raise ModelProfileError("project Model Profile lock schema is unsupported")
    bound_nexus = locks.get("project_nexus")
    try:
        bound_nexus = pm.validate_nexus(bound_nexus)
    except (TypeError, ValueError) as exc:
        raise ModelProfileError("project Model Profile identity is invalid") from exc
    if expected_nexus is not None:
        expected_nexus = pm.validate_nexus(expected_nexus)
        if bound_nexus != expected_nexus:
            raise ModelProfileError(
                "project Model Profile identity does not match the requested project"
            )
    if locks.get("profile_name") != name:
        raise ModelProfileError("project Model Profile name does not match its lock")
    snapshot = locks.get("profile_snapshot")
    if not isinstance(snapshot, dict):
        raise ModelProfileError("project Model Profile snapshot is absent")
    if locks.get("profile_digest") != profile_digest(snapshot):
        raise ModelProfileError("project Model Profile snapshot digest is invalid")
    if locks.get("binding_digest") != _binding_digest(locks):
        raise ModelProfileError("project Model Profile binding digest is invalid")
    return copy.deepcopy(locks)


def project_lock_token(nexus: str, locks: dict) -> str:
    nexus = pm.validate_nexus(nexus)
    if locks.get("project_nexus") != nexus:
        raise ModelProfileError("project Model Profile identity does not match its token")
    digest = locks.get("binding_digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ModelProfileError("project Model Profile binding digest is invalid")
    return f"{LOCK_TOKEN_PREFIX}{nexus}:{digest}"


def load_project_locked_profile(token: str) -> dict:
    """Resolve a runtime-only project token back to its authenticated snapshot."""
    if not isinstance(token, str) or not token.startswith(LOCK_TOKEN_PREFIX):
        raise ModelProfileError("not a project Model Profile lock token")
    parts = token[len(LOCK_TOKEN_PREFIX):].rsplit(":", 1)
    if len(parts) != 2:
        raise ModelProfileError("malformed project Model Profile lock token")
    nexus, expected_digest = parts
    record = pm.read_project_meta(nexus)
    locks = validate_project_binding(record, expected_nexus=nexus)
    if locks["binding_digest"] != expected_digest:
        raise ModelProfileError("project Model Profile token is stale")
    profile = copy.deepcopy(locks["profile_snapshot"])
    _validate_ram_allocation(profile)
    return profile


def resolve_effective_profile(
    *,
    global_profile: str | None = None,
    project_nexus: str | None = None,
    process_profile: str | None = None,
    step_profile: str | None = None,
    one_run_profile: str | None = None,
    validate_selected: bool = True,
) -> dict:
    """Resolve the locked five-level inheritance contract; closer wins."""
    if global_profile is None:
        global_profile = ac.get_active_name()
    chain: list[dict] = []

    def add(source: str, name: str | None, runtime_name: str | None = None) -> None:
        if isinstance(name, str) and name.strip():
            chain.append({
                "source": source,
                "name": name.strip(),
                "runtime_name": runtime_name or name.strip(),
            })

    add("global", global_profile)
    if isinstance(project_nexus, str) and project_nexus.strip().lower() not in ("commons", "general"):
        record = pm.read_project_meta(project_nexus)
        project_name = (record or {}).get("default_model_profile")
        if isinstance(project_name, str) and project_name.strip():
            locks = validate_project_binding(record, expected_nexus=project_nexus)
            add("project", project_name, project_lock_token(project_nexus, locks))
    add("process", process_profile)
    add("step", step_profile)
    add("one_run", one_run_profile)
    if not chain:
        raise ModelProfileError("no Model Profile resolves from the inheritance chain")
    selected = chain[-1]
    if validate_selected:
        if selected["runtime_name"].startswith(LOCK_TOKEN_PREFIX):
            profile = load_project_locked_profile(selected["runtime_name"])
        else:
            profile = _read_profile(selected["runtime_name"])
            _validate_ram_allocation(profile)
        health = evaluate_profile_health(profile)
        if health["status"] == "unavailable":
            raise ModelProfileError(
                f"selected Model Profile {selected['name']!r} is unavailable: {health['reason']}"
            )
        selected = {**selected, "digest": profile_digest(profile), "health": health}
    return {"selected": selected, "chain": chain}


def routing_config_with_project_locks(routing: dict, locks: dict | None) -> dict:
    """Overlay only the two project-locked visual routing surfaces."""
    if not locks:
        return routing
    # Validate the exact lock independently of the caller's project record by
    # rechecking the binding digest over the supplied snapshot.
    if locks.get("binding_digest") != _binding_digest(locks):
        raise ModelProfileError("project Model Profile binding digest is invalid")
    out = copy.deepcopy(routing)
    out.setdefault("slots", {})
    image_model = locks.get("image_model")
    if isinstance(image_model, str) and image_model:
        current = copy.deepcopy(out["slots"].get("image_generates") or {})
        current["preferred"] = image_model
        out["slots"]["image_generates"] = current
    vision = locks.get("vision_mode")
    if isinstance(vision, dict):
        if isinstance(vision.get("vision_extraction"), dict):
            out["vision_extraction"] = copy.deepcopy(vision["vision_extraction"])
        for slot in ("image_extracts", "vision_input"):
            if isinstance(vision.get(slot), dict):
                out["slots"][slot] = copy.deepcopy(vision[slot])
    return out


def _provider_hint(model_id: str, record: dict | None) -> str:
    if isinstance(record, dict):
        value = record.get("provider") or record.get("vendor") or record.get("service")
        if isinstance(value, str) and value:
            return value.lower()
    raw = model_id.split(":", 1)[-1]
    return raw.split("/", 1)[0].lower() if "/" in raw else ""


def _replacement_for(model_id: str, inventory: dict) -> str | None:
    records = inventory.get("models") or {}
    aliases = inventory.get("aliases") or {}
    exact_alias = aliases.get(model_id) or aliases.get(model_id.lower())
    if isinstance(exact_alias, str) and exact_alias in records:
        return exact_alias

    # The catalog may retain metadata for an issued id after the live registry
    # drops it.  Use that evidence for similarity; never edit from a fuzzy id
    # guess alone.
    old = records.get(model_id) or {}
    old_provider = _provider_hint(model_id, old)
    old_vision = old.get("vision_capable")
    old_size = old.get("size_bucket")
    old_context = old.get("context_length") or old.get("context_window")
    old_intel = old.get("intelligence_score") or old.get("aa_intelligence_index")

    ranked: list[tuple[tuple, str]] = []
    for candidate_id, record in records.items():
        if candidate_id == model_id or not isinstance(record, dict):
            continue
        if record.get("reachable") is False:
            continue
        if (record.get("category") or "chat") != "chat":
            continue
        provider = _provider_hint(candidate_id, record)
        vision = record.get("vision_capable")
        size = record.get("size_bucket")
        context = record.get("context_length") or record.get("context_window")
        intel = record.get("intelligence_score") or record.get("aa_intelligence_index")
        score = (
            0 if old_provider and provider == old_provider else 1,
            0 if old_vision is not None and vision == old_vision else 1,
            0 if old_size and size == old_size else 1,
            abs(float(context or 0) - float(old_context or 0)) if old_context else 0,
            abs(float(intel or 0) - float(old_intel or 0)) if old_intel else 0,
            candidate_id,
        )
        ranked.append((score, candidate_id))
    return min(ranked)[1] if ranked else None


def _replace_model_ids(node: Any, replacements: dict[str, str]) -> Any:
    if isinstance(node, dict):
        return {key: _replace_model_ids(value, replacements) for key, value in node.items()}
    if isinstance(node, list):
        return [_replace_model_ids(value, replacements) for value in node]
    if isinstance(node, str) and node in replacements:
        return replacements[node]
    return node


def preview_migration(profile_name: str, project_nexus: str | None = None) -> dict:
    """Build a content-bound proposal.  This function is read-only."""
    profile_name = validate_profile_name(profile_name)
    target = "profile"
    locks = None
    if project_nexus:
        record = pm.read_project_meta(project_nexus)
        locks = validate_project_binding(record, expected_nexus=project_nexus)
        if locks["profile_name"] != profile_name:
            raise ModelProfileError("project is not bound to the requested Model Profile")
        profile = locks["profile_snapshot"]
        target = "project"
    else:
        profile = _read_profile(profile_name)
    inventory = load_model_inventory()
    health = evaluate_profile_health(profile, inventory)
    replacements: dict[str, str] = {}
    for model_id in health.get("deprecated_model_ids", []):
        replacement = _replacement_for(model_id, inventory)
        if replacement:
            replacements[model_id] = replacement
    if health["status"] != "deprecated" or not replacements:
        raise ModelProfileError(
            "the selected Model Profile has no reviewable deprecated-model migration"
        )
    proposed = _replace_model_ids(profile, replacements)
    proposal = {
        "schema_version": MIGRATION_SCHEMA_VERSION,
        "target": target,
        "profile_name": profile_name,
        "project_nexus": project_nexus or None,
        "expected_digest": profile_digest(profile),
        "proposed_digest": profile_digest(proposed),
        "replacements": replacements,
        "health_before": health["status"],
    }
    if target == "project":
        proposed_locks = copy.deepcopy(locks)
        proposed_locks["profile_snapshot"] = copy.deepcopy(proposed)
        proposed_locks["profile_digest"] = profile_digest(proposed)
        proposed_locks["binding_digest"] = _binding_digest(proposed_locks)
        proposal["expected_binding_digest"] = locks["binding_digest"]
        proposal["proposed_binding_digest"] = proposed_locks["binding_digest"]
    proposal["proposal_id"] = _digest(proposal)
    return proposal


def _read_receipts() -> list[dict]:
    try:
        lines = MIGRATION_RECEIPTS_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise ModelProfileError(
            f"Model Profile migration receipt history is unreadable: {exc}"
        ) from exc
    out: list[dict] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            raise ModelProfileError(
                f"Model Profile migration receipt history has a blank row at {line_number}"
            )
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ModelProfileError(
                f"Model Profile migration receipt history is malformed at row {line_number}"
            ) from exc
        if not isinstance(row, dict):
            raise ModelProfileError(
                f"Model Profile migration receipt history is malformed at row {line_number}"
            )
        out.append(row)
    return out


def _receipt_body(receipt: dict) -> dict:
    return {key: value for key, value in receipt.items() if key != "receipt_digest"}


def _validate_receipt(
    receipt: dict,
    *,
    proposal_id: str,
    profile_name: str,
    project_nexus: str | None,
) -> dict:
    """Authenticate one issued receipt and its proposal identity.

    The digest protects the exact receipt schema.  Reconstructing the proposal
    proves that the receipt describes the reviewed mutation, and the caller
    separately reauthenticates the current post-state before treating a retry
    as successful.
    """
    expected_keys = {
        "schema_version", "receipt_id", "proposal_id", "target",
        "profile_name", "project_nexus", "before_digest", "after_digest",
        "replacements", "user_confirmed", "recorded_at", "receipt_digest",
        "before_binding_digest", "after_binding_digest",
    }
    if not isinstance(proposal_id, str) or not re.fullmatch(r"[0-9a-f]{64}", proposal_id):
        raise ModelProfileError("Model Profile migration receipt proposal is invalid")
    try:
        profile_name = validate_profile_name(profile_name)
        if project_nexus is not None:
            project_nexus = pm.validate_nexus(project_nexus)
    except (TypeError, ValueError) as exc:
        raise ModelProfileError("Model Profile migration receipt target is invalid") from exc
    if set(receipt) != expected_keys:
        raise ModelProfileError("Model Profile migration receipt schema is invalid")
    if receipt.get("schema_version") != MIGRATION_SCHEMA_VERSION:
        raise ModelProfileError("Model Profile migration receipt schema is unsupported")
    if receipt.get("receipt_digest") != _digest(_receipt_body(receipt)):
        raise ModelProfileError("Model Profile migration receipt digest is invalid")
    if receipt.get("proposal_id") != proposal_id:
        raise ModelProfileError("Model Profile migration receipt proposal is invalid")
    if receipt.get("receipt_id") != "mpr-" + proposal_id[:24]:
        raise ModelProfileError("Model Profile migration receipt identity is invalid")
    target = "project" if project_nexus else "profile"
    if (
        receipt.get("target") != target
        or receipt.get("profile_name") != profile_name
        or receipt.get("project_nexus") != (project_nexus or None)
        or receipt.get("user_confirmed") is not True
    ):
        raise ModelProfileError("Model Profile migration receipt target is invalid")
    for key in ("before_digest", "after_digest"):
        if not isinstance(receipt.get(key), str) or not re.fullmatch(
            r"[0-9a-f]{64}", receipt[key]
        ):
            raise ModelProfileError("Model Profile migration receipt content digest is invalid")
    if (
        not isinstance(receipt.get("replacements"), dict)
        or not receipt["replacements"]
        or any(
            not isinstance(old, str) or not old
            or not isinstance(new, str) or not new
            for old, new in receipt["replacements"].items()
        )
    ):
        raise ModelProfileError("Model Profile migration receipt replacements are invalid")
    if not isinstance(receipt.get("recorded_at"), str) or not receipt["recorded_at"]:
        raise ModelProfileError("Model Profile migration receipt time is invalid")
    try:
        recorded_at = datetime.fromisoformat(receipt["recorded_at"])
    except ValueError as exc:
        raise ModelProfileError("Model Profile migration receipt time is invalid") from exc
    if recorded_at.tzinfo is None:
        raise ModelProfileError("Model Profile migration receipt time must include a timezone")
    if target == "project":
        for key in ("before_binding_digest", "after_binding_digest"):
            if not isinstance(receipt.get(key), str) or not re.fullmatch(
                r"[0-9a-f]{64}", receipt[key]
            ):
                raise ModelProfileError(
                    "Model Profile migration receipt binding digest is invalid"
                )
    elif receipt.get("before_binding_digest") is not None or receipt.get(
        "after_binding_digest"
    ) is not None:
        raise ModelProfileError("profile migration receipt has unexpected project binding")
    proposal = {
        "schema_version": MIGRATION_SCHEMA_VERSION,
        "target": target,
        "profile_name": profile_name,
        "project_nexus": project_nexus or None,
        "expected_digest": receipt["before_digest"],
        "proposed_digest": receipt["after_digest"],
        "replacements": receipt["replacements"],
        "health_before": "deprecated",
    }
    if target == "project":
        proposal["expected_binding_digest"] = receipt["before_binding_digest"]
        proposal["proposed_binding_digest"] = receipt["after_binding_digest"]
    if _digest(proposal) != proposal_id:
        raise ModelProfileError("Model Profile migration receipt does not match its proposal")
    return copy.deepcopy(receipt)


def _validate_receipt_post_state(receipt: dict) -> None:
    if receipt["target"] == "project":
        record = pm.read_project_meta(receipt["project_nexus"])
        locks = validate_project_binding(
            record, expected_nexus=receipt["project_nexus"],
        )
        if locks.get("profile_name") != receipt["profile_name"]:
            raise ModelProfileError("migrated project Model Profile name no longer matches")
        if (
            locks.get("profile_digest") != receipt["after_digest"]
            or locks.get("binding_digest") != receipt["after_binding_digest"]
        ):
            raise ModelProfileError("migrated project Model Profile post-state no longer matches")
        return
    current = _read_profile(receipt["profile_name"])
    if profile_digest(current) != receipt["after_digest"]:
        raise ModelProfileError("migrated Model Profile post-state no longer matches")


def _append_receipt(receipt: dict) -> None:
    MIGRATION_RECEIPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    rp.append_text_no_follow(
        MIGRATION_RECEIPTS_PATH, _canonical_json(receipt) + "\n",
    )


def confirm_migration(
    profile_name: str,
    proposal_id: str,
    *,
    user_confirmed: bool,
    project_nexus: str | None = None,
) -> dict:
    """Apply exactly one still-current proposal and return its receipt."""
    profile_name = validate_profile_name(profile_name)
    if project_nexus is not None:
        project_nexus = pm.validate_nexus(project_nexus)
    if user_confirmed is not True:
        raise ModelProfileError("explicit migration confirmation is required")
    if not isinstance(proposal_id, str) or not re.fullmatch(r"[0-9a-f]{64}", proposal_id):
        raise ModelProfileError("migration proposal identity is invalid")

    profile_lock = (
        rp.locked_file(ac._config_path(profile_name, for_write=True))
        if project_nexus is None else contextlib.nullcontext()
    )
    with _lock, rp.locked_file(MIGRATION_RECEIPTS_PATH), profile_lock:
        receipts = _read_receipts()
        for persisted in receipts:
            _validate_receipt(
                persisted,
                proposal_id=persisted.get("proposal_id"),
                profile_name=persisted.get("profile_name"),
                project_nexus=persisted.get("project_nexus"),
            )
        matching_receipts = [
            receipt for receipt in receipts
            if receipt.get("proposal_id") == proposal_id
        ]
        if len(matching_receipts) > 1:
            raise ModelProfileError("duplicate Model Profile migration receipts detected")
        if matching_receipts:
            receipt = _validate_receipt(
                matching_receipts[0], proposal_id=proposal_id,
                profile_name=profile_name, project_nexus=project_nexus,
            )
            _validate_receipt_post_state(receipt)
            return receipt
        proposal = preview_migration(profile_name, project_nexus)
        if proposal["proposal_id"] != proposal_id:
            raise ModelProfileError(
                "Model Profile or registry changed after preview; review a new proposal"
            )
        rollback = None
        if project_nexus:
            record = pm.read_project_meta(project_nexus)
            locks = validate_project_binding(record, expected_nexus=project_nexus)
            previous_locks = copy.deepcopy(locks)
            proposed = _replace_model_ids(
                locks["profile_snapshot"], proposal["replacements"],
            )
            _validate_ram_allocation(proposed)
            locks["profile_snapshot"] = proposed
            locks["profile_digest"] = profile_digest(proposed)
            locks["binding_digest"] = _binding_digest(locks)
            if locks["binding_digest"] != proposal["proposed_binding_digest"]:
                raise ModelProfileError(
                    "project Model Profile migration no longer matches the reviewed proposal"
                )
            updated = pm.set_project_model_binding(
                project_nexus, profile_name, locks,
            )
            if updated is None:
                raise ModelProfileError(f"project {project_nexus!r} no longer exists")
            rollback = lambda: pm.set_project_model_binding(
                project_nexus, profile_name, previous_locks,
            )
        else:
            current = _read_profile(profile_name)
            if profile_digest(current) != proposal["expected_digest"]:
                raise ModelProfileError(
                    "Model Profile changed after preview; review a new proposal"
                )
            proposed = _replace_model_ids(current, proposal["replacements"])
            _validate_ram_allocation(proposed)
            ac._save_config(profile_name, proposed, _locked=True)
            rollback = lambda: ac._save_config(
                profile_name, current, _locked=True,
            )

        receipt = {
            "schema_version": MIGRATION_SCHEMA_VERSION,
            "receipt_id": "mpr-" + proposal_id[:24],
            "proposal_id": proposal_id,
            "target": proposal["target"],
            "profile_name": profile_name,
            "project_nexus": project_nexus or None,
            "before_digest": proposal["expected_digest"],
            "after_digest": proposal["proposed_digest"],
            "replacements": proposal["replacements"],
            "user_confirmed": True,
            "recorded_at": _utc_now(),
            "before_binding_digest": proposal.get("expected_binding_digest"),
            "after_binding_digest": proposal.get("proposed_binding_digest"),
        }
        receipt["receipt_digest"] = _digest(receipt)
        try:
            _append_receipt(receipt)
        except Exception as exc:
            # The confirmed migration and its append-only receipt are one
            # authority unit.  A receipt failure may not leave a silently
            # changed profile behind.
            try:
                rollback()
            except Exception as rollback_exc:
                raise ModelProfileError(
                    "Model Profile migration receipt failed and rollback also "
                    f"failed: {rollback_exc}"
                ) from exc
            raise ModelProfileError(
                f"Model Profile migration receipt failed; mutation was rolled back: {exc}"
            ) from exc
        return receipt


__all__ = [
    "HEALTH_STATES", "LOCK_TOKEN_PREFIX", "ModelProfileError",
    "capture_project_binding", "confirm_migration",
    "decorate_configuration_catalog", "evaluate_profile_health",
    "list_profile_summaries", "load_model_inventory",
    "load_project_locked_profile", "preview_migration", "profile_digest",
    "profile_summary", "project_lock_token", "resolve_effective_profile",
    "routing_config_with_project_locks", "validate_profile_name",
    "validate_profile_allocation", "validate_project_binding",
]
