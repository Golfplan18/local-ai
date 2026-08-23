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
    var match;

    function node(id, label, kind, metadata) {
      var key = text(id, 'node-' + nodes.length);
      if (!seen.has(key)) {
        seen.add(key);
        nodes.push(Object.assign({
          id: key,
          label: text(label, key),
          kind: kind || 'node',
        }, metadata || {}));
      } else {
        var existing = nodes.find(function (entry) { return entry.id === key; });
        if (existing && (!existing.label || existing.label === key) && label) {
          existing.label = text(label, key);
        }
        if (existing && kind && (!existing.kind || existing.kind === 'node'
          || existing.kind === 'causal-node')) {
          existing.kind = kind;
        }
        if (existing && metadata) {
          Object.keys(metadata).forEach(function (name) {
            existing[name] = metadata[name];
          });
        }
      }
      return key;
    }

    function edge(from, to, label, kind, metadata) {
      var source = node(from, from);
      var target = node(to, to);
      if (!edges.some(function (entry) {
        return entry.from === source && entry.to === target
          && entry.label === text(label, '')
          && (entry.operator || '') === ((metadata && metadata.operator) || '');
      })) {
        edges.push(Object.assign({
          from: source,
          to: target,
          label: text(label, ''),
          kind: kind || 'relationship',
        }, metadata || {}));
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
      var dag = typeof spec.dsl === 'string' ? spec.dsl : '';
      var dagRenderer = ns._renderers && ns._renderers.causalDag;
      var dagParser = dagRenderer && dagRenderer._parseDagitty;
      if (typeof dagParser !== 'function') {
        throw new Error('The canonical DAGitty parser is unavailable');
      }
      var parsedDag = dagParser(dag);
      parsedDag.nodes.forEach(function (entry, id) {
        var roles = entry && entry.kinds ? Array.from(entry.kinds) : [];
        node(id, id, roles[0] || 'causal-node', { dagRoles: roles });
      });
      parsedDag.edges.forEach(function (entry) {
        edge(
          entry.from,
          entry.to,
          entry.op === '--' ? '' : 'causes',
          'causal-edge',
          { operator: entry.op }
        );
      });
      function focalDagNode(id, role) {
        var existing = nodes.find(function (entry) { return entry.id === id; });
        var roles = existing && Array.isArray(existing.dagRoles) ? existing.dagRoles : [];
        if (existing) existing.kind = role;
        node(id, id, role, {
          dagRoles: Array.from(new Set(roles.concat(role))),
        });
      }
      if (spec.focal_exposure) {
        focalDagNode(spec.focal_exposure, 'exposure');
      }
      if (spec.focal_outcome) {
        focalDagNode(spec.focal_outcome, 'outcome');
      }
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
      function argumentLabel(entry) {
        var label = text(entry && entry.text, 'Argument');
        return Number.isInteger(entry && entry.weight)
          ? label + ' [weight ' + entry.weight + '/5]'
          : label;
      }
      function addArgument(parent, entry, path, kind, relation, reverse) {
        var weight = Number.isInteger(entry && entry.weight) ? entry.weight : null;
        var id = node(path, argumentLabel(entry), kind, { argumentWeight: weight });
        edge(reverse ? id : parent, reverse ? parent : id, relation, kind);
        (entry.children || []).forEach(function (child, childIndex) {
          addArgument(id, child, path + '-' + childIndex, kind, 'because', false);
        });
      }
      (spec.pros || []).forEach(function (entry, index) {
        addArgument(claim, entry, 'pro-' + index, 'pro', 'supports', false);
      });
      (spec.cons || []).forEach(function (entry, index) {
        addArgument(claim, entry, 'con-' + index, 'con', 'challenges', true);
      });
      if (spec.decision) edge(claim, node('decision', spec.decision, 'decision'), 'decision', 'decision');
    } else if (type === 'concept_map') {
      (spec.concepts || []).forEach(function (entry) {
        node(entry.id, entry.label, 'concept', {
          hierarchyLevel: entry.hierarchy_level,
        });
      });
      var phrases = {};
      (spec.linking_phrases || []).forEach(function (entry) { phrases[entry.id] = entry.text; });
      (spec.propositions || []).forEach(function (entry) {
        edge(entry.from_concept, entry.to_concept, phrases[entry.via_phrase] || entry.via_phrase, 'proposition');
      });
    } else if (type === 'c4') {
      // The SVG renderer and the editable scene must consume the same
      // Structurizr AST. Regex extraction used to treat commented-out
      // declarations as real nodes and could silently turn malformed DSL
      // into the generic placeholder below.
      var c4Vendor = (ns._vendor || {}).structurizrMini;
      var c4Parser = c4Vendor && c4Vendor.parser;
      if (!c4Parser || typeof c4Parser.parse !== 'function') {
        throw new Error('The canonical Structurizr parser is unavailable');
      }
      var ast = c4Parser.parse(typeof spec.dsl === 'string' ? spec.dsl : '');
      var declared = new Set();
      (ast.model && ast.model.people || []).forEach(function (person) {
        declared.add(person.id);
        node(person.id, person.name, 'person');
      });
      (ast.model && ast.model.softwareSystems || []).forEach(function (system) {
        declared.add(system.id);
        node(system.id, system.name, 'softwareSystem', {
          external: system.external === true,
        });
        (system.containers || []).forEach(function (container) {
          declared.add(container.id);
          node(container.id, container.name, 'container', {
            technology: container.technology || '',
          });
        });
      });
      (ast.model && ast.model.relationships || []).forEach(function (rel) {
        if (!declared.has(rel.fromId) || !declared.has(rel.toId)) return;
        edge(rel.fromId, rel.toId, rel.description, 'uses');
      });
    }

    // A malformed C4 source must fail at the canonical parser boundary. Do
    // not replace it with a misleading placeholder visual. Other native
    // types retain the established empty-graph placeholder behavior.
    if (!nodes.length && type !== 'c4') {
      node('visual', envelope && envelope.title || type || 'visual', 'visual');
    }
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
      var column = Number.isInteger(entry.hierarchyLevel) && entry.hierarchyLevel >= 0
        ? entry.hierarchyLevel : depth(entry.id, {});
      (columns[column] = columns[column] || []).push(entry);
    });

    var positions = {};
    graphData.nodes.forEach(function (entry) {
      var column = Number.isInteger(entry.hierarchyLevel) && entry.hierarchyLevel >= 0
        ? entry.hierarchyLevel : depth(entry.id, {});
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

  function generationFingerprint(element) {
    var roundness = element && element.roundness;
    var boundElements = Array.isArray(element && element.boundElements)
      ? element.boundElements.map(function (binding) {
        return {
          id: String(binding && binding.id || ''),
          type: String(binding && binding.type || ''),
        };
      }).sort(function (left, right) {
        return (left.type + '\u0000' + left.id).localeCompare(right.type + '\u0000' + right.id);
      })
      : [];
    function pointBinding(binding) {
      if (!binding || typeof binding !== 'object') return null;
      return {
        elementId: binding.elementId || null,
        focus: Number(binding.focus) || 0,
        gap: Number(binding.gap) || 0,
        fixedPoint: Array.isArray(binding.fixedPoint)
          ? binding.fixedPoint.slice() : (binding.fixedPoint || null),
      };
    }
    return JSON.stringify({
      x: Number(element.x) || 0,
      y: Number(element.y) || 0,
      width: Number(element.width) || 0,
      height: Number(element.height) || 0,
      scale: Array.isArray(element.scale) ? element.scale.slice() : null,
      flipHorizontal: element.flipHorizontal === true,
      flipVertical: element.flipVertical === true,
      angle: Number(element.angle) || 0,
      locked: element.locked === true,
      text: String(element.text || ''),
      points: Array.isArray(element.points) ? element.points : null,
      strokeColor: element.strokeColor || '',
      backgroundColor: element.backgroundColor || '',
      fillStyle: element.fillStyle || '',
      opacity: Number(element.opacity) || 0,
      strokeWidth: Number(element.strokeWidth) || 0,
      strokeStyle: element.strokeStyle || '',
      roughness: Number(element.roughness) || 0,
      roundness: roundness && typeof roundness === 'object'
        ? { type: roundness.type == null ? null : roundness.type,
          value: roundness.value == null ? null : roundness.value }
        : (roundness || null),
      originalText: String(element.originalText || ''),
      fontSize: Number(element.fontSize) || 0,
      fontFamily: Number(element.fontFamily) || 0,
      textAlign: element.textAlign || '',
      verticalAlign: element.verticalAlign || '',
      lineHeight: Number(element.lineHeight) || 0,
      autoResize: element.autoResize === true,
      containerId: element.containerId || null,
      boundElements: boundElements.length ? boundElements : null,
      startBinding: pointBinding(element && element.startBinding),
      endBinding: pointBinding(element && element.endBinding),
      groupIds: Array.isArray(element && element.groupIds)
        ? element.groupIds.map(String) : [],
      frameId: element && element.frameId || null,
      index: element && element.index == null ? null : String(element.index),
      link: element.link || null,
      startArrowhead: element.startArrowhead || null,
      endArrowhead: element.endArrowhead || null,
    });
  }

  function tagFingerprint(element) {
    element.customData.originalGenerationFingerprint = generationFingerprint(element);
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

    function owned(kind, semanticElementId, metadata) {
      return Object.assign({
        oraAssistantVisual: true,
        oraAssistantVisualKind: 'native',
        assistantVisualId: assistantVisualId,
        generationRevision: revision,
        semanticElementId: semanticElementId,
        nativeKind: kind,
      }, metadata || {});
    }

    function semanticMetadata(entry) {
      var metadata = {};
      if (Array.isArray(entry.dagRoles)) metadata.dagRoles = entry.dagRoles.slice();
      if (entry.operator) metadata.dagOperator = entry.operator;
      if (Number.isInteger(entry.argumentWeight)) {
        metadata.argumentWeight = entry.argumentWeight;
      }
      if (Number.isInteger(entry.hierarchyLevel)) {
        metadata.hierarchyLevel = entry.hierarchyLevel;
      }
      return metadata;
    }

    graphData.nodes.forEach(function (entry) {
      var bounds = positions[entry.id];
      var semantic = text(envelope.type, 'visual') + ':node:' + entry.id;
      var nodeElement = baseElement(
        'ora-' + hash(assistantVisualId + ':' + semantic + ':shape'),
        entry.kind === 'decision' ? 'diamond' : 'rectangle',
        bounds,
        owned(entry.kind, semantic, semanticMetadata(entry))
      );
      nodeElement.groupIds = [groupId + '-' + safe(entry.id)];
      elements.push(nodeElement);
      byId[entry.id] = { element: nodeElement, bounds: bounds, semantic: semantic };

      var label = baseElement(
        'ora-' + hash(assistantVisualId + ':' + semantic + ':label'),
        'text',
        { x: bounds.x + 10, y: bounds.y + 16, width: bounds.width - 20, height: 24 },
        owned(entry.kind + '-label', semantic + ':label', semanticMetadata(entry))
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
      elements.push(label);
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
      var sourceScale = Math.min(
        (from.bounds.width / 2) / Math.max(Math.abs(dx), 1),
        (from.bounds.height / 2) / Math.max(Math.abs(dy), 1)
      );
      var targetScale = Math.min(
        (to.bounds.width / 2) / Math.max(Math.abs(dx), 1),
        (to.bounds.height / 2) / Math.max(Math.abs(dy), 1)
      );
      if (!isFinite(sourceScale) || sourceScale <= 0) sourceScale = 0.25;
      if (!isFinite(targetScale) || targetScale <= 0) targetScale = 0.25;
      var start = {
        x: fromCenter.x + dx * sourceScale,
        y: fromCenter.y + dy * sourceScale,
      };
      var end = {
        x: toCenter.x - dx * targetScale,
        y: toCenter.y - dy * targetScale,
      };
      var operator = entry.operator || '->';
      var semantic = text(envelope.type, 'visual') + ':edge:' + entry.from
        + operator + entry.to + ':' + entry.label;
      var origin = { x: Math.min(start.x, end.x), y: Math.min(start.y, end.y) };
      var relativeStart = [start.x - origin.x, start.y - origin.y];
      var relativeEnd = [end.x - origin.x, end.y - origin.y];
      var arrow = baseElement(
        'ora-' + hash(assistantVisualId + ':' + semantic),
        'arrow',
        {
          x: origin.x,
          y: origin.y,
          width: Math.max(Math.abs(end.x - start.x), 1),
          height: Math.max(Math.abs(end.y - start.y), 1),
        },
        owned(entry.kind, semantic, semanticMetadata(entry))
      );
      arrow.points = [relativeStart, relativeEnd];
      arrow.lastCommittedPoint = relativeEnd;
      arrow.startArrowhead = operator === '<->' ? 'arrow' : null;
      arrow.endArrowhead = operator === '--' ? null : 'arrow';
      arrow.startBinding = { elementId: from.element.id, focus: 0, gap: 4, fixedPoint: null };
      arrow.endBinding = { elementId: to.element.id, focus: 0, gap: 4, fixedPoint: null };
      arrow.boundElements = null;
      elements.push(arrow);
      from.element.boundElements.push({ id: arrow.id, type: 'arrow' });
      to.element.boundElements.push({ id: arrow.id, type: 'arrow' });

      // Relationship labels are semantic content, not arrow metadata only:
      // emit an editable text object so the relationship survives the native
      // Excalidraw projection visibly.
      if (entry.label) {
        var labelWidth = Math.max(80, Math.min(320, entry.label.length * 7 + 20));
        var labelX = (start.x + end.x) / 2 - labelWidth / 2;
        var labelY = (start.y + end.y) / 2 - 22;
        var edgeLabel = baseElement(
          'ora-' + hash(assistantVisualId + ':' + semantic + ':label'),
          'text',
          { x: labelX, y: labelY, width: labelWidth, height: 24 },
          owned(entry.kind + '-label', semantic + ':label', Object.assign(
            { relationshipLabel: entry.label }, semanticMetadata(entry)
          ))
        );
        edgeLabel.text = entry.label;
        edgeLabel.originalText = entry.label;
        edgeLabel.fontSize = 14;
        edgeLabel.fontFamily = 1;
        edgeLabel.textAlign = 'center';
        edgeLabel.verticalAlign = 'middle';
        edgeLabel.autoResize = false;
        edgeLabel.lineHeight = 1.25;
        edgeLabel.groupIds = [groupId + '-' + safe(semantic + ':label')];
        elements.push(edgeLabel);
      }
    });

    elements.forEach(tagFingerprint);

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
    generationFingerprint: generationFingerprint,
    _graph: graph,
    _layout: layout,
  };
}(typeof window !== 'undefined' ? window : globalThis));
