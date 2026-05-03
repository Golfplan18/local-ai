#!/usr/bin/env python3
"""
Ora Canvas File Format — server-side reader / writer for `.ora-canvas` and
`.ora-canvas.json` per Visual Intelligence Implementation Plan §11.7 and
WP-7.0.2.

Mirrors ``server/static/canvas-file-format.js`` so server-side code (vault
export, autosave persistence, server-rendered previews) can produce and
consume the same artifacts the client does. Both surfacing forms wrap the
SAME canonical JSON payload; round-trip is byte-identical after
decompression.

Public API::

    from orchestrator.canvas_file_format import (
        read_bytes, write_bytes,
        read_path, write_path,
        validate, new_canvas_state,
        is_compressed, SCHEMA_VERSION, FORMAT_ID,
    )

    state = new_canvas_state()
    blob  = write_bytes(state, compressed=True)        # → gzip bytes
    again = read_bytes(blob)                           # auto-detects gzip

The schema lives at ``~/ora/config/schemas/canvas-state.schema.json`` and
is the source of truth for the structure described here. The structural
fallback validator below is a stripped-down mirror of the JS module's,
used when ``jsonschema`` is unavailable.

Round-trip contract — for any state S with no ``NaN``/``Infinity``::

    read_bytes(write_bytes(S, compressed=True))  == S
    read_bytes(write_bytes(S, compressed=False)) == S
    gzip.decompress(write_bytes(S, compressed=True))
        == write_bytes(S, compressed=False)

The third invariant is the "bytes equivalent after decompression" criterion
from WP-7.0.2's test brief.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# ── Constants ───────────────────────────────────────────────────────────────

SCHEMA_VERSION = "0.1.0"
FORMAT_ID      = "ora-canvas"

# Default canvas dims per Plan §11.7 (10000 x 10000 px).
DEFAULT_CANVAS_W = 10000
DEFAULT_CANVAS_H = 10000

# gzip magic bytes (RFC 1952 §2.3.1).
_GZIP_MAGIC = b"\x1f\x8b"

# Canonical schema location (informational; this module is self-contained
# and does not need to import the schema for the structural fallback).
SCHEMAS_ROOT = Path(os.path.expanduser("~/ora/config/schemas"))
SCHEMA_PATH  = SCHEMAS_ROOT / "canvas-state.schema.json"

# ── Compression ─────────────────────────────────────────────────────────────

def is_compressed(blob: bytes) -> bool:
    """True iff the blob begins with the gzip magic 1F 8B."""
    return len(blob) >= 2 and blob[:2] == _GZIP_MAGIC


def _gzip_compress(data: bytes) -> bytes:
    # mtime=0 keeps the gzip header deterministic across writes — important
    # for test invariants that assert byte-equivalence between two writes
    # of the same canonical payload.
    return gzip.compress(data, compresslevel=6, mtime=0)


def _gzip_decompress(data: bytes) -> bytes:
    return gzip.decompress(data)


# ── Canonicalisation ────────────────────────────────────────────────────────

def _canonicalize(value: Any) -> Any:
    """Recursively sort dict keys; preserve list order. Mirrors the JS
    module's ``_canonicalize`` so both sides emit the same bytes for the
    same payload."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {k: _canonicalize(value[k]) for k in sorted(value.keys())}
    if isinstance(value, list):
        return [_canonicalize(v) for v in value]
    return value


def _serialize_json(state: dict, canonical: bool = True) -> bytes:
    payload = _canonicalize(state) if canonical else state
    # ``separators`` matches JSON.stringify's compact default (`,`/`:`).
    # ``ensure_ascii=False`` keeps the byte stream UTF-8 — Plan §11.7 image
    # payloads are ASCII base64, but free-form labels may carry Unicode.
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8")


# ── Public API ──────────────────────────────────────────────────────────────

def new_canvas_state(
    *,
    canvas_size: dict | None = None,
    layers: list[dict] | None = None,
    title: str | None = None,
    conversation_id: str | None = None,
    ora_version: str | None = None,
    now: str | None = None,
) -> dict:
    """Build an empty canvas state with the four canonical layers and a
    default 100%-zoom centered view. Mirrors the JS factory."""
    size = canvas_size or {"width": DEFAULT_CANVAS_W, "height": DEFAULT_CANVAS_H}
    timestamp = now or datetime.now(timezone.utc).isoformat()
    default_layers = [
        {"id": "background",  "kind": "background",  "visible": True, "locked": False, "opacity": 1},
        {"id": "annotation",  "kind": "annotation",  "visible": True, "locked": False, "opacity": 1},
        {"id": "user_input",  "kind": "user_input",  "visible": True, "locked": False, "opacity": 1},
        {"id": "selection",   "kind": "selection",   "visible": True, "locked": False, "opacity": 1},
    ]
    metadata: dict[str, Any] = {
        "canvas_size": {"width": size["width"], "height": size["height"]},
        "created_at": timestamp,
        "modified_at": timestamp,
    }
    if title:           metadata["title"] = title
    if conversation_id: metadata["conversation_id"] = conversation_id
    if ora_version:     metadata["ora_version"] = ora_version
    return {
        "schema_version": SCHEMA_VERSION,
        "format_id":      FORMAT_ID,
        "metadata":       metadata,
        "view":           {"zoom": 1, "pan": {"x": 0, "y": 0}},
        "layers":         layers if layers is not None else default_layers,
        "objects":        [],
    }


