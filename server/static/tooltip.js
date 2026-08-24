/* tooltip.js — the shared tooltip renderer for the Ora surface. */
(function (root) {
  'use strict';

  var SURFACE_ID = 'ora-shared-tooltip';
  var OWNED_TITLE_ATTRIBUTE = 'data-ora-tooltip-native-title';
  var DEFAULT_DELAY_MS = 500;
  var OFFSET_PX = 10;
  var EDGE_GUARD_PX = 6;
  var state = {
    initialized: false,
    enabled: true,
    delayMs: DEFAULT_DELAY_MS,
    surface: null,
    anchor: null,
    nativeTitle: null,
    timerId: null,
    anchorObserver: null,
    bodyObserver: null,
    chromeHidden: false,
    listeners: []
  };

  function _clearTimer() {
    if (state.timerId !== null) {
      clearTimeout(state.timerId);
      state.timerId = null;
    }
  }

  function _surface() {
    if (state.surface && state.surface.ownerDocument) return state.surface;
    var doc = root.document;
    if (!doc) return null;
    var surface = doc.getElementById(SURFACE_ID);
    if (!surface) {
      surface = doc.createElement('div');
      surface.id = SURFACE_ID;
      surface.className = 'ora-tooltip';
      surface.setAttribute('role', 'tooltip');
      surface.setAttribute('aria-hidden', 'true');
      var parent = doc.body || doc.documentElement;
      if (parent) parent.appendChild(surface);
    }
    surface.className = surface.className || 'ora-tooltip';
    surface.setAttribute('role', 'tooltip');
    surface.setAttribute('aria-hidden', surface.getAttribute('aria-hidden') || 'true');
    surface.style.position = 'fixed';
    surface.style.zIndex = '10001';
    surface.style.pointerEvents = 'none';
    surface.style.maxWidth = 'min(320px, calc(100vw - 12px))';
    surface.style.visibility = surface.getAttribute('aria-hidden') === 'false' ? 'visible' : 'hidden';
    state.surface = surface;
    return surface;
  }

  function _textFor(el) {
    if (!el || !el.getAttribute) return '';
    var text = el.getAttribute('data-tooltip');
    if (text) return text;
    if (state.anchor === el && state.nativeTitle !== null) return state.nativeTitle;
    text = el.getAttribute('title');
    if (text) return text;
    text = el.getAttribute('aria-label');
    return text && text.length > 1 ? text : '';
  }

  function _isHiddenByChrome(el) {
    if (state.chromeHidden || !el) return true;
    if (el.closest) {
      return !!el.closest('.visual-panel.chrome-hidden');
    }
    return false;
  }

  function _anchorFor(target) {
    var el = target && target.nodeType === 1 ? target : null;
    while (el) {
      if (el.getAttribute && el.getAttribute('data-no-tooltip') === 'true') return null;
      if (!_isHiddenByChrome(el) && _textFor(el)) return el;
      el = el.parentElement;
    }
    return null;
  }

  function _describedBy(el, on) {
    if (!el || !el.getAttribute) return;
    var values = (el.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
    var index = values.indexOf(SURFACE_ID);
    if (on && index < 0) values.push(SURFACE_ID);
    if (!on && index >= 0) values.splice(index, 1);
    if (values.length) el.setAttribute('aria-describedby', values.join(' '));
    else el.removeAttribute('aria-describedby');
  }

  function _suppressTitle(el) {
    if (!el || !el.hasAttribute || !el.hasAttribute('title')) return;
    state.nativeTitle = el.getAttribute('title');
    el.removeAttribute('title');
  }

  function _restoreTitle() {
    if (state.anchor && state.nativeTitle !== null) {
      if (!state.anchor.hasAttribute('title')) state.anchor.setAttribute('title', state.nativeTitle);
    }
    state.nativeTitle = null;
  }

  function _removeNativeFallback(el) {
    if (!el || !el.getAttribute || !el.hasAttribute(OWNED_TITLE_ATTRIBUTE)) return;
    var ownedTitle = el.getAttribute(OWNED_TITLE_ATTRIBUTE);
    if (el.getAttribute('title') === ownedTitle) el.removeAttribute('title');
    el.removeAttribute(OWNED_TITLE_ATTRIBUTE);
  }

  function _applyNativeFallback(el) {
    if (!el || !el.getAttribute) return;
    var text = el.getAttribute('data-tooltip');
    if (!text) {
      _removeNativeFallback(el);
      return;
    }

    var ownedTitle = el.getAttribute(OWNED_TITLE_ATTRIBUTE);
    if (ownedTitle !== null) {
      if (el.getAttribute('title') !== ownedTitle) {
        // Another owner changed the title while the renderer was disabled.
        // Keep that genuine title and give up our ownership marker.
        el.removeAttribute(OWNED_TITLE_ATTRIBUTE);
        return;
      }
      if (ownedTitle !== text) {
        el.setAttribute('title', text);
        el.setAttribute(OWNED_TITLE_ATTRIBUTE, text);
      }
      return;
    }

    if (!el.hasAttribute('title')) {
      el.setAttribute('title', text);
      el.setAttribute(OWNED_TITLE_ATTRIBUTE, text);
    }
  }

  function _syncNativeFallbacks() {
    var doc = root.document;
    if (!doc || !doc.querySelectorAll) return;
    var controls = doc.querySelectorAll('[data-tooltip]');
    for (var i = 0; i < controls.length; i += 1) {
      if (state.enabled) _removeNativeFallback(controls[i]);
      else _applyNativeFallback(controls[i]);
    }
  }

  function _isConnected(el) {
    var doc = root.document;
    if (!el || !doc || el.ownerDocument !== doc) return false;
    if (typeof el.isConnected === 'boolean') return el.isConnected;
    return !!(doc.documentElement && doc.documentElement.contains(el));
  }

  function _disconnectAnchorObserver() {
    if (state.anchorObserver) state.anchorObserver.disconnect();
    state.anchorObserver = null;
  }

  function _observeAnchor(el) {
    _disconnectAnchorObserver();
    if (!root.MutationObserver || !el) return;
    state.anchorObserver = new root.MutationObserver(function () {
      if (state.anchor !== el || !state.surface || state.surface.getAttribute('aria-hidden') !== 'false') return;
      state.surface.textContent = _textFor(el);
      _position(el);
    });
    state.anchorObserver.observe(el, { attributes: true, attributeFilter: ['data-tooltip', 'title', 'aria-label'] });
  }

  function _position(anchor) {
    var surface = _surface();
    var doc = root.document;
    if (!surface || !doc || !anchor || !anchor.getBoundingClientRect) return;
    var win = doc.defaultView || root;
    var rect = anchor.getBoundingClientRect();
    surface.style.visibility = 'hidden';
    surface.style.left = '0px';
    surface.style.top = '0px';
    var tip = surface.getBoundingClientRect();
    var width = tip.width || 0;
    var height = tip.height || 0;
    var viewportWidth = win.innerWidth || doc.documentElement.clientWidth || 1024;
    var viewportHeight = win.innerHeight || doc.documentElement.clientHeight || 768;
    var below = viewportHeight - rect.bottom;
    var above = rect.top;
    var placement = below >= height + OFFSET_PX + EDGE_GUARD_PX || below >= above ? 'below' : 'above';
    var top = placement === 'below' ? rect.bottom + OFFSET_PX : rect.top - height - OFFSET_PX;
    var left = rect.left + (rect.width / 2) - (width / 2);
    left = Math.max(EDGE_GUARD_PX, Math.min(left, viewportWidth - width - EDGE_GUARD_PX));
    top = Math.max(EDGE_GUARD_PX, Math.min(top, viewportHeight - height - EDGE_GUARD_PX));
    surface.style.left = Math.round(left) + 'px';
    surface.style.top = Math.round(top) + 'px';
    surface.setAttribute('data-placement', placement);
    surface.style.visibility = 'visible';
  }

  function _hide() {
    _clearTimer();
    _disconnectAnchorObserver();
    if (state.anchor) _describedBy(state.anchor, false);
    _restoreTitle();
    var surface = state.surface || _surface();
    if (surface) {
      surface.setAttribute('aria-hidden', 'true');
      surface.style.visibility = 'hidden';
      surface.style.opacity = '0';
      surface.textContent = '';
    }
    state.anchor = null;
  }

  function _show(el, text) {
    if (!state.enabled || state.chromeHidden || !el || !text) return;
    var surface = _surface();
    if (!surface) return;
    state.anchor = el;
    _suppressTitle(el);
    surface.textContent = text;
    surface.setAttribute('aria-hidden', 'false');
    surface.style.opacity = '1';
    _describedBy(el, true);
    _position(el);
    _observeAnchor(el);
  }

  function _arm(el) {
    if (!state.enabled || state.chromeHidden || !el) return;
    _clearTimer();
    if (state.anchor && state.anchor !== el) _hide();
    state.anchor = el;
    var text = _textFor(el);
    if (!text) return;
    state.timerId = setTimeout(function () {
      state.timerId = null;
      if (state.anchor === el) _show(el, _textFor(el));
    }, state.delayMs);
  }

  function _sameOrInside(el, other) {
    return !!(el && other && (el === other || el.contains(other)));
  }

  function _onMouseOver(event) {
    var anchor = _anchorFor(event.target);
    if (anchor && !_sameOrInside(anchor, event.relatedTarget)) _arm(anchor);
  }

  function _onMouseOut(event) {
    var anchor = state.anchor;
    if (anchor && !_sameOrInside(anchor, event.relatedTarget)) _hide();
  }

  function _onFocusIn(event) {
    var anchor = _anchorFor(event.target);
    if (anchor) _arm(anchor);
  }

  function _onFocusOut(event) {
    if (state.anchor && !_sameOrInside(state.anchor, event.relatedTarget)) _hide();
  }

  function _onBodyClassChange() {
    var body = root.document && root.document.body;
    if (body && /(^|\s)(spine-dragging|dragging|chat-dragging)(\s|$)/.test(body.className)) _hide();
  }

  function _onDomChange() {
    if (state.anchor && !_isConnected(state.anchor)) _hide();
    if (!state.enabled) _syncNativeFallbacks();
    _onBodyClassChange();
  }

  function _listen(target, type, handler, options) {
    if (!target || !target.addEventListener) return;
    target.addEventListener(type, handler, options || false);
    state.listeners.push({ target: target, type: type, handler: handler, options: options || false });
  }

  function _bindBodyObserver() {
    if (!root.MutationObserver || !root.document || !root.document.body || state.bodyObserver) return;
    state.bodyObserver = new root.MutationObserver(_onDomChange);
    state.bodyObserver.observe(root.document.body, {
      attributes: true,
      attributeFilter: ['class', 'data-tooltip', 'title'],
      childList: true,
      subtree: true
    });
  }

  function init(options) {
    options = options || {};
    if (options.delayMs !== undefined) state.delayMs = Math.max(0, Number(options.delayMs) || 0);
    if (options.enabled === false) state.enabled = false;
    if (state.initialized) return api;
    state.initialized = true;
    var doc = root.document;
    _surface();
    _listen(doc, 'mouseover', _onMouseOver);
    _listen(doc, 'mouseout', _onMouseOut);
    _listen(doc, 'focusin', _onFocusIn);
    _listen(doc, 'focusout', _onFocusOut);
    _listen(doc, 'click', _hide, true);
    _listen(root, 'scroll', _hide, true);
    _listen(doc, 'keydown', function (event) { if (event.key === 'Escape') _hide(); });
    _listen(doc, 'dragstart', _hide);
    _listen(doc, 'ora-toolbar:chrome-hidden', function () { state.chromeHidden = true; _hide(); });
    _listen(doc, 'ora-toolbar:chrome-shown', function () { state.chromeHidden = false; });
    _bindBodyObserver();
    if (doc && !doc.body && doc.addEventListener) _listen(doc, 'DOMContentLoaded', function () { _surface(); _bindBodyObserver(); });
    _syncNativeFallbacks();
    return api;
  }

  function enable() { state.enabled = true; _syncNativeFallbacks(); return api; }
  function disable() { state.enabled = false; _hide(); _syncNativeFallbacks(); return api; }
  function setDelay(ms) { state.delayMs = Math.max(0, Number(ms) || 0); return api; }
  function destroy() {
    _hide();
    state.listeners.forEach(function (item) { item.target.removeEventListener(item.type, item.handler, item.options); });
    state.listeners = [];
    if (state.bodyObserver) state.bodyObserver.disconnect();
    state.bodyObserver = null;
    if (state.surface && state.surface.parentNode) state.surface.parentNode.removeChild(state.surface);
    state.surface = null;
    state.initialized = false;
    return api;
  }

  var api = {
    init: init,
    enable: enable,
    disable: disable,
    setDelay: setDelay,
    isEnabled: function () { return state.enabled; },
    destroy: destroy,
    _state: state
  };
  root.OraTooltip = api;
})(typeof window !== 'undefined' ? window : this);
