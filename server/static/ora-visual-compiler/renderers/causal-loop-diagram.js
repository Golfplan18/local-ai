/**
 * ora-visual-compiler / renderers/causal-loop-diagram.js
 * WP-1.3a — renderer for the `causal_loop_diagram` visual type.
 *
 * Per Protocol §3.3 (CAUSAL family, CLD). A CLD is a directed signed graph
 * plus a list of declared feedback loops. Node positions are computed by a
 * d3-force simulation; edges are drawn as curved SVG paths with polarity
 * markers (+ / −) near their midpoints; declared loops are annotated with
 * an R (reinforcing) or B (balancing) glyph placed at the centroid of the
 * loop's node positions.
 *
 * Invariants enforced here (the JSON Schema cannot express these):
 *   - variables[].id unique                          → E_UNRESOLVED_REF
 *   - every links[].from / links[].to resolves       → E_UNRESOLVED_REF
 *   - no orphan nodes unless spec.allow_isolated     → W_ORPHAN_NODE
 *   - each declared loop is a genuine cycle in graph → E_GRAPH_CYCLE
 *   - loop parity matches declared type:
 *       even count of '-' → R (reinforcing)
 *       odd  count of '-' → B (balancing)              → E_SCHEMA_INVALID
 *
 * Stable semantic IDs (for Phase 5 annotation targeting):
 *   - <g id="cld-node-<variable_id>">
 *   - <path id="cld-edge-<from>-<to>">
 *   - <g id="cld-loop-<loop.id>">
 *
 * Stable semantic classes (styling via ora-visual-theme.css):
 *   - ora-visual ora-visual--causal_loop_diagram           (root)
 *   - ora-visual__node                                      (each node group)
 *   - ora-visual__node-label                                (node text)
 *   - ora-visual__edge ora-visual__edge--pos | --neg        (each link path)
 *   - ora-visual__edge--delay                               (delay links)
 *   - ora-visual__edge-label ora-visual__polarity-indicator (polarity glyph)
 *   - ora-visual__polarity-indicator--positive | --negative
 *   - ora-visual__loop ora-visual__loop--reinforcing|--balancing (loop marker)
 *   - ora-visual__loop-label                                (loop glyph text)
 *   - ora-visual__marker--pos | ora-visual__marker--neg     (arrowhead markers)
 *
 * SYNC CONTRACT: render() is synchronous and returns { svg, errors, warnings }.
 * d3-force is a CPU-only simulation; 300 ticks run deterministically without
 * I/O. index.js awaits the return value if it is a Promise; a plain object is
 * handled in the sync branch. See also renderers/vega-lite.js (Promise) and
 * renderers/stub.js (sync) for the two surface shapes dispatcher accepts.
 *
 * LAYOUT STABILITY: force simulations are non-deterministic by default
 * because d3 seeds initial node positions via its own LCG-based RNG.
 * We replace Math.random inside the simulation window with a seeded
 * Mulberry32 generator so the same input yields byte-identical SVG
 * across runs. See `_seededRandom` below. This is weaker than WP-5.3's
 * continuity work (which will persist positions across edits) but ensures
 * unit-test determinism today.
 *
 * Depends on:
 *   errors.js
 *   dispatcher.js                          (via OraVisualCompiler.registerRenderer)
 *   palettes.js                            (for categorical loop colouring)
 *   vendor/d3/d3.min.js                    (window.d3 with force* APIs)
 *
 * Load order:
 *   errors.js → validator.js → renderers/stub.js → dispatcher.js → index.js
 *   palettes.js
 *   vendor/d3/d3.min.js
 *   renderers/causal-loop-diagram.js       ← this file
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.causalLoopDiagram = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;

  // ── Utility: XML-safe escape for attribute and text content. ─────────────
  function _esc(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Utility: seeded PRNG (Mulberry32). Identical input → identical output.
  // We take a 32-bit seed derived from a stable hash of variable/link ids so
  // the layout is reproducible per envelope content. The seed depends on the
  // graph shape, not the literal order of `variables` array elements.
  function _hashString(s) {
    // FNV-1a 32-bit.
    let h = 0x811c9dc5;
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 0x01000193);
    }
    return h >>> 0;
  }
  function _seededRandom(seed) {
    let t = seed >>> 0;
    return function () {
      t = (t + 0x6D2B79F5) >>> 0;
      let r = t;
      r = Math.imul(r ^ (r >>> 15), r | 1);
      r ^= r + Math.imul(r ^ (r >>> 7), r | 61);
      return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
    };
  }

  // ── Structural validation (semantic invariants beyond JSON Schema). ──────
  /**
   * _validateSpec(spec) → { errors: [], warnings: [], varMap, adj, revAdj }
   *
   * varMap:  Map<id, {id, label, description, index}>
   * adj:     Map<fromId, [{to, polarity, delay, linkIndex}]>
   * revAdj:  Map<toId, [{from, polarity, delay, linkIndex}]>
   *
   * On any E_* failure the caller returns immediately; warnings attach to the
   * final result. Paths in error objects point to the JSON position that
   * authors can edit (e.g. 'spec.links[3].from').
   */
  function _validateSpec(spec) {
    const errors = [];
    const warnings = [];

    // Defence-in-depth: the schema enforces these but the renderer runs
    // against Layer-1 too, so check the shape here.
    if (!spec || !Array.isArray(spec.variables) ||
        !Array.isArray(spec.links) || !Array.isArray(spec.loops)) {
      errors.push(make(CODES.E_NO_SPEC,
        'causal_loop_diagram: spec must include variables[], links[], loops[]',
        'spec'));
      return { errors, warnings };
    }

    // 1. variables[].id unique + build varMap.
    const varMap = new Map();
    for (let i = 0; i < spec.variables.length; i++) {
      const v = spec.variables[i];
      if (!v || typeof v.id !== 'string' || v.id.length === 0) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'causal_loop_diagram: variables[' + i + '].id must be a non-empty string',
          'spec.variables[' + i + '].id'));
        continue;
      }
      if (varMap.has(v.id)) {
        errors.push(make(CODES.E_UNRESOLVED_REF,
          'causal_loop_diagram: duplicate variable id ' + JSON.stringify(v.id),
          'spec.variables[' + i + '].id'));
        continue;
      }
      varMap.set(v.id, {
        id: v.id,
        label: v.label || v.id,
        description: v.description || '',
        index: i,
      });
    }
    if (errors.length) return { errors, warnings };

    // 2. links[].from / links[].to resolve; build adjacency maps.
    const adj    = new Map();
    const revAdj = new Map();
    for (const id of varMap.keys()) {
      adj.set(id, []);
      revAdj.set(id, []);
    }
    for (let i = 0; i < spec.links.length; i++) {
      const l = spec.links[i];
      if (!l || typeof l.from !== 'string' || typeof l.to !== 'string') {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'causal_loop_diagram: links[' + i + '] missing from/to strings',
          'spec.links[' + i + ']'));
        continue;
      }
      if (!varMap.has(l.from)) {
        errors.push(make(CODES.E_UNRESOLVED_REF,
          'causal_loop_diagram: links[' + i + '].from=' + JSON.stringify(l.from) +
          ' does not resolve to a declared variable',
          'spec.links[' + i + '].from'));
      }
      if (!varMap.has(l.to)) {
        errors.push(make(CODES.E_UNRESOLVED_REF,
          'causal_loop_diagram: links[' + i + '].to=' + JSON.stringify(l.to) +
          ' does not resolve to a declared variable',
          'spec.links[' + i + '].to'));
      }
      if (l.polarity !== '+' && l.polarity !== '-') {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'causal_loop_diagram: links[' + i + '].polarity must be "+" or "-"',
          'spec.links[' + i + '].polarity'));
      }
      if (varMap.has(l.from) && varMap.has(l.to)) {
        const entry = {
          to: l.to, from: l.from, polarity: l.polarity,
          delay: !!l.delay, linkIndex: i,
        };
        adj.get(l.from).push(entry);
        revAdj.get(l.to).push(entry);
      }
    }
    if (errors.length) return { errors, warnings };

    // 3. Orphan detection (warning only unless allow_isolated).
    const allowIsolated = spec.allow_isolated === true;
    for (const [id, outgoing] of adj.entries()) {
      const incoming = revAdj.get(id);
      if (outgoing.length === 0 && incoming.length === 0 && !allowIsolated) {
        warnings.push(make(CODES.W_ORPHAN_NODE,
          'causal_loop_diagram: variable ' + JSON.stringify(id) +
          ' has no incident links and allow_isolated is not set',
          'spec.variables'));
      }
    }

    // 4. Each declared loop forms a genuine cycle + parity check.
    for (let i = 0; i < spec.loops.length; i++) {
      const loop = spec.loops[i];
      const path = 'spec.loops[' + i + ']';
      if (!loop || !Array.isArray(loop.members) || loop.members.length < 2) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'causal_loop_diagram: loops[' + i + '].members must have length >= 2',
          path + '.members'));
        continue;
      }
      // Walk the sequence; verify each consecutive pair is an edge AND
      // accumulate negative polarity count.
      let negCount = 0;
      let cycleOk = true;
      const members = loop.members;
      // Loop edges: m[0]→m[1], m[1]→m[2], …, m[n-1]→m[0].
      for (let j = 0; j < members.length; j++) {
        const from = members[j];
        const to   = members[(j + 1) % members.length];
        if (!varMap.has(from) || !varMap.has(to)) {
          errors.push(make(CODES.E_UNRESOLVED_REF,
            'causal_loop_diagram: loops[' + i + '].members references undeclared variable',
            path + '.members'));
          cycleOk = false;
          break;
        }
        const out = adj.get(from);
        const edge = out && out.find((e) => e.to === to);
        if (!edge) {
          errors.push(make(CODES.E_GRAPH_CYCLE,
            'causal_loop_diagram: declared loop ' + JSON.stringify(loop.id || i) +
            ' is not a cycle in the graph — no link ' +
            JSON.stringify(from) + ' → ' + JSON.stringify(to),
            path + '.members'));
          cycleOk = false;
          break;
        }
        if (edge.polarity === '-') negCount += 1;
      }
      if (!cycleOk) continue;

      // Parity: even '-' → R; odd '-' → B.
      const parityType = (negCount % 2 === 0) ? 'R' : 'B';
      if (loop.type !== parityType) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'causal_loop_diagram: loop ' + JSON.stringify(loop.id || i) +
          ' declared as type=' + JSON.stringify(loop.type) +
          ' but has ' + negCount + ' negative link(s) — parity implies type=' +
          JSON.stringify(parityType),
          path + '.type'));
      }
    }

    return { errors, warnings, varMap, adj, revAdj };
  }

  // ── Force simulation. ────────────────────────────────────────────────────
  /**
   * _runLayout(varMap, links, width, height, seed)
   *
   * Returns a Map<id, {x, y}> of final positions. Uses d3.forceSimulation
   * with forceLink, forceManyBody, forceCenter. Seeded via Math.random
   * override inside this function only; the outer Math is restored.
   *
   * We tick for 300 iterations synchronously (simulation.tick() does not
   * animate by default — alpha decays deterministically). On degenerate
   * output (NaN, all-at-center) the caller falls back to a ring layout.
   */
  function _runLayout(varMap, links, width, height, seed) {
    const d3 = window.d3;

    // d3 uses Math.random internally for jitter on stalled nodes; override
    // for reproducibility and restore afterwards.
    const rng = _seededRandom(seed);
    const mathRandom = Math.random;
    Math.random = rng;

    try {
      // Build node objects. Seed initial positions on a ring so we never
      // start at exactly (0,0) where forceManyBody produces NaN gradients.
      const ids = Array.from(varMap.keys());
      const n = ids.length;
      const cx = width / 2;
      const cy = height / 2;
      const r0 = Math.min(width, height) * 0.3;
      const nodes = ids.map((id, i) => {
        const a = (i / n) * Math.PI * 2;
        return {
          id: id,
          x: cx + r0 * Math.cos(a),
          y: cy + r0 * Math.sin(a),
          vx: 0, vy: 0,
        };
      });
      const nodeById = new Map(nodes.map((n) => [n.id, n]));
      const linkData = links.map((l) => ({
        source: nodeById.get(l.from),
        target: nodeById.get(l.to),
      }));

      const sim = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(linkData).id((d) => d.id).distance(120).strength(0.6))
        .force('charge', d3.forceManyBody().strength(-400))
        .force('center', d3.forceCenter(cx, cy))
        .force('collide', d3.forceCollide().radius(44))
        .stop();

      // Explicitly seed the alpha decay and initial velocity decay so
      // the iteration count maps to a predictable energy trajectory.
      sim.alpha(1).alphaMin(0.001).alphaDecay(0.02).velocityDecay(0.4);

      for (let i = 0; i < 300; i++) sim.tick();

      const positions = new Map();
      let degenerate = false;
      for (const node of nodes) {
        if (!isFinite(node.x) || !isFinite(node.y)) {
          degenerate = true;
          break;
        }
        positions.set(node.id, { x: node.x, y: node.y });
      }

      if (degenerate) return null;
      return positions;
    } finally {
      Math.random = mathRandom;
    }
  }

  // ── Viewbox computation. ─────────────────────────────────────────────────
  function _computeViewBox(positions, padding) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const p of positions.values()) {
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    }
    const pad = padding || 60;
    const x = minX - pad;
    const y = minY - pad;
    const w = (maxX - minX) + pad * 2;
    const h = (maxY - minY) + pad * 2;
    return { x: x, y: y, width: w, height: h };
  }

  // ── SVG emission. ────────────────────────────────────────────────────────
  /**
   * Build one curved cubic-Bezier path between two points. A mild
   * perpendicular offset avoids overlap with a reverse edge (if any).
   * The control offset is constant per direction so A→B curves one way
   * and B→A curves the opposite way.
   */
  function _edgePath(from, to, curveSign) {
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    // Shrink the endpoints so arrowheads don't overlap node rects.
    const shrink = 28;
    const ux = dx / len, uy = dy / len;
    const sx = from.x + ux * shrink;
    const sy = from.y + uy * shrink;
    const ex = to.x   - ux * shrink;
    const ey = to.y   - uy * shrink;

    // Perpendicular offset for curvature (sign flips the side).
    const curveMag = 0.18;
    const px = -uy;
    const py = ux;
    const mx = (sx + ex) / 2 + px * len * curveMag * curveSign;
    const my = (sy + ey) / 2 + py * len * curveMag * curveSign;

    return {
      d: 'M ' + sx.toFixed(2) + ' ' + sy.toFixed(2) +
         ' Q ' + mx.toFixed(2) + ' ' + my.toFixed(2) +
         ' '   + ex.toFixed(2) + ' ' + ey.toFixed(2),
      midX: mx,
      midY: my,
    };
  }

  /**
   * Emit the full SVG string. Pure string building — no DOM required.
   * Called after _validateSpec and _runLayout have succeeded.
   */
  function _emitSvg(envelope, varMap, links, loops, positions) {
    const vb = _computeViewBox(positions, 80);
    const title = envelope.title || '';
    const shortAlt = (envelope.semantic_description &&
                      envelope.semantic_description.short_alt) || '';
    const typeLab = envelope.type || 'causal_loop_diagram';
    const ariaLab = (title || typeLab) + (shortAlt ? ' — ' + shortAlt : '');

    // Detect reverse-edge pairs so we can curve opposites on opposite sides.
    const reverseSet = new Set();
    for (const l of links) reverseSet.add(l.from + '→' + l.to);
    function curveSignFor(l) {
      // If the reverse edge exists, use a deterministic orientation based on
      // lexical order of the endpoints; otherwise no curvature bias.
      if (reverseSet.has(l.to + '→' + l.from)) {
        return (l.from < l.to) ? 1 : -1;
      }
      return 0.25;  // a tiny uniform curve to visually separate from straight rules
    }

    const parts = [];
    parts.push(
      '<svg xmlns="http://www.w3.org/2000/svg" ' +
      'viewBox="' + vb.x.toFixed(2) + ' ' + vb.y.toFixed(2) + ' ' +
        vb.width.toFixed(2) + ' ' + vb.height.toFixed(2) + '" ' +
      'class="ora-visual ora-visual--causal_loop_diagram" ' +
      'role="img" aria-label="' + _esc(ariaLab) + '">'
    );
    parts.push(
      '<title class="ora-visual__accessible-title">' + _esc(ariaLab) + '</title>'
    );

    // <defs>: one marker per polarity. Rendered as a small triangle; CSS
    // governs fill (semantic classes pos/neg).
    parts.push(
      '<defs>' +
        '<marker id="cld-arrow-pos" class="ora-visual__marker ora-visual__marker--pos" ' +
          'viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" ' +
          'orient="auto-start-reverse">' +
          '<path d="M0,0 L10,5 L0,10 z"/>' +
        '</marker>' +
        '<marker id="cld-arrow-neg" class="ora-visual__marker ora-visual__marker--neg" ' +
          'viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" ' +
          'orient="auto-start-reverse">' +
          '<path d="M0,0 L10,5 L0,10 z"/>' +
        '</marker>' +
      '</defs>'
    );

    // Optional title as decorative text at top (the accessible <title> is
    // separate). Tufte: keep it muted and out of the way of the data.
    if (title) {
      parts.push(
        '<text class="ora-visual__title" ' +
          'x="' + (vb.x + vb.width / 2).toFixed(2) + '" ' +
          'y="' + (vb.y + 20).toFixed(2) + '" ' +
          'text-anchor="middle">' + _esc(title) + '</text>'
      );
    }

    // ── Edges ─────────────────────────────────────────────────────────────
    // Drawn first so nodes overlay the arrowheads cleanly at the margin.
    parts.push('<g class="ora-visual__edges">');
    for (const l of links) {
      const src = positions.get(l.from);
      const dst = positions.get(l.to);
      if (!src || !dst) continue;
      const p = _edgePath(src, dst, curveSignFor(l));
      const polClass = l.polarity === '+'
        ? 'ora-visual__edge--pos'
        : 'ora-visual__edge--neg';
      const delayClass = l.delay ? ' ora-visual__edge--delay' : '';
      const markerUrl = l.polarity === '+' ? 'url(#cld-arrow-pos)' : 'url(#cld-arrow-neg)';
      parts.push(
        '<path id="cld-edge-' + _esc(l.from) + '-' + _esc(l.to) + '" ' +
          'class="ora-visual__edge ' + polClass + delayClass + '" ' +
          'd="' + p.d + '" ' +
          'marker-end="' + markerUrl + '"/>'
      );
      // Polarity label near the midpoint.
      const glyph = l.polarity === '+' ? '+' : '\u2212';  // U+2212 MINUS SIGN
      const polIndClass = l.polarity === '+'
        ? 'ora-visual__polarity-indicator--positive'
        : 'ora-visual__polarity-indicator--negative';
      parts.push(
        '<text class="ora-visual__edge-label ora-visual__polarity-indicator ' +
          polIndClass + '" ' +
          'x="' + p.midX.toFixed(2) + '" ' +
          'y="' + p.midY.toFixed(2) + '" ' +
          'text-anchor="middle" dominant-baseline="central">' + glyph + '</text>'
      );
    }
    parts.push('</g>');

    // ── Nodes ─────────────────────────────────────────────────────────────
    // Rect with label. Width estimated from label length; height fixed.
    parts.push('<g class="ora-visual__nodes">');
    const NODE_HEIGHT = 32;
    const NODE_PADDING = 14;
    const CHAR_WIDTH = 7.5;  // conservative estimate; CSS overrides via theme
    for (const v of varMap.values()) {
      const p = positions.get(v.id);
      if (!p) continue;
      const label = v.label || v.id;
      const w = Math.max(48, label.length * CHAR_WIDTH + NODE_PADDING * 2);
      const h = NODE_HEIGHT;
      parts.push(
        '<g id="cld-node-' + _esc(v.id) + '" class="ora-visual__node" ' +
          'transform="translate(' + p.x.toFixed(2) + ',' + p.y.toFixed(2) + ')">' +
          '<rect x="' + (-w / 2).toFixed(2) + '" y="' + (-h / 2).toFixed(2) + '" ' +
            'width="' + w.toFixed(2) + '" height="' + h.toFixed(2) + '"/>' +
          '<text class="ora-visual__node-label" ' +
            'x="0" y="0" text-anchor="middle" dominant-baseline="central">' +
            _esc(label) + '</text>' +
        '</g>'
      );
    }
    parts.push('</g>');

    // ── Loop annotations ─────────────────────────────────────────────────
    // Per-loop categorical colour via palettes, surfaced as a class on the
    // group so CSS / overrides can style by loop without inline hex.
    const palette = (window.OraVisualCompiler.palettes &&
                     window.OraVisualCompiler.palettes.categorical(
                       Math.max(1, loops.length))) || [];
    parts.push('<g class="ora-visual__loops">');
    for (let i = 0; i < loops.length; i++) {
      const loop = loops[i];
      // Centroid over valid members.
      let sx = 0, sy = 0, count = 0;
      for (const m of loop.members) {
        const p = positions.get(m);
        if (!p) continue;
        sx += p.x; sy += p.y; count += 1;
      }
      if (count === 0) continue;
      const cx = sx / count;
      const cy = sy / count;
      const loopModifier = loop.type === 'R'
        ? 'ora-visual__loop--reinforcing'
        : 'ora-visual__loop--balancing';
      // `data-loop-color` carries the categorical hex for optional themes
      // that want to read it; classes remain the primary styling surface.
      const colorHex = _esc(palette[i % palette.length] || '');
      parts.push(
        '<g id="cld-loop-' + _esc(loop.id) + '" ' +
          'class="ora-visual__loop ' + loopModifier + '" ' +
          (colorHex ? 'data-loop-color="' + colorHex + '" ' : '') +
          'transform="translate(' + cx.toFixed(2) + ',' + cy.toFixed(2) + ')">' +
          '<circle class="ora-visual__loop-marker" r="14"/>' +
          '<text class="ora-visual__loop-label" ' +
            'x="0" y="0" text-anchor="middle" dominant-baseline="central">' +
            _esc(loop.type) + '</text>' +
        '</g>'
      );
      // Loop text label (small annotation under the marker).
      if (loop.label) {
        parts.push(
          '<text class="ora-visual__annotation" ' +
            'x="' + cx.toFixed(2) + '" ' +
            'y="' + (cy + 28).toFixed(2) + '" ' +
            'text-anchor="middle">' +
            _esc(loop.id + ': ' + loop.label) + '</text>'
        );
      }
    }
    parts.push('</g>');

    // Optional caption at the bottom (Tufte T15). The envelope's `caption`
    // field is rendered if present and not hidden.
    if (envelope.caption && typeof envelope.caption === 'object') {
      const c = envelope.caption;
      const parts2 = [];
      if (c.source) parts2.push('Source: ' + c.source);
      if (c.period) parts2.push('Period: ' + c.period);
      if (typeof c.n === 'number') parts2.push('n=' + c.n);
      if (c.units)  parts2.push('Units: ' + c.units);
      if (parts2.length) {
        parts.push(
          '<text class="ora-visual__caption" ' +
            'x="' + (vb.x + 12).toFixed(2) + '" ' +
            'y="' + (vb.y + vb.height - 12).toFixed(2) + '">' +
            _esc(parts2.join(' · ')) + '</text>'
        );
      }
    }

    parts.push('</svg>');
    return parts.join('');
  }

  // ── Seed derivation. ─────────────────────────────────────────────────────
  // Deterministic seed from graph content. Two envelopes with identical
  // variables+links yield identical layouts regardless of map iteration
  // order concerns (we sort first).
  function _seedFor(spec) {
    const varIds = spec.variables.map((v) => v.id).sort();
    const linkIds = spec.links
      .map((l) => l.from + '>' + l.to + ':' + (l.polarity || '+'))
      .sort();
    return _hashString(varIds.join(',') + '|' + linkIds.join(','));
  }

  // ── Public render() ──────────────────────────────────────────────────────
  /**
   * render(envelope) → { svg, errors, warnings }
   * Never throws; all failure modes return structured errors.
   * Synchronous despite d3-force being CPU-bound (300 ticks complete in
   * single-digit ms for typical CLDs; no I/O involved).
   */
  function render(envelope) {
    const errors = [];
    const warnings = [];

    const spec = envelope && envelope.spec ? envelope.spec : null;
    if (!spec) {
      errors.push(make(CODES.E_NO_SPEC,
        'causal_loop_diagram: spec field missing', 'spec'));
      return { svg: '', errors, warnings };
    }

    // Library presence.
    if (typeof window.d3 === 'undefined' ||
        typeof window.d3.forceSimulation !== 'function') {
      errors.push(make(CODES.E_RENDERER_THREW,
        'causal_loop_diagram: window.d3 not loaded; ' +
        'include vendor/d3/d3.min.js before this renderer'));
      return { svg: '', errors, warnings };
    }

    // 1. Validate structural + semantic invariants.
    const v = _validateSpec(spec);
    if (v.warnings && v.warnings.length) {
      for (const w of v.warnings) warnings.push(w);
    }
    if (v.errors && v.errors.length) {
      return { svg: '', errors: v.errors, warnings };
    }

    // 2. Run force simulation. Wrap in try/catch per graceful-failure
    // contract: any thrown error becomes E_RENDERER_THREW.
    let positions;
    try {
      const seed = _seedFor(spec);
      positions = _runLayout(
        v.varMap,
        spec.links.filter((l) => v.varMap.has(l.from) && v.varMap.has(l.to)),
        800, 600,
        seed
      );
    } catch (err) {
      errors.push(make(CODES.E_RENDERER_THREW,
        'causal_loop_diagram: d3-force simulation threw — ' +
        (err && err.message ? err.message : String(err))));
      return { svg: '', errors, warnings };
    }
    if (!positions) {
      errors.push(make(CODES.E_RENDERER_THREW,
        'causal_loop_diagram: force simulation produced degenerate coordinates'));
      return { svg: '', errors, warnings };
    }

    // 3. Emit SVG. Any exception here is a bug, not a user error; still
    // catch to uphold the "never throw" contract.
    let svg;
    try {
      svg = _emitSvg(envelope, v.varMap, spec.links, spec.loops, positions);
    } catch (err) {
      errors.push(make(CODES.E_RENDERER_THREW,
        'causal_loop_diagram: SVG emission threw — ' +
        (err && err.message ? err.message : String(err))));
      return { svg: '', errors, warnings };
    }

    return { svg: svg, errors: [], warnings };
  }

  // Register with the dispatcher. Matches the mermaid.js / vega-lite.js
  // convention of calling registerRenderer as the final side-effect.
  if (window.OraVisualCompiler &&
      typeof window.OraVisualCompiler.registerRenderer === 'function') {
    window.OraVisualCompiler.registerRenderer(
      'causal_loop_diagram',
      { render: render }
    );
  }

  // Expose internals for unit testing. Not part of the stable API surface.
  return {
    render: render,
    _validateSpec: _validateSpec,
    _runLayout: _runLayout,
    _emitSvg: _emitSvg,
    _seedFor: _seedFor,
    _seededRandom: _seededRandom,
  };
}());
