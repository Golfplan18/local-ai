/**
 * ora-visual-compiler / renderers/bow-tie.js
 *
 * WP-1.3h — Bow-tie risk compiler (RISK family).
 * Hand-rolled SVG with left-right symmetric layout. No external library.
 *
 * Protocol §3.11 (v0.2). Hazard event is the center; threats render left
 * with preventive controls on the threat→event pathway; consequences render
 * right with mitigative controls on the event→consequence pathway.
 *
 * Asymmetric control vocabularies (confirmed in the Plan's ambiguity
 * resolutions — not a shared enum):
 *   preventive  ∈ {eliminate, reduce, detect}
 *   mitigative  ∈ {reduce, recover, contain}
 *
 * Contract (sync):
 *   render(envelope) → { svg, errors, warnings }
 *   Never throws. Emits semantic CSS classes only (no inline styles).
 *
 * Stable IDs for Phase-5 annotation targeting:
 *   bt-event
 *   bt-threat-<i>                       (i = 0..threats.length-1)
 *   bt-consequence-<i>                  (i = 0..consequences.length-1)
 *   bt-control-prev-<i>-<j>             (i = threat index, j = control index)
 *   bt-control-mit-<i>-<j>              (i = consequence index, j = control index)
 *   bt-arrow-threat-<i>
 *   bt-arrow-cons-<i>
 *   bt-escalation-<k>                   (k = 0..escalation_factors.length-1)
 *
 * Load order:
 *   errors.js → validator.js → renderers/stub.js → dispatcher.js → index.js →
 *   renderers/bow-tie.js
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.bowTie = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;

  // Closed vocabularies — enforced defensively even though the JSON Schema
  // already enforces them at envelope validation time.
  const PREV_TYPES = new Set(['eliminate', 'reduce', 'detect']);
  const MIT_TYPES  = new Set(['reduce', 'recover', 'contain']);

  // ── Geometry constants ─────────────────────────────────────────────────────
  const VB_W = 960;
  const VB_H = 520;
  const MARGIN_TOP = 60;
  const MARGIN_BOT = 40;

  const CENTER_X = VB_W / 2;
  const CENTER_Y = VB_H / 2;

  const THREAT_X     = Math.round(VB_W * 0.15);   // 144
  const CONS_X       = Math.round(VB_W * 0.85);   // 816
  const EVENT_HALF_W = 80;
  const EVENT_HALF_H = 34;

  const NODE_HALF_W  = 70;   // threats / consequences
  const NODE_HALF_H  = 22;

  const CONTROL_W    = 18;
  const CONTROL_H    = 30;

  // ── HTML escape ────────────────────────────────────────────────────────────
  function esc(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // ── Symmetric y distribution ───────────────────────────────────────────────
  //
  // Given a count N, return N y-coordinates distributed evenly between
  // MARGIN_TOP and (VB_H - MARGIN_BOT). Both threats and consequences use
  // this same function independently; the visual symmetry axis is x=CENTER_X.
  // When counts differ, each side is distributed over the full vertical span
  // (this is what the Plan's §3.11 diagram shows — "same y distribution …
  // adjust spacing if counts differ").
  function distributeY(n) {
    const ys = [];
    if (n <= 0) return ys;
    const top = MARGIN_TOP;
    const bot = VB_H - MARGIN_BOT;
    if (n === 1) {
      ys.push(CENTER_Y);
      return ys;
    }
    const span = bot - top;
    const step = span / (n - 1);
    for (let i = 0; i < n; i++) ys.push(Math.round(top + i * step));
    return ys;
  }

  // ── Control placement along an arrow pathway ───────────────────────────────
  //
  // Given endpoints (x1,y1) → (x2,y2) and a count of controls, return an array
  // of {x,y} positions for each control. Controls are evenly distributed in
  // the interior of the path (avoiding the endpoints) using fractions
  // 1/(n+1), 2/(n+1), …, n/(n+1). Two controls therefore land at t = 0.333
  // and 0.667 (close to the Plan's suggested 0.35 / 0.65).
  function placeControls(x1, y1, x2, y2, n) {
    const out = [];
    for (let j = 0; j < n; j++) {
      const t = (j + 1) / (n + 1);
      out.push({
        x: Math.round(x1 + (x2 - x1) * t),
        y: Math.round(y1 + (y2 - y1) * t),
        t: t,
      });
    }
    return out;
  }

  // ── Invariant checks (pre-layout) ──────────────────────────────────────────
  //
  // The JSON Schema already enforces structural presence (≥1 threat, ≥1
  // consequence, required fields, enum membership). We do defensive re-checks
  // so a mis-registered envelope or direct renderer invocation without prior
  // validation still fails cleanly with a helpful E_SCHEMA_INVALID message
  // rather than throwing.
  function checkInvariants(spec) {
    const errs = [];

    if (!spec || typeof spec !== 'object') {
      errs.push(make(CODES.E_SCHEMA_INVALID,
        'spec must be an object', 'spec'));
      return errs;
    }

    if (!spec.hazard_event || typeof spec.hazard_event !== 'object' ||
        typeof spec.hazard_event.label !== 'string' ||
        spec.hazard_event.label.length === 0) {
      errs.push(make(CODES.E_SCHEMA_INVALID,
        'spec.hazard_event.label is required and must be a non-empty string',
        'spec.hazard_event.label'));
    }

    if (!Array.isArray(spec.threats) || spec.threats.length < 1) {
      errs.push(make(CODES.E_SCHEMA_INVALID,
        'bow_tie requires at least one threat (spec.threats is empty or absent)',
        'spec.threats'));
    }

    if (!Array.isArray(spec.consequences) || spec.consequences.length < 1) {
      errs.push(make(CODES.E_SCHEMA_INVALID,
        'bow_tie requires at least one consequence ' +
        '(spec.consequences is empty or absent)',
        'spec.consequences'));
    }

    // Asymmetric control-side check.
    // Preventive controls on threat→event pathways ONLY.
    // Mitigative controls on event→consequence pathways ONLY.
    // The schema already splits these fields by the parent object shape;
    // we additionally verify that the declared `type` values fall in the
    // correct enum *for the side they were declared on*. This catches a
    // common drift — using 'recover' on a preventive control or 'detect'
    // on a mitigative control — that the envelope schema cannot express
    // as a cross-field constraint.
    if (Array.isArray(spec.threats)) {
      spec.threats.forEach((t, i) => {
        const pc = Array.isArray(t && t.preventive_controls)
          ? t.preventive_controls : [];
        pc.forEach((c, j) => {
          if (c && c.type && !PREV_TYPES.has(c.type)) {
            errs.push(make(CODES.E_SCHEMA_INVALID,
              "preventive control '" + (c.id || '?') + "' on threat '" +
              (t.id || '?') + "' declares type '" + c.type +
              "' which is not a preventive kind. Preventive controls sit on " +
              "threat→event pathways ONLY; preventive enum = " +
              '{eliminate, reduce, detect}. To render this as a mitigative ' +
              'control, move it onto a consequence.mitigative_controls entry.',
              'spec.threats[' + i + '].preventive_controls[' + j + '].type'));
          }
        });
      });
    }
    if (Array.isArray(spec.consequences)) {
      spec.consequences.forEach((c, i) => {
        const mc = Array.isArray(c && c.mitigative_controls)
          ? c.mitigative_controls : [];
        mc.forEach((ct, j) => {
          if (ct && ct.type && !MIT_TYPES.has(ct.type)) {
            errs.push(make(CODES.E_SCHEMA_INVALID,
              "mitigative control '" + (ct.id || '?') + "' on consequence '" +
              (c.id || '?') + "' declares type '" + ct.type +
              "' which is not a mitigative kind. Mitigative controls sit " +
              'on event→consequence pathways ONLY; mitigative enum = ' +
              '{reduce, recover, contain}. To render this as a preventive ' +
              'control, move it onto a threat.preventive_controls entry.',
              'spec.consequences[' + i + '].mitigative_controls[' + j + '].type'));
          }
        });
      });
    }

    return errs;
  }

  // ── SVG emitters ───────────────────────────────────────────────────────────
  function emitDefs() {
    // Two arrowhead markers — preventive (left→center) and mitigative
    // (center→right). Using separate markers makes each side's stroke
    // color follow the semantic class via currentColor in CSS.
    return [
      '  <defs>',
      '    <marker id="bt-arrow-prev" class="ora-visual__arrowhead ora-visual__arrowhead--preventive" ' +
        'viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" ' +
        'orient="auto-start-reverse">',
      '      <path d="M0,0 L10,5 L0,10 z" />',
      '    </marker>',
      '    <marker id="bt-arrow-mit" class="ora-visual__arrowhead ora-visual__arrowhead--mitigative" ' +
        'viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" ' +
        'orient="auto-start-reverse">',
      '      <path d="M0,0 L10,5 L0,10 z" />',
      '    </marker>',
      '  </defs>',
    ].join('\n');
  }

  function emitEvent(label) {
    const x = CENTER_X - EVENT_HALF_W;
    const y = CENTER_Y - EVENT_HALF_H;
    const w = EVENT_HALF_W * 2;
    const h = EVENT_HALF_H * 2;
    return [
      '  <g id="bt-event" class="ora-visual__bt-event ora-visual__hazard ora-visual__event">',
      '    <rect class="ora-visual__bt-event-shape" ' +
        'x="' + x + '" y="' + y + '" width="' + w + '" height="' + h +
        '" rx="6" ry="6" />',
      '    <text class="ora-visual__bt-event-label ora-visual__node-label" ' +
        'x="' + CENTER_X + '" y="' + CENTER_Y +
        '" text-anchor="middle" dominant-baseline="middle">' +
        esc(label) +
        '</text>',
      '  </g>',
    ].join('\n');
  }

  // Threat: triangle pointing right. Centered at (cx, cy) with NODE half-w/h.
  // The label sits to the left of the triangle so it doesn't fight with the
  // outgoing arrow tail.
  function emitThreat(threat, i, cx, cy) {
    const tipX   = cx + NODE_HALF_W;
    const baseX  = cx - NODE_HALF_W;
    const topY   = cy - NODE_HALF_H;
    const botY   = cy + NODE_HALF_H;
    const id = 'bt-threat-' + i;
    const origId = threat && threat.id ? threat.id : '';
    return [
      '  <g id="' + id + '" class="ora-visual__bt-threat ora-visual__threat" ' +
        'data-orig-id="' + esc(origId) + '">',
      '    <polygon class="ora-visual__bt-threat-shape" points="' +
        baseX + ',' + topY + ' ' + tipX + ',' + cy + ' ' + baseX + ',' + botY +
        '" />',
      '    <text class="ora-visual__bt-threat-label ora-visual__node-label" ' +
        'x="' + (cx - 2) + '" y="' + cy +
        '" text-anchor="middle" dominant-baseline="middle">' +
        esc(threat && threat.label ? threat.label : '') +
        '</text>',
      '  </g>',
    ].join('\n');
  }

  // Consequence: triangle pointing right (mirrored style per Plan). Centered
  // at (cx, cy). Since the triangle points right, the tip is at cx+NODE_HALF_W.
  function emitConsequence(cons, i, cx, cy) {
    const tipX   = cx + NODE_HALF_W;
    const baseX  = cx - NODE_HALF_W;
    const topY   = cy - NODE_HALF_H;
    const botY   = cy + NODE_HALF_H;
    const id = 'bt-consequence-' + i;
    const origId = cons && cons.id ? cons.id : '';
    return [
      '  <g id="' + id +
        '" class="ora-visual__bt-consequence ora-visual__consequence" ' +
        'data-orig-id="' + esc(origId) + '">',
      '    <polygon class="ora-visual__bt-consequence-shape" points="' +
        baseX + ',' + topY + ' ' + tipX + ',' + cy + ' ' + baseX + ',' + botY +
        '" />',
      '    <text class="ora-visual__bt-consequence-label ora-visual__node-label" ' +
        'x="' + (cx - 2) + '" y="' + cy +
        '" text-anchor="middle" dominant-baseline="middle">' +
        esc(cons && cons.label ? cons.label : '') +
        '</text>',
      '  </g>',
    ].join('\n');
  }

  // Arrow from threat node (tip at threatX + NODE_HALF_W) to event
  // (left edge of event box = CENTER_X - EVENT_HALF_W).
  function emitThreatArrow(i, threatCx, threatCy) {
    const x1 = threatCx + NODE_HALF_W;
    const y1 = threatCy;
    const x2 = CENTER_X - EVENT_HALF_W;
    const y2 = CENTER_Y;
    return '  <line id="bt-arrow-threat-' + i +
      '" class="ora-visual__bt-arrow ora-visual__bt-arrow--preventive" ' +
      'x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 +
      '" marker-end="url(#bt-arrow-prev)" />';
  }

  // Arrow from event (right edge) to consequence (base of triangle =
  // consCx - NODE_HALF_W). The arrow flows left→right mirroring the threat
  // side.
  function emitConsArrow(i, consCx, consCy) {
    const x1 = CENTER_X + EVENT_HALF_W;
    const y1 = CENTER_Y;
    const x2 = consCx - NODE_HALF_W;
    const y2 = consCy;
    return '  <line id="bt-arrow-cons-' + i +
      '" class="ora-visual__bt-arrow ora-visual__bt-arrow--mitigative" ' +
      'x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 +
      '" marker-end="url(#bt-arrow-mit)" />';
  }

  // Small barrier glyph: a rounded vertical bar with a short horizontal tick
  // across the arrow. Centered at (x, y). Classes include the kind so the
  // theme can optionally tint by effectiveness or type later.
  function emitControl(kind, side, i, j, control, x, y) {
    const half = CONTROL_W / 2;
    const h = CONTROL_H;
    const type = control && control.type ? control.type : 'unknown';
    const label = control && control.label ? control.label : '';
    const origId = control && control.id ? control.id : '';
    const id = 'bt-control-' + (side === 'preventive' ? 'prev' : 'mit') +
      '-' + i + '-' + j;

    const sideCls = side === 'preventive'
      ? 'ora-visual__control--preventive ora-visual__bt-control--preventive'
      : 'ora-visual__control--mitigative ora-visual__bt-control--mitigative';
    const kindCls = 'ora-visual__bt-control--' + side + '-' + esc(kind);

    const rx = Math.round(x - half);
    const ry = Math.round(y - h / 2);

    // Label sits below the glyph so it doesn't overlap the arrow.
    const lblY = ry + h + 12;

    return [
      '  <g id="' + id + '" class="ora-visual__bt-control ' + sideCls + ' ' +
        kindCls + '" data-orig-id="' + esc(origId) + '" ' +
        'data-kind="' + esc(kind) + '">',
      '    <rect class="ora-visual__bt-control-shape" x="' + rx +
        '" y="' + ry + '" width="' + CONTROL_W + '" height="' + h +
        '" rx="3" ry="3" />',
      // Three short vertical ticks to suggest a barrier.
      '    <line class="ora-visual__bt-control-tick" ' +
        'x1="' + (rx + 4) + '" y1="' + (ry + 4) +
        '" x2="' + (rx + 4) + '" y2="' + (ry + h - 4) + '" />',
      '    <line class="ora-visual__bt-control-tick" ' +
        'x1="' + (rx + CONTROL_W / 2) + '" y1="' + (ry + 4) +
        '" x2="' + (rx + CONTROL_W / 2) + '" y2="' + (ry + h - 4) + '" />',
      '    <line class="ora-visual__bt-control-tick" ' +
        'x1="' + (rx + CONTROL_W - 4) + '" y1="' + (ry + 4) +
        '" x2="' + (rx + CONTROL_W - 4) + '" y2="' + (ry + h - 4) + '" />',
      '    <text class="ora-visual__bt-control-label" x="' + x +
        '" y="' + lblY + '" text-anchor="middle">' +
        esc(label) + '</text>',
      '  </g>',
    ].join('\n');
  }

  // Escalation factors — optional, rendered as dashed lines linking a
  // named control to a small box annotating the escalation condition.
  // Escalation factors are rendered at the bottom of the diagram to
  // avoid interfering with the main symmetric layout.
  function emitEscalations(spec, controlIndex) {
    const factors = Array.isArray(spec.escalation_factors)
      ? spec.escalation_factors : [];
    if (factors.length === 0) return '';
    const parts = ['  <g class="ora-visual__bt-escalations">'];
    factors.forEach((f, k) => {
      if (!f || typeof f !== 'object') return;
      const target = controlIndex[f.from_control_id];
      if (!target) return;  // skip unresolved silently; not a blocking issue
      const id = 'bt-escalation-' + k;
      const boxY = VB_H - 20;
      const boxX = target.x;
      parts.push(
        '    <g id="' + id + '" class="ora-visual__bt-escalation ora-visual__escalation">',
        '      <line class="ora-visual__bt-escalation-line" x1="' + target.x +
          '" y1="' + (target.y + CONTROL_H / 2) +
          '" x2="' + boxX + '" y2="' + boxY + '" />',
        '      <text class="ora-visual__bt-escalation-label" x="' + boxX +
          '" y="' + boxY + '" text-anchor="middle">' +
          esc(f.label || '') +
          '</text>',
        '    </g>'
      );
    });
    parts.push('  </g>');
    return parts.join('\n');
  }

  // ── render entry point ─────────────────────────────────────────────────────
  function render(envelope) {
    const errors = [];
    const warnings = [];

    if (!envelope || typeof envelope !== 'object') {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'envelope must be an object', ''));
      return { svg: '', errors: errors, warnings: warnings };
    }

    const spec = envelope.spec;
    const invariantErrs = checkInvariants(spec);
    if (invariantErrs.length > 0) {
      return { svg: '', errors: invariantErrs, warnings: warnings };
    }

    // Accessible label
    const title = envelope.title || 'Bow-tie risk diagram';
    const sd = envelope.semantic_description;
    const gist = sd && (sd.level_1_elemental || sd.short_alt);
    const ariaLabel = gist ? (title + ' — ' + gist) : title;

    // Compute positions
    const threats = spec.threats;
    const conseqs = spec.consequences;
    const threatYs = distributeY(threats.length);
    const consYs   = distributeY(conseqs.length);

    // Build control index for escalation resolution.
    const controlIndex = {};

    // ── Emit body ────────────────────────────────────────────────────────────
    const parts = [];

    parts.push(emitDefs());

    // Arrows first so nodes overlay them cleanly.
    const arrowParts = [];
    const controlParts = [];

    threats.forEach((t, i) => {
      const cy = threatYs[i];
      arrowParts.push(emitThreatArrow(i, THREAT_X, cy));
      // Preventive controls along the threat→event pathway.
      const pcs = Array.isArray(t.preventive_controls) ? t.preventive_controls : [];
      if (pcs.length > 0) {
        const x1 = THREAT_X + NODE_HALF_W;
        const y1 = cy;
        const x2 = CENTER_X - EVENT_HALF_W;
        const y2 = CENTER_Y;
        const places = placeControls(x1, y1, x2, y2, pcs.length);
        pcs.forEach((c, j) => {
          const pos = places[j];
          controlParts.push(emitControl(c.type || 'unknown',
            'preventive', i, j, c, pos.x, pos.y));
          if (c && c.id) {
            controlIndex[c.id] = { x: pos.x, y: pos.y };
          }
        });
      }
    });

    conseqs.forEach((c, i) => {
      const cy = consYs[i];
      arrowParts.push(emitConsArrow(i, CONS_X, cy));
      // Mitigative controls along the event→consequence pathway.
      const mcs = Array.isArray(c.mitigative_controls) ? c.mitigative_controls : [];
      if (mcs.length > 0) {
        const x1 = CENTER_X + EVENT_HALF_W;
        const y1 = CENTER_Y;
        const x2 = CONS_X - NODE_HALF_W;
        const y2 = cy;
        const places = placeControls(x1, y1, x2, y2, mcs.length);
        mcs.forEach((ct, j) => {
          const pos = places[j];
          controlParts.push(emitControl(ct.type || 'unknown',
            'mitigative', i, j, ct, pos.x, pos.y));
          if (ct && ct.id) {
            controlIndex[ct.id] = { x: pos.x, y: pos.y };
          }
        });
      }
    });

    parts.push('  <g class="ora-visual__bt-arrows">');
    parts.push(arrowParts.join('\n'));
    parts.push('  </g>');

    parts.push('  <g class="ora-visual__bt-controls">');
    parts.push(controlParts.join('\n'));
    parts.push('  </g>');

    // Threat + consequence nodes overlay the arrows.
    parts.push('  <g class="ora-visual__bt-threats">');
    threats.forEach((t, i) => {
      parts.push(emitThreat(t, i, THREAT_X, threatYs[i]));
    });
    parts.push('  </g>');

    parts.push('  <g class="ora-visual__bt-consequences">');
    conseqs.forEach((c, i) => {
      parts.push(emitConsequence(c, i, CONS_X, consYs[i]));
    });
    parts.push('  </g>');

    // Central event on top (so it visually dominates the pivot).
    parts.push(emitEvent(spec.hazard_event.label));

    // Optional escalation factors at the end (so they sit below everything).
    const escalations = emitEscalations(spec, controlIndex);
    if (escalations) parts.push(escalations);

    // Title caption on top of the diagram.
    const titleBlock = envelope.title
      ? '  <text class="ora-visual__title" x="' + CENTER_X + '" y="24" ' +
          'text-anchor="middle">' + esc(envelope.title) + '</text>'
      : '';

    const svg = [
      '<svg xmlns="http://www.w3.org/2000/svg"',
      '     class="ora-visual ora-visual--bow_tie"',
      '     role="img"',
      '     aria-label="' + esc(ariaLabel) + '"',
      '     viewBox="0 0 ' + VB_W + ' ' + VB_H + '">',
      '  <title class="ora-visual__accessible-title">' +
        esc(ariaLabel) + '</title>',
      titleBlock,
      parts.join('\n'),
      '</svg>',
    ].filter(function (s) { return s !== ''; }).join('\n');

    return { svg: svg, errors: errors, warnings: warnings };
  }

  // ── Register with compiler ─────────────────────────────────────────────────
  if (window.OraVisualCompiler.registerRenderer) {
    window.OraVisualCompiler.registerRenderer('bow_tie', { render: render });
  } else if (window.OraVisualCompiler._dispatcher &&
             window.OraVisualCompiler._dispatcher.register) {
    window.OraVisualCompiler._dispatcher.register('bow_tie', { render: render });
  }

  return { render: render };

}());
