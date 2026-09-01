"""Renderer-neutral aggregation for Ora's shared Library browse contract.

Providers enumerate their complete eligible rows before calling this module.
This module owns only normalization, deterministic identity/sort, complete-set
facets, and pagination.  It has no Flask, storage, search, or rendering
dependency and therefore cannot turn a visible page into the authoritative
universe by accident.
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any, Iterable, Mapping


SOURCES = ("dialogues", "engrams", "files")
PREVIEW_KINDS = frozenset({"text", "visual", "mixed", "unsupported"})
PREVIEW_ROUTES = {
    "text": "text-pane",
    "visual": "visual-pane",
    "mixed": "text-and-visual-panes",
    "unsupported": "metadata-only",
}
RELATIONSHIP_STATES = frozenset({
    "fresh", "stale", "incomplete", "unavailable",
})
METADATA_FIELDS = (
    "project_ids",
    "tags",
    "lifecycle",
    "privacy",
    "modified_at",
    "content_type",
    "item_type",
)


class LibraryBrowserError(ValueError):
    """The provider contract or browse parameters are invalid."""


def parse_sources(values: Iterable[str] | None) -> tuple[str, ...]:
    """Normalize repeated/comma-delimited source values.

    Omission (and an explicitly empty parameter) means all sources.  Caller
    order is retained after deduplication so deterministic tie-breaking also
    respects a consumer's requested source order without deciding its UI.
    """

    if isinstance(values, str):
        values = (values,)
    requested: list[str] = []
    seen: set[str] = set()
    for raw in values or ():
        for part in str(raw or "").split(","):
            source = part.strip().lower()
            if not source:
                continue
            if source not in SOURCES:
                raise LibraryBrowserError(
                    f"invalid Library source {source!r}; expected "
                    + ", ".join(SOURCES)
                )
            if source not in seen:
                seen.add(source)
                requested.append(source)
    return tuple(requested or SOURCES)


def stable_item_id(source: str, identity: str) -> str:
    """Return a deterministic, reversible, source-namespaced item id."""

    if source not in SOURCES:
        raise LibraryBrowserError(f"invalid Library source {source!r}")
    value = str(identity or "").strip()
    if not value:
        raise LibraryBrowserError(f"{source} row has no stable identity")
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
    return f"{source}:{encoded.rstrip('=')}"


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _normalize_provenance(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, Mapping) else {}
    available = bool(raw.get("available"))
    identity = str(raw.get("identity") or "").strip() or None
    kind = str(raw.get("kind") or "").strip() or None
    if identity and kind and "available" not in raw:
        available = True
    reason = str(raw.get("reason") or "").strip() or None
    if not available and reason is None:
        reason = "provenance authority is unavailable"
    normalized = {
        "available": available,
        "kind": kind,
        "identity": identity,
        "reason": reason,
    }
    details = raw.get("details")
    if isinstance(details, Mapping) and details:
        normalized["details"] = dict(details)
    return normalized


def _normalize_relationships(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, Mapping) else {}
    state = str(raw.get("state") or "unavailable").strip().lower()
    if state not in RELATIONSHIP_STATES:
        raise LibraryBrowserError(f"invalid relationship state {state!r}")
    summaries: list[dict[str, Any]] = []
    for summary in raw.get("summaries") or ():
        if not isinstance(summary, Mapping):
            continue
        relation_type = str(summary.get("type") or "").strip()
        direction = str(summary.get("direction") or "").strip().lower()
        if not relation_type or direction not in {
            "incoming", "outgoing", "peer",
        }:
            continue
        item = {"type": relation_type, "direction": direction}
        count = summary.get("count")
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            item["count"] = count
        confidence = str(summary.get("confidence") or "").strip()
        if confidence:
            item["confidence"] = confidence
        original_type = str(summary.get("original_type") or "").strip()
        if original_type:
            item["original_type"] = original_type
        summaries.append(item)
    summaries.sort(key=lambda item: (
        item["direction"], item["type"], item.get("confidence", ""),
    ))
    reason = str(raw.get("reason") or "").strip() or None
    if state in {"incomplete", "unavailable"} and reason is None:
        reason = "relationship authority is incomplete"
    return {
        "state": state,
        "updated_at": str(raw.get("updated_at") or "").strip() or None,
        "reason": reason,
        "summaries": summaries,
    }


def _normalize_preview(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, Mapping) else {}
    kind = str(raw.get("kind") or "unsupported").strip().lower()
    if kind not in PREVIEW_KINDS:
        raise LibraryBrowserError(f"invalid preview kind {kind!r}")
    available = bool(raw.get("available", kind != "unsupported"))
    reason = str(raw.get("reason") or "").strip() or None
    if not available and reason is None:
        reason = "preview is unavailable for this item"
    normalized = {
        "kind": kind,
        "route": PREVIEW_ROUTES[kind],
        "available": available,
        "reason": reason,
    }
    locator = raw.get("locator")
    if isinstance(locator, Mapping) and locator:
        normalized["locator"] = dict(locator)
    return normalized


def _normalize_editability(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, Mapping) else {}
    available = bool(raw.get("available"))
    editable = raw.get("editable")
    if available and not isinstance(editable, bool):
        raise LibraryBrowserError(
            "available editability requires a Boolean editable value"
        )
    if not available:
        editable = None
    reason = str(raw.get("reason") or "").strip() or None
    if not available and reason is None:
        reason = "source edit policy is unavailable"
    normalized = {
        "available": available,
        "editable": editable,
        "descriptor_only": True,
        "reason": reason,
    }
    surface = str(raw.get("surface") or "").strip() or None
    if surface:
        normalized["surface"] = surface
    return normalized


def normalize_row(source: str, row: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one provider row without inventing unavailable metadata."""

    if source not in SOURCES:
        raise LibraryBrowserError(f"invalid Library source {source!r}")
    if not isinstance(row, Mapping):
        raise LibraryBrowserError(f"{source} provider returned a non-object row")
    identity = str(row.get("identity") or "").strip()
    item_id = stable_item_id(source, identity)
    title = str(row.get("title") or "").strip() or "(untitled)"

    metadata = (
        dict(row.get("metadata"))
        if isinstance(row.get("metadata"), Mapping) else {}
    )
    for key in ("project_ids", "tags"):
        if key in metadata and metadata[key] is not None:
            metadata[key] = _string_list(metadata[key])
    unavailable = set(_string_list(row.get("unavailable_fields")))
    for field in METADATA_FIELDS:
        if field not in metadata or metadata[field] is None:
            unavailable.add(field)
    for field in tuple(unavailable):
        if field in metadata and metadata[field] is not None:
            unavailable.discard(field)

    return {
        "id": item_id,
        "source": source,
        "title": title,
        "metadata": metadata,
        "unavailable_fields": sorted(unavailable),
        "provenance": _normalize_provenance(row.get("provenance")),
        "relationships": _normalize_relationships(row.get("relationships")),
        "preview": _normalize_preview(row.get("preview")),
        "editability": _normalize_editability(row.get("editability")),
    }


