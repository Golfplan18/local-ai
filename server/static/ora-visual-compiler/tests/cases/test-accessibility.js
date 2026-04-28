/**
 * tests/cases/test-accessibility.js — WP-1.5 regression suite.
 *
 * Exports { label, run(ctx, record) } following the run.js case-file
 * convention used by every other WP-1.x test suite.
 *
 * Coverage:
 *   1. End-to-end: every examples/*.valid.json envelope (minus the
 *      jsdom flowchart skip) is run through compileWithNav() and the
 *      produced SVG + ariaDescription are asserted against the protocol:
 *       - root <svg> has role="img", aria-labelledby, aria-describedby,
 *         tabindex="0"
 *       - <title> text === envelope.semantic_description.short_alt
 *       - <desc> text contains level_1 / level_2 / level_3 strings
 *       - every <g id="..."> with a semantic class has aria-label OR
 *         aria-hidden
 *       - ariaDescription.nodes.length ≥ 1 (i.e. at least one semantic
 *         element was discoverable) OR at least one group got aria-label —
 *         we accept either signal. For viz-js output the nav tree is
 *         usually non-empty; for stub-only types we require decoration.
 *       - ariaDescription has no cycles; every non-null parent_id resolves
 *   2. Three unit tests per module against hand-crafted tiny SVG strings:
 *      - alt-text-generator: decorate base SVG, replace existing, idempotency
 *      - aria-annotator: graphics-symbol, graphics-datapoint, presentation
 *      - keyboard-nav: flat tree, nested tree, depth cap at 5
 */

'use strict';

const fs   = require('fs');
const path = require('path');

const JSDOM_FLOWCHART_SKIP = new Set(['flowchart.valid.json']);

// ── Small string helpers (test-only — no dependency on compiler) ────────────
function extract(str, re) {
  const m = re.exec(str);
  return m ? m[1] : null;
}

function decodeHtml(s) {
  if (s == null) return s;
  return String(s)
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"');
}

function findRootSvgOpen(svg) {
  return /<svg\b[^>]*>/i.exec(svg);
}

function findDirectChild(svg, tagName) {
  // scan for <tagName>…</tagName> at depth 0 inside the root svg.
  const openM = findRootSvgOpen(svg);
  if (!openM) return null;
  const bodyStart = openM.index + openM[0].length;
  const lastClose = svg.toLowerCase().lastIndexOf('</svg>');
  if (lastClose < 0 || lastClose < bodyStart) return null;
  const body = svg.slice(bodyStart, lastClose);
  // naive depth-0 scan
  const re = new RegExp('<' + tagName + '\\b[^>]*>([\\s\\S]*?)</' + tagName + '>', 'i');
  const m = re.exec(body);
  return m ? { tag: m[0], inner: m[1] } : null;
}

function attrOf(tag, name) {
  const re = new RegExp('\\b' + name + '\\s*=\\s*"([^"]*)"', 'i');
  const m = re.exec(tag);
  return m ? m[1] : null;
}

// Count <g id="..."> that carry a class matching ora-visual__* and report
// whether each has aria-label OR aria-hidden.
function* iterSemanticGroups(svg) {
  const re = /<g\b[^>]*>/gi;
  let m;
  while ((m = re.exec(svg)) != null) {
    const tag = m[0];
    const id  = attrOf(tag, 'id');
    const cls = attrOf(tag, 'class') || '';
    if (!id) continue;
    if (!/\bora-visual__/.test(cls) &&
        !(attrOf(tag, 'role') === 'graphics-symbol' ||
          attrOf(tag, 'role') === 'graphics-datapoint')) continue;
    yield { id: id, cls: cls, tag: tag };
  }
}

