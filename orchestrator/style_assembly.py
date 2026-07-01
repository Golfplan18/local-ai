"""Output Style assembly.

Composes a resolved Output Style profile into the text injected into the model:
  - the compact DEMEANOR block (gears 1-2, fast judgments / short replies)
  - the full STYLE block (gears 3-4, at the produce/format steps)

Standalone and side-effect-free: it reads the style-*.md files from
frameworks/book and returns strings. Nothing in the pipeline imports it yet —
this is the unit-testable core (build step 2). The injection wiring (gears) and
the resolution chain (one-off / project / default) sit on top of this later.

Precedence baked into every block:
    values floor > completeness floor > craft floor > substance/findings > style.
The values floor is INSTRUCTED (a prompt line), not a mechanical gate.
"""

import os
import re

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMEWORKS_DIR = os.path.join(WORKSPACE, "frameworks", "book")

# Axis order = the order the lines appear in an assembled block.
AXIS_ORDER = ["warmth", "force", "energy", "outlook",
              "playfulness", "directness", "agreeableness"]

# Rungs low->high per axis, for situational-delta math (one-rung swaps).
RUNGS = {
    "warmth": ["cool", "even", "warm"],
    "force": ["gentle", "measured", "forceful"],
    "energy": ["calm", "steady", "lively"],
    "outlook": ["skeptical", "balanced", "affirming"],
    "playfulness": ["straight", "dry", "playful"],
    "directness": ["diplomatic", "plain", "blunt"],
    "agreeableness": ["accommodating", "candid", "challenging"],
}

VALUES_FLOOR_LINE = ("Never flatter to please, never manufacture disagreement, "
                     "never mislead — these hold regardless of the tone above.")
COMPLETENESS_LINE = "Never drop information the reader needs to satisfy brevity."


def _read(name, base=None):
    base = base or FRAMEWORKS_DIR
    with open(os.path.join(base, name), encoding="utf-8") as fh:
        return fh.read()


def load_registry(base=None):
    """{style_id: entry_dict} from style-registry.md (one `## id` + yaml block each)."""
    if yaml is None:
        raise RuntimeError("PyYAML is required to parse the style registry")
    text = _read("style-registry.md", base)
    entries = {}
    for m in re.finditer(r"^##[ \t]+([^\n]+)\n.*?```yaml\n(.*?)\n```",
                         text, re.S | re.M):
        sid = m.group(1).strip()
        entries[sid] = yaml.safe_load(m.group(2)) or {}
    return entries


def load_demeanor_axes(base=None):
    """({axis: {rung: text}}, {device: text}) from style-demeanor-axes.md."""
    text = _read("style-demeanor-axes.md", base)
    axes, devices = {}, {}
    for sec in re.split(r"^##[ \t]+", text, flags=re.M)[1:]:
        head, _, body = sec.partition("\n")
        name = head.split("—")[0].split("(")[0].strip().lower()
        bullets = dict(re.findall(r"^-[ \t]+(\w+):[ \t]*(.+)$", body, re.M))
        if name.startswith("device"):
            devices.update(bullets)
        else:
            axes[name] = bullets
    return axes, devices


def load_arrangement_schemas(base=None):
    """{schema_id: prose} from style-arrangement-schemas.md."""
    text = _read("style-arrangement-schemas.md", base)
    schemas = {}
    for sec in re.split(r"^##[ \t]+", text, flags=re.M)[1:]:
        head, _, body = sec.partition("\n")
        schemas[head.split("(")[0].strip()] = body.strip()
    return schemas


def load_craft_floor(base=None):
    """The craft-floor bullet lines from style-craft-floor.md."""
    text = _read("style-craft-floor.md", base)
    return [m.group(1).strip() for m in re.finditer(r"^-[ \t]+(.+)$", text, re.M)]


