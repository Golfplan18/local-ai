/**
 * ora-visual-compiler / vendor/structurizr-mini/renderer.js
 *
 * Layout + SVG emitter for parsed Structurizr AST. (WP-1.2d)
 *
 * Public surface:
 *   window.OraVisualCompiler._vendor.structurizrMini.renderer.render(ast, options)
 *       → { svg: string }
 *
 *   options: {
 *     level: 'context' | 'container',  // required — matches envelope.spec.level
 *     title: string?,                  // envelope.title, rendered in the figure
 *     ariaLabel: string?,              // ARIA label for the root <svg>
 *   }
 *
 * Layout strategy: deterministic three-column layered layout.
 *   • For `context` level we select the `systemContext` view on the scope
 *     software system; people go into the left column, the scope system into
 *     the middle column, all other systems (external or otherwise) into the
 *     right column. If the DSL has no matching view we synthesize one with
 *     `include *` + `autolayout lr`.
 *   • For `container` level we select the `container` view on the scope
 *     system; containers of the scope system tile vertically in the middle.
 *     Related people + other systems (reachable by one relationship hop)
 *     flank left/right. `autolayout tb` swaps the role of the middle column
 *     to a horizontal tile of containers instead of vertical.
 *
 * No Dagre / D3. Arithmetic spacing. Arrow routing is straight-line between
 * centre edges of the source/target rectangles (orthogonal clipping on the
 * rectangle boundary). Labels render at the midpoint of each arrow.
 *
 * All classes are semantic; no inline styles. WP-1.4 supplies CSS.
 *
 * Depends on: nothing (pure ES5-ish).
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._vendor = window.OraVisualCompiler._vendor || {};
window.OraVisualCompiler._vendor.structurizrMini =
  window.OraVisualCompiler._vendor.structurizrMini || {};

window.OraVisualCompiler._vendor.structurizrMini.renderer = (function () {

  // ── Geometry constants ────────────────────────────────────────────────────
  const BOX_W = 170;
  const BOX_H = 90;
  const BOX_PERSON_W = 150;
  const BOX_PERSON_H = 100;
  const COL_GAP = 110;          // horizontal gap between columns
  const ROW_GAP = 44;           // vertical gap between rows within a column
  const PAD = 40;               // outer padding
  const TITLE_H = 40;           // reserved top strip for title

  // ── Escape helpers ────────────────────────────────────────────────────────
  function esc(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function slug(str) {
    // Keep original id characters where safe; used for SVG element IDs.
    return String(str).replace(/[^A-Za-z0-9_-]/g, '_');
  }

  // Wrap a label string into up to `maxLines` lines fitting `maxChars` each.
  function wrapLabel(text, maxChars, maxLines) {
    if (!text) return [];
    maxChars = maxChars || 22;
    maxLines = maxLines || 3;
    const words = String(text).split(/\s+/);
    const lines = [];
    let cur = '';
    for (let i = 0; i < words.length; i++) {
      const w = words[i];
      if ((cur + ' ' + w).trim().length <= maxChars) {
        cur = (cur ? cur + ' ' : '') + w;
      } else {
        if (cur) lines.push(cur);
        cur = w;
        if (lines.length >= maxLines - 1) {
          // Remaining words clump onto the last line; truncate with ellipsis.
          const rest = words.slice(i).join(' ');
          lines.push(rest.length > maxChars
            ? rest.slice(0, maxChars - 1) + '…'
            : rest);
          cur = '';
          break;
        }
      }
    }
    if (cur) lines.push(cur);
    return lines.slice(0, maxLines);
  }

  // ── View selection ────────────────────────────────────────────────────────
  function findView(ast, level) {
    const kindWanted = level === 'context' ? 'systemContext' : 'container';
    for (let i = 0; i < ast.views.length; i++) {
      if (ast.views[i].kind === kindWanted) return ast.views[i];
    }
    return null;
  }

  function synthesizeView(ast, level) {
    // Use the first softwareSystem as default scope.
    const scope = ast.model.softwareSystems[0];
    if (!scope) return null;
    return {
      kind: level === 'context' ? 'systemContext' : 'container',
      scopeId: scope.id,
      name: 'synthesized-' + level,
      include: ['*'],
      layout: 'lr',
    };
  }

  // ── Element construction helpers ──────────────────────────────────────────
  function makeShape(kind, id, name, description, technology, external, x, y) {
    return {
      kind: kind,              // 'person' | 'system' | 'container'
      id: id,
      name: name || '',
      description: description || '',
      technology: technology || '',
      external: !!external,
      x: x || 0,
      y: y || 0,
      w: kind === 'person' ? BOX_PERSON_W : BOX_W,
      h: kind === 'person' ? BOX_PERSON_H : BOX_H,
    };
  }

  function elementCenter(el) {
    return { cx: el.x + el.w / 2, cy: el.y + el.h / 2 };
  }

  // Clip a line going from centre-A to centre-B at the boundary of rect B.
  function clipToRect(fromC, toEl) {
    const cx = toEl.x + toEl.w / 2;
    const cy = toEl.y + toEl.h / 2;
    const dx = cx - fromC.cx;
    const dy = cy - fromC.cy;
    if (dx === 0 && dy === 0) return { x: cx, y: cy };
    const hx = toEl.w / 2;
    const hy = toEl.h / 2;
    const absDx = Math.abs(dx);
    const absDy = Math.abs(dy);
    let t;
    if (absDx / hx > absDy / hy) {
      t = hx / absDx;
    } else {
      t = hy / absDy;
    }
    return { x: cx - dx * t, y: cy - dy * t };
  }

  // ── Main render ───────────────────────────────────────────────────────────
  function render(ast, options) {
    options = options || {};
    const level = options.level === 'container' ? 'container' : 'context';

    let view = findView(ast, level);
    if (!view) view = synthesizeView(ast, level);
    if (!view) {
      // Model is empty enough that we can't even synthesize a view.
      const svgEmpty = emptySvg(options);
      return { svg: svgEmpty };
    }

    const pipeline = level === 'context'
      ? layoutContext(ast, view)
      : layoutContainer(ast, view);

    const svg = toSvg(pipeline, level, options);
    return { svg: svg };
  }

  // ── Context layout ────────────────────────────────────────────────────────
  function layoutContext(ast, view) {
    const includeAll = view.include.indexOf('*') !== -1;
    const allowed = new Set(view.include);
    const inView = function (id) { return includeAll || allowed.has(id); };

    const scope = ast.model.softwareSystems
      .filter(function (s) { return s.id === view.scopeId; })[0];

    // Relevant elements: the scope system + any system/person that has a
    // relationship to/from an included id. For `include *` we simply take
    // all people + all systems.
    const relevantSystems = ast.model.softwareSystems.filter(function (s) {
      return includeAll || inView(s.id) || s.id === view.scopeId;
    });
    const relevantPeople = ast.model.people.filter(function (p) {
      return includeAll || inView(p.id);
    });

    // Column assignment:
    //   left: people
    //   middle: scope system + any non-external system directly connected
    //   right: external systems
    const left = relevantPeople.map(function (p) {
      return makeShape('person', p.id, p.name, p.description, '', false);
    });
    const middle = [];
    const right = [];
    relevantSystems.forEach(function (s) {
      if (s.id === view.scopeId) {
        middle.push(makeShape('system', s.id, s.name, s.description, '', s.external));
      } else if (s.external) {
        right.push(makeShape('system', s.id, s.name, s.description, '', true));
      } else {
        right.push(makeShape('system', s.id, s.name, s.description, '', false));
      }
    });

    const elements = assignColumns([left, middle, right]);

    // Relationships: filter to those whose endpoints are both in the view.
    const elSet = new Set(elements.map(function (e) { return e.id; }));
    const edges = ast.model.relationships
      .filter(function (r) { return elSet.has(r.fromId) && elSet.has(r.toId); });

    return { elements: elements, edges: edges, view: view };
  }

  // ── Container layout ──────────────────────────────────────────────────────
  function layoutContainer(ast, view) {
    const includeAll = view.include.indexOf('*') !== -1;
    const allowed = new Set(view.include);
    const inView = function (id) { return includeAll || allowed.has(id); };

    const scope = ast.model.softwareSystems
      .filter(function (s) { return s.id === view.scopeId; })[0];
    if (!scope) {
      return { elements: [], edges: [], view: view };
    }

    const containers = scope.containers.filter(function (c) {
      return includeAll || inView(c.id);
    });
    const containerShapes = containers.map(function (c) {
      return makeShape('container', c.id, c.name, c.description, c.technology, false);
    });

    // One-hop neighbours of any container: people or other systems.
    const neighbourIds = new Set();
    const containerIds = new Set(containers.map(function (c) { return c.id; }));
    ast.model.relationships.forEach(function (r) {
      if (containerIds.has(r.fromId)) neighbourIds.add(r.toId);
      if (containerIds.has(r.toId)) neighbourIds.add(r.fromId);
    });
    containerIds.forEach(function (id) { neighbourIds.delete(id); });

    const people = [];
    const systems = [];
    neighbourIds.forEach(function (id) {
      const p = ast.model.people.filter(function (x) { return x.id === id; })[0];
      if (p) {
        people.push(makeShape('person', p.id, p.name, p.description, '', false));
        return;
      }
      const s = ast.model.softwareSystems.filter(function (x) { return x.id === id; })[0];
      if (s) {
        systems.push(makeShape('system', s.id, s.name, s.description, '', s.external));
      }
    });

    // Layout direction: if autolayout 'tb' then containers tile horizontally
    // in the middle row with people above and systems below. Default 'lr'
    // mirrors the context-view layout.
    let elements;
    if (view.layout === 'tb') {
      elements = assignRows([people, containerShapes, systems]);
    } else {
      elements = assignColumns([people, containerShapes, systems]);
    }

    const elSet = new Set(elements.map(function (e) { return e.id; }));
    const edges = ast.model.relationships
      .filter(function (r) { return elSet.has(r.fromId) && elSet.has(r.toId); });

    return { elements: elements, edges: edges, view: view };
  }

  // ── Column / row placement ────────────────────────────────────────────────
  // Elements in each column are stacked vertically, centred in their column.
  function assignColumns(columns) {
    // Strip empty columns so we don't leave gaps.
    const nonEmpty = columns.filter(function (c) { return c.length > 0; });

    const colHeights = nonEmpty.map(function (col) {
      let h = 0;
      col.forEach(function (el, i) {
        if (i > 0) h += ROW_GAP;
        h += el.h;
      });
      return h;
    });

    const maxH = colHeights.reduce(function (a, b) { return Math.max(a, b); }, 0);

    let x = PAD;
    const placed = [];
    nonEmpty.forEach(function (col, ci) {
      const colH = colHeights[ci];
      let y = PAD + TITLE_H + (maxH - colH) / 2;
      // Columns align on their widest element.
      const colW = col.reduce(function (a, b) {
        return Math.max(a, b.w);
      }, 0);
      col.forEach(function (el, i) {
        el.x = x + (colW - el.w) / 2;
        el.y = y;
        placed.push(el);
        y += el.h + ROW_GAP;
      });
      x += colW + COL_GAP;
    });
    return placed;
  }

  // Elements in each row tile horizontally, centred in their row.
  function assignRows(rows) {
    const nonEmpty = rows.filter(function (r) { return r.length > 0; });
    const rowWidths = nonEmpty.map(function (row) {
      let w = 0;
      row.forEach(function (el, i) {
        if (i > 0) w += COL_GAP;
        w += el.w;
      });
      return w;
    });
    const maxW = rowWidths.reduce(function (a, b) { return Math.max(a, b); }, 0);

    let y = PAD + TITLE_H;
    const placed = [];
    nonEmpty.forEach(function (row, ri) {
      const rowW = rowWidths[ri];
      let x = PAD + (maxW - rowW) / 2;
      // Row height is max of its elements.
      const rowH = row.reduce(function (a, b) {
        return Math.max(a, b.h);
      }, 0);
      row.forEach(function (el, i) {
        el.x = x;
        el.y = y + (rowH - el.h) / 2;
        placed.push(el);
        x += el.w + COL_GAP;
      });
      y += rowH + ROW_GAP * 2;
    });
    return placed;
  }

  // ── SVG serialisation ─────────────────────────────────────────────────────
  function toSvg(pipeline, level, options) {
    const elements = pipeline.elements;
    const edges = pipeline.edges;
    const view = pipeline.view;

    // Compute viewBox from placed elements.
    let minX = Infinity, minY = Infinity, maxX = 0, maxY = 0;
    elements.forEach(function (el) {
      if (el.x < minX) minX = el.x;
      if (el.y < minY) minY = el.y;
      if (el.x + el.w > maxX) maxX = el.x + el.w;
      if (el.y + el.h > maxY) maxY = el.y + el.h;
    });
    if (!isFinite(minX)) {
      minX = 0; minY = 0; maxX = 480; maxY = 320;
    }
    const width = Math.ceil(maxX + PAD - (minX < PAD ? 0 : minX - PAD));
    const height = Math.ceil(maxY + PAD);
    // Ensure at least a sensible minimum canvas.
    const wFinal = Math.max(width, 320);
    const hFinal = Math.max(height, 240);

    const ariaLabel = options.ariaLabel || options.title || 'C4 diagram';

    const parts = [];
    parts.push(
      '<svg xmlns="http://www.w3.org/2000/svg" ' +
      'class="ora-visual ora-visual--c4 ora-visual--c4-' + esc(level) + '" ' +
      'role="img" ' +
      'aria-label="' + esc(ariaLabel) + '" ' +
      'viewBox="0 0 ' + wFinal + ' ' + hFinal + '">');
    parts.push('  <title class="ora-visual__accessible-title">' +
      esc(ariaLabel) + '</title>');

    // Title strip
    if (options.title) {
      parts.push('  <text class="ora-visual__title" ' +
        'x="' + (wFinal / 2) + '" y="' + 24 + '" ' +
        'text-anchor="middle" dominant-baseline="middle">' +
        esc(options.title) + '</text>');
    }

    // Arrow-head marker (uses CSS for colour via currentColor).
    parts.push(
      '  <defs>' +
      '<marker id="ora-c4-arrowhead" class="ora-visual__c4-arrowhead" ' +
      'viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" ' +
      'orient="auto-start-reverse">' +
      '<path d="M 0 0 L 10 5 L 0 10 z" />' +
      '</marker>' +
      '</defs>');

    // Edges first (behind shapes). Build quick element lookup.
    const byId = {};
    elements.forEach(function (el) { byId[el.id] = el; });

    edges.forEach(function (e, i) {
      const from = byId[e.fromId];
      const to = byId[e.toId];
      if (!from || !to) return;
      const fc = elementCenter(from);
      const tc = elementCenter(to);
      const p1 = clipToRect(tc, from); // boundary of FROM facing TO
      const p2 = clipToRect(fc, to);   // boundary of TO facing FROM
      const mx = (p1.x + p2.x) / 2;
      const my = (p1.y + p2.y) / 2;
      const relId = 'c4-relationship-' + slug(e.fromId) + '-' + slug(e.toId) + '-' + i;
      parts.push(
        '  <g class="ora-visual__c4-relationship" ' +
        'id="' + esc(relId) + '">' +
        '<line class="ora-visual__c4-relationship-line" ' +
        'x1="' + p1.x.toFixed(1) + '" y1="' + p1.y.toFixed(1) + '" ' +
        'x2="' + p2.x.toFixed(1) + '" y2="' + p2.y.toFixed(1) + '" ' +
        'marker-end="url(#ora-c4-arrowhead)" />' +
        (e.description
          ? '<text class="ora-visual__c4-relationship-label" ' +
            'x="' + mx.toFixed(1) + '" y="' + (my - 6).toFixed(1) + '" ' +
            'text-anchor="middle">' + esc(e.description) + '</text>'
          : '') +
        '</g>');
    });

    // Shapes
    elements.forEach(function (el) {
      parts.push(shapeSvg(el));
    });

    parts.push('</svg>');
    return parts.join('\n');
  }

  function shapeSvg(el) {
    const id = 'c4-' + el.kind + '-' + slug(el.id);
    if (el.kind === 'person') {
      return personSvg(id, el);
    }
    if (el.kind === 'container') {
      return boxSvg(id, el, 'container', false);
    }
    // system (may be external)
    return boxSvg(id, el, 'system', el.external);
  }

  function boxSvg(id, el, kind, external) {
    const rx = 6;
    const cls = 'ora-visual__c4-' + kind +
      (external ? ' ora-visual__c4-system--external' : '');
    const labelLines = wrapLabel(el.name, 20, 2);
    const techLines = el.technology
      ? wrapLabel('[' + el.technology + ']', 22, 1)
      : [];
    const descLines = el.description
      ? wrapLabel(el.description, 26, 2)
      : [];
    const cx = el.x + el.w / 2;
    let y = el.y + 26;
    const textParts = [];

    labelLines.forEach(function (ln, i) {
      textParts.push('<text class="ora-visual__c4-label" ' +
        'x="' + cx + '" y="' + (y + i * 16) + '" ' +
        'text-anchor="middle">' + esc(ln) + '</text>');
    });
    y += labelLines.length * 16 + 6;
    techLines.forEach(function (ln, i) {
      textParts.push('<text class="ora-visual__c4-technology" ' +
        'x="' + cx + '" y="' + (y + i * 14) + '" ' +
        'text-anchor="middle">' + esc(ln) + '</text>');
    });
    y += techLines.length * 14 + 2;
    descLines.forEach(function (ln, i) {
      textParts.push('<text class="ora-visual__c4-description" ' +
        'x="' + cx + '" y="' + (y + i * 13) + '" ' +
        'text-anchor="middle">' + esc(ln) + '</text>');
    });

    return '  <g class="' + cls + '" id="' + esc(id) + '">' +
      '<rect class="ora-visual__c4-shape" ' +
      'x="' + el.x + '" y="' + el.y + '" ' +
      'width="' + el.w + '" height="' + el.h + '" ' +
      'rx="' + rx + '" ry="' + rx + '" />' +
      textParts.join('') +
      '</g>';
  }

  function personSvg(id, el) {
    // Person pictogram: circle (head) atop rounded rectangle (body).
    const cx = el.x + el.w / 2;
    const headR = 12;
    const headY = el.y + 16;
    const bodyY = headY + headR + 2;
    const bodyH = el.h - (headY + headR + 2 - el.y) - 6;
    const bodyW = el.w - 20;
    const bodyX = el.x + 10;
    const labelLines = wrapLabel(el.name, 18, 2);
    const descLines = el.description ? wrapLabel(el.description, 22, 2) : [];
    const textY0 = bodyY + 20;
    const textParts = [];
    labelLines.forEach(function (ln, i) {
      textParts.push('<text class="ora-visual__c4-label" ' +
        'x="' + cx + '" y="' + (textY0 + i * 14) + '" ' +
        'text-anchor="middle">' + esc(ln) + '</text>');
    });
    const descY = textY0 + labelLines.length * 14 + 2;
    descLines.forEach(function (ln, i) {
      textParts.push('<text class="ora-visual__c4-description" ' +
        'x="' + cx + '" y="' + (descY + i * 12) + '" ' +
        'text-anchor="middle">' + esc(ln) + '</text>');
    });

    return '  <g class="ora-visual__c4-person" id="' + esc(id) + '">' +
      '<circle class="ora-visual__c4-person-head" ' +
      'cx="' + cx + '" cy="' + headY + '" r="' + headR + '" />' +
      '<rect class="ora-visual__c4-person-body" ' +
      'x="' + bodyX + '" y="' + bodyY + '" ' +
      'width="' + bodyW + '" height="' + bodyH + '" ' +
      'rx="8" ry="8" />' +
      textParts.join('') +
      '</g>';
  }

  function emptySvg(options) {
    const label = options.ariaLabel || options.title || 'Empty C4 diagram';
    return '<svg xmlns="http://www.w3.org/2000/svg" ' +
      'class="ora-visual ora-visual--c4 ora-visual--c4-empty" ' +
      'role="img" aria-label="' + esc(label) + '" viewBox="0 0 320 160">' +
      '<title class="ora-visual__accessible-title">' + esc(label) + '</title>' +
      '<text class="ora-visual__c4-empty-notice" x="160" y="80" ' +
      'text-anchor="middle" dominant-baseline="middle">Empty C4 model</text>' +
      '</svg>';
  }

  return {
    render: render,
  };

}());
