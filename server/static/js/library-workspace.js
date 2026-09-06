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
  const groupSelect = mount.querySelector('[data-library-group]');
  const folderGroupOption = groupSelect && groupSelect.querySelector('option[value="folder"]');
  const contentTypeGroupOption = groupSelect && groupSelect.querySelector('option[value="content-type"]');
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
    showArchived: false,
    refinementStatus: {},
    progress: { final: true },
    traceId: null,
    traceLimit: 50,
    trace: null,
    storageNotice: '',
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
    resolvedPreview: { id: null, loading: false, error: '', text: null, imageSrc: '' },
    edit: { id: null, text: '', digest: '', crlf: false, busy: false, error: '', notice: '' },
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
  let previewSlots = null;
  let documentSession = null;
  let documentIdentity = null;
  let documentText = null;
  let editorSession = null;
  let editController = null;
  let savedLogo = null;
  const ownedUpperState = new Map();
  const sceneSlots = new Map();
  const scenePositions = new Map();
  let sceneGeometry = '';
  function clearScene() { sceneSlots.clear(); scenePositions.clear(); sceneGeometry = ''; }
  const VIEW_STORAGE_KEY = 'ora.library.last-view';
  try {
    const savedView = localStorage.getItem(VIEW_STORAGE_KEY);
    if (savedView === 'list' || savedView === 'visual') state.view = savedView;
    else if (savedView !== null) state.storageNotice = 'The saved Library view was invalid; List is being used.';
  } catch (error) {
    state.storageNotice = 'Saved view storage is unavailable; List is being used.';
  }
  const refinementLabels = { lifecycle: 'Lifecycle', privacy: 'Privacy', local_restriction: 'Local restriction',
    relationship: 'Relationship kind', relationship_family: 'Relationship family', epistemic_kind: 'Epistemic kind',
    file_type: 'Canonical File type', folder: 'Folder', category: 'Project category', content_type: 'Content type' };
  const refinementControls = mount.querySelector('[data-library-refinement-controls]');
  Object.entries(refinementLabels).forEach(([key, label]) => {
    const host = document.createElement('label');
    host.append(document.createTextNode(label + ' '));
    const select = document.createElement('select');
    select.dataset.libraryRefinement = key;
    select.appendChild(new Option('Any', ''));
    host.appendChild(select);
    refinementControls.appendChild(host);
  });
  ['extraction_date_from', 'extraction_date_to'].forEach((key) => {
    const label = document.createElement('label');
    label.textContent = key.endsWith('from') ? 'Extracted from ' : 'Extracted through ';
    const input = document.createElement('input');
    input.type = 'date'; input.dataset.libraryRefinement = key;
    label.appendChild(input); refinementControls.appendChild(label);
  });

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
    return Array.isArray(projects) && projects.length ? projects.join(', ') : 'Commons';
  }

  function rowFolder(row) {
    if (!row || row.source !== 'files') return '';
    const details = row.provenance && row.provenance.details;
    const relativePath = String((details && details.relative_path) || '').trim();
    if (!relativePath) return '';
    const parts = relativePath.replace(/\\/g, '/').split('/').filter(Boolean);
    if (parts.length <= 1) return 'Project root';
    parts.pop();
    return parts.join('/');
  }

  function fileGroupingAvailable() {
    return state.sources.size === 1 && state.sources.has('files');
  }

  function syncGroupAvailability() {
    const fileGroupsAvailable = fileGroupingAvailable();
    [folderGroupOption, contentTypeGroupOption].forEach((option) => {
      if (!option) return;
      option.hidden = !fileGroupsAvailable;
      option.disabled = !fileGroupsAvailable;
    });
    if (!fileGroupsAvailable && ['folder', 'content-type'].includes(state.group)) state.group = 'none';
    if (groupSelect) groupSelect.value = state.group;
  }

  function pinnedRow() {
    return state.pinnedId ? state.rowsById.get(state.pinnedId) || null : null;
  }

  function allReturnedPagesLoaded() {
    return state.progress.final !== false && !state.pagination.has_more;
  }

  function localQualificationRequested() {
    return Boolean(state.group !== 'none' || state.sort === 'title');
  }

  function qualificationAvailable() {
    return allReturnedPagesLoaded();
  }

  function visibleRows() {
    let rows = state.traceId && state.trace ? state.trace.rows.slice() : state.rows.slice();
    if (localQualificationRequested() && !qualificationAvailable()) return rows;
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
    && SOURCES.includes(row.source)
    && row.preview && row.preview.kind === 'text'
    && row.preview.available === true);

  const imagePreviewEligible = (row) => Boolean(row
    && row.source === 'files'
    && row.preview && row.preview.kind === 'visual'
    && row.preview.available === true);

  const markdownEditEligible = (row) => Boolean(textPreviewEligible(row)
    && row.source !== 'dialogues' && row.metadata.lifecycle !== 'archived'
    && row.metadata && row.metadata.content_type === 'text/markdown'
    && row.editability && row.editability.available === true
    && row.editability.editable === true);

  function resetEdit(notice) {
    if (editController) editController.abort();
    editController = null;
    if (editorSession) {
      editorSession.destroy();
      editorSession = null;
      documentSession = null;
      documentIdentity = null;
      documentText = null;
      if (previewSlots) previewSlots.document.removeAttribute('data-library-edit-draft');
    }
    state.edit = { id: null, text: '', digest: '', crlf: false, busy: false, error: '', notice: notice || '' };
  }

  async function libraryEditRequest(url, options) {
    const controller = new AbortController();
    editController = controller;
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(url, Object.assign({}, options, { signal: controller.signal }));
      const payload = await response.json();
      if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        throw new Error('The edit response was incomplete.');
      }
      if (!response.ok) {
        const error = new Error(payload.error || `Library edit failed (HTTP ${response.status})`);
        error.notSaved = payload.saved === false || [400, 403, 404, 409].includes(response.status);
        throw error;
      }
      return payload;
    } finally {
      clearTimeout(timeout);
      if (editController === controller) editController = null;
    }
  }

  async function startMarkdownEdit(row) {
    if (!state.open || state.pinnedId !== row.id || state.edit.busy || state.edit.digest
        || !markdownEditEligible(row) || !documentEditingAvailable()) return;
    resetEdit();
    const edit = state.edit;
    edit.id = row.id;
    edit.busy = true;
    renderPreview();
    try {
      const params = new URLSearchParams({ id: row.id });
      const payload = await libraryEditRequest(`/api/library/edit?${params.toString()}`, {
        headers: { Accept: 'application/json' },
      });
      if (edit !== state.edit || !state.open || state.pinnedId !== row.id) return;
      if (payload.id !== row.id || payload.source !== row.source || typeof payload.text !== 'string'
          || !/^[0-9a-f]{64}$/.test(payload.digest || '')) {
        throw new Error('The edit response did not match the pinned Library item.');
      }
      const withoutCrlf = payload.text.replace(/\r\n/g, '');
      edit.crlf = payload.text.includes('\r\n');
      if (withoutCrlf.includes('\r') || (edit.crlf && withoutCrlf.includes('\n'))) {
        throw new Error('Mixed or lone-carriage-return line endings cannot be edited safely.');
      }
      edit.text = edit.crlf ? payload.text.replace(/\r\n/g, '\n') : payload.text;
      edit.digest = payload.digest;
    } catch (error) {
      if (edit === state.edit) edit.error = error.message || String(error);
    } finally {
      if (edit === state.edit) { edit.busy = false; renderPreview(); }
    }
  }

  async function saveMarkdownEdit(row) {
    const edit = state.edit;
    if (!state.open || edit.id !== row.id || state.pinnedId !== row.id
        || !edit.digest || edit.busy || !editorSession) return;
    edit.text = editorSession.getText();
    edit.busy = true;
    edit.error = '';
    renderPreview();
    try {
      if (edit.text.includes('\r')) throw new Error('The edit draft contains unsupported carriage returns.');
      const payload = await libraryEditRequest('/api/library/edit', {
        method: 'PUT',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: row.id,
          expected_digest: edit.digest,
          text: edit.crlf ? edit.text.replace(/\n/g, '\r\n') : edit.text,
        }),
      });
      if (edit !== state.edit || !state.open || state.pinnedId !== row.id) return;
      if (payload.id !== row.id || payload.source !== row.source || payload.saved !== true
          || (row.source === 'files' ? payload.index_refreshed !== null
            : typeof payload.index_refreshed !== 'boolean')) throw new Error('The save response was incomplete.');
      const message = payload.index_refreshed === false
        ? `File saved, but the Engram index refresh failed. ${payload.index_error || ''}`.trim()
        : payload.index_refreshed === true
          ? 'File saved and the Engram index refreshed.'
          : 'File saved. Files remain inventory-only.';
      resetEdit(message);
      renderPreview();
      fetchPreview(row);
    } catch (error) {
      if (edit === state.edit) {
        edit.error = (error.name === 'AbortError' ? 'The save request timed out.' : error.message || String(error))
          + (error.notSaved ? ' Nothing was written. Your draft is still here.'
            : ' The save outcome is unknown. Your draft is still here; check the source before retrying.');
      }
    } finally {
      if (edit === state.edit) { edit.busy = false; renderPreview(); }
    }
  }

  function invalidatePreviewRequest() {
    ++state.previewGeneration;
    if (previewController) previewController.abort();
    previewController = null;
    state.resolvedPreview.loading = false;
  }

  function resetResolvedPreview(row) {
    invalidatePreviewRequest();
    state.resolvedPreview = {
      id: row ? row.id : null, loading: false, error: '', text: null, imageSrc: '',
    };
  }

  async function fetchPreview(row) {
    resetResolvedPreview(row);
    if ((!textPreviewEligible(row) && !imagePreviewEligible(row)) || !state.open) return;
    const generation = state.previewGeneration;
    previewController = new AbortController();
    const controller = previewController;
    state.resolvedPreview.loading = true;
    try {
      const params = new URLSearchParams({ id: row.id });
      if (state.showArchived) params.set('show_archived', '1');
      const response = await fetch(`/api/library/preview?${params.toString()}`, {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || `Preview request failed (HTTP ${response.status})`);
      if (generation !== state.previewGeneration || state.pinnedId !== row.id) return;
      if (payload.id !== row.id || payload.source !== row.source) {
        throw new Error('The preview response did not match the pinned Library item.');
      }
      if (row.source === 'dialogues' && Array.isArray(payload.turns)
          && payload.turns.length && payload.turns.length % 2 === 0
          && payload.turns.every((turn, index) => turn && turn.role === (index % 2 ? 'assistant' : 'user') && typeof turn.content === 'string')) {
        state.resolvedPreview.turns = payload.turns;
        state.resolvedPreview.incomplete = payload.incomplete === true;
      } else if (textPreviewEligible(row) && row.source !== 'dialogues' && typeof payload.text === 'string') {
        state.resolvedPreview.text = payload.text;
      } else if (imagePreviewEligible(row) && payload.image
          && ['image/png', 'image/jpeg', 'image/webp'].includes(payload.image.mime_type)
          && typeof payload.image.data === 'string' && payload.image.data) {
        state.resolvedPreview.imageSrc = `data:${payload.image.mime_type};base64,${payload.image.data}`;
      } else {
        throw new Error('The preview response did not contain the requested safe content.');
      }
      state.resolvedPreview.error = '';
    } catch (error) {
      if (error && error.name === 'AbortError') return;
      if (generation !== state.previewGeneration) return;
      state.resolvedPreview.error = error && error.message ? error.message : String(error);
      state.resolvedPreview.text = null;
      state.resolvedPreview.imageSrc = '';
      state.resolvedPreview.turns = null;
    } finally {
      if (generation === state.previewGeneration) {
        state.resolvedPreview.loading = false;
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
      show_archived: state.showArchived ? '1' : '0',
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
    if (!row || state.edit.id !== row.id) resetEdit();
    state.pinnedId = row ? row.id : null;
    resetRelated(row);
    fetchPreview(row);
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
    if (state.group === 'provenance') return ((row.provenance && row.provenance.sources) || []).map((source) => source.title).join(', ') || 'Unresolved extraction source';
    if (['nexus', 'file_type', 'tags', 'category'].includes(state.group)) {
      const value = row.metadata[state.group];
      return Array.isArray(value) ? value.join(', ') : value || 'Unavailable';
    }
    if (state.group === 'source') return sourceLabels[row.source] || row.source;
    if (state.group === 'type') return rowType(row);
    if (state.group === 'content-type') {
      const value = row.metadata && row.metadata.content_type;
      return value === undefined || value === null || String(value).trim() === '' ? '' : String(value);
    }
    if (state.group === 'project') return rowProject(row);
    if (state.group === 'folder') return rowFolder(row);
    return '';
  }

  function groupOccurrences(row) {
    if (state.group === 'project') return row.metadata.project_ids && row.metadata.project_ids.length ? row.metadata.project_ids : ['Commons'];
    if (state.group === 'provenance') return ((row.provenance && row.provenance.sources) || []).map((source) => source.id);
    if (['nexus', 'tags', 'category'].includes(state.group) && Array.isArray(row.metadata[state.group])) return row.metadata[state.group];
    return [groupValue(row) || 'Unavailable'];
  }

  function groupLabel(value) {
    if (state.group === 'category') return (state.facets.category && state.facets.category.labels && state.facets.category.labels[value]) || value;
    if (state.group === 'provenance') {
      for (const row of state.rows) {
        const source = ((row.provenance && row.provenance.sources) || []).find((item) => item.id === value);
        if (source) return `${source.title} (${sourceLabels[source.source] || 'source'})`;
      }
    }
    return value;
  }

  function renderList(rows) {
    const fragment = document.createDocumentFragment();
    const effectiveGroup = qualificationAvailable() ? state.group : 'none';
    if (effectiveGroup === 'none') {
      rows.forEach((row) => fragment.appendChild(buildListRow(row)));
    } else {
      const groups = new Map();
      rows.forEach((row) => {
        const values = groupOccurrences(row);
        (values.length ? values : ['Unresolved']).forEach((value) => {
          if (!groups.has(value)) groups.set(value, []);
          groups.get(value).push(row);
        });
      });
      Array.from(groups.keys()).sort().forEach((name) => {
        const section = document.createElement('section');
        section.className = 'library-result-group';
        const heading = document.createElement('h2');
        heading.textContent = `${groupLabel(name)} (${groups.get(name).length})`;
        section.appendChild(heading);
        groups.get(name).forEach((row) => section.appendChild(buildListRow(row)));
        fragment.appendChild(section);
      });
    }
    results.appendChild(fragment);
  }

  function buildVisualNode(row, occurrence = '') {
    const button = document.createElement('div');
    button.className = `library-visual-node is-${row.source}`;
    button.dataset.libraryNodeId = row.id;
    button.dataset.librarySlot = row.id + '::' + occurrence;
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = state.selectedIds.has(row.id);
    checkbox.setAttribute('aria-label', `Select ${row.title} for bulk actions`);
    checkbox.addEventListener('change', () => selectRow(row, checkbox.checked));
    checkbox.addEventListener('click', (event) => event.stopPropagation());
    button.appendChild(checkbox);
    const pin = document.createElement('button');
    pin.type = 'button';
    pin.className = 'library-visual-node__pin';
    pin.setAttribute('aria-label', `Read ${row.title}`);
    pin.setAttribute('aria-pressed', String(state.pinnedId === row.id));
    button.setAttribute('aria-pressed', state.pinnedId === row.id ? 'true' : 'false');
    const groupedAs = qualificationAvailable() && state.group !== 'none'
      ? ` Group: ${groupValue(row) || 'Unavailable'}.`
      : '';
    button.setAttribute('aria-label', `${sourceLabels[row.source]}: ${row.title}. ${metadataLine(row)}.${groupedAs}`);
    button.append(sourceBadge(row));
    const title = document.createElement('span');
    title.textContent = row.title;
    pin.appendChild(title);
    button.appendChild(pin);
    if (qualificationAvailable() && state.group !== 'none') {
      const group = document.createElement('small');
      group.className = 'library-visual-node__group';
      group.textContent = groupLabel(occurrence) || groupValue(row) || 'Unavailable';
      button.appendChild(group);
    }
    button.addEventListener('click', () => pinRow(row));
    return button;
  }

  function renderVisual(rows) {
    const visual = document.createElement('div');
    visual.className = 'library-visual-map';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.classList.add('library-visual-connectors');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    visual.appendChild(svg);
    rows.forEach((row) => {
      const groups = qualificationAvailable() && state.group !== 'none' ? groupOccurrences(row) : [''];
      (groups.length ? groups : ['Unresolved']).forEach((group) => visual.appendChild(buildVisualNode(row, group)));
    });
    // Arrival and enrichment append slots; only an explicit scene change clears them.
    Array.from(visual.querySelectorAll('[data-library-slot]')).sort((a, b) => {
      [a, b].forEach((node) => { if (!sceneSlots.has(node.dataset.librarySlot)) sceneSlots.set(node.dataset.librarySlot, sceneSlots.size); });
      return sceneSlots.get(a.dataset.librarySlot) - sceneSlots.get(b.dataset.librarySlot);
    }).forEach((node) => visual.appendChild(node));
    if (state.group !== 'none') {
      const groupState = document.createElement('p');
      groupState.className = 'library-visual-group-state';
      const label = {
        source: 'source', type: 'type', 'content-type': 'content type', project: 'project', folder: 'folder',
      }[state.group] || state.group;
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
    edgeState.textContent = state.traceId
      ? 'Trace shows stored direction, type and confidence within the current Library filters. Every advertised neighbor remains in the relationship list below.'
      : 'Browse keeps inventory positions stable. Related discovery stays below; use Trace from an Engram for typed connectors.';
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
    const geometry = [visualRect.width, visualRect.height, anchorX, anchorY].join(':');
    if (geometry !== sceneGeometry) { scenePositions.clear(); sceneGeometry = geometry; }
    scenePositions.forEach((placement) => { if (placement) occupied.push(placement); });

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
        const slot = node.dataset.librarySlot;
        const placement = scenePositions.get(slot) || candidateAngles.map((degrees) => {
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
        if (!scenePositions.has(slot)) { scenePositions.set(slot, placement); occupied.push(placement); }
        visible.push(node);
      });
      return visible;
    }

    const visibleInventoryNodes = placeArc(inventoryNodes, availableRadius);
    const visibleRelatedNodes = [];

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
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    marker.id = 'library-trace-arrow'; marker.setAttribute('viewBox', '0 0 10 10');
    marker.setAttribute('refX', '9'); marker.setAttribute('refY', '5'); marker.setAttribute('markerWidth', '6'); marker.setAttribute('markerHeight', '6'); marker.setAttribute('orient', 'auto-start-reverse');
    const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    arrow.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z'); marker.appendChild(arrow); defs.appendChild(marker); svg.appendChild(defs);
    ((state.traceId && state.trace && state.trace.edges) || []).forEach((edge) => {
      const from = visibleInventoryNodes.find((node) => node.dataset.libraryNodeId === edge.source);
      const to = visibleInventoryNodes.find((node) => node.dataset.libraryNodeId === edge.target);
      if (!from || !to) return;
      const fromRect = from.getBoundingClientRect();
      const toRect = to.getBoundingClientRect();
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', String(fromRect.left + fromRect.width / 2 - visualRect.left));
      line.setAttribute('y1', String(fromRect.top + fromRect.height / 2 - visualRect.top));
      line.setAttribute('x2', String(toRect.left + toRect.width / 2 - visualRect.left));
      line.setAttribute('y2', String(toRect.top + toRect.height / 2 - visualRect.top));
      line.dataset.relationshipType = edge.type;
      line.dataset.relationshipFamily = edge.family;
      line.setAttribute('marker-end', 'url(#library-trace-arrow)');
      line.setAttribute('stroke-dasharray', { evidence: 'none', building: '6 3', causal: '2 3', hierarchy: '8 3 2 3' }[edge.family] || '1 5');
      const label = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      label.textContent = `${edge.type}; ${edge.family}; confidence ${edge.confidence || 'unknown'}`;
      line.appendChild(label);
      svg.appendChild(line);
      drawnConnectors += 1;
    });
    const edgeState = visual.querySelector('.library-visual-edge-state');
    if (edgeState && state.traceId && state.trace) {
      edgeState.textContent = `${drawnConnectors} stored connectors fit this screen. All ${state.trace.total_neighbors} admitted neighbors and the displayed endpoints' typed edges are disclosed below; ${state.trace.remaining} more neighbors await explicit expansion. State: ${state.trace.state}. ${state.trace.reason || ''}`;
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
    syncGroupAvailability();
    renderRefinementChips();
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
    } else if (state.storageNotice) {
      setNotice(state.storageNotice, 'incomplete');
    } else if (state.universe && !state.universe.complete) {
      const unavailable = (state.universe.unavailable_sources || [])
        .map((item) => `${sourceLabels[item.source] || item.source}: ${item.reason}`)
        .join(' ');
      setNotice(`Results are incomplete. ${unavailable}`.trim(), 'incomplete');
    } else {
      setNotice('', 'info');
    }

    if (!rows.length) {
      renderEmpty(state.filters.provenance_id && !state.query
        ? 'No admitted indexed derivation exists for this source in the current scope. No Engram has been created.'
        : state.query
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

    if (state.progress.final !== false && state.pagination.has_more && !state.loadingAll) {
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
      const key = select.dataset.libraryRefinement || 'type';
      const current = state.filters[key] || '';
      Array.from(select.options).slice(1).forEach((option) => option.remove());
      Object.keys(counts || {}).sort().forEach((value) => {
        const option = document.createElement('option');
        option.value = value;
        const label = key === 'category' ? ((state.facets.category || {}).labels || {})[value] || value : value;
        option.textContent = `${label} (${counts[value]})`;
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
    mount.querySelectorAll('select[data-library-refinement]').forEach((select) => {
      const key = select.dataset.libraryRefinement;
      const facet = state.facets[key] || {};
      update(select, facet.counts);
      select.disabled = !Object.keys(facet.counts || {}).length && !state.filters[key];
      select.title = select.disabled ? 'No authoritative values are available in this scope. Unknown metadata is not inferred.' : '';
    });
    // A validated destination remains selectable before results and without matching rows.
    const projects = Object.keys((state.facets.projects && state.facets.projects.counts) || {})
      .filter((value) => value && value !== 'commons' && value !== 'general');
    projects.concat(state.projectId).sort().forEach((value) => {
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
      const group = {
        none: 'None', source: 'Source', type: 'Type', 'content-type': 'Content type', project: 'Project', folder: 'Folder',
      }[state.group] || state.group;
      const sort = state.sort === 'title' ? 'Title' : 'Most recent';
      groupButton.textContent = `Group: ${group}`;
      groupButton.setAttribute('aria-label', `Group and sort Library results. Current group: ${group}. Current sort: ${sort}.`);
    }
    if (filterButton) {
      const count = Object.values(state.filters).filter(Boolean).length + Number(state.showArchived);
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
    if (state.edit.id && (state.edit.id !== state.pinnedId || !textPreviewEligible(pinnedRow()))) resetEdit();
    updateLogo();
    renderPreview();
    renderActions();
  }

  function invalidateProjectScopeRows() {
    clearScene();
    state.traceId = null;
    state.trace = null;
    state.traceLimit = 50;
    state.loading = false;
    state.loadingAll = false;
    state.retryAppend = false;
    state.error = '';
    state.actionNotice = '';
    resetEdit();
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
    const params = new URLSearchParams({ offset: String(offset), limit: String(PAGE_LIMIT), stream: '1' });
    state.sources.forEach((source) => params.append('source', source));
    if (state.projectId !== 'commons') params.set('project_id', state.projectId);
    if (state.query.trim()) params.set('q', state.query.trim());
    Object.entries(state.filters).forEach(([key, value]) => {
      if (!value) return;
      if (key === 'tag') String(value).split(',').map((tag) => tag.trim()).filter(Boolean).forEach((tag) => params.append('tag', tag));
      else params.set(key === 'type' ? 'item_type' : key, value);
    });
    if (state.showArchived) params.set('show_archived', '1');
    if (state.traceId) { params.set('trace_id', state.traceId); params.set('trace_limit', String(state.traceLimit)); }
    return `/api/library/browser?${params.toString()}`;
  }

  function renderRefinementChips() {
    const host = mount.querySelector('[data-library-chips]');
    host.replaceChildren();
    Object.entries(state.filters).filter(([, value]) => value).forEach(([key, value]) => {
      const chip = document.createElement('button');
      chip.type = 'button'; chip.dataset.libraryChip = key;
      const info = state.refinementStatus[key === 'type' ? 'item_type' : key];
      chip.textContent = `${refinementLabels[key] || key}: ${value} ×${info && info.available === false ? ' (unavailable)' : ''}`;
      chip.title = (info && info.reason) || 'Remove this refinement';
      if (info && info.reason) chip.setAttribute('aria-label', chip.textContent + '. ' + info.reason);
      chip.addEventListener('click', () => {
        delete state.filters[key];
        const control = mount.querySelector(`[data-library-refinement="${key}"]`);
        if (control) control.value = '';
        if (key === 'type') typeFilter.value = '';
        changeCriteria();
      });
      host.appendChild(chip);
      if (info && info.reason) {
        const reason = document.createElement('small'); reason.textContent = info.reason; host.appendChild(reason);
      }
    });
    if (state.showArchived) {
      const chip = document.createElement('button'); chip.type = 'button'; chip.textContent = 'Archives included (read-only) ×';
      chip.addEventListener('click', () => { state.showArchived = false; mount.querySelector('[data-library-archived]').checked = false; changeCriteria(); });
      host.appendChild(chip);
    }
    if (state.group !== 'none') {
      const note = document.createElement('small');
      note.textContent = 'One grouping axis. Items with multiple memberships appear in each group; totals and bulk selection count each item once.';
      host.appendChild(note);
    }
  }

  function changeCriteria() {
    invalidateProjectScopeRows();
    fetchPage({ append: false });
  }

  function acceptSnapshot(payload, append, final) {
    if (!payload || !Array.isArray(payload.rows) || !payload.universe || !payload.pagination
        || payload.rows.some((row) => !row || typeof row.id !== 'string' || !row.metadata || !row.preview)) {
      throw new Error('The Library response was malformed; safe earlier results have been retained.');
    }
    const previousPinnedId = state.pinnedId;
    const nextRows = append || !final ? state.rows.slice() : [];
    const nextRowsById = !final ? new Map(state.rowsById) : new Map(nextRows.map((row) => [row.id, row]));
    payload.rows.forEach((row) => {
      const old = nextRows.findIndex((item) => item.id === row.id);
      if (old < 0) nextRows.push(row); else nextRows[old] = row;
      nextRowsById.set(row.id, row);
    });
    state.rows = nextRows; state.rowsById = nextRowsById;
    state.total = Number(payload.total || 0);
    state.sourceCounts = payload.source_counts || {}; state.facets = payload.facets || {};
    state.universe = Object.assign({}, payload.universe, { complete: final && payload.universe.complete === true });
    state.refinementStatus = payload.refinements || {};
    state.progress = Object.assign({}, payload.progress, { final });
    state.pagination = final ? payload.pagination : { ...payload.pagination, has_more: false, next_offset: null };
    state.retryAppend = false;
    if (final && state.traceId) {
      if (payload.trace && (!Array.isArray(payload.trace.rows) || !Array.isArray(payload.trace.edges)
          || payload.trace.rows.some((row) => !row || typeof row.id !== 'string' || !row.preview || !row.metadata))) {
        throw new Error('The Trace response was malformed; safe inventory remains available.');
      }
      state.trace = payload.trace || { rows: [], edges: [], state: 'unavailable', reason: 'Trace response unavailable', total_neighbors: 0, remaining: 0 };
      state.trace.rows.forEach((row) => state.rowsById.set(row.id, row));
    }
    updateFacetOptions();
    if (final) {
      reconcileRows();
      const row = pinnedRow();
      if (row && (!append || previousPinnedId !== row.id || state.resolvedPreview.id !== row.id)) fetchPreview(row);
      if (!row) resetResolvedPreview(null);
      if (!append && (!state.related.anchorId || state.related.anchorId !== state.pinnedId)) {
        resetRelated(row); if (state.related.locator) fetchRelated(row);
      }
    }
    render();
  }

  function settleNoSources() {
    ++state.requestGeneration;
    if (requestController) requestController.abort();
    requestController = null;
    state.loading = false;
    state.loadingAll = false;
    state.retryAppend = false;
    state.error = '';
    resetEdit();
    state.rows = [];
    state.rowsById.clear();
    state.total = 0;
    state.sourceCounts = {};
    state.facets = {};
    state.universe = null;
    state.pagination = { offset: 0, limit: PAGE_LIMIT, returned: 0, has_more: false, next_offset: null };
    updateFacetOptions();
    resetResolvedPreview(null);
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
      invalidatePreviewRequest();
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
        headers: { Accept: 'application/x-ndjson, application/json' },
        signal: controller.signal,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || `Library request failed (HTTP ${response.status})`);
      }
      const current = () => generation === state.requestGeneration && controller === requestController && state.open;
      if (response.headers && (response.headers.get('content-type') || '').includes('application/x-ndjson')) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '', finalSeen = false;
        try {
          while (current()) {
            const chunk = await reader.read();
            if (!current()) return false;
            buffer += decoder.decode(chunk.value || new Uint8Array(), { stream: !chunk.done });
            let newline;
            while ((newline = buffer.indexOf('\n')) >= 0) {
              const line = buffer.slice(0, newline); buffer = buffer.slice(newline + 1);
              if (!line.trim()) continue;
              const frame = JSON.parse(line);
              if (finalSeen || frame.event !== 'snapshot' || typeof frame.stage !== 'string' || typeof frame.final !== 'boolean') throw new Error('Malformed Library progress frame.');
              acceptSnapshot(frame.data, append, frame.final);
              finalSeen = frame.final;
            }
            if (chunk.done) break;
          }
          if (buffer.trim() || !finalSeen) throw new Error('The Library stream ended without final accounting. Safe results remain incomplete; retry to finish.');
        } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
      } else {
        const payload = await response.json();
        if (!current()) return false;
        acceptSnapshot(payload, append, true);
      }
      return true;
    } catch (error) {
      if (error && error.name === 'AbortError') return false;
      if (generation !== state.requestGeneration) return false;
      state.error = error && error.message ? error.message : String(error);
      state.progress = { final: false };
      if (state.universe) state.universe.complete = false;
      state.pagination = { ...state.pagination, has_more: false, next_offset: null };
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
        entry.textContent = `${count}${item.direction} ${item.type}; ${family}; ${confidence}. ${item.endpoint_title ? `${item.origin || 'Stored relationship'}: ${item.endpoint_title}.` : 'Endpoints are not supplied by this inventory summary.'}`;
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
    if (state.traceId && state.trace) {
      const trace = document.createElement('details');
      trace.className = 'library-trace'; trace.open = true;
      const summary = document.createElement('summary');
      summary.textContent = `Trace within current filters: ${state.trace.total_neighbors} admitted neighbors; ${state.trace.state}`;
      trace.appendChild(summary);
      const reason = document.createElement('p');
      reason.textContent = [state.trace.reason, state.trace.ambiguity_reason].filter(Boolean).join(' ');
      trace.appendChild(reason);
      const list = document.createElement('ul');
      state.trace.rows.forEach((neighbor) => {
        const entry = document.createElement('li');
        const select = document.createElement('input'); select.type = 'checkbox';
        select.checked = state.selectedIds.has(neighbor.id);
        select.setAttribute('aria-label', `Select ${neighbor.title} for bulk actions`);
        select.addEventListener('change', () => selectRow(neighbor, select.checked));
        const button = document.createElement('button'); button.type = 'button'; button.textContent = neighbor.title;
        button.dataset.libraryTraceNeighbor = neighbor.id;
        button.addEventListener('click', () => pinRow(neighbor));
        entry.append(select, button); list.appendChild(entry);
      });
      trace.appendChild(list);
      const edges = document.createElement('ul');
      state.trace.edges.forEach((edge) => {
        const entry = document.createElement('li');
        const source = state.rowsById.get(edge.source), target = state.rowsById.get(edge.target);
        entry.textContent = `${source ? source.title : 'Admitted source'} → ${target ? target.title : 'Admitted target'}: ${edge.type}; ${edge.family}; confidence ${edge.confidence || 'unknown'}.`;
        edges.appendChild(entry);
      });
      trace.appendChild(edges);
      if (state.trace.remaining) {
        const more = document.createElement('button'); more.type = 'button'; more.dataset.libraryTraceExpand = '';
        more.textContent = `${state.trace.remaining} more neighbors — show next 50`;
        more.addEventListener('click', () => { state.traceLimit += 50; fetchPage({ append: false }); });
        trace.appendChild(more);
      }
      host.appendChild(trace);
    }
  }

  function ensurePreviewLayers() {
    if (!previewTextLayer) {
      const pane = document.querySelector('.output-pane');
      if (pane) {
        previewTextLayer = document.createElement('section');
        previewTextLayer.className = 'library-preview-layer library-preview-layer--findings';
        previewTextLayer.setAttribute('aria-label', 'Selected Library item in Findings');
        previewSlots = {};
        ['metadata', 'document', 'controls', 'status', 'relationships'].forEach((name) => {
          const slot = document.createElement('div');
          slot.className = `library-preview-${name}`;
          previewSlots[name] = slot;
          previewTextLayer.appendChild(slot);
        });
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

  function destroyDocument() {
    if (documentSession) documentSession.destroy();
    documentSession = null;
    editorSession = null;
    documentIdentity = null;
    documentText = null;
    if (previewSlots) {
      previewSlots.document.replaceChildren();
      previewSlots.document.removeAttribute('data-library-edit-draft');
    }
  }

  function showRead(host, row, text) {
    if (documentIdentity === row.id && documentText === text && documentSession) return;
    destroyDocument();
    const body = document.createElement('div');
    body.className = 'library-preview-body';
    host.appendChild(body);
    try {
      if (!window.OraDocumentSurface) throw new Error('The local document bundle is unavailable.');
      documentSession = window.OraDocumentSurface.renderRead({
        host: body, markdown: text, ariaLabel: `Read ${row.title}`,
      });
    } catch (error) {
      body.classList.add('ora-document-read--unavailable');
      const diagnostic = document.createElement('p');
      diagnostic.textContent = 'Rendered Read is unavailable. Showing the complete literal text; Edit is unavailable.';
      diagnostic.setAttribute('role', 'status');
      const literal = document.createElement('pre');
      literal.className = 'ora-document-literal';
      literal.textContent = text;
      body.replaceChildren(diagnostic, literal);
      documentSession = { destroy() { body.remove(); } };
      console.error('Library document surface unavailable:', error);
    }
    documentIdentity = row.id;
    documentText = text;
  }

  function documentEditingAvailable() {
    return Boolean(window.OraDocumentSurface && previewSlots
      && !previewSlots.document.querySelector('.ora-document-read--unavailable'));
  }

  function renderMarkdownDocument(row, previewText) {
    const host = previewSlots.document;
    const edit = state.edit.id === row.id ? state.edit : null;
    if (edit && edit.digest && !editorSession) {
      destroyDocument();
      try {
        editorSession = window.OraDocumentSurface.createEditor({
          host, text: edit.text, ariaLabel: `Edit complete Markdown for ${row.title}`,
          onChange(text) { if (edit === state.edit) edit.text = text; },
        });
        documentSession = editorSession;
        documentIdentity = row.id;
        host.dataset.libraryEditDraft = '';
        editorSession.focus();
      } catch (error) {
        edit.digest = '';
        edit.error = `Edit is unavailable. ${error.message || error}`;
      }
    }
    const active = Boolean(edit && edit.digest && editorSession);
    if (active) editorSession.setDisabled(edit.busy);
    else if (previewText !== null) showRead(host, row, previewText);
    else destroyDocument();

    if (active) {
      let saveButton = previewSlots.controls.querySelector('[data-library-edit="save"]');
      if (!saveButton) {
        const controls = document.createElement('div');
        controls.className = 'library-edit-controls';
        ['Save', 'Cancel'].forEach((label) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.dataset.libraryEdit = label.toLowerCase();
          button.textContent = label;
          button.addEventListener('click', () => {
            if (label === 'Save') saveMarkdownEdit(row);
            else {
              resetEdit();
              fetchPreview(row);
              renderPreview();
            }
          });
          controls.appendChild(button);
        });
        previewSlots.controls.replaceChildren(controls);
        saveButton = controls.querySelector('[data-library-edit="save"]');
      }
      // Keep both controls mounted and Save focusable while its busy guard
      // rejects repeat activation. Native disabled can blur the focused button.
      saveButton.textContent = edit.busy ? 'Saving…' : 'Save';
      saveButton.setAttribute('aria-disabled', String(edit.busy));
      return;
    }

    previewSlots.controls.replaceChildren();
    if (previewText !== null && markdownEditEligible(row)) {
      const controls = document.createElement('div');
      controls.className = 'library-edit-controls';
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.libraryEdit = 'start';
      button.textContent = edit && edit.busy ? 'Opening editor…' : 'Edit';
      button.disabled = Boolean(edit && edit.busy) || !documentEditingAvailable();
      if (!documentEditingAvailable()) button.title = 'The local Markdown document surface is unavailable.';
      button.addEventListener('click', () => startMarkdownEdit(row));
      controls.appendChild(button);
      previewSlots.controls.appendChild(controls);
      if (!documentEditingAvailable()) {
        const unavailable = document.createElement('p');
        unavailable.textContent = 'Edit is unavailable because the local document surface could not render this document.';
        previewSlots.controls.appendChild(unavailable);
      }
    } else {
      const reason = document.createElement('p');
      reason.textContent = row.source === 'dialogues' ? 'Dialogues are read-only.'
        : `Edit unavailable. ${(row.editability && row.editability.reason) || 'This source does not grant Markdown write authority.'}`;
      previewSlots.controls.appendChild(reason);
    }
  }

  function renderDialogueDocument(row, turns) {
    const signature = JSON.stringify(turns);
    if (documentIdentity === row.id && documentText === signature && documentSession) return;
    destroyDocument();
    if (!turns) return;
    const sessions = [];
    const withinBound = new TextEncoder().encode(turns.map((turn) => turn.content).join('')).length <= 4 * 1024 * 1024;
    turns.forEach((turn) => {
      const section = document.createElement('section'); section.className = 'library-dialogue-turn';
      const label = document.createElement('h3'); label.dataset.librarySpeaker = turn.role;
      label.textContent = turn.role === 'user' ? 'You' : 'Ora';
      const body = document.createElement('div'); section.append(label, body);
      previewSlots.document.appendChild(section);
      try {
        if (!withinBound || !window.OraDocumentSurface) throw new Error('Safe labelled literal reading is being used.');
        sessions.push(window.OraDocumentSurface.renderRead({ host: body, markdown: turn.content,
          ariaLabel: `${label.textContent} — read-only Dialogue turn` }));
      } catch (error) {
        const literal = document.createElement('pre'); literal.className = 'ora-document-literal'; literal.textContent = turn.content;
        body.replaceChildren(literal);
        const notice = document.createElement('p'); notice.textContent = 'Rendered reading unavailable; source text is shown literally below its fixed speaker label.';
        body.prepend(notice);
      }
    });
    documentSession = { destroy() { sessions.forEach((session) => session.destroy()); } };
    documentIdentity = row.id; documentText = signature;
  }

  function appendEditStatus(host, row) {
    const edit = state.edit.id === row.id ? state.edit : null;
    const message = (edit && edit.error) || state.edit.notice;
    if (message) {
      const editStatus = document.createElement('p');
      editStatus.dataset.libraryEditStatus = '';
      editStatus.className = edit && edit.error ? 'is-error' : 'is-success';
      editStatus.textContent = message;
      host.appendChild(editStatus);
    }
  }

  function renderPreview() {
    if (!state.open) return;
    ensurePreviewLayers();
    if (!previewTextLayer || !previewVisualLayer) return;
    previewSlots.metadata.replaceChildren();
    previewSlots.status.replaceChildren();
    previewSlots.relationships.replaceChildren();
    previewVisualLayer.replaceChildren();
    const row = pinnedRow();
    if (!row) {
      destroyDocument();
      previewSlots.controls.replaceChildren();
      previewSlots.metadata.textContent = 'Pin a Library item to inspect its metadata and relationships without replacing the active Dialogue.';
      previewVisualLayer.textContent = 'No Library item is pinned.';
      return;
    }

    const heading = document.createElement('h2');
    heading.textContent = row.title;
    const badges = document.createElement('p');
    badges.className = 'library-preview-badges';
    badges.append(sourceBadge(row), document.createTextNode(` ${metadataLine(row)}`));
    const previewMessage = document.createElement('p');
    const currentPreview = state.resolvedPreview.id === row.id
      ? state.resolvedPreview
      : null;
    let previewBody = null;
    if (!row.preview.available) {
      previewMessage.textContent = row.source === 'dialogues'
        ? `This Dialogue is intentionally metadata-only and cannot be read here. ${row.preview.reason || ''}`.trim()
        : `Preview unavailable. ${row.preview.reason || ''}`.trim();
    } else if (currentPreview && currentPreview.loading) {
      previewMessage.textContent = row.preview.kind === 'visual'
        ? 'Loading the current image into Exhibits…'
        : 'Loading the current text body…';
    } else if (currentPreview && currentPreview.error) {
      previewMessage.textContent = `Preview unavailable. ${currentPreview.error}`;
    } else if (row.source === 'dialogues' && currentPreview && currentPreview.turns) {
      previewMessage.textContent = `Read-only Dialogue; the active Dialogue and draft have not changed.${currentPreview.incomplete ? ' Some indexed exchanges are unavailable.' : ''}`;
    } else if (currentPreview && typeof currentPreview.text === 'string') {
      previewMessage.textContent = state.edit.id === row.id && state.edit.digest
        ? 'Edit complete Markdown'
        : 'Text preview';
      previewBody = currentPreview.text;
    } else if (currentPreview && currentPreview.imageSrc) {
      previewMessage.textContent = 'Current image preview shown in Exhibits. Metadata and relationships remain in Findings.';
    } else {
      previewMessage.textContent = 'Preview unavailable. The current content has not been loaded.';
    }
    previewSlots.metadata.append(heading, badges, previewMessage);
    if (row.source === 'dialogues') {
      renderDialogueDocument(row, currentPreview && currentPreview.turns);
      previewSlots.controls.textContent = 'Dialogues are read-only. Continue deliberately opens a retained Dialogue.';
    } else renderMarkdownDocument(row, previewBody);
    if (row.source === 'engrams') {
      const provenance = document.createElement('p');
      const sources = (row.provenance && row.provenance.sources) || [];
      provenance.textContent = sources.length ? `Extracted from: ${sources.map((source) => source.title).join('; ')}.` : 'Extraction source is unresolved; no source is guessed.';
      if (row.provenance && row.provenance.reason) provenance.textContent += ' ' + row.provenance.reason;
      previewSlots.metadata.appendChild(provenance);
    }
    appendEditStatus(previewSlots.status, row);
    appendRelationshipDisclosure(previewSlots.relationships, row);

    const visualHeading = document.createElement('h2');
    visualHeading.textContent = 'Exhibits preview';
    const visualMessage = document.createElement('p');
    let previewImage = null;
    if (row.preview.kind === 'visual' && currentPreview && currentPreview.loading) {
      visualMessage.textContent = 'Loading the current image…';
    } else if (row.preview.kind === 'visual' && currentPreview && currentPreview.error) {
      visualMessage.textContent = `Image preview unavailable. ${currentPreview.error}`;
    } else if (row.preview.kind === 'visual' && currentPreview && currentPreview.imageSrc) {
      visualMessage.textContent = 'Current project image';
      previewImage = document.createElement('img');
      previewImage.className = 'library-preview-image';
      previewImage.alt = row.title;
      const imageGeneration = state.previewGeneration;
      previewImage.addEventListener('error', () => {
        if (imageGeneration !== state.previewGeneration || state.pinnedId !== row.id) return;
        state.resolvedPreview.imageSrc = '';
        state.resolvedPreview.error = 'The browser could not decode the current image.';
        renderPreview();
      }, { once: true });
      previewImage.src = currentPreview.imageSrc;
    } else if (row.preview.kind === 'visual' || row.preview.kind === 'mixed') {
      visualMessage.textContent = 'Visual preview is unavailable after current authority, type, and size validation.';
    } else if (row.preview.kind === 'unsupported') {
      visualMessage.textContent = row.preview.reason || 'This item has no supported visual preview.';
    } else {
      visualMessage.textContent = 'This is a text-oriented item; its metadata and relationship disclosure are shown in Findings.';
    }
    previewVisualLayer.append(visualHeading, visualMessage);
    if (previewImage) previewVisualLayer.appendChild(previewImage);
  }

  function dialogueId(row) {
    if (!row || row.source !== 'dialogues' || !row.preview.available || row.metadata.lifecycle === 'indexed_archive') return '';
    return String((row.preview.locator && row.preview.locator.dialogue_id) || '');
  }

  function builtinActions(row) {
    const actions = [];
    if (row) actions.push({ id: 'related', label: 'Show relationships', run: activatePinned });
    if (row && ['dialogues', 'files'].includes(row.source) && row.preview.available) actions.push({
      id: 'derived', label: 'Show derived Engrams', run: () => open({ sources: ['engrams'], provenanceId: row.id, projectId: state.projectId }),
    });
    if (row && row.source === 'engrams') actions.push({ id: 'trace', label: 'Trace from this Engram', run: () => {
      state.traceId = row.id; state.traceLimit = 50; state.trace = null; clearScene(); fetchPage({ append: false });
    } });
    if (state.traceId) actions.push({ id: 'browse', label: 'Return to Browse', run: () => {
      state.traceId = null; state.trace = null; clearScene(); fetchPage({ append: false });
    } });
    const fileLocator = row && row.source === 'files' && row.preview && row.preview.locator;
    const obsidianUri = fileLocator && typeof fileLocator.obsidian_uri === 'string'
      && fileLocator.obsidian_uri.trim() ? fileLocator.obsidian_uri : '';
    if (obsidianUri) {
      actions.push({
        id: 'open-obsidian',
        label: 'Open in Obsidian',
        run: () => {
          const anchor = document.createElement('a');
          anchor.href = obsidianUri;
          anchor.click();
        },
      });
    }
    const revealPath = fileLocator && typeof fileLocator.path === 'string'
      && fileLocator.path.trim() ? fileLocator.path : '';
    if (revealPath) {
      actions.push({
        id: 'reveal',
        label: 'Reveal in Finder',
        run: async () => {
          const response = await fetch('/api/fs/reveal', {
            method: 'POST',
            headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: revealPath }),
          });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok || payload.ok !== true) {
            throw new Error(payload.error || `Reveal request failed (HTTP ${response.status})`);
          }
          state.actionNotice = '';
          setNotice('Revealed in Finder.', 'success');
        },
      });
    }
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
    options = options || {};
    const project = options.projectId === undefined ? state.projectId : String(options.projectId).trim().toLowerCase();
    const sources = options.sources === undefined ? Array.from(state.sources) : options.sources;
    const provenance = options.provenanceId;
    const cleanBrowse = options.cleanBrowse === true;
    if (!/^[a-z0-9][a-z0-9_-]*$/.test(project) || !Array.isArray(sources)
        || sources.some((source) => !SOURCES.includes(source))
        || (options.cleanBrowse !== undefined && typeof options.cleanBrowse !== 'boolean')
        || (cleanBrowse && provenance !== undefined)
        || (provenance !== undefined && (typeof provenance !== 'string' || !/^(dialogues|files):[A-Za-z0-9_-]+$/.test(provenance)))) {
      throw new Error('Library entry requires a valid project, source list and admitted-source identity.');
    }
    const changed = cleanBrowse || project !== state.projectId || sources.join(',') !== Array.from(state.sources).join(',')
      || (provenance !== undefined && provenance !== state.filters.provenance_id);
    if (changed) {
      state.projectId = project; state.sources = new Set(sources);
      if (cleanBrowse) {
        // Criteria input is synchronous: no deferred search can reapply an old scope.
        state.filters = { type: '' }; state.query = ''; searchInput.value = '';
        state.showArchived = false;
        state.refinementStatus = {}; state.progress = { final: true };
        if (state.group === 'provenance' && !state.sources.has('engrams')) state.group = 'none';
        resetResolvedPreview(null);
        destroyDocument();
        closePopovers();
      } else if (provenance !== undefined) {
        state.filters = { type: '', provenance_id: provenance }; state.query = ''; searchInput.value = ''; state.group = 'provenance';
      }
      mount.querySelectorAll('[data-library-source]').forEach((checkbox) => { checkbox.checked = state.sources.has(checkbox.value); });
      mount.querySelectorAll('[data-library-refinement]').forEach((control) => { control.value = state.filters[control.dataset.libraryRefinement] || ''; });
      typeFilter.value = state.filters.type || '';
      mount.querySelector('[data-library-archived]').checked = state.showArchived;
      sourceCount.textContent = String(state.sources.size);
      syncGroupAvailability();
      invalidateProjectScopeRows();
    }
    if (state.open) {
      if (options.returnFocus) returnFocus = options.returnFocus;
      if (changed) fetchPage({ append: false });
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
    resetResolvedPreview(null);
    resetEdit();
    destroyDocument();
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
    previewSlots = null;
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
      try { localStorage.setItem(VIEW_STORAGE_KEY, state.view); state.storageNotice = ''; }
      catch (error) { state.storageNotice = 'This view works now, but saved view storage is unavailable.'; }
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
      changeCriteria();
      searchInput.focus();
    } else if (command.dataset.libraryCommand === 'clear-filters') {
      state.filters = { type: '' };
      typeFilter.value = '';
      mount.querySelectorAll('[data-library-refinement]').forEach((control) => { control.value = ''; });
      changeCriteria();
    } else if (command.dataset.libraryCommand === 'load-more') fetchPage({ append: true });
    else if (command.dataset.libraryCommand === 'load-all') loadAll();
    else if (command.dataset.libraryCommand === 'retry') fetchPage({ append: state.retryAppend });
  });

  searchInput.addEventListener('input', () => {
    state.query = searchInput.value;
    changeCriteria();
  });

  mount.querySelectorAll('[data-library-source]').forEach((checkbox) => {
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) state.sources.add(checkbox.value);
      else state.sources.delete(checkbox.value);
      invalidateProjectScopeRows();
      const pin = pinnedRow();
      if (pin && !state.sources.has(pin.source)) {
        resetEdit();
        state.pinnedId = null;
        resetResolvedPreview(null);
        resetRelated(null);
        renderPreview();
        renderActions();
        updateLogo();
      }
      syncGroupAvailability();
      sourceCount.textContent = String(state.sources.size);
      closePopover('sources');
      fetchPage({ append: false });
    });
  });

  groupSelect.addEventListener('change', (event) => {
    state.group = event.target.value;
    clearScene();
    syncGroupAvailability();
    render();
  });
  mount.querySelector('[data-library-sort]').addEventListener('change', (event) => {
    state.sort = event.target.value;
    render();
  });
  typeFilter.addEventListener('change', () => {
    state.filters.type = typeFilter.value;
    changeCriteria();
  });
  mount.querySelectorAll('[data-library-refinement]').forEach((control) => control.addEventListener('change', () => {
    state.filters[control.dataset.libraryRefinement] = control.value;
    changeCriteria();
  }));
  mount.querySelector('[data-library-archived]').addEventListener('change', (event) => {
    state.showArchived = event.target.checked; changeCriteria();
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
    const overview = document.getElementById('overviewDesktop');
    if (overview && !overview.hidden) return;
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
      traceId: state.traceId,
      traceLimit: state.traceLimit,
      showArchived: state.showArchived,
      progressFinal: state.progress.final,
    }),
  };
})();
