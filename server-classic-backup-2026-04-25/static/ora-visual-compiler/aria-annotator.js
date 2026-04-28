/**
 * ora-visual-compiler / aria-annotator.js
 *
 * WP-1.5 — Accessibility layer (module 2 of 3): element-level ARIA walker.
 *
 * Walks the compiled SVG (as a string; DOM-free) and adds ARIA attributes to
 * every semantic group element that doesn't already have them. Decorative
 * markers and defs get aria-hidden.
 *
 * Contract (pure transformation):
 *   annotate(svgString) → svgString
 *
 * Role assignment heuristic (Protocol §8.3 + WAI-ARIA graphics module):
 *
 *   "graphics-datapoint"  — for <g> whose semantic class designates a single
 *                           datum or cell: ora-visual__cell, ora-visual__bar,
 *                           ora-visual__item, ora-visual__quadrant-item,
 *                           ora-visual__ach-cell, ora-visual__point,
 *                           ora-visual__datapoint. Also generic <g> with
 *                           role="graphics-datapoint" already set by Vega.
 *
 *   "graphics-symbol"     — for <g> whose semantic class designates a node,
 *                           stock, concept, entity, or any compound visual
 *                           element (nodes, edges, loops, categories, clusters,
 *                           containers, etc.). The default for semantic-group
 *                           elements.
 *
 *   "presentation"        — for <g> whose only purpose is layout grouping:
 *                           axis, legend, gridline, tick, background, frame,
 *                           and any <g class="mark-group role-frame">-style
 *                           Vega containers.
 *
 *   aria-hidden="true"    — on <defs>, <marker>, <mask>, <clipPath>, and on
 *                           <g class="ora-visual__decoration"> and similar.
 *                           Does not strip anything that's already there.
 *
 * Does not strip existing attributes — only ADDS when absent. Calls are
 * idempotent.
 *
 * Load order: after alt-text-generator.js.
 *
 * Depends on: nothing.
 */

