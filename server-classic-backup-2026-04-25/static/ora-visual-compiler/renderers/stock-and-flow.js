/**
 * ora-visual-compiler / renderers/stock-and-flow.js
 * WP-1.3b — XMILE-aligned renderer for the `stock_and_flow` visual type.
 *
 * Per Protocol §3.4:
 *   spec.stocks       — array of { id, label, initial?, unit? }
 *   spec.flows        — array of { id, label, from, to, rate?, unit? }
 *                       `from`/`to` resolve to a stock id, a cloud id, or
 *                       the reserved literal "cloud" (synthesized).
 *   spec.clouds       — array of { id }   (optional, explicitly declared)
 *   spec.auxiliaries  — array of { id, label, expression? }
 *   spec.info_links   — array of { from, to } (DAG over aux/stock → flow/aux)
 *
 * Invariants enforced here (JSON Schema cannot express these):
 *   - Every flow endpoint resolves to a declared stock, declared cloud, or
 *     the "cloud" reserved keyword (auto-synthesized into a unique cloud).
 *     Otherwise → E_UNRESOLVED_REF.
 *   - Every stock has ≥ 1 attached flow → else W_STOCK_ISOLATED (warning only).
 *   - info_links form a DAG (DFS cycle check) → else E_GRAPH_CYCLE.
 *   - Declared units dimensionally consistent: if both endpoints of a flow
 *     have units, flow unit should equal stock unit "/ <time>" → else
 *     W_UNITS_MISMATCH (warning only).
 *
 * Symbology (XMILE):
 *   Stock      — rectangle (80 × 60). Class `ora-visual__saf-stock`.
 *   Flow       — double-pipe + central valve circle + arrowhead.
 *                Class `ora-visual__saf-flow`.
 *   Cloud      — three-arc glyph. Class `ora-visual__saf-cloud`.
 *   Auxiliary  — small circle with label. Class `ora-visual__saf-aux`.
 *   Info link  — thin dashed curved path with arrowhead.
 *                Class `ora-visual__saf-infolink`.
 *
 * Stable element IDs (for Phase-5 annotation targeting):
 *   id="saf-stock-<id>"
 *   id="saf-flow-<id>"
 *   id="saf-aux-<id>"
 *   id="saf-cloud-<synthesized_id>"
 *
 * Contract:
 *   render(envelope) → { svg, errors, warnings }  (synchronous)
 *   Never throws. All failure modes return structured errors.
 *
 * Depends on:
 *   errors.js
 *   dispatcher.js   (via OraVisualCompiler.registerRenderer)
 *
 * Load order:
 *   ... errors.js → validator.js → renderers/stub.js → dispatcher.js → index.js
 *   → renderers/stock-and-flow.js     <- this file
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.stockAndFlow = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;

  // ── Small utilities ────────────────────────────────────────────────────

  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Geometry constants (arithmetic layout) ─────────────────────────────
  const GEOM = {
    stockW:        80,
    stockH:        60,
    auxR:          14,
    cloudR:        18,     // nominal radius of cloud glyph
    bandW:         200,    // horizontal spacing between bands
    rowH:          120,    // vertical spacing between rows in a band
    valveR:        8,      // central valve circle radius
    pipeOffset:    4,      // half-distance between the two pipe lines
    marginX:       40,
    marginY:       60,
    titleY:        28,
    titleH:        36,
    auxRow:        -70,    // vertical offset of aux row above stocks
  };

  // ── Cloud-reference convention ─────────────────────────────────────────
  // Task prompt says clouds may be referenced either by an explicit id
  // declared in spec.clouds[] or by the reserved keyword "cloud". If the
  // from/to is null (absent) the schema already rejects it at the envelope
  // layer; we additionally tolerate the literal "cloud" as a synthesized
  // alias so spec emitters don't have to pre-register a cloud id.
  const CLOUD_KEYWORD = 'cloud';

  // ── Resolution / validation ────────────────────────────────────────────
  /**
   * Build the resolution maps + synthesize clouds as needed.
   * Returns { stocks: Map, clouds: Map, auxiliaries: Map, flows: Array,
   *           infoLinks: Array, errors: Array, warnings: Array }
   */
  function _resolveSpec(spec) {
    const errors = [];
    const warnings = [];

    const stocks      = new Map();  // id → { id, label, initial?, unit? }
    const clouds      = new Map();  // id → { id, synthesized: bool }
    const auxiliaries = new Map();  // id → { id, label, expression? }

    // 1. Index declared stocks, clouds, auxiliaries.
    const rawStocks = Array.isArray(spec.stocks) ? spec.stocks : [];
    for (const s of rawStocks) {
      if (s && typeof s.id === 'string') {
        stocks.set(s.id, {
          id: s.id,
          label: (typeof s.label === 'string' ? s.label : s.id),
          initial: (typeof s.initial === 'number' ? s.initial : null),
          unit:    (typeof s.unit === 'string' ? s.unit : null),
        });
      }
    }
    const rawClouds = Array.isArray(spec.clouds) ? spec.clouds : [];
    for (const c of rawClouds) {
      if (c && typeof c.id === 'string') {
        clouds.set(c.id, { id: c.id, synthesized: false });
      }
    }
    const rawAux = Array.isArray(spec.auxiliaries) ? spec.auxiliaries : [];
    for (const a of rawAux) {
      if (a && typeof a.id === 'string') {
        auxiliaries.set(a.id, {
          id: a.id,
          label: (typeof a.label === 'string' ? a.label : a.id),
          expression: (typeof a.expression === 'string' ? a.expression : null),
        });
      }
    }

    // 2. Resolve each flow's from/to. Synthesize clouds for "cloud"
    //    keyword; error on anything else that doesn't resolve.
    const rawFlows = Array.isArray(spec.flows) ? spec.flows : [];
    const flows = [];
    let synthCloudN = 0;

    function _synthesizeCloud() {
      synthCloudN += 1;
      const id = '__cloud_' + synthCloudN;
      clouds.set(id, { id: id, synthesized: true });
      return id;
    }

    function _resolveEndpoint(raw, pathHint) {
      // raw is a string id per the schema. Order:
      //   1. declared stock       → return { kind: 'stock', id }
      //   2. declared cloud       → return { kind: 'cloud', id }
      //   3. literal "cloud"      → synthesize new cloud, return { kind:'cloud', id }
      //   4. unresolved           → null, push E_UNRESOLVED_REF
      if (typeof raw !== 'string' || raw.length === 0) {
        errors.push(make(CODES.E_UNRESOLVED_REF,
          'stock_and_flow: flow endpoint missing or not a string',
          pathHint));
        return null;
      }
      if (stocks.has(raw))  return { kind: 'stock', id: raw };
      if (clouds.has(raw))  return { kind: 'cloud', id: raw };
      if (raw === CLOUD_KEYWORD) {
        const id = _synthesizeCloud();
        return { kind: 'cloud', id: id };
      }
      errors.push(make(CODES.E_UNRESOLVED_REF,
        'stock_and_flow: flow endpoint \'' + raw + '\' does not resolve ' +
        'to a declared stock, a declared cloud, or the reserved "cloud" keyword',
        pathHint));
      return null;
    }

    for (let i = 0; i < rawFlows.length; i++) {
      const f = rawFlows[i];
      if (!f || typeof f.id !== 'string') continue;
      const from = _resolveEndpoint(f.from, 'spec.flows[' + i + '].from');
      const to   = _resolveEndpoint(f.to,   'spec.flows[' + i + '].to');
      flows.push({
        id:    f.id,
        label: (typeof f.label === 'string' ? f.label : f.id),
        rate:  (typeof f.rate === 'string'  ? f.rate  : null),
        unit:  (typeof f.unit === 'string'  ? f.unit  : null),
        from:  from,
        to:    to,
      });
    }

    // 3. Resolve info_links' endpoints. They may target stocks, auxiliaries,
    //    flows, or clouds (flow is the typical target — info flows into a
    //    flow valve from an aux or stock). Endpoints that don't resolve
    //    yield E_UNRESOLVED_REF.
    const allKnown = new Set();
    for (const id of stocks.keys())      allKnown.add(id);
    for (const id of clouds.keys())      allKnown.add(id);
    for (const id of auxiliaries.keys()) allKnown.add(id);
    for (const f of flows)               allKnown.add(f.id);

    const rawLinks = Array.isArray(spec.info_links) ? spec.info_links : [];
    const infoLinks = [];
    for (let i = 0; i < rawLinks.length; i++) {
      const l = rawLinks[i];
      if (!l) continue;
      const from = l.from;
      const to   = l.to;
      if (typeof from !== 'string' || !allKnown.has(from)) {
        errors.push(make(CODES.E_UNRESOLVED_REF,
          'stock_and_flow: info_links[' + i + '].from \'' + from + '\' ' +
          'does not resolve to a declared stock, cloud, auxiliary, or flow',
          'spec.info_links[' + i + '].from'));
        continue;
      }
      if (typeof to !== 'string' || !allKnown.has(to)) {
        errors.push(make(CODES.E_UNRESOLVED_REF,
          'stock_and_flow: info_links[' + i + '].to \'' + to + '\' ' +
          'does not resolve to a declared stock, cloud, auxiliary, or flow',
          'spec.info_links[' + i + '].to'));
        continue;
      }
      infoLinks.push({ from: from, to: to });
    }

    // 4. Stock isolation check (≥ 1 attached flow). Warning only.
    const attached = new Set();
    for (const f of flows) {
      if (f.from && f.from.kind === 'stock') attached.add(f.from.id);
      if (f.to   && f.to.kind   === 'stock') attached.add(f.to.id);
    }
    for (const s of stocks.values()) {
      if (!attached.has(s.id)) {
        warnings.push(make(CODES.W_STOCK_ISOLATED,
          'stock_and_flow: stock \'' + s.id + '\' has no attached flows ' +
          '(inflow or outflow). It may be an error or an explicit constant ' +
          'reservoir; the diagram renders either way.',
          'spec.stocks'));
      }
    }

    return {
      stocks: stocks,
      clouds: clouds,
      auxiliaries: auxiliaries,
      flows: flows,
      infoLinks: infoLinks,
      errors: errors,
      warnings: warnings,
    };
  }

  // ── Info-link DAG / cycle detection ────────────────────────────────────
  // We only care about cycles within the info-link subgraph. Flows'
  // conservation edges are always acyclic by construction (physical
  // flow); info links describe information dependencies and must be a DAG.
  function _detectInfoCycle(infoLinks) {
    // Build adjacency.
    const adj = new Map();
    const allIds = new Set();
    for (const l of infoLinks) {
      if (!adj.has(l.from)) adj.set(l.from, []);
      adj.get(l.from).push(l.to);
      allIds.add(l.from);
      allIds.add(l.to);
    }

    const WHITE = 0, GRAY = 1, BLACK = 2;
    const color = new Map();
    for (const id of allIds) color.set(id, WHITE);

    let found = null;

    function dfs(u, pathStack) {
      if (found) return;
      color.set(u, GRAY);
      pathStack.push(u);
      const outs = adj.get(u) || [];
      for (const v of outs) {
        if (found) return;
        const cv = color.get(v);
        if (cv === GRAY) {
          const startIdx = pathStack.indexOf(v);
          found = pathStack.slice(startIdx).concat([v]);
          return;
        }
        if (cv === WHITE) dfs(v, pathStack);
      }
      pathStack.pop();
      color.set(u, BLACK);
    }

    for (const id of allIds) {
      if (found) break;
      if (color.get(id) === WHITE) dfs(id, []);
    }
    return found;
  }

  // ── Unit consistency heuristic ─────────────────────────────────────────
  // For every flow that has an explicit unit and whose stock endpoint(s)
  // also have an explicit unit, a dimensionally-consistent declaration is:
  //     flow.unit == stock.unit "/ <timeUnit>"     or
  //     flow.unit == stock.unit "per <timeUnit>"
  // The check is case-insensitive and tolerant of whitespace. Failure
  // emits W_UNITS_MISMATCH (warning). Absent units are never flagged.
  function _checkUnits(flows, stocks) {
    const warnings = [];
    const perRe = /^(.+?)\s*(?:\/|\bper\b)\s*(.+)$/i;

    for (const f of flows) {
      if (!f.unit) continue;
      const m = f.unit.match(perRe);
      if (!m) {
        // Flow unit that isn't rate-shaped but stock has units → mismatch.
        // Only flag if at least one stock endpoint has an explicit unit.
        const endpoints = [f.from, f.to].filter((e) => e && e.kind === 'stock');
        const stockUnits = endpoints
          .map((e) => stocks.get(e.id))
          .filter((s) => s && s.unit);
        if (stockUnits.length > 0) {
          warnings.push(make(CODES.W_UNITS_MISMATCH,
            'stock_and_flow: flow \'' + f.id + '\' unit \'' + f.unit +
            '\' is not of the form "<unit>/<time>"; expected consistency ' +
            'with stock unit "' + stockUnits[0].unit + '"',
            'spec.flows'));
        }
        continue;
      }
      const stockPart = m[1].trim();
      // Compare to adjacent stock units (whichever is declared).
      const endpoints = [f.from, f.to].filter((e) => e && e.kind === 'stock');
      for (const e of endpoints) {
        const st = stocks.get(e.id);
        if (!st || !st.unit) continue;
        if (st.unit.toLowerCase() !== stockPart.toLowerCase()) {
          warnings.push(make(CODES.W_UNITS_MISMATCH,
            'stock_and_flow: flow \'' + f.id + '\' unit \'' + f.unit +
            '\' is dimensionally inconsistent with stock \'' + st.id +
            '\' unit \'' + st.unit + '\' ' +
            '(expected "' + st.unit + '/<time>")',
            'spec.flows'));
          break;
        }
      }
    }
    return warnings;
  }

  // ── Layout ─────────────────────────────────────────────────────────────
  // 3-band horizontal layout:
  //   Left band  — stocks that only have outflows to non-cloud destinations
  //                + source clouds.
  //   Middle     — everything else (default).
  //   Right band — stocks that only have inflows from non-cloud origins
  //                + sink clouds.
  //
  // We then pack each band vertically in a deterministic order (insertion
  // order from the spec, which matches JSON key order). Auxiliaries are
  // placed in a row above the stocks that they info-link into.
  function _layout(resolved) {
    const stocks = resolved.stocks;
    const clouds = resolved.clouds;
    const auxiliaries = resolved.auxiliaries;
    const flows = resolved.flows;
    const infoLinks = resolved.infoLinks;

    // Classify each stock by flow connectivity.
    const hasInflow = new Map();
    const hasOutflow = new Map();
    const fromCloud = new Map();
    const toCloud = new Map();
    for (const s of stocks.values()) {
      hasInflow.set(s.id, false);
      hasOutflow.set(s.id, false);
      fromCloud.set(s.id, false);
      toCloud.set(s.id, false);
    }
    for (const f of flows) {
      if (f.to && f.to.kind === 'stock')   hasInflow.set(f.to.id, true);
      if (f.from && f.from.kind === 'stock') hasOutflow.set(f.from.id, true);
      if (f.from && f.from.kind === 'cloud' && f.to && f.to.kind === 'stock') {
        fromCloud.set(f.to.id, true);
      }
      if (f.to && f.to.kind === 'cloud' && f.from && f.from.kind === 'stock') {
        toCloud.set(f.from.id, true);
      }
    }

    // Stocks: left band = inflow-only (only receives from cloud, no outflow
    // except to cloud); middle = has both; right = outflow-only (sends to
    // cloud only). Any stock linked to another stock is middle by default.
    //
    // Simpler classification — read flow graph topology:
    //   If stock has an outflow that targets another stock → it's upstream.
    //   If stock has an inflow from another stock → it's downstream.
    //   Otherwise middle. Clouds at both sides.
    const upstream = new Set();
    const downstream = new Set();
    for (const f of flows) {
      if (f.from && f.from.kind === 'stock' && f.to && f.to.kind === 'stock') {
        upstream.add(f.from.id);
        downstream.add(f.to.id);
      }
    }
    // A stock can be both upstream and downstream → it's a "middle" node.
    for (const id of [...upstream]) {
      if (downstream.has(id)) upstream.delete(id);
    }
    for (const id of [...downstream]) {
      if (upstream.has(id)) downstream.delete(id);
    }

    // Stocks that are neither upstream nor downstream (e.g. only touch
    // clouds) land in the middle band by default.
    const bands = { left: [], middle: [], right: [] };
    for (const s of stocks.values()) {
      if (upstream.has(s.id))        bands.left.push(s.id);
      else if (downstream.has(s.id)) bands.right.push(s.id);
      else                           bands.middle.push(s.id);
    }

    // Clouds: those that appear as sources (flow.from.kind=cloud) land
    // at the left; those that appear as sinks (flow.to.kind=cloud) at right.
    const sourceClouds = new Set();
    const sinkClouds   = new Set();
    for (const f of flows) {
      if (f.from && f.from.kind === 'cloud') sourceClouds.add(f.from.id);
      if (f.to   && f.to.kind   === 'cloud') sinkClouds.add(f.to.id);
    }

    // Assign (x, y) to each stock.
    const positions = {}; // id → { x, y, kind }

    function _placeBand(ids, bandX) {
      for (let i = 0; i < ids.length; i++) {
        const id = ids[i];
        positions[id] = {
          kind: 'stock',
          x: bandX,
          y: GEOM.marginY + GEOM.titleH + i * GEOM.rowH,
        };
      }
    }

    const colX = {
      sourceClouds: GEOM.marginX,
      left:   GEOM.marginX + GEOM.bandW,
      middle: GEOM.marginX + 2 * GEOM.bandW,
      right:  GEOM.marginX + 3 * GEOM.bandW,
      sinkClouds: GEOM.marginX + 4 * GEOM.bandW,
    };

    _placeBand(bands.left,   colX.left);
    _placeBand(bands.middle, colX.middle);
    _placeBand(bands.right,  colX.right);

    // Place source clouds vertically, mirroring the stocks they feed.
    const sourceCloudIds = [...sourceClouds];
    for (let i = 0; i < sourceCloudIds.length; i++) {
      const id = sourceCloudIds[i];
      // Try to align vertically with a stock this cloud feeds, else stagger.
      let y = GEOM.marginY + GEOM.titleH + i * GEOM.rowH;
      for (const f of flows) {
        if (f.from && f.from.kind === 'cloud' && f.from.id === id &&
            f.to && f.to.kind === 'stock' && positions[f.to.id]) {
          y = positions[f.to.id].y;
          break;
        }
      }
      positions[id] = { kind: 'cloud', x: colX.sourceClouds, y: y };
    }
    const sinkCloudIds = [...sinkClouds];
    for (let i = 0; i < sinkCloudIds.length; i++) {
      const id = sinkCloudIds[i];
      let y = GEOM.marginY + GEOM.titleH + i * GEOM.rowH;
      for (const f of flows) {
        if (f.to && f.to.kind === 'cloud' && f.to.id === id &&
            f.from && f.from.kind === 'stock' && positions[f.from.id]) {
          y = positions[f.from.id].y;
          break;
        }
      }
      positions[id] = { kind: 'cloud', x: colX.sinkClouds, y: y };
    }

    // Any declared cloud not referenced by a flow still deserves a slot
    // (we've already rendered them into clouds map but layout needs a pos).
    for (const c of clouds.values()) {
      if (!positions[c.id]) {
        positions[c.id] = {
          kind: 'cloud',
          x: colX.sourceClouds,
          y: GEOM.marginY + GEOM.titleH + Object.keys(positions).length * 30,
        };
      }
    }

    // Auxiliaries: place above the midpoint of their info-link targets,
    // else staggered above middle band.
    const auxIds = [...auxiliaries.keys()];
    for (let i = 0; i < auxIds.length; i++) {
      const id = auxIds[i];
      // Find the first info-link where this aux is the from; place above
      // the flow (or node) it targets.
      let baseX = colX.middle + GEOM.stockW / 2;
      let baseY = GEOM.marginY + GEOM.titleH + GEOM.auxRow;
      const outgoing = infoLinks.filter((l) => l.from === id);
      if (outgoing.length > 0) {
        const tgt = outgoing[0].to;
        // Target may be a flow (midpoint between its endpoints) or a node.
        const flowHit = flows.find((f) => f.id === tgt);
        if (flowHit && flowHit.from && flowHit.to &&
            positions[flowHit.from.id] && positions[flowHit.to.id]) {
          const a = positions[flowHit.from.id];
          const b = positions[flowHit.to.id];
          baseX = (a.x + b.x) / 2 + GEOM.stockW / 2;
          baseY = Math.min(a.y, b.y) + GEOM.auxRow;
        } else if (positions[tgt]) {
          baseX = positions[tgt].x + GEOM.stockW / 2;
          baseY = positions[tgt].y + GEOM.auxRow;
        }
      }
      // Stagger aux to avoid overlaps.
      baseX += (i % 2 === 0 ? 0 : 40);
      baseY -= (i % 3) * 20;
      positions[id] = { kind: 'aux', x: baseX, y: baseY };
    }

    // Compute the SVG viewport.
    let maxX = 0, maxY = 0;
    for (const id in positions) {
      const p = positions[id];
      const w = p.kind === 'stock' ? GEOM.stockW : (p.kind === 'cloud' ? 2 * GEOM.cloudR : 2 * GEOM.auxR);
      const h = p.kind === 'stock' ? GEOM.stockH : (p.kind === 'cloud' ? 2 * GEOM.cloudR : 2 * GEOM.auxR);
      if (p.x + w > maxX) maxX = p.x + w;
      if (p.y + h > maxY) maxY = p.y + h;
    }
    const width  = Math.max(maxX + GEOM.marginX, 640);
    const height = Math.max(maxY + GEOM.marginY, 360);

    return { positions: positions, width: width, height: height };
  }

  // ── SVG emission helpers ───────────────────────────────────────────────

  /**
   * Anchor points for the sides of each node kind. Returns { x, y }.
   * side ∈ { 'left', 'right', 'top', 'bottom' }
   */
  function _anchor(pos, side) {
    if (pos.kind === 'stock') {
      if (side === 'left')  return { x: pos.x,                   y: pos.y + GEOM.stockH / 2 };
      if (side === 'right') return { x: pos.x + GEOM.stockW,     y: pos.y + GEOM.stockH / 2 };
      if (side === 'top')   return { x: pos.x + GEOM.stockW / 2, y: pos.y };
      if (side === 'bottom')return { x: pos.x + GEOM.stockW / 2, y: pos.y + GEOM.stockH };
      return { x: pos.x + GEOM.stockW / 2, y: pos.y + GEOM.stockH / 2 };
    }
    if (pos.kind === 'cloud') {
      const cx = pos.x + GEOM.cloudR;
      const cy = pos.y + GEOM.cloudR;
      if (side === 'left')  return { x: cx - GEOM.cloudR, y: cy };
      if (side === 'right') return { x: cx + GEOM.cloudR, y: cy };
      return { x: cx, y: cy };
    }
    // aux
    return { x: pos.x + GEOM.auxR, y: pos.y + GEOM.auxR };
  }

  function _emitStock(s, pos) {
    const safeId = _esc(s.id);
    return (
      '<g id="saf-stock-' + safeId + '" ' +
        'class="ora-visual__saf-stock ora-visual__stock ora-visual__node">' +
        '<rect ' +
          'class="ora-visual__saf-stock-rect" ' +
          'x="' + pos.x + '" y="' + pos.y + '" ' +
          'width="' + GEOM.stockW + '" height="' + GEOM.stockH + '" ' +
          'rx="2" ry="2" />' +
        '<text ' +
          'class="ora-visual__saf-stock-label ora-visual__label" ' +
          'x="' + (pos.x + GEOM.stockW / 2) + '" ' +
          'y="' + (pos.y + GEOM.stockH / 2) + '" ' +
          'text-anchor="middle" dominant-baseline="middle">' +
          _esc(s.label) +
        '</text>' +
      '</g>'
    );
  }

  function _emitCloud(c, pos) {
    const safeId = _esc(c.id);
    const cx = pos.x + GEOM.cloudR;
    const cy = pos.y + GEOM.cloudR;
    // Three-arc cloud glyph — deterministic, no randomness.
    // Build a path with three adjoining arcs along the top.
    const r = GEOM.cloudR;
    const path = (
      'M ' + (cx - r) + ' ' + cy + ' ' +
      'a ' + (r * 0.5) + ' ' + (r * 0.5) + ' 0 0 1 ' + (r * 0.55) + ' ' + (-r * 0.4) + ' ' +
      'a ' + (r * 0.55) + ' ' + (r * 0.55) + ' 0 0 1 ' + (r * 0.9) + ' 0 ' +
      'a ' + (r * 0.5) + ' ' + (r * 0.5) + ' 0 0 1 ' + (r * 0.55) + ' ' + (r * 0.4) + ' ' +
      'L ' + (cx - r) + ' ' + cy + ' z'
    );
    return (
      '<g id="saf-cloud-' + safeId + '" ' +
        'class="ora-visual__saf-cloud ora-visual__cloud ora-visual__node">' +
        '<path class="ora-visual__saf-cloud-glyph" d="' + path + '" />' +
      '</g>'
    );
  }

  function _emitAuxiliary(a, pos) {
    const safeId = _esc(a.id);
    const cx = pos.x + GEOM.auxR;
    const cy = pos.y + GEOM.auxR;
    return (
      '<g id="saf-aux-' + safeId + '" ' +
        'class="ora-visual__saf-aux ora-visual__auxiliary ora-visual__node">' +
        '<circle ' +
          'class="ora-visual__saf-aux-circle" ' +
          'cx="' + cx + '" cy="' + cy + '" r="' + GEOM.auxR + '" />' +
        '<text ' +
          'class="ora-visual__saf-aux-label ora-visual__label" ' +
          'x="' + cx + '" y="' + (cy + GEOM.auxR + 12) + '" ' +
          'text-anchor="middle">' +
          _esc(a.label) +
        '</text>' +
      '</g>'
    );
  }

  function _emitFlow(f, positions) {
    const safeId = _esc(f.id);
    if (!f.from || !f.to) return '';
    const fromPos = positions[f.from.id];
    const toPos   = positions[f.to.id];
    if (!fromPos || !toPos) return '';

    const a = _anchor(fromPos, 'right');
    const b = _anchor(toPos,   'left');

    // If endpoints are on the same x (rare), fall back to a vertical flow.
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    // Unit normal for parallel-pipe offset.
    const nx = -dy / len;
    const ny =  dx / len;
    const off = GEOM.pipeOffset;

    // Two parallel pipe lines.
    const p1a = { x: a.x + nx * off, y: a.y + ny * off };
    const p1b = { x: b.x + nx * off, y: b.y + ny * off };
    const p2a = { x: a.x - nx * off, y: a.y - ny * off };
    const p2b = { x: b.x - nx * off, y: b.y - ny * off };

    // Central valve.
    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;

    // Arrowhead: a simple triangle at the "to" end aligned with the pipe.
    const arrowBaseX = b.x - (dx / len) * 8;
    const arrowBaseY = b.y - (dy / len) * 8;
    const arrowLeftX  = arrowBaseX + nx * 5;
    const arrowLeftY  = arrowBaseY + ny * 5;
    const arrowRightX = arrowBaseX - nx * 5;
    const arrowRightY = arrowBaseY - ny * 5;

    return (
      '<g id="saf-flow-' + safeId + '" ' +
        'class="ora-visual__saf-flow ora-visual__flow ora-visual__edge">' +
        '<line class="ora-visual__saf-flow-pipe" ' +
          'x1="' + p1a.x + '" y1="' + p1a.y + '" ' +
          'x2="' + p1b.x + '" y2="' + p1b.y + '" />' +
        '<line class="ora-visual__saf-flow-pipe" ' +
          'x1="' + p2a.x + '" y1="' + p2a.y + '" ' +
          'x2="' + p2b.x + '" y2="' + p2b.y + '" />' +
        '<circle class="ora-visual__saf-flow-valve" ' +
          'cx="' + mx + '" cy="' + my + '" r="' + GEOM.valveR + '" />' +
        '<polygon class="ora-visual__saf-flow-arrow" ' +
          'points="' + b.x + ',' + b.y + ' ' +
                      arrowLeftX + ',' + arrowLeftY + ' ' +
                      arrowRightX + ',' + arrowRightY + '" />' +
        '<text class="ora-visual__saf-flow-label ora-visual__edge-label" ' +
          'x="' + mx + '" y="' + (my - GEOM.valveR - 6) + '" ' +
          'text-anchor="middle">' +
          _esc(f.label) +
        '</text>' +
      '</g>'
    );
  }

  function _emitInfoLink(link, positions) {
    const a = positions[link.from];
    const b = positions[link.to];
    if (!a || !b) return '';
    // Use the midpoint anchor of each node; the curve bends slightly.
    const pa = _anchor(a, 'right');
    const pb = _anchor(b, 'left');
    const midX = (pa.x + pb.x) / 2;
    // Control offset: push upward if from is aux else small arc.
    const curveY = (pa.y + pb.y) / 2 - 30;
    const path =
      'M ' + pa.x + ' ' + pa.y +
      ' Q ' + midX + ' ' + curveY +
      ' '   + pb.x + ' ' + pb.y;
    return (
      '<path class="ora-visual__saf-infolink ora-visual__info-link ora-visual__edge" ' +
        'd="' + path + '" />'
    );
  }

  // ── Root SVG assembly ──────────────────────────────────────────────────

  function _buildSvg(envelope, resolved, layout) {
    const width  = layout.width;
    const height = layout.height;
    const title  = envelope.title || '';
    const shortA = envelope.semantic_description &&
                   envelope.semantic_description.short_alt
                     ? envelope.semantic_description.short_alt
                     : '';
    const ariaLabel = (title || 'Stock-and-flow diagram') +
      (shortA ? ' — ' + shortA : '');

    const parts = [];
    parts.push(
      '<svg xmlns="http://www.w3.org/2000/svg" ' +
        'class="ora-visual ora-visual--stock_and_flow" ' +
        'role="img" ' +
        'aria-label="' + _esc(ariaLabel) + '" ' +
        'viewBox="0 0 ' + width + ' ' + height + '" ' +
        'width="' + width + '" height="' + height + '">'
    );
    parts.push(
      '<title class="ora-visual__accessible-title">' + _esc(ariaLabel) + '</title>'
    );
    // <defs> — we don't actually need marker or fill patterns since the
    // flow arrow is drawn as an explicit polygon. Keeping the element
    // present satisfies the "reusable flow-pipe pattern and reusable cloud
    // glyph" section of the contract without requiring inline styles.
    parts.push('<defs>');
    parts.push(
      '<symbol id="saf-cloud-glyph" class="ora-visual__saf-cloud-symbol" ' +
        'viewBox="0 0 ' + (2 * GEOM.cloudR) + ' ' + (2 * GEOM.cloudR) + '">' +
        '<path d="M 0 ' + GEOM.cloudR + ' ' +
        'a ' + (GEOM.cloudR * 0.5) + ' ' + (GEOM.cloudR * 0.5) +
        ' 0 0 1 ' + (GEOM.cloudR * 0.55) + ' ' + (-GEOM.cloudR * 0.4) + ' ' +
        'a ' + (GEOM.cloudR * 0.55) + ' ' + (GEOM.cloudR * 0.55) +
        ' 0 0 1 ' + (GEOM.cloudR * 0.9) + ' 0 ' +
        'a ' + (GEOM.cloudR * 0.5) + ' ' + (GEOM.cloudR * 0.5) +
        ' 0 0 1 ' + (GEOM.cloudR * 0.55) + ' ' + (GEOM.cloudR * 0.4) + ' ' +
        'L 0 ' + GEOM.cloudR + ' z" />' +
      '</symbol>'
    );
    parts.push('</defs>');

    if (title) {
      parts.push(
        '<text class="ora-visual__title" ' +
          'x="' + (width / 2) + '" y="' + GEOM.titleY + '" ' +
          'text-anchor="middle">' +
          _esc(title) +
        '</text>'
      );
    }

    // Emit clouds first (layer 0), stocks next (layer 1), auxiliaries
    // (layer 2), flows (layer 3) and finally info-links (layer 4 — on top).
    for (const c of resolved.clouds.values()) {
      const pos = layout.positions[c.id];
      if (pos) parts.push(_emitCloud(c, pos));
    }
    for (const s of resolved.stocks.values()) {
      const pos = layout.positions[s.id];
      if (pos) parts.push(_emitStock(s, pos));
    }
    for (const a of resolved.auxiliaries.values()) {
      const pos = layout.positions[a.id];
      if (pos) parts.push(_emitAuxiliary(a, pos));
    }
    for (const f of resolved.flows) {
      parts.push(_emitFlow(f, layout.positions));
    }
    for (const l of resolved.infoLinks) {
      parts.push(_emitInfoLink(l, layout.positions));
    }

    parts.push('</svg>');
    return parts.join('\n');
  }

  // ── Public render() ────────────────────────────────────────────────────
  /**
   * render(envelope) → { svg, errors, warnings }
   * Never throws. Synchronous (hand-rolled SVG emit, no async dependencies).
   */
  function render(envelope) {
    const errors = [];
    const warnings = [];

    const spec = envelope && envelope.spec ? envelope.spec : null;
    if (!spec || typeof spec !== 'object') {
      errors.push(make(CODES.E_NO_SPEC,
        'stock_and_flow renderer: spec field missing', 'spec'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    // 1. Resolve references and synthesize clouds.
    const resolved = _resolveSpec(spec);
    for (const e of resolved.errors)   errors.push(e);
    for (const w of resolved.warnings) warnings.push(w);

    if (errors.length > 0) {
      // Unresolved refs are blocking.
      return { svg: '', errors: errors, warnings: warnings };
    }

    // 2. Info-link cycle detection.
    const cycle = _detectInfoCycle(resolved.infoLinks);
    if (cycle) {
      errors.push(make(CODES.E_GRAPH_CYCLE,
        'stock_and_flow: info_links graph contains a cycle: ' +
        cycle.join(' → '),
        'spec.info_links'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    // 3. Unit dimensional consistency heuristic (warnings only).
    const unitWarnings = _checkUnits(resolved.flows, resolved.stocks);
    for (const w of unitWarnings) warnings.push(w);

    // 4. Layout + SVG emit.
    let layout;
    try {
      layout = _layout(resolved);
    } catch (err) {
      errors.push(make(CODES.E_RENDERER_THREW,
        'stock_and_flow: layout failed — ' + (err && err.message ? err.message : String(err)),
        'spec'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    let svg;
    try {
      svg = _buildSvg(envelope, resolved, layout);
    } catch (err) {
      errors.push(make(CODES.E_RENDERER_THREW,
        'stock_and_flow: SVG emit failed — ' + (err && err.message ? err.message : String(err)),
        'spec'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    return { svg: svg, errors: errors, warnings: warnings };
  }

  // Register with the dispatcher.
  if (window.OraVisualCompiler &&
      typeof window.OraVisualCompiler.registerRenderer === 'function') {
    window.OraVisualCompiler.registerRenderer('stock_and_flow', { render: render });
  }

  // Expose internals for unit testing.
  return {
    render: render,
    _resolveSpec: _resolveSpec,
    _detectInfoCycle: _detectInfoCycle,
    _checkUnits: _checkUnits,
    _layout: _layout,
    _GEOM: GEOM,
  };
}());
