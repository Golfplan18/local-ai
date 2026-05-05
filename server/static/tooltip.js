/* tooltip.js — Universal hover tooltip layer for Ora V3.
 *
 * Watches every mouseover on the page. When the cursor settles on an
 * element with a `title`, `aria-label`, or `data-tip` attribute, a
 * themed tooltip fades in after a short delay. Works for any
 * interactive element — buttons, links, list rows, toolbar items,
 * settings fields — without per-element wiring.
 *
 * Why a global helper instead of native browser tooltips?
 *   Native `title=""` tooltips work but their styling is owned by the
 *   OS, can't honor the Ora theme, and don't unify look across V3.
 *   This helper renders one styled tooltip element per document,
 *   themed via CSS variables so it tracks the active theme. The
 *   `title` attribute is preserved (moved to `data-orig-title` while
 *   the helper is active) so screenreaders and a disabled-helper
 *   fallback still work.
 *
 * Public API (exposed on window.OraTooltip)
 *   init(opts?)               — bind the global mouseover listener
 *   enable()                  — turn the helper on (default state after init)
 *   disable()                 — turn off; restores native title attributes
 *   isEnabled()               — boolean
 *   setDelay(ms)              — change the hover-to-show delay
 *   destroy()                 — full teardown
 *
 * Skipped contexts
 *   - The visual-toolbar's own tooltip system handles `.ora-toolbar__item`.
 *     We skip those so the two systems don't double-fire.
 *   - Form inputs (input/textarea/select) — the browser's behavior is
 *     more appropriate; native tooltips on form fields are uncommon.
 *   - Elements with `data-no-tooltip="true"` opt out explicitly.
 */
