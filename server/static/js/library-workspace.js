/* Knowledge Library — one shared List/Visual workspace over Ora's upper panes.
 *
 * This is deliberately an ordinary controller. The server remains the source
 * of query-qualified inventory, total, facet, completeness, and pagination
 * truth. Local metadata filters are applied only after every returned page is
 * loaded; the server query remains exact/fuzzy keyword search, never semantic.
 */
(function () {
  'use strict';

  const PAGE_LIMIT = 100;
  const RELATED_LIMIT = 500;
  const SOURCES = ['dialogues', 'engrams', 'files'];
  const sourceLabels = { dialogues: 'Dialogues', engrams: 'Engrams', files: 'Files' };
  const relationshipDirections = {
    parent: 'incoming',
    'direct-child': 'outgoing',
    sibling: 'peer',
    contributor: 'outgoing',
    'direct-related': 'incoming',
    'shared-project': 'peer',
  };

  const mount = document.getElementById('libraryWorkspace');
  if (!mount) return;

  const searchInput = document.getElementById('librarySearchInput');
  const results = document.getElementById('libraryWorkspaceResults');
  const status = document.getElementById('libraryWorkspaceStatus');
  const notice = document.getElementById('libraryWorkspaceNotice');
  const logoO = document.getElementById('logo-o');
  const logoType = logoO && logoO.querySelector('.library-o-type');
  const logoState = logoO && logoO.querySelector('.library-o-state');
  const sourceCount = mount.querySelector('[data-library-source-count]');
  const actionHost = mount.querySelector('[data-library-actions]');
  const actionButton = mount.querySelector('[data-library-popover="actions"]');
  const groupButton = mount.querySelector('[data-library-popover="group"]');
  const filterButton = mount.querySelector('[data-library-popover="filters"]');
  const typeFilter = mount.querySelector('[data-library-filter="type"]');
  const projectScope = mount.querySelector('[data-library-project]');

  const state = {
    open: false,
    view: 'list',
    sources: new Set(SOURCES),
    projectId: 'commons',
    query: '',
    filters: { type: '' },
    group: 'none',
    sort: 'recent',
    selectedIds: new Set(),
    pinnedId: null,
    rows: [],
    rowsById: new Map(),
    total: 0,
    sourceCounts: {},
    facets: {},
    universe: null,
    pagination: { offset: 0, limit: PAGE_LIMIT, returned: 0, has_more: false, next_offset: null },
    loading: false,
    loadingAll: false,
    retryAppend: false,
    error: '',
    actionNotice: '',
    requestGeneration: 0,
    previewGeneration: 0,
    relationshipGeneration: 0,
    renderGeneration: 0,
    textPreview: { id: null, loading: false, error: '', text: null },
    related: {
      anchorId: null,
      locator: '',
      loading: false,
      resolved: false,
      error: '',
      reason: 'Pin a readable Dialogue or Engram to request explicit relationship endpoints.',
      rows: [],
      total: 0,
      returned: 0,
    },
  };

  let requestController = null;
  let previewController = null;
  let relationshipController = null;
  let returnFocus = null;
  let resizeObserver = null;
  let previewTextLayer = null;
  let previewVisualLayer = null;
  let savedLogo = null;
  const ownedUpperState = new Map();

  function setStatus(message) {
    status.textContent = message;
  }

  function setNotice(message, tone, command) {
    notice.replaceChildren();
    if (!message) {
      notice.hidden = true;
      notice.removeAttribute('data-tone');
      return;
    }
    notice.hidden = false;
    notice.dataset.tone = tone || 'info';
    const text = document.createElement('span');
    text.textContent = message;
    notice.appendChild(text);
    if (command) {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.libraryCommand = command;
      button.textContent = command === 'load-all' ? 'Load all to qualify results' : 'Try again';
      notice.appendChild(button);
    }
  }

  function rememberAndSetInert(element) {
    if (!element || ownedUpperState.has(element)) return;
    ownedUpperState.set(element, {
      inert: element.hasAttribute('inert'),
      ariaHidden: element.getAttribute('aria-hidden'),
    });
    element.setAttribute('inert', '');
    element.setAttribute('aria-hidden', 'true');
  }

  function ownUpperWorkspace() {
    rememberAndSetInert(document.querySelector('.input-pane'));
    rememberAndSetInert(document.getElementById('chatZone'));
    rememberAndSetInert(document.querySelector('#bridgeStrip .bridge-toolbar'));
    rememberAndSetInert(document.querySelector('#bridgeStripRight .bridge-toolbar'));
    document.body.classList.add('library-workspace-open');
  }

  function restoreUpperWorkspace() {
    ownedUpperState.forEach((previous, element) => {
      if (!element.isConnected) return;
      if (!previous.inert) element.removeAttribute('inert');
      if (previous.ariaHidden === null) element.removeAttribute('aria-hidden');
      else element.setAttribute('aria-hidden', previous.ariaHidden);
    });
    ownedUpperState.clear();
    document.body.classList.remove('library-workspace-open');
  }

  function measureWorkspace() {
    if (!state.open) return;
    const input = document.querySelector('.input-pane');
    const aside = document.getElementById('chatZone');
    const leftBridge = document.getElementById('bridgeStrip');
    const rightBridge = document.getElementById('bridgeStripRight');
    if (!input || !aside || !leftBridge || !rightBridge) return;

    const inputRect = input.getBoundingClientRect();
    const asideRect = aside.getBoundingClientRect();
    const leftBridgeRect = leftBridge.getBoundingClientRect();
    const rightBridgeRect = rightBridge.getBoundingClientRect();
    const left = Math.min(inputRect.left, leftBridgeRect.left);
    const right = Math.max(asideRect.right, rightBridgeRect.right);
    const top = Math.min(inputRect.top, asideRect.top);
    const bottom = Math.max(leftBridgeRect.bottom, rightBridgeRect.bottom);

    mount.style.left = `${left}px`;
    mount.style.top = `${top}px`;
    mount.style.width = `${Math.max(1, right - left)}px`;
    mount.style.height = `${Math.max(1, bottom - top)}px`;
    mount.style.setProperty('--library-bridge-height', `${Math.max(leftBridgeRect.height, rightBridgeRect.height)}px`);
    mount.style.setProperty('--library-left-bank-left', `${Math.max(0, leftBridgeRect.left - left)}px`);
    mount.style.setProperty('--library-left-bank-top', `${Math.max(0, leftBridgeRect.top - top)}px`);
    mount.style.setProperty('--library-left-bank-width', `${leftBridgeRect.width}px`);
    mount.style.setProperty('--library-left-bank-height', `${leftBridgeRect.height}px`);
    mount.style.setProperty('--library-right-bank-left', `${Math.max(0, rightBridgeRect.left - left)}px`);
    mount.style.setProperty('--library-right-bank-top', `${Math.max(0, rightBridgeRect.top - top)}px`);
    mount.style.setProperty('--library-right-bank-width', `${rightBridgeRect.width}px`);
    mount.style.setProperty('--library-right-bank-height', `${rightBridgeRect.height}px`);

    // A bridge can sit at the top of one upper pane while its counterpart is
    // below the other. Keep the one search field in the free horizontal span
    // instead of covering controls that correctly follow that top bridge.
    mount.style.setProperty('--library-search-left', '0px');
    mount.style.setProperty('--library-search-right', '0px');
    const searchRect = searchInput.getBoundingClientRect();
    const overlapsSearch = (rect) => (
      rect.top < searchRect.bottom && rect.bottom > searchRect.top
      && rect.left < searchRect.right && rect.right > searchRect.left
    );
    if (overlapsSearch(leftBridgeRect)) {
      mount.style.setProperty('--library-search-left', `${Math.max(0, leftBridgeRect.right - left)}px`);
    }
    if (overlapsSearch(rightBridgeRect)) {
      mount.style.setProperty('--library-search-right', `${Math.max(0, right - rightBridgeRect.left)}px`);
    }
    mount.dataset.layout = right - left < 720 ? 'narrow' : 'wide';
    layoutVisual(state.renderGeneration);
  }

  function rowType(row) {
    return String(row.metadata.item_type || row.metadata.content_type || sourceLabels[row.source] || row.source);
  }

  function rowProject(row) {
    const projects = row.metadata.project_ids;
    return Array.isArray(projects) && projects.length ? projects[0] : 'Unassigned';
  }

  function pinnedRow() {
    return state.pinnedId ? state.rowsById.get(state.pinnedId) || null : null;
  }

  function allReturnedPagesLoaded() {
    return !state.pagination.has_more;
  }

  function localQualificationRequested() {
    return Boolean(state.filters.type || state.group !== 'none' || state.sort === 'title');
  }

  function qualificationAvailable() {
    return allReturnedPagesLoaded();
  }

  function visibleRows() {
    let rows = state.rows.slice();
    if (localQualificationRequested() && !qualificationAvailable()) return rows;
    if (state.filters.type) rows = rows.filter((row) => rowType(row) === state.filters.type);
    if (state.sort === 'title') {
      rows.sort((a, b) => a.title.localeCompare(b.title) || a.id.localeCompare(b.id));
    }
    if (state.group !== 'none') {
      rows.sort((a, b) => groupValue(a).localeCompare(groupValue(b)));
    }
    return rows;
  }

  function sourceBadge(row) {
    const badge = document.createElement('span');
    badge.className = `library-source-badge is-${row.source}`;
    badge.textContent = sourceLabels[row.source] || row.source;
    return badge;
  }

  function metadataLine(row) {
    const parts = [rowType(row), rowProject(row)];
    if (row.metadata.modified_at) parts.push(row.metadata.modified_at);
    if (row.unavailable_fields && row.unavailable_fields.length) {
      parts.push(`${row.unavailable_fields.length} metadata field${row.unavailable_fields.length === 1 ? '' : 's'} unavailable`);
    }
    return parts.filter(Boolean).join(' · ');
  }

  function selectRow(row, selected) {
    if (selected) state.selectedIds.add(row.id);
    else state.selectedIds.delete(row.id);
    renderActions();
    render();
  }

  function relatedLocator(row) {
    if (!row || !row.preview || !row.preview.available) return '';
    if (row.source === 'dialogues') {
      return String((row.preview.locator && row.preview.locator.dialogue_id) || '');
    }
    if (row.source === 'engrams' && String(row.id || '').startsWith('engrams:')) {
      // The Related endpoint and Library inventory use the same URL-safe
      // encoded source identity with different, route-owned type prefixes.
      return `engram:${String(row.id).slice('engrams:'.length)}`;
    }
    return '';
  }

  const textPreviewEligible = (row) => Boolean(row
    && (row.source === 'engrams' || row.source === 'files')
    && row.preview && row.preview.kind === 'text'
    && row.preview.available === true);

  function invalidateTextPreviewRequest() {
    ++state.previewGeneration;
    if (previewController) previewController.abort();
    previewController = null;
    state.textPreview.loading = false;
  }

  function resetTextPreview(row) {
    invalidateTextPreviewRequest();
    state.textPreview = { id: row ? row.id : null, loading: false, error: '', text: null };
  }

  async function fetchTextPreview(row) {
    resetTextPreview(row);
    if (!textPreviewEligible(row) || !state.open) return;
    const generation = state.previewGeneration;
    previewController = new AbortController();
    const controller = previewController;
    state.textPreview.loading = true;
    try {
      const params = new URLSearchParams({ id: row.id });
      const response = await fetch(`/api/library/preview?${params.toString()}`, {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || `Preview request failed (HTTP ${response.status})`);
      if (generation !== state.previewGeneration || state.pinnedId !== row.id) return;
      if (payload.id !== row.id || typeof payload.text !== 'string') {
        throw new Error('The preview response did not match the pinned Library item.');
      }
      state.textPreview.text = payload.text;
      state.textPreview.error = '';
    } catch (error) {
      if (error && error.name === 'AbortError') return;
      if (generation !== state.previewGeneration) return;
      state.textPreview.error = error && error.message ? error.message : String(error);
      state.textPreview.text = null;
    } finally {
      if (generation === state.previewGeneration) {
        state.textPreview.loading = false;
        previewController = null;
        renderPreview();
      }
    }
  }

  function resetRelated(row, reason) {
    ++state.relationshipGeneration;
    if (relationshipController) relationshipController.abort();
    relationshipController = null;
    const locator = relatedLocator(row);
    state.related = {
      anchorId: row ? row.id : null,
      locator,
      loading: false,
      resolved: false,
      error: '',
      reason: reason || (locator
        ? ''
        : row && row.source === 'files'
          ? 'Files have no registered Related route, so this item remains connector-free.'
          : row
            ? 'This item has no privacy-safe Related locator, so it remains connector-free.'
            : 'Pin a readable Dialogue or Engram to request explicit relationship endpoints.'),
      rows: [],
      total: 0,
      returned: 0,
    };
  }

  function relatedUrl(locator) {
    const params = new URLSearchParams({
      conversations: state.sources.has('dialogues') ? '1' : '0',
      engrams: state.sources.has('engrams') ? '1' : '0',
      show_archived: '0',
      limit: String(RELATED_LIMIT),
    });
    return `/api/conversation/${encodeURIComponent(locator)}/related?${params.toString()}`;
  }

  function normalizeRelatedRows(payload, anchorLocator) {
    const seen = new Set();
    return (Array.isArray(payload.rows) ? payload.rows : []).reduce((rows, raw) => {
      if (!raw || typeof raw !== 'object') return rows;
      const endpointId = String(raw.conversation_id || '').trim();
      if (!endpointId || endpointId === anchorLocator || seen.has(endpointId)) return rows;
      const source = raw.source_kind === 'engram' ? 'engrams' : 'dialogues';
      if (!state.sources.has(source)) return rows;
      const relationship = raw.relationship && typeof raw.relationship === 'object'
        ? raw.relationship
        : {};
      const kinds = relationship.available === true && Array.isArray(relationship.kinds)
        ? relationship.kinds.filter((kind) => Object.prototype.hasOwnProperty.call(relationshipDirections, kind))
        : [];
      seen.add(endpointId);
      rows.push({
        id: endpointId,
        source,
        title: String(raw.title || raw.display_name || 'Related item'),
        kinds,
        drawable: kinds.length > 0,
      });
      return rows;
    }, []);
  }

  async function fetchRelated(row) {
    const locator = relatedLocator(row);
    if (!row || !locator || !state.open) return;
    const generation = ++state.relationshipGeneration;
    if (relationshipController) relationshipController.abort();
    relationshipController = new AbortController();
    const controller = relationshipController;
    state.related.anchorId = row.id;
    state.related.locator = locator;
    state.related.loading = true;
    state.related.error = '';
    state.related.reason = '';
    renderPreview();
    render();
    try {
      const response = await fetch(relatedUrl(locator), {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || `Related request failed (HTTP ${response.status})`);
      if (
        generation !== state.relationshipGeneration
        || controller !== relationshipController
        || state.pinnedId !== row.id
      ) return;
      state.related.rows = normalizeRelatedRows(payload, locator);
      state.related.total = Number.isFinite(Number(payload.total)) ? Number(payload.total) : state.related.rows.length;
      state.related.returned = Array.isArray(payload.rows) ? payload.rows.length : 0;
      state.related.resolved = true;
      const reasons = [];
      if (state.related.returned < state.related.total) {
        reasons.push(`Only ${state.related.returned} of ${state.related.total} Related rows were returned; omitted endpoints are not drawn.`);
      }
      if (!state.related.rows.some((endpoint) => endpoint.drawable)) {
        reasons.push(state.related.rows.length
          ? 'Returned suggestions did not carry explicit relationship authority, so no connector is drawn.'
          : 'Related returned no non-self endpoint with explicit relationship authority.');
      }
      state.related.reason = reasons.join(' ');
    } catch (error) {
      if (error && error.name === 'AbortError') return;
      if (generation !== state.relationshipGeneration) return;
      state.related.error = error && error.message ? error.message : String(error);
      state.related.resolved = false;
      state.related.rows = [];
      state.related.total = 0;
      state.related.returned = 0;
    } finally {
      if (generation === state.relationshipGeneration) {
        state.related.loading = false;
        renderPreview();
        render();
      }
    }
  }

  function pinRow(row) {
    state.pinnedId = row ? row.id : null;
    resetRelated(row);
    fetchTextPreview(row);
    updateLogo();
    renderPreview();
    renderActions();
    render();
    if (state.related.locator) fetchRelated(row);
  }

  function buildListRow(row) {
    const item = document.createElement('article');
    item.className = 'library-list-row';
    item.dataset.libraryRowId = row.id;
    item.classList.toggle('is-pinned', state.pinnedId === row.id);

    const check = document.createElement('input');
    check.type = 'checkbox';
    check.checked = state.selectedIds.has(row.id);
    check.setAttribute('aria-label', `Select ${row.title}`);
    check.addEventListener('change', () => selectRow(row, check.checked));

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'library-list-row__pin';
    button.setAttribute('aria-pressed', state.pinnedId === row.id ? 'true' : 'false');
    button.setAttribute('aria-label', `Preview ${row.title} in Findings and Exhibits`);
    button.addEventListener('click', () => pinRow(row));
    const title = document.createElement('strong');
    title.textContent = row.title;
    const meta = document.createElement('span');
    meta.textContent = metadataLine(row);
    button.append(title, meta);

    item.append(check, sourceBadge(row), button);
    return item;
  }

  function groupValue(row) {
    if (state.group === 'source') return sourceLabels[row.source] || row.source;
    if (state.group === 'type') return rowType(row);
    if (state.group === 'project') return rowProject(row);
    return '';
  }

  function renderList(rows) {
    const fragment = document.createDocumentFragment();
    const effectiveGroup = qualificationAvailable() ? state.group : 'none';
    if (effectiveGroup === 'none') {
      rows.forEach((row) => fragment.appendChild(buildListRow(row)));
    } else {
      const groups = new Map();
      rows.forEach((row) => {
        const value = groupValue(row) || 'Unavailable';
        if (!groups.has(value)) groups.set(value, []);
        groups.get(value).push(row);
      });
      Array.from(groups.keys()).sort().forEach((name) => {
        const section = document.createElement('section');
        section.className = 'library-result-group';
        const heading = document.createElement('h2');
        heading.textContent = `${name} (${groups.get(name).length})`;
        section.appendChild(heading);
        groups.get(name).forEach((row) => section.appendChild(buildListRow(row)));
        fragment.appendChild(section);
      });
    }
    results.appendChild(fragment);
  }

  function buildVisualNode(row) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `library-visual-node is-${row.source}`;
    button.dataset.libraryNodeId = row.id;
    button.setAttribute('aria-pressed', state.pinnedId === row.id ? 'true' : 'false');
    const groupedAs = qualificationAvailable() && state.group !== 'none'
      ? ` Group: ${groupValue(row) || 'Unavailable'}.`
      : '';
    button.setAttribute('aria-label', `${sourceLabels[row.source]}: ${row.title}. ${metadataLine(row)}.${groupedAs}`);
    button.append(sourceBadge(row));
    const title = document.createElement('span');
    title.textContent = row.title;
    button.appendChild(title);
    if (qualificationAvailable() && state.group !== 'none') {
      const group = document.createElement('small');
      group.className = 'library-visual-node__group';
      group.textContent = groupValue(row) || 'Unavailable';
      button.appendChild(group);
    }
    button.addEventListener('click', () => pinRow(row));
    return button;
  }

  function focusRelatedEndpoint(endpointId) {
    const details = previewTextLayer && previewTextLayer.querySelector('.library-relationships');
    if (!details) return;
    details.open = true;
    const target = Array.from(details.querySelectorAll('[data-related-endpoint-id]'))
      .find((item) => item.dataset.relatedEndpointId === endpointId);
    if (target) {
      target.tabIndex = -1;
      target.focus();
    } else {
      const summary = details.querySelector('summary');
      if (summary) summary.focus();
    }
  }

  function buildRelatedNode(endpoint) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `library-visual-node library-visual-node--related is-${endpoint.source}`;
    button.dataset.relatedEndpointId = endpoint.id;
    const relationships = endpoint.kinds.map((kind) => `${relationshipDirections[kind]} ${kind}`).join(', ');
    button.setAttribute('aria-label', `${sourceLabels[endpoint.source]} related endpoint: ${endpoint.title}. ${relationships}. Activate for relationship details.`);
    button.append(sourceBadge(endpoint));
    const title = document.createElement('span');
    title.textContent = endpoint.title;
    button.appendChild(title);
    button.addEventListener('click', () => focusRelatedEndpoint(endpoint.id));
    return button;
  }

  function drawableRelatedRows() {
    const row = pinnedRow();
    if (!row || state.related.anchorId !== row.id) return [];
    return state.related.rows.filter((endpoint) => endpoint.drawable);
  }

  function renderVisual(rows) {
    const visual = document.createElement('div');
    visual.className = 'library-visual-map';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.classList.add('library-visual-connectors');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    visual.appendChild(svg);
    rows.filter((row) => row.id !== state.pinnedId)
      .forEach((row) => visual.appendChild(buildVisualNode(row)));
    const endpoints = drawableRelatedRows();
    endpoints.forEach((endpoint) => visual.appendChild(buildRelatedNode(endpoint)));
    if (state.group !== 'none') {
      const groupState = document.createElement('p');
      groupState.className = 'library-visual-group-state';
      const label = { source: 'source', type: 'type', project: 'project' }[state.group] || state.group;
      groupState.textContent = qualificationAvailable()
        ? `Grouped by ${label}; inventory nodes are ordered by their visible group labels around the measured arc.`
        : `Grouping by ${label} is unavailable until every query-qualified inventory page is loaded.`;
      visual.appendChild(groupState);
    }
    const capacityState = document.createElement('p');
    capacityState.className = 'library-visual-capacity-state';
    capacityState.textContent = 'Measuring Visual capacity from the live workspace.';
    visual.appendChild(capacityState);
    const edgeState = document.createElement('p');
    edgeState.className = 'library-visual-edge-state';
    if (state.related.loading) {
      edgeState.textContent = 'Loading explicit relationship endpoints for the selected O anchor…';
    } else if (state.related.error) {
      edgeState.textContent = `Relationship endpoints unavailable: ${state.related.error}. No connectors are drawn.`;
    } else if (!endpoints.length) {
      edgeState.textContent = state.related.reason
        || 'No drawable connectors: inventory summaries do not identify authoritative endpoints.';
    } else {
      edgeState.textContent = `Laying out ${endpoints.length} explicit Related endpoint${endpoints.length === 1 ? '' : 's'} from the O anchor.`;
    }
    visual.appendChild(edgeState);
    results.appendChild(visual);
  }

  function layoutVisual(generation) {
    if (generation !== state.renderGeneration || state.view !== 'visual') return;
    const visual = results.querySelector('.library-visual-map');
    if (!visual) return;
    const inventoryNodes = Array.from(visual.querySelectorAll('.library-visual-node:not(.library-visual-node--related)'));
    const relatedNodes = Array.from(visual.querySelectorAll('.library-visual-node--related'));
    const workspaceRect = mount.getBoundingClientRect();
    const visualRect = visual.getBoundingClientRect();
    const oRect = logoO ? logoO.getBoundingClientRect() : null;
    if (!workspaceRect.width || !visualRect.width || !oRect) return;

    const anchorX = oRect.left + oRect.width / 2 - visualRect.left;
    const anchorY = oRect.top + oRect.height / 2 - visualRect.top;
    const availableRadius = Math.max(54, Math.min(
      visualRect.width * 0.38,
      Math.max(54, anchorY - 38),
      visualRect.height * 0.68
    ));
    const occupied = [];
    const padding = 6;
    const collisionGap = 6;
    const candidateAngles = [270];
    for (let delta = 4; delta <= 135; delta += 4) {
      candidateAngles.push(270 - delta, 270 + delta);
    }
    candidateAngles.push(135, 405);

    function overlaps(candidate, placed) {
      return !(
        candidate.right + collisionGap <= placed.left
        || placed.right + collisionGap <= candidate.left
        || candidate.bottom + collisionGap <= placed.top
        || placed.bottom + collisionGap <= candidate.top
      );
    }

    function placeArc(nodes, radius) {
      const visible = [];
      nodes.forEach((node) => {
        node.hidden = false;
        const nodeRect = node.getBoundingClientRect();
        const placement = candidateAngles.map((degrees) => {
          // 135°..405° is a 270° arc. It leaves the 90° downward cone clear.
          const angle = degrees * Math.PI / 180;
          const left = anchorX + Math.cos(angle) * radius - nodeRect.width / 2;
          const top = anchorY + Math.sin(angle) * radius - nodeRect.height / 2;
          return {
            left,
            top,
            right: left + nodeRect.width,
            bottom: top + nodeRect.height,
          };
        }).find((candidate) => (
          candidate.left >= padding
          && candidate.top >= padding
          && candidate.right <= visualRect.width - padding
          && candidate.bottom <= visualRect.height - padding
          && !occupied.some((placed) => overlaps(candidate, placed))
        ));
        if (!placement) {
          node.hidden = true;
          return;
        }
        node.style.left = `${placement.left}px`;
        node.style.top = `${placement.top}px`;
        occupied.push(placement);
        visible.push(node);
      });
      return visible;
    }

    // Reserve the inner O-centred arc for explicitly authoritative Related
    // endpoints first; inventory overflow always retains its complete List.
    const visibleRelatedNodes = placeArc(relatedNodes, Math.max(48, availableRadius * 0.56));
    const visibleInventoryNodes = placeArc(inventoryNodes, availableRadius);

    const capacityState = visual.querySelector('.library-visual-capacity-state');
    const hiddenInventory = inventoryNodes.length - visibleInventoryNodes.length;
    const hiddenRelated = relatedNodes.length - visibleRelatedNodes.length;
    if (capacityState) {
      capacityState.textContent = hiddenInventory || hiddenRelated
        ? `Measured Visual capacity shows ${visibleInventoryNodes.length} of ${inventoryNodes.length} fully contained, non-overlapping inventory nodes and ${visibleRelatedNodes.length} of ${relatedNodes.length} relationship nodes. All current result rows remain available in List, and all relationship endpoints remain available in Findings.`
        : `All ${inventoryNodes.length} inventory node${inventoryNodes.length === 1 ? '' : 's'} and ${relatedNodes.length} relationship node${relatedNodes.length === 1 ? '' : 's'} fit fully inside the measured Visual without overlap.`;
    }

    const svg = visual.querySelector('.library-visual-connectors');
    svg.replaceChildren();
    let drawnConnectors = 0;
    drawableRelatedRows().forEach((endpoint) => {
      const to = visibleRelatedNodes.find((node) => node.dataset.relatedEndpointId === endpoint.id);
      if (!to) return;
      const toRect = to.getBoundingClientRect();
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', String(anchorX));
      line.setAttribute('y1', String(anchorY));
      line.setAttribute('x2', String(toRect.left + toRect.width / 2 - visualRect.left));
      line.setAttribute('y2', String(toRect.top + toRect.height / 2 - visualRect.top));
      line.dataset.relationshipType = endpoint.kinds.join(' ');
      svg.appendChild(line);
      drawnConnectors += 1;
    });
    const endpoints = drawableRelatedRows();
    const edgeState = visual.querySelector('.library-visual-edge-state');
    if (edgeState && endpoints.length) {
      const withheld = state.related.rows.length - endpoints.length;
      const capacityWithheld = endpoints.length - drawnConnectors;
      edgeState.textContent = `${drawnConnectors} of ${endpoints.length} explicit Related endpoint connector${endpoints.length === 1 ? '' : 's'} shown from the O${capacityWithheld ? `; ${capacityWithheld} remain in Findings because they exceed measured Visual capacity` : ''}${withheld ? `; ${withheld} returned suggestion${withheld === 1 ? '' : 's'} lacked edge authority and remain connector-free` : ''}.${state.related.reason ? ` ${state.related.reason}` : ''}`;
    }
  }

  function renderEmpty(message) {
    const empty = document.createElement('div');
    empty.className = 'library-empty-state';
    empty.textContent = message;
    results.appendChild(empty);
  }

  function render() {
    if (!state.open) return;
    const generation = ++state.renderGeneration;
    results.replaceChildren();
    sourceCount.textContent = String(state.sources.size);
    updateControlSummaries();
    mount.querySelectorAll('[data-library-view]').forEach((button) => {
      button.setAttribute('aria-pressed', button.dataset.libraryView === state.view ? 'true' : 'false');
    });

    if (!state.sources.size) {
      setNotice('', 'info');
      renderEmpty('No sources are included. Select Dialogues, Engrams, Files, or any mixed subset.');
      setStatus('Zero sources selected. Nothing is loaded; the server is not called because omitting source would mean all sources.');
      return;
    }
    if (state.loading && !state.rows.length) {
      setNotice('', 'info');
      renderEmpty('Loading the authoritative Library inventory…');
      setStatus('Loading Library inventory.');
      return;
    }
    if (state.error && !state.rows.length) {
      setNotice(state.error, 'error', 'retry');
      renderEmpty('Library inventory is unavailable.');
      setStatus(`Library error: ${state.error}`);
      return;
    }

    const rows = visibleRows();
    if (state.loading && state.rows.length) {
      setNotice('Refreshing the authoritative Library inventory. Current rows remain until the replacement response commits.', 'info');
    } else if (state.actionNotice) {
      setNotice(state.actionNotice, 'error');
    } else if (state.error) {
      setNotice(`The latest Library request could not load: ${state.error}`, 'error', 'retry');
    } else if (localQualificationRequested() && !qualificationAvailable()) {
      setNotice(
        `Type filtering, grouping, and title sorting are unavailable while ${state.rows.length} of ${state.total} query-qualified inventory items are loaded. The visible page is not being locally qualified or grouped.`,
        'incomplete',
        'load-all'
      );
    } else if (state.universe && !state.universe.complete) {
      const unavailable = (state.universe.unavailable_sources || [])
        .map((item) => `${sourceLabels[item.source] || item.source}: ${item.reason}`)
        .join(' ');
      setNotice(`Results are incomplete. ${unavailable}`.trim(), 'incomplete');
    } else {
      setNotice('', 'info');
    }

    if (!rows.length) {
      renderEmpty(state.query
        ? 'No eligible Dialogue or Engram body matches the current keyword query. Files do not support body keyword search.'
        : localQualificationRequested()
          ? 'No returned Library item matches the current metadata qualification.'
          : 'The selected source inventory is empty.');
    } else if (state.view === 'visual') {
      renderVisual(rows);
    } else {
      renderList(rows);
    }

    const completeness = state.universe && state.universe.complete ? 'complete' : 'incomplete';
    const qualification = localQualificationRequested() && qualificationAvailable()
      ? `; ${rows.length} match the local metadata filters`
      : '';
    const query = state.query ? `; keyword query ${JSON.stringify(state.query)}` : '';
    const paging = state.pagination.has_more ? '; more pages available' : '; all returned pages loaded';
    const loading = state.loading ? '; refresh in progress' : '';
    setStatus(`${state.rows.length} of ${state.total} items loaded from a ${completeness} source universe${query}${qualification}${paging}${loading}.`);

    if (state.pagination.has_more && !state.loadingAll) {
      const more = document.createElement('button');
      more.type = 'button';
      more.className = 'library-load-more';
      more.dataset.libraryCommand = 'load-more';
      more.textContent = `Load more (${Math.max(0, state.total - state.rows.length)} remaining)`;
      results.appendChild(more);
    }
    requestAnimationFrame(() => layoutVisual(generation));
  }

  function updateFacetOptions() {
    function update(select, counts) {
      const current = state.filters.type || select.value;
      Array.from(select.options).slice(1).forEach((option) => option.remove());
      Object.keys(counts || {}).sort().forEach((value) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = `${value} (${counts[value]})`;
        select.appendChild(option);
      });
      if (current && !Object.prototype.hasOwnProperty.call(counts || {}, current)) {
        const option = document.createElement('option');
        option.value = current;
        option.textContent = `${current} (0)`;
        option.dataset.zeroCount = 'true';
        select.appendChild(option);
      }
      select.value = current;
    }
    update(typeFilter, state.facets.item_type && state.facets.item_type.counts);
    state.filters.type = typeFilter.value;
    Object.keys((state.facets.projects && state.facets.projects.counts) || {}).sort().forEach((value) => {
      if (!value || value === 'commons' || value === 'general') return;
      if (Array.from(projectScope.options).some((option) => option.value === value)) return;
      const option = document.createElement('option');
      option.value = value;
      option.textContent = value;
      projectScope.appendChild(option);
    });
    projectScope.value = state.projectId;
  }

  function updateControlSummaries() {
    if (groupButton) {
      const group = { none: 'None', source: 'Source', type: 'Type', project: 'Project' }[state.group] || state.group;
      const sort = state.sort === 'title' ? 'Title' : 'Most recent';
      groupButton.textContent = `Group: ${group}`;
      groupButton.setAttribute('aria-label', `Group and sort Library results. Current group: ${group}. Current sort: ${sort}.`);
    }
    if (filterButton) {
      const count = Number(Boolean(state.filters.type));
      const scope = state.projectId === 'commons' ? 'Commons' : state.projectId;
      filterButton.textContent = `Scope: ${scope} · ${count}`;
      filterButton.setAttribute('aria-label', `Project scope: ${scope}. ${count} active metadata filter${count === 1 ? '' : 's'}.`);
    }
  }

  function reconcileRows() {
    state.selectedIds.forEach((id) => {
      if (!state.rowsById.has(id)) state.selectedIds.delete(id);
    });
    if (state.pinnedId && !state.rowsById.has(state.pinnedId)) state.pinnedId = null;
    updateLogo();
    renderPreview();
    renderActions();
  }

  function invalidateProjectScopeRows() {
    state.loading = false;
    state.loadingAll = false;
    state.retryAppend = false;
    state.error = '';
    state.actionNotice = '';
    state.rows = [];
    state.rowsById.clear();
    state.selectedIds.clear();
    state.pinnedId = null;
    state.total = 0;
    state.sourceCounts = {};
    state.facets = {};
    state.universe = null;
    state.pagination = { offset: 0, limit: PAGE_LIMIT, returned: 0, has_more: false, next_offset: null };
    updateFacetOptions();
    resetRelated(null, 'Project scope changed. Pin an item from the new result universe to request Related.');
    reconcileRows();
  }

  function browserUrl(offset) {
    const params = new URLSearchParams({ offset: String(offset), limit: String(PAGE_LIMIT) });
    state.sources.forEach((source) => params.append('source', source));
    if (state.projectId !== 'commons') params.set('project_id', state.projectId);
    if (state.query.trim()) params.set('q', state.query.trim());
    return `/api/library/browser?${params.toString()}`;
  }

  function settleNoSources() {
    ++state.requestGeneration;
    if (requestController) requestController.abort();
    requestController = null;
    state.loading = false;
    state.loadingAll = false;
    state.retryAppend = false;
    state.error = '';
    state.rows = [];
    state.rowsById.clear();
    state.total = 0;
    state.sourceCounts = {};
    state.facets = {};
    state.universe = null;
    state.pagination = { offset: 0, limit: PAGE_LIMIT, returned: 0, has_more: false, next_offset: null };
    updateFacetOptions();
    resetTextPreview(null);
    resetRelated(null, 'No sources are selected, so Related is not requested.');
    reconcileRows();
    render();
  }

  async function fetchPage(options) {
    if (!state.sources.size) {
      settleNoSources();
      return false;
    }
    const append = Boolean(options && options.append);
    if (!append) {
      state.loadingAll = false;
      invalidateTextPreviewRequest();
    }
    state.actionNotice = '';
    const externalGeneration = options && options.generation;
    const generation = externalGeneration || ++state.requestGeneration;
    if (!externalGeneration) {
      if (requestController) requestController.abort();
      requestController = new AbortController();
    }
    const controller = requestController;
    const offset = append ? Number(state.pagination.next_offset || 0) : 0;
    state.loading = true;
    state.error = '';
    render();
    try {
      const response = await fetch(browserUrl(offset), {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || `Library request failed (HTTP ${response.status})`);
      if (generation !== state.requestGeneration || controller !== requestController) return false;
      const nextRows = append ? state.rows.slice() : [];
      const nextRowsById = append ? new Map(state.rowsById) : new Map();
      (payload.rows || []).forEach((row) => {
        if (!row || !row.id || nextRowsById.has(row.id)) return;
        nextRowsById.set(row.id, row);
        nextRows.push(row);
      });
      const previousPinnedId = state.pinnedId;
      state.rows = nextRows;
      state.rowsById = nextRowsById;
      state.total = Number(payload.total || 0);
      state.sourceCounts = payload.source_counts || {};
      state.facets = payload.facets || {};
      state.universe = payload.universe || { complete: false, unavailable_sources: [] };
      state.pagination = payload.pagination || state.pagination;
      state.retryAppend = false;
      updateFacetOptions();
      if (!append) {
        state.selectedIds.forEach((id) => {
          if (!state.rowsById.has(id)) state.selectedIds.delete(id);
        });
        if (state.pinnedId && !state.rowsById.has(state.pinnedId)) state.pinnedId = null;
        const refreshedPin = pinnedRow();
        resetRelated(refreshedPin, previousPinnedId && !refreshedPin
          ? 'The previously pinned item is not present in the replacement inventory.'
          : undefined);
        fetchTextPreview(refreshedPin);
      }
      reconcileRows();
      if (!append && state.related.locator) fetchRelated(pinnedRow());
      return true;
    } catch (error) {
      if (error && error.name === 'AbortError') return false;
      if (generation !== state.requestGeneration) return false;
      state.error = error && error.message ? error.message : String(error);
      state.retryAppend = append;
      return false;
    } finally {
      if (generation === state.requestGeneration) {
        state.loading = false;
        render();
      }
    }
  }

  async function loadAll() {
    if (state.loadingAll || !state.pagination.has_more) return;
    const generation = ++state.requestGeneration;
    if (requestController) requestController.abort();
    requestController = new AbortController();
    state.loadingAll = true;
    state.error = '';
    render();
    try {
      while (generation === state.requestGeneration && state.pagination.has_more) {
        const before = state.rows.length;
        const loaded = await fetchPage({ append: true, generation });
        if (!loaded || state.rows.length === before) break;
      }
    } finally {
      if (generation === state.requestGeneration) {
        state.loadingAll = false;
        render();
      }
    }
  }

  function exactRelationshipCount(row, related) {
    const relationships = row.relationships || {};
    const summaries = Array.isArray(relationships.summaries) ? relationships.summaries : [];
    if (related && related.resolved && !related.loading && !related.error) {
      const complete = Number.isInteger(related.total)
        && Number.isInteger(related.returned)
        && related.returned === related.total;
      if (complete) return related.rows.filter((endpoint) => endpoint.drawable).length;
    }
    if (relationships.state !== 'fresh') return null;
    if (!summaries.every((item) => Number.isInteger(item.count))) return null;
    return summaries.reduce((total, item) => total + item.count, 0);
  }

  function appendRelationshipDisclosure(host, row) {
    const relationships = row.relationships || { state: 'unavailable', summaries: [] };
    const related = state.related.anchorId === row.id ? state.related : null;
    const endpoints = related ? related.rows.filter((endpoint) => endpoint.drawable) : [];
    const details = document.createElement('details');
    details.className = 'library-relationships';
    const summary = document.createElement('summary');
    summary.tabIndex = 0;
    const relationshipState = relationships.state || 'unavailable';
    const relationshipUpdated = relationships.updated_at || 'time unavailable';
    const exactCount = exactRelationshipCount(row, related);
    summary.textContent = `Relationships (${exactCount === null ? 'count unavailable' : exactCount}) — state ${relationshipState}; updated ${relationshipUpdated}`;
    details.appendChild(summary);
    if (relationships.reason) {
      const reason = document.createElement('p');
      reason.textContent = relationships.reason;
      details.appendChild(reason);
    }
    if (!(relationships.summaries || []).length) {
      const empty = document.createElement('p');
      empty.textContent = 'No authoritative relationship summaries are available for this item.';
      details.appendChild(empty);
    } else {
      const list = document.createElement('ul');
      relationships.summaries.forEach((item) => {
        const entry = document.createElement('li');
        const family = item.family || 'family unavailable';
        const confidence = item.confidence || 'confidence unavailable';
        const count = Number.isInteger(item.count) ? `${item.count} ` : '';
        entry.textContent = `${count}${item.direction} ${item.type}; ${family}; ${confidence}. Endpoints are not supplied by this inventory summary.`;
        list.appendChild(entry);
      });
      details.appendChild(list);
    }
    if (related && related.loading) {
      const loading = document.createElement('p');
      loading.textContent = 'Loading explicit relationship endpoints from the existing Related route.';
      details.appendChild(loading);
    } else if (related && related.error) {
      const error = document.createElement('p');
      error.textContent = `Explicit endpoints are unavailable: ${related.error}. Inventory summaries remain visible, but no connector is drawn.`;
      details.appendChild(error);
    } else if (related && endpoints.length) {
      const authority = document.createElement('p');
      authority.textContent = 'The following endpoints and relationship kinds were returned explicitly by Related. Freshness is unavailable; family and confidence stay unavailable unless the response supplies them.';
      details.appendChild(authority);
      const list = document.createElement('ul');
      list.className = 'library-related-endpoints';
      endpoints.forEach((endpoint) => {
        const entry = document.createElement('li');
        entry.dataset.relatedEndpointId = endpoint.id;
        const kinds = endpoint.kinds.map((kind) => `${relationshipDirections[kind]} ${kind}`).join(', ');
        entry.textContent = `${endpoint.title}: ${kinds}; family unavailable; confidence unavailable; freshness unavailable.`;
        list.appendChild(entry);
      });
      details.appendChild(list);
      const undrawable = related.rows.length - endpoints.length;
      if (undrawable) {
        const withheld = document.createElement('p');
        withheld.textContent = `${undrawable} returned suggestion${undrawable === 1 ? '' : 's'} lacked explicit relationship authority and therefore ${undrawable === 1 ? 'is' : 'are'} not drawn.`;
        details.appendChild(withheld);
      }
      if (related.reason) {
        const reason = document.createElement('p');
        reason.textContent = related.reason;
        details.appendChild(reason);
      }
    } else if (related && related.reason) {
      const reason = document.createElement('p');
      reason.textContent = related.reason;
      details.appendChild(reason);
    }
    host.appendChild(details);
  }

  function ensurePreviewLayers() {
    if (!previewTextLayer) {
      const pane = document.querySelector('.output-pane');
      if (pane) {
        previewTextLayer = document.createElement('section');
        previewTextLayer.className = 'library-preview-layer library-preview-layer--findings';
        previewTextLayer.setAttribute('aria-label', 'Selected Library item in Findings');
        pane.appendChild(previewTextLayer);
      }
    }
    if (!previewVisualLayer) {
      const pane = document.querySelector('.visual-pane-shell');
      if (pane) {
        previewVisualLayer = document.createElement('section');
        previewVisualLayer.className = 'library-preview-layer library-preview-layer--exhibits';
        previewVisualLayer.setAttribute('aria-label', 'Selected Library item in Exhibits');
        pane.appendChild(previewVisualLayer);
      }
    }
  }

  function renderPreview() {
    if (!state.open) return;
    ensurePreviewLayers();
    if (!previewTextLayer || !previewVisualLayer) return;
    previewTextLayer.replaceChildren();
    previewVisualLayer.replaceChildren();
    const row = pinnedRow();
    if (!row) {
      previewTextLayer.textContent = 'Pin a Library item to inspect its metadata and relationships without replacing the active Dialogue.';
      previewVisualLayer.textContent = 'No Library item is pinned.';
      return;
    }

    const heading = document.createElement('h2');
    heading.textContent = row.title;
    const badges = document.createElement('p');
    badges.className = 'library-preview-badges';
    badges.append(sourceBadge(row), document.createTextNode(` ${metadataLine(row)}`));
    const previewMessage = document.createElement('p');
    const currentTextPreview = state.textPreview.id === row.id
      ? state.textPreview
      : null;
    let previewBody = null;
    if (!row.preview.available) {
      previewMessage.textContent = row.source === 'dialogues'
        ? `This Dialogue is intentionally metadata-only and cannot be read here. ${row.preview.reason || ''}`.trim()
        : `Preview unavailable. ${row.preview.reason || ''}`.trim();
    } else if (row.source === 'dialogues') {
      previewMessage.textContent = 'The active Dialogue and its draft have not changed. Use Continue to open this readable Dialogue in the normal reader.';
    } else if (currentTextPreview && currentTextPreview.loading) {
      previewMessage.textContent = 'Loading the current text body…';
    } else if (currentTextPreview && currentTextPreview.error) {
      previewMessage.textContent = `Preview unavailable. ${currentTextPreview.error}`;
    } else if (currentTextPreview && typeof currentTextPreview.text === 'string') {
      previewMessage.textContent = 'Text preview';
      previewBody = document.createElement('pre');
      previewBody.className = 'library-preview-body';
      previewBody.textContent = currentTextPreview.text;
    } else {
      previewMessage.textContent = 'Preview unavailable. The current text body has not been loaded.';
    }
    previewTextLayer.append(heading, badges, previewMessage);
    if (previewBody) previewTextLayer.appendChild(previewBody);
    appendRelationshipDisclosure(previewTextLayer, row);

    const visualHeading = document.createElement('h2');
    visualHeading.textContent = 'Exhibits preview';
    const visualMessage = document.createElement('p');
    if (row.preview.kind === 'visual' || row.preview.kind === 'mixed') {
      visualMessage.textContent = 'Visual preview is unavailable from the inventory-only Library response; no filesystem locator is opened in the browser.';
    } else if (row.preview.kind === 'unsupported') {
      visualMessage.textContent = row.preview.reason || 'This item has no supported visual preview.';
    } else {
      visualMessage.textContent = 'This is a text-oriented item; its metadata and relationship disclosure are shown in Findings.';
    }
    previewVisualLayer.append(visualHeading, visualMessage);
  }

  function dialogueId(row) {
    if (!row || row.source !== 'dialogues' || !row.preview.available) return '';
    return String((row.preview.locator && row.preview.locator.dialogue_id) || '');
  }

  function builtinActions(row) {
    const actions = [];
    if (row) actions.push({ id: 'related', label: 'Show relationships', run: activatePinned });
    const id = dialogueId(row);
    if (id) {
      actions.push({ id: 'continue', label: 'Continue Dialogue', run: () => window.OraSidebar && window.OraSidebar.continueLibraryDialogue(row) });
      actions.push({ id: 'fork', label: 'Fork Dialogue', run: () => window.OraSidebar && window.OraSidebar.forkLibraryDialogue(row) });
      actions.push({ id: 'contributor', label: 'New Dialogue with contributor', run: () => window.OraSidebar && window.OraSidebar.createFromLibraryDialogue(row) });
      const lifecycle = String(row.metadata.lifecycle || '').toLowerCase();
      const privacy = String(row.metadata.privacy || '').toLowerCase();
      if (privacy !== 'stealth' && privacy !== 'off_record') {
        actions.push({
          id: lifecycle === 'archived' || lifecycle === 'inactive' ? 'restore' : 'archive',
          label: lifecycle === 'archived' || lifecycle === 'inactive' ? 'Restore Dialogue' : 'Archive Dialogue',
          run: () => window.OraSidebar && window.OraSidebar.setLibraryDialogueArchived(row, !(lifecycle === 'archived' || lifecycle === 'inactive')),
        });
      }
    }
    const selectedDialogues = Array.from(state.selectedIds)
      .map((itemId) => state.rowsById.get(itemId))
      .filter((item) => Boolean(dialogueId(item)));
    const selectedRows = Array.from(state.selectedIds)
      .map((itemId) => state.rowsById.get(itemId))
      .filter(Boolean);
    if (selectedRows.length && window.OraSidebar
        && typeof window.OraSidebar.createFromLibrarySelection === 'function') {
      actions.push({
        id: 'new-dialogue',
        label: `New Dialogue with checked context (${selectedRows.length})`,
        run: () => window.OraSidebar.createFromLibrarySelection(selectedRows, state.projectId),
      });
    }
    if (selectedDialogues.length && window.OraSidebar && typeof window.OraSidebar.addLibrarySelectionToActiveProject === 'function') {
      actions.push({
        id: 'project',
        label: `Add selected Dialogues to active project (${selectedDialogues.length})`,
        run: async () => {
          const outcome = await window.OraSidebar.addLibrarySelectionToActiveProject(selectedDialogues);
          (outcome.successfulIds || []).forEach((id) => state.selectedIds.delete(id));
          renderActions();
          render();
          if (outcome.failures && outcome.failures.length) {
            throw new Error(`${outcome.successfulIds.length} added; ${outcome.failures.length} failed. ${outcome.failures.join(' ')}`);
          }
        },
      });
    }
    return actions;
  }

  function renderActions() {
    actionHost.replaceChildren();
    const row = pinnedRow();
    const hasSelection = state.selectedIds.size > 0;
    actionButton.disabled = !row && !hasSelection;
    if (!row && !hasSelection) {
      actionHost.textContent = 'Pin an item or check rows to see available actions.';
      return;
    }
    const actions = builtinActions(row);
    const extensions = [];
    // G1.27-compatible extension seam: contributors may append contextual
    // actions without replacing the Library controller or its built-ins.
    if (row) {
      try {
        document.dispatchEvent(new CustomEvent('ora:library-actions-requested', {
          detail: { row, selection: Array.from(state.selectedIds), actions: extensions },
        }));
      } catch (error) {
        setNotice(`An action extension failed: ${error && error.message ? error.message : error}`, 'error');
      }
    }
    extensions.forEach((action) => actions.push(action));
    if (!actions.length) {
      actionHost.textContent = 'No action is available for this item. Its metadata remains readable.';
      return;
    }
    actions.forEach((action) => {
      if (!action || !action.id || !action.label || typeof action.run !== 'function') return;
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.libraryAction = action.id;
      button.textContent = action.label;
      button.disabled = Boolean(action.disabled);
      button.addEventListener('click', async () => {
        button.disabled = true;
        try {
          await action.run({ row, selection: Array.from(state.selectedIds) });
        } catch (error) {
          state.actionNotice = `Action failed: ${error && error.message ? error.message : error}`;
          setNotice(state.actionNotice, 'error');
        } finally {
          if (button.isConnected) button.disabled = Boolean(action.disabled);
        }
      });
      actionHost.appendChild(button);
    });
  }

  function updateLogo() {
    if (!logoO) return;
    const row = pinnedRow();
    if (!state.open) return;
    logoO.setAttribute('role', 'button');
    logoO.setAttribute('aria-label', row
      ? `Selected Library item: ${row.title}. Move focus to its relationship disclosure.`
      : 'Knowledge Library: no item selected. Move focus to Library results.');
    if (logoType) logoType.textContent = row ? (sourceLabels[row.source] || row.source).slice(0, 10) : 'Library';
    if (logoState) logoState.textContent = row ? (row.preview.available ? 'selected' : 'metadata') : 'no pin';
  }

  function activatePinned() {
    const relationship = previewTextLayer && previewTextLayer.querySelector('.library-relationships summary');
    const firstResult = results.querySelector('button:not(:disabled)');
    const target = relationship || firstResult || searchInput;
    if (target && typeof target.focus === 'function') target.focus();
  }

  function closePopover(name) {
    const panel = mount.querySelector(`[data-library-panel="${name}"]`);
    const button = mount.querySelector(`[data-library-popover="${name}"]`);
    if (panel) panel.hidden = true;
    if (button) button.setAttribute('aria-expanded', 'false');
  }

  function closePopovers() {
    mount.querySelectorAll('[data-library-panel]').forEach((panel) => { panel.hidden = true; });
    mount.querySelectorAll('[data-library-popover]').forEach((button) => button.setAttribute('aria-expanded', 'false'));
  }

  function togglePopover(name) {
    const panel = mount.querySelector(`[data-library-panel="${name}"]`);
    const button = mount.querySelector(`[data-library-popover="${name}"]`);
    if (!panel || !button || button.disabled) return;
    const opening = panel.hidden;
    closePopovers();
    panel.hidden = !opening;
    button.setAttribute('aria-expanded', opening ? 'true' : 'false');
    if (opening) {
      const focusable = panel.querySelector('input, select, button');
      if (focusable) focusable.focus();
    }
  }

  function open(options) {
    if (state.open) {
      searchInput.focus();
      return;
    }
    state.open = true;
    returnFocus = (options && options.returnFocus) || document.activeElement;
    savedLogo = logoO ? {
      role: logoO.getAttribute('role'),
      ariaLabel: logoO.getAttribute('aria-label'),
    } : null;
    ownUpperWorkspace();
    mount.hidden = false;
    ensurePreviewLayers();
    measureWorkspace();
    updateLogo();
    renderPreview();
    renderActions();
    fetchPage({ append: false });
    if (window.ResizeObserver) {
      resizeObserver = new ResizeObserver(measureWorkspace);
      ['.ora-shell', '.input-pane', '#chatZone', '#bridgeStrip', '#bridgeStripRight']
        .map((selector) => document.querySelector(selector))
        .filter(Boolean)
        .forEach((element) => resizeObserver.observe(element));
    }
    window.addEventListener('resize', measureWorkspace);
    setTimeout(() => searchInput.focus(), 0);
  }

  function close(options) {
    if (!state.open) return;
    state.open = false;
    ++state.requestGeneration;
    if (requestController) requestController.abort();
    requestController = null;
    resetTextPreview(null);
    resetRelated(null);
    state.loading = false;
    state.loadingAll = false;
    state.retryAppend = false;
    closePopovers();
    mount.hidden = true;
    if (resizeObserver) resizeObserver.disconnect();
    resizeObserver = null;
    window.removeEventListener('resize', measureWorkspace);
    if (previewTextLayer) previewTextLayer.remove();
    if (previewVisualLayer) previewVisualLayer.remove();
    previewTextLayer = null;
    previewVisualLayer = null;
    restoreUpperWorkspace();
    if (logoO && savedLogo) {
      if (savedLogo.role === null) logoO.removeAttribute('role');
      else logoO.setAttribute('role', savedLogo.role);
      if (savedLogo.ariaLabel === null) logoO.removeAttribute('aria-label');
      else logoO.setAttribute('aria-label', savedLogo.ariaLabel);
    }
    if (logoType) logoType.textContent = '';
    if (logoState) logoState.textContent = '';
    setStatus('Library closed.');
    const target = options && options.focus === false ? null : returnFocus;
    returnFocus = null;
    savedLogo = null;
    let focusTarget = target;
    const targetSidebar = target && target.closest ? target.closest('.left-sidebar') : null;
    if (targetSidebar && !targetSidebar.classList.contains('expanded')) {
      focusTarget = document.getElementById('sidebarDashExpand') || target;
    }
    if (focusTarget && focusTarget.isConnected && typeof focusTarget.focus === 'function') {
      try { focusTarget.focus(); } catch (error) {}
    }
  }

  mount.addEventListener('click', (event) => {
    const popover = event.target.closest('[data-library-popover]');
    if (popover) {
      togglePopover(popover.dataset.libraryPopover);
      return;
    }
    const view = event.target.closest('[data-library-view]');
    if (view) {
      state.view = view.dataset.libraryView;
      closePopovers();
      render();
      return;
    }
    const command = event.target.closest('[data-library-command]');
    if (!command) return;
    if (command.dataset.libraryCommand === 'close') close();
    else if (command.dataset.libraryCommand === 'clear-search') {
      state.query = '';
      searchInput.value = '';
      fetchPage({ append: false });
      searchInput.focus();
    } else if (command.dataset.libraryCommand === 'clear-filters') {
      state.filters = { type: '' };
      typeFilter.value = '';
      render();
    } else if (command.dataset.libraryCommand === 'load-more') fetchPage({ append: true });
    else if (command.dataset.libraryCommand === 'load-all') loadAll();
    else if (command.dataset.libraryCommand === 'retry') fetchPage({ append: state.retryAppend });
  });

  searchInput.addEventListener('input', () => {
    state.query = searchInput.value;
    fetchPage({ append: false });
  });

  mount.querySelectorAll('[data-library-source]').forEach((checkbox) => {
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) state.sources.add(checkbox.value);
      else state.sources.delete(checkbox.value);
      sourceCount.textContent = String(state.sources.size);
      closePopover('sources');
      fetchPage({ append: false });
    });
  });

  mount.querySelector('[data-library-group]').addEventListener('change', (event) => {
    state.group = event.target.value;
    render();
  });
  mount.querySelector('[data-library-sort]').addEventListener('change', (event) => {
    state.sort = event.target.value;
    render();
  });
  typeFilter.addEventListener('change', () => {
    state.filters.type = typeFilter.value;
    render();
  });
  projectScope.addEventListener('change', () => {
    const nextProjectId = projectScope.value || 'commons';
    if (nextProjectId !== state.projectId) {
      state.projectId = nextProjectId;
      invalidateProjectScopeRows();
    }
    fetchPage({ append: false });
  });

  document.addEventListener('ora:library-open-requested', (event) => open(event.detail || {}));
  document.addEventListener('ora:library-close-requested', () => close());
  document.addEventListener('ora:fresh-conversation-started', () => close({ focus: false }));
  document.addEventListener('keydown', (event) => {
    if (!state.open || event.key !== 'Escape') return;
    const openPanel = mount.querySelector('[data-library-panel]:not([hidden])');
    event.preventDefault();
    event.stopPropagation();
    if (openPanel) {
      closePopover(openPanel.dataset.libraryPanel);
      searchInput.focus();
    } else {
      close();
    }
  }, true);

  window.OraLibraryWorkspace = {
    open,
    close,
    isOpen: () => state.open,
    activatePinned,
    refresh: () => fetchPage({ append: false }),
    getState: () => ({
      open: state.open,
      view: state.view,
      sources: Array.from(state.sources),
      projectId: state.projectId,
      query: state.query,
      filters: Object.assign({}, state.filters),
      group: state.group,
      sort: state.sort,
      selectedIds: Array.from(state.selectedIds),
      pinnedId: state.pinnedId,
      loaded: state.rows.length,
      indexed: state.rowsById.size,
      total: state.total,
      loadingAll: state.loadingAll,
      universeComplete: Boolean(state.universe && state.universe.complete),
      pagination: Object.assign({}, state.pagination),
      requestGeneration: state.requestGeneration,
      relationshipGeneration: state.relationshipGeneration,
      related: {
        anchorId: state.related.anchorId,
        loading: state.related.loading,
        error: state.related.error,
        returned: state.related.returned,
        total: state.related.total,
        drawable: state.related.rows.filter((endpoint) => endpoint.drawable).length,
      },
      renderGeneration: state.renderGeneration,
    }),
  };
})();
