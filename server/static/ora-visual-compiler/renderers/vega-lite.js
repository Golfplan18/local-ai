/**
 * ora-visual-compiler / renderers/vega-lite.js
 * QUANT family renderer — comparison, time_series, distribution, scatter,
 *                        heatmap, tornado (WP-1.2a).
 *
 * Depends on: errors.js, the vendored Vega + Vega-Lite libraries.
 *
 * Load order:
 *   errors.js
 *   validator.js
 *   renderers/stub.js
 *   dispatcher.js
 *   index.js
 *   vendor/vega/vega.min.js            ← must load before vega-lite
 *   vendor/vega-lite/vega-lite.min.js  ← must load before this file
 *   renderers/vega-lite.js             ← this file
 *
 * ASYNC CONTRACT (same pattern as renderers/mermaid.js):
 *   Vega's `view.toSVG()` is Promise-returning. This renderer therefore
 *   returns a Promise<{ svg, errors, warnings }>. dispatcher.js is left
 *   untouched; WP-2.3 panel wiring must `await` the result of dispatch().
 *
 * Semantic CSS only: no inline styles. Vega injects many computed
 * fill/stroke/font-* attributes on its SVG output — we strip them so WP-1.4
 * ora-visual-theme.css owns appearance. The stripping uses DOMParser where
 * available (jsdom in tests, browser in production), with a conservative
 * regex fallback for environments without DOMParser. See _postProcessSvg.
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.vegaLite = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;

  // The six QUANT types this renderer handles.
  const QUANT_TYPES = [
    'comparison', 'time_series', 'distribution', 'scatter', 'heatmap', 'tornado',
  ];

  // The verified subset of Vega-Lite marks allowed across QUANT types.
  // Per Protocol §3.1 and the per-type schemas (WP-0.2). Schema already
  // constrains these, so this is a defence-in-depth check for anything
  // a renderer-side transform (e.g. tornado→VL) might slip through.
  const ALLOWED_MARKS = new Set([
    'bar', 'point', 'circle', 'square', 'tick', 'rule', 'line', 'area',
    'errorband', 'errorbar', 'boxplot', 'rect', 'text',
  ]);

  // ── Tornado → Vega-Lite translator ──────────────────────────────────────────
  /**
   * Tornado (sensitivity) specs have a bespoke shape (Protocol §3.2):
   *   { base_case_label, base_case_value, outcome_variable, outcome_units,
   *     parameters: [{ label, low_value, high_value, outcome_at_low, outcome_at_high }],
   *     sort_by }
   * Convert to a Vega-Lite bar chart with one horizontal bar per parameter.
   * The bar spans from outcome_at_low to outcome_at_high; a rule marks the
   * base_case_value as the vertical reference.
   */
  function _tornadoToVegaLite(spec) {
    const baseValue = spec.base_case_value;
    // Order parameters per sort_by. 'custom' leaves the caller's order intact.
    let params = spec.parameters.slice();
    if (spec.sort_by === 'swing' || spec.sort_by === 'high_impact') {
      params.sort((a, b) => {
        const swingA = Math.abs(a.outcome_at_high - a.outcome_at_low);
        const swingB = Math.abs(b.outcome_at_high - b.outcome_at_low);
        return swingB - swingA;  // descending
      });
    }
    const rows = params.map((p) => ({
      label:           p.label,
      outcome_at_low:  p.outcome_at_low,
      outcome_at_high: p.outcome_at_high,
    }));
    const labelOrder = params.map((p) => p.label);

    return {
      $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
      data: { values: rows },
      layer: [
        {
          mark: { type: 'bar', cornerRadius: 0 },
          encoding: {
            y: { field: 'label', type: 'nominal', sort: labelOrder, title: null },
            x:  { field: 'outcome_at_low',  type: 'quantitative', title: spec.outcome_variable + ' (' + spec.outcome_units + ')' },
            x2: { field: 'outcome_at_high' },
          },
        },
        {
          mark: { type: 'rule' },
          encoding: {
            x: { datum: baseValue },
          },
        },
      ],
      width:  400,
      height: { step: 28 },
    };
  }

  // ── SVG post-processing ─────────────────────────────────────────────────────
  /**
   * Strip inline appearance attributes from a Vega-produced SVG string and
   * add our semantic classes. Vega sets style/fill/stroke/font-family/etc.
   * on nearly every element — we want CSS in ora-visual-theme.css to own
   * these (WP-1.4).
   *
   * Approach: prefer DOMParser (jsdom in tests, browser in production) for
   * proper XML handling. Fall back to a conservative regex strip if the
   * environment has no DOMParser. The regex path is deliberately limited:
   * it only targets the specific attributes named in STRIP_ATTRS and never
   * touches element structure. Tradeoff: regex cannot handle escaped quotes
   * in attribute values; we accept this because Vega does not emit such
   * values in practice. DOMParser is exercised by the test harness.
   */
  const STRIP_ATTRS = [
    'style', 'fill', 'stroke', 'stroke-width', 'stroke-dasharray',
    'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit',
    'font-family', 'font-size', 'font-weight', 'font-style',
    'opacity', 'fill-opacity', 'stroke-opacity',
  ];

  function _stripInlineStyles(svgString, envelope) {
    const title    = (envelope.title && String(envelope.title)) || '';
    const typeLbl  = String(envelope.type || 'unknown');
    const shortAlt = (envelope.semantic_description && envelope.semantic_description.short_alt)
      ? String(envelope.semantic_description.short_alt) : '';
    const ariaLabel = title + (shortAlt ? ' — ' + shortAlt : '') || typeLbl;

    if (typeof window !== 'undefined' && typeof window.DOMParser === 'function') {
      try {
        const parser = new window.DOMParser();
        const doc = parser.parseFromString(svgString, 'image/svg+xml');
        const root = doc.documentElement;
        if (root && root.nodeName && root.nodeName.toLowerCase() === 'svg') {
          _walkStrip(root);
          // Apply semantic classes + ARIA on root <svg>.
          const existingClass = root.getAttribute('class') || '';
          const cleaned = existingClass
            .split(/\s+/)
            .filter((c) => c && c !== 'marks')   // drop Vega's "marks" class
            .join(' ');
          const newClass = (
            'ora-visual ora-visual--' + typeLbl +
            (cleaned ? ' ' + cleaned : '')
          ).trim();
          root.setAttribute('class', newClass);
          root.setAttribute('role', 'img');
          root.setAttribute('aria-label', ariaLabel);
          // Insert an accessible <title> child if missing.
          let hasTitle = false;
          for (let i = 0; i < root.childNodes.length; i++) {
            const n = root.childNodes[i];
            if (n.nodeType === 1 && n.nodeName && n.nodeName.toLowerCase() === 'title') {
              hasTitle = true;
              break;
            }
          }
          if (!hasTitle) {
            const ns = 'http://www.w3.org/2000/svg';
            const t = doc.createElementNS ? doc.createElementNS(ns, 'title') : doc.createElement('title');
            t.setAttribute('class', 'ora-visual__accessible-title');
            t.textContent = ariaLabel;
            root.insertBefore(t, root.firstChild);
          }
          // Serialize back.
          if (typeof window.XMLSerializer === 'function') {
            return new window.XMLSerializer().serializeToString(root);
          }
          // Fall through to regex if no serializer.
        }
      } catch (_) {
        // Fall through to regex path.
      }
    }
    return _regexStrip(svgString, ariaLabel, typeLbl);
  }

  function _walkStrip(el) {
    if (!el || el.nodeType !== 1) return;
    for (let i = STRIP_ATTRS.length - 1; i >= 0; i--) {
      const attr = STRIP_ATTRS[i];
      if (el.hasAttribute && el.hasAttribute(attr)) {
        el.removeAttribute(attr);
      }
    }
    const children = el.childNodes || [];
    for (let j = 0; j < children.length; j++) {
      _walkStrip(children[j]);
    }
  }

  function _regexStrip(svgString, ariaLabel, typeLbl) {
    let out = svgString;
    // Strip targeted attributes. Single- or double-quoted values.
    for (let i = 0; i < STRIP_ATTRS.length; i++) {
      const attr = STRIP_ATTRS[i];
      const pat = new RegExp('\\s' + attr + '=(?:"[^"]*"|\'[^\']*\')', 'g');
      out = out.replace(pat, '');
    }
    // Inject class + ARIA onto the root <svg>.
    out = out.replace(/<svg\b([^>]*)>/, function (_m, attrs) {
      let cleaned = attrs
        .replace(/\sclass=(?:"[^"]*"|'[^']*')/g, '')
        .replace(/\srole=(?:"[^"]*"|'[^']*')/g, '')
        .replace(/\saria-label=(?:"[^"]*"|'[^']*')/g, '');
      const aria = _esc(ariaLabel);
      return '<svg' + cleaned +
        ' class="ora-visual ora-visual--' + _esc(typeLbl) + '"' +
        ' role="img"' +
        ' aria-label="' + aria + '">';
    });
    // Insert accessible <title> right after <svg ...>.
    if (!/<title\b/.test(out)) {
      out = out.replace(/<svg\b[^>]*>/, function (m) {
        return m + '<title class="ora-visual__accessible-title">' + _esc(ariaLabel) + '</title>';
      });
    }
    return out;
  }

  function _esc(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Vega-Lite compile + Vega render ────────────────────────────────────────
  /**
   * _compileAndRender(vlSpec) → Promise<string>  (raw SVG)
   * Rejects on any compile/parse/render error; caller maps to E_DSL_PARSE.
   */
  function _compileAndRender(vlSpec) {
    if (typeof window.vegaLite === 'undefined' || typeof window.vega === 'undefined') {
      return Promise.reject(new Error('vega / vega-lite globals not available; check vendor load order'));
    }

    // Defensive: check the mark against the allowed subset BEFORE compile.
    const declaredMark = _extractMark(vlSpec);
    if (declaredMark && !ALLOWED_MARKS.has(declaredMark)) {
      return Promise.reject(new Error(
        "Mark '" + declaredMark + "' is outside the verified Vega-Lite subset. " +
        'Allowed: ' + Array.from(ALLOWED_MARKS).join(', ')
      ));
    }

    let vgSpec;
    try {
      const compiled = window.vegaLite.compile(vlSpec);
      vgSpec = compiled && compiled.spec;
      if (!vgSpec) throw new Error('vega-lite.compile returned no .spec');
    } catch (err) {
      return Promise.reject(err);
    }

    let runtime;
    try {
      runtime = window.vega.parse(vgSpec);
    } catch (err) {
      return Promise.reject(err);
    }

    let view;
    try {
      view = new window.vega.View(runtime, { renderer: 'none' });
    } catch (err) {
      return Promise.reject(err);
    }

    // view.toSVG() returns a Promise<string>. We do not call .run() because
    // toSVG triggers a run internally and resolves after it.
    return view.toSVG().catch(function (err) { throw err; });
  }

  function _extractMark(vlSpec) {
    if (!vlSpec) return null;
    if (vlSpec.mark) {
      return (typeof vlSpec.mark === 'string') ? vlSpec.mark : (vlSpec.mark.type || null);
    }
    // Layered / repeated specs: check first layer's mark.
    if (Array.isArray(vlSpec.layer) && vlSpec.layer.length > 0) {
      return _extractMark(vlSpec.layer[0]);
    }
    return null;
  }

  // ── Public entry ───────────────────────────────────────────────────────────
  /**
   * render(envelope) → Promise<{ svg, errors, warnings }>
   *
   * envelope.type is one of QUANT_TYPES. envelope.spec has already been
   * schema-validated (to at least the per-type Vega-Lite subset schema) —
   * we still guard compile/parse errors defensively.
   */
  function render(envelope) {
    const warnings = [];
    const type = envelope && envelope.type;

    if (QUANT_TYPES.indexOf(type) === -1) {
      return Promise.resolve({
        svg: '',
        errors: [make(CODES.E_UNKNOWN_TYPE,
          "vega-lite renderer called with non-QUANT type '" + type + "'",
          'type')],
        warnings: warnings,
      });
    }

    let vlSpec;
    try {
      vlSpec = (type === 'tornado')
        ? _tornadoToVegaLite(envelope.spec)
        : envelope.spec;
    } catch (err) {
      return Promise.resolve({
        svg: '',
        errors: [make(CODES.E_DSL_PARSE,
          'Vega-Lite translation failed for type ' + type + ': ' + (err.message || err),
          'spec')],
        warnings: warnings,
      });
    }

    return _compileAndRender(vlSpec).then(
      function (rawSvg) {
        const svg = _stripInlineStyles(rawSvg, envelope);
        return { svg: svg, errors: [], warnings: warnings };
      },
      function (err) {
        return {
          svg: '',
          errors: [make(CODES.E_DSL_PARSE,
            'Vega-Lite compile failed: ' + (err.message || err),
            'spec')],
          warnings: warnings,
        };
      }
    );
  }

  // ── Registration ───────────────────────────────────────────────────────────
  const mod = { render, _internals: { _tornadoToVegaLite, _stripInlineStyles, _extractMark, QUANT_TYPES, ALLOWED_MARKS } };

  if (window.OraVisualCompiler && typeof window.OraVisualCompiler.registerRenderer === 'function') {
    for (let i = 0; i < QUANT_TYPES.length; i++) {
      window.OraVisualCompiler.registerRenderer(QUANT_TYPES[i], mod);
    }
  }

  return mod;
}());