def write_bytes(state: dict, *, compressed: bool = True, canonical: bool = True) -> bytes:
    """Serialize a canvas-state object to wire bytes.

    ``compressed=True``  → gzip bytes (.ora-canvas, default save).
    ``compressed=False`` → UTF-8 JSON bytes (.ora-canvas.json).
    ``canonical=True``   → sort dict keys before serializing (default).
    """
    if not isinstance(state, dict):
        raise TypeError("write_bytes: state must be a dict")
    raw = _serialize_json(state, canonical=canonical)
    return _gzip_compress(raw) if compressed else raw


def write_json_string(state: dict, *, indent: int | None = None, canonical: bool = True) -> str:
    """Convenience helper for the ‘Save as readable copy’ command — returns
    a JSON string, optionally pretty-printed."""
    if not isinstance(state, dict):
        raise TypeError("write_json_string: state must be a dict")
    payload = _canonicalize(state) if canonical else state
    if indent and indent > 0:
        return json.dumps(payload, indent=indent, ensure_ascii=False)
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def read_bytes(blob: bytes) -> dict:
    """Parse wire bytes back into a canvas-state object. Auto-detects gzip
    vs raw JSON via header sniff."""
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        raise TypeError("read_bytes: blob must be bytes-like")
    data = bytes(blob)
    if is_compressed(data):
        data = _gzip_decompress(data)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"read_bytes: payload is not valid UTF-8: {e}") from e
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"read_bytes: invalid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ValueError("read_bytes: top-level value must be an object")
    if obj.get("format_id") != FORMAT_ID:
        raise ValueError(f"read_bytes: format_id mismatch (got {obj.get('format_id')!r})")
    return obj


