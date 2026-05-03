/* v3-template-gallery.js — V3 sample-template gallery (WP-7.7.5, 2026-04-30)
 *
 * Modal gallery launched by the universal toolbar's "New canvas" button.
 * Shows two sections:
 *
 *   1. Templates — pack-shipped composition templates surfaced from
 *      OraCompositionTemplateLoader.list(). Plus a "Blank canvas" tile
 *      that calls OraCanvasFileFormat.newCanvasState({}) for an empty
 *      starting state.
 *
 *   2. Your templates — user-saved templates stored in localStorage
 *      under "ora.userTemplates". Plus a "Save current as template"
 *      tile that snapshots the current canvas. The list grows as the
 *      user adds entries; the modal re-renders after each save.
 *
 * Each tile is a card with thumbnail (uses pack's inline-SVG thumbnail
 * when present, falls back to a placeholder glyph), label, and source
 * note (pack name or "Saved by you").
 *
 * Apply path uses OraCompositionTemplateLoader.applyTemplate(id, panel)
 * which dispatches to panel.loadCanvasState(state). visual-panel doesn't
 * ship a loadCanvasState today, so this module monkey-patches a minimal
 * one onto the panel that clears layers, sets view, and dispatches an
 * ora:canvas-loaded event. Object reconstruction (full canvas-state →
 * Konva nodes) is deferred — current pack templates ship empty objects.
 *
 * Public API: window.OraV3TemplateGallery
 *   open(panel)   — open the gallery anchored to the given panel
 *   close()       — close the gallery
 *
 * The "New canvas" button itself is added to universal.toolbar.json with
 * binding "tool:new_canvas". v3-pack-toolbars attaches the click handler
 * after the universal toolbar mounts (visual-panel's actionRegistry is
 * a closure variable that we can't extend after _mountUniversalToolbar
 * returns).
 */
