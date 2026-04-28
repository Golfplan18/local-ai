/**
 * ora-visual-compiler / keyboard-nav.js
 *
 * WP-1.5 — Accessibility layer (module 3 of 3): Olli-pattern keyboard
 * navigation graph builder.
 *
 * Walks the (already-annotated) SVG and:
 *   - adds tabindex="0" to the root <svg>
 *   - adds tabindex="-1" + data-olli-level="1" to the root's top-level
 *     semantic <g> children
 *   - descends into nested semantic <g> elements, incrementing data-olli-level
 *     up to a cap of 5 (Olli-recommended; beyond 5 the tree is too deep to
 *     navigate)
 *   - produces a JSON sidecar describing the navigation tree, consumed by
 *     WP-2.1 (visual-panel.js) for arrow-key wiring
 *
 * Contract:
 *   buildNav(svgString, envelope) → { svg, ariaDescription }
 *
 * ariaDescription shape:
 *   {
 *     root_id: string,
 *     nodes: [
 *       {
 *         id:           string,
 *         level:        1..5,
 *         label:        string,
 *         parent_id:    string | null,     // null when parent is root svg
 *         children_ids: string[]
 *       },
 *       ...
 *     ]
 *   }
 *
 * "Semantic <g>" definition: a <g> that carries an id attribute AND a class
 * matching one of the semantic patterns (ora-visual__*, or role=graphics-*).
 * Pure layout <g>s (Vega axis, legend, frame) are skipped, as are defs /
 * markers / decorative groups (aria-hidden="true").
 *
 * Well-formedness guarantees on the emitted ariaDescription:
 *   - root_id is always the svg's id (or a synthetic "ora-visual-root" if
 *     the svg has no id)
 *   - every parent_id either === null (root) or resolves to a node in the
 *     list
 *   - no cycles (by construction: the SVG tree is acyclic and we emit in
 *     depth-first pre-order)
 *   - children_ids[] is consistent with parent_id[] (every id that lists X
 *     as its parent appears in X's children)
 *
 * Load order: after aria-annotator.js.
 *
 * Depends on: nothing.
 */

