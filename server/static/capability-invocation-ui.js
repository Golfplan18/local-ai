/**
 * capability-invocation-ui.js — WP-7.3.1
 *
 * Generic UX layer for invoking a capability slot. Reads a slot's contract
 * from `~/ora/config/capabilities.json` (loaded by the host page and
 * passed in at init), renders the right input widgets per declared input
 * type, gates the Run button on context (selection active, prompt typed,
 * image present, …), surfaces a sync spinner or async "sent" badge per
 * the slot's `execution_pattern`, and renders typed errors with fix-path
 * action buttons drawn from the slot's `common_errors[]`.
 *
 * Provider-agnostic. WP-7.3.2 sub-WPs supply the actual handlers; this
 * module only emits a `capability-dispatch` CustomEvent on submit and
 * listens for `capability-result` / `capability-error` events to render
 * the outcome. The dispatch event payload is exactly what the WP-7.6.1
 * job queue needs, so async slots integrate cleanly when the queue UI
 * lands.
 *
 * ── Slot input → widget mapping ────────────────────────────────────────
 *   `text`            → <input type="text"> (or <textarea> if hint long)
 *   `image-ref`       → canvas-object picker. Pre-fills with the active
 *                       canvas selection if it's image-shaped.
 *   `image-bytes`     → <input type="file" accept="image/*">. The chosen
 *                       file's base64 encoding lands in the dispatch
 *                       payload.
 *   `mask`            → reference to the current selection-tool output.
 *                       The mask itself is shaped per WP-7.5.1 (rectangle
 *                       / brush / lasso); we store the opaque ref the
 *                       host hands us.
 *   `enum`            → <select> populated from `enum_values[]`.
 *   `count`           → <input type="number" step="1">; clamps to
 *                       `min`/`max`/`min_count` when declared.
 *   `float`           → <input type="number" step="0.01">; clamps to
 *                       `min`/`max` when declared.
 *   `direction-list`  → four <input type="checkbox">: top / bottom /
 *                       left / right. Submits a string[] subset.
 *   `images-list`     → multi-file picker. The dispatched payload holds
 *                       an array of base64-encoded entries.
 *
 * ── Button enabled-state ──────────────────────────────────────────────
 * The Run button is enabled iff every required input has a non-empty
 * value. When disabled, hover surfaces a tooltip listing what's missing,
 * worded against each unfilled required input's `description` (per the
 * §11.5 "missing prerequisite" requirement).
 *
 * Sync UX — spinner + active-input lock. Async UX — replace the spinner
 * with a "Sent — will arrive when ready" badge and emit a
 * `capability-dispatch` event whose payload the WP-7.6.1 queue UI picks
 * up (we don't enqueue here; that's WP-7.6.1).
 *
 * ── Error UX ──────────────────────────────────────────────────────────
 * `capability-error` events carry { code, message, fix_path }. We look
 * up the matching entry in the slot's `common_errors[]` to surface the
 * declared `fix_path` as an action button. Three canonical fix-paths
 * have built-in handlers:
 *   - "Configure a model …"  → emits `open-settings` event
 *   - "Draw a mask first …"  → emits `activate-mask-tool` event
 *   - "Retry"                → re-submits the same input dict
 * Anything else renders as a passive label.
 *
 * Public API: window.OraCapabilityInvocationUI
 *
 *   .init(opts)  → mount and prime against a host element
 *     opts:
 *       hostEl        — DOM element to mount into (REQUIRED).
 *       capabilities  — capabilities.json dict { slots: {...} }.
 *       slotName      — string. Slot to render against.
 *       contextProvider — () => { canvasSelection, hasMask, ... }
 *                         Called on every input change to refresh
 *                         the enabled-state. Optional; defaults to {}.
 *       onDispatch    — (event) => void. Optional; receives the same
 *                         event payload that the CustomEvent carries.
 *
 *   .setSlot(slotName)             — switch to another slot in place
 *   .setContextProvider(fn)        — swap the context provider
 *   .refreshEnabledState()         — re-evaluate the Run button
 *   .submit()                       — programmatic submit (used in tests)
 *   .renderError(payload)           — surface an error from outside
 *   .renderResult(payload)          — surface a result from outside
 *   .destroy()                      — tear down DOM + listeners
 *   .getInputs()                    — current input dict (for tests)
 *
 * The module also dispatches DOM events on `hostEl` so that hosts that
 * prefer event listeners over callbacks can plug in:
 *
 *   capability-dispatch    — fired on submit. detail: { slot, inputs,
 *                            execution_pattern, provider_override }
 *   open-settings          — "Configure a model" fix-path
 *   activate-mask-tool     — "Draw a mask" fix-path
 *
 * Style hooks: every element has an `ora-cap-` class. CSS lives in
 * server/static/styles/components/capability-invocation-ui.css (out of
 * scope for this WP — the fallback browser styling is acceptable).
 */