def resolve_demeanor(entry, deltas=None):
    """Profile's demeanor picks with situational deltas applied (one-rung swaps, clamped)."""
    picks = dict(entry.get("demeanor", {}))
    for axis, step in (deltas or {}).items():
        order = RUNGS.get(axis)
        if not order:
            continue
        cur = picks.get(axis, order[len(order) // 2])
        idx = order.index(cur) if cur in order else len(order) // 2
        picks[axis] = order[max(0, min(len(order) - 1, idx + step))]
    return picks


# ── Card labels (for the Output Styles picker) ───────────────────────────────
# Short headline forms of the four card slots. Pure functions of an entry — the
# settings endpoint calls these so the cards stay in lockstep with the registry.

ARRANGEMENT_LABELS = {
    "answer-first": "answer-first",
    "motivation-first": "motivation-first",
    "problem-rationale": "problem→why",
    "goal-steps": "goal→steps",
    "inverted-pyramid": "inverted pyr.",
    "bottom-line-up-front": "bottom-line",
    "problem-recommendation": "problem→rec",
    "thesis-evidence": "thesis→evid.",
    "defined-terms": "defined terms",
    "benefit-led": "benefit-led",
    "reference-lookup": "lookup",
    "scene-reflection": "scene→reflect",
}

ELABORATION_LABELS = {1: "minimal", 2: "essentials", 3: "balanced",
                      4: "examples-rich", 5: "exhaustive"}


def arrangement_short(arr_id):
    """Card label for an arrangement schema id."""
    return ARRANGEMENT_LABELS.get(arr_id, (arr_id or "").replace("-", " "))


def elaboration_label(n):
    """Card label for the 1–5 elaboration dial."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 3
    return ELABORATION_LABELS.get(max(1, min(5, n)), "balanced")


def demeanor_summary(entry, max_terms=2):
    """A one-glance label for the demeanor slot: the rung words of the one or two
    axes furthest from neutral (e.g. ``warm · affirming``). ``neutral`` when every
    axis sits on its middle rung. The card's "more" view shows all seven."""
    picks = (entry or {}).get("demeanor") or {}
    marked = []
    for axis in AXIS_ORDER:
        order = RUNGS.get(axis, [])
        rung = picks.get(axis)
        if not order or rung not in order:
            continue
        dist = abs(order.index(rung) - len(order) // 2)
        if dist > 0:
            marked.append((dist, AXIS_ORDER.index(axis), rung))
    marked.sort(key=lambda t: (-t[0], t[1]))
    terms = [r for _, _, r in marked[:max_terms]]
    return " · ".join(terms) if terms else "neutral"


def _demeanor_lines(entry, axes, devices, deltas=None, prefix=""):
    picks = resolve_demeanor(entry, deltas)
    lines = []
    for axis in AXIS_ORDER:
        rung = picks.get(axis)
        if rung and rung in axes.get(axis, {}):
            lines.append(prefix + axes[axis][rung])
    for dev, on in (entry.get("devices") or {}).items():
        if on and dev in devices:
            lines.append(prefix + devices[dev])
    return lines


def compose_demeanor_block(entry, axes, devices, deltas=None):
    """Compact block for gears 1-2: disposition + the two floors. No arrangement."""
    out = ["## DEMEANOR (this turn)",
           "PRECEDENCE: values floor > completeness > craft > substance > style.",
           ""]
    out += _demeanor_lines(entry, axes, devices, deltas)
    out += ["", VALUES_FLOOR_LINE, COMPLETENESS_LINE]
    return "\n".join(out)


def compose_style_block(entry, axes, devices, schemas, craft, deltas=None):
    """Full block for gears 3-4: demeanor + craft + arrangement + diction + completeness."""
    arr = entry.get("arrangement")
    out = ["## STYLE — SECONDARY TO SUBSTANCE",
           "PRECEDENCE: values floor > completeness > craft > findings > style.",
           ("Style shapes how the piece reads. It never overrides a finding, "
            "a correction, or a fact."),
           "", "DEMEANOR:"]
    out += _demeanor_lines(entry, axes, devices, deltas, prefix="- ")
    out += ["", "CRAFT FLOOR (outranks style):"]
    out += ["- " + b for b in craft]
    out += ["", "ARRANGEMENT (%s): %s" % (arr, schemas.get(arr, "(schema not found)"))]
    diction = []
    gl = entry.get("glossary") or {}
    if gl.get("forbidden"):
        diction.append("Avoid: " + ", ".join(str(x) for x in gl["forbidden"]) + ".")
    if gl.get("required"):
        diction.append("Use: " + ", ".join(str(x) for x in gl["required"]) + ".")
    if gl.get("canonical"):
        diction.append("Canonical terms: "
                        + ", ".join("%s = %s" % (k, v) for k, v in gl["canonical"].items()) + ".")
    if diction:
        out += ["", "DICTION: " + " ".join(diction)]
    out += ["",
            "COMPLETENESS: floored — never traded for length. Elaboration %s of 5."
            % entry.get("elaboration", 3),
            COMPLETENESS_LINE]
    return "\n".join(out)


def compose(style_id, register="written", gear=3, deltas=None, base=None,
            custom_entries=None):
    """Top-level: return the injected block for a style at a given gear.

    gear <= 2 -> compact demeanor block; gear >= 3 -> full style block.
    `register` is where situational deltas will be derived once the resolution
    chain is wired; for now the caller passes `deltas` explicitly.
    `custom_entries` ({id: entry}) are user-authored profiles merged over the
    built-ins, so an active custom profile injects exactly like a genre.
    """
    registry = load_registry(base)
    if custom_entries:
        registry = {**registry, **custom_entries}
    if style_id not in registry:
        raise KeyError("unknown style_id: %s" % style_id)
    entry = registry[style_id]
    axes, devices = load_demeanor_axes(base)
    if gear <= 2:
        # Gears 1-2 (quick conversational replies) inject demeanor only, so the
        # conversational register is nothing more than an optional alternate
        # demeanor. Overlay it on the written demeanor per-axis; unset axes
        # inherit written. Gears 3-4 (produced/written output) ignore it.
        conv = entry.get("conversational") or {}
        if conv.get("demeanor") or conv.get("devices"):
            entry = {**entry,
                     "demeanor": {**(entry.get("demeanor") or {}),
                                  **(conv.get("demeanor") or {})},
                     "devices": {**(entry.get("devices") or {}),
                                 **(conv.get("devices") or {})}}
        return compose_demeanor_block(entry, axes, devices, deltas)
    schemas = load_arrangement_schemas(base)
    craft = load_craft_floor(base)
    return compose_style_block(entry, axes, devices, schemas, craft, deltas)


if __name__ == "__main__":  # quick manual peek
    print(compose("explainer", gear=3))
