/**
 * ora-visual-compiler / renderers/concept-map.js
 * WP-1.3k — renderer for the `concept_map` visual type.
 *
 * Novak concept maps use CXL-shaped propositions: each proposition is a
 * directed, labeled edge  concept_A — {linking phrase} → concept_B .
 * This renderer emits Graphviz DOT with the linking phrase as a dedicated
 * plaintext intermediate node (not an edge label) so the layout engine
 * routes concept → phrase → concept with bent arrows, matching the
 * classic CXL rendering used by dagity.net / CmapTools.
 *
 * Per Protocol §3.14:
 *   spec.focus_question     — string (the guiding question for the map)
 *   spec.concepts[]         — [{ id, label, hierarchy_level }]
 *   spec.linking_phrases[]  — [{ id, text }]
 *   spec.propositions[]     — [{ from_concept, via_phrase, to_concept, is_cross_link? }]
 *
 * Invariants enforced here (the JSON Schema cannot express these):
 *   - Every proposition's from_concept, via_phrase, to_concept resolves to a
 *     declared id in concepts / linking_phrases → else E_UNRESOLVED_REF.
 *   - Soft warning W_NO_CROSS_LINKS when no proposition has is_cross_link:
 *     true (Novak's marker of integrative learning; absence suggests a
 *     thin map).
 *
 * Semantic IDs (for Phase 5 annotation targeting):
 *   - Each concept:  id="cm-concept-<id>"
 *   - Each linking phrase node:  id="cm-phrase-<id>"  (when used)
 *   - Each proposition:  id="cm-prop-<from>-<via>-<to>"
 *
 * DOT engine choice: `dot` (hierarchical top-down). Concept maps have an
 * explicit hierarchy_level per concept; `dot` honors that through rank
 * assignment when we emit  { rank=same; c1; c2 }  subgraphs per level.
 * `neato` would ignore the hierarchy. `dot` is therefore faithful to
 * Novak's top-down organization (most general → most specific).
 *
 * IMPORTANT: render() is async (returns a Promise). The dispatcher awaits
 * renderer return values.
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
 *   renderers/concept-map.js     <- this file
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.conceptMap = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;

  // ── Small utilities ────────────────────────────────────────────────────

  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Conservative DOT-literal escape for ids/labels that go inside "..." in
  // the emitted DOT. Labels can contain spaces; ids come from the schema.
  function _dotQ(s) {
    return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
  }

  // Produce a DOT-safe identifier. Graphviz IDs must match [A-Za-z_][A-Za-z0-9_]*
  // OR be quoted. We always quote to be safe; but for the "node statement name"
  // position we still use a sanitised short token so debug dumps stay readable.
  function _safeId(s) {
    return String(s).replace(/[^A-Za-z0-9_]/g, '_');
  }

  // ── Invariant checks ──────────────────────────────────────────────────
  /**
   * validateReferences(spec) → { errors: [], warnings: [] }
   *
   * Walks spec.propositions, checks that each from_concept / to_concept is a
   * declared concept id, and that via_phrase is a declared linking_phrase id.
   * Emits one E_UNRESOLVED_REF per missing reference.
   *
   * Also emits W_NO_CROSS_LINKS if no proposition has is_cross_link:true.
   */
  function validateReferences(spec) {
    const errors = [];
    const warnings = [];

    const concepts = Array.isArray(spec.concepts) ? spec.concepts : [];
    const phrases  = Array.isArray(spec.linking_phrases) ? spec.linking_phrases : [];
    const props    = Array.isArray(spec.propositions) ? spec.propositions : [];

    const conceptIds = new Set(concepts.map((c) => c && c.id).filter(Boolean));
    const phraseIds  = new Set(phrases.map((p) => p && p.id).filter(Boolean));

    let sawCrossLink = false;

    props.forEach(function (p, i) {
      if (!p || typeof p !== 'object') return;
      const pathPrefix = 'spec.propositions[' + i + ']';

      if (!conceptIds.has(p.from_concept)) {
        errors.push(make(CODES.E_UNRESOLVED_REF,
          'concept_map: proposition.from_concept ' +
          JSON.stringify(p.from_concept) +
          ' is not a declared concept id',
          pathPrefix + '.from_concept'));
      }
      if (!conceptIds.has(p.to_concept)) {
        errors.push(make(CODES.E_UNRESOLVED_REF,
          'concept_map: proposition.to_concept ' +
          JSON.stringify(p.to_concept) +
          ' is not a declared concept id',
          pathPrefix + '.to_concept'));
      }
      if (!phraseIds.has(p.via_phrase)) {
        errors.push(make(CODES.E_UNRESOLVED_REF,
          'concept_map: proposition.via_phrase ' +
          JSON.stringify(p.via_phrase) +
          ' is not a declared linking_phrase id',
          pathPrefix + '.via_phrase'));
      }

      if (p.is_cross_link === true) sawCrossLink = true;
    });

    if (props.length > 0 && !sawCrossLink) {
      warnings.push(make(CODES.W_NO_CROSS_LINKS,
        'concept_map: no proposition has is_cross_link:true. ' +
        'Cross-links are Novak\'s marker of integrative learning; ' +
        'their absence may indicate a thin map.',
        'spec.propositions'));
    }

    return { errors: errors, warnings: warnings };
  }

  // ── Semantic-id helpers ───────────────────────────────────────────────
  function conceptNodeId(cid) {
    return 'cm-concept-' + cid;
  }
  function phraseNodeId(pid) {
    return 'cm-phrase-' + pid;
  }
  function propositionId(from, via, to) {
    return 'cm-prop-' + from + '-' + via + '-' + to;
  }

  // ── DOT generator ─────────────────────────────────────────────────────
  /**
   * specToDot(spec, envelope) → string
   *
   * Emits DOT with:
   *   - Each concept as an ellipse with id=cm-concept-<id> and
   *     class="ora-visual__cm-concept" (+ hierarchy tier class).
   *   - Each linking phrase that is used by at least one proposition is
   *     emitted ONCE as a plaintext intermediate node with
   *     id=cm-phrase-<id> and class="ora-visual__cm-phrase". (An unused
   *     linking_phrase is silently skipped.)
   *   - For propositions that share the same via_phrase we instantiate
   *     separate intermediate nodes (phrase_id + "__" + prop-index) so the
   *     layout routes each proposition through its own bent path. Reusing
   *     a single phrase node for N propositions produces cluttered
   *     many-to-many bundles in Graphviz — the Novak convention is one
   *     phrase instance per proposition.
   *   - Concept → phrase edge:  [dir=none]  (no arrowhead; phrase sits on
   *     the edge line).  Phrase → concept edge:  default (arrowhead) —
   *     together they render as one visually continuous concept → phrase
   *     → concept arc.
   *   - Cross-link propositions add class="ora-visual__cm-edge--cross-link"
   *     and style=dashed on BOTH half-edges.
   *   - hierarchy_level gets applied via  { rank=same; ... }  subgraphs so
   *     concepts at the same level sit on the same horizontal row.
   */
  function specToDot(spec, envelope) {
    const title = envelope.title || '';

    const concepts = Array.isArray(spec.concepts) ? spec.concepts : [];
    const phrases  = Array.isArray(spec.linking_phrases) ? spec.linking_phrases : [];
    const props    = Array.isArray(spec.propositions) ? spec.propositions : [];

    // Index phrases by id so we can resolve display text.
    const phraseById = new Map();
    for (const p of phrases) if (p && p.id) phraseById.set(p.id, p);

    // Group concepts by hierarchy_level for rank=same subgraphs.
    const byLevel = new Map();
    for (const c of concepts) {
      if (!c || typeof c.id !== 'string') continue;
      const lvl = Number.isInteger(c.hierarchy_level) ? c.hierarchy_level : 0;
      if (!byLevel.has(lvl)) byLevel.set(lvl, []);
      byLevel.get(lvl).push(c);
    }

    const lines = [];
    lines.push('digraph OraConceptMap {');
    lines.push('  rankdir=TB;');  // Novak maps are top-down by convention.
    lines.push('  splines=true;');
    lines.push('  nodesep=0.4;');
    lines.push('  ranksep=0.6;');
    lines.push('  node [shape=ellipse, margin="0.15,0.08"];');

    if (title) {
      lines.push('  labelloc="t"; label=' + _dotQ(title) + ';');
    }

    // Emit concepts.
    for (const c of concepts) {
      if (!c || typeof c.id !== 'string') continue;
      const lvl = Number.isInteger(c.hierarchy_level) ? c.hierarchy_level : 0;
      const classList = [
        'ora-visual__cm-concept',
        'ora-visual__cm-concept--level-' + lvl,
      ];
      const attrs = [
        'id=' + _dotQ(conceptNodeId(c.id)),
        'class=' + _dotQ(classList.join(' ')),
        'label=' + _dotQ(c.label || c.id),
        'shape=ellipse',
      ];
      lines.push('  ' + _dotQ(_safeId('c_' + c.id)) +
        ' [' + attrs.join(', ') + '];');
    }

    // Emit one intermediate plaintext phrase node PER proposition (see the
    // design note above).  Key: proposition index.  Each proposition gets
    // its own unique DOT node name so Graphviz doesn't merge them, but the
    // stable semantic id we expose is cm-phrase-<phraseId> (first occurrence
    // wins for annotation targeting; that's the designed behaviour — a
    // phrase is the same concept across propositions).
    // We still give each DOT node a unique id attribute so downstream
    // element tracking doesn't see duplicates in the SVG; we derive that
    // from the proposition itself: cm-phrase-<phraseId>--<propIdx>.
    const propDotMeta = [];  // parallel array: { nodeName, from, to, via, crossLink, propId }
    props.forEach(function (p, i) {
      if (!p || typeof p !== 'object') return;
      const via = p.via_phrase;
      const phrase = phraseById.get(via);
      const text = (phrase && phrase.text) ? phrase.text : via;

      const propDotName = _safeId('p_' + via + '_' + i);
      const propSemanticId = phraseNodeId(via) + (props.length > 1 ? '--' + i : '');

      const classList = ['ora-visual__cm-phrase'];
      if (p.is_cross_link === true) {
        classList.push('ora-visual__cm-phrase--cross-link');
      }

      const attrs = [
        'id=' + _dotQ(propSemanticId),
        'class=' + _dotQ(classList.join(' ')),
        'shape=plaintext',
        'label=' + _dotQ(text),
      ];
      lines.push('  ' + _dotQ(propDotName) +
        ' [' + attrs.join(', ') + '];');

      propDotMeta.push({
        nodeName: propDotName,
        from: p.from_concept,
        to: p.to_concept,
        via: via,
        crossLink: p.is_cross_link === true,
        propIndex: i,
      });
    });

    // Rank-same subgraphs so concepts at the same hierarchy_level align.
    // We only emit these when there are >= 2 concepts at that level;
    // otherwise the subgraph is noise.
    const levels = [...byLevel.keys()].sort((a, b) => a - b);
    for (const lvl of levels) {
      const group = byLevel.get(lvl);
      if (!group || group.length < 2) continue;
      const names = group
        .map((c) => _dotQ(_safeId('c_' + c.id)))
        .join('; ');
      lines.push('  { rank=same; ' + names + '; }');
    }

    // Emit edges:  concept → phrase  (dir=none),  phrase → concept  (arrow).
    propDotMeta.forEach(function (meta) {
      const classBase = ['ora-visual__cm-prop'];
      if (meta.crossLink) classBase.push('ora-visual__cm-edge--cross-link');
      const pid = propositionId(meta.from, meta.via, meta.to);

      // First half: from-concept → phrase node (no arrowhead).
      const attrsA = [
        'id=' + _dotQ(pid + '--in'),
        'class=' + _dotQ(classBase.concat(['ora-visual__cm-prop--in']).join(' ')),
        'dir=none',
      ];
      if (meta.crossLink) attrsA.push('style=dashed');

      lines.push('  ' + _dotQ(_safeId('c_' + meta.from)) + ' -> ' +
        _dotQ(meta.nodeName) + ' [' + attrsA.join(', ') + '];');

      // Second half: phrase node → to-concept (arrowhead).
      const attrsB = [
        'id=' + _dotQ(pid),
        'class=' + _dotQ(classBase.concat(['ora-visual__cm-prop--out']).join(' ')),
      ];
      if (meta.crossLink) attrsB.push('style=dashed');

      lines.push('  ' + _dotQ(meta.nodeName) + ' -> ' +
        _dotQ(_safeId('c_' + meta.to)) + ' [' + attrsB.join(', ') + '];');
    });

    lines.push('}');
    return lines.join('\n');
  }

  // ── Root SVG wrap/decoration ───────────────────────────────────────────
  // dot-engine.js already added `ora-visual` to the root <svg>. Here we
  // extend with `ora-visual--concept_map`, role="img", aria-label, and a
  // semantic <title>.
  function wrapRootSvg(svg, envelope, spec) {
    const title  = envelope.title || '';
    const shortA = envelope.semantic_description &&
                   envelope.semantic_description.short_alt
                     ? envelope.semantic_description.short_alt
                     : '';
    const fq     = (spec && spec.focus_question) ? spec.focus_question : '';
    const typeLab = envelope.type || 'concept_map';
    const ariaLab = (title || typeLab) +
                    (shortA ? ' — ' + shortA :
                      (fq ? ' — ' + fq : ''));

    let out = svg.replace(/<svg\b([^>]*?)>/i, function (m, attrs) {
      let classes = ['ora-visual', 'ora-visual--concept_map'];
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

    // Insert a semantic <title> as first child (replace any Graphviz one).
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
        'concept_map renderer: spec field missing', 'spec'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    // Basic shape checks (Ajv has already run at Layer 2, but the structural
    // validator may be the only thing gating us if Ajv isn't bootstrapped).
    if (!Array.isArray(spec.concepts) || spec.concepts.length === 0) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'concept_map: spec.concepts must be a non-empty array',
        'spec.concepts'));
      return { svg: '', errors: errors, warnings: warnings };
    }
    if (!Array.isArray(spec.propositions)) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'concept_map: spec.propositions must be an array',
        'spec.propositions'));
      return { svg: '', errors: errors, warnings: warnings };
    }
    if (!Array.isArray(spec.linking_phrases)) {
      // Schema marks it required; tolerate missing here with clear error.
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'concept_map: spec.linking_phrases must be an array',
        'spec.linking_phrases'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    // 1. Invariant checks (reference resolution + cross-link heuristic).
    const refCheck = validateReferences(spec);
    if (refCheck.errors.length) {
      return { svg: '', errors: refCheck.errors, warnings: refCheck.warnings };
    }
    warnings.push.apply(warnings, refCheck.warnings);

    // 2. Emit DOT.
    const dot = specToDot(spec, envelope);

    // 3. Hand to shared dot-engine (engine=dot; rationale in file header).
    const engineApi = window.OraVisualCompiler._dotEngine;
    if (!engineApi || typeof engineApi.dotToSvg !== 'function') {
      errors.push(make(CODES.E_RENDERER_THREW,
        'concept_map: dot-engine not loaded; cannot render'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    const result = await engineApi.dotToSvg(dot, { engine: 'dot' });
    if (result.errors && result.errors.length) {
      return {
        svg: '',
        errors: result.errors,
        warnings: warnings.concat(result.warnings || []),
      };
    }

    // 4. Wrap the root <svg> with semantic classes and ARIA.
    const svg = wrapRootSvg(result.svg, envelope, spec);

    return {
      svg: svg,
      errors: [],
      warnings: warnings.concat(result.warnings || []),
    };
  }

  // Register with the dispatcher.
  if (window.OraVisualCompiler &&
      typeof window.OraVisualCompiler.registerRenderer === 'function') {
    window.OraVisualCompiler.registerRenderer('concept_map', { render: render });
  }

  // Expose internals for unit testing.
  return {
    render: render,
    _validateReferences: validateReferences,
    _specToDot: specToDot,
    _wrapRootSvg: wrapRootSvg,
  };
}());
