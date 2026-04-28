/**
 * ora-visual-compiler / renderers/mermaid.js
 * PROCESS family renderer — sequence, flowchart, state (WP-1.2b).
 *
 * Depends on: errors.js, the vendored Mermaid library (~/vendor/mermaid/mermaid.min.js).
 *
 * Load order:
 *   errors.js
 *   validator.js
 *   renderers/stub.js
 *   dispatcher.js
 *   index.js
 *   vendor/mermaid/mermaid.min.js        ← must load before this file
 *   renderers/mermaid.js                 ← this file
 *
 * IMPORTANT — ASYNC CONTRACT:
 *   Mermaid's parse() and render() are Promise-returning. The existing renderer
 *   contract is synchronous ({ svg, errors, warnings }). This renderer therefore
 *   returns a Promise<{ svg, errors, warnings }>. WP-2.3 panel wiring must await
 *   the result of dispatch(). dispatcher.js is left untouched so that the change
 *   is localised and explicit.
 *
 * Semantic CSS only: no inline styles. Mermaid's injected styles and hardcoded
 * fill/stroke attributes are stripped before return — WP-1.4 ora-visual-theme.css
 * owns all appearance.
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.mermaid = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;

  // ── Mermaid initialization ──────────────────────────────────────────────────
  // `theme: 'base'` produces the least styling, leaving room for WP-1.4 CSS.
  // `securityLevel: 'strict'` disables click handlers and raw HTML.
  // `startOnLoad: false` prevents Mermaid from auto-rendering any .mermaid nodes.
  let _initialized = false;
  function _ensureInitialized() {
    if (_initialized) return true;
    if (typeof window.mermaid === 'undefined') return false;
    try {
      window.mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'base',
        // Prevent Mermaid from polluting the host document with its own error SVGs.
        suppressErrorRendering: true,
      });
      _initialized = true;
    } catch (_err) {
      // Initialisation failure surfaces on the first render via E_RENDERER_THREW-path.
      _initialized = false;
    }
    return _initialized;
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────
  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Generate a unique id for each Mermaid render call — Mermaid uses this as the
  // SVG root element id. Random suffix keeps parallel renders from colliding.
  let _idCounter = 0;
  function _uniqueId() {
    _idCounter += 1;
    return 'ora-mermaid-' + Date.now().toString(36) + '-' + _idCounter;
  }

  // ── DSL repair heuristics ───────────────────────────────────────────────────
  // Mermaid reserved words that commonly show up in LLM-emitted node labels.
  // Any of these appearing as a bare token inside brackets breaks the parse.
  const MERMAID_RESERVED = new Set([
    'end', 'subgraph', 'graph', 'flowchart', 'classDef', 'class',
    'click', 'style', 'linkStyle', 'direction',
    'state', 'note', 'as', 'fork', 'join', 'choice',
  ]);

  /**
   * Apply a sequence of mechanical fixes to a DSL string.
   * Returns the (possibly changed) string.
   *
   * Fixes applied in order:
   *   1. Quote bracketed labels that contain reserved words or spaces.
   *      [Label with spaces]  →  ["Label with spaces"]
   *      [end]                →  ["end"]
   *   2. Escape HTML-like chars (<, >, &) that appear inside quoted label strings.
   *      Only inside strings — we mustn't touch -->, -->>, --x, etc.
   *   3. Remove empty edges/nodes of the form `A -->` or `-->`.
   *   4. Normalize arrow tokens: collapse runs of dashes inside an arrow body.
   */
  function _mechanicalFixes(dsl) {
    let out = dsl;

    // 1a. Quote bracketed labels containing spaces or reserved words.
    //     Matches [content], (content), {content}, ((content)), etc.
    //     We only rewrite when the content is not already double-quoted.
    const bracketPatterns = [
      { open: '[', close: ']' },
      { open: '(', close: ')' },
      { open: '{', close: '}' },
    ];
    for (const { open, close } of bracketPatterns) {
      // Escape for regex
      const o = open.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const c = close.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      // Non-greedy inner capture; avoid matching nested brackets on the same line.
      const re = new RegExp(o + '([^' + c + '"\\n]+)' + c, 'g');
      out = out.replace(re, (match, inner) => {
        const trimmed = inner.trim();
        if (trimmed.length === 0) return match;
        // If already contains double-quote, leave alone.
        if (trimmed.indexOf('"') !== -1) return match;
        // Quote if contains space or is a reserved word.
        const hasSpace = /\s/.test(trimmed);
        const isReserved = MERMAID_RESERVED.has(trimmed.toLowerCase());
        const hasSpecial = /[<>&|;:#]/.test(trimmed);
        if (hasSpace || isReserved || hasSpecial) {
          return open + '"' + trimmed + '"' + close;
        }
        return match;
      });
    }

    // 2. Escape HTML-like chars inside already-double-quoted strings.
    //    Replace &, <, > with their HTML entities in the quoted regions.
    out = out.replace(/"([^"\n]*)"/g, (match, inner) => {
      const escaped = inner
        .replace(/&(?!(amp|lt|gt|quot|#);)/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
      return '"' + escaped + '"';
    });

    // 3. Remove lines that are pure empty edges (A -->, --> B, -->) after trim.
    out = out.split('\n').filter((line) => {
      const t = line.trim();
      if (t.length === 0) return true;
      // Pure arrow with no endpoints on either side: "-->", "-.->", "==>", "-->>"
      if (/^[-=.~]{1,3}[>xo]{1,2}$/.test(t)) return false;
      return true;
    }).join('\n');

    // 4. Normalize arrow tokens — collapse `---->` and similar oversights into `-->`.
    //    Only touch sequences of 3+ dashes followed by >.
    out = out.replace(/-{3,}>/g, '-->');
    out = out.replace(/-{3,}>>/g, '-->>');

    return out;
  }

  /**
   * Heuristic repair targeted at a specific error message.
   * Parses the Mermaid error string for line/token hints and quotes or strips
   * the offending token. Returns either a repaired DSL string or null.
   */
  function _heuristicFix(dsl, errorMessage) {
    if (!errorMessage) return null;
    const msg = String(errorMessage);

    // Pattern: "got 'TOKEN'" — Mermaid often reports the offending token this way.
    const tokenMatch = msg.match(/got\s+['"`]([^'"`]+)['"`]/i);
    // Pattern: "Parse error on line N: ..." — gives us the line number.
    const lineMatch = msg.match(/on line\s+(\d+)/i);

    const lines = dsl.split('\n');
    let changed = false;

    if (lineMatch) {
      const lineIdx = parseInt(lineMatch[1], 10) - 1;
      if (lineIdx >= 0 && lineIdx < lines.length) {
        let line = lines[lineIdx];
        // Strip trailing punctuation that often trips the parser.
        const stripped = line.replace(/[;,]+\s*$/, '');
        if (stripped !== line) {
          lines[lineIdx] = stripped;
          changed = true;
        }
        // If we also know the token, quote any bare occurrence on this line.
        if (tokenMatch) {
          const token = tokenMatch[1];
          // Bare token between brackets, not already quoted.
          const bareRe = new RegExp('([\\[\\(\\{])(' +
            token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') +
            ')([\\]\\)\\}])', 'g');
          const next = lines[lineIdx].replace(bareRe, (_m, a, b, c) => a + '"' + b + '"' + c);
          if (next !== lines[lineIdx]) {
            lines[lineIdx] = next;
            changed = true;
          }
        }
      }
    }

    return changed ? lines.join('\n') : null;
  }

  // ── SVG post-processing ─────────────────────────────────────────────────────
  // Strip Mermaid-injected style= attrs, <style> elements, and hardcoded
  // fill=/stroke= colors. Add ora-visual classes and ARIA attributes.
  function _postProcessSvg(rawSvg, envelope) {
    // Use DOMParser in browsers; parse5/jsdom in Node test harness supplies its own.
    const Parser = (typeof DOMParser !== 'undefined') ? DOMParser : null;
    if (!Parser) {
      // No DOMParser — return raw SVG (test harness should polyfill).
      return rawSvg;
    }

    const parser = new Parser();
    const doc = parser.parseFromString(rawSvg, 'image/svg+xml');
    const svgEl = doc.documentElement;
    if (!svgEl || svgEl.nodeName.toLowerCase() !== 'svg') {
      return rawSvg;
    }

    // Remove any <style> tags (theme CSS owns styling).
    const styleTags = svgEl.getElementsByTagName('style');
    for (let i = styleTags.length - 1; i >= 0; i--) {
      const node = styleTags[i];
      if (node.parentNode) node.parentNode.removeChild(node);
    }

    // Walk all descendants, strip inline style, fill, stroke.
    function walk(el) {
      if (!el || el.nodeType !== 1) return;
      // Only strip on the root and descendants — skip <title> text nodes etc.
      if (el.removeAttribute) {
        el.removeAttribute('style');
        // Strip fill/stroke attributes entirely — WP-1.4 CSS dictates appearance.
        // Keep fill="none" because removing it would fill shapes we don't want filled.
        const fill = el.getAttribute && el.getAttribute('fill');
        if (fill && fill !== 'none') el.removeAttribute('fill');
        const stroke = el.getAttribute && el.getAttribute('stroke');
        if (stroke && stroke !== 'none') el.removeAttribute('stroke');
      }
      const children = el.childNodes;
      if (children) {
        for (let i = 0; i < children.length; i++) walk(children[i]);
      }
    }
    walk(svgEl);

    // Add ora-visual classes to root SVG.
    const typeClass = 'ora-visual--' + (envelope.type || 'unknown');
    const existingClass = svgEl.getAttribute('class') || '';
    // Drop Mermaid's own root classes; we want a clean slate.
    svgEl.setAttribute('class', ('ora-visual ' + typeClass).trim());

    // ARIA attributes.
    svgEl.setAttribute('role', 'img');
    const title = envelope.title || '';
    const shortAlt = (envelope.semantic_description && envelope.semantic_description.short_alt) || '';
    const ariaLabel = title && shortAlt
      ? (title + ' — ' + shortAlt)
      : (title || shortAlt || envelope.type || 'visual');
    svgEl.setAttribute('aria-label', ariaLabel);

    // Ensure inner <title> element exists and carries our label.
    let titleEl = null;
    const titleCandidates = svgEl.getElementsByTagName('title');
    if (titleCandidates && titleCandidates.length > 0) {
      titleEl = titleCandidates[0];
      // Clear and refill.
      while (titleEl.firstChild) titleEl.removeChild(titleEl.firstChild);
      titleEl.appendChild(doc.createTextNode(ariaLabel));
    } else {
      titleEl = doc.createElementNS('http://www.w3.org/2000/svg', 'title');
      titleEl.appendChild(doc.createTextNode(ariaLabel));
      if (svgEl.firstChild) {
        svgEl.insertBefore(titleEl, svgEl.firstChild);
      } else {
        svgEl.appendChild(titleEl);
      }
    }
    if (titleEl && titleEl.setAttribute) {
      titleEl.setAttribute('class', 'ora-visual__accessible-title');
    }

    // Serialize back to string. XMLSerializer in browsers; fallback in Node.
    if (typeof XMLSerializer !== 'undefined') {
      return new XMLSerializer().serializeToString(svgEl);
    }
    // Very defensive fallback — should never be hit in the browser path.
    return svgEl.outerHTML || rawSvg;
  }

  // ── Core render path ────────────────────────────────────────────────────────
  /**
   * _tryMermaid(dsl) → Promise<{ ok: bool, svg?: string, error?: Error }>
   * Single attempt: parse + render.
   */
  async function _tryMermaid(dsl) {
    const id = _uniqueId();
    try {
      // parse() throws on invalid DSL (unless suppressErrors).
      await window.mermaid.parse(dsl);
      const result = await window.mermaid.render(id, dsl);
      return { ok: true, svg: result.svg };
    } catch (err) {
      return { ok: false, error: err };
    }
  }

  /**
   * render(envelope) → Promise<{ svg, errors, warnings }>
   *
   * Contract is Promise-returning; dispatcher.js catches throws via try/catch,
   * so we never throw — on failure we return { svg: '', errors: [...], warnings: [] }.
   */
  async function render(envelope) {
    const warnings = [];
    const errors = [];

    if (!_ensureInitialized()) {
      errors.push(make(CODES.E_RENDERER_THREW,
        'Mermaid library not loaded. Ensure vendor/mermaid/mermaid.min.js is included before renderers/mermaid.js.',
        'type'));
      return { svg: '', errors, warnings };
    }

    // Schema guarantees spec.dsl and spec.dialect per sequence/flowchart/state.json.
    const originalDsl = envelope.spec.dsl;

    // Attempt 0: try as-is.
    let attempt = await _tryMermaid(originalDsl);
    if (attempt.ok) {
      const processed = _postProcessSvg(attempt.svg, envelope);
      return { svg: processed, errors: [], warnings: [] };
    }

    // Attempt 1: mechanical fixes.
    const firstError = attempt.error;
    const mechanicallyFixed = _mechanicalFixes(originalDsl);
    if (mechanicallyFixed !== originalDsl) {
      attempt = await _tryMermaid(mechanicallyFixed);
      if (attempt.ok) {
        const processed = _postProcessSvg(attempt.svg, envelope);
        warnings.push(make(CODES.W_DSL_REPAIRED,
          'Mermaid DSL repaired via mechanical fixes (reserved-word quoting, HTML escaping, arrow normalization). ' +
          'Original: <<<' + originalDsl + '>>> Repaired: <<<' + mechanicallyFixed + '>>>',
          'spec.dsl'));
        return { svg: processed, errors: [], warnings };
      }
    }

    // Attempt 2: heuristic fix targeting the error message.
    const heuristicallyFixed = _heuristicFix(
      mechanicallyFixed !== originalDsl ? mechanicallyFixed : originalDsl,
      (attempt.error && attempt.error.message) || (firstError && firstError.message)
    );
    if (heuristicallyFixed) {
      attempt = await _tryMermaid(heuristicallyFixed);
      if (attempt.ok) {
        const processed = _postProcessSvg(attempt.svg, envelope);
        warnings.push(make(CODES.W_DSL_REPAIRED,
          'Mermaid DSL repaired via heuristic fix (error-targeted token quoting / trailing-punctuation strip). ' +
          'Original: <<<' + originalDsl + '>>> Repaired: <<<' + heuristicallyFixed + '>>>',
          'spec.dsl'));
        return { svg: processed, errors: [], warnings };
      }
    }

    // All repairs exhausted — surface original parse error.
    const finalMsg = (attempt.error && attempt.error.message)
      || (firstError && firstError.message)
      || 'unknown Mermaid parse error';
    errors.push(make(CODES.E_DSL_PARSE,
      'Mermaid parse failed after 2 repair attempts: ' + finalMsg,
      'spec.dsl'));
    warnings.push(make(CODES.W_DSL_REPAIR_FAILED,
      'Repair loop exhausted. Attempts: mechanical fixes' +
      (heuristicallyFixed ? ' + heuristic fix' : '') + '.',
      'spec.dsl'));
    return { svg: '', errors, warnings };
  }

  // Expose for tests / introspection.
  const _internals = {
    _mechanicalFixes,
    _heuristicFix,
    _postProcessSvg,
    _ensureInitialized,
  };

  // ── Registration ────────────────────────────────────────────────────────────
  const mod = { render, _internals };

  if (window.OraVisualCompiler && typeof window.OraVisualCompiler.registerRenderer === 'function') {
    window.OraVisualCompiler.registerRenderer('sequence',  mod);
    window.OraVisualCompiler.registerRenderer('flowchart', mod);
    window.OraVisualCompiler.registerRenderer('state',     mod);
  }

  return mod;
}());
