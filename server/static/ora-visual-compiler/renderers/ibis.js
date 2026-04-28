/**
 * ora-visual-compiler / renderers/ibis.js
 * WP-1.3i — renderer for the `ibis` (Issue-Based Information System) type.
 *
 * IBIS diagrams record a discussion as a typed graph. Per Protocol §3.12:
 *
 *   Node kinds  : question, idea (a.k.a. position), pro, con
 *   Edge kinds  : responds_to, supports, objects_to, questions
 *
 *   Legal (source_kind, edge_kind, target_kind) triples:
 *     (idea,     responds_to, question)    — an idea proposes an answer
 *     (pro,      supports,    idea)        — an argument for an idea
 *     (con,      objects_to,  idea)        — an argument against an idea
 *     (question, questions,   question)    — sub-question meta-level
 *     (question, questions,   idea)        — question an idea
 *     (question, questions,   pro)         — question a pro argument
 *     (question, questions,   con)         — question a con argument
 *
 *   Any other combination is a blocking E_IBIS_GRAMMAR violation.
 *
 * Invariants enforced here (the JSON Schema cannot express these):
 *   - Every edge is one of the legal triples above
 *   - Every edge's `from` and `to` resolve to a declared node id
 *   - At least one `question` node is present (IBIS is a question-rooted form)
 *
 * Symbology (via Graphviz shape attributes, styled by ora-visual-theme.css):
 *   question — shape=diamond, class ora-visual__node--question
 *   idea     — shape=box,style=rounded, class ora-visual__node--idea
 *   pro      — shape=triangle (apex up), class ora-visual__node--pro
 *   con      — shape=invtriangle (apex down), class ora-visual__node--con
 *
 * Semantic IDs (Phase 5 annotation targets):
 *   question → id="ibis-q-<id>"
 *   idea     → id="ibis-i-<id>"
 *   pro      → id="ibis-pro-<id>"
 *   con      → id="ibis-con-<id>"
 *   edge     → id="ibis-edge-<from>-<to>"
 *
 * IMPORTANT: render() is async (returns a Promise). The dispatcher awaits
 * renderer return values; WP-2.3 awaits compile().
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
 *   renderers/ibis.js           <- this file
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.ibis = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;

  // ── Grammar table ────────────────────────────────────────────────────────
  // Each entry is a (source_kind, edge_kind, target_kind) triple. Anything
  // not present is a blocking grammar violation.
  //
  //   idea --responds_to--> question
  //   pro  --supports-----> idea
  //   con  --objects_to---> idea
  //   question --questions--> {question|idea|pro|con}   (question.questions → any)
  //
  const LEGAL_TRIPLES = [
    ['idea',     'responds_to', 'question'],
    ['pro',      'supports',    'idea'],
    ['con',      'objects_to',  'idea'],
    ['question', 'questions',   'question'],
    ['question', 'questions',   'idea'],
    ['question', 'questions',   'pro'],
    ['question', 'questions',   'con'],
  ];

  // Build a set of stringified triples for O(1) lookup.
  const LEGAL_SET = new Set(
    LEGAL_TRIPLES.map(function (t) { return t.join('|'); })
  );

  // Legal edge-kinds for grammar error messages.
  const EDGE_KINDS = new Set(['responds_to', 'supports', 'objects_to', 'questions']);
  const NODE_KINDS = new Set(['question', 'idea', 'pro', 'con']);

  // Per-kind id prefix used in emitted SVG `id=` attributes.
  const ID_PREFIX = {
    question: 'ibis-q-',
    idea:     'ibis-i-',
    pro:      'ibis-pro-',
    con:      'ibis-con-',
  };

  // ── Small utilities ──────────────────────────────────────────────────────

  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Conservative DOT-literal escape (ids + labels that go inside "...").
  function _dotQ(s) {
    return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
  }

  // ── Grammar validator ────────────────────────────────────────────────────
  /**
   * validateGrammar(nodes, edges) → { errors, nodeById }
   *
   * Exhaustive (does not stop on first violation). Accumulates one
   * E_IBIS_GRAMMAR error per offending edge so the user sees the whole list.
   *
   * Also produces E_UNRESOLVED_REF for edges referencing undeclared ids,
   * and E_SCHEMA_INVALID if no `question` node is present.
   */
  function validateGrammar(nodes, edges) {
    const errors = [];
    const nodeById = new Map();

    // Build id → node map. The JSON schema already enforces required
    // fields and the type enum, but we guard against duplicate ids here
    // because the schema cannot express uniqueness of arbitrary string ids.
    const seen = new Set();
    for (let i = 0; i < nodes.length; i += 1) {
      const n = nodes[i];
      if (!n || typeof n !== 'object') continue;
      if (seen.has(n.id)) {
        errors.push(make(CODES.E_UNRESOLVED_REF,
          'ibis: duplicate node id ' + JSON.stringify(n.id),
          'spec.nodes[' + i + '].id'));
        continue;
      }
      seen.add(n.id);
      nodeById.set(n.id, n);
    }

    // At least one question is required (IBIS is question-rooted).
    let hasQuestion = false;
    for (const n of nodeById.values()) {
      if (n.type === 'question') { hasQuestion = true; break; }
    }
    if (!hasQuestion) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'ibis: at least one node of type "question" is required',
        'spec.nodes'));
    }

    // Validate every edge. Do NOT short-circuit.
    for (let i = 0; i < edges.length; i += 1) {
      const e = edges[i];
      if (!e || typeof e !== 'object') continue;

      const path = 'spec.edges[' + i + ']';

      // Resolve endpoints.
      const fromNode = nodeById.get(e.from);
      const toNode   = nodeById.get(e.to);
      if (!fromNode) {
        errors.push(make(CODES.E_UNRESOLVED_REF,
          'ibis: edge ' + path + '.from references undeclared node id ' +
          JSON.stringify(e.from),
          path + '.from'));
      }
      if (!toNode) {
        errors.push(make(CODES.E_UNRESOLVED_REF,
          'ibis: edge ' + path + '.to references undeclared node id ' +
          JSON.stringify(e.to),
          path + '.to'));
      }
      if (!fromNode || !toNode) continue;

      // Edge-kind must be a recognised IBIS relation.
      if (!EDGE_KINDS.has(e.type)) {
        errors.push(make(CODES.E_IBIS_GRAMMAR,
          'ibis: edge ' + path + ' has unknown edge kind ' +
          JSON.stringify(e.type) + ' (expected one of: ' +
          [...EDGE_KINDS].join(', ') + ')',
          path + '.type'));
        continue;
      }

      // Endpoint node kinds must be recognised (JSON schema enforces, but
      // guard again so we can produce a sharp message on malformed input).
      if (!NODE_KINDS.has(fromNode.type) || !NODE_KINDS.has(toNode.type)) {
        errors.push(make(CODES.E_IBIS_GRAMMAR,
          'ibis: edge ' + path + ' has endpoint with unknown node kind ' +
          '(from.type=' + JSON.stringify(fromNode.type) +
          ', to.type=' + JSON.stringify(toNode.type) + ')',
          path));
        continue;
      }

      const triple = fromNode.type + '|' + e.type + '|' + toNode.type;
      if (!LEGAL_SET.has(triple)) {
        errors.push(make(CODES.E_IBIS_GRAMMAR,
          'ibis: grammar violation on edge ' + path + ': (' +
          fromNode.type + ')' + JSON.stringify(fromNode.id) +
          ' --' + e.type + '--> (' +
          toNode.type + ')' + JSON.stringify(toNode.id) +
          '. Legal patterns: ' +
          'idea.responds_to→question, ' +
          'pro.supports→idea, ' +
          'con.objects_to→idea, ' +
          'question.questions→any.',
          path));
      }
    }

    return { errors: errors, nodeById: nodeById };
  }

  // ── DOT emitter ──────────────────────────────────────────────────────────
  /**
   * emitDot(nodes, edges, envelope) → dot string
   *
   * Pre-condition: grammar already validated (no violations). Nodes are
   * emitted with shape tokens selected by kind; edges get a semantic class
   * derived from their edge kind.
   */
  function emitDot(nodes, edges, envelope) {
    const title = envelope.title || '';

    const lines = [];
    lines.push('digraph OraIbis {');
    lines.push('  rankdir=TB;');
    lines.push('  node [margin="0.18,0.10"];');
    if (title) {
      lines.push('  labelloc="t"; label=' + _dotQ(title) + ';');
    }

    // Emit each node. The class attribute threads through Graphviz into the
    // <g class="..."> wrapping the node in the resulting SVG, so downstream
    // CSS can style by role. IDs are stable and prefix-typed.
    for (const n of nodes) {
      const attrs = [];
      attrs.push('id=' + _dotQ(ID_PREFIX[n.type] + n.id));
      attrs.push('label=' + _dotQ(n.text));

      const classList = ['ora-visual__node', 'ora-visual__node--' + n.type];
      // The task spec also requested `ora-visual__ibis-<kind>` class; add
      // it so either convention resolves. Theme CSS uses the __node--
      // form; both live on the element without conflict.
      classList.push('ora-visual__ibis-' + n.type);
      attrs.push('class=' + _dotQ(classList.join(' ')));

      if (n.type === 'question') {
        attrs.push('shape=diamond');
      } else if (n.type === 'idea') {
        attrs.push('shape=box');
        attrs.push('style=rounded');
      } else if (n.type === 'pro') {
        // Upward-pointing triangle — "supports" apex-up visual metaphor.
        attrs.push('shape=triangle');
      } else if (n.type === 'con') {
        // Downward-pointing triangle — "objects" apex-down.
        attrs.push('shape=invtriangle');
      }

      lines.push('  ' + _dotQ(n.id) + ' [' + attrs.join(', ') + '];');
    }

    // Emit each edge. The edge id uses an IBIS-specific prefix and avoids
    // hyphens in the id segment so Graphviz's HTML-entity escape does not
    // mangle downstream selectors. We still use hyphens in the prefix
    // ("ibis-edge-") which is fine because the entity substitution that
    // happens in attribute positions is handled by dot-engine.js (it
    // decodes the numeric entity back to '-').
    for (const e of edges) {
      const attrs = [];
      attrs.push('id=' + _dotQ('ibis-edge-' + e.from + '-' + e.to));
      attrs.push('label=' + _dotQ(e.type));
      const classList = [
        'ora-visual__edge',
        'ora-visual__edge--' + e.type,
        'ora-visual__ibis-edge--' + e.type,
      ];
      attrs.push('class=' + _dotQ(classList.join(' ')));
      lines.push(
        '  ' + _dotQ(e.from) + ' -> ' + _dotQ(e.to) +
        ' [' + attrs.join(', ') + '];'
      );
    }

    lines.push('}');
    return lines.join('\n');
  }

  // ── Root <svg> wrap (class + ARIA + accessible title) ───────────────────
  function wrapRootSvg(svg, envelope) {
    const title   = envelope.title || '';
    const shortA  = envelope.semantic_description &&
                    envelope.semantic_description.short_alt
                      ? envelope.semantic_description.short_alt
                      : '';
    const typeLab = envelope.type || 'ibis';
    const ariaLab = (title || typeLab) + (shortA ? ' — ' + shortA : '');

    let out = svg.replace(/<svg\b([^>]*?)>/i, function (m, attrs) {
      let classes = ['ora-visual', 'ora-visual--ibis'];
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

    // Insert an accessible <title> as the first child of <svg>. Remove any
    // Graphviz-emitted <title> so ours is authoritative.
    out = out.replace(/<title\b[^>]*>[\s\S]*?<\/title>/i, '');
    out = out.replace(/<svg\b[^>]*>/i, function (openTag) {
      return openTag +
        '<title class="ora-visual__accessible-title">' +
        _esc(ariaLab) + '</title>';
    });

    return out;
  }

  // ── Public render() ──────────────────────────────────────────────────────
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
        'ibis renderer: spec field missing', 'spec'));
      return { svg: '', errors, warnings };
    }

    const nodes = Array.isArray(spec.nodes) ? spec.nodes : null;
    const edges = Array.isArray(spec.edges) ? spec.edges : null;
    if (!nodes) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'ibis: spec.nodes must be an array', 'spec.nodes'));
      return { svg: '', errors, warnings };
    }
    if (!edges) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'ibis: spec.edges must be an array', 'spec.edges'));
      return { svg: '', errors, warnings };
    }
    if (nodes.length < 1) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'ibis: spec.nodes must contain at least one node',
        'spec.nodes'));
      return { svg: '', errors, warnings };
    }

    // 1. Validate grammar exhaustively. Accumulate every violation.
    const gv = validateGrammar(nodes, edges);
    if (gv.errors.length) {
      return { svg: '', errors: gv.errors, warnings };
    }

    // 2. Emit DOT and invoke the shared engine.
    const dot = emitDot(nodes, edges, envelope);

    const engineApi = window.OraVisualCompiler._dotEngine;
    if (!engineApi || typeof engineApi.dotToSvg !== 'function') {
      errors.push(make(CODES.E_RENDERER_THREW,
        'ibis: dot-engine not loaded; cannot render'));
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

    // 3. Wrap root <svg> with the ibis classes + ARIA + accessible title.
    const svg = wrapRootSvg(result.svg, envelope);

    return {
      svg: svg,
      errors: [],
      warnings: warnings.concat(result.warnings || []),
    };
  }

  // Register with the dispatcher.
  if (window.OraVisualCompiler &&
      typeof window.OraVisualCompiler.registerRenderer === 'function') {
    window.OraVisualCompiler.registerRenderer('ibis', { render: render });
  }

  // Expose internals for unit testing.
  return {
    render: render,
    _validateGrammar: validateGrammar,
    _emitDot: emitDot,
    _LEGAL_TRIPLES: LEGAL_TRIPLES,
  };
}());
