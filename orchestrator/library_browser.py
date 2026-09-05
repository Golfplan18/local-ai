"""Renderer-neutral aggregation for Ora's shared Library browse contract.

Providers enumerate their complete eligible rows before calling this module.
This module owns only normalization, deterministic identity/sort, complete-set
facets, and pagination.  It has no Flask, storage, search, or rendering
dependency and therefore cannot turn a visible page into the authoritative
universe by accident.
"""

from __future__ import annotations

import base64
from datetime import date, datetime
import logging
import math
from typing import Any, Callable, Iterable, Mapping


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
    "local_restriction", "file_type", "folder", "category", "nexus",
    "epistemic_kind", "extraction_date", "provenance_ids",
)
RELATIONSHIP_FAMILIES = {
    "evidence": ("supports", "contradicts", "qualifies"),
    "building": ("extends", "supersedes", "derived-from"),
    "causal": ("enables", "requires", "produces", "precedes"),
    "hierarchy": ("parent", "child", "analogous-to"),
}
REFINEMENT_FIELDS = {
    "item_type": "item_type", "tag": "tags", "lifecycle": "lifecycle",
    "privacy": "privacy", "local_restriction": "local_restriction",
    "file_type": "file_type", "folder": "folder", "category": "category",
    "content_type": "content_type", "epistemic_kind": "epistemic_kind",
    "provenance_id": "provenance_ids",
}
_LOG = logging.getLogger(__name__)


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