(function (root) {
  'use strict';

  if (typeof root === 'undefined') return;

  var DEFAULT_DELAY_MS = 500;
  var OFFSET_PX = 10;
  var EDGE_GUARD_PX = 6;

  var _state = {
    initialized: false,
    enabled: true,
    delayMs: DEFAULT_DELAY_MS,
    listenerOver: null,
    listenerOut: null,
    listenerScroll: null,
    listenerKeydown: null,
    surface: null,
    timerId: null,
    anchor: null,
  };

  // ---- text resolution -----------------------------------------------------

  function _findAnchor(target) {
    var el = target;
    while (el && el.nodeType === 1) {
      if (el.getAttribute('data-no-tooltip') === 'true') return null;
      // Skip elements the toolbar's own tooltip already covers.
      if (el.classList && el.classList.contains('ora-toolbar__item')) return null;
      // Skip form inputs — native browser handling is more appropriate.
      var tag = el.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return null;
      var text = _readTipText(el);
      if (text) return el;
      el = el.parentElement;
    }
    return null;
  }

  function _readTipText(el) {
    if (!el || el.nodeType !== 1) return '';
    // Preference order: explicit data-tip > original-title (set by us)
    // > current title > aria-label.
    var v = el.getAttribute('data-tip');
    if (v) return v;
    v = el.getAttribute('data-orig-title');
    if (v) return v;
    v = el.getAttribute('title');
    if (v) {
      // Move into data-orig-title so the native browser tooltip won't
      // also fire for this element while the helper is active.
      el.setAttribute('data-orig-title', v);
      el.removeAttribute('title');
      return v;
    }
    v = el.getAttribute('aria-label');
    if (v && (v.length > 1)) return v;  // skip single-letter labels (close X etc.)
    return '';
  }

  // ---- surface element -----------------------------------------------------

  function _ensureSurface() {
    if (_state.surface && _state.surface.parentNode) return _state.surface;
    var el = document.createElement('div');
    el.className = 'ora-tooltip';
    el.setAttribute('role', 'tooltip');
    el.setAttribute('aria-hidden', 'true');
    var s = el.style;
    s.position = 'fixed';
    s.zIndex = '10001';
    s.pointerEvents = 'none';
    s.opacity = '0';
    s.transition = 'opacity 120ms ease-out';
    s.background = 'var(--ora-tooltip-bg, rgba(20, 22, 28, 0.95))';
    s.color = 'var(--ora-tooltip-fg, #f6f7f9)';
    s.font = '12px/1.35 var(--ora-tooltip-font, system-ui, -apple-system, sans-serif)';
    s.padding = '6px 9px';
    s.borderRadius = '4px';
    s.maxWidth = '320px';
    s.whiteSpace = 'normal';
    s.boxShadow = '0 2px 8px rgba(0,0,0,0.25)';
    s.top = '0px';
    s.left = '0px';
    s.visibility = 'hidden';
    document.body.appendChild(el);
    _state.surface = el;
    return el;
  }

  function _positionSurface(anchor) {
    var el = _state.surface;
    if (!el || !anchor) return;
    var rect = anchor.getBoundingClientRect();
    el.style.visibility = 'hidden';
    el.style.left = '0px';
    el.style.top = '0px';
    var tip = el.getBoundingClientRect();
    var vw = window.innerWidth || document.documentElement.clientWidth || 1024;
    var vh = window.innerHeight || document.documentElement.clientHeight || 768;

    // Default: below the anchor. Flip above when there isn't room.
    var spaceBelow = vh - rect.bottom;
    var spaceAbove = rect.top;
    var placement = (spaceBelow < tip.height + OFFSET_PX + EDGE_GUARD_PX
                     && spaceAbove > spaceBelow) ? 'above' : 'below';
    var top = (placement === 'below')
      ? rect.bottom + OFFSET_PX
      : rect.top - tip.height - OFFSET_PX;

    var center = rect.left + (rect.width / 2);
    var left = center - (tip.width / 2);
    if (left < EDGE_GUARD_PX) left = EDGE_GUARD_PX;
    if (left + tip.width > vw - EDGE_GUARD_PX) left = vw - tip.width - EDGE_GUARD_PX;

    el.style.left = Math.round(left) + 'px';
    el.style.top = Math.round(top) + 'px';
    el.style.visibility = 'visible';
  }

  function _showFor(anchor, text) {
    if (!_state.enabled) return;
    var el = _ensureSurface();
    el.textContent = text;
    el.setAttribute('aria-hidden', 'false');
    el.style.opacity = '1';
    _positionSurface(anchor);
  }

  function _hideNow() {
    if (_state.timerId) {
      try { clearTimeout(_state.timerId); } catch (e) { /* ignore */ }
      _state.timerId = null;
    }
    if (_state.surface) {
      _state.surface.style.opacity = '0';
      _state.surface.style.visibility = 'hidden';
      _state.surface.setAttribute('aria-hidden', 'true');
    }
    _state.anchor = null;
  }

  // ---- event handlers ------------------------------------------------------

  function _onMouseOver(evt) {
    if (!_state.enabled) return;
    var anchor = _findAnchor(evt.target);
    if (!anchor) {
      // Movement off any tip-bearing element ends the show timer.
      if (_state.anchor) _hideNow();
      return;
    }
    if (_state.anchor === anchor) return;  // already armed for this element
    if (_state.timerId) {
      try { clearTimeout(_state.timerId); } catch (e) { /* ignore */ }
      _state.timerId = null;
    }
    _state.anchor = anchor;
    var text = _readTipText(anchor);
    if (!text) return;
    _state.timerId = setTimeout(function () {
      _state.timerId = null;
      if (_state.anchor !== anchor) return;
      _showFor(anchor, text);
    }, _state.delayMs);
  }

  function _onMouseOut(evt) {
    var goingTo = evt.relatedTarget;
    if (!goingTo || (_state.anchor && !_state.anchor.contains(goingTo))) {
      _hideNow();
    }
  }

  function _onScrollOrKey() {
    _hideNow();
  }

  // ---- public API ----------------------------------------------------------

  function init(opts) {
    opts = opts || {};
    if (_state.initialized) return;
    if (typeof opts.delay === 'number' && opts.delay >= 0) _state.delayMs = opts.delay;
    if (opts.enabled === false) _state.enabled = false;
    _state.listenerOver = _onMouseOver;
    _state.listenerOut = _onMouseOut;
    _state.listenerScroll = _onScrollOrKey;
    _state.listenerKeydown = _onScrollOrKey;
    document.addEventListener('mouseover', _state.listenerOver, true);
    document.addEventListener('mouseout', _state.listenerOut, true);
    window.addEventListener('scroll', _state.listenerScroll, true);
    document.addEventListener('keydown', _state.listenerKeydown, true);
    _state.initialized = true;
  }

  function enable() {
    _state.enabled = true;
    // Re-claim title attributes from elements the user may have hovered
    // since disable() restored them. Lazy: happens on next mouseover.
  }

  function disable() {
    _state.enabled = false;
    _hideNow();
    // Restore native titles so the user still gets OS-level tooltips.
    if (typeof document === 'undefined') return;
    var els = document.querySelectorAll('[data-orig-title]');
    Array.prototype.forEach.call(els, function (el) {
      var v = el.getAttribute('data-orig-title');
      if (v && !el.getAttribute('title')) el.setAttribute('title', v);
      el.removeAttribute('data-orig-title');
    });
  }

  function isEnabled() { return !!_state.enabled; }

  function setDelay(ms) {
    if (typeof ms === 'number' && ms >= 0) _state.delayMs = ms;
  }

  function destroy() {
    _hideNow();
    if (_state.surface && _state.surface.parentNode) {
      _state.surface.parentNode.removeChild(_state.surface);
    }
    if (_state.listenerOver) document.removeEventListener('mouseover', _state.listenerOver, true);
    if (_state.listenerOut) document.removeEventListener('mouseout', _state.listenerOut, true);
    if (_state.listenerScroll) window.removeEventListener('scroll', _state.listenerScroll, true);
    if (_state.listenerKeydown) document.removeEventListener('keydown', _state.listenerKeydown, true);
    _state.initialized = false;
    _state.surface = null;
    _state.listenerOver = null;
    _state.listenerOut = null;
    _state.listenerScroll = null;
    _state.listenerKeydown = null;
  }

  root.OraTooltip = {
    init: init,
    enable: enable,
    disable: disable,
    isEnabled: isEnabled,
    setDelay: setDelay,
    destroy: destroy,
    _state: _state  // for tests
  };
})(typeof window !== 'undefined' ? window : this);