(function () {
  'use strict';

  var USER_TEMPLATE_KEY = 'ora.userTemplates';

  var _modalEls = null;
  var _activePanel = null;

  // ── Panel monkey-patch ─────────────────────────────────────────────────

  function _ensurePanelLoadState(panel) {
    // panel.loadCanvasState is patched at canvas-mount time by
    // v3-canvas-state-codec.js. This wrapper is only used when the
    // codec isn't available (headless / pre-load); it falls back to
    // a clear-only stub so the gallery doesn't crash.
    if (typeof panel.loadCanvasState === 'function') return;
    if (window.OraV3CanvasStateCodec && typeof window.OraV3CanvasStateCodec._patchPanel === 'function') {
      window.OraV3CanvasStateCodec._patchPanel(panel);
      return;
    }
    // Last-resort fallback — clear layers and apply view only.
    panel.loadCanvasState = function (state) {
      ['userInputLayer', 'annotationLayer'].forEach(function (key) {
        var layer = panel[key];
        if (layer && typeof layer.removeChildren === 'function') {
          layer.removeChildren();
          if (typeof layer.draw === 'function') layer.draw();
        }
      });
      if (state && state.view && typeof panel.setZoom === 'function') {
        panel.setZoom(state.view.zoom);
      }
    };
  }

  // ── User-template storage (localStorage) ───────────────────────────────

  function _readUserTemplates() {
    try {
      var raw = localStorage.getItem(USER_TEMPLATE_KEY);
      if (!raw) return [];
      var arr = JSON.parse(raw);
      return Array.isArray(arr) ? arr : [];
    } catch (e) {
      console.warn('[v3-template-gallery] read user templates failed:', e && e.message);
      return [];
    }
  }

  function _writeUserTemplates(arr) {
    try {
      localStorage.setItem(USER_TEMPLATE_KEY, JSON.stringify(arr));
      return true;
    } catch (e) {
      console.warn('[v3-template-gallery] write user templates failed:', e && e.message);
      return false;
    }
  }

  function _captureCurrentCanvasState(panel, label) {
    // Use the canvas-state codec when available — it walks the Konva
    // layers and serializes each shape/text/image into a canvas-state
    // object, including base64-encoded image bytes for round-trip.
    if (window.OraV3CanvasStateCodec
        && typeof window.OraV3CanvasStateCodec.serializeFromPanel === 'function') {
      return window.OraV3CanvasStateCodec.serializeFromPanel(panel, { title: label });
    }

    // Fallback — empty-objects state (the codec should always be present
    // in V3, but keep this as a safety net for headless tests).
    return {
      schema_version: '0.1',
      format_id:      'ora-canvas',
      metadata: {
        title:       label,
        canvas_size: { width: 10000, height: 10000 },
        created_at:  (new Date()).toISOString(),
        modified_at: (new Date()).toISOString()
      },
      view: {
        zoom: (typeof panel._zoom === 'number') ? panel._zoom : 1,
        pan:  { x: 0, y: 0 }
      },
      layers: [
        { id: 'background', kind: 'background' },
        { id: 'annotation', kind: 'annotation' },
        { id: 'user_input', kind: 'user_input' },
        { id: 'selection',  kind: 'selection' }
      ],
      objects: []
    };
  }

  function _saveCurrentAsTemplate(panel, label) {
    if (!panel || !label) return null;
    var entry = {
      id:           'user-' + Date.now() + '-' + Math.floor(Math.random() * 1e6),
      label:        label,
      created_at:   (new Date()).toISOString(),
      thumbnail:    null,
      canvas_state: _captureCurrentCanvasState(panel, label)
    };
    var existing = _readUserTemplates();
    existing.push(entry);
    return _writeUserTemplates(existing) ? entry : null;
  }

  function _deleteUserTemplate(id) {
    var existing = _readUserTemplates();
    var next = existing.filter(function (t) { return t.id !== id; });
    return _writeUserTemplates(next);
  }

  // ── Pack source resolution (which pack owns a template id) ─────────────

  function _packForTemplate(templateId) {
    if (!window.OraPackLoader || typeof window.OraPackLoader.listInstalled !== 'function') return null;
    var packs = window.OraPackLoader.listInstalled();
    for (var i = 0; i < packs.length; i++) {
      var p = packs[i];
      var ids = p.registered && p.registered.composition_templates;
      if (ids && ids.indexOf(templateId) >= 0) return p.pack_name || p.pack_id;
    }
    return null;
  }

  // ── Modal scaffolding ──────────────────────────────────────────────────

  function _ensureModal() {
    if (_modalEls) return _modalEls;

    var overlay = document.createElement('div');
    overlay.id = 'ora-template-gallery-overlay';
    overlay.setAttribute('aria-hidden', 'true');
    overlay.style.cssText = [
      'position:fixed', 'inset:0', 'z-index:99998',
      'background:rgba(0,0,0,0.55)',
      'display:none', 'align-items:center', 'justify-content:center'
    ].join(';');

    var modal = document.createElement('div');
    modal.id = 'ora-template-gallery-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-label', 'New canvas');
    modal.style.cssText = [
      'background:var(--ora-bg-1, #282a36)',
      'color:var(--ora-fg, #f8f8f2)',
      'border:1px solid var(--ora-border, #44475a)',
      'border-radius:10px',
      'padding:20px 24px',
      'min-width:640px', 'max-width:880px',
      'max-height:80vh', 'overflow:auto',
      'box-shadow:0 16px 48px rgba(0,0,0,0.6)',
      'font-family:var(--ora-font-body, Inter, system-ui, sans-serif)',
      'font-size:13px', 'line-height:1.4'
    ].join(';');

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) close();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && overlay.style.display !== 'none') close();
    });

    _modalEls = { overlay: overlay, modal: modal };
    return _modalEls;
  }

  // ── Card builders ──────────────────────────────────────────────────────

  function _styleCard(card, dashed) {
    card.style.cssText = [
      'all:unset', 'box-sizing:border-box', 'cursor:pointer',
      'display:flex', 'flex-direction:column',
      'width:180px', 'height:180px', 'padding:10px',
      'background:var(--ora-bg-0, #1e1f29)',
      'border:1px ' + (dashed ? 'dashed' : 'solid') + ' var(--ora-border, #44475a)',
      'border-radius:8px',
      'text-align:left', 'transition:border-color 0.15s'
    ].join(';');
    card.addEventListener('mouseenter', function () { card.style.borderColor = 'var(--ora-accent, #50fa7b)'; });
    card.addEventListener('mouseleave', function () { card.style.borderColor = 'var(--ora-border, #44475a)'; });
    card.addEventListener('focus',      function () { card.style.borderColor = 'var(--ora-accent, #50fa7b)'; });
    card.addEventListener('blur',       function () { card.style.borderColor = 'var(--ora-border, #44475a)'; });
  }

  var PLACEHOLDER_THUMB = '<svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.45"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>';

  function _buildTemplateCard(opts) {
    // opts: { id, label, source, thumbnail, onClick, onDelete? }
    var card = document.createElement('button');
    card.type = 'button';
    _styleCard(card, false);

    var thumb = document.createElement('div');
    thumb.style.cssText = [
      'flex:1 1 auto', 'min-height:0',
      'background:var(--ora-bg-2, #44475a)',
      'border-radius:4px', 'margin-bottom:8px',
      'display:flex', 'align-items:center', 'justify-content:center',
      'overflow:hidden'
    ].join(';');
    thumb.innerHTML = opts.thumbnail || PLACEHOLDER_THUMB;
    card.appendChild(thumb);

    var labelRow = document.createElement('div');
    labelRow.style.cssText = 'display:flex;justify-content:space-between;align-items:flex-start;gap:6px;';

    var labelCol = document.createElement('div');
    labelCol.style.cssText = 'min-width:0;flex:1 1 auto;';

    var label = document.createElement('div');
    label.style.cssText = 'font-weight:600;font-size:13px;margin-bottom:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
    label.textContent = opts.label;
    labelCol.appendChild(label);

    var src = document.createElement('div');
    src.style.cssText = 'font-size:11px;opacity:0.7;';
    src.textContent = opts.source;
    labelCol.appendChild(src);

    labelRow.appendChild(labelCol);

    if (typeof opts.onDelete === 'function') {
      var del = document.createElement('span');
      del.setAttribute('role', 'button');
      del.setAttribute('aria-label', 'Delete template');
      del.textContent = '×';
      del.style.cssText = 'cursor:pointer;padding:0 4px;font-size:18px;line-height:1;opacity:0.5;';
      del.addEventListener('mouseenter', function () { del.style.opacity = '1'; });
      del.addEventListener('mouseleave', function () { del.style.opacity = '0.5'; });
      del.addEventListener('click', function (e) {
        e.stopPropagation();
        opts.onDelete();
      });
      labelRow.appendChild(del);
    }

    card.appendChild(labelRow);
    card.addEventListener('click', opts.onClick);
    return card;
  }

  function _buildActionCard(opts) {
    // opts: { label, sublabel, iconSvg, onClick }
    var card = document.createElement('button');
    card.type = 'button';
    _styleCard(card, true);
    card.style.cssText += ';align-items:center;justify-content:center;text-align:center;';

    var iconWrap = document.createElement('div');
    iconWrap.style.cssText = 'margin-bottom:10px;opacity:0.7;';
    iconWrap.innerHTML = opts.iconSvg;
    card.appendChild(iconWrap);

    var label = document.createElement('div');
    label.style.cssText = 'font-weight:600;font-size:13px;margin-bottom:2px;';
    label.textContent = opts.label;
    card.appendChild(label);

    if (opts.sublabel) {
      var sub = document.createElement('div');
      sub.style.cssText = 'font-size:11px;opacity:0.7;';
      sub.textContent = opts.sublabel;
      card.appendChild(sub);
    }

    card.addEventListener('click', opts.onClick);
    return card;
  }

  // ── Modal renderer ─────────────────────────────────────────────────────

  function _renderModal(panel) {
    var m = _modalEls.modal;
    m.innerHTML = '';

    // Header.
    var header = document.createElement('div');
    header.style.cssText = 'display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;';
    var title = document.createElement('h2');
    title.textContent = 'New canvas';
    title.style.cssText = 'font-size:18px;margin:0;font-weight:600;';
    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.textContent = '×';
    closeBtn.setAttribute('aria-label', 'Close');
    closeBtn.style.cssText = 'background:none;border:none;color:inherit;font-size:24px;line-height:1;cursor:pointer;padding:0 4px;';
    closeBtn.addEventListener('click', close);
    header.appendChild(title);
    header.appendChild(closeBtn);
    m.appendChild(header);

    // ── Pack Templates section ──
    var packSection = document.createElement('section');
    packSection.style.cssText = 'margin-bottom:24px;';

    var packHeader = document.createElement('h3');
    packHeader.textContent = 'Templates';
    packHeader.style.cssText = 'font-size:11px;font-weight:600;opacity:0.7;text-transform:uppercase;letter-spacing:0.06em;margin:0 0 10px 0;';
    packSection.appendChild(packHeader);

    var packGrid = document.createElement('div');
    packGrid.style.cssText = 'display:flex;flex-wrap:wrap;gap:12px;';

    // Blank tile (always first).
    packGrid.appendChild(_buildActionCard({
      label: 'Blank canvas',
      sublabel: 'Empty workspace',
      iconSvg: '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
      onClick: function () { _applyBlank(panel); }
    }));

    // Pack templates. v3-phase7-boot wires OraCompositionTemplateLoader as
    // pack-loader's compositionRegistry (with a label→title adapter), so
    // the loader is the canonical source. Fall back to pack-loader's
    // internal fallback storage if the loader isn't available — keeps
    // headless test paths working.
    var ctl = window.OraCompositionTemplateLoader;
    var packLoader = window.OraPackLoader;
    var templates = [];
    if (ctl && typeof ctl.list === 'function') {
      templates = ctl.list();
    } else if (packLoader && typeof packLoader.listCompositionTemplates === 'function') {
      templates = packLoader.listCompositionTemplates();
    }
    templates.forEach(function (t) {
      packGrid.appendChild(_buildTemplateCard({
        id: t.id,
        label: t.label || t.title || t.id,
        source: _packForTemplate(t.id) || 'Pack',
        thumbnail: t.thumbnail || null,
        onClick: function () { _applyPackTemplate(t, panel); }
      }));
    });

    packSection.appendChild(packGrid);
    m.appendChild(packSection);

    // ── Your Templates section ──
    var userSection = document.createElement('section');
    var userHeader = document.createElement('h3');
    userHeader.textContent = 'Your templates';
    userHeader.style.cssText = 'font-size:11px;font-weight:600;opacity:0.7;text-transform:uppercase;letter-spacing:0.06em;margin:0 0 10px 0;';
    userSection.appendChild(userHeader);

    var userTemplates = _readUserTemplates();
    if (userTemplates.length === 0) {
      var emptyHint = document.createElement('p');
      emptyHint.style.cssText = 'font-size:12px;opacity:0.6;margin:0 0 10px 0;';
      emptyHint.textContent = 'No saved templates yet. Use the tile below to capture the current canvas as a starting point you can return to.';
      userSection.appendChild(emptyHint);
    }

    var userGrid = document.createElement('div');
    userGrid.style.cssText = 'display:flex;flex-wrap:wrap;gap:12px;';

    userTemplates.forEach(function (ut) {
      userGrid.appendChild(_buildTemplateCard({
        id: ut.id,
        label: ut.label,
        source: 'Saved by you',
        thumbnail: ut.thumbnail || null,
        onClick: function () { _applyUserTemplate(ut, panel); },
        onDelete: function () {
          if (_deleteUserTemplate(ut.id)) _renderModal(panel);
        }
      }));
    });

    // Save-as-template tile (always last).
    userGrid.appendChild(_buildActionCard({
      label: 'Save current as template',
      sublabel: 'Capture this canvas',
      iconSvg: '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>',
      onClick: function () { _saveCurrentFlow(panel); }
    }));

    userSection.appendChild(userGrid);
    m.appendChild(userSection);
  }

  // ── Apply paths ────────────────────────────────────────────────────────

  function _applyBlank(panel) {
    _ensurePanelLoadState(panel);
    if (window.OraCanvasFileFormat && typeof window.OraCanvasFileFormat.newCanvasState === 'function') {
      var blank = window.OraCanvasFileFormat.newCanvasState({});
      panel.loadCanvasState(blank);
    }
    close();
  }

  function _applyPackTemplate(template, panel) {
    _ensurePanelLoadState(panel);
    if (template && template.canvas_state) {
      try {
        panel.loadCanvasState(template.canvas_state);
      } catch (e) {
        console.warn('[v3-template-gallery] applyPackTemplate failed:', e && e.message);
      }
    }
    close();
  }

  function _applyUserTemplate(ut, panel) {
    _ensurePanelLoadState(panel);
    panel.loadCanvasState(ut.canvas_state);
    close();
  }

  function _saveCurrentFlow(panel) {
    var label = window.prompt('Template name:');
    if (!label) return;
    label = String(label).trim();
    if (!label) return;
    var saved = _saveCurrentAsTemplate(panel, label);
    if (saved) {
      _renderModal(panel);  // re-render to show the new tile
    } else {
      window.alert('Failed to save template — local storage may be unavailable.');
    }
  }

  // ── Public API ─────────────────────────────────────────────────────────

  function open(panel) {
    _activePanel = panel || (window.OraCanvas && window.OraCanvas.panel);
    if (!_activePanel) {
      console.warn('[v3-template-gallery] no panel available; cannot open gallery');
      return;
    }
    _ensurePanelLoadState(_activePanel);
    var els = _ensureModal();
    _renderModal(_activePanel);
    els.overlay.style.display = 'flex';
    els.overlay.setAttribute('aria-hidden', 'false');
  }

  function close() {
    if (!_modalEls) return;
    _modalEls.overlay.style.display = 'none';
    _modalEls.overlay.setAttribute('aria-hidden', 'true');
  }

  window.OraV3TemplateGallery = {
    open: open,
    close: close,
    _readUserTemplates: _readUserTemplates,
    _saveCurrentAsTemplate: _saveCurrentAsTemplate,
    _deleteUserTemplate: _deleteUserTemplate
  };

  // ── Document-level click delegation ───────────────────────────────────
  // The "New canvas" button lives in the universal toolbar, whose action
  // registry is built inside visual-panel._mountUniversalToolbar and not
  // accessible from outside. Rather than monkey-patching the panel, listen
  // at the document level for clicks on any element with the
  // tool:new_canvas binding and route them to open(). This also handles
  // pack toolbars that include the same binding.
  document.addEventListener('click', function (e) {
    var t = e.target;
    while (t && t !== document) {
      if (t.dataset && t.dataset.binding === 'tool:new_canvas') {
        e.preventDefault();
        e.stopPropagation();
        open(window.OraCanvas && window.OraCanvas.panel);
        return;
      }
      t = t.parentElement;
    }
  }, true); // capture phase so we win against the toolbar's own listener
})();
