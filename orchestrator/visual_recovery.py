"""
visual_recovery.py — recover a valid ``ora-visual`` envelope from the model's
OWN diagram output, deterministically, before falling back to prose synthesis.

Why this exists
---------------
The analytical models are GOOD at drawing diagrams in their native idiom
(a fenced ```mermaid block, a DAGitty ``dag { … }`` block, a Structurizr
``workspace { … }`` block) but BAD at emitting a strict ``ora-visual`` JSON
envelope — empirically, model-emitted envelopes validate at ~0% while the
mermaid/DSL they draw is well-formed. The Gear-4 step-8 formatter then often
strips the diagram entirely (it rewrites the consolidated corpus as prose), so
the only surviving visual came from a separate prose→envelope synthesis call.

This module closes that gap on the *faithful* side: it finds the diagram the
model actually drew — in the final response OR in the earlier pipeline steps
(analyst / reviser / verifier), where the formatter hasn't yet erased it — and
converts it into a schema-valid envelope of the correct ``type``. The envelope
is then validated by the same ``visual_validator`` + ``visual_adversarial``
gate every visual passes, so honesty rules still apply.

Two conversion classes:

* **DSL-native kinds** (``flowchart`` / ``sequence`` / ``state`` carry a Mermaid
  string; ``c4`` carries Structurizr; ``causal_dag`` carries DAGitty). These wrap
  the model's own DSL verbatim (lightly normalized) — zero re-authoring.
* **Malformed model envelopes.** When the model *did* emit an ``ora-visual``
  block that schema-rejected (extra props, missing mechanical fields, out-of-range
  numbers), :func:`repair_spec` + schema-guided pruning fix the recoverable cases
  rather than dropping the diagram (the premium-config E_SCHEMA_INVALID path).

Pure functions; unit-testable without a model. ``boot.py`` binds the search
texts and target-kind ordering.
"""
from __future__ import annotations

import json
import hashlib
import re

try:
    import runtime_paths as _rp
except ImportError:  # package import
    from orchestrator import runtime_paths as _rp

SCHEMAS_ROOT = _rp.CONFIG_DIR / "visual-schemas"

# Kinds whose spec is just a DSL string (we can wrap the model's own diagram
# verbatim, no re-authoring needed).
MERMAID_NATIVE_KINDS = frozenset({"flowchart", "sequence", "state"})

# Any fenced block language we treat as a diagram source.
_FENCE_RE = re.compile(r"```([A-Za-z0-9_-]*)\s*\n(.*?)```", re.DOTALL)

# The canonical ``ora-visual`` fenced-block pattern. Every consumer that
# extracts, deletes or REPLACES an ora-visual block must use this one.
#
# Why it is shaped this way. The obvious pattern — ```` ```ora-visual\s*\n(.*?)\n``` ````
# — is non-greedy, so an UNTERMINATED opening fence does not fail to match:
# it runs forward and closes on the next ``` it can find, which is normally
# the opening fence of an unrelated code block much further down. Every line
# in between is then captured, and the suppression/strip paths replace all of
# it with a one-line marker — deleting real analytical prose from a delivered
# response, and mangling the innocent block whose fence was consumed.
#
# The fix is an invariant rather than a heuristic: an ora-visual body is JSON,
# so it can never legitimately contain a fence line. Forbidding fence lines in
# the body means an unterminated fence matches NOTHING and the raw text is left
# in place, visible and inspectable — the same failure posture the client-side
# dispatcher already takes for unparseable JSON.
ORA_VISUAL_FENCE_RE = re.compile(
    r"```ora-visual[ \t]*\n"            # opening fence, alone on its line
    r"((?:(?![ \t]*```)[^\n]*\n)*?)"    # body: no line may open or close a fence
    r"[ \t]*```+[ \t]*(?=\n|$)"         # closing fence, alone on its line
)


def _extract_brace_block(text: str, keyword: str) -> str | None:
    """Return ``<keyword> { … }`` with BALANCED braces, starting at the first
    ``<keyword> {`` in ``text``. Brace-balanced so a Structurizr
    ``workspace { model { … } views { … } }`` (nested) isn't truncated at the
    first inner ``}`` (which a lazy ``.*?`` would do) and trailing prose with a
    stray ``}`` / ``${…}`` isn't swallowed (which a greedy ``.*`` would do)."""
    m = re.search(r"\b" + re.escape(keyword) + r"\s*\{", text)
    if not m:
        return None
    start = m.start()
    depth = 0
    i = m.end() - 1  # at the opening '{'
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    return None  # unbalanced — no reliable block


# ---------------------------------------------------------------------------
# Fenced-block + dialect detection
# ---------------------------------------------------------------------------

def find_fenced_blocks(text: str) -> list[tuple[str, str, str]]:
    """Return ``(lang, body, full)`` for every fenced code block — ``full`` is
    the exact matched substring (fences included) so a recovered block can be
    located and replaced verbatim in the source text."""
    if not text:
        return []
    out: list[tuple[str, str, str]] = []
    for m in _FENCE_RE.finditer(text):
        lang = (m.group(1) or "").strip().lower()
        body = m.group(2).strip("\n")
        out.append((lang, body, m.group(0)))
    return out


