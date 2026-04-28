/**
 * canvas-serializer.js — WP-3.2
 *
 * Turns the runtime state of a VisualPanel `userInputLayer` (Konva.Layer) into
 * a `spatial_representation`-shaped JSON object per Protocol v0.2 §10.1 and
 * the authoritative schema at config/visual-schemas/spatial_representation.json.
 *
 * Exposed namespace: window.OraCanvasSerializer.
 *
 *   OraCanvasSerializer.serialize(userInputLayer)         → spatialRep | null
 *   OraCanvasSerializer.detectClusters(entities, rels)    → clusters[]
 *   OraCanvasSerializer.validate(spatialRep)              → {valid, errors}
 *   OraCanvasSerializer.captureFromPanel(panelInstance)   → spatialRep | null
 *
 * ── Shared shape-attribute contract (pact with WP-3.1) ───────────────────────
 *
 * Every user-drawn Konva node on `userInputLayer` is expected to carry these
 * attrs (set by the drawing tools in visual-panel.js):
 *
 *   {
 *     name:                'user-shape',
 *     userShapeType:       'rect'|'ellipse'|'diamond'|'line'|'arrow'|'text',
 *     userShapeId:         '<unique id, e.g. u-rect-0>',
 *     userLabel:           '<string>',
 *     userCluster:         null,                        // computed here
 *     connEndpointStart:   '<userShapeId or null>',     // line/arrow only
 *     connEndpointEnd:     '<userShapeId or null>',     // line/arrow only
 *   }
 *
 * The serializer walks the layer, reads those attrs, and produces
 * spatial_representation. No other attrs are required.
 *
 * ── Shape-type → output mapping ──────────────────────────────────────────────
 *
 *   rect, ellipse, diamond, text  → entity
 *   line, arrow                   → relationship (edge between two entities)
 *
 *   Relationship type mapping (default heuristic):
 *     arrow → 'causal'      (directed edge; user intent is cause-effect)
 *     line  → 'associative' (undirected; user intent is "these are related")
 *
 * ── Cluster detection (Section 3 of the brief) ──────────────────────────────
 *
 *   Method 1 — enclosure. If a user-drawn rect or ellipse entirely contains
 *   two or more other entities (by axis-aligned bounding-box containment),
 *   that shape is treated as a cluster boundary. Its `userLabel` becomes the
 *   cluster label; the enclosed entities become cluster members; the outer
 *   shape is REMOVED from the entities array (its sole purpose is to group).
 *   Method 1 is preferred when applicable — enclosure is intentional.
 *
 *   Method 2 — proximity + edge density. Used only when Method 1 emitted
 *   nothing. Union-Find over non-cluster entities: two entities are merged
 *   when (a) their centroid distance is below threshold, or (b) they are
 *   directly connected by a relationship. Threshold = 15% of canvas width.
 *   Clusters with ≥ 2 members are emitted. Unlabeled clusters receive a
 *   placeholder label "cluster-<n>".
 *
 * ── Empty-layer behavior ────────────────────────────────────────────────────
 *
 * The schema requires entities[].minItems = 1. When the userInputLayer has
 * zero user shapes, `serialize()` returns `null` (the "no spatial input"
 * sentinel). Callers MUST treat `null` as a skip signal — do not construct
 * an empty entities[] or the emit will fail schema validation.
 *
 * ── Validation ──────────────────────────────────────────────────────────────
 *
 * `validate()` uses the Ajv-compiled spatial_representation validator when
 * OraVisualCompiler._ajv is present (after bootstrapAjv succeeded). It falls
 * back to a structural check otherwise: required entities[] non-empty,
 * unique ids, relationship source/target resolve to entity ids.
 *
 * Depends on: (optional) window.OraVisualCompiler._ajv for full validation.
 * No direct dependency on Konva — we duck-type the layer object so the
 * serializer can be unit-tested with plain mocks that expose the same
 * getChildren() / attrs / getClientRect() / stage hooks.
 */

