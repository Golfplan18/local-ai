#!/usr/bin/env python3
"""
Ora vault export — WP-6.1

Writes a conversation as a canonical Markdown document into the Obsidian
vault at ``~/Documents/vault/Sessions/<YYYY-MM-DD>-<slug>.md`` plus a
companion SVG sidecar for every ``ora-visual`` fenced JSON block found in
assistant messages.

Reading the conversation
------------------------

The module looks at two locations, in order:

  1. ``<sessions_root>/<conversation_id>/conversation.json`` — structured
     message log. The native format when available.

  2. ``~/Documents/conversations/raw/*.md`` — the raw log produced by
     ``server.py::_save_conversation``. The matching file is the one whose
     frontmatter/header contains ``panel_id: <conversation_id>``. When
     multiple files match, the most recently modified wins.

If neither source exists we raise ``FileNotFoundError``. No silent-skip.

Rendering the sidecars
----------------------

For every valid ``ora-visual`` envelope in assistant messages we call the
Node CLI at
``~/ora/server/static/ora-visual-compiler/tools/render-envelope.js`` with
the envelope on stdin. stdout is written as ``<session-name>.fig-<N>.svg``
next to the Markdown. Invalid envelopes and CLI failures generate warnings
(never abort the export) — the Markdown is the source of truth, and the
user can regenerate sidecars by re-opening the session in Ora.

Markdown shape (Phase 5.7, Schema §12 chunk template)
-----------------------------------------------------

  ---
  nexus:
    - <topic-derived from Master Matrix; section absent if domain-general>
  type: chat
  tags:
    - <controlled-vocabulary tags; section absent if none>
  date created: YYYY-MM-DD
  date modified: YYYY-MM-DD
  ---
  # <title>

  **Conversation ID:** <id>
  **Exported:** <iso>

  ## Exchanges

  ### Turn 1 — <timestamp>
  **User:** …
  **Assistant:**
  …fenced ``ora-visual`` JSON kept verbatim…
  ![[<session-name>.fig-1.svg]]

The conversation_id and session_title are kept in the body's meta
block (preserves the back-link to the source session) but are not
in the YAML frontmatter — Schema §12 keeps the conversation chunk
template minimal. Filename includes HH-MM to prevent same-day
collisions when multiple sessions are exported on the same date.

This module is deliberately free of Flask; the HTTP wrapper lives in
``server.py`` as ``POST /api/session/export``.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional

# visual_validator lives in the same orchestrator package. Import lazily so
# tests that stub the validator don't need to boot the jsonschema layer.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ExportResult:
    """Return value of :func:`export_session_to_vault`."""

    markdown_path: Path
    sidecar_paths: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    envelope_count: int = 0
    invalid_envelopes: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "markdown_path": str(self.markdown_path),
            "sidecar_paths": [str(p) for p in self.sidecar_paths],
            "warnings": list(self.warnings),
            "envelope_count": self.envelope_count,
            "invalid_envelopes": list(self.invalid_envelopes),
        }


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Node CLI used to render envelope → SVG.
_DEFAULT_RENDER_CLI = Path.home() / "ora" / "server" / "static" / "ora-visual-compiler" / "tools" / "render-envelope.js"

# Where the chat server writes raw conversation logs.
_DEFAULT_RAW_CONVERSATIONS = Path.home() / "Documents" / "conversations" / "raw"

# Per-session auxiliary root (uploads, vision retry queue, future
# conversation.json). When a ``conversation.json`` shows up here the export
# path prefers it.
_DEFAULT_SESSIONS_ROOT = Path.home() / "ora" / "sessions"

# The sidecar-gitignore pattern: everything we emit is ``*.fig-*.svg``.
_SIDECAR_GITIGNORE_PATTERN = "*.fig-*.svg"

# Used by filename sanitization. Keeps ASCII alphanumerics and hyphen.
_SLUG_KEEP = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------------------------
# Filename / slug helpers
# ---------------------------------------------------------------------------


def _slugify(text: str, max_words: int = 6, max_chars: int = 60) -> str:
    """Sanitize arbitrary text into an ASCII filename slug.

    * lowercased
    * non-alphanumeric runs → ``-``
    * leading/trailing hyphens trimmed
    * truncated to ``max_words`` words (word count, not char)
    * then truncated to ``max_chars`` chars as a final safety cap
    """
    if not text:
        return ""
    lowered = text.lower()
    # Replace non-alphanumeric runs with spaces first so word-count works.
    spaced = _SLUG_KEEP.sub(" ", lowered).strip()
    words = [w for w in spaced.split() if w]
    if max_words and len(words) > max_words:
        words = words[:max_words]
    slug = "-".join(words).strip("-")
    if max_chars and len(slug) > max_chars:
        slug = slug[:max_chars].rstrip("-")
    return slug


def _derive_session_name(
    session_title: str | None,
    conversation_id: str,
    first_user_message: str | None,
    when: datetime | date | None = None,
) -> str:
    """Return the filesystem stem ``YYYY-MM-DD-HH-MM-<slug>`` for the
    markdown doc.

    HH-MM is included in the stem to prevent same-day collisions when
    multiple sessions export on the same date (Phase 5.7 / Q4
    requirement).

    For backward compat: callers who pass a `date` (not a `datetime`)
    get the time defaulted to 00-00 so explicit-date tests stay
    deterministic.
    """
    if when is None:
        when = datetime.now()
    if isinstance(when, datetime):
        date_str = when.strftime("%Y-%m-%d-%H-%M")
    else:
        # date instance → no time component; use 00-00 sentinel
        date_str = when.strftime("%Y-%m-%d") + "-00-00"

    if session_title:
        slug = _slugify(session_title)
    elif first_user_message:
        slug = _slugify(first_user_message)
    else:
        slug = ""

    if not slug:
        # conversation_id may be a UUID-hex or something arbitrary; take
        # first 8 chars after slugifying so we always end up with ASCII.
        id_slug = _slugify(conversation_id) or "session"
        slug = f"session-{id_slug[:8]}"

    return f"{date_str}-{slug}"


# ---------------------------------------------------------------------------
# Conversation loading
# ---------------------------------------------------------------------------


def _load_structured_conversation(sessions_root: Path, conversation_id: str) -> dict[str, Any] | None:
    """Look for ``<sessions_root>/<conversation_id>/conversation.json``.

    Expected shape:
        {
          "conversation_id": "...",
          "session_title": "...",            # optional
          "created_at": "ISO-8601",           # optional
          "messages": [
            {"role": "user" | "assistant" | "system",
             "content": "...",
             "timestamp": "ISO-8601"          # optional
            }, ...
          ]
        }

    Returns None when the file is absent.
    """
    path = sessions_root / conversation_id / "conversation.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("messages"), list):
        return None
    return data


def _parse_raw_session_log(text: str) -> list[dict[str, Any]]:
    """Parse a raw session log (server.py ``_save_conversation`` format).

    Returns a list of messages with role/content. A raw log looks like::

        # Session <id>
        session_start: ...
        panel_id: ...
        ...
        ---
        <!-- pair 001 | <timestamp> -->
        **User:** <input>
        **Assistant:** <output>
        ---
        <!-- pair 002 | <timestamp> -->
        ...
    """
    messages: list[dict[str, Any]] = []
    # Split on pair boundaries — the ``<!-- pair NNN | ts -->`` comment
    # is the most reliable cut.
    pair_re = re.compile(r"<!--\s*pair\s+(\d+)\s*\|\s*([^>]+?)\s*-->", re.IGNORECASE)
    cuts = [(m.start(), m.group(1), m.group(2).strip()) for m in pair_re.finditer(text)]
    if not cuts:
        return messages

    for i, (start, pair_num, ts) in enumerate(cuts):
        end = cuts[i + 1][0] if i + 1 < len(cuts) else len(text)
        block = text[start:end]
        # Strip the comment header itself
        block = pair_re.sub("", block, count=1).strip()
        # Strip the trailing --- separator
        block = re.sub(r"\n---\s*$", "", block).strip()

        # User segment
        user_match = re.search(r"\*\*User:\*\*\s*(.+?)(?=\n\s*\*\*Assistant:\*\*|\Z)", block, re.DOTALL)
        # Assistant segment
        asst_match = re.search(r"\*\*Assistant:\*\*\s*(.+?)\Z", block, re.DOTALL)

        if user_match:
            messages.append({
                "role": "user",
                "content": user_match.group(1).strip(),
                "timestamp": ts,
                "pair": int(pair_num),
            })
        if asst_match:
            messages.append({
                "role": "assistant",
                "content": asst_match.group(1).strip(),
                "timestamp": ts,
                "pair": int(pair_num),
            })
    return messages


def _load_raw_conversation(raw_dir: Path, conversation_id: str) -> dict[str, Any] | None:
    """Find the raw session log whose panel_id matches ``conversation_id``.

    Returns the same shape as :func:`_load_structured_conversation` so the
    rest of the pipeline doesn't branch on source.
    """
    if not raw_dir.is_dir():
        return None

    # Also match by the session-id token in the filename (e.g.
    # ``2026-04-01_07-29_session-ad4d24.md`` where ``conversation_id``
    # equals ``ad4d24``).
    candidates: list[tuple[float, Path, str]] = []  # (mtime, path, src_text)
    panel_re = re.compile(r"panel_id:\s*(\S+)", re.IGNORECASE)
    session_re = re.compile(r"#\s*Session\s+([A-Za-z0-9]+)", re.IGNORECASE)

    for p in raw_dir.glob("*.md"):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        panel_match = panel_re.search(text)
        session_match = session_re.search(text)
        matched = False
        if panel_match and panel_match.group(1) == conversation_id:
            matched = True
        elif session_match and session_match.group(1) == conversation_id:
            matched = True
        if matched:
            try:
                mtime = p.stat().st_mtime
            except OSError:
                mtime = 0.0
            candidates.append((mtime, p, text))

    if not candidates:
        return None

    # Most-recently-modified wins (resumed sessions rewrite the file).
    candidates.sort(reverse=True)
    _mtime, path, text = candidates[0]

    messages = _parse_raw_session_log(text)
    # Session header fields
    start_match = re.search(r"session_start:\s*(.+)", text)
    model_match = re.search(r"model:\s*(\S+)", text)
    created_at = start_match.group(1).strip() if start_match else None

    return {
        "conversation_id": conversation_id,
        "session_title": None,
        "created_at": created_at,
        "model": model_match.group(1).strip() if model_match else None,
        "messages": messages,
        "_source_path": str(path),
    }


def _load_conversation(
    conversation_id: str,
    sessions_root: Path,
    raw_conversations_dir: Path,
) -> dict[str, Any]:
    """Pick up a conversation from whichever source has it.

    Raises FileNotFoundError when neither path carries the id.
    """
    structured = _load_structured_conversation(sessions_root, conversation_id)
    if structured is not None:
        return structured

    raw = _load_raw_conversation(raw_conversations_dir, conversation_id)
    if raw is not None:
        return raw

    raise FileNotFoundError(
        f"No conversation found for id '{conversation_id}'. "
        f"Looked under {sessions_root}/{conversation_id}/conversation.json "
        f"and {raw_conversations_dir}/*.md (by panel_id)."
    )


# ---------------------------------------------------------------------------
# ora-visual block extraction
# ---------------------------------------------------------------------------

# Fenced-code scanner. Captures the raw JSON body between the fences so we
# can both validate it AND preserve the exact original text in the exported
# markdown.
_FENCE_RE = re.compile(
    r"(?P<fence>```+)\s*ora-visual\s*\n(?P<body>.*?)(?P=fence)",
    re.DOTALL | re.IGNORECASE,
)


def _extract_ora_visuals(content: str) -> list[dict[str, Any]]:
    """Return a list of ``{start, end, body, envelope, parse_error}`` dicts.

    ``body`` is the raw string between the fences (whitespace-trimmed).
    ``envelope`` is the parsed JSON object, or None on parse failure.
    ``parse_error`` is a string message when JSON parsing failed; else ``""``.

    Positions are into ``content`` (useful if the caller wants to splice).
    """
    results: list[dict[str, Any]] = []
    for m in _FENCE_RE.finditer(content):
        body = m.group("body").strip()
        envelope: dict[str, Any] | None = None
        parse_error = ""
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                envelope = parsed
            else:
                parse_error = "parsed JSON is not an object"
        except json.JSONDecodeError as e:
            parse_error = str(e)
        results.append({
            "start": m.start(),
            "end": m.end(),
            "body": body,
            "envelope": envelope,
            "parse_error": parse_error,
        })
    return results


# ---------------------------------------------------------------------------
# Sidecar SVG rendering (Node CLI subprocess)
# ---------------------------------------------------------------------------


def _render_envelope_to_svg(
    envelope: dict[str, Any],
    node_cli: Path,
    timeout_s: float = 60.0,
) -> tuple[str, str]:
    """Invoke the Node CLI on an envelope. Returns ``(svg, error_message)``.

    ``error_message`` is empty on success. On failure the SVG is "" and
    the message is a short human-readable summary suitable for a warning.
    """
    if not node_cli.exists():
        return "", f"Node CLI not found at {node_cli}"

    try:
        proc = subprocess.run(
            ["node", str(node_cli)],
            input=json.dumps(envelope),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "", f"Node CLI timed out after {timeout_s}s"
    except FileNotFoundError:
        return "", "node executable not on PATH"
    except OSError as e:
        return "", f"Node CLI subprocess error: {e}"

    if proc.returncode != 0:
        # Prefer the structured JSON kind on stderr if present.
        detail = ""
        for ln in (proc.stderr or "").splitlines():
            ln = ln.strip()
            if ln.startswith("{"):
                try:
                    rec = json.loads(ln)
                    detail = rec.get("kind", "") or rec.get("message", "")
                    break
                except json.JSONDecodeError:
                    continue
        if not detail:
            detail = (proc.stderr or "").strip().splitlines()[-1][:200] if proc.stderr else "non-zero exit"
        return "", f"Node CLI exit {proc.returncode}: {detail}"

    svg = proc.stdout or ""
    if not svg.lstrip().startswith("<svg"):
        return "", "Node CLI stdout did not begin with <svg"
    return svg, ""


# ---------------------------------------------------------------------------
# Markdown assembly
# ---------------------------------------------------------------------------


def _build_canonical_frontmatter(
    nexus: list[str] | None = None,
    type_: str = "chat",
    tags: list[str] | None = None,
    created_at: str | None = None,
    modified_at: datetime | None = None,
) -> str:
    """Produce YAML frontmatter per Schema §12 conversation chunk template.

    Keys (canonical order from Schema §11):
        nexus, type, tags, date created, date modified

    Empty lists are emitted as bare key (Schema §10 rule 4):
        nexus:
        tags:

    `conversation_id` and `session_title` are NOT included — they live
    in the body's meta block per Phase 5.7. Date format is YYYY-MM-DD
    (Schema §10 rule 9).
    """
    modified_at = modified_at or datetime.now()
    date_created = _format_vault_date(created_at) or modified_at.strftime("%Y-%m-%d")
    date_modified = modified_at.strftime("%Y-%m-%d")

    parts = [
        "---\n",
        _format_yaml_list("nexus", nexus or []),
        f"type: {type_}\n",
        _format_yaml_list("tags", tags or []),
        f"date created: {date_created}\n",
        f"date modified: {date_modified}\n",
        "---\n",
    ]
    return "".join(parts)


def _format_yaml_list(key: str, values: list[str]) -> str:
    """Emit a YAML list property in canonical block-list form.

    Empty list → ``key:\\n`` per Schema §10 rule 4 (no `[]`, no `null`).
    Non-empty → multi-line ``- value`` form per §10 rule 3.
    """
    if not values:
        return f"{key}:\n"
    lines = [f"{key}:"]
    for v in values:
        lines.append(f"  - {v}")
    return "\n".join(lines) + "\n"


def _format_vault_date(value: str | None) -> str | None:
    """Normalize an arbitrary date-ish string to ``YYYY-MM-DD`` (Schema §10
    rule 9 — dashes, not slashes)."""
    if not value:
        return None
    # Try common ISO shapes.
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:19 if "T" in value or " " in value else 10], fmt).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    # Fallback: extract YYYY-MM-DD prefix if present.
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


# ---------------------------------------------------------------------------
# Master Matrix nexus matcher (Phase 5.7)
# ---------------------------------------------------------------------------


_DEFAULT_MASTER_MATRIX_PATH = (
    Path.home() / "Documents" / "vault" / "Engrams" / "Reference — Master Matrix.md"
)

# Match `project property name: <id>` and `passion property name: <id>`.
# Skip `parent project name:` (no "property" keyword — that's a back-reference).
_MATRIX_PROPERTY_RE = re.compile(
    r"^(?:project|passion)\s+property\s+name:\s*(\S+)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def _load_master_matrix(path: Path | str | None = None) -> list[str]:
    """Parse the Master Matrix file and return a deduped list of
    project/passion identifiers (canonical nexus values).

    Defensively returns [] if the file is missing or unreadable —
    callers fall through to empty nexus when no match.
    """
    target = Path(path) if path else _DEFAULT_MASTER_MATRIX_PATH
    try:
        content = target.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return []

    seen: set[str] = set()
    identifiers: list[str] = []
    for m in _MATRIX_PROPERTY_RE.finditer(content):
        ident = m.group(1).strip()
        if ident and ident not in seen:
            seen.add(ident)
            identifiers.append(ident)
    return identifiers


def _normalize_for_match(s: str) -> str:
    """Lowercase and replace underscores/hyphens with spaces.

    Lets `idea_refinery` (matrix identifier) match `idea refinery` or
    `Idea-Refinery` in a free-form topic string.
    """
    return re.sub(r"[_\-]+", " ", s.lower())


def _match_topic_to_nexus(topic: str | None, identifiers: list[str]) -> list[str]:
    """Return identifiers whose normalized form appears in the topic.

    Substring match with normalization (underscore/hyphen → space,
    case-folded). When multiple identifiers match, all are returned in
    the order they appear in the matrix file. Empty topic or no
    identifiers → empty list.
    """
    if not topic or not identifiers:
        return []
    haystack = _normalize_for_match(topic)
    matches: list[str] = []
    for ident in identifiers:
        needle = _normalize_for_match(ident)
        if not needle:
            continue
        if needle in haystack:
            matches.append(ident)
    return matches


# ---------------------------------------------------------------------------
# WP-6.2 — regeneration note
# ---------------------------------------------------------------------------

# The editing-caveat note appended after each SVG embed. Obsidian renders
# single-line italics cleanly; the note reminds the user that the JSON block
# above is source of truth and Ora must be re-opened to regenerate the SVG.
_REGENERATION_NOTE = (
    "*Source of truth is the JSON block above. "
    "If you edit the JSON in Obsidian, return to Ora to regenerate the "
    "sidecar SVG.*"
)


def _splice_visuals_with_sidecars(
    content: str,
    visuals: list[dict[str, Any]],
    sidecar_names_by_visual_id: dict[int, str],
) -> str:
    """Rewrite assistant ``content`` so each ora-visual fenced block is
    followed by an ``![[<sidecar>.svg]]`` embed line, then by a single-line
    italic regeneration-caveat note (WP-6.2).

    Only rewrites blocks whose id (by position in ``visuals``) is in
    ``sidecar_names_by_visual_id``. Unknown/invalid blocks pass through
    unchanged so the raw JSON is preserved as source of truth.
    """
    if not visuals:
        return content

    # Walk from end → start so earlier indexes aren't perturbed.
    out = content
    for idx in range(len(visuals) - 1, -1, -1):
        v = visuals[idx]
        sidecar_name = sidecar_names_by_visual_id.get(idx)
        if not sidecar_name:
            continue
        # Embed + regeneration note. One blank line between embed and note
        # so Obsidian's paragraph breaks render the italic on its own line;
        # one blank line after so the following prose stays visually distinct.
        embed = (
            f"\n\n![[{sidecar_name}]]"
            f"\n\n{_REGENERATION_NOTE}"
        )
        out = out[: v["end"]] + embed + out[v["end"]:]
    return out


def _render_messages_markdown(
    messages: list[dict[str, Any]],
    sidecars_per_message: list[dict[int, str]],
) -> str:
    """Turn a sequence of messages into the ``## Exchanges`` body."""
    parts: list[str] = ["## Exchanges\n"]
    turn_idx = 0
    for mi, msg in enumerate(messages):
        role = str(msg.get("role", "unknown")).lower()
        content = str(msg.get("content", "")).rstrip()
        ts = msg.get("timestamp") or msg.get("ts") or ""

        if role == "user":
            turn_idx += 1
            header = f"\n### Turn {turn_idx}"
            if ts:
                header += f" — {ts}"
            parts.append(header)
            parts.append("\n**User:**\n")
            parts.append(content + "\n")
        elif role == "assistant":
            parts.append("\n**Assistant:**\n")
            sidecar_map = sidecars_per_message[mi] if mi < len(sidecars_per_message) else {}
            if sidecar_map:
                visuals = _extract_ora_visuals(content)
                content = _splice_visuals_with_sidecars(content, visuals, sidecar_map)
            parts.append(content + "\n")
        else:
            # System / tool messages — keep the role label so round-trip
            # survives.
            parts.append(f"\n**{role.capitalize()}:**\n{content}\n")
    return "\n".join(parts).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Gitignore maintenance