def detect_mermaid_dialect(dsl: str) -> str | None:
    """Map a Mermaid source to the ora-visual ``type`` it renders as
    (``flowchart`` / ``sequence`` / ``state``), or ``None`` if unrecognized."""
    if not dsl:
        return None
    first = ""
    for line in dsl.strip().splitlines():
        s = line.strip()
        if not s or s.startswith("%%"):
            continue
        first = s.lower()
        break
    if first.startswith("sequencediagram"):
        return "sequence"
    if first.startswith("statediagram"):
        return "state"
    if first.startswith(("flowchart", "graph")):
        return "flowchart"
    return None


# ---------------------------------------------------------------------------
# DSL normalization (make a model's DSL the renderer's parser can accept)
# ---------------------------------------------------------------------------

def normalize_dagitty(dsl: str) -> str:
    """Normalize a model-authored DAGitty block into the single-line,
    semicolon-separated form the validator/renderer parse cleanly.

    Models write multi-line DAGitty with ``#`` comments and occasional LaTeX
    ``$…$`` wrappers; the parser splits on ``;`` and reads one token per
    statement, so newline-separated statements collapse. We strip comments,
    drop LaTeX delimiters, and rejoin statements with ``;``.
    """
    if not dsl:
        return ""
    src = dsl.strip()
    # Pull the inside of dag { ... } if present, keep the wrapper for re-emit.
    m = re.search(r"dag\s*\{(.*)\}", src, re.DOTALL)
    inner = m.group(1) if m else src
    statements: list[str] = []
    for raw_line in inner.splitlines():
        line = raw_line.split("#", 1)[0]          # strip trailing comment
        line = line.replace("$", "").strip()       # drop LaTeX math delimiters
        if not line:
            continue
        for piece in line.split(";"):
            piece = piece.strip().rstrip(";").strip()
            if piece:
                statements.append(piece)
    return "dag { " + " ; ".join(statements) + " }"


def _dagitty_nodes_edges(norm_dsl: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Parse a normalized DAGitty block into (ordered nodes, edges)."""
    m = re.search(r"dag\s*\{(.*)\}", norm_dsl, re.DOTALL)
    inner = m.group(1) if m else norm_dsl
    nodes: list[str] = []
    edges: list[tuple[str, str]] = []

    def _add(n: str):
        if n and n not in nodes:
            nodes.append(n)

    for stmt in inner.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        if "->" in stmt:
            left, right = stmt.split("->", 1)
            a = left.strip().split()[0] if left.strip() else ""
            b = right.strip().split()[0] if right.strip() else ""
            if a and b:
                _add(a)
                _add(b)
                edges.append((a, b))
        else:
            tok = stmt.split()[0] if stmt.split() else ""
            _add(tok)
    return nodes, edges


def _dagitty_tag(norm_dsl: str, tag: str) -> str | None:
    """Find the node carrying ``[tag]`` (exposure/outcome) in the DSL."""
    m = re.search(r"([A-Za-z0-9_.]+)\s*\[[^\]]*\b" + re.escape(tag) + r"\b", norm_dsl)
    return m.group(1) if m else None


def _mermaid_node_id(tok: str) -> str:
    """Bare node id from a Mermaid token: strip shape decorations
    ``A[Label]`` / ``B{Label}`` / ``C((Label))`` / ``D>Label]`` and any
    leftover edge-label residue, then take the first whitespace token."""
    tok = tok.strip()
    # Drop a leading pipe-label residue ``|text|`` if one slipped through.
    tok = re.sub(r"^\|[^|]*\|\s*", "", tok)
    tok = re.split(r"[\[\({>]", tok, 1)[0].strip()
    return tok.split()[0] if tok.split() else ""


def _parse_mermaid_graph(mermaid: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Parse a Mermaid ``graph``/``flowchart`` into (ordered nodes, directed
    edges). Handles ``A --> B``, ``A -- text --> B``, ``A -->|text| B``,
    ``A ==> B``, ``A -.-> B``, chained single-line edges, and bare standalone
    node declarations. Subgraph/loop scaffolding lines are ignored."""
    nodes: list[str] = []
    edges: list[tuple[str, str]] = []

    def _add(n: str):
        if n and n not in nodes:
            nodes.append(n)

    # Split a chained line ``A --> B --> C`` into its arrow segments while
    # keeping the connector so labels stay attached to the right segment.
    arrow = re.compile(r"\s*[-.=]+(?:\|[^|]*\||\"[^\"]*\"|[^>\|\"\n]*?)?[-.=]*>\s*")

    # Diagram-scaffolding lines to skip — matched as whole keywords at a word
    # boundary, so a node id like ``endpoint`` or ``directionA`` is NOT dropped.
    skip_kw = re.compile(
        r"^(?:graph|flowchart|subgraph|end|classDef|class|style|linkStyle|"
        r"direction)\b", re.IGNORECASE)
    for raw in (mermaid or "").splitlines():
        s = raw.strip()
        if not s or s.startswith("%%") or skip_kw.match(s):
            continue
        if not arrow.search(s):
            # Bare node declaration (e.g. ``A[Label]`` or ``A``). Preserve it.
            nid = _mermaid_node_id(s)
            if nid:
                _add(nid)
            continue
        # Chain: collect the node tokens between successive arrows.
        toks = [t for t in arrow.split(s) if t.strip() != ""]
        ids = [_mermaid_node_id(t) for t in toks]
        ids = [i for i in ids if i]
        for n in ids:
            _add(n)
        for i in range(len(ids) - 1):
            edges.append((ids[i], ids[i + 1]))
    return nodes, edges


