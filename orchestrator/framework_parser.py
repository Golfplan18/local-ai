"""Framework parser — reads framework markdown files and extracts structured
milestone, layer, and M0 routing data.

Designed for the milestone executor (milestone_executor.py). Implements the
Section 2.3 Milestones Delivered schema declared by Process Formalization
Framework v2.1: inline-properties, mode-namespacing, M0 routing, and
Conditional layers.

The parser is deliberately strict — it returns clear errors when a framework's
Milestones Delivered section doesn't conform to the schema, rather than
silently producing garbage.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

FRAMEWORKS_DIR = os.path.expanduser("~/ora/frameworks/book")


# ---------- Data structures ----------

@dataclass
class Layer:
    """One ## LAYER N: ... block from a framework."""
    raw_label: str  # e.g., "1", "5.1", "VI"
    number: int     # parsed integer if possible, else 0
    title: str
    body: str       # full markdown body until next ## boundary


@dataclass
class M0Routing:
    """Routing/triage block declared at the top of MILESTONES DELIVERED."""
    function: str
    layers_covered: list[str]
    output: str


@dataclass
class Milestone:
    """A single milestone with all properties bound inline."""
    id: str                         # e.g., "M1", "M2"
    name: str                       # e.g., "Approved Research Plan"
    mode: Optional[str]             # None or "all" for single-mode frameworks
    endpoint_produced: str
    verification_criterion: str
    layers_covered: list[str]       # raw labels referencing Layer.raw_label
    conditional_layers: Optional[str]  # raw text including condition; None if absent
    required_prior: list[str]       # M-references; e.g., ["M1"] or ["I-Create.M4"]
    gear: int
    output_format: str
    drift_check_question: str


@dataclass
class Framework:
    """Structured representation of a parsed framework file."""
    name: str
    file_path: str
    raw_markdown: str
    is_multi_mode: bool
    modes: list[str]                              # empty for single-mode
    m0_routing: Optional[M0Routing]
    milestones_by_mode: dict[str, list[Milestone]]  # mode → milestones; "all" for single-mode
    layers: dict[str, Layer]                      # raw_label → Layer

    def all_milestones(self) -> list[Milestone]:
        """Flat list of all milestones across modes, in declared order."""
        out = []
        for mode_milestones in self.milestones_by_mode.values():
            out.extend(mode_milestones)
        return out


class FrameworkParseError(Exception):
    """Raised when a framework's Milestones Delivered section is malformed."""
    pass


# ---------- Public API ----------

def parse_framework_file(path: str) -> Framework:
    """Parse a framework markdown file at the given absolute path."""
    if not os.path.isabs(path):
        path = os.path.join(FRAMEWORKS_DIR, path)
    with open(path) as f:
        text = f.read()
    return parse_framework_text(text, path=path)


def parse_framework_text(text: str, path: str = "<inline>") -> Framework:
    """Parse a framework from raw markdown text. Used for testing."""
    name = os.path.basename(path).replace(".md", "") if path else "<unknown>"

    milestones_section = _extract_milestones_section(text)
    if not milestones_section:
        raise FrameworkParseError(
            f"{name}: no '## MILESTONES DELIVERED' section found"
        )

    mode_subsections = re.findall(
        r"^### Milestones for Mode\s+(\S+)", milestones_section, re.M
    )
    is_multi_mode = len(mode_subsections) > 0

    m0_routing = _parse_m0(milestones_section)

    if is_multi_mode:
        milestones_by_mode = {}
        for mode in mode_subsections:
            mode_block = _extract_mode_block(milestones_section, mode)
            milestones_by_mode[mode] = _parse_milestones(
                mode_block, header_level=4, mode_default=mode
            )
    else:
        milestones_by_mode = {
            "all": _parse_milestones(
                milestones_section, header_level=3, mode_default=None
            )
        }

    if not any(milestones_by_mode.values()):
        raise FrameworkParseError(
            f"{name}: MILESTONES DELIVERED section contains no milestones"
        )

    layers = _parse_layers(text)

    return Framework(
        name=name,
        file_path=path,
        raw_markdown=text,
        is_multi_mode=is_multi_mode,
        modes=mode_subsections,
        m0_routing=m0_routing,
        milestones_by_mode=milestones_by_mode,
        layers=layers,
    )


# ---------- Section extraction ----------

def _extract_milestones_section(text: str) -> str:
    """Extract the top-level ## MILESTONES DELIVERED section.

    Stops at the next H2 that is NOT itself MILESTONES DELIVERED (which
    excludes example blocks inside subsections like §2.3 of PFF).
    """
    m = re.search(r"^## MILESTONES DELIVERED\s*$", text, re.M)
    if not m:
        return ""
    start = m.end()
    # Find next ## boundary that isn't inside a code fence
    next_h2 = _next_h2_boundary(text, start)
    return text[start:next_h2] if next_h2 else text[start:]


def _next_h2_boundary(text: str, from_pos: int) -> Optional[int]:
    """Return position of next ## header after from_pos, ignoring fenced
    code blocks. Returns None if no further ## header exists."""
    # Track code-fence state
    pos = from_pos
    in_fence = False
    for line_match in re.finditer(r"^(```|## )", text[from_pos:], re.M):
        absolute = from_pos + line_match.start()
        token = line_match.group(1)
        if token == "```":
            in_fence = not in_fence
            continue
        # token == "## "
        if not in_fence:
            return absolute
    return None


