/**
 * ora-visual-compiler / alt-text-generator.js
 *
 * WP-1.5 — Accessibility layer (module 1 of 3): envelope-aware SVG decorator.
 *
 * Reads envelope.semantic_description (Lundgard-Satyanarayan four-level
 * description, per Protocol §8) and injects / upgrades the <title> and <desc>
 * nodes inside the root <svg>. Wires the root svg's aria-labelledby and
 * aria-describedby attributes to those generated element IDs.
 *
 * Contract (pure transformation):
 *   decorate(svgString, envelope) → svgString
 *
 * Rules:
 *   - <title> text === envelope.semantic_description.short_alt (≤ 150 chars by schema).
 *   - <desc> text === concatenation of level_1_elemental + level_2_statistical +
 *     level_3_perceptual + (level_4_contextual if non-null), joined with '\n'.
 *     When relation_to_prose === 'redundant', levels 2-4 may be the literal
 *     string "See surrounding prose." — we copy whatever the envelope contains.
 *   - Root <svg> gets role="img" if not already present.
 *   - Root <svg> gets aria-labelledby="<title-id>" aria-describedby="<desc-id>".
 *   - If the renderer already emitted a <title> or <desc> as a direct child of
 *     the root <svg>, we REPLACE them (not duplicate). The stub renderer and
 *     many of the real renderers inject a <title class="ora-visual__accessible-title">
 *     from the short_alt or a type label; this module is the authoritative
 *     source and overwrites.
 *   - If the root <svg> already has aria-labelledby / aria-describedby we
 *     append the generated IDs (schema-consistent with WAI-ARIA's space-
 *     separated ID list).
 *   - No DOM library required; we operate on SVG source text so this module
 *     works in jsdom, worker contexts, and offline serialization paths.
 *
 * Load order:
 *   errors.js → validator.js → renderers/stub.js → dispatcher.js → index.js →
 *   <vendor libs> → palettes.js → dot-engine.js → ajv-init.js →
 *   <all renderers> →
 *   alt-text-generator.js
 *
 * Depends on: nothing (pure regex-and-string transformation).
 */