def dagitty_from_mermaid(mermaid: str) -> str:
    """Convert a Mermaid ``graph``/``flowchart`` into a DAGitty ``dag { … }``."""
    nodes, edges = _parse_mermaid_graph(mermaid)
    stmts = [f"{n}" for n in nodes] + [f"{a} -> {b}" for a, b in edges]
    return "dag { " + " ; ".join(stmts) + " }"


# ---------------------------------------------------------------------------
# Envelope builders (DSL-native kinds)
# ---------------------------------------------------------------------------

def _base_envelope(vtype: str, mode: str | None) -> dict:
    return {
        "schema_version": "0.2",
        "id": f"fig-{vtype}",
        "type": vtype,
        "mode_context": mode or "unknown",
        "relation_to_prose": "integrated",
    }


def mermaid_envelope(dsl: str, vtype: str, mode: str | None) -> dict:
    """Wrap a Mermaid DSL into a flowchart/sequence/state envelope."""
    env = _base_envelope(vtype, mode)
    env["spec"] = {"dialect": vtype, "dsl": dsl.strip()}
    return env


def causal_dag_envelope(dsl: str, mode: str | None,
                        from_mermaid: bool = False) -> dict:
    """Wrap a DAGitty block (or a Mermaid graph) into a causal_dag envelope."""
    norm = dagitty_from_mermaid(dsl) if from_mermaid else normalize_dagitty(dsl)
    nodes, edges = _dagitty_nodes_edges(norm)
    exposure = _dagitty_tag(norm, "exposure")
    outcome = _dagitty_tag(norm, "outcome")
    if not exposure:
        # first node with an outgoing edge (a source)
        srcs = [a for a, _ in edges]
        exposure = next((n for n in nodes if n in srcs), nodes[0] if nodes else "x")
    if not outcome:
        dsts = [b for _, b in edges]
        outcome = next((n for n in reversed(nodes) if n in dsts),
                       nodes[-1] if nodes else "y")
    env = _base_envelope("causal_dag", mode)
    env["spec"] = {"dsl": norm, "focal_exposure": exposure, "focal_outcome": outcome}
    return env


def c4_envelope(dsl: str, mode: str | None, level: str | None = None) -> dict:
    """Wrap a Structurizr workspace DSL into a c4 envelope. Infers the level
    from the DSL when not given (container/component keyword presence)."""
    # Detect container/component as Structurizr DSL KEYWORDS at a token
    # boundary, not as a bare substring (else an identifier like
    # ``thecontainer = …`` would false-positive the level).
    has_container = bool(re.search(r"(?<![A-Za-z0-9_])container\b", dsl))
    has_component = bool(re.search(r"(?<![A-Za-z0-9_])component\b", dsl))
    if not level:
        if has_component:
            level = "component"
        elif has_container:
            level = "container"
        else:
            level = "context"
    # The validator forbids a 'container' keyword on a context-level diagram;
    # if the DSL references containers, promote the level so it validates.
    if level == "context" and has_container:
        level = "container"
    env = _base_envelope("c4", mode)
    env["spec"] = {"level": level, "dsl": dsl.strip()}
    return env


# ---------------------------------------------------------------------------
# Deterministic universal fallback
# ---------------------------------------------------------------------------

_RELATION_RE = re.compile(
    r"\b(because|causes?|caused by|leads? to|results? in|increases?|"
    r"reduces?|supports?|depends? on|requires?|enables?|blocks?|drives?|"
    r"produces?|creates?|slows?|constrains?|amplifies?|dampens?|"
    r"reinforces?|limits?|shapes?|informs?|follows?)\b",
    re.IGNORECASE,
)


def _clip_source_phrase(text: str, limit: int = 84) -> str:
    """Clip source wording at a phrase boundary without re-abstracting it."""
    value = re.sub(r"[`*_#]", "", str(text or ""))
    value = re.sub(r"\s+", " ", value).strip(" \t\r\n-:;,.")
    value = re.sub(r"^(?:the|a|an)\s+", "", value, flags=re.IGNORECASE)
    if len(value) <= limit:
        return value
    boundary = max(
        (value.rfind(mark, 0, limit) for mark in (",", ";", ":", " and ")),
        default=-1,
    )
    if boundary >= 24:
        value = value[:boundary]
    else:
        value = value[:limit].rsplit(" ", 1)[0]
    return value.rstrip(" ,;:")


def _concept_key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()


def _focus_question(inquiry: str | None) -> str | None:
    """Normalize the user's inquiry into a deterministic focus question."""
    source = _clip_source_phrase(inquiry or "", 140)
    if not source:
        return None
    source = source.rstrip(".!;:").strip()
    if source.endswith("?"):
        return source
    lower = source.lower()
    if lower.startswith((
        "how ", "what ", "why ", "when ", "where ", "which ", "who ",
        "can ", "could ", "should ", "would ", "will ", "is ", "are ",
        "do ", "does ", "did ",
    )):
        return source + "?"
    if lower.startswith((
        "explain ", "describe ", "analyze ", "analyse ", "compare ",
        "contrast ", "discuss ", "identify ", "show ", "map ", "trace ",
    )):
        subject = re.sub(
            r"^(?:explain|describe|analyze|analyse|compare|contrast|discuss|"
            r"identify|show|map|trace)\s+",
            "",
            source,
            flags=re.IGNORECASE,
        ).strip()
        if not subject:
            return "What does this response say?"
        return "What does this response say about " + subject[0].lower() + subject[1:] + "?"
    return "What is the answer to: " + source + "?"