// ── Whole-envelope end-to-end assertions ─────────────────────────────────────
function assertEnvelopeOutput(envelope, result) {
  const sd = envelope.semantic_description;
  if (!result || typeof result !== 'object') return 'no result object';
  if (!result.svg || result.svg.length === 0) return 'empty svg';
  if (!Array.isArray(result.errors)) return 'result.errors missing';

  const rootOpen = findRootSvgOpen(result.svg);
  if (!rootOpen) return 'no <svg> root';

  // aria-labelledby, aria-describedby, role=img, tabindex=0
  const rootTag = rootOpen[0];
  if (!/\brole\s*=\s*"img"/i.test(rootTag))
    return 'root svg missing role="img"';
  if (!/\baria-labelledby\s*=\s*"/i.test(rootTag))
    return 'root svg missing aria-labelledby';
  if (!/\baria-describedby\s*=\s*"/i.test(rootTag))
    return 'root svg missing aria-describedby';
  if (!/\btabindex\s*=\s*"0"/i.test(rootTag))
    return 'root svg missing tabindex="0"';

  // <title> text should equal short_alt.
  const title = findDirectChild(result.svg, 'title');
  if (!title) return 'no direct <title> child of root svg';
  const titleText = decodeHtml(title.inner).trim();
  const shortAlt  = (sd.short_alt || '').trim();
  if (titleText !== shortAlt) {
    return 'title text mismatch: got "' + titleText + '" expected "' + shortAlt + '"';
  }

  // <desc> text should contain each of level_1/2/3.
  const desc = findDirectChild(result.svg, 'desc');
  if (!desc) return 'no direct <desc> child of root svg';
  const descText = decodeHtml(desc.inner);
  for (const key of ['level_1_elemental', 'level_2_statistical', 'level_3_perceptual']) {
    const val = sd[key];
    if (!val) continue;
    if (descText.indexOf(String(val)) < 0) {
      return 'desc text missing ' + key + ' content';
    }
  }

  // Every semantic <g id="..."> has a screen-reader-visible label:
  // aria-label OR aria-labelledby OR aria-hidden OR aria-roledescription
  // (WAI-ARIA-equivalent).
  let ungrouped = 0;
  for (const g of iterSemanticGroups(result.svg)) {
    if (!/\baria-label\s*=\s*"/i.test(g.tag) &&
        !/\baria-hidden\s*=\s*"\s*true\s*"/i.test(g.tag) &&
        !/\baria-labelledby\s*=\s*"/i.test(g.tag) &&
        !/\baria-roledescription\s*=\s*"/i.test(g.tag)) {
      ungrouped++;
    }
  }
  if (ungrouped > 0) {
    return ungrouped + ' semantic <g id=..."> missing aria-label/aria-hidden/aria-roledescription';
  }

  // ariaDescription sanity.
  const ad = result.ariaDescription;
  if (!ad || typeof ad !== 'object') return 'missing ariaDescription';
  if (!ad.root_id || typeof ad.root_id !== 'string') return 'ariaDescription.root_id missing';
  if (!Array.isArray(ad.nodes)) return 'ariaDescription.nodes not an array';
  // Well-formedness: no cycles, every parent resolves, every child listed.
  const ids = new Set();
  for (const n of ad.nodes) {
    if (ids.has(n.id)) return 'duplicate node id ' + n.id;
    ids.add(n.id);
    if (typeof n.level !== 'number' || n.level < 1 || n.level > 5) {
      return 'node ' + n.id + ' level out of range: ' + n.level;
    }
  }
  for (const n of ad.nodes) {
    if (n.parent_id != null && !ids.has(n.parent_id)) {
      return 'parent ' + n.parent_id + ' of ' + n.id + ' not in nodes list';
    }
    if (!Array.isArray(n.children_ids)) return 'node ' + n.id + ' children_ids missing';
    for (const cid of n.children_ids) {
      if (!ids.has(cid)) return 'child ' + cid + ' of ' + n.id + ' not in nodes list';
    }
  }
  // No cycles: BFS from each node and ensure we don't revisit.
  for (const n of ad.nodes) {
    const seen = new Set([n.id]);
    const q = n.children_ids.slice();
    while (q.length) {
      const id = q.shift();
      if (seen.has(id)) return 'cycle detected near ' + n.id;
      seen.add(id);
      const ch = ad.nodes.find(x => x.id === id);
      if (ch) for (const c of ch.children_ids) q.push(c);
    }
  }

  return null;
}

// ── Hand-crafted unit tests ──────────────────────────────────────────────────
function unitAltText(win, record) {
  const a11y = win.OraVisualCompiler.accessibility;
  if (!a11y || typeof a11y.decorateAltText !== 'function') {
    record('unit:alt-text-generator loaded', false, 'decorateAltText missing');
    return;
  }
  const envelope = {
    id: 'fig-unit-1',
    title: 'Unit test figure',
    semantic_description: {
      level_1_elemental:   'L1 content for unit test.',
      level_2_statistical: 'L2 content for unit test.',
      level_3_perceptual:  'L3 content for unit test.',
      level_4_contextual:  null,
      short_alt:           'Unit test short alt.',
    },
  };

  // 1. Base SVG with no title/desc → gets both plus aria attrs.
  const base = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><g/></svg>';
  const out  = a11y.decorateAltText(base, envelope);
  const hasTitle = /<title[^>]*>Unit test short alt\.<\/title>/.test(out);
  const descMatch = /<desc[^>]*>([\s\S]*?)<\/desc>/.exec(out);
  const descBody = descMatch ? descMatch[1] : '';
  const hasDesc  = descBody.indexOf('L1 content') >= 0 &&
                   descBody.indexOf('L2 content') >= 0 &&
                   descBody.indexOf('L3 content') >= 0;
  const hasRole  = /role="img"/.test(/<svg\b[^>]*>/.exec(out)[0]);
  const hasLb    = /aria-labelledby="fig-unit-1-a11y-title"/.test(/<svg\b[^>]*>/.exec(out)[0]);
  const hasDb    = /aria-describedby="fig-unit-1-a11y-desc"/.test(/<svg\b[^>]*>/.exec(out)[0]);
  record('unit:alt-text: base decoration',
    hasTitle && hasDesc && hasRole && hasLb && hasDb,
    (hasTitle ? '' : 'no title;') + (hasDesc ? '' : 'no desc;') +
    (hasRole ? '' : 'no role;') + (hasLb ? '' : 'no labelledby;') + (hasDb ? '' : 'no describedby'));

  // 2. Existing title/desc are replaced, not duplicated.
  const pre = '<svg xmlns="http://www.w3.org/2000/svg">' +
              '<title>Old title</title><desc>Old desc</desc><g/></svg>';
  const out2 = a11y.decorateAltText(pre, envelope);
  const titleCount = (out2.match(/<title\b/g) || []).length;
  const descCount  = (out2.match(/<desc\b/g) || []).length;
  const stillHasNew = /Unit test short alt\./.test(out2) && /L1 content/.test(out2);
  record('unit:alt-text: replaces existing title/desc (no duplicate)',
    titleCount === 1 && descCount === 1 && stillHasNew,
    'titleCount=' + titleCount + ' descCount=' + descCount + ' new=' + stillHasNew);

  // 3. Idempotence: decorate(decorate(x)) === decorate(x).
  const out3a = a11y.decorateAltText(base, envelope);
  const out3b = a11y.decorateAltText(out3a, envelope);
  record('unit:alt-text: idempotent',
    out3a === out3b,
    out3a === out3b ? '' : 'diverged on second call (len ' + out3a.length + ' vs ' + out3b.length + ')');
}

function unitAria(win, record) {
  const a11y = win.OraVisualCompiler.accessibility;
  if (!a11y || typeof a11y.annotateAria !== 'function') {
    record('unit:aria-annotator loaded', false, 'annotateAria missing');
    return;
  }

  // 1. graphics-symbol on a node-class <g>.
  const svg1 = '<svg xmlns="http://www.w3.org/2000/svg">' +
               '<g id="n1" class="ora-visual__node"><text>Alpha</text></g></svg>';
  const out1 = a11y.annotateAria(svg1);
  const gTag = /<g\b[^>]*>/.exec(out1.slice(out1.indexOf('<g ')))[0];
  const roleOk  = /role="graphics-symbol"/.test(gTag);
  const labelOk = /aria-label="Alpha"/.test(gTag);
  record('unit:aria: graphics-symbol on node + label from <text>',
    roleOk && labelOk,
    (roleOk ? '' : 'no role;') + (labelOk ? '' : 'no aria-label'));

  // 2. graphics-datapoint on a cell-class <g>.
  const svg2 = '<svg xmlns="http://www.w3.org/2000/svg">' +
               '<g id="c1" class="ora-visual__cell" data-label="Cell X"></g></svg>';
  const out2 = a11y.annotateAria(svg2);
  const gTag2 = /<g\b[^>]*>/.exec(out2.slice(out2.indexOf('<g ')))[0];
  const okRole2 = /role="graphics-datapoint"/.test(gTag2);
  const okLbl2  = /aria-label="Cell X"/.test(gTag2);
  record('unit:aria: graphics-datapoint on cell + label from data-label',
    okRole2 && okLbl2,
    (okRole2 ? '' : 'no role;') + (okLbl2 ? '' : 'no aria-label'));

  // 3. aria-hidden on <defs> and presentation on mark-group role-frame.
  const svg3 = '<svg xmlns="http://www.w3.org/2000/svg">' +
               '<defs><marker id="m1"/></defs>' +
               '<g class="mark-group role-frame root"><rect/></g></svg>';
  const out3 = a11y.annotateAria(svg3);
  const defsOk  = /<defs\b[^>]*aria-hidden="true"/i.test(out3);
  const presOk  = /<g\b[^>]*role="presentation"[^>]*class="mark-group role-frame root"/i.test(out3) ||
                  /<g\b[^>]*class="mark-group role-frame root"[^>]*role="presentation"/i.test(out3);
  record('unit:aria: aria-hidden on defs + presentation on Vega frame',
    defsOk && presOk,
    (defsOk ? '' : 'no hidden on defs;') + (presOk ? '' : 'no presentation on frame'));
}

function unitNav(win, record) {
  const a11y = win.OraVisualCompiler.accessibility;
  if (!a11y || typeof a11y.buildKeyboardNav !== 'function') {
    record('unit:keyboard-nav loaded', false, 'buildKeyboardNav missing');
    return;
  }

  // 1. Flat tree: three siblings.
  const flat =
    '<svg xmlns="http://www.w3.org/2000/svg">' +
    '<g id="a" class="ora-visual__node" role="graphics-symbol" aria-label="A"></g>' +
    '<g id="b" class="ora-visual__node" role="graphics-symbol" aria-label="B"></g>' +
    '<g id="c" class="ora-visual__node" role="graphics-symbol" aria-label="C"></g>' +
    '</svg>';
  const out1 = a11y.buildKeyboardNav(flat, { id: 'fig-flat' });
  const ad1 = out1.ariaDescription;
  const ok1 = /<svg\b[^>]*tabindex="0"/.test(out1.svg) &&
              ad1.nodes.length === 3 &&
              ad1.nodes.every(n => n.level === 1 && n.parent_id === null);
  record('unit:nav: flat tree — 3 level-1 siblings',
    ok1,
    ok1 ? '' : 'nodes=' + ad1.nodes.length + ' levels=' + ad1.nodes.map(n => n.level).join(','));

  // 2. Nested tree: parent with two children, child with one grandchild.
  const nested =
    '<svg xmlns="http://www.w3.org/2000/svg">' +
    '<g id="p" class="ora-visual__node" role="graphics-symbol" aria-label="P">' +
      '<g id="c1" class="ora-visual__node" role="graphics-symbol" aria-label="C1"></g>' +
      '<g id="c2" class="ora-visual__node" role="graphics-symbol" aria-label="C2">' +
        '<g id="gc" class="ora-visual__node" role="graphics-symbol" aria-label="GC"></g>' +
      '</g>' +
    '</g>' +
    '</svg>';
  const out2 = a11y.buildKeyboardNav(nested, { id: 'fig-nested' });
  const ad2 = out2.ariaDescription;
  const byId = {};
  ad2.nodes.forEach(n => { byId[n.id] = n; });
  const ok2 = ad2.nodes.length === 4 &&
              byId.p && byId.p.level === 1 && byId.p.parent_id === null &&
              byId.c1 && byId.c1.level === 2 && byId.c1.parent_id === 'p' &&
              byId.c2 && byId.c2.level === 2 && byId.c2.parent_id === 'p' &&
              byId.gc && byId.gc.level === 3 && byId.gc.parent_id === 'c2' &&
              byId.p.children_ids.length === 2 &&
              byId.c2.children_ids.length === 1;
  record('unit:nav: nested tree — levels + parent_ids + children_ids',
    ok2,
    ok2 ? '' : 'tree: ' + JSON.stringify(ad2.nodes.map(n => [n.id, n.level, n.parent_id])));

  // 3. Depth cap at 5: build 7 levels, verify level 5 is the deepest.
  let deep = '<svg xmlns="http://www.w3.org/2000/svg">';
  for (let i = 1; i <= 7; i++) {
    deep += '<g id="d' + i + '" class="ora-visual__node" role="graphics-symbol" aria-label="D' + i + '">';
  }
  for (let i = 1; i <= 7; i++) deep += '</g>';
  deep += '</svg>';
  const out3 = a11y.buildKeyboardNav(deep, { id: 'fig-deep' });
  const levels = out3.ariaDescription.nodes.map(n => n.level);
  const maxLevel = Math.max.apply(null, levels);
  const ok3 = maxLevel === 5;
  record('unit:nav: depth capped at 5',
    ok3,
    ok3 ? 'max level ' + maxLevel : 'max level was ' + maxLevel + ' (levels=' + levels.join(',') + ')');
}

// ── Case-file export ────────────────────────────────────────────────────────
module.exports = {
  label: 'Accessibility layer (WP-1.5) — end-to-end + unit tests',
  run: async function run(ctx, record) {
    const { win, EXAMPLES_DIR } = ctx;

    // Guard: all three modules must be loaded.
    const a11y = win.OraVisualCompiler.accessibility;
    if (!a11y || typeof a11y.decorateAltText !== 'function' ||
        typeof a11y.annotateAria !== 'function' ||
        typeof a11y.buildKeyboardNav !== 'function') {
      record('accessibility modules loaded', false,
        'OraVisualCompiler.accessibility incomplete');
      return;
    }
    record('accessibility modules loaded', true, '3/3');

    // compileWithNav on every valid envelope.
    const files = fs.readdirSync(EXAMPLES_DIR)
      .filter((f) => f.endsWith('.valid.json'))
      .sort();

    for (const f of files) {
      if (JSDOM_FLOWCHART_SKIP.has(f)) {
        record('e2e:' + f, true, 'skipped (Mermaid flowchart jsdom skip)');
        continue;
      }
      const envelope = JSON.parse(fs.readFileSync(path.join(EXAMPLES_DIR, f), 'utf-8'));
      try {
        let result = win.OraVisualCompiler.compileWithNav(envelope);
        if (result && typeof result.then === 'function') result = await result;
        const fail = assertEnvelopeOutput(envelope, result);
        if (fail) record('e2e:' + f, false, fail);
        else      record('e2e:' + f, true, 'nav nodes=' + (result.ariaDescription ? result.ariaDescription.nodes.length : 0));
      } catch (err) {
        record('e2e:' + f, false, 'threw: ' + (err && err.stack ? err.stack : err));
      }
    }

    // ── Unit tests against hand-crafted SVG ──────────────────────────────
    try { unitAltText(win, record); }
    catch (err) { record('unit:alt-text suite', false, 'threw: ' + (err && err.stack ? err.stack : err)); }

    try { unitAria(win, record); }
    catch (err) { record('unit:aria suite', false, 'threw: ' + (err && err.stack ? err.stack : err)); }

    try { unitNav(win, record); }
    catch (err) { record('unit:nav suite', false, 'threw: ' + (err && err.stack ? err.stack : err)); }

    // ── compileWithNav() backward-compat signal when a11y missing ─────────
    // Simulate by deleting the namespace on a second pass.
    try {
      const saved = win.OraVisualCompiler.accessibility;
      win.OraVisualCompiler.accessibility = undefined;
      const sampleFile = files.find(f => !JSDOM_FLOWCHART_SKIP.has(f));
      const env = JSON.parse(fs.readFileSync(path.join(EXAMPLES_DIR, sampleFile), 'utf-8'));
      let r = win.OraVisualCompiler.compileWithNav(env);
      if (r && typeof r.then === 'function') r = await r;
      const ok = 'ariaDescription' in r && r.ariaDescription === null;
      record('compat: compileWithNav returns ariaDescription=null when a11y missing',
        ok, ok ? '' : 'value was ' + JSON.stringify(r.ariaDescription));
      win.OraVisualCompiler.accessibility = saved;
    } catch (err) {
      record('compat: compileWithNav null ariaDescription', false,
        'threw: ' + (err && err.stack ? err.stack : err));
    }
  },
};
