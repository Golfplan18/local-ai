"""Custom Output Style profiles — user-authored, persisted store.

Built-in genre profiles live in ``frameworks/book/style-registry.md`` (read-only,
parsed by :mod:`style_assembly`). When a user forks a genre on the Output Styles
tab and edits a line, the result is a *custom profile*: the same shape as a
registry entry plus ``id`` / ``custom`` / ``forked_from`` bookkeeping, saved here
in ``~/ora/data/custom-styles.json``.

This mirrors how model custom configurations persist beside the read-only model
registry (``~/ora/data/active-configuration.json``): the framework files stay
canonical, user edits live in the data dir. The path is derived from this
module's location, so a worktree's tests write the worktree's ``data/`` and never
touch the live store.

Side-effect-free to import (no file I/O until a function is called). Every reader
degrades to an empty store on a missing/corrupt file — a bad custom profile must
never break the picker or the pipeline.
"""

import json
import os
import re

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_PATH = os.path.join(WORKSPACE, "data", "custom-styles.json")

# A blank profile for "+ new profile" when the user forks from nothing. Same
# shape as a registry entry; neutral demeanor across all seven axes.
DEFAULT_PROFILE = {
    "display_name": "New profile",
    "description": "",
    "values_source": "default-mindspec",
    "arrangement": "answer-first",
    "register_default": "written",
    "demeanor": {
        "warmth": "even", "force": "measured", "energy": "steady",
        "outlook": "balanced", "playfulness": "straight",
        "directness": "plain", "agreeableness": "candid",
    },
    "devices": {},
    "elaboration": 3,
    "format": {},
    "glossary": {},
}

# Fields a PATCH may set on a custom profile. Anything else is ignored — the
# endpoint never lets an arbitrary key into a stored entry.
PATCHABLE = {
    "display_name", "description", "arrangement", "register_default",
    "elaboration", "demeanor", "devices", "glossary", "values_source", "format",
}


def _builtin_ids():
    """Built-in style ids, so a custom id never shadows a genre. Best-effort."""
    try:
        try:
            from style_assembly import load_registry
        except ImportError:
            from orchestrator.style_assembly import load_registry
        return set((load_registry() or {}).keys())
    except Exception:
        return set()


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s or "profile"


def load_custom_profiles():
    """``{id: entry}`` of saved custom profiles. ``{}`` if none / unreadable."""
    try:
        with open(STORE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, ValueError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for sid, entry in data.items():
        if isinstance(entry, dict):
            entry = dict(entry)
            entry["id"] = sid
            entry["custom"] = True
            out[sid] = entry
    return out


def _save_all(profiles):
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    tmp = STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(profiles, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, STORE_PATH)


def get_custom_profile(sid):
    return load_custom_profiles().get(sid)


def _unique_id(desired, taken):
    """A store id not already used by a built-in or another custom profile."""
    base = _slug(desired)
    if base not in taken:
        return base
    n = 2
    while "%s-%d" % (base, n) in taken:
        n += 1
    return "%s-%d" % (base, n)


def create_custom_profile(base_entry=None, display_name=None, forked_from=None):
    """Save a new custom profile copied from ``base_entry`` (a registry entry or
    ``DEFAULT_PROFILE``). Returns the stored entry (with its assigned ``id``)."""
    entry = dict(DEFAULT_PROFILE)
    entry.update({k: v for k, v in (base_entry or {}).items()
                  if k in DEFAULT_PROFILE or k in PATCHABLE})
    # Deep-copy the nested dicts so later edits don't mutate the source preset.
    entry["demeanor"] = dict(entry.get("demeanor") or {})
    entry["devices"] = dict(entry.get("devices") or {})
    entry["glossary"] = dict(entry.get("glossary") or {})
    entry["format"] = dict(entry.get("format") or {})

    if display_name:
        entry["display_name"] = display_name
    elif forked_from and (base_entry or {}).get("display_name"):
        entry["display_name"] = base_entry["display_name"] + " (custom)"

    profiles = load_custom_profiles()
    taken = set(profiles.keys()) | _builtin_ids()
    sid = _unique_id(entry["display_name"], taken)

    if forked_from:
        entry["forked_from"] = forked_from
    entry.pop("id", None)
    entry.pop("custom", None)
    profiles[sid] = entry
    _save_all(profiles)
    stored = dict(entry)
    stored["id"] = sid
    stored["custom"] = True
    return stored


def update_custom_profile(sid, patch):
    """Apply ``patch`` (only PATCHABLE keys) to a stored profile. Nested dicts
    (demeanor / devices / glossary / format) merge key-by-key so a single axis or
    one forbidden term can be set without resending the whole block. Returns the
    updated entry, or ``None`` if ``sid`` is unknown."""
    profiles = load_custom_profiles()
    entry = profiles.get(sid)
    if entry is None:
        return None
    entry = {k: v for k, v in entry.items() if k not in ("id", "custom")}
    for key, val in (patch or {}).items():
        if key not in PATCHABLE:
            continue
        if key in ("demeanor", "devices", "glossary", "format") and isinstance(val, dict):
            merged = dict(entry.get(key) or {})
            merged.update(val)
            entry[key] = merged
        else:
            entry[key] = val
    profiles[sid] = entry
    _save_all(profiles)
    out = dict(entry)
    out["id"] = sid
    out["custom"] = True
    return out


def delete_custom_profile(sid):
    """Remove a custom profile. Returns ``True`` if it existed."""
    profiles = load_custom_profiles()
    if sid not in profiles:
        return False
    del profiles[sid]
    _save_all(profiles)
    return True