def _extract_mode_block(section: str, mode_name: str) -> str:
    """Extract a ### Milestones for Mode <name> subsection."""
    header_pattern = re.compile(
        rf"^### Milestones for Mode\s+{re.escape(mode_name)}\s*$", re.M
    )
    m = header_pattern.search(section)
    if not m:
        return ""
    start = m.end()
    next_subsection = re.search(r"^### Milestones for Mode ", section[start:], re.M)
    if next_subsection:
        return section[start:start + next_subsection.start()]
    return section[start:]


# ---------- Block parsing ----------

def _parse_m0(section: str) -> Optional[M0Routing]:
    """Find a ### M0: Routing block and parse it."""
    m = re.search(r"^### M0: Routing\s*$", section, re.M)
    if not m:
        return None
    start = m.end()
    next_h = re.search(r"^(### |#### )", section[start:], re.M)
    end = start + next_h.start() if next_h else len(section)
    body = section[start:end]
    properties = _parse_properties(body)
    return M0Routing(
        function=properties.get("function", ""),
        layers_covered=_split_csv(properties.get("layers covered", "")),
        output=properties.get("output", ""),
    )


def _parse_milestones(
    section: str, header_level: int, mode_default: Optional[str]
) -> list[Milestone]:
    """Parse milestone blocks. header_level=3 for single-mode, 4 for multi-mode."""
    header_prefix = "#" * header_level
    pattern = rf"^{header_prefix} Milestone (\d+):\s*(.+?)$"

    milestones = []
    matches = list(re.finditer(pattern, section, re.M))
    for i, m in enumerate(matches):
        milestone_num = m.group(1)
        milestone_name = m.group(2).strip()

        start = m.end()
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(section)
        body = section[start:end]

        properties = _parse_properties(body)
        mode_value = properties.get("mode") or mode_default

        ms = Milestone(
            id=f"M{milestone_num}",
            name=milestone_name,
            mode=mode_value,
            endpoint_produced=properties.get("endpoint produced", ""),
            verification_criterion=properties.get("verification criterion", ""),
            layers_covered=_split_csv(properties.get("layers covered", "")),
            conditional_layers=properties.get("conditional layers"),
            required_prior=_parse_required_prior(
                properties.get("required prior milestones", "None")
            ),
            gear=_parse_gear(properties.get("gear", "4")),
            output_format=properties.get("output format", ""),
            drift_check_question=properties.get("drift check question", ""),
        )
        milestones.append(ms)
    return milestones


def _parse_properties(body: str) -> dict[str, str]:
    """Extract `- **PropertyName:** value` lines into a lowercase-keyed dict.

    Values can span multiple lines; they end at the next bullet, blank line
    pair, or end of body.
    """
    properties = {}
    pattern = re.compile(
        r"^- \*\*([^:*]+):\*\*\s*(.*?)(?=\n- \*\*|\n\n|\Z)",
        re.M | re.DOTALL,
    )
    for m in pattern.finditer(body):
        key = m.group(1).strip().lower()
        value = m.group(2).strip()
        properties[key] = value
    return properties


def _split_csv(text: str) -> list[str]:
    """Split a comma-separated string. Returns [] for empty or 'None'."""
    if not text or text.strip().lower() == "none":
        return []
    return [s.strip() for s in text.split(",") if s.strip()]


def _parse_required_prior(text: str) -> list[str]:
    """Parse 'Required prior milestones' value. 'None' → []."""
    if not text or text.strip().lower() == "none":
        return []
    return _split_csv(text)


def _parse_gear(text: str) -> int:
    """Parse gear number, defaulting to 4 on parse failure."""
    if not text:
        return 4
    m = re.search(r"\d+", text)
    return int(m.group()) if m else 4


# ---------- Layer parsing ----------

def _parse_layers(text: str) -> dict[str, Layer]:
    """Parse all ## LAYER N: ... blocks (case-insensitive 'LAYER')."""
    pattern = re.compile(r"^##\s+(?:LAYER|Layer)\s+(\S+):\s*(.+?)$", re.M)
    matches = list(pattern.finditer(text))
    layers: dict[str, Layer] = {}
    for i, m in enumerate(matches):
        raw_label = m.group(1)
        title = m.group(2).strip()
        start = m.end()
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            next_h2 = re.search(r"^## ", text[start:], re.M)
            end = start + next_h2.start() if next_h2 else len(text)
        body = text[start:end].strip()

        try:
            number = int(raw_label.rstrip("."))
        except ValueError:
            number = 0

        layers[raw_label] = Layer(
            raw_label=raw_label,
            number=number,
            title=title,
            body=body,
        )
    return layers


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "deep-research-protocol.md"
    fw = parse_framework_file(target)
    print(f"Framework: {fw.name}")
    print(f"  multi-mode: {fw.is_multi_mode}")
    print(f"  modes: {fw.modes}")
    print(f"  M0 routing: {fw.m0_routing.function if fw.m0_routing else 'none'}")
    print(f"  layers: {sorted(fw.layers.keys())}")
    print()
    print("Milestones:")
    for mode, ms_list in fw.milestones_by_mode.items():
        print(f"  Mode '{mode}':")
        for ms in ms_list:
            print(f"    {ms.id}: {ms.name}")
            print(f"      layers={ms.layers_covered} prior={ms.required_prior} gear={ms.gear}")
            print(f"      drift_check: {ms.drift_check_question[:80]}{'...' if len(ms.drift_check_question) > 80 else ''}")
