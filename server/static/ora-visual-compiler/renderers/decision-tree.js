/**
 * ora-visual-compiler / renderers/decision-tree.js
 * WP-1.3d — renderer for the `decision_tree` visual type (DECISION family).
 *
 * Howard-Raiffa convention:
 *   Decision  node  → square
 *   Chance    node  → circle
 *   Terminal  node  → triangle
 *
 * Edges from chance nodes carry a probability label; edges from decision
 * nodes carry an action label. Decision-node edges MUST NOT carry a
 * probability (enforced here; the JSON Schema cannot express it).
 *
 * Rollback EV (mode=decision):
 *   terminal.EV = payoff
 *   chance.EV   = Σ (child.probability × child.EV)
 *   decision.EV = max(child.EV)   — argmax marks the optimal branch.
 *
 * Layout: Dagre (MIT, v0.8.5) with rankdir="LR". The renderer emits
 * hand-rolled SVG on top of the Dagre geometry; we never ask Dagre to
 * produce SVG (it does not).
 *
 * Semantic IDs (for Phase 5 annotation targeting):
 *   Node: id="dt-node-<path>"     where <path> is a stable ancestry hash
 *                                 (root → child index chain; see _nodeId).
 *   Edge: id="dt-edge-<from>-<to>"
 *
 * Error codes (from errors.js):
 *   E_NO_SPEC         — spec missing
 *   E_SCHEMA_INVALID  — structural invariant (decision.children ≥ 1,
 *                       terminals missing payoff in decision mode,
 *                       decision-edge with probability, terminal w/ children,
 *                       missing utility_units in decision mode)
 *   E_PROB_SUM        — chance-node probabilities don't sum to 1 ± 1e-6
 *   E_RENDERER_THREW  — dagre not loaded or internal failure
 *
 * Depends on:
 *   errors.js
 *   dispatcher.js       (via OraVisualCompiler.registerRenderer)
 *   vendor/dagre/dagre.min.js   — window.dagre
 *
 * Load order:
 *   ... errors.js → validator.js → renderers/stub.js → dispatcher.js → index.js ...
 *   vendor/dagre/dagre.min.js
 *   renderers/decision-tree.js       <- this file
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.decisionTree = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;

  // Invariant precision — matches the Protocol's ±1e-6 tolerance.
  const PROB_EPS = 1e-6;

  // ── Small utilities ────────────────────────────────────────────────────

  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Stable per-node identifier. Encodes the path from root so siblings with
  // identical labels still get distinct IDs. Root = "r"; child of root at
  // index 2 = "r-2"; grandchild = "r-2-0"; etc. Phase 5 annotators can treat
  // these as opaque but deterministic.
  function _nodeId(path) {
    return path.length === 0 ? 'r' : 'r-' + path.join('-');
  }

  // Pretty-print an EV — trim pointless decimals, preserve negative sign.
  function _fmtEv(v) {
    if (!isFinite(v)) return String(v);
    if (Math.abs(v) >= 100 || v === Math.trunc(v)) return String(Math.round(v * 100) / 100);
    return String(Math.round(v * 1000) / 1000);
  }

  // Short probability format: 2-3 sig figs after decimal.
  function _fmtProb(p) {
    if (!isFinite(p)) return String(p);
    const s = String(Math.round(p * 1000) / 1000);
    return s;
  }

  // ── Tree walker / invariant check ──────────────────────────────────────
  // Walk the spec.root tree producing a normalized in-memory form:
  //   { id, kind, label, payoff?, children: [{ edgeLabel, probability?, node }] }
  // and simultaneously enforce the Protocol invariants.

  function _walk(root, mode, errors) {
    const nodes = [];                // flat list (for Dagre add)
    const edges = [];                // flat list (for Dagre add)

    function visit(node, path, parentKind) {
      const id = _nodeId(path);
      const kind = node && node.kind;
      const label = (node && node.label) || '';

      // Defensive structural checks — the schema should have caught most of
      // these but the renderer never throws, it always surfaces structured
      // errors.
      if (kind !== 'decision' && kind !== 'chance' && kind !== 'terminal') {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'decision_tree: node at ' + id + " has invalid kind '" + kind + "'",
          'spec.root' + path.map(function (i) { return '.children[' + i + '].node'; }).join('')));
        return null;
      }

      const record = {
        id: id,
        kind: kind,
        label: label,
        payoff: typeof node.payoff === 'number' ? node.payoff : undefined,
        children: [],
        ev: undefined,
        optimalChildIndex: undefined,
      };
      nodes.push(record);

      const children = Array.isArray(node.children) ? node.children : [];

      // Decision invariant: ≥ 1 child.
      if (kind === 'decision' && children.length === 0) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'decision_tree: decision node ' + JSON.stringify(label) +
          ' (' + id + ') has no children',
          'spec.root' + path.map(function (i) { return '.children[' + i + '].node'; }).join('')));
      }

      // Terminal invariants: no children; payoff required in decision mode.
      if (kind === 'terminal') {
        if (children.length > 0) {
          errors.push(make(CODES.E_SCHEMA_INVALID,
            'decision_tree: terminal node ' + JSON.stringify(label) +
            ' (' + id + ') has children (terminals must be leaves)',
            'spec.root' + path.map(function (i) { return '.children[' + i + '].node'; }).join('')));
        }
        if (mode === 'decision' && typeof node.payoff !== 'number') {
          errors.push(make(CODES.E_SCHEMA_INVALID,
            'decision_tree: terminal ' + JSON.stringify(label) +
            ' (' + id + ") is missing required 'payoff' (mode=decision)",
            'spec.root' + path.map(function (i) { return '.children[' + i + '].node'; }).join('') + '.payoff'));
        }
      }

      // Chance invariant: probabilities on every child edge, summing to 1.
      if (kind === 'chance' && children.length > 0) {
        let sum = 0;
        let missingCount = 0;
        for (const edge of children) {
          if (typeof edge.probability !== 'number') missingCount += 1;
          else sum += edge.probability;
        }
        if (missingCount > 0) {
          errors.push(make(CODES.E_PROB_SUM,
            'decision_tree: chance node ' + JSON.stringify(label) +
            ' (' + id + ') has ' + missingCount +
            ' outgoing edge(s) without probability',
            'spec.root' + path.map(function (i) { return '.children[' + i + '].node'; }).join('') + '.children'));
        } else if (Math.abs(sum - 1) > PROB_EPS) {
          errors.push(make(CODES.E_PROB_SUM,
            'decision_tree: chance node ' + JSON.stringify(label) +
            ' (' + id + ') child probabilities sum to ' +
            sum.toFixed(6) + ', expected 1.0 ± ' + PROB_EPS,
            'spec.root' + path.map(function (i) { return '.children[' + i + '].node'; }).join('') + '.children'));
        }
      }

      // Decision invariant: NO probability on outgoing edges.
      if (kind === 'decision') {
        for (let i = 0; i < children.length; i++) {
          if (typeof children[i].probability === 'number') {
            errors.push(make(CODES.E_SCHEMA_INVALID,
              'decision_tree: decision node ' + JSON.stringify(label) +
              ' (' + id + ') outgoing edge ' + JSON.stringify(children[i].edge_label || '') +
              ' carries probability=' + children[i].probability +
              ' (probability belongs on chance edges only)',
              'spec.root' + path.map(function (j) { return '.children[' + j + '].node'; }).join('') +
                '.children[' + i + '].probability'));
          }
        }
      }

      // Recurse.
      for (let i = 0; i < children.length; i++) {
        const edge = children[i];
        const childPath = path.concat([i]);
        const childRecord = visit(edge.node, childPath, kind);
        if (!childRecord) continue;

        const edgeRec = {
          from: id,
          to: childRecord.id,
          edgeLabel: edge.edge_label || '',
          probability: typeof edge.probability === 'number' ? edge.probability : undefined,
          payoff: typeof edge.payoff === 'number' ? edge.payoff : undefined,
          optimal: false,
          childIndex: i,
        };
        edges.push(edgeRec);
        record.children.push({ edge: edgeRec, node: childRecord });
      }

      return record;
    }

    const tree = visit(root, [], null);
    return { tree: tree, nodes: nodes, edges: edges };
  }

  // ── Rollback EV (post-order) ───────────────────────────────────────────
  // Only meaningful when mode === 'decision'. Returns the root's EV; side-
  // effects record.ev on every node and record.optimalChildIndex on
  // decision nodes, and edge.optimal=true on the chosen branch(es).
  function _rollback(record) {
    if (!record) return NaN;

    if (record.kind === 'terminal') {
      record.ev = typeof record.payoff === 'number' ? record.payoff : NaN;
      return record.ev;
    }

    if (record.children.length === 0) {
      // Guard — a decision with zero children has already produced an
      // E_SCHEMA_INVALID error; we still assign NaN so downstream code is
      // well-defined.
      record.ev = NaN;
      return NaN;
    }

    if (record.kind === 'chance') {
      let sum = 0;
      for (const c of record.children) {
        const childEv = _rollback(c.node);
        const p = typeof c.edge.probability === 'number' ? c.edge.probability : 0;
        sum += p * childEv;
      }
      record.ev = sum;
      return sum;
    }

    if (record.kind === 'decision') {
      let bestEv = -Infinity;
      let bestIdx = -1;
      for (let i = 0; i < record.children.length; i++) {
        const childEv = _rollback(record.children[i].node);
        if (childEv > bestEv || bestIdx === -1) {
          bestEv = childEv;
          bestIdx = i;
        }
      }
      record.ev = bestEv;
      record.optimalChildIndex = bestIdx;
      if (bestIdx >= 0) record.children[bestIdx].edge.optimal = true;
      return bestEv;
    }

    record.ev = NaN;
    return NaN;
  }

  // ── Dagre layout ───────────────────────────────────────────────────────
  // Box sizes account for longest label plus padding. Rough width proxy:
  // char count × 7px + padding. Height is kind-dependent — triangles need
  // a bit more vertical room to be readable.
  const NODE_DIM = {
    decision: { w: 28, h: 28 },  // square side
    chance:   { w: 28, h: 28 },  // circle diameter
    terminal: { w: 30, h: 28 },  // triangle bounding box
  };

  function _measureLabel(label) {
    // Approximate: ~6.2 px per char for 11px font. Over-estimate to keep
    // text clear of the shape.
    return Math.max(28, Math.min(160, (label || '').length * 6.5 + 12));
  }

  // Build a Dagre graph; return laid-out { nodes: Map<id,{x,y,w,h,kind}>,
  //                                         edges: [{from,to,points}] }
  function _layoutWithDagre(nodeList, edgeList) {
    if (!window.dagre || !window.dagre.graphlib ||
        typeof window.dagre.layout !== 'function') {
      const e = new Error('dagre not loaded');
      e._kind = 'dagre_missing';
      throw e;
    }

    const g = new window.dagre.graphlib.Graph({ directed: true });
    g.setGraph({
      rankdir: 'LR',
      nodesep: 44,      // between siblings
      ranksep: 110,     // between parent and child ranks
      marginx: 24,
      marginy: 24,
    });
    g.setDefaultEdgeLabel(function () { return {}; });

    // We use separate "shape" width/height for the node geometry and pass
    // a wider bounding box to Dagre that includes the text label, so the
    // layout leaves room for labels without overlap. labelOffset is how
    // much of that box sits to the RIGHT of the shape center.
    for (const n of nodeList) {
      const dim = NODE_DIM[n.kind] || { w: 28, h: 28 };
      const labelW = _measureLabel(n.label);
      // Full bounding box: shape diameter + label text to its right.
      const totalW = dim.w + 8 + labelW;
      const totalH = Math.max(dim.h, 24) + 18;  // + EV annotation line
      g.setNode(n.id, {
        width: totalW,
        height: totalH,
        shapeW: dim.w,
        shapeH: dim.h,
        labelW: labelW,
        label: n.label,
        kind: n.kind,
      });
    }

    for (const e of edgeList) {
      g.setEdge(e.from, e.to, {
        labelpos: 'c',
        label: e.edgeLabel,
      });
    }

    window.dagre.layout(g);

    const laidNodes = new Map();
    for (const id of g.nodes()) {
      const meta = g.node(id);
      laidNodes.set(id, {
        id: id,
        x: meta.x, y: meta.y,
        w: meta.width, h: meta.height,
        shapeW: meta.shapeW, shapeH: meta.shapeH,
        labelW: meta.labelW,
        kind: meta.kind,
        label: meta.label,
      });
    }

    const laidEdges = [];
    for (const e of g.edges()) {
      const meta = g.edge(e);
      laidEdges.push({
        from: e.v,
        to: e.w,
        points: (meta.points || []).slice(),
      });
    }

    const graph = g.graph();
    const width  = graph.width  || 480;
    const height = graph.height || 320;

    return { nodes: laidNodes, edges: laidEdges, width: width, height: height };
  }

  // ── SVG emission ───────────────────────────────────────────────────────

  function _shapeSvg(layoutNode, record, idAttr) {
    const cx = layoutNode.x;
    const cy = layoutNode.y;
    const shapeW = layoutNode.shapeW;
    const shapeH = layoutNode.shapeH;

    // Place the shape on the LEFT of the Dagre-assigned box so the text
    // label can flow to the right.
    const shapeCx = cx - layoutNode.w / 2 + shapeW / 2;
    const shapeCy = cy;

    if (record.kind === 'decision') {
      const x = shapeCx - shapeW / 2;
      const y = shapeCy - shapeH / 2;
      return (
        '<rect ' + idAttr +
        ' class="ora-visual__dt-decision ora-visual__node ora-visual__node--decision"' +
        ' x="' + x + '" y="' + y + '"' +
        ' width="' + shapeW + '" height="' + shapeH + '"' +
        ' rx="2" ry="2"' +
        '></rect>'
      );
    }
    if (record.kind === 'chance') {
      const r = Math.min(shapeW, shapeH) / 2;
      return (
        '<circle ' + idAttr +
        ' class="ora-visual__dt-chance ora-visual__node ora-visual__node--chance"' +
        ' cx="' + shapeCx + '" cy="' + shapeCy + '"' +
        ' r="' + r + '"></circle>'
      );
    }
    // terminal — pointing right (→).
    const halfW = shapeW / 2;
    const halfH = shapeH / 2;
    const p1 = (shapeCx - halfW) + ',' + (shapeCy - halfH);
    const p2 = (shapeCx + halfW) + ',' + shapeCy;
    const p3 = (shapeCx - halfW) + ',' + (shapeCy + halfH);
    return (
      '<polygon ' + idAttr +
      ' class="ora-visual__dt-terminal ora-visual__node ora-visual__node--terminal"' +
      ' points="' + p1 + ' ' + p2 + ' ' + p3 + '"></polygon>'
    );
  }

  function _labelSvg(layoutNode, record, mode) {
    // Label sits to the right of the shape.
    const shapeCx = layoutNode.x - layoutNode.w / 2 + layoutNode.shapeW / 2;
    const textX   = shapeCx + layoutNode.shapeW / 2 + 6;
    const textY   = layoutNode.y + 4;  // visual baseline alignment

    const parts = [];
    parts.push(
      '<text class="ora-visual__label"' +
      ' x="' + textX + '" y="' + textY + '"' +
      ' dominant-baseline="middle"' +
      '>' + _esc(record.label) + '</text>'
    );

    // EV annotation below the label when computed.
    if (mode === 'decision' && typeof record.ev === 'number' && isFinite(record.ev)) {
      parts.push(
        '<text class="ora-visual__ev ora-visual__dt-ev"' +
        ' x="' + textX + '" y="' + (textY + 14) + '"' +
        ' dominant-baseline="middle"' +
        '>EV=' + _esc(_fmtEv(record.ev)) + '</text>'
      );
    }

    // Payoff annotation for terminals in probability-only mode — if payoff
    // happens to be present, surface it; no EV in this mode.
    if (mode !== 'decision' && record.kind === 'terminal' &&
        typeof record.payoff === 'number') {
      parts.push(
        '<text class="ora-visual__edge-label ora-visual__edge-label--payoff"' +
        ' x="' + textX + '" y="' + (textY + 14) + '"' +
        ' dominant-baseline="middle"' +
        '>$' + _esc(_fmtEv(record.payoff)) + '</text>'
      );
    }

    return parts.join('');
  }

  function _pathDSvg(points) {
    // Dagre produces at least [start, end]; often [start, mid, end].
    // We emit a simple moveto/lineto chain — not a bezier, for legibility
    // and to keep geometry predictable for downstream selector queries.
    if (!points || points.length === 0) return '';
    let d = 'M ' + points[0].x + ' ' + points[0].y;
    for (let i = 1; i < points.length; i++) {
      d += ' L ' + points[i].x + ' ' + points[i].y;
    }
    return d;
  }

  function _edgeMidpoint(points) {
    if (!points || points.length === 0) return { x: 0, y: 0 };
    if (points.length === 1) return points[0];
    // Pick the geometric midpoint along the polyline (walk by arc length).
    let total = 0;
    const segs = [];
    for (let i = 1; i < points.length; i++) {
      const dx = points[i].x - points[i - 1].x;
      const dy = points[i].y - points[i - 1].y;
      const len = Math.sqrt(dx * dx + dy * dy);
      segs.push(len);
      total += len;
    }
    const half = total / 2;
    let walked = 0;
    for (let i = 0; i < segs.length; i++) {
      if (walked + segs[i] >= half) {
        const t = segs[i] === 0 ? 0 : (half - walked) / segs[i];
        return {
          x: points[i].x + t * (points[i + 1].x - points[i].x),
          y: points[i].y + t * (points[i + 1].y - points[i].y),
        };
      }
      walked += segs[i];
    }
    return points[points.length - 1];
  }

  function _edgeSvg(edgeRec, layout, fromRecord, mode) {
    const laid = layout.edges.find(function (e) {
      return e.from === edgeRec.from && e.to === edgeRec.to;
    });
    if (!laid) return '';

    const d = _pathDSvg(laid.points);
    const mid = _edgeMidpoint(laid.points);

    const classes = ['ora-visual__dt-edge', 'ora-visual__edge'];
    if (edgeRec.optimal) classes.push('ora-visual__dt-edge--optimal');
    if (fromRecord && fromRecord.kind === 'chance') {
      classes.push('ora-visual__dt-edge--chance');
    } else if (fromRecord && fromRecord.kind === 'decision') {
      classes.push('ora-visual__dt-edge--decision');
    }

    const id = 'dt-edge-' + edgeRec.from + '-' + edgeRec.to;

    const parts = [];
    parts.push('<g id="' + id + '" class="' + classes.join(' ') + '">');
    parts.push(
      '<path class="ora-visual__dt-edge-path"' +
      ' d="' + d + '" fill="none"></path>'
    );

    // Midpoint label: probability for chance edges, edge_label for decision
    // edges. If both are meaningful (e.g. action + terminal payoff on the
    // edge), we stack them.
    const lines = [];
    if (fromRecord && fromRecord.kind === 'chance' &&
        typeof edgeRec.probability === 'number') {
      lines.push({
        cls: 'ora-visual__edge-label ora-visual__edge-label--probability ora-visual__dt-edge-label',
        text: 'p=' + _fmtProb(edgeRec.probability),
      });
      if (edgeRec.edgeLabel) {
        lines.push({
          cls: 'ora-visual__edge-label ora-visual__dt-edge-label',
          text: edgeRec.edgeLabel,
        });
      }
    } else if (edgeRec.edgeLabel) {
      lines.push({
        cls: 'ora-visual__edge-label ora-visual__dt-edge-label',
        text: edgeRec.edgeLabel,
      });
    }
    if (typeof edgeRec.payoff === 'number') {
      lines.push({
        cls: 'ora-visual__edge-label ora-visual__edge-label--payoff ora-visual__dt-edge-label',
        text: '$' + _fmtEv(edgeRec.payoff),
      });
    }

    const lineH = 12;
    const startY = mid.y - ((lines.length - 1) * lineH) / 2;
    for (let i = 0; i < lines.length; i++) {
      parts.push(
        '<text class="' + lines[i].cls + '"' +
        ' x="' + mid.x + '" y="' + (startY + i * lineH) + '"' +
        ' text-anchor="middle" dominant-baseline="middle"' +
        '>' + _esc(lines[i].text) + '</text>'
      );
    }

    parts.push('</g>');
    return parts.join('');
  }

  function _nodeGroupSvg(record, layoutNode, mode) {
    if (!layoutNode) return '';
    const nodeId = 'dt-node-' + record.id;
    const evAttr = (mode === 'decision' && typeof record.ev === 'number' && isFinite(record.ev))
      ? ' data-rollback-ev="' + _fmtEv(record.ev) + '"' : '';
    const optimalAttr = (mode === 'decision' &&
                        record.kind === 'decision' &&
                        typeof record.optimalChildIndex === 'number')
      ? ' data-optimal-child="' + record.optimalChildIndex + '"' : '';

    const parts = [];
    parts.push(
      '<g id="' + nodeId + '"' +
      ' class="ora-visual__dt-node ora-visual__dt-node--' + record.kind + '"' +
      evAttr + optimalAttr + '>'
    );
    parts.push(_shapeSvg(layoutNode, record, 'data-node-id="' + nodeId + '"'));
    parts.push(_labelSvg(layoutNode, record, mode));
    parts.push('</g>');
    return parts.join('');
  }

  function _emitSvg(root, mode, layout, envelope) {
    const title = envelope.title || '';
    const shortA = (envelope.semantic_description &&
                    envelope.semantic_description.short_alt) || '';
    const typeLabel = envelope.type || 'decision_tree';
    const ariaLabel = (title || typeLabel) + (shortA ? ' \u2014 ' + shortA : '');

    // Compute viewBox from Dagre's reported graph extents with a bit of
    // padding to give labels breathing room.
    const pad = 12;
    const width  = layout.width  + pad * 2;
    const height = layout.height + pad * 2;
    const viewBox = (-pad) + ' ' + (-pad) + ' ' + width + ' ' + height;

    const parts = [];
    parts.push(
      '<svg xmlns="http://www.w3.org/2000/svg"' +
      ' class="ora-visual ora-visual--decision_tree"' +
      ' role="img"' +
      ' aria-label="' + _esc(ariaLabel) + '"' +
      ' viewBox="' + viewBox + '"' +
      '>'
    );
    parts.push(
      '<title class="ora-visual__accessible-title">' +
      _esc(ariaLabel) + '</title>'
    );
    if (title) {
      parts.push(
        '<text class="ora-visual__title"' +
        ' x="' + (layout.width / 2) + '" y="-2"' +
        ' text-anchor="middle" dominant-baseline="middle"' +
        '>' + _esc(title) + '</text>'
      );
    }

    // Edges first so node shapes paint on top.
    parts.push('<g class="ora-visual__dt-edges">');
    _forEachNode(root, function (rec) {
      for (const c of rec.children) {
        parts.push(_edgeSvg(c.edge, layout, rec, mode));
      }
    });
    parts.push('</g>');

    parts.push('<g class="ora-visual__dt-nodes">');
    _forEachNode(root, function (rec) {
      parts.push(_nodeGroupSvg(rec, layout.nodes.get(rec.id), mode));
    });
    parts.push('</g>');

    parts.push('</svg>');
    return parts.join('');
  }

  function _forEachNode(root, fn) {
    if (!root) return;
    fn(root);
    for (const c of root.children) _forEachNode(c.node, fn);
  }

  // ── Public render() ────────────────────────────────────────────────────
  /**
   * render(envelope) → { svg: string, errors: Array, warnings: Array }
   * Synchronous. Never throws. All failure modes return structured errors
   * and an empty svg string.
   */
  function render(envelope) {
    const errors = [];
    const warnings = [];

    const spec = envelope && envelope.spec ? envelope.spec : null;
    if (!spec) {
      errors.push(make(CODES.E_NO_SPEC,
        'decision_tree renderer: spec field missing', 'spec'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    const mode = spec.mode;
    if (mode !== 'decision' && mode !== 'probability') {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        "decision_tree: spec.mode must be 'decision' or 'probability' (got " +
        JSON.stringify(mode) + ')',
        'spec.mode'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    // utility_units is a schema-level required-if; defensively verify.
    if (mode === 'decision' &&
        (typeof spec.utility_units !== 'string' || spec.utility_units.length === 0)) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        "decision_tree: 'utility_units' is required when mode=decision",
        'spec.utility_units'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    const root = spec.root;
    if (!root || typeof root !== 'object') {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'decision_tree: spec.root is missing or not an object',
        'spec.root'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    // 1. Walk + invariant-check. Accumulates errors.
    const walked = _walk(root, mode, errors);
    if (errors.length > 0) {
      return { svg: '', errors: errors, warnings: warnings };
    }
    if (!walked.tree) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'decision_tree: unable to parse tree from spec.root',
        'spec.root'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    // 2. Rollback EV (decision mode only). Attach to records.
    if (mode === 'decision') {
      _rollback(walked.tree);
    }

    // 3. Dagre layout.
    let layout;
    try {
      layout = _layoutWithDagre(walked.nodes, walked.edges);
    } catch (err) {
      if (err && err._kind === 'dagre_missing') {
        errors.push(make(CODES.E_RENDERER_THREW,
          'decision_tree: dagre not loaded. ' +
          'Ensure vendor/dagre/dagre.min.js loads before renderers/decision-tree.js',
          'type'));
      } else {
        errors.push(make(CODES.E_RENDERER_THREW,
          'decision_tree: layout failed: ' +
          (err && err.message ? err.message : String(err)),
          'type'));
      }
      return { svg: '', errors: errors, warnings: warnings };
    }

    // 4. Emit SVG.
    let svg;
    try {
      svg = _emitSvg(walked.tree, mode, layout, envelope);
    } catch (err) {
      errors.push(make(CODES.E_RENDERER_THREW,
        'decision_tree: svg emission failed: ' +
        (err && err.message ? err.message : String(err)),
        'type'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    return { svg: svg, errors: [], warnings: warnings };
  }

  // Register with the dispatcher.
  if (window.OraVisualCompiler &&
      typeof window.OraVisualCompiler.registerRenderer === 'function') {
    window.OraVisualCompiler.registerRenderer('decision_tree', { render: render });
  } else if (window.OraVisualCompiler &&
             window.OraVisualCompiler._dispatcher &&
             window.OraVisualCompiler._dispatcher.register) {
    window.OraVisualCompiler._dispatcher.register('decision_tree', { render: render });
  }

  // Expose internals for unit testing.
  return {
    render: render,
    _walk: _walk,
    _rollback: _rollback,
    _nodeId: _nodeId,
    _fmtEv: _fmtEv,
  };
}());
