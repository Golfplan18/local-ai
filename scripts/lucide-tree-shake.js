#!/usr/bin/env node
/* lucide-tree-shake.js — WP-7.0.3
 *
 * Walks toolbar definitions and customization packs, collects every icon name
 * referenced, and emits a tree-shaken runtime icon set containing only those
 * icons. Output:
 *
 *   ~/ora/server/static/runtime/icon-set.json
 *     {
 *       "version": "<lucide-static version>",
 *       "generated_at": "<ISO timestamp>",
 *       "source": "<this script's path>",
 *       "referenced_from": [<list of source files scanned>],
 *       "icon_count": N,
 *       "icons": { "<name>": "<svg string>", ... }
 *     }
 *
 * Reference sources scanned:
 *   ~/ora/config/toolbars/*.json   — toolbar definitions (WP-7.1.1, WP-7.1.6)
 *   ~/ora/config/packs/**\/*.json   — shipped customization packs (WP-7.8.1)
 *
 * Each JSON is searched (recursively) for any `"icon"` field whose value is
 * a string matching the Lucide name pattern (lowercase letters, digits,
 * hyphens). Inline SVGs (values starting with "<svg") are skipped — they
 * don't need vendoring.
 *
 * If no source files exist yet (Phase 7 foundation: WP-7.1.6 and WP-7.8.1
 * haven't authored them), the script emits a clearly-marked "no references
 * found, no tree-shake performed" output containing zero icons. The
 * mechanism exists; subsequent WPs feed it.
 *
 * Usage:
 *   node ~/ora/scripts/lucide-tree-shake.js [--full] [--out <path>]
 *
 *   --full        Bypass tree-shaking and emit the entire vendored set
 *                 (~7.6 MB). Useful as a fallback during development.
 *   --out <path>  Override the output path (default:
 *                 ~/ora/server/static/runtime/icon-set.json).
 *   --quiet       Suppress info log output (warnings/errors still printed).
 */

'use strict';

var fs = require('fs');
var path = require('path');

var ORA_ROOT = path.resolve(__dirname, '..');
var VENDOR_DIR = path.join(ORA_ROOT, 'server', 'static', 'vendor', 'lucide');
var ICONS_DIR = path.join(VENDOR_DIR, 'icons');
var NAMES_FILE = path.join(VENDOR_DIR, 'names.json');
var VERSION_FILE = path.join(VENDOR_DIR, 'VERSION');
var TOOLBARS_DIR = path.join(ORA_ROOT, 'config', 'toolbars');
var PACKS_DIR = path.join(ORA_ROOT, 'config', 'packs');
var DEFAULT_OUT = path.join(ORA_ROOT, 'server', 'static', 'runtime', 'icon-set.json');

// ---- arg parse -------------------------------------------------------------

function _parseArgs(argv) {
  var opts = { full: false, out: DEFAULT_OUT, quiet: false };
  for (var i = 0; i < argv.length; i++) {
    var a = argv[i];
    if (a === '--full') opts.full = true;
    else if (a === '--quiet') opts.quiet = true;
    else if (a === '--out') opts.out = argv[++i];
    else if (a === '-h' || a === '--help') {
      process.stdout.write(
        'Usage: lucide-tree-shake.js [--full] [--out <path>] [--quiet]\n');
      process.exit(0);
    }
  }
  return opts;
}

// ---- helpers ---------------------------------------------------------------

function _log(opts, msg) {
  if (!opts.quiet) process.stdout.write(msg + '\n');
}

function _warn(msg) {
  process.stderr.write('warning: ' + msg + '\n');
}

function _readJsonSafe(filePath) {
  try {
    var raw = fs.readFileSync(filePath, 'utf8');
    return JSON.parse(raw);
  } catch (e) {
    _warn('could not parse ' + filePath + ': ' + e.message);
    return null;
  }
}

function _walkDir(dir, predicate, accum) {
  if (!fs.existsSync(dir)) return accum;
  var entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch (e) {
    _warn('could not read ' + dir + ': ' + e.message);
    return accum;
  }
  for (var i = 0; i < entries.length; i++) {
    var entry = entries[i];
    var full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      _walkDir(full, predicate, accum);
    } else if (entry.isFile() && predicate(full)) {
      accum.push(full);
    }
  }
  return accum;
}

function _collectIconRefs(value, names) {
  if (value == null) return;
  if (typeof value === 'string') return;
  if (Array.isArray(value)) {
    for (var i = 0; i < value.length; i++) _collectIconRefs(value[i], names);
    return;
  }
  if (typeof value === 'object') {
    var keys = Object.keys(value);
    for (var k = 0; k < keys.length; k++) {
      var key = keys[k];
      var v = value[key];
      // Capture any field literally named "icon" whose value is a Lucide
      // name (string of lowercase letters/digits/hyphens). Inline SVGs are
      // skipped — they don't need vendoring.
      if (key === 'icon' && typeof v === 'string') {
        var trimmed = v.trim();
        if (trimmed.length > 0
            && trimmed.slice(0, 4).toLowerCase() !== '<svg'
            && /^[a-z0-9][a-z0-9-]*$/.test(trimmed)) {
          names.add(trimmed);
        }
      } else {
        _collectIconRefs(v, names);
      }
    }
  }
}