def _timestamp(value: Any) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except (OverflowError, TypeError, ValueError):
        return None


def _facet(rows: list[dict[str, Any]], field: str, *, multiple: bool) -> dict:
    counts: dict[str, int] = {}
    unavailable = 0
    for row in rows:
        if field in row["unavailable_fields"]:
            unavailable += 1
            continue
        value = row["metadata"].get(field)
        values = _string_list(value) if multiple else [str(value)]
        for item in values:
            if item:
                counts[item] = counts.get(item, 0) + 1
    return {
        "counts": dict(sorted(counts.items())),
        "unavailable": unavailable,
    }


def _facets(rows: list[dict[str, Any]]) -> dict[str, Any]:
    preview_counts = {kind: 0 for kind in sorted(PREVIEW_KINDS)}
    relationship_counts = {state: 0 for state in sorted(RELATIONSHIP_STATES)}
    editability_counts = {"editable": 0, "read_only": 0, "unavailable": 0}
    for row in rows:
        preview_counts[row["preview"]["kind"]] += 1
        relationship_counts[row["relationships"]["state"]] += 1
        editability = row["editability"]
        if not editability["available"]:
            editability_counts["unavailable"] += 1
        elif editability["editable"]:
            editability_counts["editable"] += 1
        else:
            editability_counts["read_only"] += 1
    return {
        "projects": _facet(rows, "project_ids", multiple=True),
        "tags": _facet(rows, "tags", multiple=True),
        "lifecycle": _facet(rows, "lifecycle", multiple=False),
        "privacy": _facet(rows, "privacy", multiple=False),
        "content_type": _facet(rows, "content_type", multiple=False),
        "item_type": _facet(rows, "item_type", multiple=False),
        "preview": {"counts": preview_counts, "unavailable": 0},
        "relationships": {"counts": relationship_counts, "unavailable": 0},
        "editability": {"counts": editability_counts, "unavailable": 0},
    }