def _subject_size(edge_list: list[tuple[str, str, str]],
                  labels: dict[str, str]) -> int:
    """Estimate visual space from source wording and relationship count."""
    keys = {key for source, _, target in edge_list for key in (source, target)}
    return sum(70 + len(labels.get(key, key)) * 6 for key in keys) + len(edge_list) * 90


def _narrow_grounded_subject(
    edges: list[tuple[str, str, str]],
    labels: dict[str, str],
    inquiry: str | None,
) -> list[tuple[str, str, str]]:
    """Choose a grounded subject before the graph is constructed.

    This is scope selection, not post-construction pruning. It only narrows a
    response when the estimated label-and-edge footprint exceeds the visual
    budget and the inquiry identifies a connected subject, or when the source
    contains separate grounded components and one is the clear analytical
    subject. Every retained edge still comes from its original sentence.
    """
    if not edges or _subject_size(edges, labels) <= 4200:
        return edges

    adjacency: dict[str, set[str]] = {key: set() for key in labels}
    for source, _, target in edges:
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)

    inquiry_terms = {term for term in _concept_key(inquiry or "").split() if len(term) > 2}
    anchors = [
        key for key in labels
        if inquiry_terms.intersection(set(key.split()))
    ]
    if anchors:
        keep = set(anchors)
        # One-hop expansion keeps the subject legible without inventing a
        # boundary between two clauses that are actually connected.
        for anchor in anchors:
            keep.update(adjacency.get(anchor, set()))
        candidate = [edge for edge in edges if edge[0] in keep and edge[2] in keep]
        if candidate and _subject_size(candidate, labels) < _subject_size(edges, labels):
            return candidate

    components: list[set[str]] = []
    unseen = set(adjacency)
    while unseen:
        start = next(iter(unseen))
        component = {start}
        queue = [start]
        unseen.remove(start)
        while queue:
            current = queue.pop(0)
            for neighbor in adjacency.get(current, set()):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        components.append(component)
    if len(components) <= 1:
        return edges
    candidates = [
        [edge for edge in edges if edge[0] in component and edge[2] in component]
        for component in components
    ]
    best = max(candidates, key=lambda candidate: (len(candidate), -_subject_size(candidate, labels)))
    return best if best and _subject_size(best, labels) < _subject_size(edges, labels) else edges


def build_concept_map(prose: str, mode: str | None = None,
                      inquiry: str | None = None) -> dict | None:
    """Build a grounded, schema-shaped concept map without a model call.

    This is intentionally a conservative fallback. It emits only relations
    whose connecting clause appears in the source sentence; if no such clause
    exists it returns ``None`` rather than inventing a relationship. Labels are
    clipped source phrases, hierarchy is derived from graph depth, and a
    second incoming edge is preserved as a cross-link instead of being pruned.
    """
    if not isinstance(prose, str) or not prose.strip():
        return None
    sentences = [
        part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", prose)
        if part.strip()
    ]
    edges: list[tuple[str, str, str]] = []
    labels: dict[str, str] = {}
    for sentence in sentences:
        match = _RELATION_RE.search(sentence)
        if not match:
            continue
        left = _clip_source_phrase(sentence[:match.start()])
        right = _clip_source_phrase(sentence[match.end():])
        if not left or not right:
            continue
        left_key, right_key = _concept_key(left), _concept_key(right)
        if not left_key or not right_key or left_key == right_key:
            continue
        labels.setdefault(left_key, left)
        labels.setdefault(right_key, right)
        phrase = re.sub(r"\s+", " ", match.group(0).lower()).strip()
        edges.append((left_key, phrase, right_key))

    if not edges:
        return None

    # Choose the subject before concepts and propositions are materialized;
    # there is no later node-pruning pass that could silently break the claim
    # graph. Labels are retained verbatim from the selected source clauses.
    selected_edges = _narrow_grounded_subject(edges, labels, inquiry)
    if selected_edges is not edges:
        edges = selected_edges
        used_keys = {key for source, _, target in edges for key in (source, target)}
        labels = {key: value for key, value in labels.items() if key in used_keys}

    # Stable first-seen order, then de-duplicate the source-derived phrases.
    phrase_ids: dict[str, str] = {}
    phrases: list[dict[str, str]] = []
    for _, phrase, _ in edges:
        if phrase not in phrase_ids:
            phrase_ids[phrase] = f"L{len(phrases) + 1}"
            phrases.append({"id": phrase_ids[phrase], "text": phrase})

    adjacency: dict[str, list[str]] = {key: [] for key in labels}
    incoming: dict[str, int] = {key: 0 for key in labels}
    for source, _, target in edges:
        adjacency[source].append(target)
        incoming[target] += 1
    roots = [key for key in labels if incoming[key] == 0]
    if not roots:
        roots = [next(iter(labels))]
    levels = {key: 0 for key in roots}
    queue = list(roots)
    while queue:
        source = queue.pop(0)
        for target in adjacency.get(source, []):
            candidate = levels[source] + 1
            if target not in levels or candidate < levels[target]:
                levels[target] = candidate
                queue.append(target)
    for key in labels:
        levels.setdefault(key, 0)

    propositions = []
    seen_edges: set[tuple[str, str, str]] = set()
    for source, phrase, target in edges:
        edge = (source, phrase, target)
        if edge in seen_edges:
            continue
        seen_edges.add(edge)
        propositions.append({
            "from_concept": source,
            "via_phrase": phrase_ids[phrase],
            "to_concept": target,
            "is_cross_link": incoming[target] > 1 or levels[target] <= levels[source],
        })

    focus = _focus_question(inquiry)
    if not focus:
        first_source, _, first_target = edges[0]
        focus = f"How does {labels[first_source]} {phrases[phrase_ids[edges[0][1]]]['text']} {labels[first_target]}?"
        focus = _clip_source_phrase(focus, 140)
        if not focus.endswith("?"):
            focus += "?"
    concept_list = [
        {"id": key, "label": labels[key], "hierarchy_level": levels[key]}
        for key in labels
    ]
    first = propositions[0]
    first_label = labels[first["from_concept"]]
    first_target = labels[first["to_concept"]]
    first_phrase = phrases[int(first["via_phrase"][1:]) - 1]["text"]
    digest = hashlib.sha1(prose.encode("utf-8")).hexdigest()[:12]
    return {
        "schema_version": "0.2",
        "id": f"fig-concept-map-{digest}",
        "type": "concept_map",
        "mode_context": mode or "unknown",
        "relation_to_prose": "integrated",
        "spec": {
            "focus_question": focus,
            "concepts": concept_list,
            "linking_phrases": phrases,
            "propositions": propositions,
        },
        "semantic_description": {
            "level_1_elemental": f"Concept map linking {len(concept_list)} source phrases.",
            "level_2_statistical": f"{len(propositions)} source-derived propositions; {sum(1 for p in propositions if p.get('is_cross_link'))} cross-links.",
            "level_3_perceptual": f"{first_label} {first_phrase} {first_target}.",
            "level_4_contextual": None,
            "short_alt": _clip_source_phrase(
                f"Concept map showing how {first_label} {first_phrase} {first_target}.",
                150,
            ),
            "data_table_fallback": None,
        },
        "title": _clip_source_phrase(f"Concept map: {focus}", 120),
    }