function _scanSourceFiles(opts) {
  var files = [];
  var jsonFilter = function (p) { return p.toLowerCase().endsWith('.json'); };

  _walkDir(TOOLBARS_DIR, jsonFilter, files);
  _walkDir(PACKS_DIR, jsonFilter, files);

  _log(opts, 'scanned source dirs:');
  _log(opts, '  ' + TOOLBARS_DIR + '  '
       + (fs.existsSync(TOOLBARS_DIR) ? '(present)' : '(absent)'));
  _log(opts, '  ' + PACKS_DIR + '  '
       + (fs.existsSync(PACKS_DIR) ? '(present)' : '(absent)'));
  _log(opts, 'found ' + files.length + ' JSON file(s)');

  return files;
}

function _extractReferencedNames(files, opts) {
  var refs = new Set();
  for (var i = 0; i < files.length; i++) {
    var data = _readJsonSafe(files[i]);
    if (data) _collectIconRefs(data, refs);
  }
  _log(opts, 'extracted ' + refs.size + ' unique icon reference(s)');
  return refs;
}

function _loadCanonicalNames() {
  if (!fs.existsSync(NAMES_FILE)) {
    throw new Error(
      'Lucide names.json not found at ' + NAMES_FILE
      + ' — vendor the library first.');
  }
  var payload = _readJsonSafe(NAMES_FILE);
  if (!payload || !Array.isArray(payload.names)) {
    throw new Error('names.json malformed: expected { version, names: [...] }');
  }
  return {
    version: payload.version || 'unknown',
    set: new Set(payload.names),
    list: payload.names
  };
}

function _loadIconSvg(name) {
  var p = path.join(ICONS_DIR, name + '.svg');
  if (!fs.existsSync(p)) return null;
  return fs.readFileSync(p, 'utf8');
}

function _ensureDir(filePath) {
  var dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

// ---- main ------------------------------------------------------------------

function main() {
  var opts = _parseArgs(process.argv.slice(2));
  _log(opts, 'lucide-tree-shake starting');

  var canonical = _loadCanonicalNames();
  _log(opts, 'canonical Lucide name set: '
       + canonical.list.length + ' names (lucide-static '
       + canonical.version + ')');

  var sourceFiles = _scanSourceFiles(opts);
  var referenced = _extractReferencedNames(sourceFiles, opts);

  // Resolve output set.
  var outputNames;
  var mode;
  if (opts.full) {
    outputNames = canonical.list.slice();
    mode = 'full-no-tree-shake-by-flag';
  } else if (referenced.size === 0) {
    outputNames = [];
    mode = 'no-references-found-no-tree-shake-performed';
    _log(opts, 'no references found, no tree-shake performed (mechanism present, awaiting WP-7.1.6 + WP-7.8.1 to feed it)');
  } else {
    outputNames = [];
    var unknown = [];
    referenced.forEach(function (n) {
      if (canonical.set.has(n)) outputNames.push(n);
      else unknown.push(n);
    });
    outputNames.sort();
    if (unknown.length > 0) {
      _warn('the following referenced names are not in the canonical Lucide set: '
            + unknown.sort().join(', '));
    }
    mode = 'tree-shaken';
  }

  // Load the SVGs.
  var icons = {};
  var loaded = 0;
  var missing = [];
  outputNames.forEach(function (name) {
    var svg = _loadIconSvg(name);
    if (svg == null) {
      missing.push(name);
    } else {
      icons[name] = svg;
      loaded++;
    }
  });
  if (missing.length > 0) {
    _warn('SVG files not found on disk for: ' + missing.join(', '));
  }

  // Compose payload.
  var payload = {
    version: canonical.version,
    generated_at: new Date().toISOString(),
    source: __filename.replace(ORA_ROOT, '~/ora'),
    mode: mode,
    referenced_from: sourceFiles.map(function (p) {
      return p.replace(ORA_ROOT, '~/ora');
    }),
    referenced_names: Array.from(referenced).sort(),
    icon_count: loaded,
    icons: icons
  };

  _ensureDir(opts.out);
  fs.writeFileSync(opts.out, JSON.stringify(payload, null, 0));

  // Friendly summary.
  var rawSize = 0;
  outputNames.forEach(function (n) { if (icons[n]) rawSize += icons[n].length; });
  var jsonStat = fs.statSync(opts.out);
  _log(opts, 'wrote ' + opts.out);
  _log(opts, 'mode=' + mode + ', icons=' + loaded
       + ', payload bytes=' + jsonStat.size
       + ' (svg chars: ' + rawSize + ')');

  return payload;
}

if (require.main === module) {
  try {
    main();
  } catch (e) {
    process.stderr.write('error: ' + e.message + '\n');
    process.exit(1);
  }
}

module.exports = {
  main: main,
  _collectIconRefs: _collectIconRefs,
  _extractReferencedNames: _extractReferencedNames,
  _loadCanonicalNames: _loadCanonicalNames
};