(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────

  // Fix-path strings that map to first-class actions vs. passive labels.
  // Match is case-insensitive prefix; phrasing in capabilities.json is
  // free text but the §11.5 contract names these three canonical paths.
  var FIX_PATH_CONFIGURE_PREFIX = 'configure a';
  var FIX_PATH_MASK_PREFIX = 'draw a mask';
  var FIX_PATH_RETRY = 'retry';

  // Status pill text per execution pattern
  var ASYNC_BADGE_TEXT = 'Sent — will arrive when ready';
  var SYNC_SPINNER_TEXT = 'Working…';

  // ── DOM helpers ──────────────────────────────────────────────────────

  function _el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function _setAttrs(node, attrs) {
    if (!attrs) return node;
    for (var k in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, k) && attrs[k] != null) {
        node.setAttribute(k, attrs[k]);
      }
    }
    return node;
  }

  function _clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function _emit(targetEl, name, detail) {
    if (!targetEl || typeof CustomEvent !== 'function') return;
    var evt = new CustomEvent(name, { detail: detail, bubbles: true });
    targetEl.dispatchEvent(evt);
  }

  // ── State ─────────────────────────────────────────────────────────────

  // We hold a single live instance per init() call. The module supports
  // multiple concurrent instances by returning a controller from init();
  // window.OraCapabilityInvocationUI exposes the most-recent for the
  // common single-pane case.
  function _makeController(opts) {
    var state = {
      hostEl: opts.hostEl,
      capabilities: opts.capabilities || { slots: {} },
      slotName: opts.slotName,
      contextProvider: opts.contextProvider || function () { return {}; },
      onDispatch: opts.onDispatch || null,

      // DOM refs populated during render
      formEl: null,
      runBtn: null,
      tooltipEl: null,
      statusEl: null,
      errorEl: null,
      resultEl: null,
      inputControls: {},   // input name → { type, getValue, setValue, el }

      // Operational
      destroyed: false,
      inFlight: false,
      lastDispatch: null,  // for "Retry" fix-path
    };

    // ── Validation ─────────────────────────────────────────────────────

    function _getContract() {
      var slots = (state.capabilities && state.capabilities.slots) || {};
      var c = slots[state.slotName];
      if (!c) {
        throw new Error('capability-invocation-ui: unknown slot "' + state.slotName + '"');
      }
      return c;
    }

    // ── Widget renderers ───────────────────────────────────────────────

    function _renderText(spec, isRequired) {
      // Long text uses a textarea; short stays as <input>. The cutoff is
      // heuristic — `prompt` and `rubric` are obviously long-form, so we
      // bias toward textarea for any input named "prompt"/"rubric"/"description".
      var name = spec.name || '';
      var useArea = /prompt|rubric|description|text|caption/i.test(name);
      var control = useArea
        ? _el('textarea', 'ora-cap-input ora-cap-input--textarea')
        : _el('input', 'ora-cap-input ora-cap-input--text');
      _setAttrs(control, {
        name: spec.name,
        placeholder: spec.description || '',
        rows: useArea ? '3' : null,
      });
      if (!useArea) control.type = 'text';
      if (spec.default != null) control.value = String(spec.default);
      return {
        type: 'text',
        el: control,
        getValue: function () {
          var v = control.value;
          return v && v.trim().length ? v : null;
        },
        setValue: function (v) { control.value = v == null ? '' : String(v); },
      };
    }

    function _renderEnum(spec, isRequired) {
      var control = _el('select', 'ora-cap-input ora-cap-input--enum');
      control.name = spec.name;
      // Optional inputs get an empty (default) option so they can be unset.
      if (!isRequired || spec.default == null) {
        var emptyOpt = _el('option', null, isRequired ? '— choose —' : '(default)');
        emptyOpt.value = '';
        control.appendChild(emptyOpt);
      }
      var values = spec.enum_values || [];
      values.forEach(function (v) {
        var opt = _el('option', null, String(v));
        opt.value = String(v);
        control.appendChild(opt);
      });
      if (spec.default != null) control.value = String(spec.default);
      return {
        type: 'enum',
        el: control,
        getValue: function () {
          var v = control.value;
          return v && v.length ? v : null;
        },
        setValue: function (v) { control.value = v == null ? '' : String(v); },
      };
    }

    function _renderNumber(spec, kind /* 'count' | 'float' */) {
      var control = _el('input', 'ora-cap-input ora-cap-input--number');
      control.type = 'number';
      control.name = spec.name;
      control.step = (kind === 'float') ? '0.01' : '1';
      var minVal = (spec.min != null) ? spec.min
                : (spec.min_count != null) ? spec.min_count
                : null;
      if (minVal != null) control.min = String(minVal);
      if (spec.max != null) control.max = String(spec.max);
      if (spec.default != null) control.value = String(spec.default);
      if (spec.description) control.placeholder = spec.description;
      return {
        type: kind,
        el: control,
        getValue: function () {
          var raw = control.value;
          if (raw === '' || raw == null) return null;
          var n = (kind === 'float') ? parseFloat(raw) : parseInt(raw, 10);
          if (!isFinite(n)) return null;
          return n;
        },
        setValue: function (v) { control.value = v == null ? '' : String(v); },
      };
    }

    function _renderDirectionList(spec) {
      var wrap = _el('div', 'ora-cap-input ora-cap-input--directions');
      wrap.setAttribute('role', 'group');
      wrap.setAttribute('aria-label', spec.description || 'Directions');
      var dirs = ['top', 'bottom', 'left', 'right'];
      var checks = {};
      dirs.forEach(function (d) {
        var lbl = _el('label', 'ora-cap-checkbox');
        var cb = _el('input');
        cb.type = 'checkbox';
        cb.name = spec.name + '[' + d + ']';
        cb.value = d;
        lbl.appendChild(cb);
        lbl.appendChild(document.createTextNode(' ' + d));
        wrap.appendChild(lbl);
        checks[d] = cb;
      });
      return {
        type: 'direction-list',
        el: wrap,
        getValue: function () {
          var out = [];
          dirs.forEach(function (d) { if (checks[d].checked) out.push(d); });
          return out.length ? out : null;
        },
        setValue: function (v) {
          var set = {};
          (Array.isArray(v) ? v : []).forEach(function (d) { set[d] = true; });
          dirs.forEach(function (d) { checks[d].checked = !!set[d]; });
        },
      };
    }

    function _renderImageRef(spec) {
      // A canvas-object picker. We render a compact button + hidden input
      // pair: the button reads the current selection from the context
      // provider when clicked, and the hidden input holds the resolved
      // ref string for getValue(). Pre-fills from the active selection
      // on every render so the common case (user already has the right
      // image selected) needs zero extra clicks.
      var wrap = _el('div', 'ora-cap-input ora-cap-input--image-ref');
      var hidden = _el('input');
      hidden.type = 'hidden';
      hidden.name = spec.name;
      var label = _el('span', 'ora-cap-image-ref__label', '(no image selected)');
      var pickBtn = _el('button', 'ora-cap-image-ref__pick', 'Use selection');
      pickBtn.type = 'button';

      function _refresh() {
        var ctx = state.contextProvider() || {};
        var sel = ctx.canvasSelection;
        // Accept either a string id or an object with { id, kind: 'image' }.
        var id = null;
        if (typeof sel === 'string' && sel.length) id = sel;
        else if (sel && typeof sel === 'object' && sel.id && (sel.kind === 'image' || sel.kind == null)) {
          id = sel.id;
        }
        if (id) {
          hidden.value = id;
          label.textContent = 'Selected: ' + id;
        } else {
          hidden.value = '';
          label.textContent = '(no image selected)';
        }
      }

      pickBtn.addEventListener('click', function (e) {
        e.preventDefault();
        _refresh();
        _scheduleEnabledRefresh();
      });

      // Initial refresh so the field reflects whatever is selected at
      // render time without an extra click.
      _refresh();

      wrap.appendChild(label);
      wrap.appendChild(pickBtn);
      wrap.appendChild(hidden);

      return {
        type: 'image-ref',
        el: wrap,
        getValue: function () { return hidden.value || null; },
        setValue: function (v) {
          hidden.value = v == null ? '' : String(v);
          label.textContent = v ? ('Selected: ' + v) : '(no image selected)';
        },
        refresh: _refresh,
      };
    }

    function _renderImageBytes(spec) {
      var wrap = _el('div', 'ora-cap-input ora-cap-input--image-bytes');
      var fileEl = _el('input');
      fileEl.type = 'file';
      fileEl.accept = 'image/*';
      fileEl.name = spec.name;
      var status = _el('span', 'ora-cap-file__status', '(no file)');

      var cached = null; // { name, mime, base64 }

      fileEl.addEventListener('change', function () {
        var f = fileEl.files && fileEl.files[0];
        if (!f) {
          cached = null;
          status.textContent = '(no file)';
          _scheduleEnabledRefresh();
          return;
        }
        _readFileAsBase64(f).then(function (b64) {
          cached = { name: f.name, mime: f.type, base64: b64 };
          status.textContent = f.name;
          _scheduleEnabledRefresh();
        }).catch(function () {
          cached = null;
          status.textContent = 'Error reading file';
          _scheduleEnabledRefresh();
        });
      });

      wrap.appendChild(fileEl);
      wrap.appendChild(status);

      return {
        type: 'image-bytes',
        el: wrap,
        getValue: function () { return cached; },
        setValue: function (v) { cached = v; status.textContent = v && v.name ? v.name : '(no file)'; },
      };
    }

    function _renderImagesList(spec) {
      var wrap = _el('div', 'ora-cap-input ora-cap-input--images-list');
      var fileEl = _el('input');
      fileEl.type = 'file';
      fileEl.accept = 'image/*';
      fileEl.multiple = true;
      fileEl.name = spec.name;
      var status = _el('span', 'ora-cap-file__status', '(no files)');
      var minCount = spec.min_count || 0;
      if (minCount > 0) status.textContent = '(need at least ' + minCount + ')';

      var cached = []; // [{ name, mime, base64 }, ...]

      fileEl.addEventListener('change', function () {
        var files = Array.prototype.slice.call(fileEl.files || []);
        if (!files.length) {
          cached = [];
          status.textContent = minCount > 0 ? '(need at least ' + minCount + ')' : '(no files)';
          _scheduleEnabledRefresh();
          return;
        }
        Promise.all(files.map(function (f) {
          return _readFileAsBase64(f).then(function (b64) {
            return { name: f.name, mime: f.type, base64: b64 };
          });
        })).then(function (entries) {
          cached = entries;
          status.textContent = entries.length + ' file' + (entries.length === 1 ? '' : 's');
          _scheduleEnabledRefresh();
        }).catch(function () {
          cached = [];
          status.textContent = 'Error reading files';
          _scheduleEnabledRefresh();
        });
      });

      wrap.appendChild(fileEl);
      wrap.appendChild(status);

      return {
        type: 'images-list',
        el: wrap,
        getValue: function () {
          if (!cached.length) return null;
          if (minCount > 0 && cached.length < minCount) return null;
          return cached.slice();
        },
        setValue: function (v) {
          cached = Array.isArray(v) ? v.slice() : [];
          status.textContent = cached.length
            ? cached.length + ' file' + (cached.length === 1 ? '' : 's')
            : (minCount > 0 ? '(need at least ' + minCount + ')' : '(no files)');
        },
      };
    }

    function _renderMask(spec) {
      // The mask widget is a status indicator. It reads the current
      // selection-tool state from the context provider and reflects
      // whether a mask is ready. Format is opaque to us — WP-7.5.1 owns
      // the canonical shape; we just hold the ref the host hands us.
      var wrap = _el('div', 'ora-cap-input ora-cap-input--mask');
      var status = _el('span', 'ora-cap-mask__status', '(no mask drawn)');
      var refreshBtn = _el('button', 'ora-cap-mask__refresh', 'Refresh');
      refreshBtn.type = 'button';

      var cached = null; // mask payload from context.maskRef

      function _refresh() {
        var ctx = state.contextProvider() || {};
        // Accept either ctx.hasMask + ctx.maskRef, OR just ctx.maskRef.
        var ref = ctx.maskRef || (ctx.hasMask ? ctx.mask : null) || null;
        if (ref) {
          cached = ref;
          status.textContent = 'Mask ready';
        } else {
          cached = null;
          status.textContent = '(no mask drawn)';
        }
      }

      refreshBtn.addEventListener('click', function (e) {
        e.preventDefault();
        _refresh();
        _scheduleEnabledRefresh();
      });

      _refresh();

      wrap.appendChild(status);
      wrap.appendChild(refreshBtn);

      return {
        type: 'mask',
        el: wrap,
        getValue: function () { return cached; },
        setValue: function (v) {
          cached = v || null;
          status.textContent = cached ? 'Mask ready' : '(no mask drawn)';
        },
        refresh: _refresh,
      };
    }

    function _renderForType(spec, isRequired) {
      var t = spec.type;
      switch (t) {
        case 'text':            return _renderText(spec, isRequired);
        case 'enum':            return _renderEnum(spec, isRequired);
        case 'count':           return _renderNumber(spec, 'count');
        case 'float':           return _renderNumber(spec, 'float');
        case 'direction-list':  return _renderDirectionList(spec);
        case 'image-ref':       return _renderImageRef(spec);
        case 'image-bytes':     return _renderImageBytes(spec);
        case 'images-list':     return _renderImagesList(spec);
        case 'mask':            return _renderMask(spec);
        default:
          // Unknown declared type → fall back to text input with a
          // visible warning label. Mirrors icon-resolver's "fallback
          // glyph" pattern: surface, don't crash.
          var fallback = _renderText(spec, isRequired);
          fallback.el.classList.add('ora-cap-input--unknown-type');
          fallback.el.setAttribute('data-ora-unsupported-type', String(t));
          return fallback;
      }
    }

    // ── Layout ─────────────────────────────────────────────────────────

    function _render() {
      var contract = _getContract();
      _clear(state.hostEl);

      var form = _el('form', 'ora-cap-form');
      form.setAttribute('aria-label', contract.summary || contract.name);
      form.addEventListener('submit', function (e) { e.preventDefault(); submit(); });

      // Header
      var header = _el('div', 'ora-cap-header');
      header.appendChild(_el('h3', 'ora-cap-title', contract.name));
      if (contract.summary) {
        header.appendChild(_el('p', 'ora-cap-summary', contract.summary));
      }
      form.appendChild(header);

      // Inputs
      state.inputControls = {};
      var requireds = contract.required_inputs || [];
      var optionals = contract.optional_inputs || [];

      requireds.forEach(function (spec) { _appendField(form, spec, true); });
      if (optionals.length) {
        var optHeader = _el('h4', 'ora-cap-section', 'Optional');
        form.appendChild(optHeader);
        optionals.forEach(function (spec) { _appendField(form, spec, false); });
      }

      // Status / spinner / async badge area
      state.statusEl = _el('div', 'ora-cap-status');
      state.statusEl.setAttribute('role', 'status');
      state.statusEl.setAttribute('aria-live', 'polite');
      form.appendChild(state.statusEl);

      // Error area
      state.errorEl = _el('div', 'ora-cap-error');
      state.errorEl.setAttribute('role', 'alert');
      state.errorEl.style.display = 'none';
      form.appendChild(state.errorEl);

      // Result area (sync results render here unless caller routes them
      // elsewhere via onResult)
      state.resultEl = _el('div', 'ora-cap-result');
      state.resultEl.style.display = 'none';
      form.appendChild(state.resultEl);

      // Run button + tooltip wrapper
      var actions = _el('div', 'ora-cap-actions');
      var btnWrap = _el('span', 'ora-cap-runbtn-wrap');
      var btnLabel = (contract.execution_pattern === 'async') ? 'Send' : 'Run';
      state.runBtn = _el('button', 'ora-cap-runbtn', btnLabel);
      state.runBtn.type = 'submit';
      btnWrap.appendChild(state.runBtn);
      // Tooltip for disabled-state explanation; positioned via CSS
      state.tooltipEl = _el('span', 'ora-cap-tooltip');
      state.tooltipEl.setAttribute('role', 'tooltip');
      state.tooltipEl.style.display = 'none';
      btnWrap.appendChild(state.tooltipEl);
      actions.appendChild(btnWrap);
      form.appendChild(actions);

      state.formEl = form;
      state.hostEl.appendChild(form);

      // Wire change-listeners on every input so the Run button reflects
      // current readiness in real time.
      _wireChangeListeners();

      _refreshEnabled();
    }

    function _appendField(parentEl, spec, isRequired) {
      var row = _el('div', 'ora-cap-field' + (isRequired ? ' ora-cap-field--required' : ''));
      var label = _el('label', 'ora-cap-label');
      label.appendChild(document.createTextNode(spec.name));
      if (isRequired) {
        var req = _el('span', 'ora-cap-required-marker', ' *');
        label.appendChild(req);
      }
      row.appendChild(label);

      var control = _renderForType(spec, isRequired);
      // Persist the spec so submission knows what to do with the value.
      control.spec = spec;
      control.required = !!isRequired;
      // Wire label → first focusable element when feasible.
      var inner = control.el.querySelector
        ? control.el.querySelector('input, select, textarea, button')
        : null;
      if (inner) {
        var inputId = 'ora-cap-' + spec.name + '-' + Math.random().toString(36).slice(2, 8);
        inner.id = inputId;
        label.setAttribute('for', inputId);
      }
      row.appendChild(control.el);

      if (spec.description) {
        var help = _el('p', 'ora-cap-help', spec.description);
        row.appendChild(help);
      }

      parentEl.appendChild(row);
      state.inputControls[spec.name] = control;
    }

    function _wireChangeListeners() {
      // Listen for any user change inside the form and re-evaluate the
      // Run button. Covers text/enum/number/checkbox; the file/mask
      // controls call _scheduleEnabledRefresh() directly because their
      // value updates are async.
      if (!state.formEl) return;
      state.formEl.addEventListener('input', _scheduleEnabledRefresh);
      state.formEl.addEventListener('change', _scheduleEnabledRefresh);
    }

    // Coalesce rapid-fire changes into one paint frame.
    var _refreshScheduled = false;
    function _scheduleEnabledRefresh() {
      if (_refreshScheduled) return;
      _refreshScheduled = true;
      var raf = (typeof window !== 'undefined' && window.requestAnimationFrame)
        ? window.requestAnimationFrame.bind(window)
        : function (fn) { return setTimeout(fn, 0); };
      raf(function () {
        _refreshScheduled = false;
        _refreshEnabled();
      });
    }

    // ── Enabled-state ─────────────────────────────────────────────────

    function _missingRequireds() {
      var contract = _getContract();
      var missing = [];
      var requireds = contract.required_inputs || [];
      for (var i = 0; i < requireds.length; i++) {
        var spec = requireds[i];
        var ctrl = state.inputControls[spec.name];
        if (!ctrl) continue;
        var val = ctrl.getValue();
        var present = (val != null) && (val !== '' || val === 0);
        // Arrays must be non-empty
        if (Array.isArray(val) && val.length === 0) present = false;
        if (!present) missing.push(spec);
      }
      return missing;
    }

    function _refreshEnabled() {
      if (!state.runBtn) return;
      // While a sync request is in flight, we lock the button regardless
      // of input completeness — the form is "busy".
      if (state.inFlight) {
        state.runBtn.disabled = true;
        state.runBtn.setAttribute('aria-disabled', 'true');
        state.tooltipEl.style.display = 'none';
        return;
      }
      var missing = _missingRequireds();
      if (missing.length === 0) {
        state.runBtn.disabled = false;
        state.runBtn.removeAttribute('aria-disabled');
        state.runBtn.removeAttribute('title');
        state.tooltipEl.style.display = 'none';
        state.tooltipEl.textContent = '';
      } else {
        state.runBtn.disabled = true;
        state.runBtn.setAttribute('aria-disabled', 'true');
        var tooltip = _composeMissingTooltip(missing);
        // The native `title` attribute keeps the spec's "hover-tooltip"
        // requirement working when the visible custom tooltip is hidden
        // by CSS or unsupported.
        state.runBtn.setAttribute('title', tooltip);
        state.tooltipEl.textContent = tooltip;
        state.tooltipEl.style.display = '';
      }
    }

    function _composeMissingTooltip(missingSpecs) {
      var parts = missingSpecs.map(function (s) {
        // Per §11.5: explain the missing prerequisite using the slot
        // contract's input requirements.
        var label = s.description || s.name;
        return label;
      });
      if (parts.length === 1) {
        return 'Missing: ' + parts[0];
      }
      return 'Missing inputs: ' + parts.join('; ');
    }

    // ── Submit / dispatch ─────────────────────────────────────────────

    function submit() {
      if (state.inFlight) return null;
      var missing = _missingRequireds();
      if (missing.length) return null; // disabled-button safety

      var contract = _getContract();
      var inputs = _collectInputs();
      state.lastDispatch = { slot: state.slotName, inputs: inputs };

      // Update UI to in-flight presentation
      state.inFlight = true;
      _refreshEnabled();
      _clearError();
      _clearResult();
      if (contract.execution_pattern === 'async') {
        _renderAsyncBadge();
      } else {
        _renderSpinner();
      }

      var detail = {
        slot: state.slotName,
        inputs: inputs,
        execution_pattern: contract.execution_pattern || 'sync',
        provider_override: inputs.provider_override || null,
      };

      _emit(state.hostEl, 'capability-dispatch', detail);
      if (typeof state.onDispatch === 'function') {
        try { state.onDispatch(detail); } catch (_e) { /* swallow */ }
      }
      return detail;
    }

    function _collectInputs() {
      var out = {};
      var names = Object.keys(state.inputControls);
      for (var i = 0; i < names.length; i++) {
        var name = names[i];
        var ctrl = state.inputControls[name];
        var v = ctrl.getValue();
        if (v == null) continue;
        // Don't record empty arrays / empty strings
        if (Array.isArray(v) && v.length === 0) continue;
        if (typeof v === 'string' && !v.length) continue;
        out[name] = v;
      }
      return out;
    }

    // ── Status presentations ─────────────────────────────────────────

    function _renderSpinner() {
      _clear(state.statusEl);
      var spin = _el('span', 'ora-cap-spinner', '');
      spin.setAttribute('aria-hidden', 'true');
      state.statusEl.appendChild(spin);
      state.statusEl.appendChild(document.createTextNode(' ' + SYNC_SPINNER_TEXT));
      state.statusEl.classList.remove('ora-cap-status--async');
      state.statusEl.classList.add('ora-cap-status--sync');
    }

    function _renderAsyncBadge() {
      _clear(state.statusEl);
      var badge = _el('span', 'ora-cap-badge', ASYNC_BADGE_TEXT);
      state.statusEl.appendChild(badge);
      state.statusEl.classList.remove('ora-cap-status--sync');
      state.statusEl.classList.add('ora-cap-status--async');
    }

    function _clearStatus() {
      _clear(state.statusEl);
      if (state.statusEl) {
        state.statusEl.classList.remove('ora-cap-status--sync');
        state.statusEl.classList.remove('ora-cap-status--async');
      }
    }

    // ── Error UX ──────────────────────────────────────────────────────

    function renderError(payload) {
      // payload: { code, message, fix_path? }
      // Look up the slot's declared common_errors[] for the canonical
      // fix-path text, falling back to whatever the dispatcher passed.
      var contract = _getContract();
      var common = (contract.common_errors || []).filter(function (e) {
        return e.code === payload.code;
      })[0] || {};
      var fixPath = payload.fix_path || common.fix_path || null;
      var description = payload.message || common.description || ('Error: ' + (payload.code || 'unknown'));

      _clear(state.errorEl);
      state.errorEl.style.display = '';
      state.errorEl.classList.add('ora-cap-error--visible');

      var head = _el('div', 'ora-cap-error__head');
      head.appendChild(_el('strong', null, 'Error'));
      if (payload.code) {
        var codeBadge = _el('span', 'ora-cap-error__code', payload.code);
        head.appendChild(codeBadge);
      }
      state.errorEl.appendChild(head);

      var msg = _el('p', 'ora-cap-error__msg', description);
      state.errorEl.appendChild(msg);

      if (fixPath) {
        var actions = _el('div', 'ora-cap-error__actions');
        var btn = _renderFixPathButton(fixPath);
        actions.appendChild(btn);
        state.errorEl.appendChild(actions);
      }

      state.inFlight = false;
      _clearStatus();
      _refreshEnabled();
    }

    function _renderFixPathButton(fixPath) {
      var lower = String(fixPath).toLowerCase();
      var btn = _el('button', 'ora-cap-fix-btn', fixPath);
      btn.type = 'button';

      var handler;
      if (lower.indexOf(FIX_PATH_CONFIGURE_PREFIX) === 0) {
        handler = function () { _emit(state.hostEl, 'open-settings', { fix_path: fixPath }); };
      } else if (lower.indexOf(FIX_PATH_MASK_PREFIX) === 0) {
        handler = function () { _emit(state.hostEl, 'activate-mask-tool', { fix_path: fixPath }); };
      } else if (lower === FIX_PATH_RETRY) {
        handler = function () {
          if (state.lastDispatch) {
            _clearError();
            // Re-run with the same inputs.
            // We don't try to re-validate against context; the user
            // intentionally retried.
            state.inFlight = true;
            _refreshEnabled();
            var contract = _getContract();
            if (contract.execution_pattern === 'async') {
              _renderAsyncBadge();
            } else {
              _renderSpinner();
            }
            var detail = {
              slot: state.slotName,
              inputs: state.lastDispatch.inputs,
              execution_pattern: contract.execution_pattern || 'sync',
              provider_override: state.lastDispatch.inputs.provider_override || null,
              retry: true,
            };
            _emit(state.hostEl, 'capability-dispatch', detail);
            if (typeof state.onDispatch === 'function') {
              try { state.onDispatch(detail); } catch (_e) {}
            }
          }
        };
      } else {
        // Unknown fix-path → render as a passive descriptive label
        // (still a button so screen readers reach it, but click is no-op).
        handler = function () { /* no-op for unknown fix paths */ };
        btn.classList.add('ora-cap-fix-btn--passive');
      }
      btn.addEventListener('click', function (e) { e.preventDefault(); handler(); });
      return btn;
    }

    function _clearError() {
      if (!state.errorEl) return;
      _clear(state.errorEl);
      state.errorEl.style.display = 'none';
      state.errorEl.classList.remove('ora-cap-error--visible');
    }

    // ── Result UX ────────────────────────────────────────────────────

    function renderResult(payload) {
      // Sync result rendering. Async results normally land in the queue
      // / chat stream (per §11.6, WP-7.6.x); we still accept renderResult
      // here so callers without a queue UI have a fallback.
      state.inFlight = false;
      _clearStatus();
      _refreshEnabled();

      _clear(state.resultEl);
      state.resultEl.style.display = '';
      state.resultEl.classList.add('ora-cap-result--visible');

      var contract = _getContract();
      var outType = (contract.output && contract.output.type) || 'text';

      var head = _el('div', 'ora-cap-result__head');
      head.appendChild(_el('strong', null, 'Result'));
      var typeBadge = _el('span', 'ora-cap-result__type', outType);
      head.appendChild(typeBadge);
      state.resultEl.appendChild(head);

      // Best-effort renderers per output type. These are intentionally
      // simple — image-bytes / video-bytes lands on canvas in real life,
      // not in this panel; we just confirm receipt here.
      if (outType === 'text') {
        var pre = _el('pre', 'ora-cap-result__text', String(payload.output || ''));
        state.resultEl.appendChild(pre);
      } else if (outType === 'image-bytes') {
        if (payload.imageDataUrl) {
          var img = _el('img', 'ora-cap-result__img');
          img.src = payload.imageDataUrl;
          img.alt = 'Generated image';
          state.resultEl.appendChild(img);
        } else {
          state.resultEl.appendChild(_el('p', 'ora-cap-result__msg', 'Image delivered to canvas.'));
        }
      } else if (outType === 'images-list') {
        state.resultEl.appendChild(_el('p', 'ora-cap-result__msg',
          'Image set delivered (' + ((payload.output && payload.output.length) || 0) + ' items).'));
      } else if (outType === 'video-bytes') {
        state.resultEl.appendChild(_el('p', 'ora-cap-result__msg',
          'Video will arrive in the chat output stream.'));
      } else if (outType === 'style-adapter-id') {
        state.resultEl.appendChild(_el('p', 'ora-cap-result__msg',
          'Style adapter registered: ' + (payload.output || '(unnamed)')));
      } else {
        var fallback = _el('pre', 'ora-cap-result__text');
        try { fallback.textContent = JSON.stringify(payload.output, null, 2); }
        catch (_e) { fallback.textContent = String(payload.output); }
        state.resultEl.appendChild(fallback);
      }
    }

    function _clearResult() {
      if (!state.resultEl) return;
      _clear(state.resultEl);
      state.resultEl.style.display = 'none';
      state.resultEl.classList.remove('ora-cap-result--visible');
    }

    // ── External API ─────────────────────────────────────────────────

    function setSlot(slotName) {
      state.slotName = slotName;
      _render();
    }

    function setContextProvider(fn) {
      state.contextProvider = (typeof fn === 'function') ? fn : function () { return {}; };
      // Prompt any context-aware controls (image-ref, mask) to refresh.
      Object.keys(state.inputControls).forEach(function (name) {
        var c = state.inputControls[name];
        if (c && typeof c.refresh === 'function') c.refresh();
      });
      _refreshEnabled();
    }

    function destroy() {
      if (state.destroyed) return;
      state.destroyed = true;
      if (state.formEl && state.formEl.parentNode) {
        state.formEl.parentNode.removeChild(state.formEl);
      }
      state.formEl = null;
      state.runBtn = null;
      state.tooltipEl = null;
      state.statusEl = null;
      state.errorEl = null;
      state.resultEl = null;
      state.inputControls = {};
    }

    // ── Boot ─────────────────────────────────────────────────────────

    if (!state.hostEl) {
      throw new Error('capability-invocation-ui: hostEl is required');
    }
    if (!state.slotName) {
      throw new Error('capability-invocation-ui: slotName is required');
    }
    _render();

    return {
      setSlot: setSlot,
      setContextProvider: setContextProvider,
      refreshEnabledState: _refreshEnabled,
      submit: submit,
      renderError: renderError,
      renderResult: renderResult,
      destroy: destroy,
      getInputs: _collectInputs,
      _state: state,        // exposed for tests only
    };
  }

  // ── File-reader helper ────────────────────────────────────────────────

  function _readFileAsBase64(file) {
    return new Promise(function (resolve, reject) {
      if (typeof FileReader === 'undefined') {
        reject(new Error('FileReader unavailable'));
        return;
      }
      var fr = new FileReader();
      fr.onload = function () {
        var result = fr.result || '';
        var idx = String(result).indexOf('base64,');
        resolve(idx >= 0 ? String(result).slice(idx + 7) : String(result));
      };
      fr.onerror = function () { reject(fr.error || new Error('FileReader error')); };
      fr.readAsDataURL(file);
    });
  }

  // ── Module-level "active" controller ──────────────────────────────────

  var _activeController = null;

  function init(opts) {
    var ctl = _makeController(opts || {});
    _activeController = ctl;
    return ctl;
  }

  function _delegate(method) {
    return function () {
      if (!_activeController) return null;
      return _activeController[method].apply(_activeController, arguments);
    };
  }

  var api = {
    init: init,
    setSlot: _delegate('setSlot'),
    setContextProvider: _delegate('setContextProvider'),
    refreshEnabledState: _delegate('refreshEnabledState'),
    submit: _delegate('submit'),
    renderError: _delegate('renderError'),
    renderResult: _delegate('renderResult'),
    destroy: function () {
      if (_activeController) _activeController.destroy();
      _activeController = null;
    },
    getInputs: _delegate('getInputs'),
    _getActive: function () { return _activeController; },
    // Test introspection
    _readFileAsBase64: _readFileAsBase64,
    FIX_PATH_CONFIGURE_PREFIX: FIX_PATH_CONFIGURE_PREFIX,
    FIX_PATH_MASK_PREFIX: FIX_PATH_MASK_PREFIX,
    FIX_PATH_RETRY: FIX_PATH_RETRY,
    ASYNC_BADGE_TEXT: ASYNC_BADGE_TEXT,
    SYNC_SPINNER_TEXT: SYNC_SPINNER_TEXT,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraCapabilityInvocationUI = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
