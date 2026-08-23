/* V3 Exhibits editor controller.
 *
 * Excalidraw is an isolated React island mounted over the existing Konva
 * VisualPanel.  Konva remains alive for legacy .ora-canvas files and is the
 * explicit fallback editor.  Native objects never cross the editor boundary:
 * a switch carries only the canonical flattened PNG.
 */
(() => {
  'use strict';

  const WHITE = '#ffffff';
  const EXCALIDRAW_UI_BACKGROUND = 'transparent';
  const PADDING = 16;
  const MAX_SIDE = 4096;
  const DRAFT_DELAY_MS = 700;

  const clone = (value) => {
    if (typeof structuredClone === 'function') return structuredClone(value);
    return JSON.parse(JSON.stringify(value));
  };

  const blobFromDataURL = async (dataURL) => {
    const response = await fetch(dataURL);
    return response.blob();
  };

  const blobFromCanvasImage = (canvasObject) => {
    const imageData = canvasObject && canvasObject.image_data;
    if (!imageData || typeof imageData.data !== 'string' || !imageData.data) {
      throw new Error('Image capability result has no raster bytes');
    }
    const mimeType = imageData.mime_type || imageData.mimeType || 'image/png';
    const source = imageData.data.startsWith('data:')
      ? imageData.data
      : `data:${mimeType};base64,${imageData.data}`;
    return blobFromDataURL(source);
  };

  const blobToDataURL = (blob) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error || new Error('Could not read visual PNG'));
    reader.readAsDataURL(blob);
  });

  const imageFromSource = (source) => new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error('Could not decode visual raster'));
    image.src = source;
  });

  const normalizeLegacyWhiteHandoff = async (scene) => {
    const elements = Array.isArray(scene && scene.elements)
      ? scene.elements.filter((element) => element && !element.isDeleted) : [];
    if (elements.length !== 1) return scene;
    const [element] = elements;
    if (element.type !== 'image' || element.locked !== true
        || element.customData != null
        || typeof element.fileId !== 'string'
        || !element.fileId.startsWith('ora-image-')) return scene;
    const file = scene.files && scene.files[element.fileId];
    if (!file || file.id !== element.fileId || file.mimeType !== 'image/png'
        || typeof file.dataURL !== 'string'
        || !file.dataURL.startsWith('data:image/png;base64,')) return scene;
    try {
      const image = await imageFromSource(file.dataURL);
      const width = image.naturalWidth || image.width;
      const height = image.naturalHeight || image.height;
      if (!(width > 0) || !(height > 0)) return scene;
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      if (!context || typeof context.getImageData !== 'function') return scene;
      context.drawImage(image, 0, 0);
      const rgba = context.getImageData(0, 0, width, height).data;
      if (rgba.length !== width * height * 4) return scene;
      for (let index = 0; index < rgba.length; index += 1) {
        if (rgba[index] !== 255) return scene;
      }
      return Object.assign({}, scene, { elements: [], files: {} });
    } catch (_) {
      return scene;
    }
  };

  const canvasBlob = (canvas) => new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => blob ? resolve(blob) : reject(new Error('Could not encode canonical PNG')),
      'image/png'
    );
  });

  const normalizeImageToPng = async (file) => {
    if (file && file.type === 'image/png') return file;
    const source = URL.createObjectURL(file);
    try {
      const image = await imageFromSource(source);
      const naturalWidth = image.naturalWidth || image.width || 1;
      const naturalHeight = image.naturalHeight || image.height || 1;
      const scale = Math.min(1, MAX_SIDE / Math.max(naturalWidth, naturalHeight));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(naturalWidth * scale));
      canvas.height = Math.max(1, Math.round(naturalHeight * scale));
      canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
      return canvasBlob(canvas);
    } finally {
      URL.revokeObjectURL(source);
    }
  };

  const equalBlobs = async (left, right) => {
    if (!left || !right || left.size !== right.size) return false;
    const [a, b] = await Promise.all([left.arrayBuffer(), right.arrayBuffer()]);
    const aa = new Uint8Array(a);
    const bb = new Uint8Array(b);
    for (let i = 0; i < aa.length; i += 1) if (aa[i] !== bb[i]) return false;
    return true;
  };

  const responseError = async (response, fallback) => {
    let detail = '';
    let payload = null;
    try {
      const body = String(await response.text()).trim();
      try { payload = JSON.parse(body); } catch (_) { detail = body; }
    } catch (_) {
      try { payload = await response.json(); } catch (_) { payload = null; }
    }
    if (payload && typeof payload === 'object') {
      detail = [payload.error, payload.message]
        .filter((value, index, values) => (
          typeof value === 'string' && value && values.indexOf(value) === index
        ))
        .join(': ');
    }
    const status = response && response.status ? ` (${response.status})` : '';
    return new Error(`${fallback}${status}${detail ? `: ${detail}` : ''}`);
  };

  const rasterizeSvg = async (svg) => {
    const source = new Blob([svg], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(source);
    try {
      const image = await imageFromSource(url);
      const naturalWidth = image.naturalWidth || image.width || 1;
      const naturalHeight = image.naturalHeight || image.height || 1;
      const scale = Math.min(1, MAX_SIDE / Math.max(
        naturalWidth + PADDING * 2,
        naturalHeight + PADDING * 2
      ));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round((naturalWidth + PADDING * 2) * scale));
      canvas.height = Math.max(1, Math.round((naturalHeight + PADDING * 2) * scale));
      const context = canvas.getContext('2d');
      context.fillStyle = WHITE;
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(
        image,
        Math.round(PADDING * scale),
        Math.round(PADDING * scale),
        Math.round(naturalWidth * scale),
        Math.round(naturalHeight * scale)
      );
      return canvasBlob(canvas);
    } finally {
      URL.revokeObjectURL(url);
    }
  };

  const captureKonvaRaster = (panel, state) => {
    const stage = panel.stage;
    const saveCanvas = window.OraSaveCanvas;
    let extent = saveCanvas && typeof saveCanvas.computeContentExtent === 'function'
      ? saveCanvas.computeContentExtent(state, 0)
      : null;
    if (!extent || !(extent.width > 0) || !(extent.height > 0)) {
      extent = { x: 0, y: 0, width: 1, height: 1 };
    }
    const priorPosition = typeof stage.position === 'function'
      ? stage.position() : { x: 0, y: 0 };
    const priorScale = typeof stage.scale === 'function'
      ? stage.scale() : { x: 1, y: 1 };
    const selection = panel.selectionLayer;
    const selectionVisible = selection && typeof selection.visible === 'function'
      ? selection.visible() : null;
    let stageDataURL;
    try {
      if (selection && typeof selection.visible === 'function') selection.visible(false);
      if (typeof stage.position === 'function') stage.position({ x: 0, y: 0 });
      if (typeof stage.scale === 'function') stage.scale({ x: 1, y: 1 });
      if (typeof stage.batchDraw === 'function') stage.batchDraw();
      stageDataURL = stage.toDataURL({
        mimeType: 'image/png', pixelRatio: 1,
        x: extent.x, y: extent.y, width: extent.width, height: extent.height,
      });
    } finally {
      if (typeof stage.position === 'function') stage.position(priorPosition);
      if (typeof stage.scale === 'function') stage.scale(priorScale);
      if (selection && typeof selection.visible === 'function'
          && selectionVisible !== null) selection.visible(selectionVisible);
      if (typeof stage.batchDraw === 'function') stage.batchDraw();
    }
    const svgObject = (state.objects || []).find((object) => object && object.id === 'bg-svg');
    return {
      stageDataURL,
      extent,
      svgBounds: svgObject ? {
        x: Number.isFinite(svgObject.x) ? svgObject.x : 0,
        y: Number.isFinite(svgObject.y) ? svgObject.y : 0,
        width: Number.isFinite(svgObject.width) ? svgObject.width : null,
        height: Number.isFinite(svgObject.height) ? svgObject.height : null,
      } : null,
    };
  };

  const canonicalizeKonva = async (snapshot) => {
    const stageImage = await imageFromSource(snapshot.stageDataURL);
    const sourceWidth = snapshot.extent.width || stageImage.naturalWidth || 1;
    const sourceHeight = snapshot.extent.height || stageImage.naturalHeight || 1;
    const scale = Math.min(1, MAX_SIDE / Math.max(
      sourceWidth + PADDING * 2,
      sourceHeight + PADDING * 2
    ));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round((sourceWidth + PADDING * 2) * scale));
    canvas.height = Math.max(1, Math.round((sourceHeight + PADDING * 2) * scale));
    const context = canvas.getContext('2d');
    context.fillStyle = WHITE;
    context.fillRect(0, 0, canvas.width, canvas.height);
    const x = Math.round(PADDING * scale);
    const y = Math.round(PADDING * scale);
    const width = Math.round(sourceWidth * scale);
    const height = Math.round(sourceHeight * scale);
    context.drawImage(stageImage, x, y, width, height);
    if (snapshot.svg) {
      const svgURL = URL.createObjectURL(new Blob([snapshot.svg], { type: 'image/svg+xml' }));
      try {
        const svgImage = await imageFromSource(svgURL);
        const bounds = snapshot.svgBounds || {};
        const svgWidth = bounds.width || svgImage.naturalWidth || sourceWidth;
        const svgHeight = bounds.height || svgImage.naturalHeight || sourceHeight;
        context.drawImage(
          svgImage,
          Math.round(((bounds.x || 0) - snapshot.extent.x + PADDING) * scale),
          Math.round(((bounds.y || 0) - snapshot.extent.y + PADDING) * scale),
          Math.round(svgWidth * scale),
          Math.round(svgHeight * scale)
        );
      } finally {
        URL.revokeObjectURL(svgURL);
      }
    }
    return canvasBlob(canvas);
  };

  const mount = () => {
    const right = document.querySelector('.right-pane');
    if (!right) return;
    right.classList.add('visual-panel', 'ora-visual-editor-host');

    const toolbarHost = document.getElementById('visualToolbarHost');
    const visualShell = right.closest('.visual-pane-shell');
    const importButton = document.getElementById('visualImportImage');
    const importInput = document.getElementById('visualImportImageFile');
    const exportButton = document.getElementById('visualExportButton');
    const exportMenu = document.getElementById('visualExportMenu');
    const exportMenuPopup = document.getElementById('visualExportMenuPopup');
    const exportMenuItems = exportMenuPopup
      ? Array.from(exportMenuPopup.querySelectorAll('[data-export-format]')) : [];
    const zoomControls = Array.from(document.querySelectorAll('[data-visual-zoom]'));
    const zoomValue = document.getElementById('visualZoomValue');
    const footer = document.getElementById('visualPaneFooter');
    const footerStatus = document.getElementById('visualPaneFooterStatus');

    let panel = null;
    try {
      if (typeof Konva !== 'undefined' && typeof VisualPanel !== 'undefined') {
        panel = new VisualPanel(right, { id: 'v3-canvas', toolbarHost });
        panel.init();
        panel.saveCanvas = () => {
          if (!window.OraSaveCanvas || typeof window.OraSaveCanvas.saveImmediate !== 'function') {
            return Promise.reject(new Error('Canvas save is unavailable'));
          }
          return window.OraSaveCanvas.saveImmediate(panel, 'manual');
        };
      }
    } catch (error) {
      console.warn('[v3-canvas-mount] Konva fallback failed:', error);
    }

    const host = document.createElement('div');
    host.className = 'ora-excalidraw-island';
    host.setAttribute('aria-label', 'Excalidraw editor');
    right.appendChild(host);

    let toggle = document.getElementById('visualEditorSwitch');
    if (!toggle) {
      toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'ora-visual-editor-toggle';
      right.appendChild(toggle);
    }

    let editor = 'excalidraw';
    let excalidrawApi = null;
    let islandRoot = null;
    let conversationId = 'main';
    let conversationTag = '';
    let visualState = null;
    let draftTimer = null;
    let draftDirty = false;
    let draftOwnerId = conversationId;
    let draftOwnerTag = conversationTag;
    let draftRevision = 0;
    let applyingScene = 0;
    let viewIsCurrent = true;
    let pendingKonvaEditabilityWarning = false;
    // Excalidraw reports an initial empty onChange while mounting. Until an
    // explicit load/clear establishes the active Dialogue's scene, that event
    // must never become a recoverable draft for the default/next identity.
    let sceneReady = false;
    let operations = Promise.resolve();

    const syncExcalidrawGrid = (appState) => {
      if (!appState) return;
      const rawZoom = typeof appState.zoom === 'number'
        ? appState.zoom : appState.zoom && appState.zoom.value;
      const zoom = Number.isFinite(Number(rawZoom)) && Number(rawZoom) > 0
        ? Number(rawZoom) : 1;
      const baseSize = parseFloat(
        getComputedStyle(host).getPropertyValue('--size-4-6')
      ) || 24;
      const size = baseSize * zoom;
      const scrollX = Number.isFinite(Number(appState.scrollX)) ? Number(appState.scrollX) : 0;
      const scrollY = Number.isFinite(Number(appState.scrollY)) ? Number(appState.scrollY) : 0;
      host.style.setProperty('--ora-excal-grid-size', `${size}px`);
      host.style.setProperty(
        '--ora-excal-grid-x', `${size / 2 + scrollX * zoom}px`
      );
      host.style.setProperty(
        '--ora-excal-grid-y', `${size / 2 + scrollY * zoom}px`
      );
      if (zoomValue) zoomValue.textContent = `${Math.round(zoom * 100)}%`;
    };

    const normalizedZoom = (value) => Math.min(
      30, Math.max(0.1, Math.round(value * 1000000) / 1000000)
    );

    const updateExcalidrawZoom = (nextValue, viewportX, viewportY) => {
      if (!excalidrawApi) return;
      const appState = excalidrawApi.getAppState();
      const rawZoom = typeof appState.zoom === 'number'
        ? appState.zoom : appState.zoom && appState.zoom.value;
      const currentZoom = Number(rawZoom) || 1;
      const nextZoom = normalizedZoom(nextValue);
      if (nextZoom === currentZoom) return;
      const appLayerX = viewportX - (Number(appState.offsetLeft) || 0);
      const appLayerY = viewportY - (Number(appState.offsetTop) || 0);
      excalidrawApi.updateScene({
        appState: {
          zoom: { value: nextZoom },
          scrollX: (Number(appState.scrollX) || 0)
            + appLayerX / nextZoom - appLayerX / currentZoom,
          scrollY: (Number(appState.scrollY) || 0)
            + appLayerY / nextZoom - appLayerY / currentZoom,
        },
      });
      syncExcalidrawGrid(excalidrawApi.getAppState());
    };

    const zoomAtCanvasCenter = (nextValue) => {
      const bounds = host.getBoundingClientRect();
      updateExcalidrawZoom(
        nextValue,
        bounds.left + bounds.width / 2,
        bounds.top + bounds.height / 2
      );
    };

    host.addEventListener('wheel', (event) => {
      const surface = event.target && event.target.closest
        ? event.target.closest('.excalidraw__canvas-wrapper, canvas.excalidraw__canvas')
        : null;
      if (editor !== 'excalidraw' || !excalidrawApi || !surface
          || !host.contains(surface)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const rawDelta = Number(event.deltaY) || 0;
      if (!rawDelta) return;
      const appState = excalidrawApi.getAppState();
      const rawZoom = typeof appState.zoom === 'number'
        ? appState.zoom : appState.zoom && appState.zoom.value;
      const currentZoom = Number(rawZoom) || 1;
      const deltaUnit = event.deltaMode === 1 ? 16
        : event.deltaMode === 2 ? Math.max(1, host.clientHeight) : 1;
      const delta = Math.max(-100, Math.min(100, rawDelta * deltaUnit));
      const nextZoom = currentZoom * Math.exp(-delta * 0.002);
      updateExcalidrawZoom(nextZoom, event.clientX, event.clientY);
    }, { capture: true, passive: false });

    zoomControls.forEach((button) => button.addEventListener('click', () => {
      if (!excalidrawApi) return;
      const appState = excalidrawApi.getAppState();
      const rawZoom = typeof appState.zoom === 'number'
        ? appState.zoom : appState.zoom && appState.zoom.value;
      const currentZoom = Number(rawZoom) || 1;
      const action = button.dataset.visualZoom;
      zoomAtCanvasCenter(action === 'reset'
        ? 1 : currentZoom + (action === 'in' ? 0.1 : -0.1));
    }));

    if (window.OraCanvasShareReminder
        && typeof window.OraCanvasShareReminder.init === 'function') {
      window.OraCanvasShareReminder.init();
    }

    const enqueue = (operation) => {
      const run = operations.then(operation, operation);
      operations = run.catch(() => {});
      return run;
    };

    const updateEditorPresentation = () => {
      const useExcalidraw = editor === 'excalidraw' && !!excalidrawApi;
      right.classList.toggle('ora-editor-excalidraw', useExcalidraw);
      right.classList.toggle('ora-editor-konva', !useExcalidraw);
      host.hidden = !useExcalidraw;
      toggle.title = useExcalidraw
        ? 'Excalidraw — switch to Konva'
        : 'Konva — switch to Excalidraw';
      toggle.setAttribute(
        'aria-label',
        useExcalidraw ? 'Visual editor: Excalidraw. Switch to Konva'
          : 'Visual editor: Konva. Switch to Excalidraw'
      );
      toggle.setAttribute('data-active-editor', useExcalidraw ? 'excalidraw' : 'konva');
      if (toolbarHost) toolbarHost.hidden = useExcalidraw;
      if (visualShell) visualShell.dataset.activeEditor = useExcalidraw ? 'excalidraw' : 'konva';
      document.dispatchEvent(new CustomEvent('ora:visual-editor-changed', {
        detail: { active_editor: useExcalidraw ? 'excalidraw' : 'konva' },
      }));
    };

    const setEditor = (next) => {
      editor = next === 'konva' ? 'konva' : 'excalidraw';
      updateEditorPresentation();
    };

    const commitTextEditing = () => {
      if (!excalidrawApi) return;
      const active = document.activeElement;
      if (active && host.contains(active)
          && (active.matches('textarea, input, [contenteditable="true"]')
              || active.closest('.excalidraw-wysiwyg'))) {
        active.blur();
      }
    };

    const snapshotExcalidraw = () => {
      if (!excalidrawApi) throw new Error('Excalidraw is not ready');
      commitTextEditing();
      return Object.freeze({
        editor: 'excalidraw',
        conversationId,
        conversationTag,
        elements: clone(excalidrawApi.getSceneElements()),
        appState: clone(excalidrawApi.getAppState()),
        files: clone(excalidrawApi.getFiles()),
      });
    };

    const snapshotKonva = () => {
      if (!panel || !panel.stage || !window.OraSaveCanvas) {
        throw new Error('Konva is not ready');
      }
      const state = clone(window.OraSaveCanvas.buildCanvasState(panel));
      const spatial = window.OraCanvasSerializer
        && typeof window.OraCanvasSerializer.captureFromPanel === 'function'
        ? clone(window.OraCanvasSerializer.captureFromPanel(panel))
        : null;
      const svg = panel._svgHost && panel._svgHost.querySelector('svg');
      const raster = captureKonvaRaster(panel, state);
      return Object.freeze({
        editor: 'konva',
        conversationId,
        conversationTag,
        state,
        spatial,
        svg: svg ? svg.outerHTML : '',
        stageDataURL: raster.stageDataURL,
        extent: raster.extent,
        svgBounds: raster.svgBounds,
      });
    };

    const snapshotActive = () => editor === 'excalidraw'
      ? snapshotExcalidraw()
      : snapshotKonva();

    const materialize = async (snapshot) => {
      const owner = {
        conversationId: snapshot.conversationId || conversationId || 'main',
        conversationTag: snapshot.conversationTag || conversationTag || '',
      };
      if (snapshot.editor === 'excalidraw') {
        const native = window.OraExcalidrawIsland.serialize(snapshot);
        const preview = await window.OraExcalidrawIsland.canonicalPng(snapshot);
        return Object.assign(owner, {
          editor: 'excalidraw', native, preview, spatial: null,
        });
      }
      const bounded = window.OraSaveCanvas.boundStateToContent(clone(snapshot.state), 100);
      const [bytes, preview] = await Promise.all([
        window.OraCanvasFileFormat.write(bounded.state, { compressed: true }),
        canonicalizeKonva(snapshot),
      ]);
      return Object.assign(owner, {
        editor: 'konva',
        native: new Blob([bytes], { type: 'application/gzip' }),
        preview,
        spatial: snapshot.spatial,
      });
    };

    const postCheckpoint = async (materialized) => {
      const ownerId = materialized.conversationId || conversationId || 'main';
      const body = new FormData();
      body.append('conversation_id', ownerId);
      body.append('tag', materialized.conversationTag || '');
      body.append('editor', materialized.editor);
      body.append('native', materialized.native,
        materialized.editor === 'excalidraw' ? 'scene.excalidraw' : 'scene.ora-canvas');
      body.append('preview', materialized.preview, 'preview.png');
      const response = await fetch('/api/canvas/checkpoint', { method: 'POST', body });
      if (!response.ok) {
        throw await responseError(response, `Checkpoint write failed for ${ownerId}`);
      }
      return response.json();
    };

    const postVisualState = async (
      state, ownerId = conversationId, ownerTag = conversationTag
    ) => {
      const response = await fetch(
        `/api/canvas/visual-state/${encodeURIComponent(ownerId || 'main')}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tag: ownerTag || '', visual_state: state }),
        }
      );
      if (!response.ok) throw new Error(`Visual editor state write failed (${response.status})`);
      if (conversationId === ownerId) visualState = state;
      return response.json();
    };

    const confirmKonvaMutation = () => {
      if (editor !== 'konva' || !pendingKonvaEditabilityWarning) return true;
      const confirmed = typeof window.confirm !== 'function' || window.confirm(
        'This is a flattened Konva copy. Editing it means the next switch to '
        + 'Excalidraw will open a flattened image instead of the original editable '
        + 'objects. The original Excalidraw checkpoint will remain saved. Continue?'
      );
      if (!confirmed) return false;
      pendingKonvaEditabilityWarning = false;
      const nextState = Object.assign({}, visualState || {}, {
        active_editor: 'konva',
        konva_edit_warning_acknowledged: true,
      });
      visualState = nextState;
      enqueue(() => postVisualState(nextState)).catch((error) => {
        console.warn('[visual editor] editability acknowledgement was not persisted:', error);
      });
      return true;
    };

    if (panel && panel.config) panel.config.beforeUserMutation = confirmKonvaMutation;

    const writeCurrentKonva = async (materialized) => {
      const body = new FormData();
      body.append('conversation_id', materialized.conversationId || conversationId || 'main');
      body.append('canvas', materialized.native, 'latest.ora-canvas');
      body.append('preview', await blobToDataURL(materialized.preview));
      body.append('reason', 'editor-switch');
      const response = await fetch('/api/canvas/save', { method: 'POST', body });
      if (!response.ok) throw new Error(`Konva current-state write failed (${response.status})`);
    };

    const writeDraft = async (
      snapshot,
      ownerId = snapshot && snapshot.conversationId || conversationId,
      ownerTag = snapshot && snapshot.conversationTag || conversationTag
    ) => {
      if (!snapshot || snapshot.editor !== 'excalidraw') return;
      const body = new FormData();
      body.append('conversation_id', ownerId || 'main');
      body.append('tag', ownerTag || '');
      body.append('scene', window.OraExcalidrawIsland.serialize(snapshot), 'latest.excalidraw');
      const response = await fetch('/api/canvas/draft', { method: 'POST', body });
      if (!response.ok) throw new Error(`Excalidraw draft write failed (${response.status})`);
    };

    const markDraftDirty = () => {
      draftDirty = true;
      draftOwnerId = conversationId;
      draftOwnerTag = conversationTag;
      draftRevision += 1;
    };

    const scheduleDraft = () => {
      markDraftDirty();
      if (draftTimer) clearTimeout(draftTimer);
      draftTimer = setTimeout(() => {
        draftTimer = null;
        enqueue(flushDraftNow).catch(
          (error) => console.warn('[Excalidraw] draft autosave failed:', error)
        );
      }, DRAFT_DELAY_MS);
    };

    const flushDraftNow = async () => {
      if (draftTimer) {
        clearTimeout(draftTimer);
        draftTimer = null;
      }
      if (!draftDirty || editor !== 'excalidraw' || !excalidrawApi) return;
      const ownerId = draftOwnerId;
      const ownerTag = draftOwnerTag;
      const revision = draftRevision;
      const snapshot = snapshotExcalidraw();
      await writeDraft(snapshot, ownerId, ownerTag);
      if (draftRevision === revision && draftOwnerId === ownerId) {
        draftDirty = false;
      }
    };

    const resetKonvaToPng = async (png, attachPng = true) => {
      if (!panel) throw new Error('Konva fallback is unavailable');
      if (typeof panel.clearArtifact === 'function') panel.clearArtifact();
      if (typeof panel.clearPendingImage === 'function') panel.clearPendingImage();
      if (typeof panel.loadCanvasState === 'function') panel.loadCanvasState({ objects: [] });
      if (!attachPng) return;
      const file = new File([png], 'excalidraw-flattened.png', { type: 'image/png' });
      const attached = await panel.attachImage(file);
      if (!attached) throw new Error('Konva rejected the flattened visual');
    };

    const updateExcalidraw = (scene) => {
      if (!excalidrawApi) throw new Error('Excalidraw is not ready');
      applyingScene += 1;
      try {
        excalidrawApi.resetScene();
        if (scene.files) excalidrawApi.addFiles(Object.values(scene.files));
        excalidrawApi.updateScene({
          elements: scene.elements || [],
          appState: Object.assign({}, scene.appState || {}, {
            theme: 'light', viewBackgroundColor: EXCALIDRAW_UI_BACKGROUND,
            gridModeEnabled: false,
          }),
        });
        excalidrawApi.scrollToContent(scene.elements || [], { fitToContent: true });
        syncExcalidrawGrid(excalidrawApi.getAppState());
        draftDirty = false;
        sceneReady = true;
      } finally {
        // Excalidraw may deliver its onChange callback on a microtask after
        // updateScene. Hold the guard through that callback turn.
        queueMicrotask(() => {
          applyingScene = Math.max(0, applyingScene - 1);
          updateCanvasState();
        });
      }
    };

    const isAssistantArtifact = (element) => {
      const data = element && element.customData;
      return !!data && (
        data.oraAssistantVisualKind === 'artifact'
        || (data.oraAssistantVisualKey && data.oraAssistantVisualKind !== 'annotation')
      );
    };

    const placeExcalidrawPng = async (
      png,
      { action = 'append', locked = true, customData = null, bounds = null } = {}
    ) => {
      const raster = await window.OraExcalidrawIsland.imageBackedScene(
        png, locked, customData
      );
      const current = snapshotExcalidraw();
      let existing = current.elements.filter((element) => !element.isDeleted);
      const assistantArtifacts = existing.filter(isAssistantArtifact);
      const replacedArtifact = assistantArtifacts[assistantArtifacts.length - 1] || null;
      if (action === 'replace') existing = [];
      if (action === 'update') existing = existing.filter(
        (element) => !isAssistantArtifact(element)
      );
      const maxX = existing.reduce(
        (value, element) => Math.max(value, element.x + element.width), 0
      );
      const [image] = raster.elements;
      let placement = {};
      if (action === 'update' && replacedArtifact) {
        placement = {
          x: replacedArtifact.x,
          y: replacedArtifact.y,
          width: replacedArtifact.width,
          height: replacedArtifact.height,
        };
      } else if (action === 'append' && existing.length) {
        placement = { x: maxX + PADDING * 2 };
      } else {
        placement = { x: 0, y: 0 };
      }
      const placed = Object.assign(
        {}, image, placement,
        bounds && bounds.width > 0 ? { width: bounds.width } : null,
        bounds && bounds.height > 0 ? { height: bounds.height } : null
      );
      const files = {};
      existing.forEach((element) => {
        if (element.fileId && current.files[element.fileId]) {
          files[element.fileId] = current.files[element.fileId];
        }
      });
      Object.assign(files, raster.files || {});
      updateExcalidraw({
        elements: [...existing, placed],
        appState: current.appState,
        files,
      });
      return placed;
    };

    const persistExcalidrawMutation = async (persist) => {
      if (!persist) return;
      markDraftDirty();
      await flushDraftNow();
    };

    const fetchCheckpoint = async (
      checkpointId, legacyTurn, previewOnly = false, ownerId = conversationId
    ) => {
      const params = new URLSearchParams();
      if (checkpointId) params.set('checkpoint', checkpointId);
      else if (Number.isInteger(legacyTurn)) params.set('turn', String(legacyTurn));
      if (previewOnly) params.set('preview', '1');
      const response = await fetch(
        `/api/canvas/load/${encodeURIComponent(ownerId)}?${params.toString()}`
      );
      if (!response.ok) return null;
      return {
        blob: await response.blob(),
        editor: response.headers.get('X-Ora-Visual-Editor') || 'konva',
      };
    };

    const fetchDraft = async () => {
      const response = await fetch(
        `/api/canvas/load/${encodeURIComponent(conversationId)}?draft=excalidraw`
      );
      if (!response.ok) return null;
      return { blob: await response.blob(), editor: 'excalidraw' };
    };

    const fetchCurrentKonva = async () => {
      const response = await fetch(
        `/api/canvas/load/${encodeURIComponent(conversationId)}`
      );
      if (!response.ok) return null;
      return {
        blob: await response.blob(),
        editor: response.headers.get('X-Ora-Visual-Editor') || 'konva',
      };
    };

    const recoverExcalidrawInKonva = async (checkpointId) => {
      const recovered = await fetchCheckpoint(checkpointId, null, true);
      if (!recovered) throw new Error('Saved Excalidraw preview is unavailable');
      await resetKonvaToPng(recovered.blob);
      if (!viewIsCurrent) {
        // Historical recovery is display-only. Publishing a baseline or
        // editor authority here would overwrite the current Dialogue state.
        setEditor('konva');
        return;
      }
      const materialized = await materialize(snapshotKonva());
      const baseline = await postCheckpoint(materialized);
      const nextState = {
        active_editor: 'konva',
        resume_excalidraw_checkpoint_id: checkpointId,
        konva_baseline_checkpoint_id: baseline.checkpoint_id,
        konva_edit_warning_acknowledged: false,
      };
      await postVisualState(
        nextState, materialized.conversationId, materialized.conversationTag
      );
      pendingKonvaEditabilityWarning = true;
      setEditor('konva');
    };

    const loadCheckpoint = async (id, checkpointId, legacyTurn, state, options = {}) => {
      await flushDraftNow();
      conversationId = id || 'main';
      visualState = state || null;
      viewIsCurrent = options.currentDialogue !== false;
      pendingKonvaEditabilityWarning = !!(
        viewIsCurrent
        && state
        && state.active_editor === 'konva'
        && state.resume_excalidraw_checkpoint_id
        && state.konva_baseline_checkpoint_id
        && state.konva_edit_warning_acknowledged !== true
      );
      let loaded = null;
      if (options.currentDialogue && state && state.active_editor === 'konva') {
        loaded = await fetchCurrentKonva();
        if (!loaded && state.konva_baseline_checkpoint_id) {
          loaded = await fetchCheckpoint(
            state.konva_baseline_checkpoint_id, null, false
          );
        }
      } else if (options.preferDraft) {
        loaded = await fetchDraft();
      }
      if (!loaded) loaded = await fetchCheckpoint(checkpointId, legacyTurn, false);
      if (!loaded && !checkpointId && viewIsCurrent) loaded = await fetchDraft();
      if (!loaded) {
        if (excalidrawApi) {
          updateExcalidraw({ elements: [], appState: {}, files: {} });
          setEditor((state && state.active_editor) || 'excalidraw');
        } else {
          setEditor('konva');
        }
        return false;
      }
      if (loaded.editor === 'excalidraw') {
        try {
          const scene = await normalizeLegacyWhiteHandoff(
            await window.OraExcalidrawIsland.load(loaded.blob)
          );
          updateExcalidraw(scene);
          setEditor('excalidraw');
        } catch (error) {
          console.warn('[Excalidraw] native scene failed to load; recovering preview in Konva:', error);
          await recoverExcalidrawInKonva(checkpointId);
        }
      } else {
        const bytes = new Uint8Array(await loaded.blob.arrayBuffer());
        const canvasState = await window.OraCanvasFileFormat.read(bytes);
        if (panel && typeof panel.loadCanvasState === 'function') panel.loadCanvasState(canvasState);
        setEditor('konva');
      }
      return true;
    };

    const switchExcalidrawToKonva = async () => {
      await flushDraftNow();
      const sourceSnapshot = snapshotExcalidraw();
      const ownerId = sourceSnapshot.conversationId;
      const ownerTag = sourceSnapshot.conversationTag;
      const hadEditableContent = sourceSnapshot.elements.some(
        (element) => element && !element.isDeleted && !isAssistantArtifact(element)
      );
      const hasContent = sourceSnapshot.elements.some(
        (element) => element && !element.isDeleted
      );
      const source = await materialize(sourceSnapshot);
      const savedSource = await postCheckpoint(source);
      await resetKonvaToPng(source.preview, hasContent);
      const baselineMaterialized = await materialize(Object.assign(
        {}, snapshotKonva(), { conversationId: ownerId, conversationTag: ownerTag }
      ));
      const baseline = await postCheckpoint(baselineMaterialized);
      // Current-dialogue reloads use latest.ora-canvas so later Konva
      // autosaves win. Initialize that recoverable source from the exact K
      // baseline before publishing Konva authority; an older legacy latest
      // file must never shadow the new baseline.
      await writeCurrentKonva(baselineMaterialized);
      const state = {
        active_editor: 'konva',
        resume_excalidraw_checkpoint_id: savedSource.checkpoint_id,
        konva_baseline_checkpoint_id: baseline.checkpoint_id,
        konva_edit_warning_acknowledged: !hadEditableContent,
      };
      await postVisualState(state, ownerId, ownerTag);
      if (conversationId !== ownerId) {
        throw new Error('Dialogue changed while switching editor');
      }
      pendingKonvaEditabilityWarning = hadEditableContent;
      setEditor('konva');
    };

    const switchKonvaToExcalidraw = async () => {
      if (!excalidrawApi) throw new Error('Excalidraw is unavailable');
      const current = await materialize(snapshotKonva());
      const ownerId = current.conversationId;
      const ownerTag = current.conversationTag;
      const resumeId = visualState && visualState.resume_excalidraw_checkpoint_id;
      const baselineId = visualState && visualState.konva_baseline_checkpoint_id;
      let unchanged = false;
      if (resumeId && baselineId) {
        const baseline = await fetchCheckpoint(baselineId, null, true, ownerId);
        unchanged = !!baseline && await equalBlobs(current.preview, baseline.blob);
      }
      let scene;
      let durableSceneSnapshot;
      if (unchanged) {
        const saved = await fetchCheckpoint(resumeId, null, false, ownerId);
        if (!saved || saved.editor !== 'excalidraw') {
          throw new Error('The saved Excalidraw source is unavailable');
        }
        scene = await normalizeLegacyWhiteHandoff(
          await window.OraExcalidrawIsland.load(saved.blob)
        );
        durableSceneSnapshot = Object.freeze({
          editor: 'excalidraw',
          conversationId: ownerId,
          conversationTag: ownerTag,
          elements: clone(scene.elements),
          appState: clone(scene.appState),
          files: clone(scene.files || {}),
        });
      } else {
        scene = await window.OraExcalidrawIsland.imageBackedScene(current.preview, true);
        durableSceneSnapshot = Object.freeze({
          editor: 'excalidraw',
          conversationId: ownerId,
          conversationTag: ownerTag,
          elements: clone(scene.elements),
          appState: clone(scene.appState),
          files: clone(scene.files),
        });
        await postCheckpoint(await materialize(durableSceneSnapshot));
      }
      // latest.excalidraw is the current-dialogue recovery source. It must be
      // durable before provenance is cleared, especially for the new B scene.
      await writeDraft(durableSceneSnapshot, ownerId, ownerTag);
      await postVisualState({ active_editor: 'excalidraw' }, ownerId, ownerTag);
      if (conversationId !== ownerId) {
        throw new Error('Dialogue changed while switching editor');
      }
      pendingKonvaEditabilityWarning = false;
      updateExcalidraw(scene);
      setEditor('excalidraw');
    };

    const switchEditor = () => enqueue(async () => {
      toggle.disabled = true;
      try {
        if (editor === 'excalidraw') await switchExcalidrawToKonva();
        else await switchKonvaToExcalidraw();
      } finally {
        toggle.disabled = false;
      }
    });

    const renderAssistantVisual = (envelope, assistantKey, persist) => enqueue(async () => {
      if (editor === 'konva' || !excalidrawApi) {
        // Keep the established canvas_action state machine when Konva is
        // authoritative. Calling renderSpec directly would bypass
        // replace/update/annotate/clear semantics.
        if (panel) {
          return panel.onBridgeUpdate({
            ora_visual_blocks: [{ envelope }],
          });
        }
        return null;
      }
      const currentElements = excalidrawApi.getSceneElements();
      if (assistantKey && currentElements.some((element) => (
        !element.isDeleted
        && element.customData
        && element.customData.oraAssistantVisualKey === assistantKey
      ))) {
        return { skipped: true };
      }
      const explicitAction = envelope && envelope.canvas_action;
      const action = ['replace', 'update', 'annotate', 'clear'].includes(explicitAction)
        ? explicitAction
        : currentElements.some((element) => !element.isDeleted && isAssistantArtifact(element))
          ? 'update'
          : 'replace';
      if (action === 'clear') {
        updateExcalidraw({ elements: [], appState: {}, files: {} });
        await persistExcalidrawMutation(persist);
        return { action };
      }
      if (action === 'annotate') {
        console.warn(
          '[visual editor] Excalidraw cannot apply semantic annotations at the PNG boundary; scene preserved'
        );
        return {
          action,
          unsupported: true,
          warnings: [
            'Excalidraw cannot apply semantic canvas annotations. '
            + 'The scene was preserved; switch to Konva to apply this annotation.'
          ],
        };
      }
      const compiler = window.OraVisualCompiler;
      if (!compiler || typeof compiler.compileWithNav !== 'function') {
        throw new Error('Ora visual compiler is unavailable');
      }
      const result = await Promise.resolve(compiler.compileWithNav(envelope));
      if (!result || (result.errors && result.errors.length) || !result.svg) {
        throw new Error('Ora visual compiler did not produce an SVG');
      }
      const png = await rasterizeSvg(result.svg);
      const customData = {
        oraAssistantVisual: true,
        oraAssistantVisualKind: 'artifact',
      };
      if (assistantKey) customData.oraAssistantVisualKey = assistantKey;
      await placeExcalidrawPng(png, { action, locked: true, customData });
      await persistExcalidrawMutation(persist);
      return Object.assign({}, result, { action });
    });

    const insertCapabilityImage = (canvasObject) => enqueue(async () => {
      if (editor === 'konva' || !excalidrawApi) {
        if (panel && typeof panel.insertImageObject === 'function') {
          return panel.insertImageObject(canvasObject);
        }
        if (panel && typeof panel.attachImage === 'function') {
          const png = await blobFromCanvasImage(canvasObject);
          return panel.attachImage(new File(
            [png], 'capability-output.png', { type: png.type || 'image/png' }
          ));
        }
        return null;
      }
      const png = await blobFromCanvasImage(canvasObject);
      const placed = await placeExcalidrawPng(png, {
        action: 'append',
        locked: false,
        customData: {
          oraCapabilityOutput: true,
          oraCapabilityObjectId: canvasObject && canvasObject.id || null,
        },
        bounds: canvasObject,
      });
      await persistExcalidrawMutation(viewIsCurrent);
      return placed;
    });

    const attachImage = (file) => enqueue(async () => {
      if (editor === 'konva' || !excalidrawApi) {
        return panel && typeof panel.attachImage === 'function'
          ? panel.attachImage(file) : null;
      }
      const png = await normalizeImageToPng(file);
      const placed = await placeExcalidrawPng(png, {
        action: 'append', locked: false,
        customData: { oraCapabilityOutput: true },
      });
      await persistExcalidrawMutation(viewIsCurrent);
      return placed;
    });

    let footerStatusTimer = null;
    const setFooterStatus = (message, isError = false) => {
      if (!footerStatus || !footer) return;
      if (footerStatusTimer) clearTimeout(footerStatusTimer);
      footerStatusTimer = null;
      footerStatus.textContent = message || '';
      footerStatus.classList.toggle('is-error', !!isError);
      footer.classList.toggle('has-status', !!message);
      if (message && !isError && !String(message).endsWith('…')) {
        footerStatusTimer = setTimeout(() => setFooterStatus(''), 2400);
      }
    };

    toggle.addEventListener('click', () => {
      setFooterStatus('Switching editor…');
      switchEditor()
        .then(() => setFooterStatus(
          editor === 'konva' ? 'Konva ready' : 'Excalidraw ready'
        ))
        .catch((error) => {
          console.warn('[visual editor] switch failed; keeping durable editor:', error);
          setFooterStatus(`Switch failed: ${error && error.message || error}`, true);
          updateEditorPresentation();
        });
    });

    const originalVisualFacade = window.OraPanels && window.OraPanels.visual;
    if (originalVisualFacade) {
      originalVisualFacade.onBridgeUpdate = (state) => {
        if (!state) return;
        const blocks = Array.isArray(state.ora_visual_blocks)
          ? state.ora_visual_blocks
          : [state.envelope || state.visual || state];
        const dispatchKey = typeof state.ora_visual_dispatch_key === 'string'
          ? state.ora_visual_dispatch_key : null;
        const persist = viewIsCurrent;
        const envelopes = blocks.map((block, index) => {
          let envelope = null;
          if (block && block.envelope) envelope = block.envelope;
          if (block && block.raw_json) {
            try { envelope = JSON.parse(block.raw_json); } catch (_) { envelope = null; }
          }
          if (!envelope && block && typeof block === 'object') envelope = block;
          return envelope ? {
            envelope,
            assistantKey: dispatchKey ? `${dispatchKey}:${index}` : null,
          } : null;
        }).filter(Boolean);
        // renderAssistantVisual uses the controller's one serialized chain,
        // so every block in one assistant turn lands in source order.
        const completion = Promise.all(envelopes.map((item) => (
          renderAssistantVisual(item.envelope, item.assistantKey, persist)
        )));
        completion.catch((error) => {
          console.warn('[visual editor] assistant visual failed:', error);
        });
        return completion;
      };
      originalVisualFacade.renderSpec = (envelope) => (
        renderAssistantVisual(envelope, null, viewIsCurrent)
      );
    }

    right._oraPanel = panel;

    const resetCanvas = () => {
      if (excalidrawApi) {
        applyingScene += 1;
        try {
          excalidrawApi.resetScene();
          syncExcalidrawGrid(excalidrawApi.getAppState());
          draftDirty = false;
          sceneReady = true;
        } finally {
          queueMicrotask(() => {
            applyingScene = Math.max(0, applyingScene - 1);
            updateCanvasState();
          });
        }
      }
      if (panel && typeof panel.resetCanvas === 'function') panel.resetCanvas();
      updateCanvasState();
    };

    const clearForUser = () => {
      if (editor === 'excalidraw' && excalidrawApi) {
        window.OraExcalidrawIsland.clearForUser(excalidrawApi);
        return;
      }
      if (panel && typeof panel.clearCanvas === 'function') panel.clearCanvas();
      updateCanvasState();
    };

    window.OraCanvas = {
      panel,
      getActiveEditor: () => editor,
      setConversationContext(id, tag) {
        const nextId = id || 'main';
        if (nextId !== conversationId) {
          sceneReady = false;
          viewIsCurrent = true;
        }
        conversationId = nextId;
        conversationTag = tag || '';
      },
      capture: () => editor === 'konva' ? snapshotKonva().spatial : null,
      hasContent: () => {
        if (editor === 'excalidraw') {
          return !!excalidrawApi && excalidrawApi.getSceneElements().some((element) => !element.isDeleted);
        }
        if (!panel || !window.OraSaveCanvas
            || typeof window.OraSaveCanvas.buildCanvasState !== 'function') return false;
        try {
          const state = window.OraSaveCanvas.buildCanvasState(panel);
          return !!state && Array.isArray(state.objects) && state.objects.length > 0;
        } catch (_) {
          return false;
        }
      },
      reset: resetCanvas,
      clearForUser,
      snapshotForSubmit: snapshotActive,
      materializeSnapshot: materialize,
      persistSnapshotDraft: (
        snapshot, ownerId = conversationId, ownerTag = conversationTag
      ) => (
        snapshot && snapshot.editor === 'excalidraw'
          ? writeDraft(snapshot, ownerId, ownerTag)
          : Promise.resolve()
      ),
      flushDraft: () => enqueue(flushDraftNow),
      loadCheckpoint: (id, checkpointId, legacyTurn, state, options) => enqueue(
        () => loadCheckpoint(id, checkpointId, legacyTurn, state, options)
      ),
      insertImageObject: insertCapabilityImage,
      attachImage,
      switchEditor,
      _canonicalizeKonva: canonicalizeKonva,
      _equalBlobs: equalBlobs,
    };

    if (importButton && importInput) {
      importButton.addEventListener('click', () => importInput.click());
      importInput.addEventListener('change', async () => {
        const file = importInput.files && importInput.files[0];
        importInput.value = '';
        if (!file) return;
        importButton.disabled = true;
        setFooterStatus('Importing image…');
        try {
          const imported = await window.OraCanvas.attachImage(file);
          if (!imported) {
            setFooterStatus('Image was not imported');
          } else {
            setFooterStatus('Image imported');
          }
        } catch (error) {
          setFooterStatus(`Import failed: ${error && error.message || error}`, true);
        } finally {
          importButton.disabled = false;
        }
      });
    }

    const exportFormats = {
      png: { label: 'PNG', extension: 'png' },
      jpeg: { label: 'JPEG', extension: 'jpg' },
      svg: { label: 'SVG', extension: 'svg' },
      pdf: { label: 'PDF', extension: 'pdf' },
    };

    const closeExportMenu = (restoreFocus = false) => {
      if (!exportButton || !exportMenuPopup) return;
      exportMenuPopup.hidden = true;
      exportButton.setAttribute('aria-expanded', 'false');
      if (restoreFocus) exportButton.focus();
    };

    const openExportMenu = (focusIndex = null) => {
      if (!exportButton || !exportMenuPopup || exportButton.disabled) return;
      exportMenuPopup.hidden = false;
      exportButton.setAttribute('aria-expanded', 'true');
      if (Number.isInteger(focusIndex) && exportMenuItems[focusIndex]) {
        exportMenuItems[focusIndex].focus();
      }
    };

    const exportExcalidraw = async (format, filename) => {
      const raster = window.OraExportRaster;
      const island = window.OraExcalidrawIsland;
      if (!raster || typeof raster._runShareGate !== 'function'
          || typeof raster._triggerDownload !== 'function') {
        throw new Error('Visual export is unavailable');
      }
      const gate = await raster._runShareGate(conversationId, filename);
      if (!gate.confirmed) return { cancelled: true };
      const snapshot = snapshotExcalidraw();
      if (format === 'pdf') {
        const pdf = window.OraExportPdf;
        if (!pdf || typeof pdf.buildPdf !== 'function') {
          throw new Error('PDF export is unavailable');
        }
        const png = await island.canonicalPng(snapshot);
        const dataUrl = await blobToDataURL(png);
        const image = await imageFromSource(dataUrl);
        const width = image.naturalWidth || image.width || 1;
        const height = image.naturalHeight || image.height || 1;
        pdf.buildPdf(dataUrl, { x: 0, y: 0, width, height }).doc.save(filename);
        return { ok: true };
      }
      let blob;
      if (format === 'png') blob = await island.canonicalPng(snapshot);
      else if (format === 'jpeg') blob = await island.exportJpeg(snapshot);
      else if (format === 'svg') blob = await island.exportSvg(snapshot);
      else throw new Error(`Unsupported export format: ${format}`);
      raster._triggerDownload(await blobToDataURL(blob), filename);
      return { ok: true };
    };

    const exportKonva = (format, filename) => {
      if (format === 'png' || format === 'jpeg') {
        const raster = window.OraExportRaster;
        const handler = raster && (format === 'png' ? raster.exportPNG : raster.exportJPG);
        if (typeof handler !== 'function') {
          throw new Error(`${exportFormats[format].label} export is unavailable`);
        }
        return handler(panel, { conversation_id: conversationId, filename });
      }
      if (format === 'svg') {
        if (!window.OraExportSVG || typeof window.OraExportSVG.exportNow !== 'function') {
          throw new Error('SVG export is unavailable');
        }
        return window.OraExportSVG.exportNow(panel, { filename });
      }
      if (format === 'pdf') {
        if (!window.OraExportPdf || typeof window.OraExportPdf.apply !== 'function') {
          throw new Error('PDF export is unavailable');
        }
        return window.OraExportPdf.apply(panel, { filename });
      }
      throw new Error(`Unsupported export format: ${format}`);
    };

    const exportVisual = async (format) => {
      const config = exportFormats[format];
      if (!config || !exportButton) return;
      const restoreFocus = !!(
        exportMenuPopup && exportMenuPopup.contains(document.activeElement)
      );
      closeExportMenu();
      exportButton.disabled = true;
      setFooterStatus(`Preparing ${config.label}…`);
      try {
        const safeId = String(conversationId || 'exhibits')
          .replace(/[^a-zA-Z0-9_-]+/g, '-');
        const filename = `${safeId}-exhibits.${config.extension}`;
        const result = editor === 'konva'
          ? await exportKonva(format, filename)
          : await exportExcalidraw(format, filename);
        setFooterStatus(result && result.cancelled
          ? 'Export cancelled' : `${config.label} exported`);
      } catch (error) {
        setFooterStatus(`Export failed: ${error && error.message || error}`, true);
      } finally {
        exportButton.disabled = !window.OraCanvas.hasContent();
        if (restoreFocus && !exportButton.disabled) exportButton.focus();
      }
    };

    if (exportButton && exportMenuPopup) {
      exportButton.addEventListener('click', () => {
        if (exportMenuPopup.hidden) openExportMenu();
        else closeExportMenu();
      });
      exportButton.addEventListener('keydown', (event) => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault();
          openExportMenu(event.key === 'ArrowDown' ? 0 : exportMenuItems.length - 1);
        } else if (event.key === 'Escape') {
          closeExportMenu();
        }
      });
      exportMenuPopup.addEventListener('keydown', (event) => {
        const current = exportMenuItems.indexOf(document.activeElement);
        if (event.key === 'Escape') {
          event.preventDefault();
          closeExportMenu(true);
        } else if (event.key === 'Tab') {
          closeExportMenu();
        } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp'
                   || event.key === 'Home' || event.key === 'End') {
          event.preventDefault();
          let next = event.key === 'Home' ? 0 : event.key === 'End'
            ? exportMenuItems.length - 1
            : (current + (event.key === 'ArrowDown' ? 1 : -1)
              + exportMenuItems.length) % exportMenuItems.length;
          exportMenuItems[next].focus();
        }
      });
      exportMenuItems.forEach((item) => item.addEventListener('click', () => {
        exportVisual(item.dataset.exportFormat);
      }));
      document.addEventListener('pointerdown', (event) => {
        if (!exportMenuPopup.hidden && exportMenu && !exportMenu.contains(event.target)) {
          closeExportMenu();
        }
      });
    }

    function updateCanvasState() {
      const hasContent = window.OraCanvas.hasContent();
      right.classList.toggle('canvas-empty', !hasContent);
      const logo = document.getElementById('logo-o');
      if (logo) logo.classList.toggle('canvas-ready', hasContent);
      document.dispatchEvent(new CustomEvent('ora:canvas-state-changed', {
        detail: { hasContent },
      }));
      if (exportButton) exportButton.disabled = !hasContent;
      if (!hasContent) closeExportMenu();
    }
    if (panel && panel.userInputLayer && panel.userInputLayer.on) {
      panel.userInputLayer.on('add.vp3-state remove.vp3-state', updateCanvasState);
    }

    try {
      if (!window.OraExcalidrawIsland) throw new Error('Local Excalidraw bundle did not load');
      islandRoot = window.OraExcalidrawIsland.mount(host, {
        initialData: {
          elements: [], files: {},
          appState: {
            theme: 'light',
            viewBackgroundColor: EXCALIDRAW_UI_BACKGROUND,
            gridModeEnabled: false,
          },
        },
        onReady(api) {
          excalidrawApi = api;
          syncExcalidrawGrid(api.getAppState());
          setEditor('excalidraw');
          updateCanvasState();
          document.dispatchEvent(new CustomEvent('ora:excalidraw-ready'));
        },
        onChange(_elements, appState) {
          syncExcalidrawGrid(appState);
          if (!sceneReady || applyingScene || !viewIsCurrent) return;
          scheduleDraft();
          updateCanvasState();
        },
        onClearCanvas: clearForUser,
        onFailure(error) {
          console.warn('[v3-canvas-mount] Excalidraw render failed; using Konva:', error);
          excalidrawApi = null;
          setEditor('konva');
          document.dispatchEvent(new CustomEvent('ora:excalidraw-failed', {
            detail: { error },
          }));
        },
      });
    } catch (error) {
      console.warn('[v3-canvas-mount] Excalidraw failed; using Konva:', error);
      editor = 'konva';
      updateEditorPresentation();
      document.dispatchEvent(new CustomEvent('ora:excalidraw-failed', { detail: { error } }));
    }

    document.addEventListener('ora:conversation-tag-changed', (event) => {
      const detail = event.detail || {};
      if (detail.conversation_id) conversationId = detail.conversation_id;
      conversationTag = detail.tag || '';
    });
    updateEditorPresentation();
    updateCanvasState();
    document.dispatchEvent(new CustomEvent('ora:canvas-mounted', {
      detail: { panelId: panel && panel.panelId, defaultEditor: 'excalidraw' },
    }));
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