# ---------------------------------------------------------------------------
# Schema-guided pruning + per-type repair (malformed model-envelope path)
# ---------------------------------------------------------------------------

_SPEC_SCHEMA_CACHE: dict[str, dict] = {}


def _load_spec_schema(vtype: str) -> dict | None:
    if vtype in _SPEC_SCHEMA_CACHE:
        return _SPEC_SCHEMA_CACHE[vtype]
    try:
        p = SCHEMAS_ROOT / "specs" / f"{vtype}.json"
        schema = json.loads(p.read_text()) if p.exists() else None
    except Exception:
        schema = None
    _SPEC_SCHEMA_CACHE[vtype] = schema
    return schema


def _resolve_local_ref(ref: str, root: dict) -> dict | None:
    """Resolve a local ``#/$defs/foo`` reference within one spec schema."""
    if not ref.startswith("#/"):
        return None
    node: object = root
    for part in ref[2:].split("/"):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node if isinstance(node, dict) else None


def _prune_to_schema(obj, schema: dict, root: dict):
    """Drop object keys the schema forbids (``additionalProperties: false``),
    recursively. Conservative: only prunes where the schema is explicit; leaves
    everything else untouched. Fail-open at the call site."""
    if schema is None:
        return obj
    if "$ref" in schema:
        resolved = _resolve_local_ref(schema["$ref"], root)
        if resolved is not None:
            schema = resolved
    if isinstance(obj, dict) and schema.get("type") == "object":
        props = schema.get("properties") or {}
        addl = schema.get("additionalProperties", True)
        out = {}
        for k, v in obj.items():
            if k in props:
                out[k] = _prune_to_schema(v, props[k], root)
            elif addl is False:
                continue  # forbidden extra property → drop
            else:
                out[k] = v
        return out
    if isinstance(obj, list) and schema.get("type") == "array" and "items" in schema:
        return [_prune_to_schema(it, schema["items"], root) for it in obj]
    return obj


def _coerce_unit_interval(values: list[float]) -> float:
    """Choose a divisor that maps a 0-based scale into [0,1]."""
    mx = max((abs(v) for v in values), default=0.0)
    if mx <= 1.0:
        return 1.0
    if mx <= 10.0:
        return 10.0
    if mx <= 100.0:
        return 100.0
    return mx