def validate_item_id(value: str, sources: Iterable[str]) -> str:
    """Validate canonical encoding; admission still belongs to the provider."""
    try:
        source, encoded = value.split(":", 1)
        identity = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True).decode("utf-8")
        if source not in sources or stable_item_id(source, identity) != value:
            raise ValueError
    except (ValueError, TypeError, UnicodeError, AttributeError):
        raise LibraryBrowserError("invalid stable Library identity") from None
    return value


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
    if isinstance(raw.get("sources"), list):
        normalized["sources"] = [dict(source) for source in raw["sources"]
                                 if isinstance(source, Mapping)]
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
        confidence = str(summary.get("confidence") if summary.get("confidence") is not None else "").strip()
        if confidence:
            item["confidence"] = confidence
        original_type = str(summary.get("original_type") or "").strip()
        if original_type:
            item["original_type"] = original_type
        for field in ("origin", "endpoint_id", "endpoint_title"):
            if isinstance(summary.get(field), str):
                item[field] = summary[field]
        if "original_type" in item:
            item["family"] = relationship_family(item["original_type"])
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
    for key in ("project_ids", "tags", "provenance_ids", "category", "nexus"):
        if key in metadata and metadata[key] is not None:
            metadata[key] = _string_list(metadata[key])
    unavailable = set(_string_list(row.get("unavailable_fields")))
    for field in METADATA_FIELDS:
        if field not in metadata or metadata[field] is None:
            unavailable.add(field)
    for field in tuple(unavailable):
        if field in metadata and metadata[field] is not None:
            unavailable.discard(field)

    normalized = {
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
    relationship_identity = str(
        row.get("_relationship_identity") or ""
    ).strip()
    if relationship_identity:
        normalized["_relationship_identity"] = relationship_identity
    return normalized


def validate_refinements(values: Mapping | None) -> dict:
    values = dict(values or {})
    permitted = set(REFINEMENT_FIELDS) | {
        "date_from", "date_to", "extraction_date_from", "extraction_date_to",
        "relationship", "relationship_family",
    }
    if set(values) - permitted:
        raise LibraryBrowserError("invalid Library refinement")
    result = {}
    for key, value in values.items():
        if value in (None, "", []):
            continue
        if key == "tag":
            result[key] = _string_list(value)
        elif not isinstance(value, str):
            raise LibraryBrowserError(f"invalid {key} refinement")
        else:
            result[key] = value.strip()
    for key in ("date_from", "date_to", "extraction_date_from", "extraction_date_to"):
        if key in result:
            try:
                if date.fromisoformat(result[key]).isoformat() != result[key]:
                    raise ValueError
            except ValueError:
                raise LibraryBrowserError(f"{key} must be YYYY-MM-DD") from None
    for prefix in ("date", "extraction_date"):
        if result.get(prefix + "_from", "") > result.get(prefix + "_to", "9999-12-31"):
            raise LibraryBrowserError(f"{prefix}_from must not be after {prefix}_to")
    for key, options in {
        "item_type": {"dialogue", "engram", "file"},
        "privacy": {"standard", "contains_private", "private", "stealth"},
        "lifecycle": {"active", "inactive", "indexed_archive", "indexed", "knowledge", "archived"},
        "local_restriction": {"restricted", "unrestricted"},
        "relationship_family": set(RELATIONSHIP_FAMILIES) | {"unclassified"},
    }.items():
        if key in result and result[key] not in options:
            raise LibraryBrowserError(f"invalid {key} refinement")
    if "provenance_id" in result:
        validate_item_id(result["provenance_id"], ("dialogues", "files"))
    return result


def relationship_family(kind: str) -> str:
    return next((family for family, kinds in RELATIONSHIP_FAMILIES.items() if kind in kinds), "unclassified")


def _matches_refinements(row, refinements) -> bool:
    metadata = row["metadata"]
    for key, field in REFINEMENT_FIELDS.items():
        if key not in refinements:
            continue
        value = metadata.get(field)
        if value is None:
            return False
        expected = refinements[key] if key == "tag" else [refinements[key]]
        actual = value if isinstance(value, list) else [value]
        if not all(item in actual for item in expected):
            return False
    for prefix, field in (("date", "modified_at"), ("extraction_date", "extraction_date")):
        lower, upper = refinements.get(prefix + "_from"), refinements.get(prefix + "_to")
        if not lower and not upper:
            continue
        try:
            observed = date.fromisoformat(str(metadata.get(field) or "")[:10]).isoformat()
        except ValueError:
            return False
        if lower and observed < lower or upper and observed > upper:
            return False
    return True


def _admitted_graph_edges(rows, snapshot):
    """Exact endpoint admission; a File can never stand in for an Engram."""
    by_stem = {}
    for row in rows:
        stem = row.get("_relationship_identity")
        if stem and row["source"] == "engrams":
            by_stem.setdefault(stem, []).append(row)
    unique = {stem: items[0] for stem, items in by_stem.items() if len(items) == 1}
    edges = []
    for edge in snapshot.get("edges", []):
        source, target = unique.get(edge.get("source")), unique.get(edge.get("target"))
        if source is None or target is None:
            continue
        edges.append({"source": source["id"], "target": target["id"],
                      "type": str(edge.get("type") or ""),
                      "confidence": str(edge.get("confidence") if edge.get("confidence") is not None else ""),
                      "family": relationship_family(str(edge.get("type") or ""))})
    return edges, unique, {stem for stem, items in by_stem.items() if len(items) > 1}


def build_trace(rows, selected_id, resolver, *, limit=50, refinements=None) -> dict:
    """Read a filtered, bounded one-hop neighborhood from admitted Engrams."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 50 or limit % 50:
        raise LibraryBrowserError("trace_limit must expand in batches of fifty")
    validate_item_id(selected_id, ("engrams",))
    selected = next((row for row in rows if row["id"] == selected_id and row["source"] == "engrams"), None)
    result = {"selected_id": selected_id, "rows": [], "edges": [], "remaining": 0,
              "total_neighbors": 0, "limit": limit, "state": "unavailable",
              "reason": "the selected Engram is outside the admitted filtered scope"}
    if selected is None or not selected.get("_relationship_identity") or resolver is None:
        return result
    try:
        snapshot = dict(resolver({selected["_relationship_identity"]}))
        edges, unique, ambiguous = _admitted_graph_edges(rows, snapshot)
        if selected["_relationship_identity"] in ambiguous:
            result["reason"] = "the selected Engram has an ambiguous graph identity"
            return result
        if snapshot.get("state") in {"unavailable", "incomplete"}:
            result.update(state=snapshot["state"], reason=snapshot.get("reason"))
            return result
        def weight(value):
            if value in {"high", "medium", "low"}:
                return {"high": 1, "medium": .7, "low": .3}[value]
            try:
                number = float(value)
                return number if math.isfinite(number) and 0 <= number <= 1 else -1
            except (TypeError, ValueError):
                return -1
        refinements = refinements or {}
        families = {family: {} for family in (*RELATIONSHIP_FAMILIES, "unclassified")}
        for edge in edges:
            if selected_id not in {edge["source"], edge["target"]}:
                continue
            if refinements.get("relationship") and edge["type"] != refinements["relationship"]:
                continue
            if refinements.get("relationship_family") and edge["family"] != refinements["relationship_family"]:
                continue
            neighbor = edge["target"] if edge["source"] == selected_id else edge["source"]
            if neighbor != selected_id:
                family = families[edge["family"]]
                family[neighbor] = max(family.get(neighbor, -1), weight(edge["confidence"]))
        queues = [iter(sorted(values, key=lambda key: (-values[key], key))) for values in families.values()]
        ordered, seen = [], set()
        while queues:
            remaining_queues = []
            for queue in queues:
                for neighbor in queue:
                    if neighbor not in seen:
                        seen.add(neighbor)
                        ordered.append(neighbor)
                        remaining_queues.append(queue)
                        break
            queues = remaining_queues
        displayed = {selected_id, *ordered[:limit]}
        selected_rows = [selected] + [next(row for row in rows if row["id"] == identity) for identity in ordered[:limit]]
        pair_snapshot = dict(resolver({row["_relationship_identity"] for row in selected_rows}))
        pair_edges, _unique, _ambiguous = _admitted_graph_edges(rows, pair_snapshot)
        result.update(rows=selected_rows,
                      edges=[edge for edge in pair_edges if edge["source"] in displayed and edge["target"] in displayed],
                      remaining=max(0, len(ordered) - limit), total_neighbors=len(ordered),
                      state=pair_snapshot.get("state", "unavailable"), reason=pair_snapshot.get("reason"),
                      updated_at=pair_snapshot.get("updated_at"))
        if ambiguous:
            result["ambiguity_reason"] = "Ambiguous admitted graph identities have no connectors."
        return result
    except Exception:
        _LOG.warning("Library Trace unavailable", exc_info=True)
        result["reason"] = "relationship snapshot is unavailable; inventory remains available"
        return result


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
    facets = {
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
    for field in ("file_type", "folder", "epistemic_kind", "extraction_date", "local_restriction"):
        facets[field] = _facet(rows, field, multiple=False)
    for field in ("category", "nexus", "provenance_ids"):
        facets[field] = _facet(rows, field, multiple=True)
    facets["category"]["labels"] = {key: label for row in rows
        for key, label in (row["metadata"].get("category_labels") or {}).items()
        if isinstance(label, str)}
    for field in ("relationship", "relationship_family"):
        counts = {}
        unavailable = 0
        for row in rows:
            relationship = row["relationships"]
            if relationship["state"] in {"unavailable", "incomplete"}:
                unavailable += 1
                continue
            kinds = {item.get("original_type", item["type"]) for item in relationship["summaries"]}
            values = kinds if field == "relationship" else {relationship_family(kind) for kind in kinds}
            for value in values:
                counts[value] = counts.get(value, 0) + 1
        facets[field] = {"counts": counts, "unavailable": unavailable}
    return facets


def build_browser_response(
    providers: Mapping[str, Mapping[str, Any]],
    *,
    requested_sources: Iterable[str] | None = None,
    project_id: str | None = "commons",
    query: str = "",
    offset: int = 0,
    limit: int = 100,
    relationship_resolver: Callable[[set[str]], Mapping[str, Any]] | None = None,
    refinements: Mapping | None = None,
    trace_id: str | None = None,
    trace_limit: int = 50,
) -> dict[str, Any]:
    """Aggregate complete provider universes, then page the normalized rows.

    ``providers`` maps each source to ``{"rows": [...], "complete": bool,
    "reason": str|None}``.  An incomplete provider may return safe partial
    rows, but the response keeps its total/facets explicitly incomplete.
    """

    sources = parse_sources(requested_sources)
    refinements = validate_refinements(refinements)
    scope = str(project_id or "").strip().lower()
    if scope in {"", "commons", "general"}:
        scope = "commons"
    query = str(query or "").strip()
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

    if scope != "commons":
        normalized = [
            row for row in normalized
            if scope in row["metadata"].get("project_ids", [])
        ]
    refinement_status = {}
    for key, value in refinements.items():
        field = REFINEMENT_FIELDS.get(key)
        unavailable = sum(1 for row in normalized if field and row["metadata"].get(field) is None)
        refinement_status[key] = {"value": value, "available": not (key == "local_restriction" and unavailable == len(normalized)),
                                  "unknown_count": unavailable,
                                  "reason": "Items without this metadata do not satisfy the refinement." if unavailable else None}
    normalized = [row for row in normalized if _matches_refinements(row, refinements)]

    relationship_requested = bool(refinements.get("relationship") or refinements.get("relationship_family"))
    if relationship_requested:
        identities = {row["_relationship_identity"] for row in normalized if row.get("_relationship_identity")}
        try:
            snapshot = dict(relationship_resolver(identities)) if relationship_resolver else {}
            if identities and snapshot.get("state") != "fresh":
                raise ValueError("current relationship membership is unavailable")
            edges, _unique, _ambiguous = _admitted_graph_edges(normalized, snapshot)
            membership = set()
            for edge in edges:
                if refinements.get("relationship") and edge["type"] != refinements["relationship"]:
                    continue
                if refinements.get("relationship_family") and edge["family"] != refinements["relationship_family"]:
                    continue
                membership.update((edge["source"], edge["target"]))
            for row in normalized:
                if row["source"] == "engrams":
                    continue
                authority = row["relationships"]
                if authority["state"] != "fresh":
                    raise ValueError("current relationship membership is unavailable")
                for item in authority["summaries"]:
                    kind = item.get("original_type", item["type"])
                    if (not refinements.get("relationship") or refinements["relationship"] == kind) and (not refinements.get("relationship_family") or refinements["relationship_family"] == relationship_family(kind)):
                        membership.add(row["id"])
            normalized = [row for row in normalized if row["id"] in membership]
        except Exception:
            for key in ("relationship", "relationship_family"):
                if key in refinements:
                    refinement_status[key].update(available=False, reason="Relationship refinement is unavailable; the other qualified inventory remains visible.")

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

    graph_rows = [
        row for row in normalized if row["source"] == "engrams" and row.get("_relationship_identity")
    ]
    if relationship_resolver is not None and graph_rows:
        page_identities = {
            row["_relationship_identity"]
            for row in page
            if row["source"] == "engrams" and row.get("_relationship_identity")
        }
        try:
            resolved = relationship_resolver(page_identities)
            snapshot = dict(resolved) if isinstance(resolved, Mapping) else {}
            common = _normalize_relationships({
                "state": snapshot.get("state"),
                "updated_at": snapshot.get("updated_at"),
                "reason": snapshot.get("reason"),
                "summaries": [],
            })
            items = (
                snapshot.get("items")
                if isinstance(snapshot.get("items"), Mapping) else {}
            )
            if "edges" in snapshot:
                admitted_edges, _unique, ambiguous = _admitted_graph_edges(normalized, snapshot)
                items = {}
                for row in graph_rows:
                    identity = row["_relationship_identity"]
                    summaries = []
                    if row["source"] == "engrams" and identity not in ambiguous:
                        for edge in admitted_edges:
                            if row["id"] in (edge["source"], edge["target"]):
                                summaries.append({"type": edge["type"], "original_type": edge["type"],
                                                  "direction": "outgoing" if row["id"] == edge["source"] else "incoming",
                                                  "confidence": edge["confidence"]})
                    items[identity] = {"summaries": summaries}
        except Exception:
            _LOG.warning("Library relationship resolution failed", exc_info=True)
            common = _normalize_relationships({
                "state": "unavailable",
                "reason": "relationship snapshot is unavailable",
                "summaries": [],
            })
            items = {}

        for row in graph_rows:
            row["relationships"] = dict(common, summaries=[])
        for row in page:
            identity = row.get("_relationship_identity")
            if not identity:
                continue
            item = items.get(identity)
            summaries = item.get("summaries") if isinstance(item, Mapping) else []
            row["relationships"] = _normalize_relationships({
                "state": common["state"],
                "updated_at": common["updated_at"],
                "reason": common["reason"],
                "summaries": summaries,
            })

    trace = build_trace(normalized, trace_id, relationship_resolver, limit=trace_limit, refinements=refinements) if trace_id else None
    facets = _facets(normalized)
    for facet in facets.values():
        facet["complete"] = complete
    if (len(graph_rows) > sum(row in page for row in graph_rows)
            or any(row["relationships"]["state"] in {"unavailable", "incomplete", "stale"} for row in normalized)):
        facets["relationship"]["complete"] = False
        facets["relationship_family"]["complete"] = False
    for row in normalized:
        row.pop("_relationship_identity", None)

    return {
        "sources": list(sources),
        "project_id": scope,
        "query": query,
        "refinements": refinement_status,
        "trace": trace,
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