(function (global) {
  var ns = global.OraVisualCompiler = global.OraVisualCompiler || {};
  ns.accessibility = ns.accessibility || {};

  // ── Class-based role heuristics ──────────────────────────────────────────
  //
  // Ordered from most-specific to most-generic. The FIRST match wins.
  //
  // Why class-based and not tag-based: every renderer we ship produces
  // semantic classes on <g> wrappers. Vega-Lite additionally emits
  // role/aria-label already; we preserve those. viz-js emits <g class="node">
  // and <g class="edge"> with <title> children; those are our graphics-symbol
  // targets. Mermaid emits <g class="node">, <g class="edgePaths">,
  // <g class="cluster">; cluster is a presentation container for a subgraph.

  var ROLE_RULES = [
    // Datapoint patterns: a single cell / bar / item / point.
    { role: 'graphics-datapoint', cls: /\bora-visual__(?:cell|ach-cell|bar|point|datapoint|item|quadrant-item)\b/ },

    // Hidden / decorative patterns (set both aria-hidden and role=presentation
    // for maximum screen-reader compatibility).
    { role: 'presentation',       cls: /\bora-visual__(?:decoration|background|frame|gridline|legend-swatch|axis-tick|axis-line|spine|marker-guide)\b/, hide: true },

    // Semantic symbol patterns — the catch-all for nodes / edges / loops /
    // categories / containers / stocks / clouds / items with composite
    // geometry.
    { role: 'graphics-symbol', cls: /\bora-visual__(?:node|edge|loop|category|cluster|container|stock|flow|cloud|auxiliary|concept|proposition|linking-phrase|hypothesis|evidence|quadrant|threat|consequence|control|preventive|mitigative|hazard|escalation|effect|cause|sub-bone|branch|leaf|argument|idea|question|pro|con|pathway|actor|message|state|transition|swimlane|person|software-system|decision|chance|terminal|value|informational|functional|relevance|fb-effect|fb-category|fb-cause)\b/ },

    // viz-js / Graphviz default classes.
    { role: 'graphics-symbol', cls: /\b(?:node|edge|cluster|graph)\b/, onlyPlain: true },
  ];

  // Presentation patterns for Vega-Lite: role="frame" or aria-roledescription="group mark container".
  var VEGA_PRESENTATION = /\bmark-group\b.*\brole-frame\b/;
  var VEGA_AXIS         = /\bmark-group\b.*\brole-axis\b/;
  var VEGA_LEGEND       = /\bmark-group\b.*\brole-legend\b/;

  // Elements that are always decorative.
  var ALWAYS_HIDDEN_TAGS = { defs: true, marker: true, mask: true, clippath: true, pattern: true };

  // ── helpers ──────────────────────────────────────────────────────────────
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function hasAttr(tagSrc, attr) {
    var re = new RegExp('[\\s<](?:' + attr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') +
                        ')\\s*=', 'i');
    return re.test(tagSrc);
  }

  function getAttr(tagSrc, attr) {
    var re = new RegExp('\\b' + attr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') +
                        '\\s*=\\s*"([^"]*)"', 'i');
    var m = re.exec(tagSrc);
    return m ? m[1] : null;
  }

  function addAttr(tagSrc, attr, value) {
    if (hasAttr(tagSrc, attr)) return tagSrc;
    if (/\/\s*>$/.test(tagSrc)) {
      return tagSrc.replace(/\/\s*>$/, ' ' + attr + '="' + esc(value) + '" />');
    }
    return tagSrc.replace(/>$/, ' ' + attr + '="' + esc(value) + '">');
  }

  /**
   * Derive a human-readable aria-label from a group's context. Strategy:
   * 1. If the <g> carries a data-label attribute, use it.
   * 2. Else find the first <text> descendant (naive regex) and use its text.
   * 3. Else find the first <title> descendant and use its text.
   * 4. Else fall back to the group's id attribute (sans prefix).
   */
  function synthesizeLabel(tagSrc, innerFragment) {
    // 1. data-label or aria-roledescription on the tag itself.
    var dl = getAttr(tagSrc, 'data-label') || getAttr(tagSrc, 'aria-roledescription');
    if (dl) return stripHtml(dl);

    // 2. first <text>...</text> in the inner fragment.
    if (innerFragment) {
      var tm = /<text\b[^>]*>([\s\S]*?)<\/text>/i.exec(innerFragment);
      if (tm && tm[1]) {
        var txt = stripHtml(tm[1]).trim();
        if (txt) return txt;
      }
      // 3. <title>...</title> child.
      var tim = /<title\b[^>]*>([\s\S]*?)<\/title>/i.exec(innerFragment);
      if (tim && tim[1]) {
        var tt = stripHtml(tim[1]).trim();
        if (tt) return tt;
      }
    }

    // 4. id attribute.
    var id = getAttr(tagSrc, 'id');
    if (id) {
      // "cld-node-Velocity" → "Velocity".
      return id.replace(/^[a-z]+-(?:node|edge|loop|cell|cat|category|cause)-/i, '')
               .replace(/[-_]/g, ' ');
    }
    return '';
  }

  function stripHtml(s) {
    return String(s).replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
  }

  // ── SVG walker (string-level, depth-aware) ────────────────────────────────
  //
  // We don't build a DOM. We scan tag-by-tag, tracking a stack of parent
  // tags, so we can skip <defs> / <marker> subtrees (everything inside gets
  // aria-hidden via inheritance — no rewrite needed on children) and detect
  // whether a <title> or <text> child belongs to a <g> we're annotating.
  //
  // Output is a rewritten string. We keep the original source verbatim
  // everywhere except on <g> / <defs> / <marker> / <mask> / <clipPath>
  // opening tags.

  function annotate(svgString) {
    if (typeof svgString !== 'string' || svgString.length === 0) return svgString;

    var out = [];
    var i = 0;
    var n = svgString.length;
    var stack = [];  // array of { name, start }

    while (i < n) {
      var lt = svgString.indexOf('<', i);
      if (lt < 0) { out.push(svgString.slice(i)); break; }
      out.push(svgString.slice(i, lt));

      var gt = svgString.indexOf('>', lt);
      if (gt < 0) { out.push(svgString.slice(lt)); break; }

      var tag = svgString.slice(lt, gt + 1);
      var isComment = tag.slice(0, 4) === '<!--';
      if (isComment) {
        // Move to matching '-->' if present.
        var end = svgString.indexOf('-->', lt);
        if (end < 0) { out.push(svgString.slice(lt)); break; }
        out.push(svgString.slice(lt, end + 3));
        i = end + 3;
        continue;
      }

      var isClose = tag.charAt(1) === '/';
      var isSelfClose = /\/\s*>$/.test(tag);
      var nameMatch = /^<\/?\s*([A-Za-z][A-Za-z0-9_-]*)/.exec(tag);
      var name = nameMatch ? nameMatch[1].toLowerCase() : '';

      if (isClose) {
        // Pop stack if it matches.
        if (stack.length && stack[stack.length - 1].name === name) {
          stack.pop();
        }
        out.push(tag);
        i = gt + 1;
        continue;
      }

      // Opening tag (possibly self-closing). Decide if we rewrite it.
      var rewritten = maybeRewriteTag(tag, name, svgString, gt + 1);
      out.push(rewritten);

      if (!isSelfClose) {
        stack.push({ name: name, start: gt + 1 });
      }

      i = gt + 1;
    }

    return out.join('');
  }

  /**
   * Decide role / aria-label / aria-hidden for the given opening tag and
   * return the rewritten tag (unchanged if no rules apply).
   *
   * bodyStart: index in src just past the current tag's '>'. Used to grab
   * the next <text> or <title> descendant for label synthesis.
   */
  function maybeRewriteTag(tag, name, src, bodyStart) {
    // Always-hidden tags: set aria-hidden="true" if not already.
    if (ALWAYS_HIDDEN_TAGS[name]) {
      if (!hasAttr(tag, 'aria-hidden')) {
        tag = addAttr(tag, 'aria-hidden', 'true');
      }
      return tag;
    }

    // Only rewrite <g> elements (the semantic grouping atom).
    if (name !== 'g') return tag;

    // Preserve any existing role / aria-label on the <g>.
    var hasRole    = hasAttr(tag, 'role');
    var hasLabel   = hasAttr(tag, 'aria-label');
    var hasHide    = hasAttr(tag, 'aria-hidden');
    var hasRoleDsc = hasAttr(tag, 'aria-roledescription');

    // Aria-roledescription (e.g., Vega-Lite's "symbol mark container")
    // counts as a screen-reader-visible label for this purpose.
    var hasReadableLabel = hasLabel || hasHide || hasRoleDsc;

    // If the <g> already has role AND a readable label, leave it.
    if (hasRole && hasReadableLabel) return tag;

    var cls = getAttr(tag, 'class') || '';

    // Vega-Lite specific patterns (presentation / axis / legend).
    if (VEGA_PRESENTATION.test(cls) || VEGA_AXIS.test(cls) || VEGA_LEGEND.test(cls)) {
      if (!hasRole) tag = addAttr(tag, 'role', 'presentation');
      return tag;
    }

    // Apply class-based rules in order.
    for (var r = 0; r < ROLE_RULES.length; r++) {
      var rule = ROLE_RULES[r];
      if (rule.onlyPlain) {
        // Only match if the <g>'s classes don't include any ora-visual__*
        // already (prefer our own classes over generic Graphviz classes).
        if (/\bora-visual__/.test(cls)) continue;
      }
      if (rule.cls.test(cls)) {
        if (!hasRole) tag = addAttr(tag, 'role', rule.role);
        if (rule.hide && !hasHide) tag = addAttr(tag, 'aria-hidden', 'true');
        if (!hasLabel && !rule.hide) {
          // Synthesize a label from descendants.
          var bodyEnd = findMatchingClose(src, bodyStart, 'g');
          var inner   = bodyEnd > bodyStart ? src.slice(bodyStart, bodyEnd) : '';
          var label   = synthesizeLabel(tag, inner);
          if (label) tag = addAttr(tag, 'aria-label', label);
        }
        return tag;
      }
    }

    // A <g> with an id= and no class match: give it a graphics-symbol role
    // and try to synthesize a label. This catches renderer-quirks paths
    // where a renderer emits `<g id="…">` without a themed class (e.g.
    // viz-js `<g class="node" id="node1">` which matches the onlyPlain rule
    // above — but also `<g id="...">` root groups).
    if (getAttr(tag, 'id')) {
      if (!hasRole) tag = addAttr(tag, 'role', 'graphics-symbol');
      if (!hasLabel) {
        var bodyEnd2 = findMatchingClose(src, bodyStart, 'g');
        var inner2   = bodyEnd2 > bodyStart ? src.slice(bodyStart, bodyEnd2) : '';
        var label2   = synthesizeLabel(tag, inner2);
        if (label2) tag = addAttr(tag, 'aria-label', label2);
      }
    }

    return tag;
  }

  /**
   * Find the index just before </name> that matches the currently-open name
   * element starting at position `from`. Handles nested <name> elements.
   * Returns -1 if not found.
   */
  function findMatchingClose(src, from, name) {
    var depth = 1;
    var i = from;
    var openRe  = new RegExp('<\\s*' + name + '\\b', 'i');
    var closeRe = new RegExp('<\\s*\\/\\s*' + name + '\\s*>', 'i');
    while (i < src.length && depth > 0) {
      openRe.lastIndex = i;
      closeRe.lastIndex = i;
      var o = src.slice(i).search(openRe);
      var c = src.slice(i).search(closeRe);
      if (c < 0) return -1;
      if (o >= 0 && o < c) {
        // Found nested open before next close — only counts if not self-
        // closing. Find its end '>' and check.
        var openStart = i + o;
        var openEnd = src.indexOf('>', openStart);
        if (openEnd < 0) return -1;
        var openTag = src.slice(openStart, openEnd + 1);
        if (!/\/\s*>$/.test(openTag)) depth++;
        i = openEnd + 1;
      } else {
        // Next significant thing is a close.
        depth--;
        if (depth === 0) return i + c;   // position of '<' in close tag
        i = i + c + ('</' + name + '>').length;
      }
    }
    return -1;
  }

  // ── Public surface ────────────────────────────────────────────────────────
  ns.accessibility.annotateAria = annotate;

  // Expose internal helpers for unit testing.
  ns.accessibility._ariaInternals = {
    synthesizeLabel:   synthesizeLabel,
    maybeRewriteTag:   maybeRewriteTag,
    findMatchingClose: findMatchingClose,
    ROLE_RULES:        ROLE_RULES,
  };
}(typeof window !== 'undefined' ? window : globalThis));