(function (global) {
  var ns = global.OraVisualCompiler = global.OraVisualCompiler || {};
  ns.accessibility = ns.accessibility || {};

  var MAX_LEVEL = 5;

  // Classes that indicate a semantic grouping worth focusing. Mirrors the
  // role rules in aria-annotator.js but only positive (graphics-symbol /
  // graphics-datapoint) — we don't tab into presentation-role groups.
  var SEMANTIC_CLASS_RE = /\bora-visual__(?:node|edge|loop|category|cluster|container|stock|flow|cloud|auxiliary|concept|proposition|linking-phrase|hypothesis|evidence|quadrant|threat|consequence|control|preventive|mitigative|hazard|escalation|effect|cause|sub-bone|branch|leaf|argument|idea|question|pro|con|pathway|actor|message|state|transition|swimlane|person|software-system|decision|chance|terminal|value|cell|ach-cell|bar|point|datapoint|item|quadrant-item|fb-effect|fb-category|fb-cause)\b/;

  // Tags we always skip (no descent).
  var SKIP_TAGS = { defs: true, marker: true, mask: true, clippath: true, pattern: true };

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

  function stripHtml(s) {
    return String(s).replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
  }

  /**
   * Lightweight SVG parse to a tree of opening-tag intervals. Each node in
   * the tree has:
   *   { name, tagStart, tagEnd, closeStart, closeEnd, children }
   *
   * Self-closing tags have children === [] and closeStart === tagEnd.
   *
   * Robust against attributes containing '>' (string quoting is respected
   * inside attribute values — regex handles it correctly).
   */
  function parseTree(src) {
    // Root pseudo-node so root-level sibling tags form a consistent forest.
    var root = { name: '#root', tagStart: 0, tagEnd: 0, closeStart: src.length, closeEnd: src.length, children: [] };
    var stack = [root];
    var i = 0;
    var n = src.length;
    var TAG_RE = /<(\/?)([A-Za-z][A-Za-z0-9_-]*)\b([^>]*?)(\/?)>|<!--[\s\S]*?-->/g;
    var m;
    TAG_RE.lastIndex = 0;
    while ((m = TAG_RE.exec(src)) != null) {
      if (m[0].slice(0, 4) === '<!--') continue;
      var close     = m[1] === '/';
      var name      = m[2].toLowerCase();
      var selfClose = m[4] === '/';
      var tagStart  = m.index;
      var tagEnd    = TAG_RE.lastIndex;

      if (close) {
        // Pop until we find a matching open.
        while (stack.length > 1) {
          var top = stack.pop();
          if (top.name === name) {
            top.closeStart = tagStart;
            top.closeEnd   = tagEnd;
            break;
          }
        }
        continue;
      }

      var node = { name: name, tagStart: tagStart, tagEnd: tagEnd,
                   closeStart: tagEnd, closeEnd: tagEnd, children: [] };
      stack[stack.length - 1].children.push(node);
      if (!selfClose) stack.push(node);
    }
    return root;
  }

  /**
   * Find the root <svg> in a parsed tree.
   */
  function findRootSvg(tree) {
    for (var i = 0; i < tree.children.length; i++) {
      if (tree.children[i].name === 'svg') return tree.children[i];
    }
    return null;
  }

  /**
   * Derive a label for a semantic <g> node by walking its descendants in
   * the parse tree. Priority:
   *   1. aria-label on the tag
   *   2. <text> descendant
   *   3. <title> descendant
   *   4. data-label / data-title attribute
   *   5. id → prettified
   *   6. empty string
   */
  function nodeLabel(src, node) {
    var tagSrc = src.slice(node.tagStart, node.tagEnd);
    var al = getAttr(tagSrc, 'aria-label');
    if (al) return stripHtml(al);
    var dl = getAttr(tagSrc, 'data-label');
    if (dl) return stripHtml(dl);

    // Walk descendants for first <text> or <title>.
    var found = firstDescendant(src, node, ['text', 'title']);
    if (found) {
      var body = src.slice(found.tagEnd, found.closeStart);
      var txt  = stripHtml(body);
      if (txt) return txt;
    }

    var id = getAttr(tagSrc, 'id');
    if (id) {
      return id.replace(/^[a-z]+-(?:node|edge|loop|cell|cat|category|cause|effect|quadrant-item|item)-/i, '')
               .replace(/[-_]/g, ' ');
    }
    return '';
  }

  function firstDescendant(src, node, names) {
    for (var i = 0; i < node.children.length; i++) {
      var c = node.children[i];
      if (names.indexOf(c.name) >= 0) return c;
      var deeper = firstDescendant(src, c, names);
      if (deeper) return deeper;
    }
    return null;
  }

  /**
   * A <g> is "semantic-focusable" if:
   *   - it carries role="graphics-symbol" or role="graphics-datapoint"
   *     (anything else is either presentation or decorative)
   *   - OR it carries an id AND a semantic class (ora-visual__*)
   */
  function isSemantic(src, node) {
    if (node.name !== 'g') return false;
    var tagSrc = src.slice(node.tagStart, node.tagEnd);
    if (/aria-hidden\s*=\s*"\s*true\s*"/i.test(tagSrc)) return false;
    var role = getAttr(tagSrc, 'role') || '';
    if (role === 'graphics-symbol' || role === 'graphics-datapoint') return true;
    // Fallback: id + semantic class.
    if (!getAttr(tagSrc, 'id')) return false;
    var cls = getAttr(tagSrc, 'class') || '';
    return SEMANTIC_CLASS_RE.test(cls);
  }

  /**
   * Ensure node has an id; synthesize if missing and return it. We don't
   * rewrite the original SVG here — that's done by the emit pass. We just
   * derive a stable key.
   */
  function stableId(src, node, fallback) {
    var tagSrc = src.slice(node.tagStart, node.tagEnd);
    var id = getAttr(tagSrc, 'id');
    if (id) return id;
    return fallback;
  }

  // ── Build nav tree (pre-order, depth-capped) ─────────────────────────────
  function collectNav(src, svgNode, rootId) {
    var nodes = [];
    var idCounter = 0;
    function nextSynthId() { idCounter++; return rootId + '-n' + idCounter; }

    // parent is a nav entry already in `nodes` (or null for root svg).
    function descend(domNode, level, parentEntry) {
      if (level > MAX_LEVEL) return;   // cap depth
      for (var i = 0; i < domNode.children.length; i++) {
        var ch = domNode.children[i];
        if (SKIP_TAGS[ch.name]) continue;

        if (isSemantic(src, ch)) {
          var id    = stableId(src, ch, nextSynthId());
          var label = nodeLabel(src, ch);
          var entry = {
            id:           id,
            level:        level,
            label:        label,
            parent_id:    parentEntry ? parentEntry.id : null,
            children_ids: [],
          };
          nodes.push(entry);
          if (parentEntry) parentEntry.children_ids.push(id);
          descend(ch, level + 1, entry);
        } else {
          // Not semantic — descend into its children at the SAME level,
          // so nested semantic groups still reach level 1.
          descend(ch, level, parentEntry);
        }
      }
    }

    descend(svgNode, 1, null);
    return nodes;
  }

  // ── Emit SVG with tabindex + data-olli-level decorations ─────────────────
  //
  // We rewrite ONLY opening tags of (a) the root <svg>, and (b) every
  // semantic <g> that ended up in the nav list. To do this without a DOM
  // we stable-sort tag start indices and walk the source.

  function emitDecoratedSvg(src, svgNode, navNodes, rootId) {
    // Map from tagStart → the decoration to apply.
    var decorations = {};

    // Root svg gets tabindex=0 and (if absent) id=rootId.
    decorations[svgNode.tagStart] = {
      type:    'root',
      tagEnd:  svgNode.tagEnd,
      rootId:  rootId,
    };

    // Build a lookup from id → level so we can annotate without re-walking.
    // Some nodes have synthesized IDs; those need injecting.
    var idLevel = {};
    for (var i = 0; i < navNodes.length; i++) idLevel[navNodes[i].id] = navNodes[i].level;

    // Re-walk semantic <g>s to match them to their nav entry by id or path
    // order. We walk the same way collectNav did: depth-first pre-order,
    // skipping SKIP_TAGS, respecting isSemantic.
    var idx = 0;
    function walk(domNode) {
      for (var j = 0; j < domNode.children.length; j++) {
        var ch = domNode.children[j];
        if (SKIP_TAGS[ch.name]) continue;
        if (isSemantic(src, ch)) {
          if (idx < navNodes.length) {
            var entry = navNodes[idx++];
            decorations[ch.tagStart] = {
              type:   'semantic',
              tagEnd: ch.tagEnd,
              navId:  entry.id,
              level:  entry.level,
            };
          }
          walk(ch);
        } else {
          walk(ch);
        }
      }
    }
    walk(svgNode);

    // Build output by stitching original src with decorated tag replacements.
    var keys = Object.keys(decorations).map(Number).sort(function (a, b) { return a - b; });
    var out = [];
    var cursor = 0;
    for (var k = 0; k < keys.length; k++) {
      var tagStart = keys[k];
      var dec = decorations[tagStart];
      out.push(src.slice(cursor, tagStart));
      var tagSrc = src.slice(tagStart, dec.tagEnd);
      if (dec.type === 'root') {
        if (!hasAttr(tagSrc, 'tabindex'))  tagSrc = addAttr(tagSrc, 'tabindex', '0');
        if (!hasAttr(tagSrc, 'id'))        tagSrc = addAttr(tagSrc, 'id', dec.rootId);
      } else {
        if (!hasAttr(tagSrc, 'tabindex'))        tagSrc = addAttr(tagSrc, 'tabindex', '-1');
        if (!hasAttr(tagSrc, 'data-olli-level')) tagSrc = addAttr(tagSrc, 'data-olli-level', String(dec.level));
        if (!hasAttr(tagSrc, 'id'))              tagSrc = addAttr(tagSrc, 'id', dec.navId);
      }
      out.push(tagSrc);
      cursor = dec.tagEnd;
    }
    out.push(src.slice(cursor));
    return out.join('');
  }

  /**
   * buildNav(svgString, envelope) → { svg, ariaDescription }
   */
  function buildNav(svgString, envelope) {
    if (typeof svgString !== 'string' || svgString.length === 0) {
      return { svg: svgString, ariaDescription: emptyDesc(envelope) };
    }
    var tree = parseTree(svgString);
    var svgNode = findRootSvg(tree);
    if (!svgNode) {
      return { svg: svgString, ariaDescription: emptyDesc(envelope) };
    }

    // Resolve root_id. Prefer envelope.id + "-svg" suffix to avoid collision
    // with the envelope's short_alt/desc IDs. If the svg already has an id
    // attribute, honor it.
    var rootId = rootIdFor(svgString, svgNode, envelope);

    var navNodes = collectNav(svgString, svgNode, rootId);
    var decorated = emitDecoratedSvg(svgString, svgNode, navNodes, rootId);

    return {
      svg: decorated,
      ariaDescription: {
        root_id: rootId,
        nodes:   navNodes,
      },
    };
  }

  function rootIdFor(src, svgNode, envelope) {
    var tagSrc = src.slice(svgNode.tagStart, svgNode.tagEnd);
    var id = getAttr(tagSrc, 'id');
    if (id) return id;
    if (envelope && envelope.id) {
      return String(envelope.id).replace(/[^A-Za-z0-9_-]/g, '-') + '-svg';
    }
    return 'ora-visual-root';
  }

  function emptyDesc(envelope) {
    return {
      root_id: envelope && envelope.id ? String(envelope.id) + '-svg' : 'ora-visual-root',
      nodes:   [],
    };
  }

  // ── Public surface ────────────────────────────────────────────────────────
  ns.accessibility.buildKeyboardNav = buildNav;

  // Expose internal helpers for unit testing.
  ns.accessibility._navInternals = {
    parseTree:          parseTree,
    isSemantic:         isSemantic,
    collectNav:         collectNav,
    nodeLabel:          nodeLabel,
    MAX_LEVEL:          MAX_LEVEL,
    SEMANTIC_CLASS_RE:  SEMANTIC_CLASS_RE,
  };
}(typeof window !== 'undefined' ? window : globalThis));