(function (global) {
  var ns = global.OraVisualCompiler = global.OraVisualCompiler || {};
  ns.accessibility = ns.accessibility || {};

  // ── helpers ────────────────────────────────────────────────────────────────
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /**
   * Deterministic ID generator. Uses envelope.id when present so two calls
   * against the same envelope produce identical output (important for
   * hash-based sidecar invalidation in WP-6.1).
   */
  function makeIds(envelope) {
    var base = (envelope && envelope.id) ? String(envelope.id) : 'ora-visual';
    // sanitize to match HTML5 id grammar (letters/digits/hyphens).
    base = base.replace(/[^A-Za-z0-9_-]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
    if (!base) base = 'ora-visual';
    return {
      titleId: base + '-a11y-title',
      descId:  base + '-a11y-desc',
    };
  }

  /**
   * Assemble the <desc> body text. Joins levels 1-3 (required by schema)
   * plus level 4 if present and non-null. Preserves literal '\n' separators
   * so screen readers render them as paragraph breaks.
   */
  function buildDescText(sd) {
    if (!sd || typeof sd !== 'object') return '';
    var lines = [];
    if (sd.level_1_elemental)   lines.push(String(sd.level_1_elemental));
    if (sd.level_2_statistical) lines.push(String(sd.level_2_statistical));
    if (sd.level_3_perceptual)  lines.push(String(sd.level_3_perceptual));
    if (sd.level_4_contextual)  lines.push(String(sd.level_4_contextual));
    return lines.join('\n');
  }

  /**
   * Find the opening root <svg ...> tag in the source and return its position
   * range and the index just past the closing '>'. Returns null if no svg
   * root is found (caller should leave input unchanged).
   */
  function findSvgOpenTag(src) {
    // First <svg...>; match including trailing '>'. DOES NOT match '<svg'
    // inside comments — renderer outputs don't include comments inside the
    // pre-root area in practice.
    var m = /<svg\b[^>]*>/i.exec(src);
    if (!m) return null;
    return { start: m.index, end: m.index + m[0].length, tag: m[0] };
  }

  /**
   * Attribute presence test on an opening tag. tagSrc is the full open tag
   * string starting '<svg' and ending '>'.
   */
  function hasAttr(tagSrc, attr) {
    // Word-boundary-safe: require whitespace (or '<svg') before the attribute
    // name and '=' after.
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

  /**
   * Set or merge an attribute on the opening <svg ...> tag. If the attribute
   * already exists, merge values (space-separated) — this is what WAI-ARIA
   * requires for aria-labelledby / aria-describedby when a root already has
   * references.
   */
  function setOrMergeAttr(tagSrc, attr, value, merge) {
    if (hasAttr(tagSrc, attr)) {
      if (!merge) return tagSrc;   // caller said not to merge; leave alone.
      var existing = getAttr(tagSrc, attr);
      if (existing == null) return tagSrc;
      // Avoid duplicating tokens.
      var tokens = existing.split(/\s+/).filter(Boolean);
      var newTokens = String(value).split(/\s+/).filter(Boolean);
      for (var i = 0; i < newTokens.length; i++) {
        if (tokens.indexOf(newTokens[i]) < 0) tokens.push(newTokens[i]);
      }
      var merged = tokens.join(' ');
      return tagSrc.replace(
        new RegExp('(\\b' + attr + '\\s*=\\s*")([^"]*)(")', 'i'),
        '$1' + esc(merged).replace(/\$/g, '$$$$') + '$3'
      );
    }
    // Attribute absent: insert just before the closing '>' (or '/>' for
    // self-closing — no real renderer emits a self-closing root svg, but
    // defensively handle both).
    if (/\/\s*>$/.test(tagSrc)) {
      return tagSrc.replace(/\/\s*>$/, ' ' + attr + '="' + esc(value) + '" />');
    }
    return tagSrc.replace(/>$/, ' ' + attr + '="' + esc(value) + '">');
  }

  /**
   * Remove any existing direct-child <title> and <desc> inside the root svg.
   * We walk forward from the end of the opening tag, track depth across
   * nested <svg>s (rare but possible), and only strip top-level direct
   * children.
   *
   * Returns { content: rewrittenSvgBody, strippedTitle: bool, strippedDesc: bool }.
   */
  function stripDirectTitleDesc(svgBody) {
    // Find first-level <title> and <desc>. Strategy: scan for <title or <desc
    // at depth 0. Depth is incremented on <svg ...> (non-self-closing) and
    // decremented on </svg>.
    var out = [];
    var i = 0;
    var depth = 0;
    var strippedTitle = false;
    var strippedDesc  = false;
    var n = svgBody.length;

    while (i < n) {
      var lt = svgBody.indexOf('<', i);
      if (lt < 0) { out.push(svgBody.slice(i)); break; }
      out.push(svgBody.slice(i, lt));
      // What tag?
      var gt = svgBody.indexOf('>', lt);
      if (gt < 0) { out.push(svgBody.slice(lt)); break; }
      var tag = svgBody.slice(lt, gt + 1);

      // Depth tracking
      var isClose = tag.charAt(1) === '/';
      var isSelfClose = /\/\s*>$/.test(tag);
      var nameMatch = /^<\/?\s*([A-Za-z][A-Za-z0-9_-]*)/.exec(tag);
      var name = nameMatch ? nameMatch[1].toLowerCase() : '';

      // Top-level direct child: depth === 0 BEFORE we open. If tag is
      // <title> or <desc> at depth 0 AND it is a child of the root svg
      // (we're after the opening <svg>), strip it along with its content
      // and closing tag.
      if (depth === 0 && !isClose && (name === 'title' || name === 'desc')) {
        // Find matching closing tag for this element; title/desc should not
        // nest themselves, so we can do a simple search for </title> or </desc>.
        var closeTag = '</' + name;
        var closeIdx = svgBody.indexOf(closeTag, gt + 1);
        if (closeIdx < 0) {
          // malformed; leave as-is.
          out.push(tag);
          i = gt + 1;
          continue;
        }
        var closeEnd = svgBody.indexOf('>', closeIdx);
        if (closeEnd < 0) {
          out.push(tag);
          i = gt + 1;
          continue;
        }
        if (name === 'title') strippedTitle = true;
        else                  strippedDesc  = true;
        i = closeEnd + 1;
        continue;
      }

      // Generic depth handling for <svg>.
      if (name === 'svg') {
        if (isClose)        depth--;
        else if (!isSelfClose) depth++;
      }

      out.push(tag);
      i = gt + 1;
    }

    return {
      content:        out.join(''),
      strippedTitle:  strippedTitle,
      strippedDesc:   strippedDesc,
    };
  }

  /**
   * decorate(svgString, envelope) → svgString
   *
   * Public API. Idempotent-ish: two calls against the same (svg, envelope)
   * produce the same output because we first strip any existing root-level
   * title/desc and then re-emit with deterministic IDs.
   *
   * If the input cannot be parsed (no <svg> root found), returns the input
   * unchanged. This mirrors the compiler's "never throw" contract.
   */
  function decorate(svgString, envelope) {
    if (typeof svgString !== 'string' || svgString.length === 0) return svgString;
    if (!envelope || typeof envelope !== 'object') return svgString;
    var sd = envelope.semantic_description;
    if (!sd) return svgString;

    var open = findSvgOpenTag(svgString);
    if (!open) return svgString;

    var ids        = makeIds(envelope);
    var titleText  = sd.short_alt || envelope.title || '';
    var descText   = buildDescText(sd);

    // 1. Rewrite opening tag: add role="img" if absent; aria-labelledby /
    //    aria-describedby (merge with any existing).
    var newTag = open.tag;
    if (!hasAttr(newTag, 'role')) {
      newTag = setOrMergeAttr(newTag, 'role', 'img', false);
    }
    newTag = setOrMergeAttr(newTag, 'aria-labelledby',  ids.titleId, true);
    newTag = setOrMergeAttr(newTag, 'aria-describedby', ids.descId,  true);

    // 2. Slice out the current body between <svg ...> and </svg>, strip any
    //    existing top-level <title> / <desc>, then re-insert fresh ones at
    //    the top.
    var bodyStart = open.end;
    // closing </svg> of the root. Scan back from the end.
    var lastClose = svgString.toLowerCase().lastIndexOf('</svg>');
    if (lastClose < 0 || lastClose < bodyStart) {
      // malformed; give up gracefully.
      return svgString;
    }
    var body    = svgString.slice(bodyStart, lastClose);
    var closing = svgString.slice(lastClose);

    var stripped = stripDirectTitleDesc(body);

    var titleEl = '<title id="' + ids.titleId + '" class="ora-visual__a11y-title">' +
                  esc(titleText) + '</title>';
    var descEl  = '<desc id="'  + ids.descId  + '" class="ora-visual__a11y-desc">'  +
                  esc(descText) + '</desc>';

    var rebuiltBody = titleEl + descEl + stripped.content;

    return svgString.slice(0, open.start) + newTag + rebuiltBody + closing;
  }

  // ── Public surface ────────────────────────────────────────────────────────
  ns.accessibility.decorateAltText = decorate;

  // Expose internal helpers for unit testing.
  ns.accessibility._altTextInternals = {
    makeIds:             makeIds,
    buildDescText:       buildDescText,
    findSvgOpenTag:      findSvgOpenTag,
    stripDirectTitleDesc: stripDirectTitleDesc,
    setOrMergeAttr:      setOrMergeAttr,
  };
}(typeof window !== 'undefined' ? window : globalThis));
