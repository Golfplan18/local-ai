/**
 * pack-install-review.js — WP-7.7.1
 *
 * Pack install-review modal. Shown before any third-party pack reaches
 * `OraPackLoader.loadPack` so the user sees what the pack contains and
 * which capability slots it can reach, then explicitly clicks Install
 * (or Cancel).
 *
 * ── Why this exists (Plan §11.15, §13.7) ──────────────────────────────────
 *
 * Per the §11.15 declarative-only security model, packs cannot execute
 * code, but they can:
 *   - Add toolbars and tools that the user will click.
 *   - Bundle macros that invoke capability slots (which talk to commercial
 *     APIs).
 *   - Ship prompt templates that get fed to LLMs / image models.
 *   - Place starter composition templates (with embedded SVG thumbnails)
 *     onto a fresh canvas.
 *
 * The user owns the trust call. This modal gives them everything needed
 * to make it: full breakdown of all four artifact categories, the
 * capability scope (per §10 of the Toolbar Pack Format), and the author
 * provenance + source path. Install only fires after an explicit click —
 * never on Enter, never on the backdrop, never on Escape.
 *
 * ── Public surface ────────────────────────────────────────────────────────
 *
 *   OraPackInstallReview.init({ host })
 *     Lazy-mount the modal element. Call once at boot. `host` defaults to
 *     document.body.
 *
 *   OraPackInstallReview.show(packDefinition, { source })
 *     → Promise<{ accepted: boolean }>
 *     Renders the modal populated from `packDefinition`. The promise
 *     resolves with `accepted: true` when the user clicks Install, and
 *     `accepted: false` when they click Cancel, click the backdrop, or
 *     press Escape. `source` is an optional path/URL string shown in the
 *     "Source" line; defaults to "(provided directly)".
 *
 *   OraPackInstallReview.computeCapabilityScope(packDefinition)
 *     → [string, ...]
 *     Pure function. Walks toolbars/macros/prompt_templates per §10 and
 *     returns the de-duplicated, sorted list of capability slots the pack
 *     can reach. Exposed for tests + diagnostics.
 *
 *   OraPackInstallReview.destroy()
 *     Tear down the modal element. Tests use this between cases.
 *
 * ── Loader integration (caller contract) ──────────────────────────────────
 *
 * Pack-loader.js (or whichever UI eventually calls loadPack) must invoke
 * `OraPackInstallReview.show(pack)` for any non-default-pack source and
 * only call `OraPackLoader.loadPack(pack)` when the promise resolves with
 * `accepted: true`. "Default pack" means a pack shipping inside
 * `~/ora/config/packs/` — those are vetted by the Ora maintainers and
 * skip review. Everything else is third-party.
 *
 * ── Why this is its own file (not folded into pack-loader.js) ─────────────
 *
 * pack-loader.js stays headless — it has no DOM, runs in Node tests, and
 * is the seam the macro / prompt-template / composition-template runtimes
 * call into. Mounting a modal there would couple the loader to the
 * browser. The review modal is purely a UI gate; the loader is the data
 * pipeline. Separating them keeps the loader testable without jsdom and
 * keeps the modal callable from anywhere a pack might enter the system
 * (drag-drop, settings panel, /install <path>, etc.).
 */

