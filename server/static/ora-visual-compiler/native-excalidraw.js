/*
 * Native Excalidraw scene builder for structural visual types.
 *
 * The semantic envelope remains the source of truth. This module only turns
 * structural nodes and relationships into editable Excalidraw objects; it
 * does not parse Mermaid and it is never used for types whose data encodes
 * position or value-driven geometry.
 */
(function (global) {
  'use strict';

  var ns = global.OraVisualCompiler = global.OraVisualCompiler || {};
  var NATIVE_TYPES = [
    'causal_loop_diagram', 'stock_and_flow', 'causal_dag', 'fishbone',
    'decision_tree', 'influence_diagram', 'bow_tie', 'ibis', 'pro_con',
    'concept_map', 'c4',
  ];
  var NATIVE_SET = new Set(NATIVE_TYPES);

  function text(value, fallback) {
    var result = String(value == null ? '' : value).replace(/\s+/g, ' ').trim();
    return result || (fallback || '');
  }

  function safe(value) {
    return text(value, 'item').replace(/[^A-Za-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '')
      .slice(0, 80) || 'item';
  }

  function hash(value) {
    var h = 2166136261;
    var source = String(value);
    for (var i = 0; i < source.length; i += 1) {
      h ^= source.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return (h >>> 0).toString(16).padStart(8, '0');
  }

  function graph(envelope) {
    var type = envelope && envelope.type;
    var spec = (envelope && envelope.spec) || {};
    var nodes = [];
    var edges = [];
    var seen = new Set();

    function node(id, label, kind) {
      var key = text(id, 'node-' + nodes.length);
      if (!seen.has(key)) {
        seen.add(key);
        nodes.push({ id: key, label: text(label, key), kind: kind || 'node' });
      } else {
        var existing = nodes.find(function (entry) { return entry.id === key; });
        if (existing && (!existing.label || existing.label === key) && label) {
          existing.label = text(label, key);
        }
      }
      return key;
    }

    function edge(from, to, label, kind) {
      var source = node(from, from);
      var target = node(to, to);
      if (!edges.some(function (entry) {
        return entry.from === source && entry.to === target && entry.label === text(label, '');
      })) {
        edges.push({ from: source, to: target, label: text(label, ''), kind: kind || 'relationship' });
      }
    }

    function nestedCause(parent, cause, path) {
      if (!cause) return;
      var id = path + '-' + nodes.length;
      node(id, cause.text || cause.label || id, 'cause');
      edge(parent, id, 'causes', 'cause');
      (cause.sub_causes || cause.children || []).forEach(function (child, index) {
        nestedCause(id, child, id + '-' + index);
      });
    }

    if (type === 'causal_loop_diagram') {
      (spec.variables || []).forEach(function (entry) { node(entry.id, entry.label, 'variable'); });
      (spec.links || []).forEach(function (entry) { edge(entry.from, entry.to, entry.polarity, 'causal-link'); });
      (spec.loops || []).forEach(function (loop) {
        var members = loop.members || [];
        members.slice(0, -1).forEach(function (member, index) {
          edge(member, members[index + 1], loop.label || loop.type, 'loop');
        });
      });
    } else if (type === 'stock_and_flow') {
      (spec.stocks || []).forEach(function (entry) { node(entry.id, entry.label, 'stock'); });
      (spec.clouds || []).forEach(function (entry) { node(entry.id, entry.label || 'Source / sink', 'cloud'); });
      (spec.auxiliaries || []).forEach(function (entry) { node(entry.id, entry.label, 'auxiliary'); });
      (spec.flows || []).forEach(function (entry) { edge(entry.from, entry.to, entry.label, 'flow'); });
      (spec.info_links || []).forEach(function (entry) { edge(entry.from, entry.to, 'information', 'info-link'); });
    } else if (type === 'causal_dag') {
      var dag = text(spec.dsl, '');
      var declaration = /([A-Za-z_][\w-]*)\s*\[([^\]]+)\]/g;
      var match;
      while ((match = declaration.exec(dag))) node(match[1], match[2], 'causal-node');
      var relation = /([A-Za-z_][\w-]*)\s*[-=]+>\s*([A-Za-z_][\w-]*)/g;
      while ((match = relation.exec(dag))) edge(match[1], match[2], 'causes', 'causal-edge');
      node(spec.focal_exposure, spec.focal_exposure, 'exposure');
      node(spec.focal_outcome, spec.focal_outcome, 'outcome');
    } else if (type === 'fishbone') {
      var effect = node('effect', spec.effect, 'effect');
      (spec.categories || []).forEach(function (category, index) {
        var categoryId = node('category-' + index, category.name, 'category');
        edge(categoryId, effect, category.name, 'category');
        (category.causes || []).forEach(function (cause, causeIndex) {
          nestedCause(categoryId, cause, 'cause-' + index + '-' + causeIndex);
        });
      });
    } else if (type === 'decision_tree') {
      function walkDecision(entry, parent, path) {
        if (!entry) return;
        var id = path || 'root';
        node(id, entry.label, entry.kind || 'decision');
        if (parent) edge(parent, id, entry.edge_label || '', 'decision');
        (entry.children || []).forEach(function (child, index) {
          walkDecision(child.node || child, id, id + '-' + index);
        });
      }
      walkDecision(spec.root, null, 'root');
    } else if (type === 'influence_diagram') {
      (spec.nodes || []).forEach(function (entry) { node(entry.id, entry.label, entry.kind); });
      (spec.arcs || []).forEach(function (entry) { edge(entry.from, entry.to, entry.type, 'influence'); });
    } else if (type === 'bow_tie') {
      var hazard = node('hazard', spec.hazard_event && spec.hazard_event.label, 'hazard');
      (spec.threats || []).forEach(function (threat) {
        node(threat.id, threat.label, 'threat');
        edge(threat.id, hazard, 'threatens', 'threat');
        (threat.preventive_controls || []).forEach(function (control) {
          node(control.id, control.label, 'control');
          edge(control.id, threat.id, control.type || 'prevents', 'control');
        });
      });
      (spec.consequences || []).forEach(function (consequence) {
        node(consequence.id, consequence.label, 'consequence');
        edge(hazard, consequence.id, 'leads to', 'consequence');
        (consequence.mitigative_controls || []).forEach(function (control) {
          node(control.id, control.label, 'control');
          edge(control.id, consequence.id, control.type || 'mitigates', 'control');
        });
      });
      (spec.escalation_factors || []).forEach(function (factor, index) {
        node(factor.id || 'factor-' + index, factor.label, 'escalation');
      });
    } else if (type === 'ibis') {
      (spec.nodes || []).forEach(function (entry) { node(entry.id, entry.text, entry.type); });
      (spec.edges || []).forEach(function (entry) { edge(entry.from, entry.to, entry.type, 'argument'); });
    } else if (type === 'pro_con') {
      var claim = node('claim', spec.claim, 'claim');
      (spec.pros || []).forEach(function (entry, index) {
        var id = node('pro-' + index, entry.text, 'pro');
        edge(claim, id, 'supports', 'pro');
        (entry.children || []).forEach(function (child, childIndex) {
          var childId = node('pro-' + index + '-' + childIndex, child.text, 'pro');
          edge(id, childId, 'because', 'pro');
        });
      });
      (spec.cons || []).forEach(function (entry, index) {
        var id = node('con-' + index, entry.text, 'con');
        edge(id, claim, 'challenges', 'con');
        (entry.children || []).forEach(function (child, childIndex) {
          var childId = node('con-' + index + '-' + childIndex, child.text, 'con');
          edge(id, childId, 'because', 'con');
        });
      });
      if (spec.decision) edge(claim, node('decision', spec.decision, 'decision'), 'decision', 'decision');
    } else if (type === 'concept_map') {
      (spec.concepts || []).forEach(function (entry) { node(entry.id, entry.label, 'concept'); });
      var phrases = {};
      (spec.linking_phrases || []).forEach(function (entry) { phrases[entry.id] = entry.text; });
      (spec.propositions || []).forEach(function (entry) {
        edge(entry.from_concept, entry.to_concept, phrases[entry.via_phrase] || entry.via_phrase, 'proposition');
      });
    } else if (type === 'c4') {
      var c4 = text(spec.dsl, '');
      var c4Nodes = /([A-Za-z_][\w-]*)\s*=\s*(person|softwareSystem|container|component)\s+"([^"]+)"/g;
      while ((match = c4Nodes.exec(c4))) node(match[1], match[3], match[2]);
      var c4Edges = /([A-Za-z_][\w-]*)\s*->\s*([A-Za-z_][\w-]*)\s+"([^"]*)"/g;
      while ((match = c4Edges.exec(c4))) edge(match[1], match[2], match[3], 'uses');
    }

    if (!nodes.length) node('visual', envelope && envelope.title || type || 'visual', 'visual');
    return { nodes: nodes, edges: edges };
  }

  function layout(graphData) {
    var incoming = {};
    graphData.nodes.forEach(function (entry) { incoming[entry.id] = []; });
    graphData.edges.forEach(function (entry) {
      if (incoming[entry.to]) incoming[entry.to].push(entry.from);
    });

    var depthMemo = {};
    function depth(id, visiting) {
      if (depthMemo[id] != null) return depthMemo[id];
      if (visiting[id]) return 0;
      var next = Object.assign({}, visiting, { [id]: true });
      var parents = incoming[id] || [];
      var value = parents.length
        ? Math.max.apply(null, parents.map(function (parent) { return depth(parent, next) + 1; }))
        : 0;
      depthMemo[id] = value;
      return value;
    }

    var columns = {};
    graphData.nodes.forEach(function (entry) {
      var column = depth(entry.id, {});
      (columns[column] = columns[column] || []).push(entry);
    });

    var positions = {};
    graphData.nodes.forEach(function (entry) {
      var column = depth(entry.id, {});
      var columnEntries = columns[column];
      var row = columnEntries.indexOf(entry);
      var width = Math.max(150, Math.min(280, entry.label.length * 7 + 32));
      positions[entry.id] = {
        x: 80 + column * 260,
        y: 80 + row * 120,
        width: width,
        height: 56,
      };
    });
    return positions;
  }

  function baseElement(id, type, bounds, customData) {
    return {
      id: id,
      type: type,
      x: bounds.x,
      y: bounds.y,
      width: bounds.width,
      height: bounds.height,
      angle: 0,
      strokeColor: '#1e1e1e',
      backgroundColor: type === 'rectangle' ? '#f8f9fa' : 'transparent',
      fillStyle: 'solid',
      strokeWidth: 2,
      strokeStyle: 'solid',
      roughness: 0,
      opacity: 100,
      groupIds: [],
      frameId: null,
      roundness: type === 'rectangle' ? { type: 3 } : null,
      seed: parseInt(hash(id).slice(0, 8), 16),
      version: 1,
      versionNonce: parseInt(hash(id + ':version').slice(0, 8), 16),
      isDeleted: false,
      boundElements: [],
      updated: 1,
      link: null,
      locked: false,
      customData: customData,
    };
  }

  function tagFingerprint(element) {
    element.customData.originalGenerationFingerprint = JSON.stringify({
      x: Number(element.x) || 0,
      y: Number(element.y) || 0,
      width: Number(element.width) || 0,
      height: Number(element.height) || 0,
      angle: Number(element.angle) || 0,
      locked: element.locked === true,
      text: String(element.text || ''),
      points: Array.isArray(element.points) ? element.points : null,
      strokeColor: element.strokeColor || '',
      backgroundColor: element.backgroundColor || '',
      fillStyle: element.fillStyle || '',
    });
    return element;
  }

  function buildScene(envelope, options) {
    var assistantVisualId = text(options && options.assistantVisualId,
      'assistant:' + text(envelope && envelope.id, 'visual'));
    var revision = Number(options && options.generationRevision) || 1;
    var graphData = graph(envelope || {});
    var sharedLayout = options && options.layout;
    var positions = sharedLayout && sharedLayout.nodes
      ? sharedLayout.nodes : layout(graphData);
    var groupId = 'ora-group-' + hash(assistantVisualId);
    var elements = [];
    var byId = {};

    function owned(kind, semanticElementId) {
      return {
        oraAssistantVisual: true,
        oraAssistantVisualKind: 'native',
        assistantVisualId: assistantVisualId,
        generationRevision: revision,
        semanticElementId: semanticElementId,
        nativeKind: kind,
      };
    }

    graphData.nodes.forEach(function (entry) {
      var bounds = positions[entry.id];
      var semantic = text(envelope.type, 'visual') + ':node:' + entry.id;
      var nodeElement = baseElement(
        'ora-' + hash(assistantVisualId + ':' + semantic + ':shape'),
        entry.kind === 'decision' ? 'diamond' : 'rectangle',
        bounds,
        owned(entry.kind, semantic)
      );
      nodeElement.groupIds = [groupId + '-' + safe(entry.id)];
      elements.push(tagFingerprint(nodeElement));
      byId[entry.id] = { element: nodeElement, bounds: bounds, semantic: semantic };

      var label = baseElement(
        'ora-' + hash(assistantVisualId + ':' + semantic + ':label'),
        'text',
        { x: bounds.x + 10, y: bounds.y + 16, width: bounds.width - 20, height: 24 },
        owned(entry.kind + '-label', semantic + ':label')
      );
      label.text = entry.label;
      label.originalText = entry.label;
      label.fontSize = 16;
      label.fontFamily = 1;
      label.textAlign = 'center';
      label.verticalAlign = 'middle';
      label.containerId = nodeElement.id;
      label.autoResize = false;
      label.lineHeight = 1.25;
      label.groupIds = nodeElement.groupIds.slice();
      elements.push(tagFingerprint(label));
      nodeElement.boundElements.push({ id: label.id, type: 'text' });
    });

    graphData.edges.forEach(function (entry) {
      var from = byId[entry.from];
      var to = byId[entry.to];
      if (!from || !to) return;
      var fromCenter = { x: from.bounds.x + from.bounds.width / 2, y: from.bounds.y + from.bounds.height / 2 };
      var toCenter = { x: to.bounds.x + to.bounds.width / 2, y: to.bounds.y + to.bounds.height / 2 };
      var dx = toCenter.x - fromCenter.x;
      var dy = toCenter.y - fromCenter.y;
      var scale = Math.min(
        (from.bounds.width / 2) / Math.max(Math.abs(dx), 1),
        (from.bounds.height / 2) / Math.max(Math.abs(dy), 1),
        (to.bounds.width / 2) / Math.max(Math.abs(dx), 1),
        (to.bounds.height / 2) / Math.max(Math.abs(dy), 1)
      );
      if (!isFinite(scale) || scale <= 0) scale = 0.25;
      var start = { x: fromCenter.x + dx * scale, y: fromCenter.y + dy * scale };
      var end = { x: toCenter.x - dx * scale, y: toCenter.y - dy * scale };
      var semantic = text(envelope.type, 'visual') + ':edge:' + entry.from + '->' + entry.to + ':' + entry.label;
      var arrow = baseElement(
        'ora-' + hash(assistantVisualId + ':' + semantic),
        'arrow',
        { x: start.x, y: start.y, width: end.x - start.x, height: end.y - start.y },
        owned(entry.kind, semantic)
      );
      arrow.width = 0;
      arrow.height = 0;
      arrow.points = [[0, 0], [end.x - start.x, end.y - start.y]];
      arrow.lastCommittedPoint = [end.x - start.x, end.y - start.y];
      arrow.startArrowhead = null;
      arrow.endArrowhead = 'arrow';
      arrow.startBinding = { elementId: from.element.id, focus: 0, gap: 4, fixedPoint: null };
      arrow.endBinding = { elementId: to.element.id, focus: 0, gap: 4, fixedPoint: null };
      arrow.boundElements = null;
      elements.push(tagFingerprint(arrow));
      from.element.boundElements.push({ id: arrow.id, type: 'arrow' });
      to.element.boundElements.push({ id: arrow.id, type: 'arrow' });
    });

    var maxX = 0;
    var maxY = 0;
    Object.keys(positions).forEach(function (id) {
      maxX = Math.max(maxX, positions[id].x + positions[id].width);
      maxY = Math.max(maxY, positions[id].y + positions[id].height);
    });
    return {
      elements: elements,
      files: {},
      appState: { viewBackgroundColor: '#ffffff' },
      layout: { nodes: positions, width: maxX + 80, height: maxY + 80 },
      type: envelope && envelope.type,
    };
  }

  function buildLayout(envelope) {
    if (!envelope || !NATIVE_SET.has(envelope.type)) return null;
    var graphData = graph(envelope);
    var positions = layout(graphData);
    var width = 0;
    var height = 0;
    Object.keys(positions).forEach(function (id) {
      width = Math.max(width, positions[id].x + positions[id].width);
      height = Math.max(height, positions[id].y + positions[id].height);
    });
    return {
      nodes: positions,
      edges: graphData.edges,
      width: width + 80,
      height: height + 80,
    };
  }

  ns.nativeExcalidraw = {
    types: NATIVE_TYPES.slice(),
    isNativeType: function (type) { return NATIVE_SET.has(type); },
    buildLayout: buildLayout,
    buildScene: buildScene,
    _graph: graph,
    _layout: layout,
  };
}(typeof window !== 'undefined' ? window : globalThis));