def build_browser_response(
    providers: Mapping[str, Mapping[str, Any]],
    *,
    requested_sources: Iterable[str] | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """Aggregate complete provider universes, then page the normalized rows.

    ``providers`` maps each source to ``{"rows": [...], "complete": bool,
    "reason": str|None}``.  An incomplete provider may return safe partial
    rows, but the response keeps its total/facets explicitly incomplete.
    """

    sources = parse_sources(requested_sources)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise LibraryBrowserError("offset must be a non-negative integer")
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit < 1
        or limit > 500
    ):
        raise LibraryBrowserError("limit must be an integer from 1 to 500")

    normalized: list[dict[str, Any]] = []
    provider_state: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    for source in sources:
        result = providers.get(source)
        result = dict(result) if isinstance(result, Mapping) else {}
        complete = bool(result.get("complete"))
        reason = str(result.get("reason") or "").strip() or None
        if not complete and reason is None:
            reason = f"{source} provider is unavailable"
        provider_state[source] = {"complete": complete, "reason": reason}
        rows = result.get("rows")
        if not isinstance(rows, (list, tuple)):
            rows = []
        for raw in rows:
            try:
                item = normalize_row(source, raw)
            except LibraryBrowserError:
                provider_state[source] = {
                    "complete": False,
                    "reason": f"{source} provider returned an invalid row",
                }
                continue
            if item["id"] in seen_ids:
                provider_state[source] = {
                    "complete": False,
                    "reason": (
                        f"{source} provider returned a duplicate stable identity"
                    ),
                }
                continue
            seen_ids.add(item["id"])
            normalized.append(item)

    source_rank = {source: index for index, source in enumerate(sources)}
    normalized.sort(key=lambda row: (
        0 if _timestamp(row["metadata"].get("modified_at")) is not None else 1,
        -(_timestamp(row["metadata"].get("modified_at")) or 0.0),
        source_rank[row["source"]],
        row["title"].casefold(),
        row["id"],
    ))
    complete = all(provider_state[source]["complete"] for source in sources)
    unavailable_sources = [
        {"source": source, "reason": provider_state[source]["reason"]}
        for source in sources
        if not provider_state[source]["complete"]
    ]
    source_counts = {
        source: sum(1 for row in normalized if row["source"] == source)
        for source in sources
    }
    page = normalized[offset:offset + limit]
    next_offset = offset + len(page)
    if next_offset >= len(normalized):
        next_offset = None
    facets = _facets(normalized)
    for facet in facets.values():
        facet["complete"] = complete

    return {
        "sources": list(sources),
        "rows": page,
        "total": len(normalized),
        "source_counts": source_counts,
        "facets": facets,
        "universe": {
            "complete": complete,
            "providers": provider_state,
            "unavailable_sources": unavailable_sources,
        },
        "pagination": {
            "offset": offset,
            "limit": limit,
            "returned": len(page),
            "has_more": next_offset is not None,
            "next_offset": next_offset,
        },
    }