(function (root) {
  'use strict';

  var MODAL_ID = 'ora-pack-install-review-modal';

  // ── Mount state ──────────────────────────────────────────────────────────

  var _modalEl = null;
  var _hostEl = null;
  var _activePending = null;   // { resolve } during modal-open
  var _previousFocus = null;
  var _onKeydown = null;

  // ── Tiny string helpers ──────────────────────────────────────────────────

  function _isStr(x) { return typeof x === 'string' && x.length > 0; }

  function _esc(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Render a string that *might* be inline SVG. Inline SVGs are pasted
  // verbatim (validator already rejected anything malformed); plain
  // strings (Lucide names) become a small <span> placeholder so the
  // user at least sees the icon-name token. We never inject script tags
  // even when the input already passed validation — defense-in-depth.
  function _renderIcon(value) {
    if (!_isStr(value)) return '<span class="ora-pack-install-review__icon-empty"></span>';
    var trimmed = value.replace(/^\s+/, '');
    if (trimmed.slice(0, 4).toLowerCase() === '<svg') {
      // Re-strip script tags / event handlers as belt-and-braces. The
      // validator already blocks these but if a caller skips validation
      // we still don't want them mounted.
      var safe = value
        .replace(/<script[\s\S]*?<\/script>/gi, '')
        .replace(/\son[a-z]+\s*=\s*("[^"]*"|'[^']*')/gi, '');
      return '<span class="ora-pack-install-review__icon-svg">' + safe + '</span>';
    }
    return '<span class="ora-pack-install-review__icon-name">'
      + _esc(value) + '</span>';
  }

  // ── Capability scope (Toolbar Pack Format §10) ───────────────────────────

  function computeCapabilityScope(pack) {
    var seen = Object.create(null);

    function note(slot) {
      if (_isStr(slot)) seen[slot] = true;
    }

    if (pack && Array.isArray(pack.toolbars)) {
      for (var t = 0; t < pack.toolbars.length; t++) {
        var tb = pack.toolbars[t];
        if (!tb || !Array.isArray(tb.items)) continue;
        for (var i = 0; i < tb.items.length; i++) {
          var binding = tb.items[i] && tb.items[i].binding;
          if (_isStr(binding) && binding.indexOf('capability:') === 0) {
            note(binding.slice('capability:'.length));
          }
        }
      }
    }

    if (pack && Array.isArray(pack.macros)) {
      for (var m = 0; m < pack.macros.length; m++) {
        var mc = pack.macros[m];
        if (!mc || !Array.isArray(mc.steps)) continue;
        for (var s = 0; s < mc.steps.length; s++) {
          var step = mc.steps[s];
          if (step && _isStr(step.capability)) note(step.capability);
        }
      }
    }

    if (pack && Array.isArray(pack.prompt_templates)) {
      for (var p = 0; p < pack.prompt_templates.length; p++) {
        var pt = pack.prompt_templates[p];
        if (pt && _isStr(pt.capability_route)) note(pt.capability_route);
      }
    }

    var out = Object.keys(seen);
    out.sort();
    return out;
  }

  // ── Section renderers ────────────────────────────────────────────────────

  function _renderToolbarsSection(toolbars) {
    if (!Array.isArray(toolbars) || toolbars.length === 0) {
      return '<p class="ora-pack-install-review__empty">No toolbars.</p>';
    }
    var html = '';
    for (var t = 0; t < toolbars.length; t++) {
      var tb = toolbars[t] || {};
      html += '<div class="ora-pack-install-review__toolbar">'
            + '<h4>' + _esc(tb.label || tb.id || '(unnamed toolbar)') + '</h4>'
            + '<p class="ora-pack-install-review__id">id: <code>' + _esc(tb.id || '') + '</code>'
            +   (tb.default_dock ? ' · dock: <code>' + _esc(tb.default_dock) + '</code>' : '')
            + '</p>';
      var items = Array.isArray(tb.items) ? tb.items : [];
      if (items.length === 0) {
        html += '<p class="ora-pack-install-review__empty">No tools.</p>';
      } else {
        html += '<ul class="ora-pack-install-review__items">';
        for (var i = 0; i < items.length; i++) {
          var it = items[i] || {};
          html += '<li>'
                + _renderIcon(it.icon)
                + '<span class="ora-pack-install-review__item-label">' + _esc(it.label || it.id || '(unnamed)') + '</span>'
                + '<code class="ora-pack-install-review__binding">' + _esc(it.binding || '') + '</code>'
                + (it.shortcut ? '<kbd>' + _esc(it.shortcut) + '</kbd>' : '')
                + '</li>';
        }
        html += '</ul>';
      }
      html += '</div>';
    }
    return html;
  }

  function _renderMacrosSection(macros) {
    if (!Array.isArray(macros) || macros.length === 0) {
      return '<p class="ora-pack-install-review__empty">No macros.</p>';
    }
    var html = '';
    for (var m = 0; m < macros.length; m++) {
      var mc = macros[m] || {};
      html += '<div class="ora-pack-install-review__macro">'
            + '<h4>' + _renderIcon(mc.icon) + _esc(mc.label || mc.id || '(unnamed macro)') + '</h4>'
            + '<p class="ora-pack-install-review__id">id: <code>' + _esc(mc.id || '') + '</code>'
            +   (mc.shortcut ? ' · shortcut: <kbd>' + _esc(mc.shortcut) + '</kbd>' : '')
            + '</p>';
      var steps = Array.isArray(mc.steps) ? mc.steps : [];
      if (steps.length === 0) {
        html += '<p class="ora-pack-install-review__empty">No steps.</p>';
      } else {
        html += '<ol class="ora-pack-install-review__steps">';
        for (var s = 0; s < steps.length; s++) {
          var step = steps[s] || {};
          var kind = _isStr(step.tool)       ? 'tool: '       + step.tool
                   : _isStr(step.capability) ? 'capability: ' + step.capability
                   : '(unknown)';
          var paramsStr = '';
          try {
            paramsStr = step.params ? JSON.stringify(step.params) : '';
          } catch (_) { paramsStr = '(unstringifiable params)'; }
          html += '<li><code>' + _esc(kind) + '</code>'
                + (paramsStr ? ' <span class="ora-pack-install-review__params">' + _esc(paramsStr) + '</span>' : '')
                + '</li>';
        }
        html += '</ol>';
      }
      html += '</div>';
    }
    return html;
  }

  function _renderPromptTemplatesSection(templates) {
    if (!Array.isArray(templates) || templates.length === 0) {
      return '<p class="ora-pack-install-review__empty">No prompt templates.</p>';
    }
    var html = '';
    for (var p = 0; p < templates.length; p++) {
      var pt = templates[p] || {};
      var route = _isStr(pt.capability_route)
        ? 'capability_route: ' + pt.capability_route
        : ('gear_preference: ' + (pt.gear_preference == null ? '1' : String(pt.gear_preference)));
      html += '<div class="ora-pack-install-review__template">'
            + '<h4>' + _esc(pt.label || pt.id || '(unnamed template)') + '</h4>'
            + '<p class="ora-pack-install-review__id">id: <code>' + _esc(pt.id || '') + '</code>'
            +   (pt.slash_command ? ' · slash: <code>' + _esc(pt.slash_command) + '</code>' : '')
            +   ' · route: <code>' + _esc(route) + '</code>'
            + '</p>'
            + '<pre class="ora-pack-install-review__template-body">' + _esc(pt.template || '') + '</pre>'
            + '</div>';
    }
    return html;
  }

  function _renderCompositionTemplatesSection(comps) {
    if (!Array.isArray(comps) || comps.length === 0) {
      return '<p class="ora-pack-install-review__empty">No composition templates.</p>';
    }
    var html = '';
    for (var c = 0; c < comps.length; c++) {
      var ct = comps[c] || {};
      html += '<div class="ora-pack-install-review__composition">'
            + '<h4>' + _esc(ct.label || ct.id || '(unnamed composition)') + '</h4>'
            + '<p class="ora-pack-install-review__id">id: <code>' + _esc(ct.id || '') + '</code></p>'
            + '<div class="ora-pack-install-review__thumbnail">'
            +   _renderIcon(ct.thumbnail)
            + '</div>'
            + '</div>';
    }
    return html;
  }

  function _renderCapabilityScope(scope) {
    if (!Array.isArray(scope) || scope.length === 0) {
      return '<p class="ora-pack-install-review__empty">'
           + 'This pack does not invoke any capability slots — it operates entirely on the canvas.'
           + '</p>';
    }
    var html = '<p class="ora-pack-install-review__scope-intro">'
             + 'This pack can invoke the following capability slots, which may reach external services:'
             + '</p>'
             + '<ul class="ora-pack-install-review__scope">';
    for (var i = 0; i < scope.length; i++) {
      html += '<li><code>' + _esc(scope[i]) + '</code></li>';
    }
    html += '</ul>';
    return html;
  }

  function _renderAuthorBlock(pack, source) {
    var author = (pack && pack.author) ? pack.author : {};
    var html = '<div class="ora-pack-install-review__author">';
    html += '<p><strong>Author:</strong> ' + _esc(author.name || '(unspecified)') + '</p>';
    if (_isStr(author.url))   html += '<p><strong>URL:</strong> <code>'   + _esc(author.url)   + '</code></p>';
    if (_isStr(author.email)) html += '<p><strong>Email:</strong> <code>' + _esc(author.email) + '</code></p>';
    html += '<p><strong>Source:</strong> <code>' + _esc(source || '(provided directly)') + '</code></p>';
    html += '</div>';
    return html;
  }

  // ── Modal construction ───────────────────────────────────────────────────

  function _buildModal() {
    if (typeof document === 'undefined') return null;
    var root = document.createElement('div');
    root.id = MODAL_ID;
    root.className = 'ora-pack-install-review';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-labelledby', MODAL_ID + '-title');
    root.setAttribute('aria-describedby', MODAL_ID + '-body');
    root.hidden = true;
    root.innerHTML =
      '<div class="ora-pack-install-review__backdrop" data-action="cancel"></div>' +
      '<div class="ora-pack-install-review__dialog" role="document">' +
        '<h2 class="ora-pack-install-review__title" id="' + MODAL_ID + '-title">Install pack?</h2>' +
        '<div class="ora-pack-install-review__body" id="' + MODAL_ID + '-body"></div>' +
        '<div class="ora-pack-install-review__actions">' +
          '<button type="button" class="ora-pack-install-review__btn ora-pack-install-review__btn--cancel" data-action="cancel">Cancel</button>' +
          '<button type="button" class="ora-pack-install-review__btn ora-pack-install-review__btn--install" data-action="install">Install</button>' +
        '</div>' +
      '</div>';
    root.addEventListener('click', _onModalClick);
    return root;
  }

  function _populateBody(pack, source) {
    if (!_modalEl) return;
    var body = _modalEl.querySelector('#' + MODAL_ID + '-body');
    if (!body) return;
    pack = pack || {};
    var scope = computeCapabilityScope(pack);
    var html = '';

    // Header — pack identity + description.
    html += '<header class="ora-pack-install-review__header">';
    html += '<h3>' + _esc(pack.pack_name || '(unnamed pack)')
          + ' <span class="ora-pack-install-review__version">v'
          + _esc(pack.pack_version || '?') + '</span></h3>';
    if (_isStr(pack.description)) {
      html += '<p class="ora-pack-install-review__description">' + _esc(pack.description) + '</p>';
    }
    if (_isStr(pack.ora_compatibility)) {
      html += '<p class="ora-pack-install-review__compat">Requires Ora '
            + _esc(pack.ora_compatibility) + '.</p>';
    }
    html += '</header>';

    // Author + source.
    html += _renderAuthorBlock(pack, source);

    // Capability scope — load-bearing for trust decision; show first.
    html += '<section class="ora-pack-install-review__section ora-pack-install-review__section--scope">';
    html += '<h3>Capability scope</h3>';
    html += _renderCapabilityScope(scope);
    html += '</section>';

    // Four artifact categories.
    html += '<section class="ora-pack-install-review__section">';
    html += '<h3>Toolbars</h3>' + _renderToolbarsSection(pack.toolbars);
    html += '</section>';

    html += '<section class="ora-pack-install-review__section">';
    html += '<h3>Macros</h3>' + _renderMacrosSection(pack.macros);
    html += '</section>';

    html += '<section class="ora-pack-install-review__section">';
    html += '<h3>Prompt templates</h3>' + _renderPromptTemplatesSection(pack.prompt_templates);
    html += '</section>';

    html += '<section class="ora-pack-install-review__section">';
    html += '<h3>Composition templates</h3>' + _renderCompositionTemplatesSection(pack.composition_templates);
    html += '</section>';

    body.innerHTML = html;
  }

  function _onModalClick(e) {
    var target = e.target;
    if (!target || !target.dataset) return;
    var action = target.dataset.action;
    if (!action) return;
    if (action === 'install')       _resolveAndClose(true);
    else if (action === 'cancel')   _resolveAndClose(false);
  }

  function _resolveAndClose(accepted) {
    var pending = _activePending;
    _activePending = null;
    _hideModal();
    if (pending && typeof pending.resolve === 'function') {
      try { pending.resolve({ accepted: !!accepted }); }
      catch (e) {
        if (typeof console !== 'undefined' && console.error) {
          console.error('[pack-install-review] resolve threw:', e);
        }
      }
    }
  }

  function _hideModal() {
    if (!_modalEl) return;
    _modalEl.hidden = true;
    if (typeof document !== 'undefined' && _onKeydown) {
      document.removeEventListener('keydown', _onKeydown, true);
    }
    _onKeydown = null;
    if (_previousFocus && typeof _previousFocus.focus === 'function') {
      try { _previousFocus.focus(); } catch (e) { /* ignore */ }
    }
    _previousFocus = null;
  }

  function _showModal(pack, opts) {
    if (!_modalEl) {
      // Lazy-mount on first show, not init — supports tests that
      // construct the module before document.body exists.
      _ensureMounted();
      if (!_modalEl) {
        return Promise.resolve({ accepted: false });
      }
    }
    var source = opts && _isStr(opts.source) ? opts.source : '(provided directly)';
    _populateBody(pack, source);

    return new Promise(function (resolve) {
      // If a previous review is mid-flight, cancel it so the new one can
      // resolve cleanly. Tests + users only ever see one modal at a time.
      if (_activePending && typeof _activePending.resolve === 'function') {
        try { _activePending.resolve({ accepted: false }); } catch (_) { /* ignore */ }
      }
      _activePending = { resolve: resolve };

      _modalEl.hidden = false;
      if (typeof document !== 'undefined' && document.activeElement) {
        _previousFocus = document.activeElement;
      }
      // Default focus to Cancel — never Install. We never want Enter on a
      // freshly-opened modal to install something.
      var cancelBtn = _modalEl.querySelector('.ora-pack-install-review__btn--cancel');
      if (cancelBtn && typeof cancelBtn.focus === 'function') {
        try { cancelBtn.focus(); } catch (e) { /* ignore */ }
      }

      _onKeydown = function (e) {
        if (!_modalEl || _modalEl.hidden) return;
        if (e.key === 'Escape' || e.keyCode === 27) {
          e.preventDefault();
          _resolveAndClose(false);
        }
        // Note: no Enter-to-install — Install must be an explicit click
        // on the Install button. (Enter on the Install button itself
        // fires a click via the browser's default behavior.)
      };
      if (typeof document !== 'undefined') {
        document.addEventListener('keydown', _onKeydown, true);
      }
    });
  }

  // ── Public API ───────────────────────────────────────────────────────────

  function _ensureMounted() {
    if (_modalEl) return _modalEl;
    if (typeof document === 'undefined') return null;
    _modalEl = _buildModal();
    if (!_modalEl) return null;
    _hostEl = _hostEl || document.body || null;
    if (_hostEl) _hostEl.appendChild(_modalEl);
    return _modalEl;
  }

  function init(options) {
    options = options || {};
    if (options.host && typeof options.host === 'object') {
      _hostEl = options.host;
    }
    _ensureMounted();
  }

  function show(packDefinition, options) {
    return _showModal(packDefinition || {}, options || {});
  }

  function destroy() {
    _resolveAndClose(false);
    if (_modalEl && _modalEl.parentNode) {
      _modalEl.parentNode.removeChild(_modalEl);
    }
    _modalEl = null;
    _hostEl = null;
  }

  var api = {
    init:                    init,
    show:                    show,
    destroy:                 destroy,
    computeCapabilityScope:  computeCapabilityScope,
    // exposed for tests:
    _state: function () {
      return {
        mounted: !!_modalEl,
        hidden:  _modalEl ? !!_modalEl.hidden : true,
        activePending: !!_activePending
      };
    }
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraPackInstallReview = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