# ---------------------------------------------------------------------------


def _ensure_sessions_dir(sessions_dir: Path) -> None:
    """Create the vault sessions subdir (if missing) and drop a .gitignore
    that excludes sidecar SVGs from version control.

    The gitignore contains the single pattern ``*.fig-*.svg``. Sidecars
    are disposable compiled output — the Markdown + source JSON is the
    authoritative record.
    """
    sessions_dir.mkdir(parents=True, exist_ok=True)
    gitignore = sessions_dir / ".gitignore"
    needed = f"# Ora vault-export sidecars — disposable compiled output (WP-6.1)\n{_SIDECAR_GITIGNORE_PATTERN}\n"
    if not gitignore.exists():
        gitignore.write_text(needed, encoding="utf-8")
        return
    # Append pattern if it's missing (preserve any pre-existing lines).
    existing = gitignore.read_text(encoding="utf-8")
    if _SIDECAR_GITIGNORE_PATTERN not in existing:
        if not existing.endswith("\n"):
            existing += "\n"
        existing += needed
        gitignore.write_text(existing, encoding="utf-8")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def export_session_to_vault(
    conversation_id: str,
    session_title: str | None = None,
    vault_root: Path | None = None,
    sessions_subdir: str = "Sessions",
    sessions_root: Path | None = None,
    raw_conversations_dir: Path | None = None,
    node_cli: Path | None = None,
    render_timeout_s: float = 60.0,
    master_matrix_path: Path | None = None,
    _validator: Any = None,
) -> ExportResult:
    """Export the conversation identified by ``conversation_id`` to the vault.

    Parameters mirror the WP-6.1 spec; ``vault_root``, ``sessions_root``,
    ``raw_conversations_dir`` and ``node_cli`` default to the production
    paths but are dependency-injectable for tests.

    ``_validator`` is an optional callable ``envelope -> ValidationResult``
    (``visual_validator.validate_envelope`` is the default). Tests pass a
    stub to bypass the jsonschema dependency.
    """
    vault_root = Path(vault_root) if vault_root else Path.home() / "Documents" / "vault"
    sessions_root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    raw_conversations_dir = Path(raw_conversations_dir) if raw_conversations_dir else _DEFAULT_RAW_CONVERSATIONS
    node_cli = Path(node_cli) if node_cli else _DEFAULT_RENDER_CLI

    warnings: list[str] = []
    invalid_envelopes: list[dict[str, Any]] = []
    sidecar_paths: list[Path] = []

    # ── Resolve the validator ───────────────────────────────────────────────
    if _validator is None:
        try:
            from visual_validator import validate_envelope as _validator  # type: ignore
        except Exception as e:  # pragma: no cover — import-path drift only
            warnings.append(f"visual_validator import failed: {e}; all envelopes treated as invalid")
            def _validator(env):  # noqa: E306 — local stub
                class _R:
                    valid = False
                    errors = [type("E", (), {"code": "E_IMPORT", "message": "validator unavailable"})()]
                    warnings: list = []
                return _R()

    # ── Load conversation ───────────────────────────────────────────────────
    convo = _load_conversation(conversation_id, sessions_root, raw_conversations_dir)
    messages = convo.get("messages") or []

    # Derive the session title + filename stem.
    first_user = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
    resolved_title = session_title or convo.get("session_title") or (first_user[:80].strip() if first_user else "") or f"Ora session {conversation_id[:8]}"
    stem = _derive_session_name(session_title or convo.get("session_title"), conversation_id, first_user)

    # ── Prepare output directory ────────────────────────────────────────────
    sessions_dir = vault_root / sessions_subdir
    _ensure_sessions_dir(sessions_dir)

    # ── First pass: scan every assistant message for ora-visual blocks.
    # This walks in order so figure numbering is stable.
    sidecars_per_message: list[dict[int, str]] = [dict() for _ in messages]
    fig_counter = 0
    envelope_count = 0

    for mi, msg in enumerate(messages):
        if str(msg.get("role", "")).lower() != "assistant":
            continue
        content = str(msg.get("content", ""))
        visuals = _extract_ora_visuals(content)
        for vi, v in enumerate(visuals):
            envelope_count += 1
            if v["envelope"] is None:
                warnings.append(
                    f"Message {mi} visual block {vi}: JSON parse failed ({v['parse_error']}) — skipping sidecar"
                )
                invalid_envelopes.append({
                    "message_index": mi,
                    "block_index": vi,
                    "reason": "json_parse_failed",
                    "detail": v["parse_error"],
                })
                continue

            # Validate.
            try:
                vr = _validator(v["envelope"])
            except Exception as e:  # validator itself blew up
                warnings.append(
                    f"Message {mi} visual block {vi}: validator exception ({e}) — skipping sidecar"
                )
                invalid_envelopes.append({
                    "message_index": mi,
                    "block_index": vi,
                    "reason": "validator_exception",
                    "detail": str(e),
                })
                continue

            if not getattr(vr, "valid", False):
                err_summary = "; ".join(
                    f"{getattr(e, 'code', '')}:{(getattr(e, 'message', '') or '')[:80]}"
                    for e in (getattr(vr, "errors", []) or [])
                )
                warnings.append(
                    f"Message {mi} visual block {vi}: invalid envelope — {err_summary or 'no errors reported'}; skipping sidecar"
                )
                invalid_envelopes.append({
                    "message_index": mi,
                    "block_index": vi,
                    "reason": "validation_failed",
                    "detail": err_summary,
                })
                continue

            # Render SVG.
            fig_counter += 1
            sidecar_name = f"{stem}.fig-{fig_counter}.svg"
            sidecar_path = sessions_dir / sidecar_name

            svg, err = _render_envelope_to_svg(
                v["envelope"], node_cli=node_cli, timeout_s=render_timeout_s,
            )
            if err:
                warnings.append(
                    f"Message {mi} visual block {vi}: render failed — {err}; sidecar not written"
                )
                invalid_envelopes.append({
                    "message_index": mi,
                    "block_index": vi,
                    "reason": "render_failed",
                    "detail": err,
                })
                # Roll the counter back so figure numbering stays dense.
                fig_counter -= 1
                continue

            try:
                sidecar_path.write_text(svg, encoding="utf-8")
            except OSError as e:
                warnings.append(f"Message {mi} visual block {vi}: sidecar write failed — {e}")
                invalid_envelopes.append({
                    "message_index": mi,
                    "block_index": vi,
                    "reason": "sidecar_write_failed",
                    "detail": str(e),
                })
                fig_counter -= 1
                continue

            sidecar_paths.append(sidecar_path)
            sidecars_per_message[mi][vi] = sidecar_name

    # ── Second pass: build the markdown document. ───────────────────────────
    # Derive nexus from the topic (session title or first user message)
    # via Master Matrix substring match. Empty list when nothing matches.
    matrix_identifiers = _load_master_matrix(master_matrix_path)
    topic_for_nexus = session_title or convo.get("session_title") or first_user or ""
    nexus = _match_topic_to_nexus(topic_for_nexus, matrix_identifiers)

    frontmatter = _build_canonical_frontmatter(
        nexus=nexus,
        type_="chat",
        tags=[],  # controlled-vocabulary tags can be set by the caller / pipeline
        created_at=convo.get("created_at"),
    )
    now_iso = datetime.now().isoformat(timespec="seconds")
    heading = f"# {resolved_title}\n"
    meta_block = (
        f"\n**Conversation ID:** `{conversation_id}`\n"
        f"**Exported:** {now_iso}\n"
        f"**Source:** {convo.get('_source_path') or 'structured conversation.json'}\n"
    )
    exchanges = _render_messages_markdown(messages, sidecars_per_message)

    body = frontmatter + heading + meta_block + "\n" + exchanges + "\n"

    # ── Write markdown ──────────────────────────────────────────────────────
    markdown_path = sessions_dir / f"{stem}.md"
    markdown_path.write_text(body, encoding="utf-8")

    return ExportResult(
        markdown_path=markdown_path,
        sidecar_paths=sidecar_paths,
        warnings=warnings,
        envelope_count=envelope_count,
        invalid_envelopes=invalid_envelopes,
    )


__all__ = [
    "ExportResult",
    "export_session_to_vault",
    "_slugify",
    "_derive_session_name",
    "_extract_ora_visuals",
    "_parse_raw_session_log",
    "_render_envelope_to_svg",
    "_build_canonical_frontmatter",
    "_format_yaml_list",
    "_format_vault_date",
    "_load_master_matrix",
    "_match_topic_to_nexus",
    "_normalize_for_match",
    "_ensure_sessions_dir",
]