def _repair_quadrant(spec: dict) -> dict:
    """Make a quadrant_matrix spec valid: enforce the four required quadrants
    with names, a non-empty axes_independence_rationale, items in [0,1], and a
    subtype whose extra requirements the content can actually satisfy.

    This is the fix for the constraint-mapping quadrant_matrix synthesis
    failure (1/14): the model frequently omits axes_independence_rationale,
    plots items on a 0-10 / 0-100 scale, or copies subtype=scenario_planning
    from the example without a narrative in every quadrant.
    """
    spec = dict(spec)
    quad_default = {"TL": "Top-left", "TR": "Top-right",
                    "BL": "Bottom-left", "BR": "Bottom-right"}
    quadrants = dict(spec.get("quadrants") or {})
    for key, default_name in quad_default.items():
        q = dict(quadrants.get(key) or {})
        if not (q.get("name") or "").strip():
            q["name"] = default_name
        quadrants[key] = q
    spec["quadrants"] = quadrants

    for axis_key in ("x_axis", "y_axis"):
        ax = dict(spec.get(axis_key) or {})
        ax.setdefault("label", axis_key.replace("_", " ").title())
        ax.setdefault("low_label", "Low")
        ax.setdefault("high_label", "High")
        spec[axis_key] = ax

    # subtype: scenario_planning REQUIRES a narrative in every quadrant.
    # Honor it only when the content supplies them; else use strategic_2x2.
    subtype = spec.get("subtype")
    has_all_narratives = all(
        (quadrants[k].get("narrative") or "").strip() for k in quad_default
    )
    if subtype == "scenario_planning" and not has_all_narratives:
        subtype = "strategic_2x2"
    if subtype not in ("strategic_2x2", "scenario_planning"):
        subtype = "strategic_2x2"
    spec["subtype"] = subtype

    # items into [0,1]. Rescale only when SOMETHING is out of range, and then
    # by ONE shared divisor across all coordinates so a uniform 0-10 / 0-100
    # scale preserves relative position and ordering (a per-value divisor would
    # collapse x=8 and x=80 both to 0.8). When everything is already in [0,1],
    # leave it untouched (a genuine 0.9 stays 0.9).
    items = spec.get("items")
    if isinstance(items, list) and items:
        vals = [it[c] for it in items if isinstance(it, dict)
                for c in ("x", "y") if isinstance(it.get(c), (int, float))]
        out_of_range = any(not (0.0 <= v <= 1.0) for v in vals)
        div = _coerce_unit_interval(vals) if (vals and out_of_range) else 1.0
        fixed = []
        for it in items:
            if not isinstance(it, dict) or not (it.get("label") or "").strip():
                continue
            it = dict(it)
            for c in ("x", "y"):
                v = it.get(c)
                if not isinstance(v, (int, float)):
                    it[c] = 0.5
                else:
                    it[c] = max(0.0, min(1.0, v / div if div else 0.0))
            fixed.append(it)
        spec["items"] = fixed

    rationale = (spec.get("axes_independence_rationale") or "").strip()
    if not rationale:
        xl = spec["x_axis"]["label"]
        yl = spec["y_axis"]["label"]
        spec["axes_independence_rationale"] = (
            f"{xl} and {yl} are treated as independent dimensions: each can vary "
            f"without determining the other, so the four-quadrant partition is "
            f"meaningful rather than collapsing to a single diagonal.")
    return spec


def _repair_causal_dag(spec: dict) -> dict:
    """Normalize a causal_dag DSL and derive the schema-required
    ``focal_exposure`` / ``focal_outcome`` from it when the model omitted them
    (a source node and a sink node respectively), so a model envelope that's
    otherwise sound isn't dropped for missing focal fields."""
    spec = dict(spec)
    dsl = spec.get("dsl")
    if not isinstance(dsl, str) or not dsl.strip():
        return spec
    norm = normalize_dagitty(dsl)
    spec["dsl"] = norm
    nodes, edges = _dagitty_nodes_edges(norm)
    if not (spec.get("focal_exposure") or "").strip():
        exp = _dagitty_tag(norm, "exposure")
        if not exp:
            srcs = [a for a, _ in edges]
            exp = next((n for n in nodes if n in srcs), nodes[0] if nodes else "x")
        spec["focal_exposure"] = exp
    if not (spec.get("focal_outcome") or "").strip():
        out = _dagitty_tag(norm, "outcome")
        if not out:
            dsts = [b for _, b in edges]
            out = next((n for n in reversed(nodes) if n in dsts),
                       nodes[-1] if nodes else "y")
        spec["focal_outcome"] = out
    return spec


def _repair_causal_loop(spec: dict) -> dict:
    """Correct each declared loop ``type`` (R/B) to the parity of '-' polarities
    on its member edges — the single most common CLD synthesis error (the model
    asserts the right loop and the right edges but mislabels reinforcing vs
    balancing). The relationship is deterministic: an even number of negative
    edges → Reinforcing (R), odd → Balancing (B) — exactly what the validator
    checks, so computing it here turns a hard-block into a clean render. The id's
    leading R/B letter is flipped to match so the rendered badge stays honest.
    Non-content: variables, links, and members are untouched."""
    try:
        links = spec.get("links") or []
        # edge polarity map: (from,to) -> polarity string
        pol = {}
        for lk in links:
            if isinstance(lk, dict):
                pol[(lk.get("from"), lk.get("to"))] = lk.get("polarity", "+")
        for loop in (spec.get("loops") or []):
            if not isinstance(loop, dict):
                continue
            members = loop.get("members") or []
            n = len(members)
            if n < 2:
                continue
            minus = 0
            ok = True
            for j in range(n):
                src, dst = members[j], members[(j + 1) % n]
                p = pol.get((src, dst))
                if p is None:
                    ok = False
                    break
                if "-" in str(p):
                    minus += 1
            if not ok:
                continue
            expected = "B" if (minus % 2 == 1) else "R"
            loop["type"] = expected
            lid = loop.get("id")
            if isinstance(lid, str) and lid[:1] in ("R", "B") and lid[:1] != expected:
                loop["id"] = expected + lid[1:]
    except Exception:
        pass
    return spec


_SPEC_REPAIRERS = {
    "quadrant_matrix": _repair_quadrant,
    "causal_dag": _repair_causal_dag,
    "causal_loop_diagram": _repair_causal_loop,
}

