/**
 * ora-visual-compiler / renderers/ach-matrix.js
 * ACH (Analysis of Competing Hypotheses — Heuer) matrix — WP-1.3f.
 *
 * ACH is a decision-family technique that renders as a heatmap with
 * evidence on the y-axis and hypotheses on the x-axis. Each cell carries
 * a categorical consistency judgement from the fixed vocabulary:
 *
 *   CC  strongly consistent      (best evidence for the hypothesis)
 *   C   consistent
 *   N   neutral
 *   I   inconsistent
 *   II  strongly inconsistent    (strongest evidence against)
 *   NA  not applicable           (evidence doesn't bear on this hypothesis)
 *
 * Diagnosticity — per Heuer — is the property of the EVIDENCE row. A row
 * whose cells are all the same value (especially all N or NA) distinguishes
 * between no hypotheses; it contributes nothing to the analysis and is
 * flagged with W_ACH_NONDIAGNOSTIC. Diagnostic rows (varying judgements
 * across hypotheses) discriminate between hypotheses.
 *
 * Scoring — per `spec.scoring_method` (schema enum: heuer_tally|bayesian|weighted):
 *   - heuer_tally:  count inconsistencies per hypothesis (I counts -1, II counts -2,
 *                   NA counts 0). Most-negative score is the "strongest against";
 *                   Heuer's method favours hypotheses with the FEWEST inconsistencies
 *                   surviving, so LOWEST-magnitude-of-inconsistency wins. We invert:
 *                   the leading hypothesis is the one where sum(incons_weight) is
 *                   CLOSEST to zero (least inconsistent).
 *   - weighted:     same as heuer_tally but weighted by evidence.credibility
 *                   (H=1.0, M=0.67, L=0.33).
 *   - bayesian:     approximation: treat CC as +2, C as +1, N as 0, I as -1, II as -2,
 *                   NA as 0 log-likelihood contribution; sum per hypothesis. Highest
 *                   sum wins. Not a real Bayes computation — it's a presentation
 *                   stand-in until per-evidence likelihood ratios land in v0.3.
 *
 * The leading hypothesis gets:
 *   - class `ora-visual__ach-hyp--leading` on its axis label
 *   - data-leading="true" attribute on its column header
 *   - attached to returned warnings as informational banner (not a warning)
 *
 * Renderer contract:
 *   render(envelope) → Promise<{svg, errors, warnings}>  (async: Vega-Lite is).
 *   Never throws. Errors via errors.js CODES only.
 *
 * Stable IDs emitted on the post-processed SVG:
 *   id="ach-cell-<evidenceId>-<hypothesisId>"
 *   id="ach-hyp-<hypothesisId>"
 *   id="ach-evid-<evidenceId>"
 *
 * Semantic CSS only. Classes: ora-visual, ora-visual--ach_matrix,
 * ora-visual__ach-cell, ora-visual__ach-cell--CC|C|N|I|II|NA,
 * ora-visual__ach-hyp, ora-visual__ach-hyp--leading,
 * ora-visual__ach-evid, ora-visual__ach-evid--nondiagnostic.
 *
 * Load order:
 *   errors.js → validator.js → stub.js → dispatcher.js → index.js
 *   vendor/vega/vega.min.js → vendor/vega-lite/vega-lite.min.js
 *   renderers/vega-lite.js
 *   renderers/ach-matrix.js   ← this file
 *
 * Depends on: errors.js, palettes.js, vega, vega-lite (globals window.vega,
 *             window.vegaLite).
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.achMatrix = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;
  const palettes        = window.OraVisualCompiler.palettes;

  // Canonical cell value ordering. Used for:
  //   - the ordinal scale on the Vega-Lite color encoding
  //   - mapping cell values to diverging palette indices (II..CC across RdBu;
  //     NA is a separate neutral slot)
  //   - validation messages
  const CELL_ORDER = ['II', 'I', 'N', 'C', 'CC'];   // diverging: inconsistent → consistent
  const ALL_CELL_VALUES = new Set(['CC', 'C', 'N', 'I', 'II', 'NA']);

  // Credibility weighting for scoring_method=weighted.
  const CREDIBILITY_WEIGHT = { H: 1.0, M: 0.67, L: 0.33 };

  // Default scoring method (per briefing: if absent, use weighted-ish; per
  // schema enum: must be one of heuer_tally|bayesian|weighted). When the
  // schema-validated envelope arrives with scoring_method present, we use
  // it; if missing (Layer 1 only), we fall back to heuer_tally (most
  // interpretable of the three options).
  const DEFAULT_SCORING = 'heuer_tally';

  // ── Invariant validation ─────────────────────────────────────────────────
  /**
   * _validateInvariants(spec) → { errors, warnings, nondiagnosticEvidenceIds }
   *
   * Enforces the three ach_matrix invariants from visual-schemas/README.md:
   *   1. Every (evidence × hypothesis) cell populated.
   *   2. Cell values from vocabulary (the Ajv schema already enforces this,
   *      but we defend: cells that arrived through Layer 1 only need checks).
   *   3. Non-diagnostic evidence (all cells same, or all N/NA) flagged.
   */
  function _validateInvariants(spec) {
    const errors   = [];
    const warnings = [];
    const nondiagnosticEvidenceIds = [];

    if (!spec || typeof spec !== 'object') {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        "ach_matrix spec is not an object", 'spec'));
      return { errors, warnings, nondiagnosticEvidenceIds };
    }

    const hyps = Array.isArray(spec.hypotheses) ? spec.hypotheses : [];
    const evids = Array.isArray(spec.evidence)   ? spec.evidence    : [];
    const cells = (spec.cells && typeof spec.cells === 'object') ? spec.cells : {};

    if (hyps.length < 2) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        "ach_matrix requires at least 2 hypotheses; found " + hyps.length,
        'spec.hypotheses'));
    }
    if (evids.length < 1) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        "ach_matrix requires at least 1 piece of evidence; found 0",
        'spec.evidence'));
    }
    if (errors.length > 0) {
      // Bail early — completeness/diagnosticity don't make sense without a matrix.
      return { errors, warnings, nondiagnosticEvidenceIds };
    }

    // Invariant 1 + 2: every cell populated AND from the vocabulary.
    for (let i = 0; i < evids.length; i++) {
      const eRow  = cells[evids[i].id];
      for (let j = 0; j < hyps.length; j++) {
        const hId = hyps[j].id;
        if (!eRow || !(hId in eRow)) {
          errors.push(make(CODES.E_SCHEMA_INVALID,
            "Cell missing for evidence '" + evids[i].id + "' × hypothesis '" + hId + "'",
            "spec.matrix[" + evids[i].id + "][" + hId + "]"));
          continue;
        }
        const v = eRow[hId];
        if (!ALL_CELL_VALUES.has(v)) {
          errors.push(make(CODES.E_SCHEMA_INVALID,
            "Cell value '" + v + "' is not in the vocabulary {CC,C,N,I,II,NA}",
            "spec.matrix[" + evids[i].id + "][" + hId + "]"));
        }
      }
    }
    if (errors.length > 0) {
      return { errors, warnings, nondiagnosticEvidenceIds };
    }

    // Invariant 3: per-row diagnosticity.
    //   "non-diagnostic" per Heuer + this codebase's README:
    //     - every cell in the row is the same value, OR
    //     - every cell is N or NA (the row says nothing even if it technically
    //       varies between N and NA — neither discriminates)
    for (let i = 0; i < evids.length; i++) {
      const eId = evids[i].id;
      const row = cells[eId];
      const values = hyps.map(function (h) { return row[h.id]; });
      const distinct = new Set(values);
      const allNeutral = values.every(function (v) { return v === 'N' || v === 'NA'; });
      const allSame = distinct.size === 1;

      if (allSame || allNeutral) {
        nondiagnosticEvidenceIds.push(eId);
        const label = evids[i].text ? ('"' + _truncate(evids[i].text, 60) + '"') : ('evidence ' + eId);
        warnings.push(make(CODES.W_ACH_NONDIAGNOSTIC,
          "Evidence row " + label + " is non-diagnostic: " +
          (allSame ? ("every cell is '" + values[0] + "'") : "every cell is N or NA") +
          " — this row discriminates between no hypotheses and contributes " +
          "nothing to the analysis. Consider removing it or sourcing more " +
          "specific evidence.",
          "spec.cells[" + eId + "]"));
      }
    }

    return { errors, warnings, nondiagnosticEvidenceIds };
  }

  function _truncate(s, n) {
    s = String(s);
    return s.length <= n ? s : (s.slice(0, n - 1) + '…');
  }

  // ── Scoring ──────────────────────────────────────────────────────────────
  /**
   * _scoreHypotheses(spec, method) → { scores: { [hypId]: number },
   *                                    leadingId: string, method: string,
   *                                    rule: 'highest'|'closest-to-zero' }
   *
   * Computes one number per hypothesis per the scoring_method rule.
   * Returns both the numbers (for annotation) and the leading-hypothesis
   * identifier (for axis-label class + data attribute).
   */
  function _scoreHypotheses(spec, method) {
    const hyps  = spec.hypotheses;
    const evids = spec.evidence;
    const cells = spec.cells;

    // Heuer's original algorithm focuses on inconsistency count; the
    // hypothesis with the FEWEST inconsistencies (ie, score closest to zero)
    // wins. 'weighted' is the same with credibility applied.
    // 'bayesian' is an additive log-likelihood stand-in where HIGHEST wins.
    // Unknown method falls through to heuer_tally.
    const usedMethod = _isKnownMethod(method) ? method : DEFAULT_SCORING;

    const scores = {};
    const rule = (usedMethod === 'bayesian') ? 'highest' : 'closest-to-zero';

    for (let j = 0; j < hyps.length; j++) {
      const hId = hyps[j].id;
      let acc = 0;
      for (let i = 0; i < evids.length; i++) {
        const eId = evids[i].id;
        const v = cells[eId][hId];
        const base = _cellContribution(v, usedMethod);
        const w = (usedMethod === 'weighted')
          ? (CREDIBILITY_WEIGHT[evids[i].credibility] || 0.5)
          : 1.0;
        acc += base * w;
      }
      scores[hId] = acc;
    }

    // Pick leading per rule.
    let leadingId = hyps[0].id;
    let leadingScore = scores[leadingId];
    for (let j = 1; j < hyps.length; j++) {
      const hId = hyps[j].id;
      const s   = scores[hId];
      if (rule === 'highest') {
        if (s > leadingScore) { leadingScore = s; leadingId = hId; }
      } else {
        // closest-to-zero: the LEAST negative (least inconsistent). Since
        // inconsistency contributions are all ≤ 0, closest-to-zero == max.
        if (s > leadingScore) { leadingScore = s; leadingId = hId; }
      }
    }

    return { scores: scores, leadingId: leadingId, method: usedMethod, rule: rule };
  }

  function _isKnownMethod(m) {
    return m === 'heuer_tally' || m === 'weighted' || m === 'bayesian';
  }

  /**
   * _cellContribution(value, method) → number
   *
   * heuer_tally / weighted:
   *   CC:  0  C:  0  N:  0  I: -1  II: -2  NA: 0
   *   (inconsistency-count: count how BAD the evidence is against the hyp;
   *    consistent/neutral add nothing, inconsistent subtracts; higher score
   *    = fewer inconsistencies = the leading hypothesis)
   *
   * bayesian:
   *   CC: +2  C: +1  N:  0  I: -1  II: -2  NA: 0
   *   (symmetric log-likelihood stand-in; highest score = most supported)
   */
  function _cellContribution(v, method) {
    if (method === 'bayesian') {
      switch (v) {
        case 'CC': return  2;
        case 'C':  return  1;
        case 'N':  return  0;
        case 'I':  return -1;
        case 'II': return -2;
        case 'NA': return  0;
      }
      return 0;
    }
    // heuer_tally / weighted: only penalize inconsistencies.
    switch (v) {
      case 'CC': return 0;
      case 'C':  return 0;
      case 'N':  return 0;
      case 'I':  return -1;
      case 'II': return -2;
      case 'NA': return 0;
    }
    return 0;
  }

  // ── Vega-Lite spec construction ──────────────────────────────────────────
  /**
   * _buildVegaLiteSpec(spec, scoring) → Vega-Lite JSON
   *
   * Emits a heatmap with:
   *   - x: hypothesis.id (nominal, ordered by input order, tooltips show labels)
   *   - y: evidence.id (nominal, ordered by input order)
   *   - color: cell categorical value (ordinal, diverging palette)
   *   - text overlay: cell value label (CC|C|N|I|II|NA)
   *
   * NA gets a distinct neutral colour from palette.muted, rendered via a
   * fixed scale range. Other values take from palettes.diverging(5) mapped
   * by CELL_ORDER (II → C of RdBu cold, CC → hot). This gives visual
   * consistency with the "consistent vs inconsistent" gradient.
   */
  function _buildVegaLiteSpec(spec, scoring) {
    const hyps  = spec.hypotheses;
    const evids = spec.evidence;
    const cells = spec.cells;

    // Build long-form rows.
    const rows = [];
    for (let i = 0; i < evids.length; i++) {
      for (let j = 0; j < hyps.length; j++) {
        const eId = evids[i].id;
        const hId = hyps[j].id;
        rows.push({
          evidence:   eId,
          evidence_label: _truncate(evids[i].text || eId, 48),
          hypothesis: hId,
          hypothesis_label: hyps[j].label || hId,
          value:      cells[eId][hId],
        });
      }
    }

    // Color ramp: 5 steps from RdBu diverging covering II → CC. NA maps
    // separately to the muted grey. Call palettes.diverging(5) as required.
    const ramp5 = palettes.diverging(5);    // [II, I, N, C, CC] → cold → warm
    const rangeColors = [
      ramp5[0],  // II  strongest against  → deep red
      ramp5[1],  // I   inconsistent       → pale red
      ramp5[2],  // N   neutral            → near-white
      ramp5[3],  // C   consistent         → pale blue
      ramp5[4],  // CC  strongly consist.  → deep blue
      palettes.muted,  // NA — neutral grey
    ];
    const domain = ['II', 'I', 'N', 'C', 'CC', 'NA'];

    // Axis orderings: preserve input order.
    const evidOrder = evids.map(function (e) { return e.id; });
    const hypOrder  = hyps.map(function (h) { return h.id; });

    // Append the computed score as a synthetic dimension (displayed as a
    // text annotation row at the bottom via a second layer).
    const scoreRows = hyps.map(function (h) {
      return {
        hypothesis: h.id,
        hypothesis_label: h.label,
        score: scoring.scores[h.id],
        leading: h.id === scoring.leadingId,
      };
    });

    // The leading hypothesis gets a distinct color via a second layer's
    // axis label; but Vega-Lite axis-label styling per-tick is not
    // straightforward. We do it in post-processing (walk SVG, add the
    // `ora-visual__ach-hyp--leading` class to the matching tick-label
    // text element). Here we just return the base spec + the score-row
    // overlay.

    return {
      $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
      vconcat: [
        // Top plot: heatmap + value labels.
        {
          data: { values: rows },
          layer: [
            {
              mark: { type: 'rect', tooltip: true },
              encoding: {
                x: {
                  field: 'hypothesis', type: 'nominal',
                  sort: hypOrder,
                  title: null,
                  axis: { orient: 'top', labelAngle: 0 },
                },
                y: {
                  field: 'evidence', type: 'nominal',
                  sort: evidOrder,
                  title: null,
                },
                color: {
                  field: 'value', type: 'ordinal',
                  scale: { domain: domain, range: rangeColors },
                  legend: { title: 'Consistency' },
                },
              },
            },
            {
              mark: { type: 'text' },
              encoding: {
                x: { field: 'hypothesis', type: 'nominal', sort: hypOrder },
                y: { field: 'evidence',   type: 'nominal', sort: evidOrder },
                text: { field: 'value',   type: 'nominal' },
              },
            },
          ],
        },
        // Bottom annotation row: per-hypothesis score.
        {
          data: { values: scoreRows },
          mark: { type: 'text', baseline: 'middle' },
          encoding: {
            x: {
              field: 'hypothesis', type: 'nominal',
              sort: hypOrder,
              axis: null,
            },
            text: {
              field: 'score', type: 'quantitative',
              format: '.2f',
            },
          },
          height: 28,
        },
      ],
      resolve: { scale: { x: 'shared' } },
      config: {
        view: { stroke: null },
        axis: { grid: false },
      },
    };
  }

  // ── Vega-Lite compile + render ───────────────────────────────────────────
  function _compileAndRender(vlSpec) {
    if (typeof window.vegaLite === 'undefined' || typeof window.vega === 'undefined') {
      return Promise.reject(new Error('vega / vega-lite globals not available'));
    }
    let vgSpec;
    try {
      const compiled = window.vegaLite.compile(vlSpec);
      vgSpec = compiled && compiled.spec;
      if (!vgSpec) throw new Error('vega-lite.compile returned no .spec');
    } catch (err) { return Promise.reject(err); }

    let runtime;
    try { runtime = window.vega.parse(vgSpec); }
    catch (err) { return Promise.reject(err); }

    let view;
    try { view = new window.vega.View(runtime, { renderer: 'none' }); }
    catch (err) { return Promise.reject(err); }

    return view.toSVG();
  }

  // ── SVG post-processing ─────────────────────────────────────────────────
  /**
   * _postProcessSvg(rawSvg, envelope, spec, scoring, nondiagnosticEvidenceIds)
   *
   * Strip Vega's inline styles, apply ora-visual classes, add stable IDs
   * to every cell and every axis tick, and highlight the leading hypothesis
   * + non-diagnostic evidence rows.
   *
   * Strategy: use DOMParser (jsdom in tests, browser in production). Fall
   * back to a conservative regex strip if DOMParser is unavailable.
   */
  const STRIP_ATTRS = [
    'style', 'fill', 'stroke', 'stroke-width', 'stroke-dasharray',
    'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit',
    'font-family', 'font-size', 'font-weight', 'font-style',
    'opacity', 'fill-opacity', 'stroke-opacity',
  ];

  function _postProcessSvg(rawSvg, envelope, spec, scoring, nondiagnosticEvidenceIds) {
    const title     = (envelope.title && String(envelope.title)) || '';
    const shortAlt  = (envelope.semantic_description && envelope.semantic_description.short_alt)
      ? String(envelope.semantic_description.short_alt) : '';
    const ariaLabel = (title || 'ACH matrix') + (shortAlt ? ' — ' + shortAlt : '');

    if (typeof window !== 'undefined' && typeof window.DOMParser === 'function') {
      try {
        const parser = new window.DOMParser();
        const doc = parser.parseFromString(rawSvg, 'image/svg+xml');
        const root = doc.documentElement;
        if (root && root.nodeName && root.nodeName.toLowerCase() === 'svg') {
          _walkStrip(root);

          // Root class.
          const existingClass = root.getAttribute('class') || '';
          const cleanedExisting = existingClass
            .split(/\s+/)
            .filter(function (c) { return c && c !== 'marks'; })
            .join(' ');
          root.setAttribute('class',
            ('ora-visual ora-visual--ach_matrix' +
             (cleanedExisting ? ' ' + cleanedExisting : '')).trim());
          root.setAttribute('role', 'img');
          root.setAttribute('aria-label', ariaLabel);

          // Add data attributes identifying the leading hypothesis + method.
          root.setAttribute('data-ach-leading-hypothesis', scoring.leadingId);
          root.setAttribute('data-ach-scoring-method', scoring.method);
          root.setAttribute('data-ach-scoring-rule', scoring.rule);

          // Accessible <title>.
          let hasTitleEl = false;
          for (let i = 0; i < root.childNodes.length; i++) {
            const n = root.childNodes[i];
            if (n.nodeType === 1 && n.nodeName && n.nodeName.toLowerCase() === 'title') {
              hasTitleEl = true;
              break;
            }
          }
          if (!hasTitleEl) {
            const ns = 'http://www.w3.org/2000/svg';
            const t = doc.createElementNS ? doc.createElementNS(ns, 'title') : doc.createElement('title');
            t.setAttribute('class', 'ora-visual__accessible-title');
            t.textContent = ariaLabel;
            root.insertBefore(t, root.firstChild);
          }

          // Annotate cells + axis ticks with stable IDs.
          _annotateCells(doc, root, spec);
          _annotateAxisLabels(doc, root, spec, scoring, nondiagnosticEvidenceIds);

          if (typeof window.XMLSerializer === 'function') {
            return new window.XMLSerializer().serializeToString(root);
          }
        }
      } catch (_) {
        // Fall through.
      }
    }
    return _regexStrip(rawSvg, ariaLabel, scoring);
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

  /**
   * Walk the SVG's heatmap cell elements. Vega 6 emits rect marks as
   * <path d="M..."> elements inside <g class="mark-rect role-mark ...">,
   * each carrying an aria-label of the form
   *   aria-label="hypothesis: <H>; evidence: <E>; value: <V>"
   *
   * We match by aria-label rather than document order (which turns out
   * to be insertion-order and stable) so the mapping is robust to any
   * future Vega reordering. Fall back to document order if aria-label
   * parsing fails (unusual mark configuration).
   */
  function _annotateCells(doc, root, spec) {
    const hyps  = spec.hypotheses;
    const evids = spec.evidence;
    const cells = spec.cells;

    // Build the ordered long-form triples we expect in SVG order.
    const triples = [];
    for (let i = 0; i < evids.length; i++) {
      for (let j = 0; j < hyps.length; j++) {
        triples.push({
          evidence:   evids[i].id,
          hypothesis: hyps[j].id,
          value:      cells[evids[i].id][hyps[j].id],
        });
      }
    }

    // Find the rect-mark group (Vega class: "mark-rect role-mark ..."). The
    // cell elements inside are <path> children with role="graphics-symbol".
    const markRects = _findFirstMarkGroup(root, 'mark-rect');
    if (!markRects) return;

    // Collect cell elements: any <path> descendant whose aria-label starts
    // with "hypothesis:" and role is graphics-symbol. If aria-label is
    // absent (different Vega version), fall back to document order.
    const pathChildren = _childElements(markRects, 'path').filter(function (el) {
      const r = el.getAttribute('role');
      const lbl = el.getAttribute('aria-label') || '';
      return r === 'graphics-symbol' && /hypothesis\s*:/i.test(lbl);
    });

    if (pathChildren.length > 0) {
      // Aria-label-driven mapping: robust against Vega reordering.
      for (let k = 0; k < pathChildren.length; k++) {
        const el = pathChildren[k];
        const lbl = el.getAttribute('aria-label') || '';
        const hyp = _extractField(lbl, 'hypothesis');
        const evd = _extractField(lbl, 'evidence');
        const val = _extractField(lbl, 'value');
        if (!hyp || !evd) continue;
        el.setAttribute('id', 'ach-cell-' + evd + '-' + hyp);
        const existing = el.getAttribute('class') || '';
        const augmented = (existing + ' ora-visual__ach-cell ora-visual__ach-cell--' + (val || 'unknown')).trim();
        el.setAttribute('class', augmented);
        el.setAttribute('data-evidence-id',   evd);
        el.setAttribute('data-hypothesis-id', hyp);
        el.setAttribute('data-cell-value',    val || '');
      }
      return;
    }

    // Fallback: iterate in document order (rect or path).
    const rects = _childElements(markRects, 'rect');
    const fallback = rects.length > 0 ? rects : _childElements(markRects, 'path');
    const count = Math.min(fallback.length, triples.length);
    for (let k = 0; k < count; k++) {
      const el = fallback[k];
      const t  = triples[k];
      el.setAttribute('id', 'ach-cell-' + t.evidence + '-' + t.hypothesis);
      const existing = el.getAttribute('class') || '';
      const augmented = (existing + ' ora-visual__ach-cell ora-visual__ach-cell--' + t.value).trim();
      el.setAttribute('class', augmented);
      el.setAttribute('data-evidence-id',   t.evidence);
      el.setAttribute('data-hypothesis-id', t.hypothesis);
      el.setAttribute('data-cell-value',    t.value);
    }
  }

  // Parse a single semi-colon-delimited aria-label field. Given
  //   "hypothesis: H1; evidence: E1; value: CC"
  // and field "hypothesis", returns "H1". Trims whitespace.
  function _extractField(label, fieldName) {
    const re = new RegExp('(?:^|;)\\s*' + fieldName + '\\s*:\\s*([^;]+)', 'i');
    const m = re.exec(label);
    return m ? m[1].trim() : null;
  }

  /**
   * Walk the axis groups: x-axis (hypotheses, orient=top) and y-axis
   * (evidence). Attach ids to each tick-label <text> element matching
   * the input order. Mark the leading hypothesis column + non-diagnostic
   * evidence rows with additional classes.
   */
  function _annotateAxisLabels(doc, root, spec, scoring, nondiagnosticEvidenceIds) {
    const hyps  = spec.hypotheses;
    const evids = spec.evidence;
    const leading = scoring.leadingId;
    const ndSet = new Set(nondiagnosticEvidenceIds);

    // Vega groups axes under <g class="role-axis ..."> with a sub-group of
    // <g class="role-axis-label"> containing <text> per tick. We find all
    // role-axis groups and use heuristics to identify which is x (short, at
    // top) vs y (taller, at left). Simpler: look at the first `role-axis`
    // whose orient hint we can detect — Vega preserves the orient via a
    // class suffix `mark-text role-axis-label`. We iterate all axis-label
    // groups and tag text elements by their document order within each.
    const axisLabelGroups = _findAllByClass(root, 'role-axis-label');
    if (axisLabelGroups.length === 0) return;

    // Heuristic: the axis with `hypotheses.length` text children is the
    // x-axis (hypotheses); the axis with `evidence.length` children is
    // the y-axis. If counts are ambiguous (equal), we tag both sets per
    // the available counts.
    for (let g = 0; g < axisLabelGroups.length; g++) {
      const grp = axisLabelGroups[g];
      const texts = _childElements(grp, 'text');
      if (texts.length === hyps.length && hyps.length !== evids.length) {
        // X-axis: hypothesis labels.
        for (let i = 0; i < texts.length; i++) {
          texts[i].setAttribute('id', 'ach-hyp-' + hyps[i].id);
          let cls = texts[i].getAttribute('class') || '';
          cls = (cls + ' ora-visual__ach-hyp').trim();
          if (hyps[i].id === leading) {
            cls += ' ora-visual__ach-hyp--leading';
            texts[i].setAttribute('data-leading', 'true');
          }
          texts[i].setAttribute('class', cls);
          texts[i].setAttribute('data-hypothesis-id', hyps[i].id);
        }
      } else if (texts.length === evids.length && hyps.length !== evids.length) {
        // Y-axis: evidence labels.
        for (let i = 0; i < texts.length; i++) {
          texts[i].setAttribute('id', 'ach-evid-' + evids[i].id);
          let cls = texts[i].getAttribute('class') || '';
          cls = (cls + ' ora-visual__ach-evid').trim();
          if (ndSet.has(evids[i].id)) {
            cls += ' ora-visual__ach-evid--nondiagnostic';
            texts[i].setAttribute('data-nondiagnostic', 'true');
          }
          texts[i].setAttribute('class', cls);
          texts[i].setAttribute('data-evidence-id', evids[i].id);
        }
      } else if (texts.length === hyps.length && hyps.length === evids.length) {
        // Ambiguous square matrix. Tag this group as hypothesis on first
        // pass, evidence on second pass.
        const isFirst = (g === 0);
        if (isFirst) {
          for (let i = 0; i < texts.length; i++) {
            texts[i].setAttribute('id', 'ach-hyp-' + hyps[i].id);
            let cls = texts[i].getAttribute('class') || '';
            cls = (cls + ' ora-visual__ach-hyp').trim();
            if (hyps[i].id === leading) {
              cls += ' ora-visual__ach-hyp--leading';
              texts[i].setAttribute('data-leading', 'true');
            }
            texts[i].setAttribute('class', cls);
            texts[i].setAttribute('data-hypothesis-id', hyps[i].id);
          }
        } else {
          for (let i = 0; i < texts.length; i++) {
            texts[i].setAttribute('id', 'ach-evid-' + evids[i].id);
            let cls = texts[i].getAttribute('class') || '';
            cls = (cls + ' ora-visual__ach-evid').trim();
            if (ndSet.has(evids[i].id)) {
              cls += ' ora-visual__ach-evid--nondiagnostic';
              texts[i].setAttribute('data-nondiagnostic', 'true');
            }
            texts[i].setAttribute('class', cls);
            texts[i].setAttribute('data-evidence-id', evids[i].id);
          }
        }
      }
      // Other axis groups (eg score-row x-axis with axis:null) skipped.
    }
  }

  // ── DOM helpers (jsdom-compatible, no querySelector reliance) ────────────
  function _childElements(el, tagName) {
    const out = [];
    if (!el) return out;
    const tnLower = tagName.toLowerCase();
    // Recursive walk (Vega nests text elements several levels deep inside
    // axis groups). We collect every descendant matching the tag.
    function walk(node) {
      const children = node.childNodes || [];
      for (let i = 0; i < children.length; i++) {
        const c = children[i];
        if (c.nodeType === 1) {
          if (c.nodeName && c.nodeName.toLowerCase() === tnLower) {
            out.push(c);
          }
          walk(c);
        }
      }
    }
    walk(el);
    return out;
  }

  function _findFirstMarkGroup(root, markClass) {
    const groups = _findAllByClass(root, markClass);
    // Prefer the one that is also a role-mark (Vega's top-level marks group).
    for (let i = 0; i < groups.length; i++) {
      const cls = groups[i].getAttribute('class') || '';
      if (cls.indexOf('role-mark') !== -1) return groups[i];
    }
    return groups.length > 0 ? groups[0] : null;
  }

  function _findAllByClass(root, cls) {
    const out = [];
    function walk(node) {
      if (!node || node.nodeType !== 1) return;
      const c = node.getAttribute ? (node.getAttribute('class') || '') : '';
      if (c.split(/\s+/).indexOf(cls) !== -1) out.push(node);
      const children = node.childNodes || [];
      for (let i = 0; i < children.length; i++) walk(children[i]);
    }
    walk(root);
    return out;
  }

  function _regexStrip(svgString, ariaLabel, scoring) {
    // Very conservative fallback: no DOM parsing available.
    let out = svgString;
    for (let i = 0; i < STRIP_ATTRS.length; i++) {
      const attr = STRIP_ATTRS[i];
      const pat = new RegExp('\\s' + attr + '=(?:"[^"]*"|\'[^\']*\')', 'g');
      out = out.replace(pat, '');
    }
    out = out.replace(/<svg\b([^>]*)>/, function (_m, attrs) {
      const cleaned = attrs
        .replace(/\sclass=(?:"[^"]*"|'[^']*')/g, '')
        .replace(/\srole=(?:"[^"]*"|'[^']*')/g, '')
        .replace(/\saria-label=(?:"[^"]*"|'[^']*')/g, '');
      return '<svg' + cleaned +
        ' class="ora-visual ora-visual--ach_matrix"' +
        ' role="img"' +
        ' aria-label="' + _esc(ariaLabel) + '"' +
        ' data-ach-leading-hypothesis="' + _esc(scoring.leadingId) + '"' +
        ' data-ach-scoring-method="' + _esc(scoring.method) + '">';
    });
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

  // ── Public entry ─────────────────────────────────────────────────────────
  function render(envelope) {
    const warnings = [];
    const errors   = [];

    if (!envelope || envelope.type !== 'ach_matrix') {
      return Promise.resolve({
        svg: '',
        errors: [make(CODES.E_UNKNOWN_TYPE,
          "ach-matrix renderer called with type '" + (envelope && envelope.type) + "'",
          'type')],
        warnings: warnings,
      });
    }

    const spec = envelope.spec || {};

    // Invariant checks.
    const inv = _validateInvariants(spec);
    if (inv.errors.length > 0) {
      return Promise.resolve({ svg: '', errors: inv.errors, warnings: inv.warnings });
    }
    for (let i = 0; i < inv.warnings.length; i++) warnings.push(inv.warnings[i]);

    // Scoring.
    const scoring = _scoreHypotheses(spec, spec.scoring_method);

    // Build Vega-Lite spec + compile + render.
    let vlSpec;
    try {
      vlSpec = _buildVegaLiteSpec(spec, scoring);
    } catch (err) {
      return Promise.resolve({
        svg: '',
        errors: [make(CODES.E_DSL_PARSE,
          'ach_matrix Vega-Lite spec construction failed: ' + (err.message || err),
          'spec')],
        warnings: warnings,
      });
    }

    return _compileAndRender(vlSpec).then(
      function (rawSvg) {
        const svg = _postProcessSvg(rawSvg, envelope, spec, scoring, inv.nondiagnosticEvidenceIds);
        return { svg: svg, errors: errors, warnings: warnings };
      },
      function (err) {
        return {
          svg: '',
          errors: [make(CODES.E_DSL_PARSE,
            'ach_matrix Vega-Lite render failed: ' + (err.message || err),
            'spec')],
          warnings: warnings,
        };
      }
    );
  }

  // ── Registration ─────────────────────────────────────────────────────────
  const mod = {
    render: render,
    _internals: {
      _validateInvariants,
      _scoreHypotheses,
      _buildVegaLiteSpec,
      _cellContribution,
      CELL_ORDER,
      CREDIBILITY_WEIGHT,
    },
  };

  if (window.OraVisualCompiler &&
      typeof window.OraVisualCompiler.registerRenderer === 'function') {
    window.OraVisualCompiler.registerRenderer('ach_matrix', mod);
  }

  return mod;
}());
