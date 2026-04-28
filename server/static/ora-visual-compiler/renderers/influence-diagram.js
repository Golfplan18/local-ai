/**
 * ora-visual-compiler / renderers/influence-diagram.js
 * WP-1.3e — renderer for the `influence_diagram` visual type.
 *
 * Howard-Matheson influence diagrams (Howard & Matheson 1981, reprint
 * Decision Analysis 2005). Consumes the shared dot-engine primitive
 * (renderers/dot-engine.js) for layout/SVG. This file is the
 * semantic JSON → DOT translator + invariant checker.
 *
 * Per Protocol §3.8:
 *   spec.nodes          — [{id, label, kind: decision|chance|value|deterministic, description?}]
 *   spec.arcs           — [{from, to, type: informational|functional|relevance, note?}]
 *   spec.temporal_order — optional array of decision node ids in sequence
 *
 * Howard-Matheson symbology (via Graphviz node shapes):
 *   decision      → rectangle     (shape=box)
 *   chance        → ellipse       (shape=ellipse)
 *   value         → octagon       (shape=octagon)
 *   deterministic → double rect   (shape=box, peripheries=2)
 *
 * Arc styling:
 *   informational arcs into decisions → dashed  (style=dashed)
 *   functional/relevance arcs         → solid   (default)
 *
 * Invariants enforced here (the JSON Schema cannot express these):
 *   1. Exactly one value node                         → E_SCHEMA_INVALID
 *   2. Temporal consistency when temporal_order given:
 *      every info-arc parent of a decision is either
 *      earlier-decided OR chance/deterministic        → E_SCHEMA_INVALID
 *   3. Functional-arc subgraph into the value node
 *      must be acyclic                                → E_GRAPH_CYCLE
 *
 * Semantic IDs (for Phase 5 annotation targeting):
 *   Each node: id="id-node-<origId>"
 *   Each edge: id="id-edge-<from>-<to>"
 *
 * Semantic classes:
 *   Root <svg>:   ora-visual ora-visual--influence_diagram
 *   Node group:   ora-visual__id-<kind> ora-visual__node--<kind>
 *   Edge group:   ora-visual__id-edge ora-visual__arc--<type>
 *
 * (Two class vocabularies coexist deliberately: the task spec uses
 *  `ora-visual__id-*`; the WP-1.4 theme CSS targets `ora-visual__node--*`
 *  and `ora-visual__arc--*`. Both are emitted so tests and theme both work.)
 *
 * IMPORTANT: render() is async (returns a Promise). Dispatcher awaits.
 *
 * Depends on:
 *   errors.js
 *   dispatcher.js   (via OraVisualCompiler.registerRenderer)
 *   dot-engine.js   (OraVisualCompiler._dotEngine.dotToSvg)
 *
 * Load order:
 *   ... errors.js → validator.js → renderers/stub.js → dispatcher.js → index.js ...
 *   vendor/viz-js/viz-standalone.js
 *   dot-engine.js
 *   renderers/influence-diagram.js   <- this file
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.influenceDiagram = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;

  // ── Small utilities ────────────────────────────────────────────────────

  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Conservative DOT-literal quoting for ids and labels inside "..." in DOT.
  function _dotQ(s) {
    return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
  }

  // Graphviz is strict about id tokens — they must match a simple identifier
  // syntax or be quoted. We always quote. But we also want the original id
  // available for semantic IDs in the output SVG; we rewrite Graphviz's
  // emitted ids in a post-processing step, so the DOT id only needs to be
  // a stable round-trippable handle. We simply use the original id as the
  // DOT identifier (quoted); Graphviz echoes it into the SVG's <title>
  // child of each node/edge group, which is what we key on.
  function _dotId(s) { return _dotQ(s); }

  const KINDS = new Set(['decision', 'chance', 'value', 'deterministic']);
  const ARC_TYPES = new Set(['informational', 'functional', 'relevance']);

  // ── Invariant checks ───────────────────────────────────────────────────

  /**
   * countValueNodes(nodes) → number
   * Counts nodes with kind === 'value'.
   */
  function countValueNodes(nodes) {
    let n = 0;
    for (const node of nodes) if (node.kind === 'value') n += 1;
    return n;
  }

  /**
   * checkTemporalConsistency(nodes, arcs, temporal_order)
   *   → { ok: bool, violation?: {decisionId, parentId, reason} }
   *
   * For each decision in the temporal order, every information-arc parent
   * must be one of:
   *   - a chance or deterministic node (always available), OR
   *   - a decision node that appears EARLIER in the temporal_order.
   *
   * Non-decision nodes or decisions not in temporal_order are skipped
   * (temporal_order is optional per schema; absent = no check).
   *
   * NOTE: we deliberately check ALL info-arcs into a decision, not only
   * those with `type === informational`. Per Howard-Matheson, the relation
   * "arc entering a decision" IS the information predecessor regardless
   * of the DSL-level type annotation; we keep the check conservative.
   */
  function checkTemporalConsistency(nodes, arcs, temporal_order) {
    if (!Array.isArray(temporal_order) || temporal_order.length === 0) {
      return { ok: true };
    }
    const kindOf = new Map();
    for (const n of nodes) kindOf.set(n.id, n.kind);

    const tIndex = new Map();
    temporal_order.forEach((id, i) => tIndex.set(id, i));

    for (const arc of arcs) {
      const toKind = kindOf.get(arc.to);
      if (toKind !== 'decision') continue;
      // Only decisions that appear in temporal_order are constrained.
      if (!tIndex.has(arc.to)) continue;

      const fromKind = kindOf.get(arc.from);
      if (fromKind === 'chance' || fromKind === 'deterministic') continue;

      if (fromKind === 'decision') {
        const fromIdx = tIndex.get(arc.from);
        const toIdx = tIndex.get(arc.to);
        if (fromIdx === undefined) {
          return {
            ok: false,
            violation: {
              decisionId: arc.to,
              parentId: arc.from,
              reason:
                'decision ' + JSON.stringify(arc.to) +
                ' has an information-arc parent ' +
                JSON.stringify(arc.from) +
                ' (decision) that is not in temporal_order; cannot verify it is earlier-decided',
            },
          };
        }
        if (fromIdx >= toIdx) {
          return {
            ok: false,
            violation: {
              decisionId: arc.to,
              parentId: arc.from,
              reason:
                'decision ' + JSON.stringify(arc.to) +
                ' has an information arc from later-decided node ' +
                JSON.stringify(arc.from) +
                ' (temporal_order positions ' + toIdx + ' and ' + fromIdx + ')',
            },
          };
        }
        continue;
      }

      if (fromKind === 'value') {
        // A value node has no decided outcome until all decisions and
        // chances have resolved — it cannot legitimately inform a decision.
        return {
          ok: false,
          violation: {
            decisionId: arc.to,
            parentId: arc.from,
            reason:
              'decision ' + JSON.stringify(arc.to) +
              ' has an information arc from the value node ' +
              JSON.stringify(arc.from) +
              '; value nodes resolve last and cannot inform decisions',
          },
        };
      }

      // Unknown kind on the parent — pass through; E_SCHEMA_INVALID already
      // fired on schema validation if kind was malformed.
    }
    return { ok: true };
  }

  /**
   * functionalSubgraphCycle(nodes, arcs, valueId) → array | null
   *
   * Extracts the subgraph induced by all nodes reachable (via any arc
   * direction) on a path to the value node, then DFS-checks for a cycle
   * over the directed FUNCTIONAL-arc edges. Returns the cycle path if
   * found, or null if acyclic.
   *
   * Per Protocol §3.8 invariant: "the graph implied by functional arcs
   * from chance/deterministic nodes into the value node forms a DAG".
   */
  function functionalSubgraphCycle(nodes, arcs, valueId) {
    if (!valueId) return null;

    // Build reverse adjacency: for each node, who points TO it via a
    // functional arc. We use this to find the set of nodes on any
    // functional path leading to the value node.
    const funcIn = new Map();
    for (const n of nodes) funcIn.set(n.id, []);
    for (const arc of arcs) {
      if (arc.type !== 'functional') continue;
      if (!funcIn.has(arc.to)) funcIn.set(arc.to, []);
      funcIn.get(arc.to).push(arc.from);
    }

    // BFS backward from the value node over functional arcs to enumerate
    // the subgraph of interest.
    const subgraph = new Set();
    const queue = [valueId];
    subgraph.add(valueId);
    while (queue.length) {
      const u = queue.shift();
      for (const pred of (funcIn.get(u) || [])) {
        if (!subgraph.has(pred)) {
          subgraph.add(pred);
          queue.push(pred);
        }
      }
    }

    // Forward adjacency restricted to the subgraph.
    const adj = new Map();
    for (const id of subgraph) adj.set(id, []);
    for (const arc of arcs) {
      if (arc.type !== 'functional') continue;
      if (subgraph.has(arc.from) && subgraph.has(arc.to)) {
        adj.get(arc.from).push(arc.to);
      }
    }

    // DFS cycle detection (three-color).
    const WHITE = 0, GRAY = 1, BLACK = 2;
    const color = new Map();
    for (const id of subgraph) color.set(id, WHITE);

    let cyc = null;
    function dfs(u, stack) {
      if (cyc) return;
      color.set(u, GRAY);
      stack.push(u);
      for (const v of (adj.get(u) || [])) {
        if (cyc) return;
        const cv = color.get(v);
        if (cv === GRAY) {
          const startIdx = stack.indexOf(v);
          cyc = stack.slice(startIdx).concat([v]);
          return;
        }
        if (cv === WHITE) dfs(v, stack);
      }
      stack.pop();
      color.set(u, BLACK);
    }
    for (const id of subgraph) {
      if (cyc) break;
      if (color.get(id) === WHITE) dfs(id, []);
    }
    return cyc;
  }

  // ── Envelope → DOT translator ──────────────────────────────────────────

  /**
   * idToDot(origId) → string
   * Maps an original node id to a Graphviz-safe identifier form. We don't
   * need this for correctness (we always quote), but we keep a map of
   * original → "n_<index>" tokens so we can rewrite Graphviz's emitted
   * node-group IDs to stable `id-node-<origId>` values after render.
   *
   * We use the ORIGINAL id string for the DOT identifier (quoted) because
   * Graphviz echoes the DOT id into the node's <title> child in the SVG,
   * which is the most reliable handle for post-processing.
   */

  /**
   * buildDot(envelope, parsed) → string
   *
   * Parsed is { nodes, arcs, temporal_order, valueId }.
   * Emits a digraph with:
   *   - Howard-Matheson shapes per kind
   *   - class attributes carrying our semantic classes
   *   - id attributes = original spec node/edge ids (Graphviz uses these
   *     in the SVG <title> child; post-processing uses them to rewrite
   *     the stable id-node-/id-edge- attributes)
   *   - rank=same subgraphs per temporal_order tier when provided
   *   - informational arcs rendered dashed
   */
  function buildDot(envelope, parsed) {
    const title = envelope.title || '';
    const nodes = parsed.nodes;
    const arcs = parsed.arcs;
    const temporal = parsed.temporal_order;

    const lines = [];
    lines.push('digraph OraInfluenceDiagram {');
    lines.push('  rankdir=LR;');
    // Conservative defaults; semantic classes drive appearance via CSS.
    lines.push('  node [margin="0.15,0.08"];');
    lines.push('  edge [];');
    if (title) {
      lines.push('  labelloc="t"; label=' + _dotQ(title) + ';');
    }

    // Emit nodes. Graphviz honors the `class` attribute and passes it
    // through to the SVG <g class="..."> wrapping each node. The `id`
    // attribute we set here is NOT directly used as the SVG group id
    // (Graphviz assigns its own node1, node2, ...), but Graphviz emits
    // the DOT node id as the group's <title> child, which we use as the
    // rewrite key during post-processing.
    for (const node of nodes) {
      const shape = _shapeForKind(node.kind);
      const classList = [
        'ora-visual__id-' + node.kind,       // task-spec class name
        'ora-visual__node',                   // generic hook
        'ora-visual__node--' + node.kind,    // theme CSS (WP-1.4)
      ];
      const attrs = [
        'label=' + _dotQ(node.label),
        'class=' + _dotQ(classList.join(' ')),
        'id=' + _dotQ('id-node-' + node.id),
      ];
      attrs.push.apply(attrs, shape);
      lines.push('  ' + _dotId(node.id) + ' [' + attrs.join(', ') + '];');
    }

    // Rank subgraphs per temporal_order tier. A temporal_order supplies a
    // sequence of decision ids; we interleave each with a `{rank=same}`
    // block — effectively forcing a left-to-right layer order. Graphviz
    // with rankdir=LR will place each rank in its own column.
    if (Array.isArray(temporal) && temporal.length > 0) {
      temporal.forEach((id, i) => {
        if (!parsed.nodeIds.has(id)) return;
        lines.push('  { rank=same; ' + _dotId(id) + '; }');
        // Note: we do NOT add invisible ordering edges here. Graphviz's
        // natural DAG layout + rankdir=LR usually gets column order right
        // from actual arcs; explicit rank sets force same-column nodes.
      });
    }

    // Emit arcs. Informational arcs → dashed (style=dashed). Functional /
    // relevance arcs default solid.
    for (const arc of arcs) {
      const classList = [
        'ora-visual__id-edge',                // task-spec class
        'ora-visual__arc',                    // generic hook
        'ora-visual__arc--' + arc.type,       // theme CSS (informational etc.)
      ];
      const attrs = [
        'class=' + _dotQ(classList.join(' ')),
        'id=' + _dotQ('id-edge-' + arc.from + '-' + arc.to),
      ];
      if (arc.type === 'informational') {
        attrs.push('style=dashed');
      }
      lines.push(
        '  ' + _dotId(arc.from) + ' -> ' + _dotId(arc.to) +
        ' [' + attrs.join(', ') + '];'
      );
    }

    lines.push('}');
    return lines.join('\n');
  }

  /**
   * _shapeForKind(kind) → array of extra DOT attribute tokens
   * Shapes per Howard-Matheson:
   *   decision      → rectangle
   *   chance        → ellipse
   *   value         → octagon
   *   deterministic → double-bordered rectangle
   */
  function _shapeForKind(kind) {
    if (kind === 'decision')      return ['shape=box'];
    if (kind === 'chance')        return ['shape=ellipse'];
    if (kind === 'value')         return ['shape=octagon'];
    if (kind === 'deterministic') return ['shape=box', 'peripheries=2'];
    return ['shape=ellipse'];
  }

  // ── Post-processing: stable element IDs ────────────────────────────────

  /**
   * rewriteStableIds(svg, parsed) → svg
   *
   * Graphviz assigns each generated <g> element its own id (node1, node2,
   * edge1, edge2, etc.) and emits the DOT id as the <title> child of the
   * group. To satisfy the contract "id='id-node-<id>'" / "id='id-edge-
   * <from>-<to>'" on targetable elements, we walk the SVG text and, for
   * each node/edge group, replace the Graphviz-assigned id with our
   * stable one, keyed off the <title> content.
   *
   * We handle two forms of <g class="node">:
   *   <g id="node1" class="ora-visual__id-decision ..."><title>D1</title> ...
   * and their edge counterparts:
   *   <g id="edge1" class="ora-visual__id-edge ..."><title>D1-&gt;V1</title> ...
   *
   * We key nodes off their title text (matching node.id) and edges off
   * the "<from>-&gt;<to>" title Graphviz emits (we look up (from,to) in
   * parsed.arcs).
   */
  function rewriteStableIds(svg, parsed) {
    let out = svg;

    // Graphviz entity-escapes ">" inside <title>; the arrow shows up as
    // "&gt;" in edge titles. We decode that pattern when matching.
    // We build a map title-string → stable-id for both nodes and edges.
    const nodeTitleToId = new Map();
    for (const n of parsed.nodes) {
      nodeTitleToId.set(n.id, 'id-node-' + n.id);
    }
    const edgeTitleToId = new Map();
    for (const a of parsed.arcs) {
      // Graphviz emits either "from->to" or "from-&gt;to" depending on
      // the XML-escape context. We'll normalize both.
      const t1 = a.from + '->' + a.to;
      const t2 = a.from + '-&gt;' + a.to;
      edgeTitleToId.set(t1, 'id-edge-' + a.from + '-' + a.to);
      edgeTitleToId.set(t2, 'id-edge-' + a.from + '-' + a.to);
    }

    // Walk each <g ...> opening tag and its <title> child. We rewrite the
    // id= attribute on the <g> tag if we recognise the title.
    out = out.replace(
      /<g\b([^>]*)>\s*<title\b[^>]*>([^<]*)<\/title>/g,
      function (m, attrs, titleText) {
        const title = titleText.trim();
        const nodeId = nodeTitleToId.get(title);
        const edgeId = edgeTitleToId.get(title);
        const newId = nodeId || edgeId;
        if (!newId) return m;

        // Replace any existing id="..." within attrs, or append one.
        let newAttrs;
        if (/\sid\s*=\s*"[^"]*"/i.test(attrs)) {
          newAttrs = attrs.replace(
            /\sid\s*=\s*"[^"]*"/i,
            ' id="' + newId + '"'
          );
        } else {
          newAttrs = attrs + ' id="' + newId + '"';
        }
        return '<g' + newAttrs + '><title>' + titleText + '</title>';
      }
    );

    return out;
  }

  // ── Root SVG wrap/decoration ───────────────────────────────────────────
  function wrapRootSvg(svg, envelope) {
    const title = envelope.title || '';
    const shortA = envelope.semantic_description &&
                   envelope.semantic_description.short_alt
                     ? envelope.semantic_description.short_alt
                     : '';
    const typeLab = envelope.type || 'influence_diagram';
    const ariaLab = (title || typeLab) + (shortA ? ' — ' + shortA : '');

    let out = svg.replace(/<svg\b([^>]*?)>/i, function (m, attrs) {
      let classes = ['ora-visual', 'ora-visual--influence_diagram'];
      let rest = attrs;
      const cm = rest.match(/\sclass\s*=\s*"([^"]*)"/);
      if (cm) {
        const existing = cm[1].split(/\s+/);
        for (const c of existing) if (c && classes.indexOf(c) < 0) classes.push(c);
        rest = rest.replace(/\sclass\s*=\s*"[^"]*"/, '');
      }
      rest = rest.replace(/\srole\s*=\s*"[^"]*"/gi, '');
      rest = rest.replace(/\saria-label\s*=\s*"[^"]*"/gi, '');
      return '<svg' + rest +
        ' class="' + classes.join(' ') + '"' +
        ' role="img"' +
        ' aria-label="' + _esc(ariaLab) + '">';
    });

    out = out.replace(/<title\b[^>]*>[\s\S]*?<\/title>/i, '');
    out = out.replace(/<svg\b[^>]*>/i, function (openTag) {
      return openTag +
        '<title class="ora-visual__accessible-title">' +
        _esc(ariaLab) + '</title>';
    });

    return out;
  }

  // ── Public render() ────────────────────────────────────────────────────
  /**
   * render(envelope) → Promise<{ svg, errors, warnings }>
   * Contract: never throws. All failure modes return structured errors.
   */
  async function render(envelope) {
    const errors = [];
    const warnings = [];

    const spec = envelope && envelope.spec ? envelope.spec : null;
    if (!spec) {
      errors.push(make(CODES.E_NO_SPEC,
        'influence_diagram renderer: spec field missing', 'spec'));
      return { svg: '', errors, warnings };
    }

    const nodes = Array.isArray(spec.nodes) ? spec.nodes : null;
    const arcs = Array.isArray(spec.arcs) ? spec.arcs : null;
    if (!nodes || nodes.length === 0) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'influence_diagram: spec.nodes must be a non-empty array',
        'spec.nodes'));
      return { svg: '', errors, warnings };
    }
    if (!arcs) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'influence_diagram: spec.arcs must be an array',
        'spec.arcs'));
      return { svg: '', errors, warnings };
    }

    // Light defensive checks on enums; the schema layer is the primary
    // guard, but we may be invoked on a raw spec without Ajv bootstrapped.
    const nodeIds = new Set();
    for (const n of nodes) {
      if (!n || typeof n.id !== 'string' || !n.id.length) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'influence_diagram: every node needs a non-empty string id',
          'spec.nodes'));
        return { svg: '', errors, warnings };
      }
      if (nodeIds.has(n.id)) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'influence_diagram: duplicate node id ' + JSON.stringify(n.id),
          'spec.nodes'));
        return { svg: '', errors, warnings };
      }
      nodeIds.add(n.id);
      if (!KINDS.has(n.kind)) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'influence_diagram: node ' + JSON.stringify(n.id) +
          ' has invalid kind ' + JSON.stringify(n.kind) +
          '; expected one of decision|chance|value|deterministic',
          'spec.nodes'));
        return { svg: '', errors, warnings };
      }
    }
    for (const a of arcs) {
      if (!a || typeof a.from !== 'string' || typeof a.to !== 'string') {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'influence_diagram: every arc needs string from/to',
          'spec.arcs'));
        return { svg: '', errors, warnings };
      }
      if (!nodeIds.has(a.from)) {
        errors.push(make(CODES.E_UNRESOLVED_REF,
          'influence_diagram: arc.from ' + JSON.stringify(a.from) +
          ' does not resolve to a declared node',
          'spec.arcs'));
        return { svg: '', errors, warnings };
      }
      if (!nodeIds.has(a.to)) {
        errors.push(make(CODES.E_UNRESOLVED_REF,
          'influence_diagram: arc.to ' + JSON.stringify(a.to) +
          ' does not resolve to a declared node',
          'spec.arcs'));
        return { svg: '', errors, warnings };
      }
      if (!ARC_TYPES.has(a.type)) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'influence_diagram: arc has invalid type ' + JSON.stringify(a.type) +
          '; expected one of informational|functional|relevance',
          'spec.arcs'));
        return { svg: '', errors, warnings };
      }
    }

    // ── Invariant 1: exactly one value node ───────────────────────────
    const vCount = countValueNodes(nodes);
    if (vCount !== 1) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'influence_diagram: influence diagrams require exactly one value node; found ' + vCount,
        'spec.nodes'));
      return { svg: '', errors, warnings };
    }
    const valueNode = nodes.find(function (n) { return n.kind === 'value'; });
    const valueId = valueNode.id;

    // ── Invariant 2: temporal consistency ─────────────────────────────
    if (Array.isArray(spec.temporal_order)) {
      // Every id in temporal_order must refer to an existing decision.
      for (const id of spec.temporal_order) {
        if (!nodeIds.has(id)) {
          errors.push(make(CODES.E_UNRESOLVED_REF,
            'influence_diagram: temporal_order entry ' + JSON.stringify(id) +
            ' does not resolve to a declared node',
            'spec.temporal_order'));
          return { svg: '', errors, warnings };
        }
      }
      const tc = checkTemporalConsistency(nodes, arcs, spec.temporal_order);
      if (!tc.ok) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'influence_diagram: temporal order violated — ' + tc.violation.reason,
          'spec.temporal_order'));
        return { svg: '', errors, warnings };
      }
    }

    // ── Invariant 3: functional-arc subgraph to value is a DAG ────────
    const cycle = functionalSubgraphCycle(nodes, arcs, valueId);
    if (cycle) {
      errors.push(make(CODES.E_GRAPH_CYCLE,
        'influence_diagram: functional-arc subgraph into the value node is not acyclic: ' +
          cycle.join(' → '),
        'spec.arcs'));
      return { svg: '', errors, warnings };
    }

    // ── Build DOT ─────────────────────────────────────────────────────
    const parsed = {
      nodes: nodes,
      arcs: arcs,
      temporal_order: spec.temporal_order || null,
      valueId: valueId,
      nodeIds: nodeIds,
    };
    const dot = buildDot(envelope, parsed);

    // ── Render via dot-engine ─────────────────────────────────────────
    const engineApi = window.OraVisualCompiler._dotEngine;
    if (!engineApi || typeof engineApi.dotToSvg !== 'function') {
      errors.push(make(CODES.E_RENDERER_THREW,
        'influence_diagram: dot-engine not loaded; cannot render'));
      return { svg: '', errors, warnings };
    }

    const result = await engineApi.dotToSvg(dot, { engine: 'dot' });
    if (result.errors && result.errors.length) {
      return {
        svg: '',
        errors: result.errors,
        warnings: warnings.concat(result.warnings || []),
      };
    }

    // ── Post-process: stable element IDs ──────────────────────────────
    let svg = rewriteStableIds(result.svg, parsed);

    // ── Wrap root with classes + ARIA ─────────────────────────────────
    svg = wrapRootSvg(svg, envelope);

    return {
      svg: svg,
      errors: [],
      warnings: warnings.concat(result.warnings || []),
    };
  }

  // Register with the dispatcher.
  if (window.OraVisualCompiler &&
      typeof window.OraVisualCompiler.registerRenderer === 'function') {
    window.OraVisualCompiler.registerRenderer('influence_diagram', { render: render });
  }

  // Expose internals for unit testing.
  return {
    render: render,
    _countValueNodes: countValueNodes,
    _checkTemporalConsistency: checkTemporalConsistency,
    _functionalSubgraphCycle: functionalSubgraphCycle,
    _buildDot: buildDot,
    _rewriteStableIds: rewriteStableIds,
  };
}());