(function () {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────────

  var ENTITY_TYPES       = { rect: 1, ellipse: 1, diamond: 1, text: 1 };
  var RELATIONSHIP_TYPES = { line: 1, arrow: 1 };

  // Relationship-type mapping for the default heuristic (see header §relationship).
  var REL_TYPE_FOR = {
    arrow: 'causal',
    line:  'associative',
  };

  // Method 2 proximity threshold: fraction of canvas width.
  var PROXIMITY_FRAC = 0.15;

  // ── Utilities ─────────────────────────────────────────────────────────────

  function _isObj(v) { return v && typeof v === 'object'; }

  /**
   * Duck-typed attribute access. Konva nodes expose .attrs, getAttr(), and
   * .getClassName()/.className. We prefer .attrs for plain-object access
   * since it lets our tests use simple mocks without a full Konva runtime.
   */
  function _getAttrs(node) {
    if (!_isObj(node)) return {};
    if (_isObj(node.attrs)) return node.attrs;
    return {};
  }

  /**
   * Pull the stage dimensions from a userInputLayer. Konva layers expose
   * getStage(). We fall back to width/height set directly on the layer or
   * on the layer's _canvasDims override (test mock convention).
   */
  function _stageDims(layer) {
    if (!_isObj(layer)) return { width: 0, height: 0 };
    if (_isObj(layer._canvasDims)) return layer._canvasDims;
    try {
      if (typeof layer.getStage === 'function') {
        var st = layer.getStage();
        if (st && typeof st.width === 'function' && typeof st.height === 'function') {
          return { width: st.width(), height: st.height() };
        }
      }
    } catch (e) { /* ignore — mock path below */ }
    // Fallback — direct attrs (mock convenience).
    if (typeof layer.width === 'function' && typeof layer.height === 'function') {
      try { return { width: layer.width(), height: layer.height() }; } catch (e2) {}
    }
    return { width: 0, height: 0 };
  }

  /**
   * Get the list of children from a Konva.Layer. Konva exposes getChildren()
   * which returns a Konva.Collection; .toArray() materializes it. We also
   * accept a plain array for mock convenience.
   */
  function _children(layer) {
    if (!_isObj(layer)) return [];
    if (typeof layer.getChildren === 'function') {
      try {
        var c = layer.getChildren();
        if (Array.isArray(c)) return c;
        if (c && typeof c.toArray === 'function') return c.toArray();
        if (c && typeof c.length === 'number') {
          var out = [];
          for (var i = 0; i < c.length; i++) out.push(c[i]);
          return out;
        }
      } catch (e) { /* fall through */ }
    }
    if (Array.isArray(layer.children)) return layer.children;
    return [];
  }

  /**
   * Compute an axis-aligned bounding box for a user shape node, in stage
   * (layer) pixel coordinates. We prefer Konva's getClientRect() when
   * available (handles transforms); we fall back to attrs for mocks.
   *
   * Returns { x, y, width, height } or null if geometry is unavailable.
   */
  function _bbox(node) {
    if (!_isObj(node)) return null;
    // Konva path — honours scale, rotation, etc.
    if (typeof node.getClientRect === 'function') {
      try {
        var r = node.getClientRect({ relativeTo: node.getLayer ? node.getLayer() : undefined });
        if (r && typeof r.x === 'number') return r;
      } catch (e) { /* fall through to attrs */ }
    }
    // Mock / fallback — read attrs directly.
    var a = _getAttrs(node);
    if (typeof a.x !== 'number' || typeof a.y !== 'number') return null;
    // Ellipse attrs use {x, y, radiusX, radiusY}. Rect uses {x, y, width, height}.
    var shapeType = a.userShapeType;
    if (shapeType === 'ellipse') {
      var rx = typeof a.radiusX === 'number' ? a.radiusX : (a.width ? a.width / 2 : 0);
      var ry = typeof a.radiusY === 'number' ? a.radiusY : (a.height ? a.height / 2 : 0);
      return { x: a.x - rx, y: a.y - ry, width: rx * 2, height: ry * 2 };
    }
    if (shapeType === 'diamond') {
      // Diamond attrs: {x, y} centre + {width, height}, or points[]. Use
      // width/height if present; else derive from points.
      if (typeof a.width === 'number' && typeof a.height === 'number') {
        return { x: a.x - a.width / 2, y: a.y - a.height / 2, width: a.width, height: a.height };
      }
    }
    if (shapeType === 'text') {
      // Text's bbox isn't meaningful for clustering — return a zero-sized
      // point box at the text origin.
      return { x: a.x, y: a.y, width: 0, height: 0 };
    }
    // rect (default)
    var w = typeof a.width === 'number' ? a.width : 0;
    var h = typeof a.height === 'number' ? a.height : 0;
    return { x: a.x, y: a.y, width: w, height: h };
  }

  /**
   * Centre of the bbox. Used for position normalization and proximity
   * clustering. Text entities use their origin (0-width bbox); that's the
   * intended anchor per the brief.
   */
  function _centre(bbox) {
    if (!bbox) return null;
    return { x: bbox.x + bbox.width / 2, y: bbox.y + bbox.height / 2 };
  }

  /**
   * True iff `outer` entirely contains `inner`. Strict containment — the
   * inner bbox must fit fully inside the outer bbox (no boundary ties
   * treated as containment).
   */
  function _contains(outer, inner) {
    if (!outer || !inner) return false;
    return (
      inner.x       >  outer.x                  &&
      inner.y       >  outer.y                  &&
      (inner.x + inner.width)  < (outer.x + outer.width)  &&
      (inner.y + inner.height) < (outer.y + outer.height)
    );
  }

  // ── Serialize ─────────────────────────────────────────────────────────────

  /**
   * Walk the userInputLayer and produce a spatial_representation-shaped
   * JSON object. See the module header for the full algorithm.
   *
   * Returns null when the layer has no user shapes (see "Empty-layer
   * behavior" in the header).
   */
  function serialize(userInputLayer) {
    var dims = _stageDims(userInputLayer);
    var kids = _children(userInputLayer);
    if (kids.length === 0) return null;

    // We operate on a materialized list of {node, attrs, bbox, centre} for
    // two passes (entities first, then relationships that reference them).
    var allUserShapes = [];
    for (var i = 0; i < kids.length; i++) {
      var node  = kids[i];
      var attrs = _getAttrs(node);
      if (attrs.name !== 'user-shape') continue;
      if (typeof attrs.userShapeType !== 'string') continue;
      allUserShapes.push({
        node: node,
        attrs: attrs,
        bbox: _bbox(node),
      });
    }
    if (allUserShapes.length === 0) return null;

    // Partition by category.
    var entityShapes       = [];
    var relationshipShapes = [];
    for (var j = 0; j < allUserShapes.length; j++) {
      var s = allUserShapes[j];
      if (ENTITY_TYPES[s.attrs.userShapeType]) entityShapes.push(s);
      else if (RELATIONSHIP_TYPES[s.attrs.userShapeType]) relationshipShapes.push(s);
      // Unknown types are silently skipped; validation catches downstream issues.
    }

    // Unique-id assertion: two shapes sharing userShapeId is a bug in
    // WP-3.1's id allocator. Refuse to serialize; caller gets a structured
    // error via the thrown Error. (Tests assert on this path.)
    var seenIds = Object.create(null);
    for (var k = 0; k < allUserShapes.length; k++) {
      var id = allUserShapes[k].attrs.userShapeId;
      if (typeof id !== 'string' || id.length === 0) {
        throw new Error('canvas-serializer: user-shape missing userShapeId');
      }
      if (seenIds[id]) {
        throw new Error('canvas-serializer: duplicate userShapeId "' + id + '"');
      }
      seenIds[id] = true;
    }

    // ── Build raw entities ──────────────────────────────────────────────────
    var entities = [];
    for (var e = 0; e < entityShapes.length; e++) {
      var es = entityShapes[e];
      var a  = es.attrs;

      var posX, posY;
      if (a.userShapeType === 'text') {
        // Text anchor at origin.
        posX = typeof a.x === 'number' ? a.x : 0;
        posY = typeof a.y === 'number' ? a.y : 0;
      } else {
        var c = _centre(es.bbox) || { x: 0, y: 0 };
        posX = c.x;
        posY = c.y;
      }

      // Normalize to [0,1] using canvas dims. If dims are 0 we pass raw
      // pixels through (schema accepts any numeric pair); tests configure
      // dims explicitly via _canvasDims.
      var nx = dims.width  > 0 ? posX / dims.width  : posX;
      var ny = dims.height > 0 ? posY / dims.height : posY;

      // Label: userLabel first, then text-content for text shapes, then a
      // schema-safe placeholder ("(unlabeled)" — schema requires minLength=1).
      var label = '';
      if (typeof a.userLabel === 'string' && a.userLabel.length > 0) {
        label = a.userLabel;
      } else if (a.userShapeType === 'text' && typeof a.text === 'string' && a.text.length > 0) {
        label = a.text;
      } else {
        label = '(unlabeled)';
      }

      entities.push({
        id:       a.userShapeId,
        position: [nx, ny],
        label:    label,
        // spec_ref deferred — requires an explicit link to a rendered
        // artifact node. Out of scope for WP-3.2.
        __bbox:   es.bbox,               // internal — stripped before emit
        __type:   a.userShapeType,       // internal — stripped before emit
      });
    }

    // ── Build relationships from line/arrow shapes ──────────────────────────
    var relationships = [];
    var warnings      = [];
    var entityIds     = Object.create(null);
    for (var ei = 0; ei < entities.length; ei++) entityIds[entities[ei].id] = true;

    for (var r = 0; r < relationshipShapes.length; r++) {
      var rs   = relationshipShapes[r];
      var ra   = rs.attrs;
      var src  = ra.connEndpointStart;
      var dst  = ra.connEndpointEnd;

      // Unanchored edges (either endpoint missing) → skip + warn.
      if (typeof src !== 'string' || typeof dst !== 'string' ||
          src.length === 0 || dst.length === 0) {
        warnings.push({
          code: 'W_UNANCHORED_EDGE',
          severity: 'warning',
          message: 'Line/arrow "' + ra.userShapeId + '" has no source/target; skipped.',
          path: 'userShapeId=' + ra.userShapeId,
        });
        continue;
      }

      // Endpoint must reference an entity id. If it doesn't, warn and skip.
      if (!entityIds[src] || !entityIds[dst]) {
        warnings.push({
          code: 'W_EDGE_ENDPOINT_UNRESOLVED',
          severity: 'warning',
          message: 'Edge "' + ra.userShapeId + '" references unknown entity id(s).',
          path: 'userShapeId=' + ra.userShapeId,
        });
        continue;
      }

      var relType = REL_TYPE_FOR[ra.userShapeType] || 'associative';
      var rel     = {
        source: src,
        target: dst,
        type:   relType,
      };
      // Optional strength — only emit if explicitly set on the shape.
      if (typeof ra.userStrength === 'number' &&
          ra.userStrength >= 0 && ra.userStrength <= 1) {
        rel.strength = ra.userStrength;
      }
      relationships.push(rel);
    }

    // ── Cluster detection ───────────────────────────────────────────────────
    var clusters = detectClusters(entities, relationships, {
      canvasWidth: dims.width,
    });

    // Strip internal fields and any entities the cluster pass removed
    // (enclosure-rects are marked __clusterOnly=true).
    var finalEntities = [];
    for (var fi = 0; fi < entities.length; fi++) {
      if (entities[fi].__clusterOnly) continue;
      var clean = {
        id:       entities[fi].id,
        position: entities[fi].position,
        label:    entities[fi].label,
      };
      if (typeof entities[fi].spec_ref === 'string') clean.spec_ref = entities[fi].spec_ref;
      finalEntities.push(clean);
    }

    // Empty safety: if every entity got eaten as cluster-boundary, treat
    // as "no spatial input" — but this is extremely unlikely given the
    // Method 1 containment requirement (≥ 2 enclosed members).
    if (finalEntities.length === 0) return null;

    var out = { entities: finalEntities };
    if (relationships.length > 0) out.relationships = relationships;
    if (clusters.length      > 0) out.clusters      = clusters;
    // hierarchy deferred — requires UI hierarchy affordance (future WP).
    if (warnings.length      > 0) {
      // Warnings are non-normative; schema does NOT define a "warnings"
      // field. We tuck them under a non-enumerated symbol via a
      // non-additional property is not allowed. Instead we return them
      // on a sidecar. Callers can read serialize.lastWarnings.
      _lastWarnings = warnings;
    } else {
      _lastWarnings = [];
    }

    return out;
  }

  // Latest serialize() warnings — accessible for diagnostic logging.
  var _lastWarnings = [];
  function getLastWarnings() { return _lastWarnings.slice(); }

  // ── Cluster detection ─────────────────────────────────────────────────────

  /**
   * Heuristic cluster detection. See the module header for the full
   * algorithm and disambiguation rule. The `entities` array is augmented
   * in-place: any entity that becomes a cluster-only boundary is marked
   * with __clusterOnly=true (and stripped by serialize before emit).
   *
   * opts.canvasWidth: used by Method 2 for the proximity threshold. If 0,
   * Method 2 falls back to treating only directly-connected entities as
   * same-cluster (no distance test).
   */
  function detectClusters(entities, relationships, opts) {
    opts = opts || {};
    if (!Array.isArray(entities) || entities.length === 0) return [];

    // ── Method 1: enclosure ────────────────────────────────────────────────
    // Candidate outer shapes: rect or ellipse entities with a non-null bbox
    // that are NOT text (text bboxes are 0-sized and can't enclose).
    var containers = [];
    for (var i = 0; i < entities.length; i++) {
      var ent = entities[i];
      if (!ent.__bbox) continue;
      if (ent.__type !== 'rect' && ent.__type !== 'ellipse') continue;
      containers.push(ent);
    }

    var method1Clusters = [];
    // Sort containers descending by area so the outermost wins when nested.
    containers.sort(function (a, b) {
      var aa = a.__bbox.width * a.__bbox.height;
      var bb = b.__bbox.width * b.__bbox.height;
      return bb - aa;
    });

    var usedAsContainer = Object.create(null);
    var containedBy     = Object.create(null);

    for (var c = 0; c < containers.length; c++) {
      var outer = containers[c];
      if (usedAsContainer[outer.id]) continue;           // outer of someone else
      if (containedBy[outer.id])     continue;           // inner of someone else
      var members = [];
      for (var m = 0; m < entities.length; m++) {
        var inner = entities[m];
        if (inner === outer)              continue;
        if (!inner.__bbox)                continue;
        if (containedBy[inner.id])        continue;
        if (_contains(outer.__bbox, inner.__bbox)) {
          members.push(inner.id);
          containedBy[inner.id] = outer.id;
        }
      }
      if (members.length >= 2) {
        var label = (typeof outer.label === 'string' && outer.label.length > 0 &&
                     outer.label !== '(unlabeled)')
          ? outer.label
          : 'cluster-' + (method1Clusters.length + 1);
        method1Clusters.push({ members: members.slice(), label: label });
        outer.__clusterOnly = true;          // remove from entity emit
        usedAsContainer[outer.id] = true;
      } else {
        // Roll back containment marks — outer doesn't qualify.
        for (var ur = 0; ur < members.length; ur++) delete containedBy[members[ur]];
      }
    }

    if (method1Clusters.length > 0) return method1Clusters;

    // ── Method 2: proximity + edge density (Union-Find) ────────────────────
    // Only runs when Method 1 emitted nothing.
    var nonBoundary = entities.filter(function (e) { return !e.__clusterOnly; });
    if (nonBoundary.length < 2) return [];

    // Proximity threshold in raw pixel units. If canvas width is 0 we skip
    // the proximity step entirely (connection-only clustering).
    var w = typeof opts.canvasWidth === 'number' ? opts.canvasWidth : 0;
    var proximityPx = w * PROXIMITY_FRAC;

    // Union-Find scaffold over entity ids.
    var parent = Object.create(null);
    var rank   = Object.create(null);
    function find(x) {
      if (parent[x] === x) return x;
      parent[x] = find(parent[x]);
      return parent[x];
    }
    function union(a, b) {
      var ra = find(a), rb = find(b);
      if (ra === rb) return;
      if (rank[ra] < rank[rb]) { var t = ra; ra = rb; rb = t; }
      parent[rb] = ra;
      if (rank[ra] === rank[rb]) rank[ra] += 1;
    }
    for (var ix = 0; ix < nonBoundary.length; ix++) {
      parent[nonBoundary[ix].id] = nonBoundary[ix].id;
      rank[nonBoundary[ix].id]   = 0;
    }

    // Edge-density unions: every relationship connects two entities.
    if (Array.isArray(relationships)) {
      for (var rr = 0; rr < relationships.length; rr++) {
        var rel = relationships[rr];
        if (rel && typeof rel.source === 'string' && typeof rel.target === 'string') {
          if (parent[rel.source] != null && parent[rel.target] != null) {
            union(rel.source, rel.target);
          }
        }
      }
    }

    // Proximity unions: O(n^2) pairwise — fine for user-drawn canvases
    // where n is typically < 50.
    if (proximityPx > 0) {
      // Centre in pixel space. The entity position is normalized [0,1];
      // multiply by canvas dims. We only have width; approximate y-scale
      // with the same ratio (canvases are usually square-ish and the
      // threshold is fuzzy anyway).
      function px(ent) {
        var x = ent.position[0], y = ent.position[1];
        return { x: x * w, y: y * w };
      }
      for (var a1 = 0; a1 < nonBoundary.length; a1++) {
        for (var b1 = a1 + 1; b1 < nonBoundary.length; b1++) {
          var pa = px(nonBoundary[a1]);
          var pb = px(nonBoundary[b1]);
          var dx = pa.x - pb.x, dy = pa.y - pb.y;
          if ((dx * dx + dy * dy) <= (proximityPx * proximityPx)) {
            union(nonBoundary[a1].id, nonBoundary[b1].id);
          }
        }
      }
    }

    // Group by root. Emit clusters with ≥ 2 members only.
    var groups = Object.create(null);
    for (var ii = 0; ii < nonBoundary.length; ii++) {
      var root = find(nonBoundary[ii].id);
      if (!groups[root]) groups[root] = [];
      groups[root].push(nonBoundary[ii].id);
    }
    var out = [];
    var n = 0;
    // Preserve insertion order via Object.keys.
    var rootKeys = Object.keys(groups);
    for (var rk = 0; rk < rootKeys.length; rk++) {
      var members = groups[rootKeys[rk]];
      if (members.length < 2) continue;
      n += 1;
      out.push({ members: members.slice(), label: 'cluster-' + n });
    }
    return out;
  }

  // ── Validation ────────────────────────────────────────────────────────────

  /**
   * Validate a spatial_representation object. Uses Ajv via
   * OraVisualCompiler._ajv when available (full schema), else falls back
   * to a structural check.
   *
   * Returns { valid: bool, errors: [{code, message, path}] }.
   */
  function validate(spatialRep) {
    // Ajv path.
    var ajv = (window.OraVisualCompiler && window.OraVisualCompiler._ajv) || null;
    if (ajv && typeof ajv.getSchema === 'function') {
      try {
        var validator =
          ajv.getSchema('spatial_representation.json') ||
          ajv.getSchema('https://ora.local/schemas/spatial_representation.json');
        if (typeof validator === 'function') {
          var ok = validator(spatialRep);
          if (ok) return { valid: true, errors: [] };
          var errs = (validator.errors || []).map(function (e) {
            return {
              code:    'E_SCHEMA_INVALID',
              message: '[Ajv] ' + (e.instancePath || '(root)') + ': ' + e.message,
              path:    e.instancePath || '',
            };
          });
          return { valid: false, errors: errs };
        }
      } catch (e) { /* fall through to structural */ }
    }

    // Structural fallback.
    return _validateStructural(spatialRep);
  }

  function _validateStructural(sr) {
    var errors = [];
    if (!_isObj(sr)) {
      return { valid: false, errors: [{ code: 'E_MISSING_FIELD', message: 'not an object', path: '' }] };
    }
    if (!Array.isArray(sr.entities) || sr.entities.length === 0) {
      errors.push({ code: 'E_MISSING_FIELD', message: 'entities[] required and non-empty', path: 'entities' });
    }
    var ids = Object.create(null);
    if (Array.isArray(sr.entities)) {
      for (var i = 0; i < sr.entities.length; i++) {
        var ent = sr.entities[i];
        if (!_isObj(ent)) { errors.push({ code: 'E_SCHEMA_INVALID', message: 'entity not object', path: 'entities[' + i + ']' }); continue; }
        if (typeof ent.id !== 'string' || ent.id.length === 0) {
          errors.push({ code: 'E_MISSING_FIELD', message: 'entity.id required', path: 'entities[' + i + '].id' });
        } else if (ids[ent.id]) {
          errors.push({ code: 'E_SCHEMA_INVALID', message: 'duplicate entity id "' + ent.id + '"', path: 'entities[' + i + '].id' });
        } else {
          ids[ent.id] = true;
        }
        if (!Array.isArray(ent.position) || ent.position.length !== 2 ||
            typeof ent.position[0] !== 'number' || typeof ent.position[1] !== 'number') {
          errors.push({ code: 'E_SCHEMA_INVALID', message: 'entity.position must be [x,y]', path: 'entities[' + i + '].position' });
        }
        if (typeof ent.label !== 'string' || ent.label.length === 0) {
          errors.push({ code: 'E_SCHEMA_INVALID', message: 'entity.label required', path: 'entities[' + i + '].label' });
        }
      }
    }
    if (Array.isArray(sr.relationships)) {
      var validTypes = { causal: 1, associative: 1, hierarchical: 1, temporal: 1 };
      for (var r = 0; r < sr.relationships.length; r++) {
        var rel = sr.relationships[r];
        if (!_isObj(rel)) { errors.push({ code: 'E_SCHEMA_INVALID', message: 'rel not object', path: 'relationships[' + r + ']' }); continue; }
        if (typeof rel.source !== 'string' || !ids[rel.source]) {
          errors.push({ code: 'E_SCHEMA_INVALID', message: 'rel.source unresolved', path: 'relationships[' + r + '].source' });
        }
        if (typeof rel.target !== 'string' || !ids[rel.target]) {
          errors.push({ code: 'E_SCHEMA_INVALID', message: 'rel.target unresolved', path: 'relationships[' + r + '].target' });
        }
        if (typeof rel.type !== 'string' || !validTypes[rel.type]) {
          errors.push({ code: 'E_SCHEMA_INVALID', message: 'rel.type must be causal|associative|hierarchical|temporal', path: 'relationships[' + r + '].type' });
        }
      }
    }
    return { valid: errors.length === 0, errors: errors };
  }

  // ── Panel helper ──────────────────────────────────────────────────────────

  /**
   * Capture a spatial_representation from a live VisualPanel instance. The
   * panel exposes `userInputLayer` directly as a public field (see
   * visual-panel.js); no getter is required. WP-3.3 will wire this into
   * chat submission.
   *
   * NOTE: if a future refactor makes userInputLayer private (e.g. prefix
   * `_userInputLayer`), add a public getter on VisualPanel and update the
   * lookup path here. For now both `userInputLayer` and `_userInputLayer`
   * are accepted to keep this code resilient to either convention.
   */
  function captureFromPanel(panel) {
    if (!_isObj(panel)) return null;
    var layer = panel.userInputLayer || panel._userInputLayer || null;
    if (!layer) return null;
    return serialize(layer);
  }

  // ── Exports ───────────────────────────────────────────────────────────────

  window.OraCanvasSerializer = {
    serialize:          serialize,
    detectClusters:     detectClusters,
    validate:           validate,
    captureFromPanel:   captureFromPanel,
    getLastWarnings:    getLastWarnings,
    // Internal knobs exposed for tests.
    _PROXIMITY_FRAC:    PROXIMITY_FRAC,
    _REL_TYPE_FOR:      REL_TYPE_FOR,
  };
})();