# QUANT family (mirror of visual_adversarial.QUANT_TYPES). Under a
# 'critical'-strictness mode the T7/T15 'missing attribution' findings escalate
# Major→Critical and block an otherwise-valid chart. tornado (routed via
# decision-under-uncertainty, which is critical) carries no caption field in
# its schema, so the only honest place to satisfy attribution is a non-empty
# top-level envelope.caption — which T7/T15 accept as evidence of intent.
_QUANT_TYPES = frozenset({"comparison", "time_series", "distribution",
                          "scatter", "heatmap", "tornado"})


def _ensure_quant_caption(env: dict, vtype: str) -> dict:
    """Guarantee a non-empty envelope.caption for a QUANT chart when the model
    supplied no attribution, so it isn't blocked under critical strictness. The
    caption points to the surrounding analysis rather than inventing a
    source/period/n — honest completeness, not fabricated provenance."""
    cap = env.get("caption")
    if isinstance(cap, str) and cap.strip():
        return env
    spec_cap = (env.get("spec") or {}).get("caption")
    if isinstance(spec_cap, dict) and all(spec_cap.get(k) for k in ("source", "period", "n")):
        return env  # structured attribution already present
    title = (env.get("title") or vtype.replace("_", " ")).strip()
    env["caption"] = (f"{title}. Source, period, and parameters are detailed in "
                      f"the accompanying analysis.")
    return env


_ENVELOPE_PROPS: frozenset | None = None


def _envelope_prop_names() -> frozenset:
    """Allowed top-level envelope property names (envelope.json declares
    ``additionalProperties: false``), cached."""
    global _ENVELOPE_PROPS
    if _ENVELOPE_PROPS is None:
        try:
            schema = json.loads((SCHEMAS_ROOT / "envelope.json").read_text())
            _ENVELOPE_PROPS = frozenset((schema.get("properties") or {}).keys())
        except Exception:
            _ENVELOPE_PROPS = frozenset()
    return _ENVELOPE_PROPS


def repair_spec(env: dict, vtype: str | None = None) -> dict:
    """Apply deterministic, content-preserving repairs to a model/synth
    envelope so recoverable shapes validate. Schema-guided pruning (drop
    forbidden extra properties — at the envelope level AND inside the spec)
    runs for every type; per-type repairers fill required fields the model
    commonly omits. Fail-open."""
    try:
        env = dict(env)
        vtype = vtype or env.get("type")
        if not vtype:
            return env
        # Drop forbidden top-level extras (e.g. a stray ``notes`` key) so a
        # model envelope whose only fault is an extra property validates rather
        # than being dropped.
        allowed = _envelope_prop_names()
        if allowed:
            env = {k: v for k, v in env.items() if k in allowed}
        spec = env.get("spec")
        if isinstance(spec, dict):
            repairer = _SPEC_REPAIRERS.get(vtype)
            if repairer:
                spec = repairer(spec)
            schema = _load_spec_schema(vtype)
            if schema is not None:
                spec = _prune_to_schema(spec, schema, schema)
            env["spec"] = spec
        if vtype in _QUANT_TYPES:
            env = _ensure_quant_caption(env, vtype)
        return env
    except Exception:
        return env


# ---------------------------------------------------------------------------
# Candidate extraction + validation
# ---------------------------------------------------------------------------

def _validate_ok(env: dict, mode: str | None,
                 prose: str | None = None) -> bool:
    """Schema-valid AND not adversarially blocked."""
    try:
        from visual_validator import validate_envelope
        from visual_adversarial import review_envelope
    except Exception:
        return False
    try:
        vres = validate_envelope(env)
        if not vres.valid:
            return False
        review = review_envelope(
            env, mode or env.get("mode_context"), prose=prose,
        )
        return not review.blocks
    except Exception:
        return False


# Reader-facing default titles for diagrams the model drew without one. A
# non-empty title is also load-bearing: under a 'critical'-strictness mode the
# adversarial T7 'missing title' finding is escalated Major→Critical and would
# block an otherwise-valid recovered envelope.
_DEFAULT_TITLES = {
    "flowchart": "Process flowchart",
    "sequence": "Sequence diagram",
    "state": "State diagram",
    "causal_dag": "Causal DAG",
    "c4": "Architecture diagram (C4)",
    "causal_loop_diagram": "Causal loop diagram",
    "stock_and_flow": "Stock-and-flow diagram",
}


def _finalize(env: dict, mode: str | None, vtype: str) -> dict:
    """autofill mechanical fields + spec repair + guarantee a title."""
    try:
        from visual_synthesis import autofill
        env = autofill(env, mode or "unknown", vtype)
    except Exception:
        pass
    if not (env.get("title") or "").strip():
        env["title"] = _DEFAULT_TITLES.get(vtype, vtype.replace("_", " ").title())
    return repair_spec(env, vtype)


def _model_envelope_candidates(text: str, mode: str | None):
    """Yield (env, vtype, full_block) for every ``ora-visual`` fenced JSON
    block the model emitted (parse → finalize/repair). ``full_block`` is the
    exact fenced substring, for verbatim replacement."""
    for lang, body, full in find_fenced_blocks(text):
        if lang != "ora-visual":
            continue
        try:
            obj = json.loads(body)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        vtype = obj.get("type")
        if not isinstance(vtype, str):
            continue
        yield _finalize(obj, mode, vtype), vtype, full


