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
 *
 * ── DSL REPAIR (hardened 2026-06-14) ───────────────────────────────────────
 *   Real model-emitted Mermaid breaks the parser in predictable ways. The
 *   `_normalizeDsl` pass repairs the common classes per dialect:
 *
 *   FLOWCHART
 *     - Node-shape labels ([..], ([..]), [[..]], ((..)), {..}, {{..}}, [(..)],
 *       [/../], [\..\]) whose inner text contains special characters
 *       (parens, <br>, &, :, punctuation, spaces) are wrapped in double quotes
 *       so the lexer treats them as opaque label text. Only `"` is encoded
 *       (→ #quot;); <br>, &, parens etc. are LEFT INTACT (Mermaid renders them).
 *       The scanner is arrow-aware: it never touches `-->`, `-->|x|`,
 *       `-- x -->`, `==>`, `-.->`, or pipe-delimited edge labels.
 *     - Subgraph titles with spaces are quoted.
 *     - Malformed inline edge labels `X ---- "label" --> Y` (3+ leading dashes
 *       before a quoted inline label) are normalized to the valid
 *       `X -- "label" --> Y` form.
 *     - Trailing malformed `class ... displayName ...` directive lines (model
 *       hallucinations referencing undefined nodes) are dropped.
 *
 *   SEQUENCE
 *     - `;` inside message / Note text is replaced with `,` (Mermaid treats a
 *       bare `;` as a statement terminator, which truncates the message and
 *       breaks the parse). Parens and <br/> in message text are fine as-is.
 *
 *   STATE
 *     - State ids containing `-` or `.` (e.g. `Past-Due`, `1.3`) are invalid
 *       Mermaid identifiers. They are sanitized to `_` and a
 *       `state "Past-Due" as Past_Due` alias declaration is emitted so the
 *       original human-readable label is preserved on display. The header
 *       (`stateDiagram-v2`), `-->` arrows, and `[*]` start/end markers are
 *       never touched.
 *
 *   "Could not find a suitable point for the given distance" is a Mermaid
 *   *layout* failure (edge-label geometry), not a parse failure. In a real
 *   browser it does not occur because getBBox/getComputedTextLength return
 *   accurate non-zero sizes. Under jsdom (the server-side render-envelope.js /
 *   tests/run.js path) it surfaces only when the SVG-measurement polyfills
 *   return zero-width boxes; those polyfills carry a minimum-size floor so the
 *   geometry never collapses. The renderer additionally catches this specific
 *   error and retries with an alternate layout direction as a last resort.
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

  // Node-shape delimiter pairs, longest-opener first so `[[` wins over `[`.
  // (The `>` asymmetric-flag node opener is deliberately excluded: it collides
  // with the `>` of arrow tokens, and is vanishingly rare in model output.)
  const SHAPE_PAIRS = [
    { open: '[[', close: ']]' },
    { open: '[(', close: ')]' },
    { open: '([', close: '])' },
    { open: '[/', close: '/]' },
    { open: '[\\', close: '\\]' },
    { open: '((', close: '))' },
    { open: '{{', close: '}}' },
    { open: '[', close: ']' },
    { open: '(', close: ')' },
    { open: '{', close: '}' },
  ];

  // Inside a Mermaid "..." label string, only the double-quote needs encoding.
  // Mermaid accepts the HTML entity `#quot;`. Everything else — <br>, parens,
  // &, :, punctuation — renders fine and is left intact.
  function _escapeLabelText(s) {
    return String(s).replace(/"/g, '#quot;');
  }

  function _isIdChar(ch) {
    return ch !== undefined && /[A-Za-z0-9_]/.test(ch);
  }

  /**
   * Quote node-shape labels on a single flowchart line. Only treats a shape
   * opener as a node shape when it immediately follows an identifier char (the
   * node id). Skips arrow tokens and pipe-delimited edge labels (|...|) so we
   * never touch `-->`, `-->|x|`, `-- x -->`, `==>`, or `-.->`.
   */
  function _quoteNodeLabels(line) {
    let out = '';
    let i = 0;
    const n = line.length;
    while (i < n) {
      const ch = line[i];

      // Skip a pipe-delimited edge label |....| verbatim.
      if (ch === '|') {
        const end = line.indexOf('|', i + 1);
        if (end !== -1) { out += line.slice(i, end + 1); i = end + 1; continue; }
      }

      // A shape opener only counts when the previously-emitted char is an id
      // char — i.e. the opener belongs to a node id, not an arrow or a bare group.
      const prev = out.length ? out[out.length - 1] : '';
      if (_isIdChar(prev)) {
        let matched = null;
        for (const p of SHAPE_PAIRS) {
          if (line.startsWith(p.open, i)) {
            const innerStart = i + p.open.length;
            const closeIdx = line.indexOf(p.close, innerStart);
            if (closeIdx === -1) continue;
            matched = { p, closeIdx, inner: line.slice(innerStart, closeIdx) };
            break;
          }
        }
        if (matched) {
          const { p, closeIdx, inner } = matched;
          const trimmed = inner.trim();
          if (trimmed.length === 0) {
            out += line.slice(i, closeIdx + p.close.length);
          } else if (trimmed.startsWith('"') && trimmed.endsWith('"') && trimmed.length >= 2) {
            // Already a quoted string — re-emit, encoding any inner quotes.
            out += p.open + '"' + _escapeLabelText(trimmed.slice(1, -1)) + '"' + p.close;
          } else {
            out += p.open + '"' + _escapeLabelText(inner) + '"' + p.close;
          }
          i = closeIdx + p.close.length;
          continue;
        }
      }

      out += ch;
      i += 1;
    }
    return out;
  }

  function _firstKeywordLine(dsl) {
    const lines = dsl.split('\n');
    for (const l of lines) {
      const t = l.trim();
      if (t.length) return t.toLowerCase();
    }
    return '';
  }

  function _detectDialect(dsl, declaredType) {
    const first = _firstKeywordLine(dsl);
    if (/^sequencediagram/.test(first) || declaredType === 'sequence') return 'sequence';
    if (/^statediagram/.test(first) || declaredType === 'state') return 'state';
    if (/^(flowchart|graph)\b/.test(first) || declaredType === 'flowchart') return 'flowchart';
    return null;
  }

  // ── Per-dialect strong normalization ─────────────────────────────────────────
  function _normalizeFlowchart(dsl) {
    let lines = dsl.split('\n');
    lines = lines.map((line) => {
      // Malformed inline edge label `X ---- "label" --> Y` (3+ leading dashes
      // before a quoted inline label) → valid `X -- "label" --> Y`. The
      // already-valid two-dash form is left untouched.
      line = line.replace(/-{3,}(\s*"[^"]*"\s*)-{2,}>/g, '--$1-->');

      // Quote a subgraph title that has spaces / specials and isn't already
      // quoted: `subgraph ID [Customer Support]` → `subgraph ID ["Customer Support"]`.
      line = line.replace(/^(\s*subgraph\s+[^\s\[]+\s*\[)([^\]"]*\S)(\])/i,
        (m, head, title, tail) => head + '"' + _escapeLabelText(title) + '"' + tail);

      return _quoteNodeLabels(line);
    });

    // Drop trailing malformed directive lines (model hallucinations). A `class`
    // statement with extra trailing words (`class A, B displayName exception`)
    // is not valid and references undefined nodes / classes.
    lines = lines.filter((line) => {
      const t = line.trim();
      if (/^class\s+[\w,\s]+\s+\w+\s+\w+/.test(t) && !/^classDef\b/i.test(t)) {
        // `class <ids> <className>` is valid (exactly one trailing word). Three+
        // trailing words after the id list means it's malformed.
        return false;
      }
      return true;
    });

    return lines.join('\n');
  }

  function _normalizeSequence(dsl) {
    const lines = dsl.split('\n').map((line) => {
      const colon = line.indexOf(':');
      if (colon === -1) return line;
      // Replace `;` with `,` only in the text that follows the first `:` —
      // i.e. message / Note text — because a bare `;` terminates the statement.
      return line.slice(0, colon + 1) + line.slice(colon + 1).replace(/;/g, ',');
    });
    return lines.join('\n');
  }

  function _sanitizeStateId(raw, aliases) {
    const orig = raw.trim();
    if (orig === '[*]' || orig.length === 0) return raw;
    // A clean identifier (no spaces, dots, hyphens) is left as-is.
    if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(orig)) return raw;
    // Build a valid identifier: replace runs of invalid chars with `_`, then
    // ensure it starts with a letter/underscore (digit-leading ids are invalid).
    let safe = orig.replace(/[^A-Za-z0-9_]+/g, '_').replace(/^_+|_+$/g, '');
    if (!/^[A-Za-z_]/.test(safe)) safe = 'S_' + safe;
    if (!aliases.has(safe)) aliases.set(safe, orig);
    // Preserve surrounding whitespace from the original token slot.
    const lead = raw.match(/^\s*/)[0];
    const trail = raw.match(/\s*$/)[0];
    return lead + safe + trail;
  }

  function _normalizeState(dsl) {
    let lines = dsl.split('\n');
    const aliases = new Map(); // sanitizedId -> originalDisplayName

    lines = lines.map((line) => {
      const t = line.trim();
      // Never touch the diagram header, comments, or explicit `state` decls.
      if (/^statediagram/i.test(t) || t.startsWith('%%') || /^state\b/i.test(t)) return line;
      // Sanitize ids only in the transition part (before the `:` label).
      const colon = line.indexOf(':');
      const idPart = colon === -1 ? line : line.slice(0, colon);
      const rest = colon === -1 ? '' : line.slice(colon);
      // A transition is `<source> --> <target>` (arrow may be -->/-->). Split on
      // the arrow so a state id that itself contains spaces (e.g. `1.3 Past-Due`)
      // is sanitized as a single unit, not token-by-token.
      const arrowMatch = idPart.match(/^(.*?)(\s*-->\s*)(.*)$/);
      if (arrowMatch) {
        const src = _sanitizeStateId(arrowMatch[1], aliases);
        const tgt = _sanitizeStateId(arrowMatch[3], aliases);
        return src + arrowMatch[2] + tgt + rest;
      }
      // Non-transition line (bare state id, etc.) — sanitize token-by-token.
      const fixedId = idPart.replace(/[A-Za-z_][A-Za-z0-9_.-]*/g, (tok) => {
        if (tok.indexOf('-') === -1 && tok.indexOf('.') === -1) return tok;
        const safe = tok.replace(/[.-]/g, '_');
        if (!aliases.has(safe)) aliases.set(safe, tok);
        return safe;
      });
      return fixedId + rest;
    });

    if (aliases.size) {
      // Emit `state "Original" as Sanitized` right after the header so the
      // human-readable label survives the id sanitization.
      const headerIdx = lines.findIndex((l) => /^\s*statediagram/i.test(l));
      const decls = [];
      for (const [safe, orig] of aliases) {
        decls.push('    state "' + _escapeLabelText(orig) + '" as ' + safe);
      }
      const at = headerIdx === -1 ? 0 : headerIdx + 1;
      lines.splice(at, 0, ...decls);
    }

    return lines.join('\n');
  }

  /**
   * _normalizeDsl(dsl, declaredType) — the primary repair pass. Dispatches to
   * the per-dialect normalizer. Returns the (possibly changed) string; returns
   * the input unchanged when the dialect can't be determined.
   */
  function _normalizeDsl(dsl, declaredType) {
    const dialect = _detectDialect(dsl, declaredType);
    if (dialect === 'flowchart') return _normalizeFlowchart(dsl);
    if (dialect === 'sequence') return _normalizeSequence(dsl);
    if (dialect === 'state') return _normalizeState(dsl);
    return dsl;
  }

  /**
   * Apply a sequence of mechanical fixes to a DSL string. Retained for
   * backward compatibility and as a secondary pass; `_normalizeDsl` is the
   * primary, dialect-aware repair.
   *
   * Fixes applied in order:
   *   1. Quote bracketed labels that contain reserved words or spaces.
   *   2. Escape HTML-like chars inside already-double-quoted strings.
   *   3. Remove empty edges/nodes.
   *   4. Normalize over-long arrow tokens.
   */
  function _mechanicalFixes(dsl) {
    let out = dsl;

    // 1a. Quote bracketed labels containing spaces or reserved words.
    const bracketPatterns = [
      { open: '[', close: ']' },
      { open: '(', close: ')' },
      { open: '{', close: '}' },
    ];
    for (const { open, close } of bracketPatterns) {
      const o = open.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const c = close.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const re = new RegExp(o + '([^' + c + '"\\n]+)' + c, 'g');
      out = out.replace(re, (match, inner) => {
        const trimmed = inner.trim();
        if (trimmed.length === 0) return match;
        if (trimmed.indexOf('"') !== -1) return match;
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
    out = out.replace(/"([^"\n]*)"/g, (match, inner) => {
      const escaped = inner
        .replace(/&(?!(amp|lt|gt|quot|#);)/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
      return '"' + escaped + '"';
    });

    // 3. Remove lines that are pure empty edges.
    out = out.split('\n').filter((line) => {
      const t = line.trim();
      if (t.length === 0) return true;
      if (/^[-=.~]{1,3}[>xo]{1,2}$/.test(t)) return false;
      return true;
    }).join('\n');

    // 4. Normalize over-long arrow tokens.
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

    const tokenMatch = msg.match(/got\s+['"`]([^'"`]+)['"`]/i);
    const lineMatch = msg.match(/on line\s+(\d+)/i);

    const lines = dsl.split('\n');
    let changed = false;

    if (lineMatch) {
      const lineIdx = parseInt(lineMatch[1], 10) - 1;
      if (lineIdx >= 0 && lineIdx < lines.length) {
        let line = lines[lineIdx];
        const stripped = line.replace(/[;,]+\s*$/, '');
        if (stripped !== line) {
          lines[lineIdx] = stripped;
          changed = true;
        }
        if (tokenMatch) {
          const token = tokenMatch[1];
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

  /**
   * Apply a layout-direction tweak. The "Could not find a suitable point for
   * the given distance" failure is geometry-sensitive; switching the diagram
   * direction (TD↔LR for flowcharts) sometimes routes edges differently and
   * sidesteps the degenerate case. Returns a changed string or null.
   */
  function _layoutDirectionTweak(dsl) {
    const lines = dsl.split('\n');
    for (let i = 0; i < lines.length; i++) {
      const m = lines[i].match(/^(\s*)(flowchart|graph)\s+(TB|TD|BT|RL|LR)\b(.*)$/i);
      if (m) {
        const cur = m[3].toUpperCase();
        const next = (cur === 'LR' || cur === 'RL') ? 'TD' : 'LR';
        lines[i] = m[1] + m[2] + ' ' + next + m[4];
        return lines.join('\n');
      }
    }
    return null;
  }

  function _isLayoutError(err) {
    const m = (err && err.message) || '';
    return /suitable point for the given distance/i.test(m);
  }

  // ── SVG post-processing ─────────────────────────────────────────────────────
  // Preserve Mermaid's own style block/attributes and add Ora classes + ARIA.
  // Mermaid's native classes carry the visual paint; the Ora theme does not
  // reconstruct them.
  function _postProcessSvg(rawSvg, envelope) {
    const Parser = (typeof DOMParser !== 'undefined') ? DOMParser : null;
    if (!Parser) {
      return rawSvg;
    }

    const parser = new Parser();
    const doc = parser.parseFromString(rawSvg, 'image/svg+xml');
    const svgEl = doc.documentElement;
    if (!svgEl || svgEl.nodeName.toLowerCase() !== 'svg') {
      return rawSvg;
    }

    const typeClass = 'ora-visual--' + (envelope.type || 'unknown');
    svgEl.setAttribute('class', ('ora-visual ' + typeClass).trim());

    svgEl.setAttribute('role', 'img');
    const title = envelope.title || '';
    const shortAlt = (envelope.semantic_description && envelope.semantic_description.short_alt) || '';
    const ariaLabel = title && shortAlt
      ? (title + ' — ' + shortAlt)
      : (title || shortAlt || envelope.type || 'visual');
    svgEl.setAttribute('aria-label', ariaLabel);

    let titleEl = null;
    const titleCandidates = svgEl.getElementsByTagName('title');
    if (titleCandidates && titleCandidates.length > 0) {
      titleEl = titleCandidates[0];
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

    if (typeof XMLSerializer !== 'undefined') {
      return new XMLSerializer().serializeToString(svgEl);
    }
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
   * Repair ladder (each attempt parses + renders; first success wins):
   *   0. DSL as-is.
   *   1. Strong dialect-aware normalization (`_normalizeDsl`).
   *   2. Normalization + mechanical fixes (legacy quoting / escaping).
   *   3. Error-targeted heuristic fix.
   *   4. Layout-direction tweak — only when the failure is the geometry-level
   *      "suitable point" layout error (applied on top of the best DSL so far).
   *
   * Contract is Promise-returning; on exhaustion we return
   * { svg: '', errors: [...], warnings: [] } and never throw.
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

    const originalDsl = envelope.spec.dsl;
    const declaredType = envelope.type;

    const ok = (dsl, repairLabel) => {
      // Renders dsl; on success post-processes and returns the result object,
      // pushing a repair warning when a repair was applied. Returns null on
      // failure so the caller can fall through to the next ladder rung.
      return _tryMermaid(dsl).then((attempt) => {
        if (!attempt.ok) return { attempt };
        const processed = _postProcessSvg(attempt.svg, envelope);
        if (repairLabel) {
          warnings.push(make(CODES.W_DSL_REPAIRED,
            'Mermaid DSL repaired via ' + repairLabel + '. ' +
            'Original: <<<' + originalDsl + '>>> Repaired: <<<' + dsl + '>>>',
            'spec.dsl'));
        }
        return { done: { svg: processed, errors: [], warnings } };
      });
    };

    // Attempt 0 — as-is.
    let r = await ok(originalDsl, null);
    if (r.done) return r.done;
    let lastError = r.attempt.error;

    // Attempt 1 — strong dialect-aware normalization.
    const normalized = _normalizeDsl(originalDsl, declaredType);
    if (normalized !== originalDsl) {
      r = await ok(normalized, 'dialect-aware normalization (label quoting / id sanitization / statement-terminator repair)');
      if (r.done) return r.done;
      lastError = r.attempt.error || lastError;
    }

    // Best-effort base for the subsequent rungs.
    const base1 = (normalized !== originalDsl) ? normalized : originalDsl;

    // Attempt 2 — normalization + legacy mechanical fixes.
    const mechanical = _mechanicalFixes(base1);
    if (mechanical !== base1) {
      r = await ok(mechanical, 'mechanical fixes (reserved-word quoting, HTML escaping, arrow normalization)');
      if (r.done) return r.done;
      lastError = r.attempt.error || lastError;
    }

    const base2 = (mechanical !== base1) ? mechanical : base1;

    // Attempt 3 — error-targeted heuristic fix.
    const heuristic = _heuristicFix(base2, lastError && lastError.message);
    if (heuristic) {
      r = await ok(heuristic, 'heuristic fix (error-targeted token quoting / trailing-punctuation strip)');
      if (r.done) return r.done;
      lastError = r.attempt.error || lastError;
    }

    const base3 = heuristic || base2;

    // Attempt 4 — layout-direction tweak, only for the geometry-level failure.
    if (_isLayoutError(lastError)) {
      const tweaked = _layoutDirectionTweak(base3);
      if (tweaked) {
        r = await ok(tweaked, 'layout-direction tweak (worked around "suitable point" edge-geometry failure)');
        if (r.done) return r.done;
        lastError = r.attempt.error || lastError;
      }
    }

    // All repairs exhausted — surface the most recent parse / render error.
    const finalMsg = (lastError && lastError.message) || 'unknown Mermaid parse error';
    errors.push(make(CODES.E_DSL_PARSE,
      'Mermaid render failed after repair attempts (normalization, mechanical, heuristic, layout): ' + finalMsg,
      'spec.dsl'));
    warnings.push(make(CODES.W_DSL_REPAIR_FAILED,
      'Repair ladder exhausted: dialect-aware normalization + mechanical fixes + heuristic fix' +
      (_isLayoutError(lastError) ? ' + layout-direction tweak' : '') + '.',
      'spec.dsl'));
    return { svg: '', errors, warnings };
  }

  // Expose for tests / introspection.
  const _internals = {
    _mechanicalFixes,
    _heuristicFix,
    _postProcessSvg,
    _ensureInitialized,
    _normalizeDsl,
    _normalizeFlowchart,
    _normalizeSequence,
    _normalizeState,
    _quoteNodeLabels,
    _layoutDirectionTweak,
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
