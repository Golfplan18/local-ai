/**
 * ora-visual-compiler / renderers/causal-dag.js
 * WP-1.2c — renderer for the `causal_dag` visual type.
 *
 * Accepts a DAGitty DSL string in envelope.spec.dsl, translates it to
 * Graphviz DOT (attaching semantic class attributes per node kind and
 * edge kind), runs a structural acyclicity check, and asks the shared
 * dot-engine to render the DOT to an SVG.
 *
 * Per Protocol §3.5:
 *   spec.dsl              — DAGitty DSL string
 *   spec.focal_exposure   — id of the treatment/exposure node
 *   spec.focal_outcome    — id of the outcome node
 *
 * Invariants enforced here (the JSON Schema cannot express these):
 *   - DAGitty parses cleanly
 *   - Graph is acyclic
 *   - focal_exposure and focal_outcome appear as declared nodes
 *
 * Semantic IDs (for Phase 5 annotation targeting):
 *   - Each node:  id="node_<declared_name>"
 *   - Each edge:  id="edge_<from>__<to>"
 * Underscores are used in preference to hyphens because Graphviz
 * HTML-entity-encodes hyphens in SVG attribute values ('-' → '&#45;'),
 * which defeats straight-forward DOM selectors in downstream consumers.
 *
 * IMPORTANT: render() is async (returns a Promise). The dispatcher awaits
 * renderer return values. WP-2.3 must also await compile().
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
 *   renderers/causal-dag.js     <- this file
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.causalDag = (function () {

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
  // the emitted DOT. We enforce simple identifier syntax on nodes from the
  // DAGitty parser, but labels can contain spaces.
  function _dotQ(s) {
    return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
  }

  // ── DAGitty parser ─────────────────────────────────────────────────────
  // DAGitty DSL grammar (the subset we target — the mainstream form used in
  // daggity.net and the dagitty R package):
  //
  //   dag [name] { statement* }
  //   statement := nodeDecl | edge | comment | ";"
  //   nodeDecl  := id annotation? ("," id annotation?)*
  //   annotation := "[" (keyword ("," keyword)*)? "]"
  //     keyword ∈ { exposure, outcome, latent, adjusted,
  //                 selected, unobserved, pos="x,y" }
  //   edge      := id  ("->" | "<-" | "<->" | "--")  id
  //   comment   := "//" ... end-of-line
  //
  // Tolerances:
  //   - leading "dag {" may be absent (plain DSL also seen in the wild)
  //   - statements separated by ";" and/or newlines
  //   - whitespace free
  //
  // This is a hand-rolled tokenizer+recursive parser. It emits structured
  // error messages on failure. No third-party parser dependency.

  // Node-kind vocabulary recognised in annotation brackets. Anything else
  // is preserved as a raw attribute (ignored downstream) and emits no
  // warning — DAGitty is liberal.
  const KIND_KEYWORDS = new Set([
    'exposure', 'outcome', 'latent', 'adjusted',
    'selected', 'unobserved',
  ]);

  function _tokenize(src) {
    // Strip comments.
    const clean = src.replace(/\/\/[^\n]*/g, '');
    const tokens = [];
    let i = 0;
    const n = clean.length;

    while (i < n) {
      const c = clean[i];

      if (c === ' ' || c === '\t' || c === '\n' || c === '\r') {
        i += 1;
        continue;
      }

      if (c === '{' || c === '}' || c === '[' || c === ']' ||
          c === ';' || c === ',' || c === '=') {
        tokens.push({ kind: c, value: c, pos: i });
        i += 1;
        continue;
      }

      // Edge operators: "->", "<-", "<->", "--"
      if (c === '-' && clean[i + 1] === '>') {
        tokens.push({ kind: 'edge', value: '->', pos: i });
        i += 2;
        continue;
      }
      if (c === '<' && clean[i + 1] === '-' && clean[i + 2] === '>') {
        tokens.push({ kind: 'edge', value: '<->', pos: i });
        i += 3;
        continue;
      }
      if (c === '<' && clean[i + 1] === '-') {
        tokens.push({ kind: 'edge', value: '<-', pos: i });
        i += 2;
        continue;
      }
      if (c === '-' && clean[i + 1] === '-') {
        tokens.push({ kind: 'edge', value: '--', pos: i });
        i += 2;
        continue;
      }

      // Quoted string literal (used for pos="x,y" in DAGitty).
      if (c === '"') {
        let j = i + 1;
        while (j < n && clean[j] !== '"') {
          if (clean[j] === '\\' && j + 1 < n) j += 2;
          else j += 1;
        }
        if (j >= n) {
          throw new _ParseError('Unterminated string literal', i);
        }
        tokens.push({ kind: 'string', value: clean.slice(i + 1, j), pos: i });
        i = j + 1;
        continue;
      }

      // Identifier or keyword. DAGitty identifiers: letters, digits, "_",
      // ".". We allow "$" too for robustness. Must start with a letter or
      // underscore.
      if (/[A-Za-z_]/.test(c)) {
        let j = i + 1;
        while (j < n && /[A-Za-z0-9_.$]/.test(clean[j])) j += 1;
        tokens.push({ kind: 'ident', value: clean.slice(i, j), pos: i });
        i = j;
        continue;
      }

      // Numeric literal (rare, but allowed inside pos).
      if (/[0-9]/.test(c) || (c === '-' && /[0-9]/.test(clean[i + 1] || ''))) {
        let j = i + 1;
        while (j < n && /[0-9.\-]/.test(clean[j])) j += 1;
        tokens.push({ kind: 'number', value: clean.slice(i, j), pos: i });
        i = j;
        continue;
      }

      throw new _ParseError(
        'Unexpected character ' + JSON.stringify(c), i);
    }

    return tokens;
  }

  function _ParseError(message, pos) {
    this.message = message;
    this.pos = pos;
  }

  /**
   * parseDagitty(src) → { nodes: Map<id, {id, kinds: Set, pos?}>,
   *                       edges: [{from, to, op}], name?: string }
   *
   * Throws _ParseError on malformed input; render() turns that into
   * E_DSL_PARSE.
   */
  function parseDagitty(src) {
    const tokens = _tokenize(src);
    let cursor = 0;

    const peek = () => tokens[cursor];
    const eat = () => tokens[cursor++];
    const expect = (kind, value) => {
      const t = tokens[cursor];
      if (!t || t.kind !== kind || (value !== undefined && t.value !== value)) {
        throw new _ParseError(
          'Expected ' + (value || kind) + ' but got ' +
          (t ? JSON.stringify(t.value) : 'end-of-input'),
          t ? t.pos : src.length);
      }
      cursor += 1;
      return t;
    };

    const nodes = new Map(); // id → {id, kinds:Set<string>, pos?}
    const edges = [];        // {from, to, op}
    let graphName;

    function getOrCreateNode(id) {
      if (!nodes.has(id)) {
        nodes.set(id, { id: id, kinds: new Set(), pos: null });
      }
      return nodes.get(id);
    }

    function parseAnnotation(node) {
      expect('[', '[');
      while (peek() && peek().kind !== ']') {
        const t = eat();
        if (t.kind !== 'ident') {
          throw new _ParseError(
            'Expected annotation keyword, got ' + JSON.stringify(t.value),
            t.pos);
        }
        const kw = t.value;
        if (peek() && peek().kind === '=') {
          eat(); // '='
          const val = eat();
          if (kw === 'pos') {
            // pos="x,y" — value is a string token
            node.pos = val.value;
          }
          // other key=val annotations silently ignored (outcome confidence
          // intervals etc. — not relevant to rendering).
        } else {
          if (KIND_KEYWORDS.has(kw)) {
            node.kinds.add(kw);
          }
          // unknown bare keyword → silently accepted; DAGitty tolerates.
        }
        if (peek() && peek().kind === ',') eat();
      }
      expect(']', ']');
    }

    function parseNodeDecl() {
      // identifier followed by optional annotation, optionally followed by
      // more identifier+annotation groups separated by commas.
      while (peek() && peek().kind === 'ident') {
        const nameTok = eat();
        const node = getOrCreateNode(nameTok.value);

        if (peek() && peek().kind === '[') {
          parseAnnotation(node);
        }

        if (peek() && peek().kind === ',') {
          eat();
          continue;
        }
        break;
      }
    }

    function parseEdgeChain(firstIdTok) {
      // We have consumed the first identifier. Look for an edge operator.
      let lhs = firstIdTok.value;
      getOrCreateNode(lhs);

      while (peek() && peek().kind === 'edge') {
        const op = eat();
        const rhsTok = peek();
        if (!rhsTok || rhsTok.kind !== 'ident') {
          throw new _ParseError(
            'Expected target node after ' + op.value + ', got ' +
            (rhsTok ? JSON.stringify(rhsTok.value) : 'end-of-input'),
            rhsTok ? rhsTok.pos : op.pos);
        }
        eat();
        const rhs = rhsTok.value;
        getOrCreateNode(rhs);

        if (op.value === '->') {
          edges.push({ from: lhs, to: rhs, op: '->' });
        } else if (op.value === '<-') {
          edges.push({ from: rhs, to: lhs, op: '->' });
        } else if (op.value === '<->') {
          edges.push({ from: lhs, to: rhs, op: '<->' });
        } else if (op.value === '--') {
          // Undirected edge — DAGitty allows this inside PAG/MAG, not DAG.
          // We render as a bidirected-style line but don't include it in
          // the acyclicity graph (it's not a directed edge).
          edges.push({ from: lhs, to: rhs, op: '--' });
        }

        // Allow optional annotation on the RIGHT of an edge chain target
        // if followed by "[...]".
        if (peek() && peek().kind === '[') {
          parseAnnotation(nodes.get(rhs));
        }

        lhs = rhs;
      }
    }

    function parseStatement() {
      const t = peek();
      if (!t) return;
      if (t.kind === ';') { eat(); return; }

      if (t.kind === 'ident') {
        // Could be a node declaration (ident [anno]) or an edge chain
        // (ident -> ident). We commit to the branch after looking ahead.
        const first = eat();

        if (peek() && peek().kind === '[') {
          // annotation binds to this node
          const node = getOrCreateNode(first.value);
          parseAnnotation(node);

          // After annotation, could be followed by more in a declaration
          // list ("x [exposure], y [outcome]") or an edge chain
          // ("x [exposure] -> y").
          if (peek() && peek().kind === ',') {
            eat();
            parseNodeDecl();
            return;
          }
          if (peek() && peek().kind === 'edge') {
            parseEdgeChain(first);
            return;
          }
          return;
        }

        if (peek() && peek().kind === 'edge') {
          parseEdgeChain(first);
          return;
        }
        if (peek() && peek().kind === ',') {
          eat();
          // bare identifier list — treat first as node decl, continue.
          getOrCreateNode(first.value);
          parseNodeDecl();
          return;
        }

        // Bare identifier, no edge, no annotation. Register as node.
        getOrCreateNode(first.value);
        return;
      }

      throw new _ParseError(
        'Unexpected token ' + JSON.stringify(t.value) +
        ' at start of statement', t.pos);
    }

    // Optional leading "dag [name] { ... }" wrapper.
    if (peek() && peek().kind === 'ident' &&
        (peek().value === 'dag' || peek().value === 'pdag' ||
         peek().value === 'mag' || peek().value === 'pag')) {
      eat();
      if (peek() && peek().kind === 'ident') {
        graphName = eat().value;
      }
      if (peek() && peek().kind === '{') {
        eat();
        while (peek() && peek().kind !== '}') {
          parseStatement();
          while (peek() && peek().kind === ';') eat();
        }
        expect('}', '}');
      }
    } else {
      // Un-wrapped DSL.
      while (peek()) {
        parseStatement();
        while (peek() && peek().kind === ';') eat();
      }
    }

    return { nodes: nodes, edges: edges, name: graphName };
  }

  // ── Cycle detection over the directed subgraph ─────────────────────────
  // Only true directed edges (-> and the normalised form of <-) participate
  // in acyclicity. Bidirected (<->) and undirected (--) edges are excluded.
  function hasCycle(nodes, edges) {
    const adj = new Map();
    for (const id of nodes.keys()) adj.set(id, []);
    for (const e of edges) {
      if (e.op === '->') adj.get(e.from).push(e.to);
    }

    const WHITE = 0, GRAY = 1, BLACK = 2;
    const color = new Map();
    for (const id of nodes.keys()) color.set(id, WHITE);

    let cyc = null;

    function dfs(u, pathStack) {
      if (cyc) return;
      color.set(u, GRAY);
      pathStack.push(u);
      for (const v of adj.get(u) || []) {
        if (cyc) return;
        const cv = color.get(v);
        if (cv === GRAY) {
          // Cycle detected. Capture the slice for the message.
          const startIdx = pathStack.indexOf(v);
          cyc = pathStack.slice(startIdx).concat([v]);
          return;
        }
        if (cv === WHITE) dfs(v, pathStack);
      }
      pathStack.pop();
      color.set(u, BLACK);
    }

    for (const id of nodes.keys()) {
      if (cyc) break;
      if (color.get(id) === WHITE) dfs(id, []);
    }

    return cyc;
  }

  // ── DAGitty → DOT translator ───────────────────────────────────────────
  function dagittyToDot(parsed, envelope) {
    const nodes = parsed.nodes;
    const edges = parsed.edges;

    const title = envelope.title || '';

    const lines = [];
    lines.push('digraph OraCausalDag {');
    lines.push('  rankdir=LR;');
    // Invariant node attributes. Semantic class goes on each node.
    lines.push('  node [shape=ellipse, margin="0.15,0.08"];');
    if (title) {
      // Graphviz label on the graph. Renderer-level title is set in the
      // <svg><title> element; the graph-level label here is informational
      // only. Plaintext-style keeps fewer inline attrs.
      lines.push('  labelloc="t"; label=' + _dotQ(title) + ';');
    }

    // Emit each node. class= attribute is respected by Graphviz when it
    // renders SVG — it appears on the <g class="..."> wrapping the node.
    // We also give each node an id= so annotations can target it later.
    for (const node of nodes.values()) {
      const classList = ['ora-visual__node'];
      if (node.kinds.has('exposure')) classList.push('ora-visual__node--exposure');
      if (node.kinds.has('outcome'))  classList.push('ora-visual__node--outcome');
      if (node.kinds.has('latent') || node.kinds.has('unobserved'))
        classList.push('ora-visual__node--latent');
      if (node.kinds.has('adjusted')) classList.push('ora-visual__node--adjusted');
      if (node.kinds.has('selected')) classList.push('ora-visual__node--selected');

      // Use underscore-separated IDs so Graphviz's HTML entity escaping of
      // hyphens ('-' → '&#45;') does not mangle downstream selectors.
      const attrs = [
        'id=' + _dotQ('node_' + node.id),
        'class=' + _dotQ(classList.join(' ')),
        'label=' + _dotQ(node.id),
      ];
      // Latent nodes get a dashed shape outline cue via class only; no
      // inline style. Renderer CSS handles appearance.
      if (node.kinds.has('latent') || node.kinds.has('unobserved')) {
        // Use a different shape token so CSS can distinguish; CSS will
        // style the shape. We pick shape=circle for latents — a common
        // DAGitty convention.
        attrs.push('shape=circle');
      }
      lines.push('  ' + _dotQ(node.id) + ' [' + attrs.join(', ') + '];');
    }

    // Emit each edge. <-> becomes dir=both with a bidirected class that
    // CSS may dash; -- gets dir=none.
    for (const e of edges) {
      const classList = ['ora-visual__edge'];
      const attrs = ['id=' + _dotQ('edge_' + e.from + '__' + e.to)];
      if (e.op === '->') {
        // default
      } else if (e.op === '<->') {
        classList.push('ora-visual__edge--bidirected');
        attrs.push('dir=both');
      } else if (e.op === '--') {
        classList.push('ora-visual__edge--undirected');
        attrs.push('dir=none');
      }
      attrs.push('class=' + _dotQ(classList.join(' ')));
      lines.push(
        '  ' + _dotQ(e.from) + ' -> ' + _dotQ(e.to) +
        ' [' + attrs.join(', ') + '];'
      );
    }

    lines.push('}');
    return lines.join('\n');
  }

  // ── Root SVG wrap/decoration ───────────────────────────────────────────
  // After Graphviz + dot-engine strips inline styles, we rewrite the root
  // <svg> element to carry the `ora-visual--causal_dag` class, role="img",
  // and an aria-label stitched from envelope title + short_alt.
  function wrapRootSvg(svg, envelope) {
    const title   = envelope.title || '';
    const shortA  = envelope.semantic_description &&
                    envelope.semantic_description.short_alt
                      ? envelope.semantic_description.short_alt
                      : '';
    const typeLab = envelope.type || 'causal_dag';
    const ariaLab = (title || typeLab) + (shortA ? ' — ' + shortA : '');

    // Add our semantic classes and ARIA attributes to <svg ...>. dot-engine
    // already injected `ora-visual` — here we extend.
    let out = svg.replace(/<svg\b([^>]*?)>/i, function (m, attrs) {
      // Extract existing classes if any.
      let classes = ['ora-visual', 'ora-visual--causal_dag'];
      let rest = attrs;
      const cm = rest.match(/\sclass\s*=\s*"([^"]*)"/);
      if (cm) {
        const existing = cm[1].split(/\s+/);
        for (const c of existing) if (c && classes.indexOf(c) < 0) classes.push(c);
        rest = rest.replace(/\sclass\s*=\s*"[^"]*"/, '');
      }
      // Drop any existing role/aria-label so ours wins.
      rest = rest.replace(/\srole\s*=\s*"[^"]*"/gi, '');
      rest = rest.replace(/\saria-label\s*=\s*"[^"]*"/gi, '');

      return '<svg' + rest +
        ' class="' + classes.join(' ') + '"' +
        ' role="img"' +
        ' aria-label="' + _esc(ariaLab) + '">';
    });

    // Insert an accessible <title> as the first child of <svg>. Replace any
    // existing <title> that Graphviz might have already emitted.
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
        'causal_dag renderer: spec field missing', 'spec'));
      return { svg: '', errors, warnings };
    }

    const dsl = spec.dsl;
    if (typeof dsl !== 'string' || dsl.length === 0) {
      errors.push(make(CODES.E_DSL_PARSE,
        'causal_dag renderer: spec.dsl must be a non-empty string',
        'spec.dsl'));
      return { svg: '', errors, warnings };
    }

    // 1. Parse the DAGitty DSL.
    let parsed;
    try {
      parsed = parseDagitty(dsl);
    } catch (err) {
      const msg = (err && err.message) ? err.message : String(err);
      const pos = (err && typeof err.pos === 'number') ? ' at char ' + err.pos : '';
      errors.push(make(CODES.E_DSL_PARSE,
        'causal_dag: DAGitty parse failure' + pos + ' — ' + msg,
        'spec.dsl'));
      return { svg: '', errors, warnings };
    }

    if (parsed.nodes.size === 0) {
      errors.push(make(CODES.E_DSL_PARSE,
        'causal_dag: no nodes declared in DSL', 'spec.dsl'));
      return { svg: '', errors, warnings };
    }

    // 2. Acyclicity (only over directed -> edges).
    const cycle = hasCycle(parsed.nodes, parsed.edges);
    if (cycle) {
      errors.push(make(CODES.E_GRAPH_CYCLE,
        'causal_dag: graph contains a directed cycle: ' +
          cycle.join(' → '),
        'spec.dsl'));
      return { svg: '', errors, warnings };
    }

    // 3. Focal exposure / outcome presence.
    const fx = spec.focal_exposure;
    const fy = spec.focal_outcome;
    if (!parsed.nodes.has(fx)) {
      errors.push(make(CODES.E_UNRESOLVED_REF,
        'causal_dag: focal_exposure ' + JSON.stringify(fx) +
        ' not declared as a node in spec.dsl',
        'spec.focal_exposure'));
    }
    if (!parsed.nodes.has(fy)) {
      errors.push(make(CODES.E_UNRESOLVED_REF,
        'causal_dag: focal_outcome ' + JSON.stringify(fy) +
        ' not declared as a node in spec.dsl',
        'spec.focal_outcome'));
    }
    if (errors.length) return { svg: '', errors, warnings };

    // Annotate focal roles on the parsed nodes if the DSL didn't.
    const fxNode = parsed.nodes.get(fx);
    const fyNode = parsed.nodes.get(fy);
    if (fxNode && !fxNode.kinds.has('exposure')) fxNode.kinds.add('exposure');
    if (fyNode && !fyNode.kinds.has('outcome'))  fyNode.kinds.add('outcome');

    // 4. Emit DOT and hand to the shared engine.
    const dot = dagittyToDot(parsed, envelope);

    const engineApi = window.OraVisualCompiler._dotEngine;
    if (!engineApi || typeof engineApi.dotToSvg !== 'function') {
      errors.push(make(CODES.E_RENDERER_THREW,
        'causal_dag: dot-engine not loaded; cannot render'));
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

    // 5. Wrap the root <svg> with ora-visual--causal_dag classes and ARIA.
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
    window.OraVisualCompiler.registerRenderer('causal_dag', { render: render });
  }

  // Also expose internals for unit testing.
  return {
    render: render,
    _parseDagitty: parseDagitty,
    _hasCycle: hasCycle,
    _dagittyToDot: dagittyToDot,
  };
}());
