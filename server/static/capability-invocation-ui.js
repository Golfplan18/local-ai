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
 * ── Where a failure goes ──────────────────────────────────────────────
 * Capability modules report failures through the module-level singleton
 * (`state.ui.renderError`), not through a controller handle of their own.
 * By the time most failures arrive there is no popover left to render
 * into: v3-pack-toolbars.js closes the popover 250 ms after dispatch and
 * that close calls `controller.destroy()`, which nulls `state.errorEl`.
 * And `image_generates` is dispatched from three places with no popover
 * at all (index-v3.html, js/slash-command-client.js,
 * prompt-template-runtime.js).
 *
 * So the singleton's `renderError` is not a plain delegate. It routes:
 *
 *   1. the live popover — but only when it is genuinely live (not
 *      destroyed, error element still attached) AND it belongs to the
 *      slot the failure came from. Without the slot test, a late failure
 *      from slot A painted into whatever popover slot B had opened since,
 *      wearing B's fix-path button, and cleared B's in-flight state while
 *      B's own request was still running;
 *   2. otherwise the Exhibits pane error bar via
 *      `OraPanels.visual._getActive()._showErrorBar()` — the surface that
 *      outlives the popover, and the same strip tools/image-edits.js
 *      writes to. Both writers clear only their own text, so neither
 *      retracts the other's message;
 *   3. otherwise `console.warn`. Never wholly silent.
 *
 * A pane message is retracted from two places, because no single one sees
 * every run: `submit()` clears at the start of a popover-driven run, and
 * the singleton's `renderResult` clears when any run succeeds — including
 * the three popover-less `image_generates` dispatches, which never call
 * `submit()` and would otherwise leave a dead failure pinned over the
 * image the next successful run just produced.
 *
 * ── Where a result goes ───────────────────────────────────────────────
 * A result is in exactly the same position as a failure, and for the same
 * reason: it arrives after the popover that asked for it is gone. Three
 * slots return something the user has to READ rather than something that
 * lands on the canvas — `image_varies` (a chooser of candidates),
 * `image_critique` (a rubric plus prose), `image_to_prompt` (a prompt
 * string) — and each of them was painting into `document.body`. The shell
 * is `height: 100vh` with `html, body { overflow: hidden }`, so a node
 * appended below it cannot be scrolled to. It existed and no one could
 * ever see it.
 *
 * So `renderResult` routes the same way `renderError` does, and
 * `getResultHost(slot)` names the element a module should paint into:
 *
 *   1. the live popover's `.ora-cap-result` — but only when the popover
 *      belongs to the slot the result came from. Without the slot test a
 *      late result painted into whatever popover was open since, clearing
 *      that popover's in-flight state while its own request was still
 *      running (the same contamination `renderError` was given a guard
 *      for, still present here);
 *   2. otherwise the docked browse overlay (v3-browse-overlay.js),
 *      registered once on first use and opened on demand. One
 *      `.ora-cap-result` per slot inside it, so two slots' results sit side
 *      by side rather than one appending into the other's panel;
 *   3. otherwise `null` — every caller must survive that without throwing,
 *      and `getResultHost` warns on the way out, because a null host means
 *      the result is dropped. There is no third surface: a result is
 *      content, not a one-line verdict, so it does not fit the pane's
 *      error bar.
 *
 * What the dock costs, stated plainly. It is non-modal in the sense that
 * matters for the canvas — no backdrop, no focus trap, the drawing surface
 * and the rest of the shell stay live — but it is not free:
 *
 *   - the dock holds ONE surface. `OraBrowseOverlays.open()` calls
 *     `_closeOthers`, so a result arriving after the user opened the
 *     Library closes the Library out from under them, with no warning and
 *     nothing put back when the result is dismissed;
 *   - its geometry is the input pane's rect inset by 8 px (see `_position`
 *     in v3-browse-overlay.js), so while it is open it covers the input
 *     pane the user types into.
 *
 * Both are the shared dock's behaviour, not this module's, and are left
 * alone deliberately: a second dock or a per-surface geometry would be a
 * new surface to own. The point here is that "non-modal" is true of the
 * canvas and false of the Library and the input pane.
 *
 * Nothing is persisted. A result lives until the overlay is closed.
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
 *   .renderError(payload)           — surface an error from outside.
 *                        Tag the payload with `slot` when calling through
 *                        the singleton: the singleton routes a failure to
 *                        the popover only when the live popover belongs to
 *                        that slot, and to the Exhibits pane error bar
 *                        otherwise (see "Where a failure goes" above).
 *   .renderResult(payload)          — surface a result from outside.
 *                        Tag the payload with `slot` for the same reason
 *                        `renderError` wants one (see "Where a result
 *                        goes" above).
 *   .getResultHost(slot)            — the element a module should paint a
 *                        result into: the live popover's result panel for
 *                        that slot, else the docked browse overlay's body,
 *                        else null.
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

  // User-authored content fields that capability handlers send to a model or
  // provider. Text controls such as adapter `name` and fixed `system_prompt`
  // configuration are deliberately outside the dialogue privacy boundary.
  var PRIVACY_TEXT_INPUTS = {
    prompt: true,
    user_prompt: true,
    rubric: true,
    genre: true,
    style: true,
  };

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

    function _privacyPrompt(inputs, approvedText) {
      var contract = _getContract();
      var specs = (contract.required_inputs || []).concat(contract.optional_inputs || []);
      var values = [];
      for (var i = 0; i < specs.length; i++) {
        var spec = specs[i];
        if (spec.type !== 'text' || !PRIVACY_TEXT_INPUTS[spec.name]) continue;
        var value = inputs && inputs[spec.name];
        if (typeof value !== 'string' || !value.trim()) continue;
        value = value.trim();
        if (typeof approvedText === 'string' && value === approvedText.trim()) continue;
        values.push(value);
      }
      return values.join('\n\n');
    }

    function _emitDispatch(detail) {
      var conversation = root && root.OraConversation;
      if (conversation && typeof conversation.getActiveConversationId === 'function') {
        detail.conversation_id = conversation.getActiveConversationId();
      }
      if (conversation && typeof conversation.getActiveTag === 'function') {
        detail.tag = conversation.getActiveTag();
      }
      _emit(state.hostEl, 'capability-dispatch', detail);
      if (typeof state.onDispatch === 'function') {
        try { state.onDispatch(detail); } catch (_e) { /* swallow */ }
      }
      return detail;
    }

    function _dispatchAfterPrivacy(detail, options) {
      var privacyText = _privacyPrompt(
        detail.inputs, options && options.privacyApprovedText
      );
      if (!privacyText) {
        return _emitDispatch(detail);
      }
      var conversation = root && root.OraConversation;
      if (!conversation || typeof conversation.submitAfterPrivacy !== 'function') {
        renderError({
          code: 'privacy_unavailable',
          message: 'Dialogue privacy controls are unavailable; prompt was not sent.',
        });
        return null;
      }
      return Promise.resolve(conversation.submitAfterPrivacy(
        privacyText,
        function () { return _emitDispatch(detail); },
        { draftText: privacyText }
      )).then(function (submitted) {
        if (submitted) return detail;
        state.inFlight = false;
        _clearStatus();
        _refreshEnabled();
        return null;
      }, function (error) {
        renderError({
          code: 'privacy_unavailable',
          message: 'Privacy check failed; prompt was not sent: '
            + ((error && error.message) || String(error)),
        });
        return null;
      });
    }

    function submit(options) {
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
      // A previous run's verdict on the Exhibits pane must not outlive the
      // run it described. Only this layer's own message is retracted.
      // This is the start-of-run half; the singleton's `renderResult`
      // retracts at end-of-run for the dispatch paths that never call
      // submit(). Both are needed: image_outpaints reports failures but
      // never calls renderResult, so submit() is its only retraction, and
      // clearing here also stops a stale verdict sitting over a run that
      // is still in flight.
      _clearPaneError();
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

      return _dispatchAfterPrivacy(detail, options || {});
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
        // Pass the surrounding error context into the fix-path button
        // factory — `_renderFixPathButton` is a sibling function (not
        // nested) so it doesn't see `description` / `payload` via
        // closure. The settings-panel.js open-settings listener uses
        // the message text to substring-match a provider name; without
        // it here the regression introduced 2026-05-11 silently broke
        // the configure-fix-path button entirely (the test harness in
        // tests/test-capability-invocation-ui.js caught it).
        var errorCtx = {
          message: description,
          code: payload && payload.code,
        };
        var btn = _renderFixPathButton(fixPath, errorCtx);
        actions.appendChild(btn);
        state.errorEl.appendChild(actions);
      }

      state.inFlight = false;
      _clearStatus();
      _refreshEnabled();
    }

    function _renderFixPathButton(fixPath, errorCtx) {
      errorCtx = errorCtx || {};
      var lower = String(fixPath).toLowerCase();
      var btn = _el('button', 'ora-cap-fix-btn', fixPath);
      btn.type = 'button';

      var handler;
      if (lower.indexOf(FIX_PATH_CONFIGURE_PREFIX) === 0) {
        // The downstream listener (settings-panel.js) opens the
        // Settings modal on the External APIs tab and uses
        // `message` to heuristically highlight a specific provider
        // row when the error text names one (e.g., "OpenAI",
        // "Gemini", "Stability"). ``slot`` is included for future
        // listeners that want to render slot-specific help.
        handler = function () {
          _emit(state.hostEl, 'open-settings', {
            fix_path: fixPath,
            message: errorCtx.message,
            slot: state.slotName,
            code: errorCtx.code,
          });
        };
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
            _dispatchAfterPrivacy(detail, {});
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
        // `output` is the batch id, a string — image_varies hands the images
        // themselves in `payload.images`. Reading `.length` off the id
        // counted its characters: "Image set delivered (29 items)" for four.
        var batch = Array.isArray(payload.images) ? payload.images
          : (Array.isArray(payload.output) ? payload.output : []);
        state.resultEl.appendChild(_el('p', 'ora-cap-result__msg',
          'Image set delivered (' + batch.length + ' items).'));
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

  // ── Error routing (see "Where a failure goes" at the top of the file) ──

  // The exact text this layer last wrote to the Exhibits pane error bar.
  // Only that text may be retracted — the bar is shared with the compiler,
  // the image-upload path, and tools/image-edits.js.
  var _paneErrorText = null;

  function _liveControllerFor(slot) {
    var ctl = _activeController;
    if (!ctl) return null;
    var st = ctl._state;
    // A controller with no elements cannot show the user anything, and
    // both the error and the result element are created together in
    // _render() and nulled together in destroy() — there is no state where
    // one exists and the other does not, so this one test covers a
    // torn-down popover for either caller.
    if (!st || !st.errorEl) return null;
    // An untagged payload can't be attributed to a slot, so it may only
    // render into the popover it was almost certainly meant for.
    if (slot && st.slotName !== slot) return null;
    return ctl;
  }

  function _activePanel() {
    var visual = root && root.OraPanels && root.OraPanels.visual;
    if (!visual || typeof visual._getActive !== 'function') return null;
    try {
      return visual._getActive() || null;
    } catch (_e) {
      return null;
    }
  }

  function _showPaneError(slot, payload) {
    var panel = _activePanel();
    // `_showErrorBar` opens `if (!this._errorBar) return;` — a silent
    // no-op. Returning true off "it didn't throw" would report a message
    // the user cannot read and skip the console.warn arm below, which is
    // the last surface there is. Check the bar itself, not just the method.
    if (!panel || !panel._errorBar || typeof panel._showErrorBar !== 'function') return false;
    var text = (slot || 'Capability') + ' failed ['
      + ((payload && payload.code) || 'unknown') + '] — '
      + ((payload && payload.message) || 'No further detail was returned.');
    try {
      panel._showErrorBar(text);
      _paneErrorText = text;
      return true;
    } catch (_e) {
      return false;
    }
  }

  /**
   * Retract this layer's own pane message at the start of a new run.
   * Clears only when the bar still carries the exact text we wrote, so a
   * compile error or an upload warning that has since replaced it — or a
   * message tools/image-edits.js owns — survives untouched.
   */
  function _clearPaneError() {
    if (_paneErrorText == null) return;
    var panel = _activePanel();
    var bar = panel && panel._errorBar;
    if (bar) {
      try {
        if (bar.textContent === _paneErrorText) {
          bar.textContent = '';
          bar.hidden = true;
        }
      } catch (_e) { /* swallow — a bar we can't touch is not a failure */ }
    }
    _paneErrorText = null;
  }

  /**
   * Singleton-level error reporting. Takes the same payload the controller
   * takes, plus an optional `slot`.
   *
   * @returns {boolean|undefined} whatever the popover render returned when
   *   it took the error; true when the pane bar took it; false when only
   *   the console did.
   */
  function reportError(payload) {
    payload = payload || {};
    var slot = payload.slot || null;

    var ctl = _liveControllerFor(slot);
    if (ctl) return ctl.renderError(payload);

    if (_showPaneError(slot, payload)) return true;

    // No popover and no pane. Fail open, loudly — a swallowed failure is
    // what this whole path exists to stop.
    if (typeof console !== 'undefined' && console && typeof console.warn === 'function') {
      console.warn('[capability-invocation-ui] ' + (slot || 'unknown slot')
        + ' failed [' + (payload.code || 'unknown') + '] — '
        + (payload.message || 'no message')
        + ' (no invocation popover and no Exhibits pane to show it in)');
    }
    return false;
  }

  /**
   * Singleton-level result reporting. A success is the other half of the
   * retraction: `submit()` clears at the start of a run, but the three
   * popover-less dispatch paths (index-v3.html, js/slash-command-client.js,
   * prompt-template-runtime.js) never call `submit()`, so without this a
   * failed run's pane verdict outlived the next SUCCESSFUL run and sat
   * pinned over the fresh image. Every module that can reach the pane on
   * failure also calls `renderResult` on success, so clearing here covers
   * the paths `submit()` cannot see.
   */
  function reportResult(payload) {
    payload = payload || {};
    // Retraction is deliberately not slot-scoped. The bar holds one
    // message, this layer wrote it, and any run that succeeds has ended
    // the episode it described — which is the whole point of the
    // end-of-run half, since the popover-less paths never call submit().
    _clearPaneError();
    // The delegation IS slot-scoped, for the reason renderError is: a
    // destroyed controller throws on `state.resultEl.style`, and a live
    // controller for a DIFFERENT slot takes a result that was never its
    // own — clearing its in-flight state and its spinner mid-request.
    var ctl = _liveControllerFor(payload.slot || null);
    if (!ctl) return null;
    return ctl.renderResult(payload);
  }

  // ── Result routing (see "Where a result goes" at the top of the file) ──

  // The docked browse surface a result falls back to. Registered on first
  // use and never again: `register` rejects a duplicate id outright, and
  // re-registering per dispatch would strand a record and an unregister
  // handle for every run.
  var RESULT_OVERLAY_ID = 'capability-results';
  var RESULT_OVERLAY_LABEL = 'Capability results';
  var _resultOverlayRegistered = false;
  // Only ever set from inside the overlay's own render callback: the
  // overlay repaints its body from scratch on every open, so a handle
  // taken anywhere else can be one the surface has already discarded.
  var _resultOverlayBody = null;

  function _browseOverlays() {
    var overlays = root && root.OraBrowseOverlays;
    if (!overlays || typeof overlays.register !== 'function'
        || typeof overlays.open !== 'function') return null;
    return overlays;
  }

  function _ensureResultOverlay() {
    var overlays = _browseOverlays();
    if (!overlays) return null;
    if (_resultOverlayRegistered) return overlays;
    if (typeof overlays.has === 'function' && overlays.has(RESULT_OVERLAY_ID)) {
      _resultOverlayRegistered = true;
      return overlays;
    }
    try {
      overlays.register({
        id: RESULT_OVERLAY_ID,
        label: RESULT_OVERLAY_LABEL,
        render: function (body) { _resultOverlayBody = body; },
        onClose: function () { _resultOverlayBody = null; },
      });
    } catch (_e) {
      return null;
    }
    // register() warns and hands back a no-op unregister rather than
    // throwing, so "did it take" is only answerable by asking.
    if (typeof overlays.has === 'function' && !overlays.has(RESULT_OVERLAY_ID)) return null;
    _resultOverlayRegistered = true;
    return overlays;
  }

  // One `.ora-cap-result` per slot inside the dock. Without it, a critique
  // and a prompt would share a container and the second module's
  // `querySelector('.ora-cap-result')` would decorate the first one's
  // panel; with it, a re-run of the same slot repaints its own box.
  function _slotResultBox(body, slot) {
    var key = slot || 'capability';
    var kids = body.children || [];
    for (var i = 0; i < kids.length; i++) {
      var kid = kids[i];
      if (kid && typeof kid.getAttribute === 'function'
          && kid.getAttribute('data-ora-result-slot') === key) return kid;
    }
    if (typeof document === 'undefined') return null;
    var box = _el('div', 'ora-cap-result ora-cap-result--overlay ora-cap-result--visible');
    // An attribute value, never a selector: a slot name is config-supplied
    // and must stay inert.
    box.setAttribute('data-ora-result-slot', key);
    var head = _el('div', 'ora-cap-result__head');
    head.appendChild(_el('strong', null, 'Result'));
    head.appendChild(_el('span', 'ora-cap-result__type', key));
    box.appendChild(head);
    body.appendChild(box);
    return box;
  }

  function _overlayResultHost(slot) {
    var overlays = _ensureResultOverlay();
    if (!overlays) return null;
    var alreadyOpen = (typeof overlays.isOpen === 'function')
      && overlays.isOpen(RESULT_OVERLAY_ID);
    if (!alreadyOpen) {
      _resultOverlayBody = null;
      // Synchronous: open() paints, which runs the render callback above.
      overlays.open(RESULT_OVERLAY_ID);
    }
    var body = _resultOverlayBody;
    if (!body || typeof body.appendChild !== 'function') return null;
    return _slotResultBox(body, slot);
  }

  /**
   * The element a module should paint a result into.
   *
   * @param {string} slot — the slot the result belongs to. Omitting it
   *   means "whatever popover is live", which is only right for a caller
   *   that cannot be wrong about it.
   * @returns {Element|null} null when there is no popover for this slot
   *   and no browse overlay to fall back on. Callers must handle it.
   */
  function getResultHost(slot) {
    var ctl = _liveControllerFor(slot || null);
    var st = ctl && ctl._state;
    if (st && st.resultEl) {
      // A hidden result panel is the same as no panel at all. renderResult
      // reveals it, but a module is entitled to ask for the host first, so
      // handing back a `display: none` element would recreate the exact
      // failure this function exists to end.
      st.resultEl.style.display = '';
      st.resultEl.classList.add('ora-cap-result--visible');
      return st.resultEl;
    }
    var host = _overlayResultHost(slot);
    if (!host && typeof console !== 'undefined' && console
        && typeof console.warn === 'function') {
      // Returning null is a dropped result — the module has nowhere to
      // paint and its whole output goes nowhere. Legitimate when the host
      // page never loaded the browse overlay; a symptom when it did, e.g.
      // something else already registered `capability-results` so our
      // render callback was never installed and the body handle stays
      // null. Either way it says so rather than failing closed or quietly.
      console.warn('[capability-invocation-ui] ' + (slot || 'unknown slot')
        + ' produced a result with nowhere to show it — no live popover for'
        + ' the slot and no browse-overlay dock. The result is dropped.');
    }
    return host;
  }

  var api = {
    init: init,
    setSlot: _delegate('setSlot'),
    setContextProvider: _delegate('setContextProvider'),
    refreshEnabledState: _delegate('refreshEnabledState'),
    submit: _delegate('submit'),
    renderError: reportError,
    renderResult: reportResult,
    getResultHost: getResultHost,
    destroy: function () {
      if (_activeController) _activeController.destroy();
      _activeController = null;
    },
    getInputs: _delegate('getInputs'),
    _getActive: function () { return _activeController; },
    // Test introspection
    _readFileAsBase64: _readFileAsBase64,
    RESULT_OVERLAY_ID: RESULT_OVERLAY_ID,
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