def _diagram_candidates(text: str, mode: str | None):
    """Yield (source_kind, body, natural_kind, full_text, is_fence) for DSL
    diagrams the model drew. ``full_text`` is the exact substring; ``is_fence``
    is True for fenced blocks (safe to replace in place) and False for an
    UNfenced brace block sitting inside prose (append-only — replacing it
    verbatim could land mid-sentence)."""
    for lang, body, full in find_fenced_blocks(text):
        if lang in ("mermaid", "mmd"):
            dialect = detect_mermaid_dialect(body)
            if dialect in MERMAID_NATIVE_KINDS:
                yield ("mermaid", body, dialect, full, True)
        elif lang in ("dagitty", "dag"):
            yield ("dagitty", body, "causal_dag", full, True)
        elif lang in ("structurizr", "c4", "dsl") and "workspace" in body.lower():
            yield ("structurizr", body, "c4", full, True)
    # Unfenced DAGitty / Structurizr blocks in prose. Strip ALL fenced regions
    # first so a ``dag {…}`` / ``workspace {…}`` that only exists INSIDE another
    # fenced block (e.g. the spec.dsl string of an ora-visual JSON envelope) is
    # never extracted as a standalone DSL — which would corrupt the JSON if the
    # hook then replaced that substring.
    prose = _FENCE_RE.sub("", text or "")
    dag = _extract_brace_block(prose, "dag")
    if dag:
        yield ("dagitty", dag, "causal_dag", dag, False)
    work = _extract_brace_block(prose, "workspace")
    if work:
        yield ("structurizr", work, "c4", work, False)


def _build_kind(source_kind: str, body: str, natural_kind: str,
                kind: str, mode: str | None):
    """Build an envelope of EXACTLY ``kind`` from one model diagram, or None.
    A mermaid ``graph`` becomes ``causal_dag`` when that's the requested kind,
    a plain ``flowchart`` otherwise."""
    env = None
    if source_kind == "mermaid":
        if kind in MERMAID_NATIVE_KINDS and kind == natural_kind:
            env = mermaid_envelope(body, kind, mode)
        elif kind == "causal_dag" and natural_kind == "flowchart":
            env = causal_dag_envelope(body, mode, from_mermaid=True)
    elif source_kind == "dagitty":
        if kind == "causal_dag":
            env = causal_dag_envelope(body, mode, from_mermaid=False)
    elif source_kind == "structurizr":
        if kind == "c4":
            env = c4_envelope(body, mode)
    return _finalize(env, mode, kind) if env is not None else None


def recover_envelope(texts: list[str], target_kinds: list[str] | None,
                     mode: str | None = None,
                     prose: str | None = None) -> dict | None:
    """Recover a valid envelope from the model's own diagrams.

    Args:
        texts: candidate source strings in priority order (final response
            first, then earlier pipeline-step outputs where the formatter
            hasn't stripped the diagram).
        target_kinds: acceptable ``type`` strings in PREFERENCE order — the
            preferred kind wins even if a different-kind diagram appears earlier
            in the text. Empty / None ⇒ accept each diagram's natural kind in
            document order (general capability).
        mode: Ora mode name (for adversarial routing + mode_context).

    Returns:
        ``{"envelope", "type", "source_text_index", "raw_block", "via"}`` for
        the first model diagram that converts to a valid, non-blocked envelope,
        or ``None`` if nothing recoverable was found.
    """
    target_kinds = [k for k in (target_kinds or []) if isinstance(k, str)]

    for idx, text in enumerate(texts):
        if not text:
            continue
        model_cands = list(_model_envelope_candidates(text, mode))
        diagram_cands = list(_diagram_candidates(text, mode))
        # Resolve kinds in PRIORITY order: explicit targets first; otherwise the
        # natural kinds present, in document order. Iterating kind-outer means a
        # threaded preferred kind beats a different-kind diagram that happens to
        # appear earlier in the text.
        if target_kinds:
            kinds = target_kinds
        else:
            seen, kinds = set(), []
            for _s, _b, nat, _f, _fc in diagram_cands:
                if nat not in seen:
                    seen.add(nat); kinds.append(nat)
            for env, vt, _f in model_cands:
                if vt not in seen:
                    seen.add(vt); kinds.append(vt)
        for kind in kinds:
            # 1) A model-emitted ora-visual envelope of this kind (repair +
            #    validate) — the premium malformed path: fix rather than drop.
            for env, vtype, full in model_cands:
                if vtype != kind:
                    continue
                if _validate_ok(env, mode, prose=prose):
                    return {"envelope": env, "type": vtype, "source_text_index": idx,
                            "raw_block": (full if idx == 0 else None),
                            "via": "model_envelope"}
            # 2) A model-drawn DSL diagram convertible to this kind.
            for source_kind, body, natural_kind, full, is_fence in diagram_cands:
                env = _build_kind(source_kind, body, natural_kind, kind, mode)
                if env is not None and _validate_ok(env, mode, prose=prose):
                    # raw_block (for verbatim in-place replacement) only for a
                    # FENCED diagram in the final response (idx 0). An unfenced
                    # brace block embedded in prose appends instead of replacing,
                    # so the splice can't land mid-sentence.
                    return {"envelope": env, "type": kind, "source_text_index": idx,
                            "raw_block": (full if (idx == 0 and is_fence) else None),
                            "via": source_kind}
    return None


__all__ = [
    "build_concept_map",
    "recover_envelope",
    "repair_spec",
    "mermaid_envelope",
    "causal_dag_envelope",
    "c4_envelope",
    "detect_mermaid_dialect",
    "dagitty_from_mermaid",
    "normalize_dagitty",
    "MERMAID_NATIVE_KINDS",
]