def write_path(state: dict, path: str | os.PathLike, *, canonical: bool = True) -> Path:
    """Persist to ``path``. Extension drives compression:

    * ``.ora-canvas``      → gzip-compressed bytes
    * ``.ora-canvas.json`` → uncompressed UTF-8 JSON

    Returns the resolved Path."""
    p = Path(path)
    name = p.name.lower()
    if name.endswith(".ora-canvas.json"):
        compressed = False
    elif name.endswith(".ora-canvas"):
        compressed = True
    else:
        raise ValueError(
            f"write_path: unrecognised extension on {p.name!r}; expected '.ora-canvas' or '.ora-canvas.json'"
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(write_bytes(state, compressed=compressed, canonical=canonical))
    return p


def read_path(path: str | os.PathLike) -> dict:
    """Load a canvas state from a file. Compression is auto-detected from
    the bytes (so a hand-renamed file still parses correctly)."""
    p = Path(path)
    blob = p.read_bytes()
    return read_bytes(blob)


# ── Validation ──────────────────────────────────────────────────────────────

_ALLOWED_TOP = {"schema_version", "format_id", "metadata", "view", "layers", "objects"}
_LAYER_KINDS = {"background", "annotation", "user_input", "selection"}
_OBJECT_KINDS = {"shape", "text", "image", "group", "path"}
_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+(\.[0-9]+)?$")
_MIME_RE   = re.compile(r"^image/[A-Za-z0-9.+-]+$")


def _structural_validate(state: Any) -> tuple[bool, list[dict]]:
    errs: list[dict] = []
    if not isinstance(state, dict):
        errs.append({"path": "", "message": "state must be an object"})
        return False, errs

    for k in state.keys():
        if k not in _ALLOWED_TOP:
            errs.append({"path": f"/{k}", "message": "unknown top-level property"})

    for required in ("schema_version", "format_id", "metadata", "view", "layers", "objects"):
        if required not in state:
            errs.append({"path": f"/{required}", "message": "required"})

    if state.get("format_id") != FORMAT_ID:
        errs.append({"path": "/format_id", "message": f'must equal "{FORMAT_ID}"'})

    sv = state.get("schema_version")
    if not isinstance(sv, str) or not _SEMVER_RE.match(sv):
        errs.append({"path": "/schema_version", "message": "must be a semver string"})

    metadata = state.get("metadata")
    if isinstance(metadata, dict):
        cs = metadata.get("canvas_size")
        if not isinstance(cs, dict):
            errs.append({"path": "/metadata/canvas_size", "message": "required object with width+height"})
        else:
            if not isinstance(cs.get("width"), (int, float)) or cs.get("width", 0) <= 0:
                errs.append({"path": "/metadata/canvas_size/width", "message": "positive number required"})
            if not isinstance(cs.get("height"), (int, float)) or cs.get("height", 0) <= 0:
                errs.append({"path": "/metadata/canvas_size/height", "message": "positive number required"})
    else:
        errs.append({"path": "/metadata", "message": "required object"})

    view = state.get("view")
    if isinstance(view, dict):
        zoom = view.get("zoom")
        if not isinstance(zoom, (int, float)) or zoom <= 0:
            errs.append({"path": "/view/zoom", "message": "positive number required"})
        pan = view.get("pan")
        if not isinstance(pan, dict) or not isinstance(pan.get("x"), (int, float)) or not isinstance(pan.get("y"), (int, float)):
            errs.append({"path": "/view/pan", "message": "object with numeric x and y required"})
    else:
        errs.append({"path": "/view", "message": "required object"})

    layers = state.get("layers")
    if not isinstance(layers, list) or len(layers) < 1:
        errs.append({"path": "/layers", "message": "non-empty array required"})
    else:
        seen = set()
        for li, L in enumerate(layers):
            if not isinstance(L, dict):
                errs.append({"path": f"/layers[{li}]", "message": "object required"})
                continue
            if not isinstance(L.get("id"), str) or not L.get("id"):
                errs.append({"path": f"/layers[{li}]/id", "message": "non-empty string required"})
            if L.get("kind") not in _LAYER_KINDS:
                errs.append({"path": f"/layers[{li}]/kind", "message": "must be background|annotation|user_input|selection"})
            if isinstance(L.get("id"), str) and L["id"] in seen:
                errs.append({"path": f"/layers[{li}]/id", "message": f'duplicate layer id "{L["id"]}"'})
            seen.add(L.get("id"))

    objects = state.get("objects")
    if not isinstance(objects, list):
        errs.append({"path": "/objects", "message": "array required"})
    else:
        ids: set[str] = set()

        def _check_obj(O: Any, base: str) -> None:
            if not isinstance(O, dict):
                errs.append({"path": base, "message": "object required"})
                return
            if not isinstance(O.get("id"), str) or not O.get("id"):
                errs.append({"path": f"{base}/id", "message": "non-empty string required"})
            if O.get("kind") not in _OBJECT_KINDS:
                errs.append({"path": f"{base}/kind", "message": "must be shape|text|image|group|path"})
            if not isinstance(O.get("layer"), str) or not O.get("layer"):
                errs.append({"path": f"{base}/layer", "message": "non-empty layer reference required"})
            oid = O.get("id")
            if isinstance(oid, str):
                if oid in ids:
                    errs.append({"path": f"{base}/id", "message": f'duplicate object id "{oid}"'})
                ids.add(oid)
            if O.get("kind") == "image":
                I = O.get("image_data")
                if not isinstance(I, dict):
                    errs.append({"path": f"{base}/image_data", "message": "required for kind=image"})
                else:
                    mt = I.get("mime_type")
                    if not isinstance(mt, str) or not _MIME_RE.match(mt):
                        errs.append({"path": f"{base}/image_data/mime_type", "message": "must match image/<subtype>"})
                    if I.get("encoding") != "base64":
                        errs.append({"path": f"{base}/image_data/encoding", "message": 'must be "base64"'})
                    data_field = I.get("data")
                    if not isinstance(data_field, str) or not data_field:
                        errs.append({"path": f"{base}/image_data/data", "message": "non-empty base64 string required"})
                    elif data_field.startswith("data:"):
                        errs.append({"path": f"{base}/image_data/data", "message": "must NOT include a data: URL prefix; raw base64 only"})
            if O.get("kind") == "group":
                children = O.get("children")
                if not isinstance(children, list):
                    errs.append({"path": f"{base}/children", "message": "required array for kind=group"})
                else:
                    for ci, child in enumerate(children):
                        _check_obj(child, f"{base}/children[{ci}]")

        for oi, obj in enumerate(objects):
            _check_obj(obj, f"/objects[{oi}]")

    return (len(errs) == 0), errs


def validate(state: Any, *, use_jsonschema: bool = True) -> tuple[bool, list[dict]]:
    """Validate a canvas-state object.

    When ``use_jsonschema=True`` (default), tries to load the schema at
    ``SCHEMA_PATH`` and validate against it via the ``jsonschema`` library.
    Falls back to the structural check on any failure (missing schema,
    missing dependency, etc.). The structural check covers the
    load-bearing invariants — top-level required fields, layer/object
    enumerations, image-must-have-image_data — so callers get
    consistent semantics regardless of dependency availability.
    """
    if use_jsonschema:
        try:
            from jsonschema import Draft202012Validator  # type: ignore
            schema = json.loads(SCHEMA_PATH.read_text())
            validator = Draft202012Validator(schema)
            errs = sorted(validator.iter_errors(state), key=lambda e: list(e.absolute_path))
            if not errs:
                return True, []
            return False, [
                {"path": "/" + "/".join(str(p) for p in e.absolute_path), "message": e.message}
                for e in errs
            ]
        except Exception:
            # Fall through to structural fallback.
            pass
    return _structural_validate(state)


__all__ = [
    "SCHEMA_VERSION",
    "FORMAT_ID",
    "DEFAULT_CANVAS_W",
    "DEFAULT_CANVAS_H",
    "SCHEMA_PATH",
    "is_compressed",
    "new_canvas_state",
    "write_bytes",
    "write_json_string",
    "read_bytes",
    "write_path",
    "read_path",
    "validate",
]
